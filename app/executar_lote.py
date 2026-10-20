# -*- coding: utf-8 -*-
"""Roda o motor nos documentos reais baixados e grava JSON + PDF por documento."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auditoria, relatorio

BASE = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(BASE, "saida")
RAIZ = os.path.dirname(BASE)

FONTES = json.load(open(os.path.join(RAIZ, "fontes.json")))
URL_C007 = FONTES["docs_reais/c007"]["url_base_arquivos"]
PORTAL_C007 = FONTES["docs_reais/c007"]["portal"]

ALVOS = [
    ("memorial-descritivo", "docs_reais/c007/2026-05-25_06_anexo_ii_memorial-descritivo_muro_26033858.pdf"),
    ("memoria-de-calculo", "docs_reais/c007/2026-05-25_07_anexo_ii_memoria-calculo_muro_26033858.pdf"),
    ("planilha-orcamentaria", "docs_reais/c007/2026-05-25_05_anexo_ii_planilha-orcamentaria-cronograma_muro_26033858.pdf"),
    ("projeto-arquitetonico", "docs_reais/c007/2026-05-25_08_anexo_ii_projeto-arquitetonico_muro_26033858.pdf"),
    ("rrt-projeto", "docs_reais/c007/2026-05-25_09_anexo_ii_rrt-projeto_muro_26033858.pdf"),
    ("termo-de-referencia", "docs_reais/c007/2026-05-25_02_anexo_i_tr_obra-muro_26033858.pdf"),
    ("etp", "docs_reais/c007/2026-05-25_03_apendice-anexo_i_etp_obra-muro_26033858.pdf"),
    ("parecer-tecnico-seinfra-go", "docs_reais/pareceres/parecer_tecnico_seinfra_go.pdf"),
    ("cesan-manual-recebimento-obras", "docs_reais/pareceres/cesan_recebimento_obras_eng002.pdf"),
    ("modelo-proposta-docx", "docs_reais/c007/2026-05-25_12_anexo_iv_modelo-proposta_conc_007-26_26033858.docx"),
    ("dec-tecnico-operacional-docx", "docs_reais/c007/2026-05-25_14_anexo_vi_dec-tecnico-operacional_conc_007-26_26033858.docx"),
]


def url_origem(rel):
    nome = rel.rsplit("/", 1)[-1]
    if rel.startswith("docs_reais/c007/"):
        return URL_C007 + nome + " (via " + PORTAL_C007 + ")"
    info = FONTES.get(rel)
    return info["url"] if info else None


def main():
    os.makedirs(SAIDA, exist_ok=True)
    indice = []
    for slug, rel in ALVOS:
        caminho = os.path.join(RAIZ, rel)
        registro, ok = auditoria.verificar_reprodutibilidade(caminho, url_origem(rel))
        with open(os.path.join(SAIDA, f"{slug}.json"), "w") as f:
            json.dump(registro, f, ensure_ascii=False, indent=2)
        relatorio.gerar_relatorio(registro, os.path.join(SAIDA, f"{slug}.pdf"))
        resumo = auditoria.resumo_status(registro["resultados"])
        indice.append({"slug": slug, "arquivo": registro["documento"]["nome"],
                       "origem": registro["documento"]["origem_url"],
                       "resumo": resumo, "reprodutivel": ok})
        print(f"{slug}: {resumo} reprodutivel={ok}")
    with open(os.path.join(SAIDA, "indice.json"), "w") as f:
        json.dump(indice, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
