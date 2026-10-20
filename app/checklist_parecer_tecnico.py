# -*- coding: utf-8 -*-
"""
Check-list FRM-SEMEC-001 - PARECER TÉCNICO (AP Consultoria e Projetos).

FONTE: transcrito do print da planilha "FRM-SEMEC-001=11.xlsx" no slide 12 do
PPTX da AP (apresentacao de briefing). O print mostra apenas a aba
"PARECER TÉCNICO". As demais abas (DESENHO, ESPEC. TÉCNICA, FOLHA DE DADOS,
LISTA DE MATERIAIS, MEMORIAL DESCRITIVO, MEMÓRIA DE CÁLCULO, REQUISIÇÃO DE M...)
existem no arquivo, mas seu conteúdo NÃO está visível no print e ficou de fora.

Leitura de imagem: itens transcritos com zoom; risco residual de erro de leitura
em caracteres individuais. Validar contra a planilha original antes de produção.

Classes do método (proposta técnica LuxVerso):
  A - determinística (formato, presença, somatório, identificadores): reproduzível.
  B - semântica com IA. NESTE PROTÓTIPO: SIMULADA por heurística determinística,
      rotulada "SIMULADO". Em produção vira chamada a LLM (ex.: Gemini Flash).
  C - julgamento profissional humano. O motor não decide: retorna
      EVIDÊNCIA INSUFICIENTE com o que falta para o humano decidir.
"""

CHECKLIST = [
    # (item, seção, descrição, classe)
    ("PAD-1.0", "PADRONIZAÇÃO", "O PADRÃO UTILIZADO É O MAIS ATUAL?", "C"),
    ("PAD-1.1", "PADRONIZAÇÃO", "O CONTROLE E A DESCRIÇÃO DE REVISÃO ESTÃO PREENCHIDO CORRETAMENTE?", "A"),
    ("PAD-1.2", "PADRONIZAÇÃO", "OS LOGOS DA AP E CLIENTE ESTÃO ATUALIZADOS?", "B"),
    ("PAD-1.3", "PADRONIZAÇÃO", "O RESPONSÁVEL TÉCNICO DO DOCUMENTO ESTÁ CORRETO? E O Nº DO CREA?", "A"),
    ("PAD-1.4", "PADRONIZAÇÃO", "A ORDEM DE SERVIÇO DO PROJETO ESTÁ CORRETA?", "A"),
    ("PAD-1.5", "PADRONIZAÇÃO", "NOME DO CLIENTE, DO PROGRAMA, DA ÁREA E DA UNIDADE ESTÃO CORRETOS?", "A"),
    ("PAD-1.6", "PADRONIZAÇÃO", "TÍTULO DO DOCUMENTO ESTÁ CORRETO E CONFORME LISTA DO PLANEJAMENTO?", "C"),
    ("PAD-1.7", "PADRONIZAÇÃO", "O NÚMERO DO DOCUMENTO E DO ARQUIVO ELETRÔNICO ESTÃO CORRETOS?", "A"),
    ("PAD-1.8", "PADRONIZAÇÃO", "O NÚMERO DE FOLHAS, NA CAPA E EM CADA PÁGINA, ESTÁ CORRETO?", "A"),
    ("PAD-1.9", "PADRONIZAÇÃO", "AS ALTERAÇÕES OCORRIDAS NO DOCUMENTO IMPACTAM NOS DOCUMENTOS DE OUTRAS DISCIPLINAS? ESTAS DISCIPLINAS FORAM INFORMADAS?", "B"),
    ("DT-1.0", "DESCRIÇÃO TÉCNICA", "TAG?", "A"),
    ("DT-1.1", "DESCRIÇÃO TÉCNICA", "PROPOSTA(S) TÉCNICA(S)?", "B"),
    ("DT-1.2", "DESCRIÇÃO TÉCNICA", "DOCUMENTO(S) DE ESCLARECIMENTO?", "B"),
    ("DT-1.3", "DESCRIÇÃO TÉCNICA", "DOCUMENTOS E NORMAS DE REFERÊNCIA?", "A"),
]

ITENS_FORA_DO_PRINT = [
    "Abas DESENHO, ESPEC. TÉCNICA, FOLHA DE DADOS, LISTA DE MATERIAIS, "
    "MEMORIAL DESCRITIVO, MEMÓRIA DE CÁLCULO e REQUISIÇÃO DE M...: abas visíveis "
    "no rodapé do print, conteúdo não legível - não transcritas.",
    "Linhas de OBSERVAÇÕES preenchidas à mão (se houver) não são legíveis no print.",
]

# Versão do conjunto de regras (auditoria): fonte + revisão da transcrição/adaptação
VERSAO_REGRAS = "FRM-SEMEC-001-parecer-tecnico v1.1 (transcrito do print do slide 12 do PPTX da AP; avaliadores adaptados para formatos de documentos reais em 2026-10-19)"
