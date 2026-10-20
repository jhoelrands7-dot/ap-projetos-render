# -*- coding: utf-8 -*-
"""Relatório PDF com bloco de auditoria (hash, versões, reprodutibilidade)."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak)

CORES = {
    "CONFORME": colors.HexColor("#2e7d32"),
    "NÃO CONFORME": colors.HexColor("#c62828"),
    "EVIDÊNCIA INSUFICIENTE": colors.HexColor("#f9a825"),
    "NÃO SE APLICA": colors.HexColor("#757575"),
}


def gerar_relatorio(registro, caminho_pdf):
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=estilos["Title"], fontSize=15, spaceAfter=6)
    sub = ParagraphStyle("s", parent=estilos["Normal"], fontSize=8, textColor=colors.HexColor("#555555"))
    h2 = ParagraphStyle("h2", parent=estilos["Heading2"], fontSize=11, spaceBefore=10)
    cel = ParagraphStyle("cel", parent=estilos["Normal"], fontSize=8)
    cel_b = ParagraphStyle("celb", parent=cel, fontName="Helvetica-Bold")

    doc = SimpleDocTemplate(caminho_pdf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=14*mm, bottomMargin=14*mm,
                            title=f"Relatório de verificação - {registro['documento']['nome']}")
    story = []
    d = registro["documento"]
    story.append(Paragraph("Relatório de Verificação - Módulo 1 (MVP)", titulo))
    story.append(Paragraph(f"Check-list FRM-SEMEC-001 - Parecer Técnico", sub))
    story.append(Spacer(1, 6))

    audit = [
        ["Documento", Paragraph(d["nome"], cel)],
        ["Origem", Paragraph(d.get("origem_url") or "(upload local)", cel)],
        ["SHA-256", Paragraph(d["sha256"], cel)],
        ["Formato / páginas", f"{d['formato']} / {d['paginas_ou_abas']}"],
        ["Versão das regras", Paragraph(registro["regras"]["versao"], cel)],
        ["Motor", registro["regras"]["motor"]],
        ["Executado (UTC)", registro["execucao"]["inicio_utc"]],
        ["Reprodutível", "sim - duas execuções idênticas" if registro.get("reprodutibilidade", {}).get("duas_execucoes_identicas") else "não - duas execuções divergiram (IA real: justificativas variam; regras determinísticas seguem reproduzíveis)"],
    ]
    t = Table(audit, colWidths=[35*mm, 145*mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    resumo = {}
    for r in registro["resultados"]:
        resumo[r["status"]] = resumo.get(r["status"], 0) + 1
    story.append(Spacer(1, 8))
    chips = "   ".join(f"{k}: {v}" for k, v in resumo.items())
    story.append(Paragraph(f"Resumo: {chips}", cel_b))
    _ias = registro.get("ia") or {}
    if _ias.get("falhas"):
        av_st = ParagraphStyle("av", parent=cel, fontSize=8.5, textColor=colors.HexColor("#6b5310"),
                               backColor=colors.HexColor("#fff8e6"), borderColor=colors.HexColor("#e5c07b"),
                               borderWidth=0.6, borderPadding=5, spaceBefore=4, spaceAfter=4)
        story.append(Paragraph(
            f"<b>Aviso:</b> a IA ({_ias.get('modelo','')}) falhou {_ias.get('falhas')}x nesta execução "
            f"({_ias.get('ultimo_erro') or 'erro'}). Itens de classe B avaliados por heurística simulada; "
            f"análise geral da IA indisponível.", av_st))
    analise = registro.get("analise_ia") or {}
    comentarios = analise.get("comentarios", {})
    if analise.get("resumo"):
        ia_st = ParagraphStyle("iag", parent=cel, fontSize=8.5, textColor=colors.HexColor("#3d3252"),
                               backColor=colors.HexColor("#f4f0fb"), borderColor=colors.HexColor("#6b4fa8"),
                               borderWidth=0.6, borderPadding=5, spaceBefore=4, spaceAfter=4)
        story.append(Paragraph("<b>ANÁLISE GERAL DA IA (NVIDIA NIM)</b> - texto auxiliar gerado por IA; não altera nenhum status nem a auditoria.", ia_st))
        story.append(Paragraph(analise["resumo"], ia_st))

    secao_atual = None
    for r in registro["resultados"]:
        if r["secao"] != secao_atual:
            secao_atual = r["secao"]
            story.append(Paragraph(secao_atual, h2))
        cor = CORES.get(r["status"], colors.black)
        cab = Table([[Paragraph(f"<b>{r['item']}</b> - {r['descricao']}", cel),
                      Paragraph(f"<b>{r['status']}</b>", ParagraphStyle('x', parent=cel_b, textColor=colors.white, alignment=2))]],
                    colWidths=[140*mm, 40*mm])
        cab.setStyle(TableStyle([
            ("BACKGROUND", (1, 0), (1, 0), cor),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f5f5f5")),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(cab)
        meta = f"Classe {r['classe']} | decisão: {r['decisao_por']}"
        story.append(Paragraph(meta, sub))
        story.append(Paragraph(r["observacao"], cel))
        if comentarios.get(r["item"]):
            ia_item = ParagraphStyle("iai", parent=cel, textColor=colors.HexColor("#3d3252"), leftIndent=8)
            story.append(Paragraph("<font color='#6b4fa8'><b>Análise da IA</b> (auxiliar, não altera o status):</font> " + comentarios[r["item"]], ia_item))
        for ev in r["evidencias"]:
            local = ev["local"] + (f" (pág. {ev['pagina']})" if ev.get("pagina") else "")
            story.append(Paragraph(f"&nbsp;&nbsp;↳ <i>{local}:</i> {ev['trecho'][:220]}", sub))
        story.append(Spacer(1, 5))

    story.append(PageBreak())
    story.append(Paragraph("Log de execução (auditoria)", h2))
    for linha in registro["log"]:
        story.append(Paragraph(linha, sub))
    story.append(Paragraph(
        "Limites: check-list transcrito de um print (só a aba Parecer Técnico); "
        "classe B: itens textuais usam IA (NVIDIA NIM) quando disponível; atualização de logos exige conferência visual. Classe C nunca é decidida pelo motor. O bloco Análise da IA é texto auxiliar gerado por IA (NVIDIA NIM): não participa das decisões de status nem da comparação de reprodutibilidade. "
        "Documentos de outras organizações não seguem o padrão de numeração/carimbo da AP - "
        "achados desse tipo indicam diferença de padrão, não necessariamente erro no documento.", sub))
    doc.build(story)
    return caminho_pdf
