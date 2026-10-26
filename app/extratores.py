# -*- coding: utf-8 -*-
"""
Extração de texto e estrutura de PDF, DOCX e XLSX.

Simplificação do protótipo: campos do carimbo/cabeçalho são localizados por
rótulo ("CLIENTE:", "Nº CREA:" etc.). Documentos reais da AP trazem esses
campos em tabelas; o caminho de produção usa coordenadas de célula/página
(pdfplumber já retorna posições), sem mudar a interface deste módulo.
"""
from dataclasses import dataclass, field
import re

@dataclass
class Pagina:
    numero: int | None      # None quando o formato não tem paginação (DOCX/XLSX)
    nome: str               # "página 1", "aba Plan1", "documento DOCX"
    texto: str
    num_imagens: int = 0
    num_vetores: int = 0  # linhas+retas+curvas (desenho vetorial)

@dataclass
class DocExtraido:
    caminho: str
    formato: str            # pdf | docx | xlsx
    paginas: list = field(default_factory=list)

    @property
    def num_paginas(self):
        return len(self.paginas)

    @property
    def texto_completo(self):
        return "\n".join(p.texto for p in self.paginas)

    def linhas(self):
        """(pagina, local, linha) para cada linha não vazia."""
        for p in self.paginas:
            for ln in p.texto.splitlines():
                if ln.strip():
                    yield p.numero, p.nome, ln.strip()

    def buscar(self, padrao, flags=re.IGNORECASE):
        """Regex linha a linha. Retorna [(pagina, local, linha, match)]."""
        rx = re.compile(padrao, flags)
        achados = []
        for numero, nome, linha in self.linhas():
            m = rx.search(linha)
            if m:
                achados.append((numero, nome, linha, m))
        return achados


def extrair_pdf(caminho):
    import pdfplumber
    doc = DocExtraido(caminho=caminho, formato="pdf")
    with pdfplumber.open(caminho) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            doc.paginas.append(Pagina(
                numero=i, nome=f"página {i}",
                texto=page.extract_text() or "",
                num_imagens=len(page.images),
                num_vetores=len(page.lines) + len(page.rects) + len(page.curves)))
    return doc


def extrair_docx(caminho):
    import docx
    d = docx.Document(caminho)
    partes = []
    for p in d.paragraphs:
        if p.text.strip():
            partes.append(p.text)
    for t in d.tables:
        for row in t.rows:
            celulas = [c.text.strip() for c in row.cells if c.text.strip()]
            if celulas:
                # rótulo e valor na mesma linha, como no carimbo impresso
                partes.append(" ".join(celulas))
    n_imagens = len(d.inline_shapes)
    doc = DocExtraido(caminho=caminho, formato="docx", paginas=[Pagina(
        numero=None, nome="documento DOCX (sem paginação)",
        texto="\n".join(partes), num_imagens=n_imagens)])
    return doc


def extrair_xlsx(caminho):
    import openpyxl
    wb = openpyxl.load_workbook(caminho, data_only=True)
    doc = DocExtraido(caminho=caminho, formato="xlsx")
    for ws in wb.worksheets:
        linhas = []
        for row in ws.iter_rows():
            vals = [(c.coordinate, str(c.value).strip()) for c in row
                    if c.value is not None and str(c.value).strip()]
            if vals:
                refs = ",".join(coord for coord, _ in vals)
                linhas.append(" ".join(v for _, v in vals) + f"  [{refs}]")
        doc.paginas.append(Pagina(
            numero=None, nome=f"aba {ws.title}",
            texto="\n".join(linhas), num_imagens=len(ws._images)))
    return doc


def extrair(caminho):
    ext = caminho.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return extrair_pdf(caminho)
    if ext == "docx":
        return extrair_docx(caminho)
    if ext == "xlsx":
        return extrair_xlsx(caminho)
    raise ValueError(f"formato não suportado: {ext}")
