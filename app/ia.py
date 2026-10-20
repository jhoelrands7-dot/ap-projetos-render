# -*- coding: utf-8 -*-
"""
Ponto de troca para IA real nas regras de classe B (NVIDIA NIM).

- A chave NUNCA fica no código: lida da variável de ambiente NVIDIA_API_KEY.
- Sem chave (ou qualquer erro de rede/parse), o chamador cai na heurística
  SIMULADA já existente, e o resultado diz qual caminho foi usado.
- Endpoint OpenAI-compatível: POST https://integrate.api.nvidia.com/v1/chat/completions
  (fonte: https://docs.api.nvidia.com/nim/reference/llm-apis)
- Modelo padrão: nvidia/nemotron-3-super-120b-a12b (modelo de raciocínio; meta/llama-3.3-70b-instruct foi descontinuado pela NVIDIA em 2026-08-26).
"""
import json, os, re, urllib.request, urllib.error

ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELO = os.environ.get("NVIDIA_MODELO", "nvidia/nemotron-3-super-120b-a12b")
ROTULO_IA = f"IA via NVIDIA NIM ({MODELO})"

_STATUS_VALIDOS = {"CONFORME", "NÃO CONFORME", "EVIDÊNCIA INSUFICIENTE", "NÃO SE APLICA"}


def disponivel():
    return bool(os.environ.get("NVIDIA_API_KEY"))


PROMPT = """Você é um verificador de documentos de engenharia. Avalie o item de check-list abaixo contra o trecho do documento.

ITEM: {item} - {descricao}

Responda SOMENTE com um JSON válido, sem texto fora do JSON, neste formato:
{{"status": "CONFORME" | "NÃO CONFORME" | "EVIDÊNCIA INSUFICIENTE" | "NÃO SE APLICA", "justificativa": "texto curto em português", "evidencia": "trecho exato do documento que sustenta a decisão, ou vazio"}}

Regras: use EVIDÊNCIA INSUFICIENTE quando o trecho não permite concluir. Não invente informação fora do trecho.

TRECHO DO DOCUMENTO:
\"\"\"
{trecho}
\"\"\""""


def avaliar_classe_b(item, descricao, trecho, timeout=30):
    """Chama o LLM. Retorna dict {status, observacao, evidencia} ou None (fallback)."""
    chave = os.environ.get("NVIDIA_API_KEY")
    if not chave:
        return None
    corpo = {
        "model": MODELO,
        "messages": [{"role": "user", "content": PROMPT.format(item=item, descricao=descricao, trecho=trecho[:20000])}],
        "temperature": 0,
        "max_tokens": 1500,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(corpo).encode(),
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read().decode())
        conteudo = dados["choices"][0]["message"].get("content") or ""
        m = re.search(r"\{.*\}", conteudo, re.DOTALL)
        if not m:
            return None
        res = json.loads(m.group(0))
        if res.get("status") not in _STATUS_VALIDOS:
            return None
        return {"status": res["status"],
                "observacao": res.get("justificativa", "")[:400],
                "evidencia": (res.get("evidencia") or "")[:300]}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        return None


PROMPT_COMENTARIO = """Você é um revisor técnico sênior de engenharia escrevendo para outro engenheiro.
Abaixo está o resultado de um check-list de Parecer Técnico (FRM-SEMEC-001) aplicado a um documento, já com status decididos pelo motor (regras, IA ou indicação para humano).

Sua tarefa NÃO é mudar nenhum status: é explicar, em português claro, o que cada achado significa na prática e o que fazer a respeito.

Responda SOMENTE com um JSON válido, sem texto fora do JSON, neste formato:
{{"resumo": "2 a 4 frases com a leitura geral do documento: principais problemas, o que corrigir primeiro e recomendação",
 "comentarios": {{"<ITEM>": "1 a 2 frases de análise prática do item"}}}}

Regras: nunca contradiga o status decidido; não invente fatos fora das evidências mostradas; seja direto; use os códigos de ITEM exatamente como recebidos.

RESULTADOS DO CHECK-LIST:
{itens_json}"""


def comentar(resultados, timeout=60):
    """Gera resumo geral + comentário por item via LLM. Retorna dict ou None (fallback)."""
    chave = os.environ.get("NVIDIA_API_KEY")
    if not chave:
        return None
    itens = []
    for r in resultados:
        ev = r["evidencias"][0]["trecho"][:200] if r.get("evidencias") else ""
        itens.append({"item": r["item"], "descricao": r["descricao"], "status": r["status"],
                      "observacao": r["observacao"][:300], "evidencia": ev})
    corpo = {
        "model": MODELO,
        "messages": [{"role": "user", "content": PROMPT_COMENTARIO.format(
            itens_json=json.dumps(itens, ensure_ascii=False))}],
        "temperature": 0,
        "max_tokens": 4000,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(corpo).encode(),
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = json.loads(resp.read().decode())
        conteudo = dados["choices"][0]["message"].get("content") or ""
        m = re.search(r"\{.*\}", conteudo, re.DOTALL)
        if not m:
            return None
        res = json.loads(m.group(0))
        comentarios = res.get("comentarios")
        if not isinstance(comentarios, dict) or not res.get("resumo"):
            return None
        validos = {r["item"] for r in resultados}
        comentarios = {k: str(v)[:500] for k, v in comentarios.items() if k in validos}
        return {"resumo": str(res["resumo"])[:1200], "comentarios": comentarios,
                "modelo": MODELO}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        return None
