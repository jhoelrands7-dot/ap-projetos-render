# -*- coding: utf-8 -*-
"""Testes determinísticos do Módulo 2 (cruzamento) — sem IA, sem rede."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import cruzamento as cz


def _doc(idx, itens, tags=(), cnpjs=()):
    return {"idx": idx, "nome": f"doc{idx}.pdf", "disciplina": "", "sha256": "x" * 64,
            "paginas": 1, "paginas_sem_texto": [], "paginas_desenho": [],
            "itens": itens, "tags": list(tags), "cnpjs": list(cnpjs)}


def _item(rotulo, valor, unidade="m²", ev_ok=True):
    return {"rotulo": rotulo, "chave": cz._chave_item(rotulo), "valor": valor,
            "valor_num": cz._parse_num(valor), "unidade": unidade,
            "unidade_norm": cz._norm_unid(unidade), "pagina": 1,
            "evidencia": "trecho", "evidencia_ok": ev_ok}


def test_parse_num():
    assert cz._parse_num("70,00") == 70.0
    assert cz._parse_num("1.234,56") == 1234.56
    assert cz._parse_num("70.00") == 70.0
    assert cz._parse_num("1.234") == 1234.0
    assert cz._parse_num("abc") is None
    assert cz._parse_num("") is None


def test_norm_unid():
    assert cz._norm_unid("m²") == cz._norm_unid("M2") == "m2"
    assert cz._norm_unid("m³") == "m3"
    assert cz._norm_unid("m linear") == "m"


def test_chave_item_ordem_nao_importa():
    assert cz._chave_item("Área de Limpeza do Terreno") == cz._chave_item("limpeza terreno area")
    assert cz._chave_item("volume escavação") != cz._chave_item("volume aterro")


def test_cruzamento_converge_diverge_sem_cor():
    d0 = _doc(0, [_item("area limpeza terreno", "70,00"), _item("volume escavacao", "14,00", "m³"),
                  _item("extensao muro", "24,00", "m")], tags=["P-101"], cnpjs=["46.947.396/0001-80"])
    d1 = _doc(1, [_item("limpeza terreno area", "70,00", "M2"), _item("volume escavacao", "16,00", "m³")],
              tags=["P-101", "TQ-02"], cnpjs=["46.947.396/0001-80"])
    itens, tags, cnpjs = cz._cruzar([d0, d1])
    por_chave = {i["chave"]: i["status"] for i in itens}
    assert por_chave[cz._chave_item("area limpeza terreno")] == "converge"      # 70 m² == 70 M2
    assert por_chave[cz._chave_item("volume escavacao")] == "diverge"           # 14 vs 16 m³
    assert por_chave[cz._chave_item("extensao muro")] == "sem_correspondente"
    tag_status = {t["tag"]: t["status"] for t in tags}
    assert tag_status["P-101"] == "compartilhada" and tag_status["TQ-02"] == "so_em_um"
    assert len(cnpjs) == 1 and len(cnpjs["46.947.396/0001-80"]) == 2


def test_unidade_diferente_marca_divergencia():
    d0 = _doc(0, [_item("ralo seco", "1", "unidade")])
    d1 = _doc(1, [_item("ralo seco", "1,00", "M")])
    itens, _, _ = cz._cruzar([d0, d1])
    assert itens[0]["status"] == "diverge"  # unidade incompatível = para confirmar


def test_dedup_mesmo_doc_nao_diverge():
    d0 = _doc(0, [_item("area limpeza terreno", "70,00"), _item("area limpeza terreno", "70,00")])
    d1 = _doc(1, [_item("area limpeza terreno", "70,00")])
    itens, _, _ = cz._cruzar([d0, d1])
    assert itens[0]["status"] == "converge"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print(f"{len(fns)}/{len(fns)} OK")
