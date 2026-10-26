# -*- coding: utf-8 -*-
"""Leitura VISUAL experimental de páginas de desenho (plantas, fluxogramas).

Um modelo de visão recebe a imagem da página e extrai elementos técnicos
(equipamentos, símbolos, ligações, cotas, identificações) como itens com
página e evidência-descritiva. Tudo que sai daqui é HIPÓTESE: o modelo pode
errar elementos, contagens e símbolos — a conferência é humana, na imagem.
"""
import base64
import io
import os

import ia

# Liga/desliga por ambiente: VISAO_DESENHO=0 desativa (volta ao comportamento anterior).
def ativo():
    return os.environ.get("VISAO_DESENHO", "1").strip().lower() not in ("0", "false", "nao", "no", "off")

MAX_PAGINAS_VISAO = int(os.environ.get("VISAO_MAX_PAGINAS", "4"))
DPI = int(os.environ.get("VISAO_DPI", "140"))

PROMPT_VISAO = """Você está vendo a imagem de UMA página de desenho técnico de engenharia (planta, fluxograma, diagrama ou similar).

Liste os elementos técnicos que você consegue identificar com clareza na imagem:
- equipamentos e componentes nomeados ou simbolizados (com a tag/rótulo se houver);
- medidas cotadas (com valor e unidade);
- áreas, volumes ou quantitativos escritos;
- ligações relevantes entre elementos (ex.: tubulação ligando X a Y), quando evidentes;
- identificações do desenho (título, número da folha, escala) quando legíveis.

Responda APENAS um array JSON, sem texto antes ou depois. Cada objeto:
{"item": "rótulo curto do elemento", "valor": "quantidade ou medida", "unidade": "unidade ou vazio",
 "evidencia": "descrição curta de onde/como aparece no desenho (ex.: 'cota no canto superior direito', 'símbolo de válvula na linha do tanque TQ-01')"}

Regras:
- inclua SOMENTE o que você identifica com clareza; na dúvida, deixe de fora;
- no máximo 30 itens;
- não meça nem estime nada que não esteja cotado ou escrito no desenho;
- se a página não tiver nada identificável, responda []."""


def render_pagina_png(caminho_pdf, numero_pagina):
    """Renderiza 1 página do PDF como PNG em memória (PyMuPDF). numero_pagina é 1-based."""
    import pymupdf
    doc = pymupdf.open(caminho_pdf)
    try:
        pag = doc.load_page(numero_pagina - 1)
        zoom = DPI / 72.0
        pix = pag.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def extrair_pagina_visao(caminho_pdf, numero_pagina):
    """Extrai itens de UMA página de desenho via modelo de visão.
    Retorna (itens:list[dict], erro:str|None). Cada item: rotulo, valor, unidade, evidencia."""
    if not ativo():
        return [], "leitura visual desativada (VISAO_DESENHO=0)"
    try:
        png = render_pagina_png(caminho_pdf, numero_pagina)
    except Exception as e:
        return [], f"falha ao renderizar página {numero_pagina}: {e}"
    b64 = base64.b64encode(png).decode()
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT_VISAO},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}]
    bruto = ia.chamar_chat(msgs, max_tokens=2500, timeout=120, tentativas=2)[0]
    if not bruto:
        ia._registrar_falha(f"visao: página {numero_pagina}: resposta vazia do modelo de visão")
        return [], "modelo de visão não respondeu"
    import json as _json
    i = bruto.find("[")
    if i < 0:
        ia._registrar_falha(f"visao: página {numero_pagina}: resposta sem JSON")
        return [], "resposta do modelo de visão sem JSON"
    try:
        obj, _ = _json.JSONDecoder().raw_decode(bruto[i:])
    except ValueError:
        ia._registrar_falha(f"visao: página {numero_pagina}: JSON inválido")
        return [], "JSON inválido do modelo de visão"
    if not isinstance(obj, list):
        return [], "formato inesperado do modelo de visão"
    itens = []
    for it in obj[:30]:
        if not isinstance(it, dict):
            continue
        rotulo = (it.get("item") or "").strip()
        valor = str(it.get("valor") or "").strip()
        if not rotulo or not valor:
            continue
        itens.append({
            "rotulo": rotulo[:120], "valor": valor[:60],
            "unidade": (it.get("unidade") or "").strip()[:20],
            "evidencia": (it.get("evidencia") or "").strip()[:300],
        })
    return itens, None
