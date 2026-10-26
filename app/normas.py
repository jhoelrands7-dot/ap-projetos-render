"""Modulo 3 — casamento de informacoes e confronto com normas (experimental).

Regras de honestidade:
- so texto de norma real e publica, citado com fonte oficial;
- toda conclusao sai como HIPOTESE, com a evidencia do documento de um lado
  e o trecho da norma do outro;
- a tela deixa explicito o que o modulo NAO cobre.
"""
import math
from datetime import datetime, timezone

import cruzamento
import ia

VERSAO = "m3-normas-1"

FONTE_NR24 = ("NR-24 - Condicoes Sanitarias e de Conforto nos Locais de Trabalho "
              "(texto atualizado 2022, Ministerio do Trabalho e Emprego)")
URL_NR24 = ("https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/"
            "participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-"
            "partitaria-permanente/arquivos/normas-regulamentadoras/nr-24-atualizada-2022.pdf")
FONTE_NR35 = ("NR-35 - Trabalho em Altura (Ministerio do Trabalho e Emprego)")
URL_NR35 = ("https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/"
            "participacao-social/conselhos-e-orgaos-colegiados/comissao-tripartite-"
            "partitaria-permanente/arquivos/normas-regulamentadoras/nr-35.pdf")

PARAMETROS = [
    {
        "id": "nr24-sanitarios",
        "norma": "NR-24",
        "item": "24.2.2",
        "titulo": "Instalacoes sanitarias por trabalhador",
        "texto": ("Deve ser atendida a proporcao minima de uma instalacao sanitaria para "
                  "cada grupo de 20 (vinte) trabalhadores ou fracao, separadas por sexo."),
        "fonte_nome": FONTE_NR24, "fonte_url": URL_NR24,
        "tipo": "razao",
        "kw_a": ["instalacao sanitaria", "instalacoes sanitarias", "vaso sanitario",
                 "vasos sanitarios", "sanitario", "sanitarios", "banheiro", "banheiros",
                 "toalete", "wc"],
        "kw_b": ["trabalhador", "trabalhadores", "funcionario", "funcionarios",
                 "operario", "operarios", "efetivo", "colaborador", "colaboradores",
                 "pessoas", "empregados"],
        "por": 20,
        "resumo_regra": "minimo de 1 instalacao sanitaria para cada 20 trabalhadores (ou fracao), separadas por sexo",
        "obs": ("A norma fala em 'instalacao sanitaria'; documentos costumam listar vasos, "
                "banheiros ou WCs de formas diferentes — a contagem extraida pode nao "
                "corresponder exatamente ao conceito da norma."),
    },
    {
        "id": "nr24-chuveiros",
        "norma": "NR-24",
        "item": "24.3.5",
        "titulo": "Chuveiros por trabalhador",
        "texto": ("Sera exigido, para cada grupo de trabalhadores ou fracao, 1 (um) chuveiro "
                  "para cada: a) 10 (dez) trabalhadores, nas atividades laborais em que haja "
                  "exposicao e manuseio de material infectante, substancias toxicas, irritantes "
                  "ou aerodispersoides, que impregnem a pele e roupas do trabalhador; "
                  "b) 20 (vinte) trabalhadores, nas atividades laborais em que haja contato com "
                  "substancias que provoquem deposicao de poeiras que impregnem a pele e as "
                  "roupas do trabalhador, ou que exijam esforco fisico ou submetidas a "
                  "condicoes ambientais de calor intenso."),
        "fonte_nome": FONTE_NR24, "fonte_url": URL_NR24,
        "tipo": "razao_dupla",
        "kw_a": ["chuveiro", "chuveiros", "ducha", "duchas"],
        "kw_b": ["trabalhador", "trabalhadores", "funcionario", "funcionarios",
                 "operario", "operarios", "efetivo", "colaborador", "colaboradores",
                 "pessoas", "empregados"],
        "por_a": 10, "por_b": 20,
        "resumo_regra": ("1 chuveiro para cada 10 trabalhadores (atividades com exposicao a "
                         "material infectante/toxico) ou para cada 20 (demais atividades com "
                         "poeira, esforco fisico ou calor intenso)"),
        "obs": ("Qual dos dois cenarios (1:10 ou 1:20) se aplica depende da natureza da "
                "atividade — o sistema mostra os dois e quem analisa decide."),
    },
    {
        "id": "nr35-altura",
        "norma": "NR-35",
        "item": "35.1.2",
        "titulo": "Trabalho em altura (acima de 2,00 m)",
        "texto": ("Considera-se trabalho em altura toda atividade executada acima de 2,00 m "
                  "(dois metros) do nivel inferior, onde haja risco de queda."),
        "fonte_nome": FONTE_NR35, "fonte_url": URL_NR35,
        "tipo": "disparador",
        "kw": ["altura", "pe direito", "elevacao", "cota", "nivel"],
        "limiar_m": 2.0,
        "resumo_regra": ("se o documento indica atividade ou estrutura acima de 2,00 m, a NR-35 "
                         "provavelmente se aplica (capacitacao, analise de risco, medidas de "
                         "protecao contra queda)"),
        "obs": ("Encontrar uma medida acima de 2,00 m no documento NAO prova que ha trabalho "
                "em altura: a norma exige tambem risco de queda, o que so a analise humana "
                "confirma."),
    },
]

NAO_COBRE = [
    "Normas ABNT (NBR 9050, NBR 15575, NBR 5410 etc.): sao pagas e seu texto nao pode ser reproduzido — o modulo nao as cita.",
    "Codigos de obras municipais e legislacao estadual: variam por cidade e nao estao na biblioteca.",
    "Confronto com o desenho (plantas, fluxogramas, diagramas): o sistema nao le geometria, so o texto escrito nos PDFs.",
    "Julgamento de aplicabilidade: se a norma de fato se aplica ao caso (natureza da atividade, risco de queda, sexo dos trabalhadores) e decisao humana.",
    "Verificacao de veracidade: o confronto usa o que esta escrito nos documentos, sem conferir se os numeros sao reais.",
]


def _tokens(s):
    return set(cruzamento._norm(s).split())


def _casa(item, keywords):
    """item da extracao casa com alguma keyword (frase)? token-set overlap."""
    chave = item.get("chave") or cruzamento._chave_item(item.get("rotulo", ""))
    toks = set(chave.split())
    for kw in keywords:
        # usa a mesma normalizacao de chave (>=3 letras, sem stopwords) dos itens
        kwt = set(cruzamento._chave_item(kw).split())
        if kwt and kwt <= toks:
            return True
    return False


def _busca_quantidade(documentos, keywords):
    """Procura itens quantificados cujo rotulo case com as keywords.
    Retorna lista de ocorrencias com numero valido."""
    achados = []
    for d in documentos:
        for it in d["itens"]:
            if it["valor_num"] is None:
                continue
            if _casa(it, keywords):
                achados.append({
                    "doc": d["idx"], "rotulo": it["rotulo"], "valor": it["valor"],
                    "valor_num": it["valor_num"], "unidade": it["unidade"],
                    "pagina": it["pagina"], "evidencia": it["evidencia"],
                })
    return achados


def _confronto_razao(p, documentos, dupla=False):
    ach_a = _busca_quantidade(documentos, p["kw_a"])
    ach_b = _busca_quantidade(documentos, p["kw_b"])
    if not ach_a or not ach_b:
        faltam = []
        if not ach_a:
            faltam.append(f"quantidade de '{p['titulo'].split(' por ')[0].lower()}'")
        if not ach_b:
            faltam.append("numero de trabalhadores/funcionarios")
        return {"status": "nao_encontrado",
                "detalhe": "Nao encontrei nos documentos: " + " e ".join(faltam) +
                           ". Sem os dois numeros, o confronto nao e possivel.",
                "evidencias": ach_a + ach_b}
    # usa o menor total de trabalhadores e o menor numero de unidades encontrado
    # (conservador: pior caso). Registra tudo como evidencia.
    n_unid = min(a["valor_num"] for a in ach_a)
    n_trab = max(b["valor_num"] for b in ach_b)
    if n_unid <= 0:
        return {"status": "nao_encontrado", "detalhe": "Quantidade extraida invalida (zero).",
                "evidencias": ach_a + ach_b}
    razao = n_trab / n_unid
    ev = ach_a + ach_b
    if not dupla:
        limite = p["por"]
        ok = razao <= limite
        return {
            "status": "atende_hipotese" if ok else "atencao_hipotese",
            "detalhe": (f"Numeros encontrados: {n_unid:g} unidade(s) para {n_trab:g} trabalhadores "
                        f"→ 1 para cada {razao:g}. Regra da norma: 1 para cada {limite}. "
                        + ("Dentro do limite — hipotese de atendimento, a confirmar pela analise humana."
                           if ok else
                           "Acima do limite — hipotese de NAO atendimento, a confirmar pela analise humana.")),
            "evidencias": ev,
            "calculo": {"unidades": n_unid, "trabalhadores": n_trab, "razao": razao, "limite": limite},
        }
    lim_a, lim_b = p["por_a"], p["por_b"]
    cenarios = []
    for rot, lim in (("cenario 1:10 (atividades com exposicao a material infectante/toxico)", lim_a),
                     ("cenario 1:20 (demais atividades com poeira, esforco fisico ou calor)", lim_b)):
        ok = razao <= lim
        cenarios.append({"rotulo": rot, "limite": lim, "atende": ok})
    pior = all(c["atende"] for c in cenarios)
    algum = any(c["atende"] for c in cenarios)
    if pior:
        status = "atende_hipotese"
        msg = "Atende nos dois cenarios da norma — hipotese de atendimento, a confirmar."
    elif algum:
        status = "atencao_hipotese"
        msg = "Atende no cenario 1:20, mas NAO no cenario 1:10 — se a atividade envolver exposicao a material infectante/toxico, estaria abaixo do exigido. Hipotese a confirmar."
    else:
        status = "atencao_hipotese"
        msg = "Abaixo do exigido nos dois cenarios — hipotese de NAO atendimento, a confirmar."
    return {
        "status": status,
        "detalhe": (f"Numeros encontrados: {n_unid:g} chuveiro(s) para {n_trab:g} trabalhadores "
                    f"→ 1 para cada {razao:g}. {msg}"),
        "evidencias": ev,
        "calculo": {"unidades": n_unid, "trabalhadores": n_trab, "razao": razao,
                    "cenarios": cenarios},
    }


def _confronto_disparador(p, documentos):
    achados = []
    for d in documentos:
        for it in d["itens"]:
            if it["valor_num"] is None:
                continue
            if it["unidade_norm"] not in ("m", "m2", "m3"):
                continue
            if it["unidade_norm"] != "m":
                continue
            if it["valor_num"] >= p["limiar_m"] and _casa(it, p["kw"]):
                achados.append({
                    "doc": d["idx"], "rotulo": it["rotulo"], "valor": it["valor"],
                    "valor_num": it["valor_num"], "unidade": it["unidade"],
                    "pagina": it["pagina"], "evidencia": it["evidencia"],
                })
    if not achados:
        return {"status": "nao_encontrado",
                "detalhe": ("Nenhuma medida em metros acima de 2,00 m associada a altura, "
                            "pe-direito, elevacao ou cota foi encontrada no texto dos documentos."),
                "evidencias": []}
    maior = max(a["valor_num"] for a in achados)
    return {"status": "aplicavel_hipotese",
            "detalhe": (f"Encontrei {len(achados)} medida(s) acima de 2,00 m "
                        f"(maior: {maior:g} m). Hipotese: a NR-35 provavelmente se aplica — "
                        "verificar se ha trabalho nessa altura com risco de queda e as "
                        "exigencias de capacitacao e protecao."),
            "evidencias": achados[:8]}


def executar(docs):
    """docs = [{"caminho", "nome"}] -> resultado auditavel (dict)."""
    inicio = datetime.now(timezone.utc)
    avisos = []
    ia.reset_contadores()
    documentos = []
    for idx, d in enumerate(docs):
        documentos.append(cruzamento._extrair_doc(idx, d["caminho"], d["nome"],
                                                  d.get("disciplina") or "", avisos))
    normas = []
    for p in PARAMETROS:
        if p["tipo"] == "razao":
            r = _confronto_razao(p, documentos)
        elif p["tipo"] == "razao_dupla":
            r = _confronto_razao(p, documentos, dupla=True)
        else:
            r = _confronto_disparador(p, documentos)
        normas.append({
            "id": p["id"], "norma": p["norma"], "item": p["item"], "titulo": p["titulo"],
            "texto": p["texto"], "fonte_nome": p["fonte_nome"], "fonte_url": p["fonte_url"],
            "resumo_regra": p["resumo_regra"], "obs": p["obs"],
            "status": r["status"], "detalhe": r["detalhe"], "evidencias": r["evidencias"],
            "calculo": r.get("calculo"),
        })
    resumo = {
        "hipoteses_atendimento": sum(1 for n in normas if n["status"] == "atende_hipotese"),
        "hipoteses_atencao": sum(1 for n in normas if n["status"] == "atencao_hipotese"),
        "hipoteses_aplicavel": sum(1 for n in normas if n["status"] == "aplicavel_hipotese"),
        "nao_encontrados": sum(1 for n in normas if n["status"] == "nao_encontrado"),
    }
    fim = datetime.now(timezone.utc)
    return {
        "versao": VERSAO,
        "documentos": [{k: d[k] for k in ("idx", "nome", "disciplina", "sha256", "paginas")}
                       | {"num_itens": len(d["itens"])} for d in documentos],
        "normas": normas,
        "resumo": resumo,
        "nao_cobre": NAO_COBRE,
        "avisos": avisos,
        "meta": {
            "inicio": inicio.isoformat(timespec="seconds"),
            "fim": fim.isoformat(timespec="seconds"),
            "duracao_s": round((fim - inicio).total_seconds(), 1),
            "ia": ia.status(),
        },
    }
