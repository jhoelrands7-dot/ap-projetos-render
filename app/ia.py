# -*- coding: utf-8 -*-
"""
Ponto de troca para IA real (OpenRouter como provedor principal, NVIDIA NIM como fallback).

- A chave NUNCA fica no código: lida da variável de ambiente NVIDIA_API_KEY.
- Sem chave (ou qualquer erro de rede/parse), o chamador cai na heurística
  SIMULADA já existente, e o resultado diz qual caminho foi usado.
- Endpoint OpenAI-compatível: POST https://integrate.api.nvidia.com/v1/chat/completions
  (fonte: https://docs.api.nvidia.com/nim/reference/llm-apis)
- Modelo padrão: meta/llama-3.2-11b-vision-instruct (nvidia/nemotron-3-super-120b-a12b passou a responder 404 para a conta em 2026-10-20; llama-3.1-8b e llama-3.3-70b foram descontinuados pela NVIDIA em 2026-08-26).
"""
import json, os, re, urllib.request, urllib.error

ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELO = os.environ.get("NVIDIA_MODELO", "meta/llama-3.2-11b-vision-instruct")
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELO = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
ROTULO_IA = f"IA via NVIDIA NIM ({MODELO})"
ULTIMO_PROVEDOR = None  # "modelo (provedor)" da última chamada bem-sucedida


def _provedores():
    """Cadeia de provedores: OpenRouter primeiro (se OPENROUTER_API_KEY), NVIDIA NIM como fallback."""
    prov = []
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        prov.append(("OpenRouter", OPENROUTER_ENDPOINT, or_key, OPENROUTER_MODELO))
    nv_key = os.environ.get("NVIDIA_API_KEY")
    if nv_key:
        prov.append(("NVIDIA NIM", ENDPOINT, nv_key, MODELO))
    return prov


def chamar_chat(mensagens, max_tokens=1500, timeout=60, tentativas=2):
    """Chama o primeiro provedor disponível (OpenRouter -> NVIDIA). 
    Retorna (conteudo, rotulo) ou (None, None) se todos falharem."""
    global ULTIMO_PROVEDOR
    for nome, url, chave, modelo in _provedores():
        corpo = {"model": modelo, "messages": mensagens, "max_tokens": max_tokens,
                 "temperature": 0, "seed": 42, "stream": False}
        for tentativa in range(tentativas):
            req = urllib.request.Request(
                url, data=json.dumps(corpo).encode(),
                headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
                method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    dados = json.loads(resp.read().decode())
                conteudo = dados["choices"][0]["message"].get("content") or ""
                ULTIMO_PROVEDOR = f"{modelo} ({nome})"
                _registrar_sucesso()
                return conteudo, ULTIMO_PROVEDOR
            except Exception as e:
                _registrar_falha(f"{nome}: {type(e).__name__} {str(e)[:120]} (tentativa {tentativa + 1})")
    return None, None

# --- observabilidade mínima (honestidade na demo) ---
ULTIMO_ERRO = None
FALHAS = 0
CHAMADAS = 0
ULTIMAS_BRUTAS = []  # respostas brutas da IA nesta execução (auditoria)


def _registrar_falha(msg):
    global ULTIMO_ERRO, FALHAS
    ULTIMO_ERRO = msg
    FALHAS += 1


def _registrar_sucesso():
    global CHAMADAS
    CHAMADAS += 1


def reset_contadores():
    global ULTIMO_ERRO, FALHAS, CHAMADAS, ULTIMAS_BRUTAS
    ULTIMO_ERRO = None
    FALHAS = 0
    CHAMADAS = 0
    ULTIMAS_BRUTAS = []


def status():
    return {"modelo": MODELO, "chamadas": CHAMADAS, "falhas": FALHAS, "ultimo_erro": ULTIMO_ERRO}


def saude(timeout=20):
    """Healthcheck real: 1 completition mínima contra o primeiro provedor disponível."""
    prov = _provedores()
    if not prov:
        return {"modelo": None, "ok": False, "http": None, "detalhe": "nenhuma chave de IA nesta instância (OPENROUTER_API_KEY / NVIDIA_API_KEY)"}
    nome, url, chave, modelo = prov[0]
    corpo = {"model": modelo,
             "messages": [{"role": "user", "content": "Responda apenas: ok"}],
             "temperature": 0, "max_tokens": 5}
    req = urllib.request.Request(
        url, data=json.dumps(corpo).encode(),
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            json.loads(resp.read().decode())
        return {"modelo": f"{modelo} ({nome})", "ok": True, "http": 200, "detalhe": "endpoint respondeu"}
    except urllib.error.HTTPError as e:
        det = ""
        try:
            det = e.read().decode()[:200]
        except Exception:
            pass
        return {"modelo": f"{modelo} ({nome})", "ok": False, "http": e.code, "detalhe": det or str(e)}
    except Exception as e:
        return {"modelo": f"{modelo} ({nome})", "ok": False, "http": None, "detalhe": str(e)[:200]}


_STATUS_VALIDOS = {"CONFORME", "NÃO CONFORME", "EVIDÊNCIA INSUFICIENTE", "NÃO SE APLICA"}


def disponivel():
    return bool(_provedores())


PROMPT = """Você é um verificador de documentos de engenharia. Avalie o item de check-list abaixo contra o trecho do documento.

ITEM: {item} - {descricao}

Responda SOMENTE com um JSON válido, sem texto fora do JSON, neste formato:
{{"status": "CONFORME" | "NÃO CONFORME" | "EVIDÊNCIA INSUFICIENTE" | "NÃO SE APLICA", "justificativa": "texto curto em português", "evidencia": "trecho exato do documento que sustenta a decisão, ou vazio"}}

Regras: use EVIDÊNCIA INSUFICIENTE quando o trecho não permite concluir. Não invente informação fora do trecho.

TRECHO DO DOCUMENTO:
\"\"\"
{trecho}
\"\"\""""


def avaliar_classe_b(item, descricao, trecho, timeout=60, tentativas=2):
    """Chama o LLM. Retorna dict {status, observacao, evidencia} ou None (fallback).
    1 retry: a conta gratuita do NIM oscila de latência e um estouro isolado
    não deve derrubar o item para a heurística."""
    if not disponivel():
        return None
    msgs = [{"role": "user", "content": PROMPT.format(item=item, descricao=descricao, trecho=trecho[:20000])}]
    for tentativa in range(tentativas):
        conteudo, provedor = chamar_chat(msgs, max_tokens=1500, timeout=timeout, tentativas=1)
        if conteudo is None:
            continue
        try:
            m = re.search(r"\{.*\}", conteudo, re.DOTALL)
            if not m:
                raise ValueError("resposta sem JSON")
            res = json.loads(m.group(0))
            if res.get("status") not in _STATUS_VALIDOS:
                raise ValueError("status inválido")
            ULTIMAS_BRUTAS.append({"item": item, "resposta": conteudo[:2000], "provedor": provedor})
            return {"status": res["status"],
                    "observacao": res.get("justificativa", "")[:400],
                    "evidencia": (res.get("evidencia") or "")[:300]}
        except (json.JSONDecodeError, ValueError) as e:
            _registrar_falha(str(e)[:160] + (f" (tentativa {tentativa+1})" if tentativas > 1 else ""))
    return None


PROMPT_COMENTARIO = """Você é um revisor técnico sênior de engenharia escrevendo para outro engenheiro.
Abaixo está o resultado de um check-list de Parecer Técnico (FRM-SEMEC-001) aplicado a um documento, já com status decididos pelo motor (regras, IA ou indicação para humano).

Sua tarefa NÃO é mudar nenhum status: é explicar, em português claro, o que cada achado significa na prática e o que fazer a respeito.

Responda SOMENTE com um JSON válido, sem texto fora do JSON, neste formato:
{{"resumo": "2 a 4 frases com a leitura geral do documento: principais problemas, o que corrigir primeiro e recomendação",
 "comentarios": {{"<ITEM>": "1 a 2 frases de análise prática do item"}}}}

Regras: nunca contradiga o status decidido; não invente fatos fora das evidências mostradas; seja direto; use os códigos de ITEM exatamente como recebidos.
Comente SOMENTE itens com status NÃO CONFORME ou EVIDÊNCIA INSUFICIENTE e classe A ou B; NÃO comente itens CONFORME, NÃO SE APLICA nem classe C (julgamento humano).
Não use os termos "crítica", "crítico" ou "grave". Documentos de outras organizações não seguem o padrão AP de numeração/carimbo: descreva esses achados como "diferença de padrão", não como erro do documento.
Baseie cada comentário APENAS na observacao e na evidencia fornecidas; não contradiga números ou fatos nelas (ex.: se a observação diz que há imagens, não diga que não há).

RESULTADOS DO CHECK-LIST:
{itens_json}"""


def comentar(resultados, timeout=60):
    """Gera resumo geral + comentário por item via LLM. Retorna dict ou None (fallback)."""
    if not disponivel():
        return None
    itens = []
    for r in resultados:
        ev = r["evidencias"][0]["trecho"][:200] if r.get("evidencias") else ""
        itens.append({"item": r["item"], "descricao": r["descricao"], "status": r["status"],
                      "observacao": r["observacao"][:300], "evidencia": ev})
    msgs = [{"role": "user", "content": PROMPT_COMENTARIO.format(
        itens_json=json.dumps(itens, ensure_ascii=False))}]
    conteudo, provedor = chamar_chat(msgs, max_tokens=4000, timeout=timeout, tentativas=1)
    if conteudo is None:
        return None
    try:
        m = re.search(r"\{.*\}", conteudo, re.DOTALL)
        if not m:
            return None
        res = json.loads(m.group(0))
        comentarios = res.get("comentarios")
        if not isinstance(comentarios, dict) or not res.get("resumo"):
            return None
        validos = {r["item"] for r in resultados
                   if r["status"] in ("NÃO CONFORME", "EVIDÊNCIA INSUFICIENTE") and r.get("classe") != "C"}
        comentarios = {k: str(v)[:500] for k, v in comentarios.items() if k in validos}
        ULTIMAS_BRUTAS.append({"item": "_analise_geral", "resposta": conteudo[:3000], "provedor": provedor})
        return {"resumo": str(res["resumo"])[:1200], "comentarios": comentarios,
                "modelo": provedor or MODELO}
    except (json.JSONDecodeError, ValueError) as e:
        _registrar_falha(str(e)[:160])
        return None
