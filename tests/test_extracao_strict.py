# -*- coding: utf-8 -*-
"""Testes do modo estrito da extracao (EXTRACAO_STRICT) + regressao do modo padrao.

Roda sem dependencias externas: auditoria/extratores sao stubados (nao sao
exercitados aqui). Nos commits sem o modo estrito, os testes estritos sao
pulados e os de regressao (modo padrao) tem que passar iguais.
"""
import io, json, os, sys, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
for _m in ("auditoria", "extratores"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

import ia
import extracao_orcamento as eo

STRICT_IMPL = hasattr(eo, "_strict") and hasattr(ia, "_strict")


class _Resp:
    def __init__(self, payload):
        self.payload = payload
    def read(self):
        return json.dumps(self.payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


PAGINA = ("Motor elétrico trifásico W22, grau de proteção IP55, 50 Hz. "
          "Forma construtiva: B3T. Tensão 380/660 V. Potência: 5,5 kW. Rotação 3500 rpm.")


def _paginas():
    return [(1, eo._norm(PAGINA))]


def _campo(nome="Forma construtiva"):
    return {"id": "f1", "campo": nome, "definicao": nome + " do motor", "unidade_ref": ""}


def _res(valor, evidencia):
    return {"ia_ok": True, "valor": valor, "unidade": "", "pagina": 1,
            "evidencia": evidencia, "obs": ""}


class Base(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        os.environ.pop("EXTRACAO_STRICT", None)
        os.environ["OPENROUTER_API_KEY"] = "sk-teste"
        os.environ.pop("NVIDIA_API_KEY", None)
        ia.reset_contadores()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        ia.reset_contadores()

    def strict_on(self):
        os.environ["EXTRACAO_STRICT"] = "1"


class RegressaoModoPadrao(Base):
    """Comportamento atual (flag desligada) — nao pode mudar com o commit."""

    def test_valor_correto_segue_extraido(self):
        st = eo._revisar("f2", _campo("Potência nominal"), _res("5,5", "Potência: 5,5 kW"), _paginas())
        self.assertEqual(st[0], eo.ST_EXTRAIDO)

    def test_bug_b5t_documentado_modo_padrao(self):
        # BUG conhecido: B5T com evidencia B3T passa como Extraido no modo padrao
        st = eo._revisar("f1", _campo(), _res("B5T", "Forma construtiva: B3T"), _paginas())
        self.assertEqual(st[0], eo.ST_EXTRAIDO)

    def test_conteudo_vazio_conta_como_sucesso_modo_padrao(self):
        with mock.patch("urllib.request.urlopen", return_value=_Resp({"choices": [{"message": {"content": ""}}]})):
            conteudo, _ = ia.chamar_chat([{"role": "user", "content": "x"}], max_tokens=5, tentativas=1)
        self.assertEqual(conteudo, "")
        self.assertEqual(ia.FALHAS, 0)

    def test_corpo_erro_http_descartado_modo_padrao(self):
        err = urllib_error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            "https://x", 402, "Payment Required", None, io.BytesIO(b'{"error":{"message":"Insufficient credits"}}'))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            conteudo, _ = ia.chamar_chat([{"role": "user", "content": "x"}], max_tokens=5, tentativas=1)
        self.assertIsNone(conteudo)
        self.assertNotIn("Insufficient credits", ia.ULTIMO_ERRO or "")

    def test_lote_incompleto_sem_falha_modo_padrao(self):
        itens = [{"id": f"f{i}", "campo": f"Campo {i}", "definicao": "", "unidade_ref": ""} for i in range(5)]
        with mock.patch.object(eo, "_chama_ia", return_value='[{"id": "f1", "valor": "x"') as m:
            out = eo._extrair_categoria("geral", itens, [])
        self.assertEqual(m.call_count, 1)
        self.assertTrue(all(out[f"f{i}"].get("_sem_resposta") for i in range(5)))
        self.assertEqual(ia.FALHAS, 0)


@unittest.skipUnless(STRICT_IMPL, "modo estrito ainda nao existe neste commit")
class ModoEstrito(Base):
    def test_valor_correto_segue_extraido(self):
        self.strict_on()
        st = eo._revisar("f2", _campo("Potência nominal"), _res("5,5", "Potência: 5,5 kW"), _paginas())
        self.assertEqual(st[0], eo.ST_EXTRAIDO)

    def test_b3t_correto_segue_extraido(self):
        self.strict_on()
        st = eo._revisar("f1", _campo(), _res("B3T", "Forma construtiva: B3T"), _paginas())
        self.assertEqual(st[0], eo.ST_EXTRAIDO)

    def test_b5t_com_evidencia_b3t_nao_passa_mais(self):
        self.strict_on()
        st = eo._revisar("f1", _campo(), _res("B5T", "Forma construtiva: B3T"), _paginas())
        self.assertEqual(st[0], eo.ST_AMBIGUO)
        self.assertIn("evidência", st[5])

    def test_ip55_no_campo_forma_construtiva_bloqueado(self):
        self.strict_on()
        st = eo._revisar("f1", _campo(), _res("IP55", "grau de proteção IP55"), _paginas())
        self.assertEqual(st[0], eo.ST_AMBIGUO)

    def test_conteudo_vazio_vira_falha(self):
        self.strict_on()
        with mock.patch("urllib.request.urlopen", return_value=_Resp({"choices": [{"message": {"content": ""}}]})):
            conteudo, _ = ia.chamar_chat([{"role": "user", "content": "x"}], max_tokens=5, tentativas=1)
        self.assertIsNone(conteudo)
        self.assertGreaterEqual(ia.FALHAS, 1)

    def test_corpo_erro_http_aparece_na_auditoria(self):
        self.strict_on()
        err = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            "https://x", 402, "Payment Required", None, io.BytesIO(b'{"error":{"message":"Insufficient credits"}}'))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            ia.chamar_chat([{"role": "user", "content": "x"}], max_tokens=5, tentativas=1)
        self.assertIn("Insufficient credits", ia.ULTIMO_ERRO or "")

    def test_lote_incompleto_retenta_e_recupera(self):
        self.strict_on()
        itens = [{"id": f"f{i}", "campo": f"Campo {i}", "definicao": "", "unidade_ref": ""} for i in range(5)]
        completo = json.dumps([{"id": f"f{i}", "valor": "1", "evidencia": "e"} for i in range(5)])
        with mock.patch.object(eo, "_chama_ia", side_effect=['[{"id": "f1", "valor": "x"', completo]) as m, \
                mock.patch("time.sleep") as slp:
            out = eo._extrair_categoria("geral", itens, [])
        self.assertEqual(m.call_count, 2)
        self.assertGreaterEqual(slp.call_count, 1)
        self.assertEqual(ia.FALHAS, 1)
        self.assertTrue(all(not out[f"f{i}"].get("_sem_resposta") for i in range(5)))

    def test_lote_sempre_incompleto_desiste_apos_3(self):
        self.strict_on()
        itens = [{"id": f"f{i}", "campo": f"Campo {i}", "definicao": "", "unidade_ref": ""} for i in range(5)]
        with mock.patch.object(eo, "_chama_ia", return_value='[{"id": "f1", "valor": "x"') as m, \
                mock.patch("time.sleep") as slp:
            out = eo._extrair_categoria("geral", itens, [])
        self.assertEqual(m.call_count, 3)
        self.assertEqual(slp.call_count, 2)
        self.assertEqual(ia.FALHAS, 3)
        self.assertTrue(all(out[f"f{i}"].get("_sem_resposta") for i in (0, 2, 3, 4)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
