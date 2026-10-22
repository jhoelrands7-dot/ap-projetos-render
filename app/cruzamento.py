# -*- coding: utf-8 -*-
"""
Cruzamento entre documentos do mesmo projeto (Módulo 2 experimental, staging).

Ideia: 2 a 5 PDFs de disciplinas/tipos diferentes (ex.: memorial descritivo,
memória de cálculo, planilha orçamentária, projeto elétrico). Para cada
documento a IA extrai os ITENS QUANTIFICADOS (valor + unidade + página +
evidência literal) e o sistema cruza os itens com o mesmo rótulo entre os
documentos: valores iguais viram convergência; valores diferentes viram
divergência PARA CONFIRMAR (nunca veredito automático). Também cruza tags de
equipamento (P-101, TQ-02...) e o CNPJ do proprietário.

Limites declarados (mostrados na tela):
- Só PDF com camada de texto. Sem OCR: PDF escaneado não funciona.
- Planta/fluxograma: o que está ESCRITO entra (carimbo, legenda, tags,
  notas); o DESENHO em si (linhas, símbolos, geometria) não é interpretado.
- O cruzamento é por rótulo de item: itens com nomes muito diferentes entre
  documentos podem não casar ("sem correspondente") — revisão humana.
- A IA pode oscilar; toda divergência é hipótese para o engenheiro confirmar,
  com a evidência dos dois lados na tela.
"""
import json, os, re, time, unicodedata
from datetime import datetime, timezone

import auditoria, extratores, ia
import visao

VERSAO = ("cruzamento v0.1.0 (2026-10-22; staging; Módulo 2 experimental: "
          "cruzamento de itens quantificados, tags e CNPJ entre 2-5 PDFs de texto; "
          "anti-eco de evidência; sem OCR; leitura visual experimental de páginas de desenho "
          "(modelo de visão, itens marcados como hipótese; confirmação humana na imagem)")

MAX_DOCS = 5
CAP_TEXTO = 28000  # por documento, como na extração de orçamento

_STOP = set("""de da do das dos e em para com uma um ao à a o as os no na nos nas que por
sobre entre conforme cada tipo ser ter the and or of for with""".split())

_ALIASES_UNID = {
    "m²": "m2", "m^2": "m2", "m2": "m2", "metro quadrado": "m2", "metros quadrados": "m2", "mq": "m2",
    "m³": "m3", "m^3": "m3", "m3": "m3", "metro cubico": "m3", "metros cubicos": "m3",
    "m linear": "m", "ml": "m", "metro linear": "m", "metro": "m", "metros": "m", "m": "m",
    "mm": "mm", "milimetro": "mm", "milimetros": "mm", "cm": "cm", "km": "km",
    "kg": "kg", "kgf": "kgf", "t": "t", "ton": "t", "tonelada": "t", "toneladas": "t",
    "kw": "kw", "w": "w", "cv": "cv", "hp": "hp", "kva": "kva", "va": "va",
    "v": "v", "volt": "v", "volts": "v", "a": "a", "ampere": "a", "amperes": "a",
    "hz": "hz", "rpm": "rpm", "l": "l", "litro": "l", "litros": "l",
    "l/s": "l/s", "l/min": "l/min", "m3/h": "m3/h", "m³/h": "m3/h", "gpm": "gpm",
    "bar": "bar", "mca": "mca", "psi": "psi", "kpa": "kpa", "mpa": "mpa", "pa": "pa",
    "kgf/cm2": "kgf/cm2", "kgf/cm²": "kgf/cm2", "°c": "°c", "°f": "°f",
    "un": "un", "unidade": "un", "unidades": "un", "pç": "un", "pc": "un",
    "vb": "vb", "vez": "vb", "dias": "dias", "dia": "dias", "meses": "meses", "mes": "meses",
    "h": "h", "hora": "h", "horas": "h", "%": "%",
}


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def _norm_unid(u):
    n = _norm(u).replace(" ", " ") if u else ""
    n = re.sub(r"\s+", " ", n)
    return _ALIASES_UNID.get(n, _ALIASES_UNID.get(n.replace(" ", ""), n.replace(" ", "")))


def _chave_item(rotulo):
    """Chave de casamento: conjunto de palavras (ordem não importa), sem stopwords."""
    toks = [t for t in re.findall(r"[a-z0-9]{3,}", _norm(rotulo)) if t not in _STOP]
    genericos = {"item", "valor", "total", "quantidade", "qtde", "servico", "execucao", "projeto"}
    toks = [t for t in toks if t not in genericos]
    return " ".join(sorted(set(toks)))


def _parse_num(v):
    """'70,00' -> 70.0 ; '1.234,56' -> 1234.56 ; '70.00' -> 70.0 ; None se não-numérico."""
    if v is None:
        return None
    s = str(v).strip().replace("\xa0", " ")
    s = re.sub(r"[^\d.,-]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")  # 1.234,56
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif re.match(r"^-?\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")  # 1.234 (milhar pt-BR, sem decimais)
    try:
        return float(s)
    except ValueError:
        return None


TAG_RX = re.compile(r"\b[A-Z]{1,4}-\d{1,4}[A-Z]?(?:/[A-Z0-9]+)?\b")
CNPJ_RX = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")

PROMPT = """Você extrai ITENS QUANTIFICADOS de um documento de engenharia para cruzar com
outros documentos do mesmo projeto (ex.: memória de cálculo x planilha orçamentária
x memorial descritivo x projeto elétrico).

Abaixo está o TEXTO do documento "{nome}", com marcadores [[PÁGINA N]].

Extraia CADA item que tenha valor numérico explícito no texto: quantitativos de serviços
(áreas, volumes, extensões, contagens), especificações com valor (potência, tensão, vazão,
pressão, espessura, diâmetro), prazos e dimensões.

Regras duras:
- Não invente. Só itens com número escrito no texto.
- "item": rótulo canônico curto, minúsculo, sem acento, do genérico para o específico
  (ex.: "area limpeza terreno", "extensao muro", "volume escavacao", "potencia bomba",
  "tensao alimentacao", "quantidade banheiros", "espessura geomembrana").
- "valor": só o número, como está (ex.: "70,00"). "unidade": como está no texto (ex.: "m²").
- "pagina": número do marcador [[PÁGINA N]] onde está o item.
- "evidencia": trecho curto (até 15 palavras) COPIADO literalmente do texto, contendo o valor.
- Sem evidência literal, não inclua o item.
- No máximo 80 itens, os mais relevantes para comparar entre documentos.

Responda SOMENTE com um JSON válido: uma lista [{{"item": "...", "valor": "...", "unidade": "...", "pagina": N, "evidencia": "..."}}, ...]

TEXTO:
\"\"\"
{trechos}
\"\"\""""


def _montar_trechos(doc):
    partes, tot = [], 0
    for p in doc.paginas:
        bloco = f"[[PÁGINA {p.numero or 1}]]\n{p.texto}"
        if tot + len(bloco) > CAP_TEXTO:
            break
        partes.append(bloco)
        tot += len(bloco)
    return "\n".join(partes), tot


def _chama_ia_json(msgs, max_tokens=4000, timeout=150, tentativas=3):
    """1 chamada + 1 retentativa se vier vazia/inparseável (anti falha silenciosa)."""
    bruto = ia.chamar_chat(msgs, max_tokens=max_tokens, timeout=timeout, tentativas=tentativas)[0]
    if bruto:
        i = bruto.find("[")
        if i >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(bruto[i:])
                if isinstance(obj, list) and obj:
                    return obj, bruto
            except ValueError:
                pass
    ia._registrar_falha("cruzamento: resposta da IA vazia ou JSON inválido; retentando uma vez")
    time.sleep(8)
    bruto = ia.chamar_chat(msgs, max_tokens=max_tokens, timeout=timeout, tentativas=tentativas)[0]
    if bruto:
        i = bruto.find("[")
        if i >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(bruto[i:])
                if isinstance(obj, list):
                    return obj, bruto
            except ValueError:
                pass
    return [], bruto


def _extrair_doc(idx, caminho, nome, disciplina, avisos):
    doc = extratores.extrair_pdf(caminho)
    sha = auditoria.sha256_arquivo(caminho)
    paginas_sem_texto = [p.numero for p in doc.paginas if len((p.texto or "").strip()) < 20]
    paginas_desenho = [p.numero for p in doc.paginas
                       if (len((p.texto or "").strip()) < 200 and p.num_imagens > 0)
                       or (p.num_vetores >= 150 and len((p.texto or "").strip()) < 1500)]
    if len(paginas_sem_texto) == doc.num_paginas:
        avisos.append(f"'{nome}': nenhuma página com texto legível — PDF escaneado ou só desenho. "
                      "Sem OCR, este documento não entra no cruzamento.")
    elif paginas_desenho:
        avisos.append(f"'{nome}': página(s) {', '.join(map(str, paginas_desenho[:8]))} parecem desenho — "
                      "o que está escrito entra no cruzamento e a leitura visual experimental tenta "
                      "identificar os elementos do desenho (hipótese).")
    trechos, tot = _montar_trechos(doc)
    if sum(len(p.texto or "") for p in doc.paginas) > tot:
        avisos.append(f"'{nome}': documento grande — analisadas as primeiras páginas até {CAP_TEXTO//1000} mil caracteres.")
    texto_norm = _norm(doc.texto_completo)
    itens_brutos, bruto = _chama_ia_json([{"role": "user", "content": PROMPT.format(nome=nome, trechos=trechos)}])
    if bruto:
        ia.ULTIMAS_BRUTAS.append(bruto[:2000])
    itens = []
    vistos = set()
    for it in itens_brutos[:120]:
        if not isinstance(it, dict):
            continue
        rotulo = (it.get("item") or "").strip()
        valor = str(it.get("valor") or "").strip()
        if not rotulo or not valor:
            continue
        evid = (it.get("evidencia") or "").strip()[:400]
        pag = it.get("pagina")
        try:
            pag = int(pag)
        except (TypeError, ValueError):
            pag = None
        chave = _chave_item(rotulo)
        if not chave:
            continue
        dedup = (chave, _norm(valor), _norm_unid(it.get("unidade")))
        if dedup in vistos:
            continue
        vistos.add(dedup)
        ev_ok = bool(evid) and _norm(evid) in texto_norm
        itens.append({
            "rotulo": rotulo, "chave": chave,
            "valor": valor, "valor_num": _parse_num(valor),
            "unidade": (it.get("unidade") or "").strip(), "unidade_norm": _norm_unid(it.get("unidade")),
            "pagina": pag, "evidencia": evid, "evidencia_ok": ev_ok, "origem": "texto",
        })
    # --- leitura VISUAL experimental das páginas de desenho (hipótese) ---
    if visao.ativo():
        pags_desenho = sorted(set(paginas_sem_texto) | set(paginas_desenho))[:visao.MAX_PAGINAS_VISAO]
        n_visao = 0
        for pnum in pags_desenho:
            vistos_pg, erro = visao.extrair_pagina_visao(caminho, pnum)
            if erro:
                avisos.append(f"'{nome}': página {pnum}: leitura visual não concluída ({erro}).")
                continue
            for it in vistos_pg:
                chave = _chave_item(it["rotulo"])
                if not chave:
                    continue
                dedup = ("visao", chave, _norm(it["valor"]), _norm_unid(it["unidade"]))
                if dedup in vistos:
                    continue
                vistos.add(dedup)
                itens.append({
                    "rotulo": it["rotulo"], "chave": chave,
                    "valor": it["valor"], "valor_num": _parse_num(it["valor"]),
                    "unidade": it["unidade"], "unidade_norm": _norm_unid(it["unidade"]),
                    "pagina": pnum, "evidencia": it["evidencia"],
                    "evidencia_ok": None, "origem": "visao",
                })
                n_visao += 1
        if n_visao:
            avisos.append(f"'{nome}': {n_visao} item(ns) lidos por VISÃO nas páginas de desenho "
                          f"({', '.join(map(str, pags_desenho))}) — hipótese de modelo de visão; "
                          "confira na imagem antes de usar.")
    tags = sorted(set(m.group(0) for m in TAG_RX.finditer(doc.texto_completo)))
    cnpjs = sorted(set(m.group(0) for m in CNPJ_RX.finditer(doc.texto_completo)))
    return {
        "idx": idx, "nome": nome, "disciplina": disciplina, "sha256": sha,
        "paginas": doc.num_paginas, "paginas_sem_texto": paginas_sem_texto,
        "paginas_desenho": paginas_desenho,
        "itens": itens, "tags": tags, "cnpjs": cnpjs,
    }


def _cruzar(documentos):
    # --- itens quantificados ---
    grupos = {}
    for d in documentos:
        for it in d["itens"]:
            grupos.setdefault(it["chave"], []).append((d["idx"], it))
    itens_cruz = []
    for chave, occs in sorted(grupos.items()):
        docs_distintos = sorted({i for i, _ in occs})
        rotulo = occs[0][1]["rotulo"]
        if len(docs_distintos) < 2:
            status = "sem_correspondente"
        else:
            # dedup dentro do mesmo documento: fica a 1ª ocorrência por doc
            por_doc = {}
            for i, it in occs:
                por_doc.setdefault(i, it)
            vals = [it["valor_num"] for it in por_doc.values()]
            unids = [it["unidade_norm"] for it in por_doc.values()]
            num_ok = all(v is not None for v in vals)
            mesma_unid = len(set(unids)) <= 1
            if num_ok and len(set(vals)) == 1 and mesma_unid:
                status = "converge"
            elif not num_ok and len({_norm(it["valor"]) for it in por_doc.values()}) == 1 and mesma_unid:
                status = "converge"
            else:
                status = "diverge"
        itens_cruz.append({
            "chave": chave, "rotulo": rotulo, "status": status,
            "ocorrencias": [{
                "doc": i, "valor": it["valor"], "unidade": it["unidade"],
                "pagina": it["pagina"], "evidencia": it["evidencia"],
                "evidencia_ok": it["evidencia_ok"], "origem": it.get("origem", "texto"),
            } for i, it in occs],
        })
    # --- tags de equipamento ---
    tag_docs = {}
    for d in documentos:
        for t in d["tags"]:
            tag_docs.setdefault(t, set()).add(d["idx"])
    tags_cruz = [{"tag": t, "docs": sorted(ix),
                  "status": "compartilhada" if len(ix) >= 2 else "so_em_um"}
                 for t, ix in sorted(tag_docs.items())]
    # --- CNPJ ---
    cnpj_docs = {}
    for d in documentos:
        for c in d["cnpjs"]:
            cnpj_docs.setdefault(c, set()).add(d["idx"])
    return itens_cruz, tags_cruz, cnpj_docs


def executar(docs):
    """docs = [{"caminho", "nome", "disciplina"}] -> resultado auditável (dict)."""
    inicio = datetime.now(timezone.utc)
    avisos = []
    ia.reset_contadores()
    documentos = []
    for idx, d in enumerate(docs):
        documentos.append(_extrair_doc(idx, d["caminho"], d["nome"], d.get("disciplina") or "", avisos))
    itens_cruz, tags_cruz, cnpj_docs = _cruzar(documentos)
    resumo = {
        "convergencias": sum(1 for i in itens_cruz if i["status"] == "converge"),
        "divergencias_para_confirmar": sum(1 for i in itens_cruz if i["status"] == "diverge"),
        "itens_sem_correspondente": sum(1 for i in itens_cruz if i["status"] == "sem_correspondente"),
        "tags_compartilhadas": sum(1 for t in tags_cruz if t["status"] == "compartilhada"),
        "tags_sem_correspondente": sum(1 for t in tags_cruz if t["status"] == "so_em_um"),
    }
    fim = datetime.now(timezone.utc)
    return {
        "versao": VERSAO,
        "documentos": [{k: d[k] for k in ("idx", "nome", "disciplina", "sha256", "paginas",
                                          "paginas_sem_texto", "paginas_desenho", "tags", "cnpjs")}
                       | {"num_itens": len(d["itens"])} for d in documentos],
        "itens": itens_cruz,
        "tags": tags_cruz,
        "cnpjs": [{"cnpj": c, "docs": sorted(ix)} for c, ix in sorted(cnpj_docs.items())],
        "resumo": resumo,
        "avisos": avisos,
        "ia": ia.status() | {"provedor": ia.ULTIMO_PROVEDOR,
                             "respostas_brutas": list(ia.ULTIMAS_BRUTAS)},
        "execucao": {"inicio_utc": inicio.isoformat(), "fim_utc": fim.isoformat()},
    }
