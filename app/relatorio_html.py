# -*- coding: utf-8 -*-
"""Renderiza o registro auditável como página HTML com a identidade visual da AP."""
import html

CORES = {
    "CONFORME": "#2e7d32",
    "NÃO CONFORME": "#c62828",
    "EVIDÊNCIA INSUFICIENTE": "#e6a817",
    "NÃO SE APLICA": "#757575",
}


def _e(s):
    return html.escape(str(s if s is not None else ""))


def _decisao(decisao_por):
    d = (decisao_por or "").lower()
    if "ia via nvidia" in d:
        return "IA (NVIDIA NIM)", "#6b4fa8"
    if "simulada" in d:
        return "Heurística (simulada)", "#8a6d3b"
    if "regra" in d:
        return "Regra determinística", "#1f6fb2"
    return "Humano", "#666666"


CSS = """
 * { box-sizing: border-box; }
 body { font-family: Calibri, 'Segoe UI', Arial, sans-serif; margin: 0; background: #f2f4f8; color: #232323; }
 .topo { background: linear-gradient(135deg, #2b3550 0%, #1b2333 60%, #131a27 100%);
         display: flex; align-items: center; gap: 26px; padding: 20px 40px; }
 .topo img { height: 62px; }
 .topo .t { color: #fff; font-size: 24px; font-weight: 300; letter-spacing: .5px; }
 .topo .s { color: #9db3d4; font-size: 13px; font-weight: 300; margin-top: 4px; letter-spacing: .3px; }
 .wrap { max-width: 1020px; margin: 26px auto 60px; padding: 0 20px; }
 h1 { font-size: 20px; font-weight: 400; margin: 0 0 2px; }
 h2 { font-size: 14px; font-weight: 600; letter-spacing: 1.2px; color: #2b3550;
      margin: 34px 0 10px; border-bottom: 2px solid #d5dce8; padding-bottom: 6px; text-transform: uppercase; }
 .sub { color: #6b7686; font-size: 13px; }
 .card { background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(20,30,50,.08); padding: 22px 26px; }
 .botoes { margin: 14px 0 20px; }
 .btn { display: inline-block; background: #1f6fb2; color: #fff; padding: 9px 18px; border-radius: 4px;
        text-decoration: none; font-size: 14px; margin-right: 10px; }
 .btn.sec { background: #2b3550; }
 table.audit { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 6px; }
 table.audit td { border-bottom: 1px solid #e6eaf1; padding: 8px 10px; vertical-align: top; }
 table.audit td:first-child { color: #5a6474; width: 190px; font-weight: 600; }
 .chips { margin: 18px 0 4px; }
 .chip { color: #fff; padding: 5px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-right: 8px; }
 .item { background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(20,30,50,.08);
         margin: 12px 0; border-left: 5px solid #ccc; overflow: hidden; }
 .item-head { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 13px 18px 9px; }
 .item-desc { font-size: 14.5px; }
 .item-desc b { color: #2b3550; }
 .badge { color: #fff; font-weight: 700; font-size: 11.5px; padding: 5px 12px; border-radius: 3px;
          white-space: nowrap; letter-spacing: .4px; }
 .linha-decisao { padding: 0 18px 8px; }
 .pill { display: inline-block; color: #fff; font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 12px; }
 .obs { font-size: 13.5px; padding: 2px 18px 6px; color: #333; line-height: 1.45; }
 .ev { font-size: 12.5px; color: #5a6474; padding: 3px 18px 3px 38px; font-style: italic; }
 .ev .loc { font-weight: 700; font-style: normal; color: #44506a; }
 .item .foot { height: 8px; }
 .transp { background: #fdf6e3; border: 1px solid #e3d193; border-radius: 8px;
           padding: 14px 20px; font-size: 12.5px; color: #5d5426; margin-top: 26px; line-height: 1.5; }
 details { margin-top: 22px; font-size: 13px; }
 .log { font-size: 11.5px; color: #6b7686; }
 @media(max-width:600px){.topo{padding:18px;flex-wrap:wrap;gap:14px}.topo img{width:240px;height:auto;max-width:100%}.topo .t{font-size:21px}.wrap{padding:0 12px;margin-top:18px}.card{padding:20px 16px}.item-head{flex-direction:column;align-items:flex-start;padding:14px}.badge{white-space:normal}.btn{display:block;margin:8px 0;text-align:center}.chip{display:inline-block;margin:4px 2px}.audit{table-layout:fixed}.audit td{overflow-wrap:anywhere}.audit td:first-child{width:95px}.ev{padding:6px 14px;overflow-wrap:anywhere}.obs{overflow-wrap:anywhere}.linha-decisao{padding:0 14px 8px}}
 .rodape { text-align: center; color: #8a93a3; font-size: 11.5px; margin-top: 34px; }
"""


def render(registro, slug=None):
    d = registro["documento"]
    resumo = {}
    for r in registro["resultados"]:
        resumo[r["status"]] = resumo.get(r["status"], 0) + 1
    chips = " ".join(
        f'<span class="chip" style="background:{CORES[k]}">{_e(k)}: {v}</span>'
        for k, v in resumo.items())
    blocos = []
    secao = None
    for r in registro["resultados"]:
        if r["secao"] != secao:
            secao = r["secao"]
            blocos.append(f'<h2>{_e(secao)}</h2>')
        cor = CORES.get(r["status"], "#333")
        rotulo, cor_dec = _decisao(r.get("decisao_por", ""))
        evs = "".join(
            f'<div class="ev"><span class="loc">{_e(ev["local"])}{" (pág. " + str(ev["pagina"]) + ")" if ev.get("pagina") else ""}:</span> {_e(ev["trecho"][:240])}</div>'
            for ev in r["evidencias"])
        blocos.append(f'''
<div class="item" style="border-left-color:{cor}">
  <div class="item-head">
    <div class="item-desc"><b>{_e(r["item"])}</b> &middot; {_e(r["descricao"])}</div>
    <div class="badge" style="background:{cor}">{_e(r["status"])}</div>
  </div>
  <div class="linha-decisao"><span class="pill" style="background:{cor_dec}">{_e(rotulo)}</span>
    <span class="sub" style="font-size:11.5px"> classe {_e(r["classe"])}</span></div>
  <div class="obs">{_e(r["observacao"])}</div>
  {evs}
  <div class="foot"></div>
</div>''')
    log = "".join(f"<li>{_e(l)}</li>" for l in registro["log"])
    repro = registro.get("reprodutibilidade", {})
    repro_txt = ("sim - duas execuções idênticas" if repro.get("duas_execucoes_identicas")
                 else "não - execuções divergiram (IA real: texto varia; regras determinísticas seguem reproduzíveis)")
    downloads = ""
    if slug:
        downloads = (f'<div class="botoes"><a class="btn" href="/relatorio/{slug}/pdf">Baixar relatório em PDF</a>'
                     f'<a class="btn sec" href="/relatorio/{slug}/json">Baixar JSON de auditoria</a></div>')
    return f'''<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Verificação - {_e(d["nome"])}</title>
<style>{CSS}</style></head><body>
<header class="topo">
  <img src="/static/logo_ap.png" alt="AP Consultoria e Projetos">
  <div><div class="t">Verificação de Documentos de Engenharia</div>
  <div class="s">Módulo 1 &middot; Check-list FRM-SEMEC-001 - Parecer Técnico &middot; MVP</div></div>
</header>
<div class="wrap">
<div class="card">
<h1>Relatório do documento enviado</h1>
<p style="overflow-wrap:anywhere;font-weight:600">{_e(d["nome"])}</p>
<p class="sub">1 documento &middot; {len(registro["resultados"])} itens do checklist Parecer Técnico</p>
<div class="sub">Cada item mostra a evidência (trecho + página) e quem decidiu: regra determinística, IA ou humano.</div>
{downloads}
<details><summary>Rastreabilidade do documento e versões</summary>
<table class="audit">
 <tr><td>Documento</td><td>{_e(d["nome"])}</td></tr>
 <tr><td>Origem</td><td>{_e(d.get("origem_url") or "(upload local)")}</td></tr>
 <tr><td>SHA-256</td><td style="font-family:Consolas,monospace;font-size:11.5px">{_e(d["sha256"])}</td></tr>
 <tr><td>Formato / páginas</td><td>{_e(d["formato"])} / {_e(d["paginas_ou_abas"])}</td></tr>
 <tr><td>Versão das regras</td><td>{_e(registro["regras"]["versao"])}</td></tr>
 <tr><td>Motor</td><td>{_e(registro["regras"]["motor"])}</td></tr>
 <tr><td>Executado (UTC)</td><td>{_e(registro["execucao"]["inicio_utc"])}</td></tr>
 <tr><td>Reprodutível</td><td>{_e(repro_txt)}</td></tr>
</table></details>
<div class="chips">{chips}</div>
</div>
{''.join(blocos)}
<div class="transp"><b>Transparência deste MVP:</b> check-list transcrito de um print (só a aba Parecer Técnico; as outras abas não eram legíveis).
Itens marcados "Heurística (simulada)" ainda não usam IA; itens marcados "IA (NVIDIA NIM)" foram decididos por modelo de linguagem real;
itens marcados "Humano" não são decididos pelo motor.
Documentos de outras organizações não seguem o padrão AP de numeração/carimbo: nesses itens, o achado indica diferença de padrão, não necessariamente erro no documento.</div>
<details><summary>Log de execução (auditoria)</summary><ul class="log">{log}</ul></details>
<details><summary>Outros documentos e histórico</summary><p><a class="btn sec" href="/?historico=1#historico">Abrir histórico</a><a class="btn" href="/?novo=1">Verificar outro documento</a></p></details>
<div class="rodape">MVP - Módulo 1 (verificação de documentos) &middot; LuxVerso &middot; extração local; trechos enviados à NVIDIA quando a IA está ligada</div>
</div></body></html>'''
