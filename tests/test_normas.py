# -*- coding: utf-8 -*-
"""Testes determinísticos do Módulo 3 (confronto com normas) — sem IA, sem rede."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import normas as nm
import cruzamento as cz


def _item(rotulo, valor, unidade="un"):
    return {"rotulo": rotulo, "chave": cz._chave_item(rotulo), "valor": valor,
            "valor_num": cz._parse_num(valor), "unidade": unidade,
            "unidade_norm": cz._norm_unid(unidade), "pagina": 1,
            "evidencia": "trecho", "evidencia_ok": True}


def _doc(idx, itens):
    return {"idx": idx, "nome": f"doc{idx}.pdf", "disciplina": "", "sha256": "x" * 64,
            "paginas": 1, "paginas_sem_texto": [], "paginas_desenho": [],
            "itens": itens, "tags": [], "cnpjs": []}


def _param(pid):
    return next(p for p in nm.PARAMETROS if p["id"] == pid)


def test_sanitarios_atende():
    p = _param("nr24-sanitarios")
    docs = [_doc(0, [_item("vasos sanitários", "4", "un"), _item("trabalhadores", "60", "un")])]
    r = nm._confronto_razao(p, docs)
    assert r["status"] == "atende_hipotese", r
    assert r["calculo"]["razao"] == 15.0  # 60/4


def test_sanitarios_atencao():
    p = _param("nr24-sanitarios")
    docs = [_doc(0, [_item("vasos sanitários", "2", "un"), _item("funcionários", "50", "un")])]
    r = nm._confronto_razao(p, docs)
    assert r["status"] == "atencao_hipotese", r
    assert r["calculo"]["razao"] == 25.0


def test_sanitarios_sem_dados():
    p = _param("nr24-sanitarios")
    docs = [_doc(0, [_item("área construída", "120", "m²")])]
    r = nm._confronto_razao(p, docs)
    assert r["status"] == "nao_encontrado"


def test_chuveiros_dois_cenarios():
    p = _param("nr24-chuveiros")
    docs = [_doc(0, [_item("chuveiros", "2", "un"), _item("trabalhadores", "30", "un")])]
    r = nm._confronto_razao(p, docs, dupla=True)
    # razao 15 -> atende 1:20 mas nao 1:10
    assert r["status"] == "atencao_hipotese", r
    c = {x["limite"]: x["atende"] for x in r["calculo"]["cenarios"]}
    assert c == {10: False, 20: True}, c


def test_nr35_dispara():
    p = _param("nr35-altura")
    docs = [_doc(0, [_item("pé direito", "3,50", "m")])]
    r = nm._confronto_disparador(p, docs)
    assert r["status"] == "aplicavel_hipotese", r
    assert r["evidencias"][0]["valor_num"] == 3.5


def test_nr35_nao_dispara_abaixo_de_2m():
    p = _param("nr35-altura")
    docs = [_doc(0, [_item("altura do guarda-corpo", "1,10", "m")])]
    r = nm._confronto_disparador(p, docs)
    assert r["status"] == "nao_encontrado", r


def test_nr35_ignora_m2():
    p = _param("nr35-altura")
    docs = [_doc(0, [_item("altura do muro", "30,00", "m²")])]
    r = nm._confronto_disparador(p, docs)
    assert r["status"] == "nao_encontrado", r


def test_textos_e_fontes():
    for p in nm.PARAMETROS:
        assert p["texto"] and p["fonte_url"].startswith("https://www.gov.br/"), p["id"]
    assert nm.NAO_COBRE and any("ABNT" in x for x in nm.NAO_COBRE)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)}/{len(fns)} OK")
