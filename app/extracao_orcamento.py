# -*- coding: utf-8 -*-
"""
Extracao de checklist de orcamento (modulo experimental, staging).

Fluxo: PDF do documento + XLSX do checklist (layout: aba "Checklist de
orcamento", cabecalho na linha 3, campos a partir da linha 4) ->
mesma planilha preenchida (valor, unidade, status, pagina, evidencia,
observacoes) + aba "Auditoria".

Metodo (mesmo validado offline em 2026-10-20):
1. Selecao de paginas por palavras-chave derivadas dos proprios campos.
2. IA (NVIDIA NIM, timeout 90s + 1 retry, temperature 0, seed 42) propoe
   valor/unidade/pagina/evidencia por campo, em lotes por categoria.
3. Revisao anti-eco DETERMINISTICA: a evidencia tem que existir
   literalmente no texto; valor nao pode repetir o nome do campo nem a
   definicao. O que nao confirma vira "Ambiguo" ou "Nao encontrado".
   (Deslocamento fino entre campos irmaos ainda exige conferencia humana.)

Limites declarados: sem OCR (PDF escaneado nao funciona); IA pode oscilar;
planilha de saida NAO e orcamento fechado.
"""
import json, os, re, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import auditoria, extratores, ia

VERSAO = "extracao-orcamento v0.2 (2026-10-20; staging; OpenRouter+NVIDIA; trava anti-deslocamento; sem OCR)"
ST_EXTRAIDO, ST_NAO, ST_AMBIGUO, ST_NAOVERIF = "Extraído", "Não encontrado", "Ambíguo", "Não verificado"

COLS = {"valor": "Valor extraído", "unidade": "Unidade encontrada", "status": "Status da extração",
        "pagina": "Página", "evidencia": "Trecho de evidência", "obs": "Observações"}

_STOP = set("""para com uma como que dos das seu sua isso este esta entre sobre deve devem ser ter tipo
tipo de cada qual quais mediante conforme quando onde pelo pela nos nas aos às the and or of for with shall""".split())


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def _palavras_chave(campos):
    kws = set()
    for c in campos:
        for w in re.findall(r"[A-Za-zÀ-ÿ0-9/³%.-]{4,}", (c["campo"] or "") + " " + (c["definicao"] or "")):
            w = _norm(w).strip(".-/")
            if len(w) >= 4 and w not in _STOP:
                kws.add(w)
    return kws


def _selecionar_paginas(campos, paginas, cap=28000):
    kws = _palavras_chave(campos)
    sel = []
    for p in paginas:
        t = _norm(p.texto)
        hits = sum(1 for k in kws if k in t)
        if hits:
            sel.append((hits, p))
    sel.sort(key=lambda x: -x[0])
    esc, tot = [], 0
    for _, p in sorted(sel, key=lambda x: x[1].numero or 0):
        if tot + len(p.texto) > cap:
            continue
        esc.append(p); tot += len(p.texto)
    if not esc:
        for p in paginas:
            if tot + len(p.texto) > cap:
                break
            esc.append(p); tot += len(p.texto)
    return esc


PROMPT = """Você extrai especificações de um documento técnico para um checklist de orçamento.
Abaixo estão TRECHOS do documento, com marcadores [[PÁGINA N]].

Para CADA campo listado, responda se a informação existe NOS TRECHOS.
Regras duras:
- Não invente. Se a informação não estiver nos trechos, use valor="não encontrado".
- Se houver, copie o valor EXATO como está no texto (sem traduzir, sem converter), a unidade como está no texto,
  o número da página (do marcador) e uma evidência curta (até 20 palavras, COPIADA literalmente do trecho).
- A evidência é obrigatória para qualquer valor preenchido.
- Se houver mais de uma opção (ex.: "AISI 304 ou 316"), copie as opções como estão.
- ATENÇÃO ao deslocamento entre campos irmãos: o valor tem que pertencer ao campo pedido
  (ex.: não coloque a tensão no campo de potência). A evidência DEVE conter o próprio valor.
- Se a informação for parcial ou indireta, ainda assim preencha e explique em "obs".

CAMPOS (categoria {categoria}):
{lista}

Responda SOMENTE com um JSON válido: uma lista [{{"id": "...", "valor": "...", "unidade": "...", "pagina": N, "evidencia": "...", "obs": "..."}}, ...]
TRECHOS:
\"\"\"
{trechos}
\"\"\""""


def _chama_ia(msgs, timeout=150, tentativas=2):
    """Cadeia OpenRouter -> NVIDIA (ia.chamar_chat). None se indisponível/falhou."""
    conteudo, _prov = ia.chamar_chat(msgs, max_tokens=2200, timeout=timeout, tentativas=tentativas)
    return conteudo


def _parse_lista(conteudo):
    i = conteudo.find("[")
    if i < 0:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(conteudo[i:])
        return obj if isinstance(obj, list) else []
    except ValueError:
        return []


def _extrair_categoria(cat, itens, paginas):
    """Retorna {id: {valor, unidade, pagina, evidencia, obs, ia_ok}}.
    Lotes de ate 8 campos por chamada: o NIM gratuito estoura timeout em
    prompts/saidas grandes; lotes menores concluem dentro do timeout."""
    out = {}
    for i in range(0, len(itens), 8):
        lote = itens[i:i + 8]
        sel = _selecionar_paginas(lote, paginas, cap=12000)
        trechos = "\n".join(f"[[PÁGINA {p.numero or 1}]]\n{p.texto}" for p in sel)
        lista = "\n".join(f'- {c["id"]}: campo "{c["campo"]}" — {(c["definicao"] or "")[:120]}'
                          + (f' (unidade típica: {c["unidade_ref"]})' if c["unidade_ref"] else "")
                          for c in lote)
        bruto = _chama_ia([{"role": "user", "content": PROMPT.format(categoria=cat, lista=lista, trechos=trechos)}],
                          timeout=120, tentativas=3)
        if bruto is None:
            out.update({c["id"]: {"ia_ok": False} for c in lote})
            continue
        achou = {}
        for item in _parse_lista(bruto):
            if isinstance(item, dict) and item.get("id"):
                item["ia_ok"] = True
                achou[str(item["id"]).strip()] = item
        for c in lote:
            out[c["id"]] = achou.get(c["id"], {"ia_ok": True, "_sem_resposta": True})
    return out


# Padroes de "tipo de valor" para a trava anti-deslocamento: se o campo pede
# um tipo e o valor claramente parece OUTRO tipo, e deslocamento de linha.
_TIPOS_VALOR = [
    ("protecao_ip", re.compile(r"\bip\s?\d{2}\b", re.I)),
    ("isolamento", re.compile(r"\b(clase|classe)\s+[abefh]\b", re.I)),
    ("ruido", re.compile(r"\d+\s?db\b", re.I)),
    ("tensao", re.compile(r"\d{3}\s?(/|o|e)?\s?\d{0,3}\s?v\b", re.I)),
    ("frequencia", re.compile(r"\d+\s?hz\b", re.I)),
    ("fases", re.compile(r"\b(mono|bi|tri)?f[aá]s", re.I)),
    ("polos", re.compile(r"\d+\s*(o|ou)?\s*\d*\s?polos?\b", re.I)),
    ("rotacao", re.compile(r"\d+\s?rpm\b", re.I)),
    ("potencia", re.compile(r"\d+[.,]?\d*\s?(kw|cv|hp|w)\b", re.I)),
    ("corrente", re.compile(r"\d+[.,]?\d*\s?a\b(?!si)", re.I)),
    ("vazao", re.compile(r"\d+[.,]?\d*\s?(l/s|l/min|m3/h|m³/h|gpm)\b", re.I)),
    ("pressao", re.compile(r"\d+[.,]?\d*\s?(bar|mca|psi|kgf|mpa|kpa|pa)\b", re.I)),
    ("temperatura", re.compile(r"\d+\s?°[cf]\b", re.I)),
]
_TIPO_CAMPO = [
    ("protecao_ip", re.compile(r"prote[cç][aã]o|grau de prote", re.I)),
    ("isolamento", re.compile(r"isolamento", re.I)),
    ("ruido", re.compile(r"ru[ií]do|n[ií]vel de som|sonoro", re.I)),
    ("tensao", re.compile(r"tens[aã]o|voltagem", re.I)),
    ("frequencia", re.compile(r"frequ[eê]ncia", re.I)),
    ("fases", re.compile(r"fases", re.I)),
    ("polos", re.compile(r"polos", re.I)),
    ("rotacao", re.compile(r"rota[cç][aã]o|velocidade de giro", re.I)),
    ("potencia", re.compile(r"pot[eê]ncia", re.I)),
    ("corrente", re.compile(r"corrente|amperagem", re.I)),
    ("vazao", re.compile(r"vaz[aã]o|caudal", re.I)),
    ("pressao", re.compile(r"press[aã]o|amt|altura manom[eé]trica", re.I)),
    ("temperatura", re.compile(r"temperatura", re.I)),
]


def _tipo_de(texto, regras):
    for nome, rx in regras:
        if rx.search(texto or ""):
            return nome
    return None


def _tokens_distintivos(valor):
    """Numeros e codigos com digitos (IP55 -> ip55, 416, 1.15...) + palavras >=4 letras."""
    v = _norm(valor)
    nums = re.findall(r"\d+[.,]?\d*", v)
    palavras = [w for w in re.findall(r"[a-z]{4,}", v) if w not in _STOP]
    return nums, palavras


def _valor_na_vizinhanca(valor, evid, texto_pagina):
    """O valor (seus tokens distintivos) aparece na evidencia ou numa janela de 80 chars em volta dela?"""
    nums, palavras = _tokens_distintivos(valor)
    if not nums and not palavras:
        return True  # valor vago demais para julgar; outras regras cuidam
    ne = _norm(evid)
    janela = ne
    if texto_pagina is not None and ne and ne in texto_pagina:
        i = texto_pagina.find(ne)
        janela = texto_pagina[max(0, i - 80): i + len(ne) + 80]
    ok_num = all(n in janela for n in nums) if nums else True
    if palavras:
        hits = sum(1 for w in palavras if w in janela)
        ok_pal = hits >= max(1, (len(palavras) + 1) // 2)
    else:
        ok_pal = True
    return ok_num and ok_pal


def _revisar(fid, campo, res, paginas_norm):
    """Revisao anti-eco + anti-deslocamento deterministica. Devolve (status, valor, unidade, pagina, evidencia, obs)."""
    valor = str(res.get("valor") or "").strip()
    unidade = str(res.get("unidade") or "").strip()
    evid = str(res.get("evidencia") or "").strip()
    obs = str(res.get("obs") or "").strip()
    pagina = res.get("pagina")
    try:
        pagina = int(pagina) if pagina not in (None, "", "-") else None
    except (TypeError, ValueError):
        pagina = None
    if not res.get("ia_ok"):
        return ST_NAOVERIF, "", "", None, "", "IA indisponível nesta execução (falha de rede/timeout); campo não verificado"
    if res.get("_sem_resposta"):
        return ST_NAOVERIF, "", "", None, "", "IA não retornou este campo nesta execução (falha da IA, NÃO significa ausência no documento); campo não verificado"
    neg = ("", "nao encontrado", "nao encontrada", "not found", "n/a", "na",
           "no encontrado", "no encontrada", "no se menciona", "no especificado",
           "no especifica", "sin informacion", "sin datos", "no consta", "no aplica")
    nv0 = _norm(valor)
    if nv0 in neg or any(nv0.startswith(n) and len(nv0) < len(n) + 40 for n in neg if n):
        return ST_NAO, "", "", None, "", obs
    # eco: valor repete o nome do campo ou a definicao
    nv, nc, nd = _norm(valor), _norm(campo["campo"]), _norm(campo["definicao"])
    if (nc and nc in nv) or (nd and len(nd) > 15 and nd in nv):
        return ST_AMBIGUO, valor, unidade, None, "", (obs + " | " if obs else "") + \
            "Revisão automática: valor repete o nome/definição do campo (possível eco da IA) — conferir no documento"
    # evidencia precisa existir literalmente em alguma pagina
    ne = _norm(evid)
    if len(ne) < 8:
        return ST_AMBIGUO, valor, unidade, None, "", (obs + " | " if obs else "") + \
            "Revisão automática: IA não forneceu evidência verificável — conferir no documento"
    achada = [n for n, t in paginas_norm if ne in t]
    if not achada:
        return ST_AMBIGUO, valor, unidade, None, evid, (obs + " | " if obs else "") + \
            "Revisão automática: evidência não localizada no texto extraído — conferir no documento"
    # trava 1: tipo do valor incompativel com o tipo do campo (deslocamento entre irmaos)
    tipo_campo = _tipo_de((campo["campo"] or "") + " " + (campo["definicao"] or "")[:80], _TIPO_CAMPO)
    tipo_valor = _tipo_de(valor + " " + unidade, _TIPOS_VALOR)
    if tipo_campo and tipo_valor and tipo_campo != tipo_valor:
        return ST_AMBIGUO, valor, unidade, achada[0], evid, (obs + " | " if obs else "") + \
            f"Revisão automática: valor parece '{tipo_valor}' mas o campo pede '{tipo_campo}' (possível deslocamento entre campos) — conferir no documento"
    # trava 2: o valor tem que constar na evidencia (ou numa janela de 80 chars em volta)
    texto_pag = dict(paginas_norm).get(achada[0])
    if not _valor_na_vizinhanca(valor, evid, texto_pag):
        return ST_AMBIGUO, valor, unidade, achada[0], evid, (obs + " | " if obs else "") + \
            "Revisão automática: valor não consta na evidência apontada (possível deslocamento entre campos) — conferir no documento"
    if pagina not in achada:
        obs = (obs + " | " if obs else "") + f"Página corrigida pela revisão automática (IA disse {pagina})"
        pagina = achada[0]
    return ST_EXTRAIDO, valor, unidade, pagina, evid, obs


def ler_checklist(caminho_xlsx):
    import openpyxl
    wb = openpyxl.load_workbook(caminho_xlsx)
    ws = wb["Checklist de orçamento"] if "Checklist de orçamento" in wb.sheetnames else wb.active
    idx = {}
    for col in range(1, ws.max_column + 1):
        h = ws.cell(3, col).value
        for k, rotulo in COLS.items():
            nh, nr = _norm(h), _norm(rotulo)
            if h and (nh == nr or (nr and nr in nh)):
                idx.setdefault(k, col)
    faltam = [r for k, r in COLS.items() if k not in idx]
    if faltam:
        raise ValueError("Checklist fora do layout esperado: colunas não achadas na linha 3: " + ", ".join(faltam))
    campos = []
    for r in range(4, ws.max_row + 1):
        if ws.cell(r, 1).value:
            campos.append({"linha": r, "id": str(ws.cell(r, 1).value).strip(),
                           "categoria": str(ws.cell(r, 2).value or "").strip(),
                           "campo": str(ws.cell(r, 3).value or "").strip(),
                           "definicao": str(ws.cell(r, 4).value or ""),
                           "unidade_ref": str(ws.cell(r, 5).value or "")})
    return wb, ws, idx, campos


def executar(caminho_pdf, caminho_xlsx, caminho_saida):
    """Roda a extracao completa. Retorna stats para a UI/auditoria."""
    doc = extratores.extrair(caminho_pdf)
    if not doc.paginas or len(doc.texto_completo.strip()) < 100:
        raise ValueError("Documento sem texto extraível (sem OCR neste MVP: PDF escaneado não funciona).")
    paginas_norm = [(p.numero or 1, _norm(p.texto)) for p in doc.paginas]
    wb, ws, idx, campos = ler_checklist(caminho_xlsx)
    cats = {}
    for c in campos:
        cats.setdefault(c["categoria"], []).append(c)

    def trabalho(cat_itens):
        cat, itens = cat_itens
        if re.search(r"revis[aã]o|pend[eê]ncia|gest[aã]o", _norm(cat)):
            return cat, {c["id"]: {"ia_ok": False, "gestao": True} for c in itens}
        return cat, _extrair_categoria(cat, itens, doc.paginas)

    resultados = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        for cat, res in ex.map(trabalho, cats.items()):
            resultados.update(res)

    stats = {ST_EXTRAIDO: 0, ST_NAO: 0, ST_AMBIGUO: 0, ST_NAOVERIF: 0}
    for c in campos:
        res = resultados.get(c["id"]) or {"ia_ok": False}
        if res.get("gestao"):
            status, valor, unidade, pagina, evid, obs = ST_NAOVERIF, "", "", None, "", \
                "Campo de gestão do checklist (revisão/aprovação), não consta do documento técnico"
        else:
            status, valor, unidade, pagina, evid, obs = _revisar(c["id"], c, res, paginas_norm)
        stats[status] += 1
        ws.cell(c["linha"], idx["valor"]).value = valor or None
        ws.cell(c["linha"], idx["unidade"]).value = unidade or None
        ws.cell(c["linha"], idx["status"]).value = status
        ws.cell(c["linha"], idx["pagina"]).value = pagina
        ws.cell(c["linha"], idx["evidencia"]).value = evid or None
        ws.cell(c["linha"], idx["obs"]).value = obs or None

    aud = wb.create_sheet("Auditoria") if "Auditoria" not in wb.sheetnames else wb["Auditoria"]
    linhas = [
        ("Auditoria da extração", ""),
        ("Versão", VERSAO),
        ("Documento (arquivo)", os.path.basename(caminho_pdf)),
        ("SHA-256 do documento", auditoria.sha256_arquivo(caminho_pdf)),
        ("Checklist (arquivo)", os.path.basename(caminho_xlsx)),
        ("SHA-256 do checklist", auditoria.sha256_arquivo(caminho_xlsx)),
        ("Modelo de IA", (ia.ULTIMO_PROVEDOR or "nenhum (sem chave ou todas as chamadas falharam)") + "; cadeia: OpenRouter (OPENROUTER_API_KEY) → NVIDIA NIM (NVIDIA_API_KEY); trechos enviados ao provedor externo"),
        ("Executado (UTC)", datetime.now(timezone.utc).isoformat()),
        ("Resultado", "; ".join(f"{k}: {v}" for k, v in stats.items())),
        ("Falhas de IA nesta execução", str(ia.FALHAS)),
        ("Último erro de IA", str(ia.ULTIMO_ERRO)),
        ("Limites", "Sem OCR; revisão automática pega eco, evidência inexistente, tipo de valor incompatível e valor fora da evidência (anti-deslocamento), mas não substitui conferência humana; IA pode oscilar entre execuções e provedores."),
    ]
    for i, (a, b) in enumerate(linhas, 1):
        aud.cell(i, 1).value = a; aud.cell(i, 2).value = b
    wb.save(caminho_saida)
    return stats
