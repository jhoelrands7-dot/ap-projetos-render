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

VERSAO = "extracao-orcamento v0.1 (2026-10-20; staging; sem OCR)"
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
- Se a informação for parcial ou indireta, ainda assim preencha e explique em "obs".

CAMPOS (categoria {categoria}):
{lista}

Responda SOMENTE com um JSON válido: uma lista [{{"id": "...", "valor": "...", "unidade": "...", "pagina": N, "evidencia": "...", "obs": "..."}}, ...]
TRECHOS:
\"\"\"
{trechos}
\"\"\""""


def _chama_ia(msgs, timeout=150, tentativas=2):
    """Mesma disciplina do ia.avaliar_classe_b: timeout + 1 retry. None se indisponível/falhou."""
    chave = os.environ.get("NVIDIA_API_KEY")
    if not chave:
        return None
    corpo = {"model": ia.MODELO, "messages": msgs, "max_tokens": 3500,
             "temperature": 0, "seed": 42, "stream": False}
    for _ in range(tentativas):
        req = urllib.request.Request(ia.ENDPOINT, data=json.dumps(corpo).encode(),
            headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except Exception as e:
            ia._registrar_falha(f"extracao: {type(e).__name__} {str(e)[:120]}")
    return None


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
    """Retorna {id: {valor, unidade, pagina, evidencia, obs, ia_ok}}"""
    sel = _selecionar_paginas(itens, paginas)
    trechos = "\n".join(f"[[PÁGINA {p.numero or 1}]]\n{p.texto}" for p in sel)
    lista = "\n".join(f'- {c["id"]}: campo "{c["campo"]}" — {(c["definicao"] or "")[:150]}'
                      + (f' (unidade típica: {c["unidade_ref"]})' if c["unidade_ref"] else "")
                      for c in itens)
    bruto = _chama_ia([{"role": "user", "content": PROMPT.format(categoria=cat, lista=lista, trechos=trechos)}])
    if bruto is None:
        return {c["id"]: {"ia_ok": False} for c in itens}
    out = {}
    for item in _parse_lista(bruto):
        if isinstance(item, dict) and item.get("id"):
            item["ia_ok"] = True
            out[str(item["id"]).strip()] = item
    for c in itens:
        out.setdefault(c["id"], {"ia_ok": True, "valor": "não encontrado", "obs": "IA não retornou este campo"})
    return out


def _revisar(fid, campo, res, paginas_norm):
    """Revisao anti-eco deterministica. Devolve (status, valor, unidade, pagina, evidencia, obs)."""
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
        ("Modelo de IA", ia.MODELO + (" (NVIDIA NIM; trechos enviados à NVIDIA)" if ia.disponivel() else " (SEM CHAVE - nada extraído)")),
        ("Executado (UTC)", datetime.now(timezone.utc).isoformat()),
        ("Resultado", "; ".join(f"{k}: {v}" for k, v in stats.items())),
        ("Falhas de IA nesta execução", str(ia.FALHAS)),
        ("Último erro de IA", str(ia.ULTIMO_ERRO)),
        ("Limites", "Sem OCR; revisão automática pega eco e evidência inexistente, mas deslocamento entre campos irmãos exige conferência humana; IA pode oscilar entre execuções."),
    ]
    for i, (a, b) in enumerate(linhas, 1):
        aud.cell(i, 1).value = a; aud.cell(i, 2).value = b
    wb.save(caminho_saida)
    return stats
