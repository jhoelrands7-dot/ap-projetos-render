# -*- coding: utf-8 -*-
"""
Motor de regras - MVP Módulo 1 (verificação) - check-list FRM-SEMEC-001 Parecer Técnico.

Evolução do protótipo para documentos REAIS:
- PAD-1.1: seção de revisão aceita ÍNDICE/CONTROLE/HISTÓRICO DE REVISÕES.
- PAD-1.3: responsável técnico e CREA buscados no documento inteiro (rótulo com
  ou sem dois-pontos); detecta CREA em branco (template), CAU/ART/RRT citados.
- PAD-1.8: aceita "FOLHA x de y", "FOLHA x/y", "Página x/y", "Página x de y".
- DT-1.3: aceita seções REFERÊNCIAS / DOCUMENTOS APLICÁVEIS / NORMAS APLICÁVEIS.
O restante segue o protótipo (sem inventar itens de checklist).

Status: CONFORME, NÃO CONFORME, NÃO SE APLICA, EVIDÊNCIA INSUFICIENTE.
Classe B: SIMULADA por heurística determinística, sem API (não há chave de IA no
ambiente); ponto de troca isolado e rotulado. Classe C: nunca decidida pelo motor.
"""
import re
import ia
from checklist_parecer_tecnico import CHECKLIST

MOTOR_VERSAO = "motor-mvp v1.1 (2026-10-19)"

CONFORME = "CONFORME"
NAO_CONFORME = "NÃO CONFORME"
EVID_INSUFICIENTE = "EVIDÊNCIA INSUFICIENTE"
NAO_SE_APLICA = "NÃO SE APLICA"

RX_NUM_DOC = r"\b[A-Z]{2,3}-\d{4}\.\d{2}-\d{4}-\d{3}-[A-Z]{3}-\d{3}\b"
RX_CREA = r"\b[A-Z]{2}\s?\d{4,7}\b"
RX_OS = r"\b[A-Z]{2,4}(?:-[A-Z0-9]{2,6}){1,3}\b"
RX_NORMA = r"\b(?:ABNT\s?)?NBR\s?\d{3,5}\b|\bISO\s?\d{3,5}\b|\bASTM\s?[A-Z]?\s?\d{2,5}\b|\bAPI\s?\d{2,4}\b"
RX_TAG = r"(?<![-\w])(?!RL|PT|DE|INT)[A-Z]{2,4}-\d{1,4}\b"
# CREA em formatos reais: "CREA-SP 0601876945", "CREA nº 12.345", "CREA/GO 12345", "CREA-ES"
RX_CREA_REAL = r"\bCREA\b[\s\-/]*(?:[A-Z]{2})?[\s\-/]*(?:n[º°o\.]*\s*)?(\d[\d\.\-/]{3,}\d)"
RX_CREA_VAZIO = r"\bCREA\b[\s\-/]*(?:[A-Z]{2})?[\s\-/]*(?:n[º°o\.]*\s*)?(\.{4,}|_{4,}|\bXX+\b)"
RX_CAU = r"\bCAU\b[\s\-/]*(?:n[º°o\.]*\s*)?([A-Z]?\d[\d\.\-/]{2,}\w?)"

DISCIPLINAS = ["ELÉTRICA", "TUBULAÇÃO", "INSTRUMENTAÇÃO", "PROCESSO", "CIVIL",
               "MECÂNICA", "ESCANEAMENTO"]


def _ev(pagina, local, trecho):
    return {"pagina": pagina, "local": local, "trecho": trecho[:300]}


def _campo(doc, rotulo):
    for numero, nome, linha, m in doc.buscar(rf"\b{re.escape(rotulo)}\s*:\s*(.*)$"):
        valor = re.sub(r"\s{2}\[[^\]]*\]\s*$", "", m.group(1)).strip()
        return valor, _ev(numero, nome, linha)
    return None, None


def _resultado(item, secao, descricao, classe, status, obs, evidencias, decisao_por=None):
    if decisao_por is None:
        decisao_por = {"A": "regra determinística",
                       "B": "heurística determinística SIMULADA (sem API de IA no ambiente; ponto de troca para LLM)",
                       "C": "não decidido pelo motor (julgamento humano)"}[classe]
    return {"item": item, "secao": secao, "descricao": descricao,
            "classe": classe, "status": status, "observacao": obs,
            "decisao_por": decisao_por,
            "evidencias": [e for e in evidencias if e]}


# ---------------- PADRONIZAÇÃO ----------------

def pad_10(doc):
    evs = [_ev(num, n, l) for num, n, l, m in doc.buscar(r"\bFRM-[A-Z]{3,6}-\d{3}\b")]
    obs = ("Classe C: exige a base de templates vigentes da AP (dado externo ao "
           "documento). O motor só coleta a referência de formulário citada, se houver.")
    return EVID_INSUFICIENTE, obs, evs[:1]


def pad_11(doc):
    idx = doc.buscar(r"(?:[ÍI]NDICE|CONTROLE|HIST[ÓO]RICO)\s+DE\s+REVIS") or \
          doc.buscar(r"^\s*(?:[ÍI]NDICE\s+DE\s+)?REVIS[ÕO]ES\s*$")
    if not idx:
        return NAO_CONFORME, ("Seção de controle de revisões (índice/controle/histórico) "
                              "não encontrada; o padrão AP exige controle e descrição de revisão."), []
    ev_idx = _ev(idx[0][0], idx[0][1], idx[0][2])
    revs = doc.buscar(r"^\s*(?:REV\.?\s*)?(\d+)(?!\.)\s+(\S.{2,})$")
    entradas, sem_descricao = [], []
    for num, nome, linha, m in revs:
        desc = m.group(2).strip(" .")
        if "DESCRI" in desc.upper() and "REVIS" in doc.texto_completo.upper():
            continue
        entradas.append(_ev(num, nome, linha))
        if not desc or len(desc) < 3:
            sem_descricao.append(_ev(num, nome, linha))
    soltas = doc.buscar(r"^\s*REV\.?\s*\d+\s*$")
    for num, nome, linha, m in soltas:
        sem_descricao.append(_ev(num, nome, linha))
    if sem_descricao:
        return NAO_CONFORME, "Revisão sem descrição preenchida.", [ev_idx] + sem_descricao
    if not entradas:
        return NAO_CONFORME, "Seção de revisões localizada, mas sem entradas de revisão identificáveis.", [ev_idx]
    return CONFORME, "Controle de revisões presente e entradas com descrição.", [ev_idx] + entradas


def pad_12(doc):
    obs = ("SIMULADO (classe B): heurística só detecta a PRESENÇA de imagem; "
           "'atualizado' exige comparação visual com a base oficial de logos "
           "(IA de visão ou humano). Em produção: chamada a LLM de visão.")
    total_imgs = sum(p.num_imagens for p in doc.paginas)
    p1 = doc.paginas[0] if doc.paginas else None
    if total_imgs == 0:
        return NAO_CONFORME, "Nenhum logotipo/imagem detectado no documento. " + obs, []
    if p1 and p1.num_imagens == 0:
        return EVID_INSUFICIENTE, ("Imagens existem, mas nenhuma na capa, onde ficam "
                                   "os logos. " + obs), []
    return EVID_INSUFICIENTE, (f"{total_imgs} imagem(ns) detectada(s), "
                               f"{p1.num_imagens} na capa. Presença OK; atualização "
                               "não verificável por heurística. " + obs), []


def pad_13(doc):
    obs = ("Classe A: presença e formato do registro. Titularidade/registro ativo é "
           "classe C (consulta ao cadastro do CREA + humano).")
    rt, ev_rt = _campo(doc, "RESPONSÁVEL TÉCNICO")
    if ev_rt is None:
        # rótulo sem dois-pontos (cabeçalho de seção/carimbo real)
        ach = doc.buscar(r"\bRESPONS[ÁA]VEL\s+T[ÉE]CNICO\b")
        if ach:
            rt, ev_rt = "(declarado no documento)", _ev(ach[0][0], ach[0][1], ach[0][2])
    faltas, evs = [], []
    if rt is None:
        faltas.append("responsável técnico não identificado")
    else:
        evs.append(ev_rt)
    # CREA preenchido em algum formato real?
    crea_hits = [m for m in doc.buscar(RX_CREA_REAL)]
    crea_vazio = [m for m in doc.buscar(RX_CREA_VAZIO)]
    cau_hits = [m for m in doc.buscar(RX_CAU)]
    if crea_vazio and not crea_hits:
        faltas.append("CREA citado, mas o número está EM BRANCO (campo de template não preenchido)")
        evs.append(_ev(crea_vazio[0][0], crea_vazio[0][1], crea_vazio[0][2]))
    elif not crea_hits:
        if cau_hits:
            faltas.append("CREA não encontrado; há registro CAU (arquiteto), que não substitui CREA de engenheiro")
            evs.append(_ev(cau_hits[0][0], cau_hits[0][1], cau_hits[0][2]))
        else:
            faltas.append("número de CREA não encontrado no documento")
    else:
        evs += [_ev(h[0], h[1], h[2]) for h in crea_hits[:2]]
    if faltas:
        return NAO_CONFORME, "; ".join(faltas) + ". " + obs, evs
    return CONFORME, "Responsável técnico identificado e CREA presente. " + obs, evs


def pad_14(doc):
    os_val, ev = _campo(doc, "AS")
    if not ev:
        os_val, ev = _campo(doc, "ORDEM DE SERVIÇO")
    obs = ("Classe A: presença e formato. Correção contra o contrato do projeto é "
           "classe C (dado externo).")
    txt = (os_val or "").strip()
    if not txt or txt == "-":
        return NAO_CONFORME, ("Ordem de serviço (AS/OS) ausente ou vazia. Em documento "
                              "fora do padrão AP, o campo pode simplesmente não existir. " + obs), [ev]
    if not re.fullmatch(RX_OS, txt):
        return NAO_CONFORME, f"AS '{txt}' fora do padrão (ex.: ASP-ENG-APJ-243). " + obs, [ev]
    return CONFORME, "AS presente e no padrão. " + obs, [ev]


def pad_15(doc):
    obs = ("Classe A: presença/preenchimento dos campos do carimbo AP. Correção dos "
           "nomes contra o planejamento do projeto é classe C (dado externo).")
    faltas, evs = [], []
    for rotulo in ["CLIENTE", "PROGRAMA", "ÁREA", "UNIDADE"]:
        val, ev = _campo(doc, rotulo)
        if ev is None:
            faltas.append(f"{rotulo} não encontrado")
        elif not val or val == "-":
            faltas.append(f"{rotulo} vazio")
            evs.append(ev)
        else:
            evs.append(ev)
    if faltas:
        return NAO_CONFORME, "; ".join(faltas) + ". " + obs, evs
    return CONFORME, "Cliente, programa, área e unidade preenchidos. " + obs, evs


def pad_16(doc):
    titulo, ev = _campo(doc, "TÍTULO")
    obs = ("Classe C: exige a lista de documentos do planejamento (dado externo). "
           "O motor extrai o título declarado para o humano conferir.")
    if not ev:
        # fallback: primeira linha significativa (docs reais sem carimbo AP)
        for numero, nome, linha in doc.linhas():
            if len(linha) > 8:
                return EVID_INSUFICIENTE, f"Campo TÍTULO (carimbo AP) não existe; primeira linha do documento: '{linha[:80]}'. " + obs, [_ev(numero, nome, linha)]
        return EVID_INSUFICIENTE, "Título não encontrado. " + obs, []
    return EVID_INSUFICIENTE, f"Título declarado: '{titulo}'. " + obs, [ev]


def pad_17(doc):
    num_val, ev_num = _campo(doc, "Nº")
    if not ev_num:
        m = doc.buscar(RX_NUM_DOC)
        if m:
            num_val, ev_num = m[0][3].group(0), _ev(m[0][0], m[0][1], m[0][2])
    arq, ev_arq = _campo(doc, "ARQUIVO ELETRÔNICO")
    if not num_val:
        return NAO_CONFORME, ("Número de documento no padrão AP (ex.: RL-3433.02-5420-940-APJ-001) "
                              "não encontrado. Documentos de outras organizações usam outra numeração."), []
    if not re.search(RX_NUM_DOC, num_val):
        return NAO_CONFORME, f"Número '{num_val}' fora do padrão AP (ex.: RL-3433.02-5420-940-APJ-001).", [ev_num]
    numdoc = re.search(RX_NUM_DOC, num_val).group(0)
    if not arq:
        return NAO_CONFORME, "Campo ARQUIVO ELETRÔNICO não encontrado.", [ev_num]
    if numdoc not in arq:
        return NAO_CONFORME, (f"Arquivo eletrônico '{arq}' não contém o número do "
                              f"documento '{numdoc}'."), [ev_num, ev_arq]
    m_rev = re.search(r"=(\d+)\.", arq)
    rev_cab = doc.buscar(r"\bREV\.?:?\s*(\d+)\b")
    if m_rev and rev_cab and m_rev.group(1) != rev_cab[0][3].group(1):
        return NAO_CONFORME, (f"Revisão do arquivo eletrônico (={m_rev.group(1)}) difere "
                              f"da revisão do cabeçalho ({rev_cab[0][3].group(1)})."), [ev_arq, _ev(rev_cab[0][0], rev_cab[0][1], rev_cab[0][2])]
    return CONFORME, "Número no padrão, arquivo eletrônico contém o número e a revisão.", [ev_num, ev_arq]


RX_FOLHAS = [
    re.compile(r"FOLHA\s*:?\s*(\d+)\s*(?:de|/)\s*(\d+)", re.IGNORECASE),
    re.compile(r"P[ÁA]GINA\s*:?\s*(\d+)\s*(?:de|/)\s*(\d+)", re.IGNORECASE),
    re.compile(r"\bFL\.?\s*:?\s*(\d+)\s*(?:de|/)\s*(\d+)", re.IGNORECASE),
]


def pad_18(doc):
    if doc.formato == "xlsx":
        return NAO_SE_APLICA, "Planilha sem folhas paginadas.", []
    if doc.formato == "docx":
        return EVID_INSUFICIENTE, ("DOCX sem paginação fixa: a contagem de folhas só "
                                   "existe após renderização. No fluxo real, o GED "
                                   "converte a PDF antes desta regra."), []
    declaradas = []
    for p in doc.paginas:
        for rx in RX_FOLHAS:
            m = rx.search(p.texto)
            if m:
                declaradas.append((p, m))
                break
    if not declaradas:
        return NAO_CONFORME, "Nenhuma página declara numeração 'folha/página x de y'.", []
    erros, evs = [], []
    total_real = doc.num_paginas
    total_decl = int(declaradas[0][1].group(2))
    if total_decl != total_real:
        erros.append(f"declara '{total_decl}' folhas, documento tem {total_real} páginas")
    for p, m in declaradas:
        linha = next((l for l in p.texto.splitlines() if m.group(0) in l), m.group(0))
        evs.append(_ev(p.numero, p.nome, linha))
        if int(m.group(1)) != p.numero:
            erros.append(f"página {p.numero} declara folha {m.group(1)}")
        if int(m.group(2)) != total_decl:
            erros.append(f"página {p.numero} declara total {m.group(2)} (primeira: {total_decl})")
    if len(declaradas) != total_real:
        erros.append(f"só {len(declaradas)} de {total_real} páginas declaram numeração")
    if erros:
        return NAO_CONFORME, "; ".join(erros) + ".", evs
    return CONFORME, f"Folhas consistentes: {total_real} páginas, todas numeradas 'x de {total_decl}'.", evs


def pad_19(doc):
    _ia = _tentar_ia("PAD-1.9", "AS ALTERAÇÕES OCORRIDAS NO DOCUMENTO IMPACTAM NOS DOCUMENTOS DE OUTRAS DISCIPLINAS? ESTAS DISCIPLINAS FORAM INFORMADAS?", doc)
    if _ia:
        return _ia[0], _ia[1], _ia[2]
    obs = ("SIMULADO (classe B): heurística busca menções a outras disciplinas; "
           "avaliar impacto real exige contexto do pacote (Team Check, M2).")
    revs = doc.buscar(r"EMISS[ÃA]O\s+ORIGINAL")
    so_rev0 = revs and not doc.buscar(r"^\s*(?:REV\.?\s*)?[1-9]\d*(?!\.)\s+\S")
    if so_rev0:
        return NAO_SE_APLICA, ("Emissão original (rev 0): não há alterações a propagar. "
                               + obs), [_ev(revs[0][0], revs[0][1], revs[0][2])]
    achados = doc.buscar("|".join(DISCIPLINAS))
    if not achados:
        return EVID_INSUFICIENTE, ("Nenhuma disciplina citada; não dá para saber se "
                                   "houve impacto não informado. " + obs), []
    evs = [_ev(a[0], a[1], a[2]) for a in achados[:3]]
    return EVID_INSUFICIENTE, ("Disciplinas citadas no texto; se foram formalmente "
                               "informadas é confirmação humana. " + obs), evs


# ---------------- DESCRIÇÃO TÉCNICA ----------------

PREFIXOS_NAO_TAG = ("NBR", "ISO", "ASTM", "API", "CPF", "CNPJ", "RRT", "ART",
                    "CAU", "CREA", "PN", "DN")

def dt_10(doc):
    achados = [(num, nome, m.group(0), l) for num, nome, l, m in doc.buscar(RX_TAG)]
    tags = sorted({t for _, _, t, _ in achados
                   if not re.fullmatch(r"V\.?\d{4}", t)
                   and "X" not in t.upper()
                   and t.split("-")[0].upper() not in PREFIXOS_NAO_TAG})
    if tags:
        evs = [_ev(num, nome, l) for num, nome, t, l in achados if t in tags][:3]
        return CONFORME, f"TAG(s) identificada(s): {', '.join(tags[:8])}.", evs
    return EVID_INSUFICIENTE, ("Nenhuma TAG encontrada. Pode não haver TAGs neste "
                               "documento - confirmar com a disciplina (classe C)."), []


def dt_11(doc):
    _ia = _tentar_ia("DT-1.1", "PROPOSTA(S) TÉCNICA(S)?", doc)
    if _ia:
        return _ia[0], _ia[1], _ia[2]
    obs = ("SIMULADO (classe B): heurística exige seção de proposta/parecer com "
           "conteúdo substantivo (>= 200 caracteres). Em produção: LLM avalia se a "
           "proposta atende ao pedido.")
    sec = doc.buscar(r"PROPOSTA") or doc.buscar(r"\bPARECER\b")
    if not sec:
        return NAO_CONFORME, "Nenhuma seção de proposta técnica/parecer localizada. " + obs, []
    texto = doc.texto_completo
    pos = re.search(r"PROPOSTA", texto, re.IGNORECASE) or re.search(r"\bPARECER\b", texto, re.IGNORECASE)
    trecho = texto[pos.start():pos.start() + 1200]
    if len(trecho.strip()) < 200:
        return NAO_CONFORME, "Seção de proposta localizada, mas sem conteúdo substantivo. " + obs, [_ev(sec[0][0], sec[0][1], sec[0][2])]
    return CONFORME, "Seção de proposta técnica/parecer com conteúdo substantivo. " + obs, [_ev(sec[0][0], sec[0][1], sec[0][2])]


def dt_12(doc):
    _ia = _tentar_ia("DT-1.2", "DOCUMENTO(S) DE ESCLARECIMENTO?", doc)
    if _ia:
        return _ia[0], _ia[1], _ia[2]
    obs = ("SIMULADO (classe B): heurística busca menção a esclarecimentos; "
           "se o documento DEVERIA citar algum é confirmação humana (classe C).")
    ach = doc.buscar(r"ESCLARECIMENTO")
    if ach:
        return CONFORME, "Documento(s) de esclarecimento citado(s). " + obs, [_ev(ach[0][0], ach[0][1], ach[0][2])]
    return EVID_INSUFICIENTE, "Nenhuma menção a documento de esclarecimento. " + obs, []


def dt_13(doc):
    sec = doc.buscar(r"(DOCUMENTOS\s+DE\s+REFER|REFER[ÊE]NCIAS(\s+BIBLIOGR[ÁA]FICAS)?|DOCUMENTOS\s+APLIC[ÁA]VEIS|NORMAS\s+APLIC[ÁA]VEIS|BASES?\s+NORMATIVAS?)")
    if not sec:
        return NAO_CONFORME, "Seção de referências/normas não encontrada.", []
    normas = doc.buscar(RX_NORMA)
    docs_ref = doc.buscar(RX_NUM_DOC)
    if not normas and len(docs_ref) == 0:
        return NAO_CONFORME, ("Seção de referências presente, mas sem normas "
                              "(NBR/ISO/ASTM/API) nem códigos de documentos."), [_ev(sec[0][0], sec[0][1], sec[0][2])]
    evs = [_ev(sec[0][0], sec[0][1], sec[0][2])]
    evs += [_ev(a[0], a[1], a[2]) for a in normas[:3]]
    return CONFORME, ("Seção de referências presente com norma(s)/documento(s) "
                      "citados."), evs


AVALIADORES = {
    "PAD-1.0": pad_10, "PAD-1.1": pad_11, "PAD-1.2": pad_12, "PAD-1.3": pad_13,
    "PAD-1.4": pad_14, "PAD-1.5": pad_15, "PAD-1.6": pad_16, "PAD-1.7": pad_17,
    "PAD-1.8": pad_18, "PAD-1.9": pad_19,
    "DT-1.0": dt_10, "DT-1.1": dt_11, "DT-1.2": dt_12, "DT-1.3": dt_13,
}


def _tentar_ia(item, descricao, doc):
    """Tenta a classe B com IA real (NVIDIA NIM). Retorna tupla pronta ou None."""
    if not ia.disponivel():
        return None
    res = ia.avaliar_classe_b(item, descricao, doc.texto_completo)
    if not res:
        return None
    evs = []
    if res["evidencia"]:
        frag = res["evidencia"][:80]
        for numero, nome, linha in doc.linhas():
            if frag[:40] in linha:
                evs = [_ev(numero, nome, linha)]
                break
    return res["status"], f"IA ({ia.MODELO}): " + res["observacao"], evs, ia.ROTULO_IA


def verificar(doc):
    resultados = []
    for item, secao, descricao, classe in CHECKLIST:
        status, obs, evs = AVALIADORES[item](doc)
        decisao = ia.ROTULO_IA if obs.startswith("IA (") else None
        resultados.append(_resultado(item, secao, descricao, classe, status, obs, evs, decisao_por=decisao))
    return resultados
