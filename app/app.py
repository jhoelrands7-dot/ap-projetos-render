# -*- coding: utf-8 -*-
"""
Interface web do MVP - Módulo 1 (verificação de documentos), AP Projetos/LuxVerso.

Uso:  python3 app.py            (sobe em http://127.0.0.1:8000)
Com IA real: definir NVIDIA_API_KEY no ambiente antes de subir.

Fluxo: sobe um PDF/DOCX/XLSX -> motor verifica -> relatório com evidências
-> baixa PDF e JSON de auditoria.
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, request, redirect, send_file, send_from_directory, abort

import auditoria, relatorio, relatorio_html, ia

BASE = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(BASE, "saida")
UPLOADS = os.path.join(BASE, "uploads")
os.makedirs(SAIDA, exist_ok=True)
os.makedirs(UPLOADS, exist_ok=True)

app = Flask(__name__)

# --- Login da demo, com sessao e senha definida no cofre ---
from flask import session, render_template_string
import secrets, hmac, json as _json
from datetime import timedelta
from werkzeug.security import check_password_hash
app.secret_key = os.environ.get("DEMO_SESSION_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True,
                  SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                  MAX_CONTENT_LENGTH=25 * 1024 * 1024)
# Mapa usuario -> hash de senha (scrypt via werkzeug). Nunca senhas em texto.
def _carregar_usuarios():
    bruto = os.environ.get("DEMO_USUARIOS", "")
    try:
        dados = _json.loads(bruto) if bruto else {}
    except ValueError:
        dados = {}
    return {str(u).strip().lower(): str(h) for u, h in dados.items() if u and h}
DEMO_USUARIOS = _carregar_usuarios()

# Identidade visual da instancia (padrao AP; outra marca via env, ex.: WEG)
CLIENTE_NOME = os.environ.get("CLIENTE_NOME", "AP Consultoria e Projetos")
CLIENTE_LOGO = os.environ.get("CLIENTE_LOGO", "/static/logo_ap.png")  # "" = nome em texto, sem logo
CLIENTE_TAGLINE = os.environ.get("CLIENTE_TAGLINE", "Verificação de documentos de engenharia")
LOGIN_USUARIO = os.environ.get("LOGIN_USUARIO", "ap")
def _cor(v, padrao):
    v = (v or "").strip() or padrao
    return v if v.startswith("#") else "#" + v  # env/.env nao aceita '#' (vira comentario)
MARCA_COR1 = _cor(os.environ.get("MARCA_COR1"), "#2b3550")
MARCA_COR2 = _cor(os.environ.get("MARCA_COR2"), "#1b2333")
MARCA_COR3 = _cor(os.environ.get("MARCA_COR3"), "#131a27")
MARCA_GRAD = f"linear-gradient(135deg,{MARCA_COR1} 0%,{MARCA_COR2} 60%,{MARCA_COR3} 100%)"
MARCA_GRAD_LOGIN = f"linear-gradient(135deg,{MARCA_COR1},{MARCA_COR3})"
CLIENTE_NOTA = os.environ.get("CLIENTE_NOTA", "")  # nota extra na tela de login (ex.: disclaimer de demonstracao)
ORC_SUB = os.environ.get("ORC_SUB", "Módulo experimental &middot; ambiente de teste (staging) &middot; não é o app da apresentação")  # subtitulo do header da pagina /orcamento
ORC_AVISO_TITULO = os.environ.get("ORC_AVISO_TITULO", "Ambiente de teste (staging).")  # parte em negrito do aviso no topo da /orcamento
ORC_RODAPE_TAG = os.environ.get("ORC_RODAPE_TAG", "staging")  # etiqueta no rodape da /orcamento
PAGINA_INICIAL = os.environ.get("PAGINA_INICIAL", "")  # se definido (ex.: "/orcamento"), a home redireciona para la; o verificador continua em /?verificador=1
if PAGINA_INICIAL and not PAGINA_INICIAL.startswith("/"):
    PAGINA_INICIAL = ""

def _marca_topo():
    if CLIENTE_LOGO:
        return f'<img src="{CLIENTE_LOGO}" alt="{CLIENTE_NOME}">'
    return (f'<div style="color:#fff;font-size:40px;font-weight:700;letter-spacing:3px;'
            f'font-family:Calibri,Segoe UI,Arial,sans-serif">{CLIENTE_NOME}</div>')

def _css_marca():
    return CSS.replace("linear-gradient(135deg, #2b3550 0%, #1b2333 60%, #131a27 100%)", MARCA_GRAD)
# Hash falso para equalizar tempo de resposta quando o usuario nao existe.
_HASH_FALSO = "scrypt:32768:8:1$Xq0Yy7p9mJ3kQ2wE$f8d0d3a1c5e6b7a9c0d2e4f6a8b0c1d3e5f7a9b1c3d5e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c3d5e7f9"
LOGIN = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Acesso | Demo {{ cliente }}</title>
<style>*{box-sizing:border-box}body{margin:0;font-family:Calibri,Segoe UI,Arial,sans-serif;background:#f2f4f8;color:#243148}.top{padding:30px 24px;background:linear-gradient(135deg,#2b3550,#131a27)}.top img{width:255px;max-width:100%;height:auto}.brand{color:#b8c8df;font-size:15px;margin:16px 0 0}.wrap{padding:30px 20px;max-width:460px;margin:auto}.card{background:#fff;border-radius:12px;padding:28px;box-shadow:0 4px 20px #17213112}h1{font-size:26px;margin:0 0 12px}p{font-size:15px;line-height:1.5;color:#586579}label{display:block;font-size:15px;font-weight:600;margin:22px 0 8px}input{width:100%;padding:14px;border:1px solid #a8b6ca;border-radius:6px;font-size:16px}button{width:100%;margin:26px 0 10px;padding:15px;background:#1f6fb2;color:white;border:0;border-radius:6px;font-size:16px;font-weight:600}.note{font-size:13px;color:#6d7788;text-align:center;line-height:1.6}.error{background:#fff0ef;color:#a22b28;padding:12px;border-radius:5px}.show{font-size:14px;display:flex;gap:8px;align-items:center;font-weight:400}.show input{width:18px;height:18px}input:focus,button:focus{outline:3px solid #9ac8ed;outline-offset:2px}</style></head><body>
<header class="top" style="background:{{ grad }}">{{ marca | safe }}<p class="brand">{{ tagline }}</p></header>
<main class="wrap"><section class="card"><h1>Entrar na demonstração</h1><p>Use o usuário <b>{{ usuario }}</b> e a senha que você definiu no link seguro.</p>
{% if error %}<p class="error" role="alert">{{error}}</p>{% endif %}
<form method="post" action="/login"><input type="hidden" name="csrf" value="{{csrf}}"><label for="username">Usuário</label><input id="username" name="username" value="{{ usuario }}" autocomplete="username" required>
<label for="password">Senha</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<label class="show"><input type="checkbox" onclick="document.getElementById('password').type=this.checked?'text':'password'">Mostrar senha</label>
<button type="submit">Entrar na plataforma</button></form></section>
<p class="note">MVP • Módulo 1 • Parecer Técnico<br>Acesso restrito. Endereço temporário para testes.<br>Trechos dos documentos são enviados a provedor externo de IA (OpenRouter/NVIDIA).<br><br><b>Ambiente de teste:</b> a 1ª abertura pode levar cerca de 1 minuto (o servidor dorme após 15 min sem acesso). Os resultados das extrações são reais.</p>
{% if nota %}<p class="note" style="margin-top:6px">{{ nota }}</p>{% endif %}</main></body></html>"""

@app.before_request
def _auth_demo():
    public = request.endpoint == "login" or request.path in ("/static/logo_ap.png", CLIENTE_LOGO)
    if not public and not session.get("authenticated"):
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect("/")
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    error = None
    if request.method == "POST":
        valid_csrf = hmac.compare_digest(request.form.get("csrf", ""), session["csrf"])
        usuario = request.form.get("username", "").strip().lower()
        senha_hash = DEMO_USUARIOS.get(usuario, _HASH_FALSO)
        valid_pass = check_password_hash(senha_hash, request.form.get("password", "")) and usuario in DEMO_USUARIOS
        if valid_csrf and valid_pass:
            session.clear();session["authenticated"] = True;session["usuario"] = usuario;session.permanent = True
            return redirect("/")
        error = "Usuário ou senha incorretos. Confira os dados e tente novamente."
    return render_template_string(LOGIN, error=error, csrf=session["csrf"], cliente=CLIENTE_NOME, marca=_marca_topo(), tagline=CLIENTE_TAGLINE, usuario=LOGIN_USUARIO, grad=MARCA_GRAD_LOGIN, nota=CLIENTE_NOTA)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login")
# --- fim autenticacao ---


EXTENSOES = {".pdf", ".docx", ".xlsx"}

CORES = {"CONFORME": "#2e7d32", "NÃO CONFORME": "#c62828",
         "EVIDÊNCIA INSUFICIENTE": "#e6a817", "NÃO SE APLICA": "#757575"}

CSS = """
 * { box-sizing: border-box; }
 body { font-family: Calibri, 'Segoe UI', Arial, sans-serif; margin: 0; background: #f2f4f8; color: #232323; }
 .topo { background: linear-gradient(135deg, #2b3550 0%, #1b2333 60%, #131a27 100%);
         display: flex; align-items: center; gap: 26px; padding: 20px 40px; }
 .topo img { height: 62px; }
 .topo .t { color: #fff; font-size: 24px; font-weight: 300; letter-spacing: .5px; }
 .topo .s { color: #9db3d4; font-size: 13px; font-weight: 300; margin-top: 4px; letter-spacing: .3px; }
 .wrap { max-width: 1020px; margin: 26px auto 60px; padding: 0 20px; }
 .card { background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(20,30,50,.08);
         padding: 24px 28px; margin-bottom: 20px; }
 h2 { font-size: 14px; font-weight: 600; letter-spacing: 1.2px; color: #2b3550; margin: 0 0 14px;
      text-transform: uppercase; }
 .drop { border: 2px dashed #9db3cc; border-radius: 8px; padding: 30px; text-align: center;
         background: #f7fafd; }
 .btn { display: inline-block; background: #1f6fb2; color: #fff; padding: 10px 22px; border: none;
        border-radius: 4px; font-size: 14.5px; cursor: pointer; text-decoration: none; font-family: inherit; }
 table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
 th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid #e6eaf1; }
 th { color: #5a6474; font-size: 12px; letter-spacing: .8px; text-transform: uppercase; }
 td a { color: #1f6fb2; text-decoration: none; }
 td a:hover { text-decoration: underline; }
 .chip { color: #fff; padding: 3px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 700; margin-right: 5px; }
 .transp { background: #fdf6e3; border: 1px solid #e3d193; border-radius: 8px; padding: 14px 20px;
           font-size: 12.5px; color: #5d5426; margin-top: 6px; line-height: 1.55; }
 .rodape { text-align: center; color: #8a93a3; font-size: 11.5px; margin-top: 30px; }
 .modo { font-size: 12px; color: #5a6474; margin-top: 10px; }
 .modo b { color: #6b4fa8; }
 @media(max-width:600px){.topo{padding:20px;flex-wrap:wrap;gap:15px}.topo img{max-width:100%;height:auto;width:240px}.topo .t{font-size:22px}.wrap{padding:0 12px}.card{padding:20px 16px}.drop{padding:22px 12px}th,td{padding:10px 4px;font-size:12px}.chip{display:inline-block;margin:3px 0}.transp{padding:14px}}
"""


NOMES = {
    "memorial-descritivo": "Memorial Descritivo - Muro do Museu (Indiaporã 007/2026)",
    "memoria-de-calculo": "Memória de Cálculo - Muro do Museu (Indiaporã 007/2026)",
    "planilha-orcamentaria": "Planilha Orçamentária e Cronograma (Indiaporã 007/2026)",
    "projeto-arquitetonico": "Projeto Arquitetônico (Indiaporã 007/2026)",
    "rrt-projeto": "RRT do Projeto (Indiaporã 007/2026)",
    "termo-de-referencia": "Termo de Referência da Obra (Indiaporã 007/2026)",
    "etp": "Estudo Técnico Preliminar (Indiaporã 007/2026)",
    "parecer-tecnico-seinfra-go": "Parecer Técnico - SEINFRA/GO (processo SEI)",
    "cesan-manual-recebimento-obras": "Procedimento CESAN ENG.002 - Recebimento de Obras",
    "modelo-proposta-docx": "Modelo de Proposta DOCX (Indiaporã 007/2026)",
    "dec-tecnico-operacional-docx": "Declaração Técnico-Operacional DOCX (Indiaporã 007/2026)",
}


def _chips(resumo):
    return " ".join(f'<span class="chip" style="background:{CORES.get(k, "#666")}">{k}: {v}</span>'
                    for k, v in resumo.items())


@app.route("/static/<path:nome>")
def estatico(nome):
    return send_from_directory(os.path.join(BASE, "static"), nome)


PAG_HUB = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>__CLIENTE__ - Verificação de Documentos de Engenharia</title>
<style>__CSS__ .mods{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.mod{display:block;background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(20,30,50,.08);padding:22px 24px;text-decoration:none;color:#232323;border-left:4px solid #1f6fb2}.mod:hover{box-shadow:0 3px 12px rgba(20,30,50,.16)}.mod h3{margin:0 0 8px;font-size:16px;color:#2b3550}.mod p{margin:0;font-size:13px;color:#5a6474;line-height:1.5}.tag{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.6px;color:#fff;background:#6b4fa8;border-radius:10px;padding:2px 9px;margin-bottom:10px}.tag.m1{background:#2e7d32}</style></head>
<body>
<header class="topo">__MARCA__
<div><div class="t">Verificação de Documentos de Engenharia</div>
<div class="s">__ORC_SUB__</div></div></header>
<div class="wrap">
<div class="mods">
 <a class="mod" href="/orcamento"><span class="tag">EXPERIMENTAL</span><h3>Extração de checklist de orçamento</h3><p>Preenche um checklist de orçamento (XLSX) a partir de um documento técnico: valor, unidade, página e evidência por campo.</p></a>
 <a class="mod" href="/cruzamento"><span class="tag">MÓDULO 2 &middot; EXPERIMENTAL</span><h3>Cruzamento entre documentos</h3><p>Cruza de 2 a 5 documentos do mesmo projeto: itens quantificados, tags de equipamento e CNPJ. Convergências e divergências para confirmar, com evidências dos dois lados.</p></a>
 <a class="mod" href="/normas"><span class="tag">MÓDULO 3 &middot; EXPERIMENTAL</span><h3>Confronto com normas</h3><p>Casa os números dos documentos com parâmetros de normas públicas (NR-24, NR-35). Toda conclusão é hipótese, com o trecho oficial da norma, a fonte e as evidências na tela — e o que não cobre, declarado.</p></a>
</div>
<div class="rodape">ambiente de teste (__ORC_RODAPE_TAG__) &middot; os resultados são reais</div>
</div></body></html>"""


@app.route("/")
def home():
    if PAGINA_INICIAL and not request.args.get("verificador"):
        return (PAG_HUB.replace("__CSS__", _css_marca()).replace("__MARCA__", _marca_topo())
                .replace("__CLIENTE__", CLIENTE_NOME).replace("__ORC_SUB__", ORC_SUB)
                .replace("__ORC_RODAPE_TAG__", ORC_RODAPE_TAG))
    ultimo = session.get("ultimo_relatorio")
    if ultimo and not request.args.get("novo") and not request.args.get("historico") and os.path.isfile(os.path.join(SAIDA, ultimo + ".json")):
        return redirect("/relatorio/" + ultimo)
    linhas = ""
    indice_path = os.path.join(SAIDA, "indice.json")
    docs = json.load(open(indice_path)) if os.path.exists(indice_path) else []
    slugs_indice = {d["slug"] for d in docs}
    for d in docs:
        try:
            reg = json.load(open(os.path.join(SAIDA, d["slug"] + ".json")))
            usa_ia = any("IA via NVIDIA" in r.get("decisao_por", "") for r in reg["resultados"])
        except Exception:
            usa_ia = False
        tag = ' <span style="color:#6b4fa8;font-size:11px;font-weight:700">IA</span>' if usa_ia else ""
        nome = NOMES.get(d["slug"], d["arquivo"][:62])
        linhas += (f'<tr><td><a href="/relatorio/{d["slug"]}">{nome}</a>{tag}</td>'
                   f'<td>{_chips(d["resumo"])}</td></tr>')
    outros = sorted(f[:-5] for f in os.listdir(SAIDA)
                    if f.endswith(".json") and f != "indice.json" and f[:-5] not in slugs_indice)
    for slug in outros:
        try:
            reg = json.load(open(os.path.join(SAIDA, f"{slug}.json")))
            resumo = auditoria.resumo_status(reg["resultados"])
            usa_ia = any("IA via NVIDIA" in r.get("decisao_por", "") for r in reg["resultados"])
            tag = ' <span style="color:#6b4fa8;font-size:11px;font-weight:700">IA</span>' if usa_ia else ""
            linhas += (f'<tr><td><a href="/relatorio/{slug}">{reg["documento"]["nome"][:62]}</a>{tag} '
                       f'<span style="color:#98a1ae;font-size:11px">(upload)</span></td>'
                       f'<td>{_chips(resumo)}</td></tr>')
        except Exception:
            pass
    modo_ia = (f"ligada (modelo {ia.MODELO}) &middot; <a href='/saude-ia' target='_blank'>testar agora</a>"
               if os.environ.get("NVIDIA_API_KEY")
               else "desligada (heurística simulada nos itens de classe B)")
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{CLIENTE_NOME} - Verificação de Documentos de Engenharia</title><style>{_css_marca()}</style><style>.spin{{display:inline-block;width:16px;height:16px;border:3px solid #c9d4e4;border-top-color:#1f6fb2;border-radius:50%;animation:giro .8s linear infinite;vertical-align:-3px;margin-right:8px}}@keyframes giro{{to{{transform:rotate(360deg)}}}}.carregando{{display:none;margin-top:12px;font-size:14px;color:#2b3550;font-weight:600}}.barra{{margin-top:10px;height:8px;background:#e3e9f2;border-radius:4px;overflow:hidden}}.barra>div{{height:100%;width:30%;background:#1f6fb2;border-radius:4px;animation:carrega 1.4s ease-in-out infinite}}@keyframes carrega{{0%{{margin-left:-30%}}100%{{margin-left:100%}}}}</style></head>
<body>
<header class="topo">
  {_marca_topo()}
  <div><div class="t">Verificação de Documentos de Engenharia</div>
  <div class="s">Módulo 1 &middot; Check-list FRM-SEMEC-001 - Parecer Técnico &middot; MVP</div></div>
</header>
<div class="wrap">
<div class="card">
 <h2>Verificar um documento</h2>
 <form method="post" action="/verificar" enctype="multipart/form-data" onsubmit="document.getElementById('um-loading').style.display='block';this.querySelector('button').disabled=true;">
  <div class="drop">
   <input type="file" name="arquivo" accept=".pdf,.docx,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/msword,application/vnd.ms-excel" required>
   <p style="color:#667;font-size:12.5px;margin:12px 0">PDF, DOCX ou XLSX. O documento é processado localmente.</p>
   <button class="btn" type="submit">Verificar documento</button>
   <div class="carregando" id="um-loading" role="status"><span class="spin"></span>Analisando o documento... leva de 1 a 3 minutos. Não feche esta página.<div class="barra"><div></div></div></div>
  </div>
 </form>
 <p class="modo" style="margin-top:14px"><b>Novo (teste):</b> <a href="/orcamento">extração de checklist de orçamento</a> (módulo experimental).</p>
 <p class="modo">IA nesta instância: <b>{modo_ia}</b> &middot; cada item do relatório mostra quem decidiu: regra determinística, IA (NVIDIA NIM), heurística simulada ou humano.</p>
</div>
<div class="card" style="margin-top:18px">
 <h2>Verificar vários documentos (até 5)</h2>
 <div class="drop">
  <input type="file" id="fila-input" multiple accept=".pdf,.docx,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/msword,application/vnd.ms-excel" style="display:none">
  <button class="btn" id="fila-add" type="button" style="background:#4a5b74">Adicionar documento</button>
  <div id="fila-selecao" style="font-size:13px;color:#445;margin-top:10px">Nenhum documento na fila.</div>
  <ul id="fila-pendente" style="list-style:none;padding:0;margin:6px 0 0;font-size:13.5px"></ul>
  <p style="color:#667;font-size:12.5px;margin:12px 0">Toque em <b>Adicionar documento</b> e escolha <b>um arquivo por vez</b> (PDF, DOCX ou XLSX), até 5. Eles são enviados um por vez, nesta ordem, e cada relatório é liberado assim que fica pronto. Cada documento leva cerca de 1 a 3 minutos.</p>
  <button class="btn" id="fila-btn" type="button">Verificar em fila</button>
 </div>
 <div id="fila-erro" role="alert" style="display:none;background:#fff0ef;color:#a22b28;padding:10px;border-radius:5px;margin-top:10px;font-size:13.5px"></div>
 <div id="fila-progresso" style="font-size:13.5px;margin-top:10px"></div>
 <div class="carregando" id="fila-loading" role="status" style="margin-top:8px"><span class="spin"></span><span id="fila-loading-txt">Analisando...</span><div class="barra"><div></div></div></div>
 <ul id="fila-lista" style="list-style:none;padding:0;margin:10px 0 0;font-size:13.5px"></ul>
 <details style="margin-top:14px"><summary style="cursor:pointer;font-size:13px;color:#445">A fila não reagiu neste aparelho? Use o envio alternativo</summary>
  <form method="post" action="/verificar-lote" enctype="multipart/form-data" style="margin-top:8px" onsubmit="document.getElementById('lote-loading').style.display='block';this.querySelector('button').disabled=true;">
   <input type="file" name="arquivos" multiple accept=".pdf,.docx,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/msword,application/vnd.ms-excel" required>
   <p style="color:#667;font-size:12px;margin:8px 0">Envio direto de até 3 arquivos de uma vez, sem a fila. Esta página pode ficar carregando por alguns minutos; os links aparecem ao final.</p>
   <button class="btn" type="submit">Enviar em lote</button>
   <div class="carregando" id="lote-loading" role="status"><span class="spin"></span>Enviando e analisando em lote... pode levar alguns minutos. Não feche esta página.<div class="barra"><div></div></div></div>
  </form>
 </details>
 <div style="font-size:11px;color:#9aa4b2;margin-top:10px">versão da página: fila-2026-10-20a</div>
</div>
<script>
(function(){{
 var BUILD="fila-2026-10-20a";
 var inp=document.getElementById("fila-input"),btn=document.getElementById("fila-btn"),
     add=document.getElementById("fila-add"),
     prog=document.getElementById("fila-progresso"),lista=document.getElementById("fila-lista"),
     sel=document.getElementById("fila-selecao"),pend=document.getElementById("fila-pendente");
 window.addEventListener("error",function(e){{
  var av=document.getElementById("fila-erro");
  if(av){{av.style.display="block";av.textContent="A fila encontrou um erro neste navegador ("+(e.message||"desconhecido")+"). Use o envio alternativo abaixo. ["+BUILD+"]";}}
 }});
 var arqs=[];
 function mostraSel(){{
  if(!arqs.length){{sel.textContent="Nenhum documento na fila.";}}
  else{{sel.innerHTML="<b>"+arqs.length+" de 5 na fila:</b>";}}
  pend.innerHTML="";
  arqs.forEach(function(f,k){{
   var li=document.createElement("li");li.style.cssText="padding:6px 0;border-bottom:1px solid #e6eaf1";
   li.innerHTML="<b>"+(k+1)+". "+f.name+"</b> ("+(f.size/1048576).toFixed(1)+" MB) ";
   var x=document.createElement("a");x.href="#";x.textContent="remover";x.style.cssText="color:#a22b28;margin-left:8px";
   x.addEventListener("click",function(ev){{ev.preventDefault();arqs.splice(k,1);mostraSel();}});
   li.appendChild(x);pend.appendChild(li);
  }});
  add.disabled=arqs.length>=5;
  add.textContent=arqs.length>=5?"Fila cheia (5)":"Adicionar documento";
 }}
 add.addEventListener("click",function(){{inp.click();}});
 function coleta(){{
  try{{
   var fs=inp.files||[],pegou=0;
   for(var q=0;q<fs.length;q++){{
    var f=fs[q];
    if(arqs.length>=5){{break;}}
    if(arqs.some(function(a){{return a.name===f.name&&a.size===f.size;}})){{continue;}}
    arqs.push(f);pegou++;
   }}
   if(fs.length&&!pegou&&arqs.length>=5){{sel.innerHTML="<b>Fila cheia:</b> remova um documento para adicionar outro.";}}
  }}catch(e){{prog.textContent="Não consegui ler os arquivos escolhidos ("+e.message+"). Use o envio alternativo abaixo. ["+BUILD+"]";}}
  inp.value="";mostraSel();
 }}
 inp.addEventListener("change",coleta);
 inp.addEventListener("input",coleta);
 mostraSel();
 btn.addEventListener("click",function(){{
  if(!arqs.length){{prog.textContent="Adicione de 1 a 5 documentos primeiro.";return;}}
  btn.disabled=true;add.disabled=true;lista.innerHTML="";
  var itens=arqs.map(function(a,i){{
   var li=document.createElement("li");li.style.cssText="padding:7px 0;border-bottom:1px solid #e6eaf1";
   li.textContent=(i+1)+". "+a.name+" - aguardando";lista.appendChild(li);return li;}});
  var i=0;
  function passo(){{
   if(i>=arqs.length){{document.getElementById("fila-loading").style.display="none";prog.innerHTML="<b>Fila concluída.</b> Os relatórios ficam no histórico abaixo enquanto o serviço estiver acordado.";btn.disabled=false;arqs=[];mostraSel();return;}}
   var a=arqs[i],li=itens[i],n=i+1,ini=Date.now(),tent=0;
   function rot(){{
    var s=Math.floor((Date.now()-ini)/1000),m=Math.floor(s/60),ss=("0"+(s%60)).slice(-2);
    prog.textContent="Processando "+n+" de "+arqs.length+": "+a.name+" (há "+m+":"+ss+(n===1?"; o primeiro pode demorar mais se o serviço estiver em repouso":"")+")...";
    li.innerHTML="<b>"+n+". "+a.name+"</b> - processando há "+m+":"+ss+"..."+(tent?" (nova tentativa)":"");
   }}
   var fl=document.getElementById("fila-loading"),flt=document.getElementById("fila-loading-txt");
   fl.style.display="block";flt.textContent="Analisando documento "+n+" de "+arqs.length+": "+a.name+" (1 a 3 min cada) — não feche esta página.";
   rot();var tick=setInterval(rot,1000);
   function enviar(){{
    var ctl=new AbortController(),to=setTimeout(function(){{ctl.abort();}},300000);
    var fd=new FormData();fd.append("arquivo",a,a.name);
    fetch("/verificar?modo=json",{{method:"POST",body:fd,signal:ctl.signal}}).then(function(r){{
     if(!r.ok)throw new Error("HTTP "+r.status);return r.json();}}).then(function(d){{
     clearTimeout(to);clearInterval(tick);
     li.innerHTML="<b>"+n+". "+a.name+"</b> - pronto: <a href='"+d.url+"'>abrir relatório</a>";
     i++;passo();}}).catch(function(e){{
     clearTimeout(to);
     if(tent<1){{tent=1;return enviar();}}
     clearInterval(tick);
     li.innerHTML="<b>"+n+". "+a.name+"</b> - <span style='color:#a22b28'>falhou ("+(e.name==="AbortError"?"tempo esgotado":e.message)+"). Tente este arquivo de novo.</span>";
     i++;passo();}});
   }}
   enviar();
  }}
  passo();
 }});
}})();
</script>
<details class="card" id="historico"><summary style="cursor:pointer;font-weight:600">Histórico de documentos (secundário)</summary>
 <table><tr><th>Documento</th><th>Resultado</th></tr>{linhas}</table>
</details>
<div class="transp"><b>Transparência deste MVP:</b> check-list transcrito de um print (só a aba Parecer Técnico; as demais abas não eram legíveis).
Itens marcados "Heurística (simulada)" ainda não usam IA; itens "IA (NVIDIA NIM)" foram decididos por modelo de linguagem real; itens "Humano" não são decididos pelo motor.
Documentos de outras organizações não seguem o padrão AP de numeração/carimbo: nesses itens, o achado indica diferença de padrão, não necessariamente erro no documento.</div>
<div class="rodape">MVP - Módulo 1 (verificação de documentos) &middot; LuxVerso &middot; extração local; trechos enviados à NVIDIA quando a IA está ligada</div>
</div></body></html>"""


@app.after_request
def _sem_cache_html(resp):
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/saude-ia")
def saude_ia():
    return ia.saude()


@app.route("/verificar", methods=["POST"])
def verificar():
    arq = request.files.get("arquivo")
    if not arq or not arq.filename:
        return redirect("/")
    ext = os.path.splitext(arq.filename)[1].lower()
    if ext not in EXTENSOES:
        return "Formato não suportado (use PDF, DOCX ou XLSX).", 400
    slug = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(arq.filename)[0].lower().encode("ascii", "ignore").decode()).strip("-")[:60]
    slug = (slug or "documento") + "-" + str(int(time.time()))[-5:]
    caminho = os.path.join(UPLOADS, slug + ext)
    arq.save(caminho)
    try:
        registro, _ = auditoria.verificar_reprodutibilidade(caminho, origem="upload via interface web")
    except ValueError as e:
        if request.args.get("modo") == "json":
            return {"erro": str(e)}, 400
        return str(e), 400
    registro["documento"]["nome"] = arq.filename
    with open(os.path.join(SAIDA, f"{slug}.json"), "w") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    relatorio.gerar_relatorio(registro, os.path.join(SAIDA, f"{slug}.pdf"))
    if request.args.get("modo") == "json":
        return {"slug": slug, "url": f"/relatorio/{slug}", "resumo": auditoria.resumo_status(registro["resultados"])}
    session["ultimo_relatorio"] = slug
    return redirect(f"/relatorio/{slug}")


@app.route("/verificar-lote", methods=["POST"])
def verificar_lote():
    arquivos = [a for a in request.files.getlist("arquivos") if a and a.filename][:3]
    if not arquivos:
        return redirect("/")
    saidas = []
    for arq in arquivos:
        ext = os.path.splitext(arq.filename)[1].lower()
        if ext not in EXTENSOES:
            saidas.append((arq.filename, None, "formato não suportado"))
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(arq.filename)[0].lower().encode("ascii", "ignore").decode()).strip("-")[:60]
        slug = (slug or "documento") + "-" + str(int(time.time()))[-5:]
        caminho = os.path.join(UPLOADS, slug + ext)
        arq.save(caminho)
        try:
            registro, _ = auditoria.verificar_reprodutibilidade(caminho, origem="upload em lote via interface web")
            registro["documento"]["nome"] = arq.filename
            with open(os.path.join(SAIDA, f"{slug}.json"), "w") as f:
                json.dump(registro, f, ensure_ascii=False, indent=2)
            relatorio.gerar_relatorio(registro, os.path.join(SAIDA, f"{slug}.pdf"))
            saidas.append((arq.filename, slug, None))
        except Exception as e:
            saidas.append((arq.filename, None, str(e)[:120]))
    itens = "".join(
        f'<li style="padding:8px 0;border-bottom:1px solid #e6eaf1"><b>{nome}</b> - '
        + (f'<a href="/relatorio/{slug}">abrir relatório</a>' if slug else f'<span style="color:#a22b28">falhou ({erro})</span>')
        + "</li>"
        for nome, slug, erro in saidas)
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Envio em lote - AP</title><style>{CSS}</style></head>
<body><div class="wrap"><div class="card"><h2>Envio em lote concluído</h2>
<ul style="list-style:none;padding:0;font-size:14px">{itens}</ul>
<p style="margin-top:14px"><a href="/">Voltar para a página inicial</a></p>
</div></div></body></html>"""


@app.route("/relatorio/<slug>")
def ver_relatorio(slug):
    if not re.fullmatch(r"[a-z0-9\-]+", slug):
        abort(404)
    caminho = os.path.join(SAIDA, f"{slug}.json")
    if not os.path.exists(caminho):
        abort(404)
    registro = json.load(open(caminho))
    session["ultimo_relatorio"] = slug
    return relatorio_html.render(registro, slug=slug)


@app.route("/relatorio/<slug>/<tipo>")
def baixar(slug, tipo):
    if not re.fullmatch(r"[a-z0-9\-]+", slug) or tipo not in ("pdf", "json"):
        abort(404)
    caminho = os.path.join(SAIDA, f"{slug}.{tipo}")
    if not os.path.exists(caminho):
        abort(404)
    return send_file(caminho, as_attachment=True)




# --- Extracao de checklist de orcamento (EXPERIMENTAL - so nesta branch/staging) ---
import threading, uuid
import extracao_orcamento, cruzamento

JOBS_ORC = {}


def _limpar_jobs():
    agora = time.time()
    for jid, j in list(JOBS_ORC.items()):
        if agora - j.get("criado_em", agora) > 3 * 3600:
            for k in ("pdf_path", "xlsx_path", "saida_path"):
                try:
                    if j.get(k) and os.path.exists(j[k]):
                        os.remove(j[k])
                except OSError:
                    pass
            JOBS_ORC.pop(jid, None)


def _roda_orcamento(jid):
    j = JOBS_ORC[jid]
    try:
        stats = extracao_orcamento.executar(j["pdf_path"], j["xlsx_path"], j["saida_path"])
        j.update(status="pronto", stats=stats)
    except Exception as e:
        j.update(status="erro", erro=str(e)[:300])


PAG_ORCAMENTO = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Extração de checklist de orçamento | __CLIENTE__ (teste)</title>
<style>__CSS__ .spin{display:inline-block;width:16px;height:16px;border:3px solid #c9d4e4;border-top-color:#1f6fb2;border-radius:50%;animation:giro .8s linear infinite;vertical-align:-3px;margin-right:8px}@keyframes giro{to{transform:rotate(360deg)}}.barra{margin-top:10px;height:8px;background:#e3e9f2;border-radius:4px;overflow:hidden}.barra>div{height:100%;width:30%;background:#1f6fb2;border-radius:4px;animation:carrega 1.4s ease-in-out infinite}@keyframes carrega{0%{margin-left:-30%}100%{margin-left:100%}}.warn{background:#fdf6e3;border:1px solid #e3d193;border-radius:8px;padding:12px 16px;font-size:12.5px;color:#5d5426;line-height:1.55;margin-top:14px}label{display:block;font-size:13.5px;font-weight:600;margin:14px 0 6px;color:#2b3550}</style></head>
<body>
<header class="topo">__MARCA__
<div><div class="t">Extração de checklist de orçamento</div>
<div class="s">__ORC_SUB__</div></div></header>
<div class="wrap">
<div class="warn" style="margin-bottom:14px"><b>__ORC_AVISO_TITULO__</b> A primeira abertura pode levar cerca de 1 minuto e, após 15 minutos sem acesso, o servidor reinicia: extração em andamento e resultados ainda não baixados se perdem — baixe a planilha ao final de cada extração. O que você já baixou não se perde. <b>Os resultados são reais:</b> cada extração roda de verdade sobre os arquivos enviados.</div>
<div class="card">
 <h2>1. Envie o documento e o checklist</h2>
 <form id="f">
  <label for="doc">Documento técnico (PDF com texto; escaneado não funciona - sem OCR)</label>
  <input type="file" id="doc" name="documento" accept=".pdf,application/pdf" required>
  <label for="chk">Checklist de orçamento (XLSX no layout padrão: aba "Checklist de orçamento")</label>
  <input type="file" id="chk" name="checklist" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required>
  <p style="margin-top:16px"><button class="btn" type="submit">Extrair campos</button></p>
 </form>
 <div id="prog" style="display:none;margin-top:14px;font-size:14px;color:#2b3550;font-weight:600"><span class="spin"></span><span id="prog-txt">Extraindo... leva de 2 a 4 minutos. Não feche esta página.</span><div class="barra"><div></div></div></div>
 <div id="erro" role="alert" style="display:none;background:#fff0ef;color:#a22b28;padding:10px;border-radius:5px;margin-top:12px;font-size:13.5px"></div>
 <div id="pronto" style="display:none;margin-top:16px"></div>
</div>
<div class="warn"><b>O que este módulo faz:</b> a IA propõe valor, unidade, página e evidência para cada campo do checklist; uma revisão automática confere se a evidência existe de verdade no texto (o que não confirma vira "A confirmar" ou "Não encontrado").<br>
<b>Limites:</b> sem OCR; deslocamento entre campos parecidos (ex.: material do corpo vs. do impulsor) ainda exige conferência humana; a IA pode oscilar entre execuções. A planilha sai no mesmo layout do checklist enviado, com uma aba "Auditoria" ao final (hash dos arquivos, modelo, data).<br>
<b>Privacidade:</b> trechos do documento são enviados a provedor externo de IA (OpenRouter/NVIDIA) durante a extração. Teste uma extração por vez — este ambiente processa uma requisição por vez.</div>
<div class="rodape">extracao-orcamento v0.4.0 &middot; __ORC_RODAPE_TAG__ &middot; <a href="/">início</a> &middot; <a href="/cruzamento">cruzamento entre documentos (Módulo 2 experimental)</a> &middot; <a href="/normas">confronto com normas (Módulo 3 experimental)</a></div>
</div>
<script>
var f=document.getElementById("f"),prog=document.getElementById("prog"),ptxt=document.getElementById("prog-txt"),
    erro=document.getElementById("erro"),pronto=document.getElementById("pronto");
f.addEventListener("submit",function(ev){
 ev.preventDefault();erro.style.display="none";pronto.style.display="none";
 var fd=new FormData(f);prog.style.display="block";
 fetch("/orcamento/novo",{method:"POST",body:fd}).then(function(r){
  if(!r.ok)return r.text().then(function(t){throw new Error(t)});
  return r.json();}).then(function(d){
  var ini=Date.now();
  var tick=setInterval(function(){
   var s=Math.floor((Date.now()-ini)/1000),m=Math.floor(s/60),ss=("0"+(s%60)).slice(-2);
   ptxt.textContent="Extraindo... há "+m+":"+ss+". Não feche esta página.";
   fetch("/orcamento/"+d.job+"/status").then(function(r){return r.json();}).then(function(st){
    if(st.status==="pronto"){clearInterval(tick);prog.style.display="none";
     var chips=Object.keys(st.stats||{}).map(function(k){return "<b>"+k+": "+st.stats[k]+"</b>"}).join(" &middot; ");
     pronto.innerHTML='<div class="card" style="margin:0"><h2>2. Baixe a planilha preenchida</h2><p style="font-size:13.5px">'+chips+'</p><p><a class="btn" href="/orcamento/'+d.job+'/baixar">Baixar XLSX preenchido</a></p></div>';
     pronto.style.display="block";}
    else if(st.status==="erro"){clearInterval(tick);prog.style.display="none";
     erro.textContent="A extração falhou: "+(st.erro||"erro desconhecido");erro.style.display="block";}
   }).catch(function(){});
  },5000);
 }).catch(function(e){prog.style.display="none";erro.textContent="Falha no envio: "+e.message;erro.style.display="block";});
});
</script></body></html>"""


@app.route("/orcamento")
def orcamento():
    return (PAG_ORCAMENTO.replace("__CSS__", _css_marca()).replace("__MARCA__", _marca_topo()).replace("__CLIENTE__", CLIENTE_NOME)
            .replace("__ORC_SUB__", ORC_SUB).replace("__ORC_AVISO_TITULO__", ORC_AVISO_TITULO).replace("__ORC_RODAPE_TAG__", ORC_RODAPE_TAG))


@app.route("/orcamento/novo", methods=["POST"])
def orcamento_novo():
    _limpar_jobs()
    doc = request.files.get("documento")
    chk = request.files.get("checklist")
    if not doc or not doc.filename or not chk or not chk.filename:
        return "Envie o documento (PDF) e o checklist (XLSX).", 400
    if os.path.splitext(doc.filename)[1].lower() != ".pdf":
        return "Documento precisa ser PDF.", 400
    if os.path.splitext(chk.filename)[1].lower() != ".xlsx":
        return "Checklist precisa ser XLSX.", 400
    jid = uuid.uuid4().hex[:12]
    pdf_path = os.path.join(UPLOADS, f"orc-{jid}.pdf")
    xlsx_path = os.path.join(UPLOADS, f"orc-{jid}.xlsx")
    saida_path = os.path.join(SAIDA, f"orc-{jid}-preenchido.xlsx")
    doc.save(pdf_path); chk.save(xlsx_path)
    JOBS_ORC[jid] = {"status": "processando", "criado_em": time.time(),
                     "pdf_path": pdf_path, "xlsx_path": xlsx_path, "saida_path": saida_path}
    threading.Thread(target=_roda_orcamento, args=(jid,), daemon=True).start()
    return {"job": jid}


@app.route("/orcamento/<jid>/status")
def orcamento_status(jid):
    j = JOBS_ORC.get(jid)
    if not j:
        return {"status": "erro", "erro": "job não encontrado (o serviço pode ter reiniciado; envie de novo)"}, 404
    return {"status": j["status"], "stats": j.get("stats"), "erro": j.get("erro")}


@app.route("/orcamento/<jid>/baixar")
def orcamento_baixar(jid):
    j = JOBS_ORC.get(jid)
    if not j or j.get("status") != "pronto" or not os.path.exists(j["saida_path"]):
        abort(404)
    return send_file(j["saida_path"], as_attachment=True,
                     download_name="checklist_orcamento_preenchido.xlsx")


# ================= Módulo 2 experimental: cruzamento entre documentos =================

JOBS_CRUZ = {}


def _limpar_jobs_cruz():
    agora = time.time()
    for jid, j in list(JOBS_CRUZ.items()):
        if agora - j.get("criado_em", agora) > 3 * 3600:
            for p in j.get("paths", []):
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass
            sj = j.get("json_path")
            try:
                if sj and os.path.exists(sj):
                    os.remove(sj)
            except OSError:
                pass
            JOBS_CRUZ.pop(jid, None)


def _roda_cruzamento(jid):
    j = JOBS_CRUZ[jid]
    try:
        res = cruzamento.executar(j["docs"])
        with open(j["json_path"], "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        j.update(status="pronto")
    except Exception as e:
        j.update(status="erro", erro=str(e)[:400])


PAG_CRUZ = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Cruzamento entre documentos | __CLIENTE__ (teste)</title>
<style>__CSS__ .spin{display:inline-block;width:16px;height:16px;border:3px solid #c9d4e4;border-top-color:#1f6fb2;border-radius:50%;animation:giro .8s linear infinite;vertical-align:-3px;margin-right:8px}@keyframes giro{to{transform:rotate(360deg)}}.barra{margin-top:10px;height:8px;background:#e3e9f2;border-radius:4px;overflow:hidden}.barra>div{height:100%;width:30%;background:#1f6fb2;border-radius:4px;animation:carrega 1.4s ease-in-out infinite}@keyframes carrega{0%{margin-left:-30%}100%{margin-left:100%}}.warn{background:#fdf6e3;border:1px solid #e3d193;border-radius:8px;padding:12px 16px;font-size:12.5px;color:#5d5426;line-height:1.55;margin-top:14px}label{display:block;font-size:13.5px;font-weight:600;margin:14px 0 6px;color:#2b3550}.docrow{display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap}.docrow select{padding:9px;border:1px solid #a8b6ca;border-radius:6px;font-size:14px}</style></head>
<body>
<header class="topo">__MARCA__
<div><div class="t">Cruzamento entre documentos &middot; Módulo 2 (experimental)</div>
<div class="s">__ORC_SUB__</div></div></header>
<div class="wrap">
<div class="warn" style="margin-bottom:14px"><b>__ORC_AVISO_TITULO__</b> Módulo 2 em versão experimental: o cruzamento é uma proposta de leitura, não um veredito — toda divergência aparece com as evidências dos dois lados para um engenheiro confirmar.</div>
<div class="card">
 <h2>1. Envie de 2 a 5 documentos do mesmo projeto</h2>
 <form id="f">
  <label for="docs">Documentos (PDF com texto; escaneado não funciona - sem OCR)</label>
  <input type="file" id="docs" name="docs" accept=".pdf,application/pdf" multiple required>
  <div id="linhas"></div>
  <p style="margin-top:16px"><button class="btn" type="submit">Cruzar documentos</button></p>
 </form>
 <div id="prog" style="display:none;margin-top:14px;font-size:14px;color:#2b3550;font-weight:600"><span class="spin"></span><span id="prog-txt">Cruzando... leva alguns minutos. Não feche esta página.</span><div class="barra"><div></div></div></div>
 <div id="erro" role="alert" style="display:none;background:#fff0ef;color:#a22b28;padding:10px;border-radius:5px;margin-top:12px;font-size:13.5px"></div>
</div>
<div class="warn"><b>O que este módulo faz:</b> a IA lê cada documento e extrai os itens quantificados (valores com unidade, página e evidência); o sistema cruza os itens com o mesmo rótulo entre os documentos, além de tags de equipamento e CNPJ. Valores iguais viram convergência; diferentes viram divergência <b>para confirmar</b>.<br>
<b>Sobre plantas e fluxogramas:</b> o que está <b>escrito</b> no documento entra no cruzamento (carimbo, legenda, tags, notas, listas). Páginas de desenho passam por <b>leitura visual experimental</b>: um modelo de visão tenta identificar elementos, símbolos, cotas e ligações — tudo marcado como <b>[leitura visual — hipótese]</b> e sujeito a erro; confira na imagem. Coordenadas e escala exatas não são garantidas. PDF escaneado sem camada de texto continua fora (sem OCR).<br>
<b>Privacidade:</b> trechos dos documentos são enviados a provedor externo de IA (OpenRouter/NVIDIA). Teste um cruzamento por vez — este ambiente processa uma requisição por vez.</div>
<div class="rodape">__CRUZ_VERSAO__ &middot; __ORC_RODAPE_TAG__ &middot; <a href="/">início</a> &middot; <a href="/orcamento">extração de checklist</a></div>
</div>
<script>
var inp=document.getElementById("docs"),linhas=document.getElementById("linhas");
var DISC=["Arquitetura","Civil / Estrutural","Elétrica","Hidráulica / Sanitária","Mecânica","Tubulação","Instrumentação","Processo","Orçamento / Planejamento","Memorial / Especificação","Outro"];
inp.addEventListener("change",function(){
 linhas.innerHTML="";
 for(var i=0;i<inp.files.length;i++){
  var row=document.createElement("div");row.className="docrow";
  var nm=document.createElement("span");nm.textContent=inp.files[i].name;nm.style.fontSize="13px";nm.style.minWidth="220px";
  var sel=document.createElement("select");sel.name="disciplina";
  DISC.forEach(function(d){var o=document.createElement("option");o.value=d;o.textContent=d;sel.appendChild(o);});
  row.appendChild(nm);row.appendChild(sel);linhas.appendChild(row);
 }
});
var f=document.getElementById("f"),prog=document.getElementById("prog"),ptxt=document.getElementById("prog-txt"),erro=document.getElementById("erro");
f.addEventListener("submit",function(ev){
 ev.preventDefault();erro.style.display="none";
 if(inp.files.length<2){erro.textContent="Envie pelo menos 2 documentos para cruzar.";erro.style.display="block";return;}
 if(inp.files.length>5){erro.textContent="Máximo de 5 documentos neste ambiente de teste.";erro.style.display="block";return;}
 var fd=new FormData(f);prog.style.display="block";
 fetch("/cruzamento/novo",{method:"POST",body:fd}).then(function(r){
  if(!r.ok)return r.text().then(function(t){throw new Error(t)});
  return r.json();}).then(function(d){
  var ini=Date.now();
  var tick=setInterval(function(){
   var s=Math.floor((Date.now()-ini)/1000),m=Math.floor(s/60),ss=("0"+(s%60)).slice(-2);
   ptxt.textContent="Cruzando... há "+m+":"+ss+". Não feche esta página.";
   fetch("/cruzamento/job/"+d.job+"/status").then(function(r){return r.json();}).then(function(st){
    if(st.status==="pronto"){clearInterval(tick);window.location="/cruzamento/resultado/"+d.job;}
    else if(st.status==="erro"){clearInterval(tick);prog.style.display="none";
     erro.textContent="O cruzamento falhou: "+(st.erro||"erro desconhecido");erro.style.display="block";}
   }).catch(function(){});
  },5000);
 }).catch(function(e){prog.style.display="none";erro.textContent="Falha no envio: "+e.message;erro.style.display="block";});
});
</script></body></html>"""


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _chips_cruz(resumo):
    cores = {"convergências": "#2e7d32", "divergências p/ confirmar": "#c62828",
             "sem correspondente": "#e6a817", "tags compartilhadas": "#1f6fb2"}
    partes = [(f'{resumo["convergencias"]} convergências', cores["convergências"]),
              (f'{resumo["divergencias_para_confirmar"]} divergências p/ confirmar', cores["divergências p/ confirmar"]),
              (f'{resumo["itens_sem_correspondente"]} itens sem correspondente', cores["sem correspondente"]),
              (f'{resumo["tags_compartilhadas"]} tags compartilhadas', cores["tags compartilhadas"])]
    return " ".join(f'<span class="chip" style="background:{c}">{t}</span>' for t, c in partes)


def _linhas_item(res, item):
    docs = res["documentos"]
    linhas = []
    divergente = item["status"] == "diverge"
    for oc in item["ocorrencias"]:
        d = docs[oc["doc"]]
        ev = _esc(oc["evidencia"]) if oc["evidencia"] else "<i>sem evidência</i>"
        if oc.get("origem") == "visao":
            ev += ' <span style="color:#7b1fa2;font-size:11px;font-weight:700">[leitura visual — hipótese]</span>'
        elif not oc["evidencia_ok"]:
            ev += ' <span style="color:#c62828;font-size:11px">(evidência não confirmada no texto)</span>'
        pag = f'página {oc["pagina"]}' if oc["pagina"] else "página não identificada"
        estilo = ' style="color:#c62828;font-weight:700"' if divergente else ""
        disc = f' <span style="color:#8a93a3">[{_esc(d["disciplina"])}]</span>' if d["disciplina"] else ""
        linhas.append(
            f'<tr><td>{_esc(d["nome"])}{disc}</td>'
            f'<td{estilo}>{_esc(oc["valor"])} {_esc(oc["unidade"])}</td>'
            f'<td style="font-size:12px">{pag} — “{ev}”</td></tr>')
    return "".join(linhas)


def _secao_itens(res, status, titulo, cor, aberto):
    itens = [i for i in res["itens"] if i["status"] == status]
    if not itens:
        return ""
    linhas = []
    for it in itens:
        linhas.append(
            f'<tr><td colspan="3" style="background:#f2f4f8;font-weight:600;color:{cor}">{_esc(it["rotulo"])}</td></tr>'
            + _linhas_item(res, it))
    return (f'<details {"open" if aberto else ""} style="margin-bottom:14px"><summary style="cursor:pointer;font-weight:600;color:{cor}">{titulo} ({len(itens)})</summary>'
            f'<table style="margin-top:8px"><tr><th>Documento</th><th>Valor</th><th>Evidência</th></tr>{"".join(linhas)}</table></details>')


def _render_cruzamento(res):
    docs = res["documentos"]
    linhas_docs = "".join(
        f'<tr><td>{_esc(d["nome"])}</td><td>{_esc(d["disciplina"])}</td><td>{d["paginas"]}</td>'
        f'<td>{d["num_itens"]}</td><td>{len(d["tags"])}</td>'
        f'<td style="font-size:11px;font-family:monospace">{d["sha256"][:16]}…</td></tr>'
        for d in docs)
    avisos = "".join(f'<div class="warn" style="margin-bottom:8px">{_esc(a)}</div>' for a in res.get("avisos", []))
    n_sem_texto = sum(len(d["paginas_sem_texto"]) for d in docs)
    if n_sem_texto:
        avisos += (f'<div class="warn" style="margin-bottom:8px">{n_sem_texto} página(s) sem camada de texto no total — '
                   'conteúdo de desenho/escaneado dessas páginas não entrou no cruzamento (sem OCR).</div>')
    cnpjs = res.get("cnpjs", [])
    if len(cnpjs) == 1 and len(cnpjs[0]["docs"]) == len(docs):
        bloco_cnpj = (f'<p style="font-size:13.5px">✔ Mesmo CNPJ do proprietário em todos os documentos: '
                      f'<b>{_esc(cnpjs[0]["cnpj"])}</b></p>')
    elif len(cnpjs) > 1:
        partes = ", ".join(f'{_esc(c["cnpj"])} em {len(c["docs"])} doc(s)' for c in cnpjs)
        bloco_cnpj = f'<p style="font-size:13.5px;color:#c62828">⚠ CNPJs diferentes entre os documentos: {partes}</p>'
    elif cnpjs:
        bloco_cnpj = (f'<p style="font-size:13.5px;color:#8a93a3">CNPJ {_esc(cnpjs[0]["cnpj"])} '
                      f'em {len(cnpjs[0]["docs"])} de {len(docs)} documentos.</p>')
    else:
        bloco_cnpj = '<p style="font-size:13.5px;color:#8a93a3">Nenhum CNPJ identificado nos documentos.</p>'
    tags_comp = [t for t in res["tags"] if t["status"] == "compartilhada"]
    bloco_tags = ""
    if tags_comp:
        lis = "".join(f'<tr><td style="font-family:monospace">{_esc(t["tag"])}</td><td>'
                      + ", ".join(_esc(docs[i]["nome"]) for i in t["docs"]) + "</td></tr>" for t in tags_comp)
        bloco_tags = (f'<details style="margin-bottom:14px"><summary style="cursor:pointer;font-weight:600;color:#1f6fb2">'
                      f'Tags de equipamento em mais de um documento ({len(tags_comp)})</summary>'
                      f'<table style="margin-top:8px"><tr><th>Tag</th><th>Aparece em</th></tr>{lis}</table></details>')
    ia_info = res.get("ia", {})
    prov = ia_info.get("provedor") or "indisponível"
    falhas = ia_info.get("falhas", 0)
    aviso_ia = (f'<div class="warn" style="margin-bottom:8px">A IA ({_esc(prov)}) falhou {falhas}x nesta execução; '
                'itens podem ter ficado de fora. Rode de novo se o resultado parecer incompleto.</div>') if falhas else ""
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Resultado do cruzamento | {CLIENTE_NOME} (teste)</title>
<style>{_css_marca()} .warn{{background:#fdf6e3;border:1px solid #e3d193;border-radius:8px;padding:12px 16px;font-size:12.5px;color:#5d5426;line-height:1.55}} details{{font-size:13.5px}} summary{{font-size:14.5px}}</style></head>
<body>
<header class="topo">{_marca_topo()}
<div><div class="t">Resultado do cruzamento &middot; Módulo 2 (experimental)</div>
<div class="s">cruzamento entre {len(docs)} documentos &middot; {res["execucao"]["inicio_utc"][:19].replace("T", " ")} UTC</div></div></header>
<div class="wrap">
<div class="card">
 <h2>Resumo</h2>
 <p>{_chips_cruz(res["resumo"])}</p>
 {bloco_cnpj}
 <p style="font-size:12.5px;color:#5a6474">Toda divergência é uma <b>hipótese para confirmar</b>: os valores vêm de documentos
 com redações diferentes e a IA pode oscilar. As evidências dos dois lados estão na tela.</p>
</div>
{avisos}
{aviso_ia}
<div class="card">
 <h2>Divergências para confirmar</h2>
 {_secao_itens(res, "diverge", "Divergências", "#c62828", True) or '<p style="font-size:13.5px;color:#8a93a3">Nenhuma divergência encontrada nos itens cruzados.</p>'}
</div>
<div class="card">
 <h2>Convergências</h2>
 {_secao_itens(res, "converge", "Convergências", "#2e7d32", True) or '<p style="font-size:13.5px;color:#8a93a3">Nenhum item convergente entre documentos.</p>'}
</div>
<div class="card">
 <h2>Itens sem correspondente e tags</h2>
 {_secao_itens(res, "sem_correspondente", "Itens encontrados em um só documento", "#e6a817", False) or '<p style="font-size:13.5px;color:#8a93a3">Todos os itens aparecem em mais de um documento.</p>'}
 {bloco_tags}
</div>
<div class="card">
 <h2>Documentos cruzados</h2>
 <table><tr><th>Documento</th><th>Disciplina</th><th>Páginas</th><th>Itens</th><th>Tags</th><th>SHA-256</th></tr>{linhas_docs}</table>
</div>
<div class="card transp" style="margin-top:0">
 <b>Auditoria:</b> {res["versao"]} &middot; IA: {_esc(prov)} ({ia_info.get("chamadas", 0)} chamadas, {falhas} falhas)
 &middot; execução {res["execucao"]["inicio_utc"][:19].replace("T", " ")} → {res["execucao"]["fim_utc"][:19].replace("T", " ")} UTC.
 Hashes SHA-256 de cada documento na tabela acima. Resultado completo em JSON no botão abaixo.<br>
 <b>Limites:</b> sem OCR; casamento por rótulo de item, então itens com nomes muito diferentes podem não casar;
 toda divergência exige confirmação humana. <b>Leitura visual de desenhos (experimental):</b> itens marcados
 [leitura visual — hipótese] vieram de um modelo de visão sobre a imagem da página — o modelo pode errar
 elementos, contagens e símbolos, e não garante coordenadas nem escala; a confirmação é humana, olhando o desenho.
</div>
<p style="margin-top:14px"><a class="btn" href="/cruzamento/resultado/{request.path.rsplit('/', 1)[-1]}/json">Baixar JSON de auditoria</a>
<a class="btn" style="background:#5a6474;margin-left:8px" href="/cruzamento">Novo cruzamento</a>
<a class="btn" style="background:#5a6474;margin-left:8px" href="/">Início</a></p>
<div class="rodape">{res["versao"].split(" (")[0]} &middot; {ORC_RODAPE_TAG}</div>
</div></body></html>"""


@app.route("/cruzamento")
def cruzamento_pagina():
    return (PAG_CRUZ.replace("__CSS__", _css_marca()).replace("__MARCA__", _marca_topo())
            .replace("__CLIENTE__", CLIENTE_NOME).replace("__ORC_SUB__", ORC_SUB)
            .replace("__ORC_AVISO_TITULO__", ORC_AVISO_TITULO).replace("__ORC_RODAPE_TAG__", ORC_RODAPE_TAG)
            .replace("__CRUZ_VERSAO__", cruzamento.VERSAO.split(" (")[0]))


@app.route("/cruzamento/novo", methods=["POST"])
def cruzamento_novo():
    _limpar_jobs_cruz()
    arquivos = request.files.getlist("docs")
    disciplinas = request.form.getlist("disciplina")
    arquivos = [a for a in arquivos if a and a.filename]
    if len(arquivos) < 2:
        return "Envie pelo menos 2 documentos PDF para cruzar.", 400
    if len(arquivos) > cruzamento.MAX_DOCS:
        return f"Máximo de {cruzamento.MAX_DOCS} documentos neste ambiente de teste.", 400
    for a in arquivos:
        if os.path.splitext(a.filename)[1].lower() != ".pdf":
            return "Todos os documentos precisam ser PDF.", 400
    jid = uuid.uuid4().hex[:12]
    docs, paths = [], []
    for i, a in enumerate(arquivos):
        p = os.path.join(UPLOADS, f"cruz-{jid}-{i}.pdf")
        a.save(p)
        paths.append(p)
        disc = disciplinas[i] if i < len(disciplinas) else ""
        docs.append({"caminho": p, "nome": a.filename, "disciplina": disc})
    json_path = os.path.join(SAIDA, f"cruz-{jid}.json")
    JOBS_CRUZ[jid] = {"status": "processando", "criado_em": time.time(),
                      "docs": docs, "paths": paths, "json_path": json_path}
    threading.Thread(target=_roda_cruzamento, args=(jid,), daemon=True).start()
    return {"job": jid}


@app.route("/cruzamento/job/<jid>/status")
def cruzamento_status(jid):
    j = JOBS_CRUZ.get(jid)
    if not j:
        return {"status": "erro", "erro": "job não encontrado (o serviço pode ter reiniciado; envie de novo)"}, 404
    return {"status": j["status"], "erro": j.get("erro")}


@app.route("/cruzamento/resultado/<jid>")
def cruzamento_resultado(jid):
    j = JOBS_CRUZ.get(jid)
    res = None
    if j and j.get("status") == "pronto" and os.path.exists(j["json_path"]):
        with open(j["json_path"], encoding="utf-8") as f:
            res = json.load(f)
    if res is None:
        abort(404)
    return _render_cruzamento(res)


@app.route("/cruzamento/resultado/<jid>/json")
def cruzamento_json(jid):
    j = JOBS_CRUZ.get(jid)
    if not j or j.get("status") != "pronto" or not os.path.exists(j["json_path"]):
        abort(404)
    return send_file(j["json_path"], as_attachment=True,
                     download_name="cruzamento_auditoria.json")



# ================= Módulo 3 experimental: casamento e confronto com normas =================

import normas

JOBS_NRM = {}


def _limpar_jobs_nrm():
    agora = time.time()
    for jid, j in list(JOBS_NRM.items()):
        if agora - j.get("criado_em", agora) > 3 * 3600:
            for p in j.get("paths", []):
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass
            sj = j.get("json_path")
            try:
                if sj and os.path.exists(sj):
                    os.remove(sj)
            except OSError:
                pass
            JOBS_NRM.pop(jid, None)


def _roda_normas(jid):
    j = JOBS_NRM[jid]
    try:
        res = normas.executar(j["docs"])
        with open(j["json_path"], "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        j.update(status="pronto")
    except Exception as e:
        j.update(status="erro", erro=str(e)[:400])


PAG_NRM = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Confronto com normas | __CLIENTE__ (teste)</title>
<style>__CSS__ .spin{display:inline-block;width:16px;height:16px;border:3px solid #c9d4e4;border-top-color:#1f6fb2;border-radius:50%;animation:giro .8s linear infinite;vertical-align:-3px;margin-right:8px}@keyframes giro{to{transform:rotate(360deg)}}.barra{margin-top:10px;height:8px;background:#e3e9f2;border-radius:4px;overflow:hidden}.barra>div{height:100%;width:30%;background:#1f6fb2;border-radius:4px;animation:carrega 1.4s ease-in-out infinite}@keyframes carrega{0%{margin-left:-30%}100%{margin-left:100%}}.warn{background:#fdf6e3;border:1px solid #e3d193;border-radius:8px;padding:12px 16px;font-size:12.5px;color:#5d5426;line-height:1.55;margin-top:14px}label{display:block;font-size:13.5px;font-weight:600;margin:14px 0 6px;color:#2b3550}</style></head>
<body>
<header class="topo">__MARCA__
<div><div class="t">Confronto com normas &middot; Módulo 3 (experimental)</div>
<div class="s">__ORC_SUB__</div></div></header>
<div class="wrap">
<div class="warn" style="margin-bottom:14px"><b>__ORC_AVISO_TITULO__</b> Módulo 3 em versão experimental: toda conclusão é uma <b>hipótese</b>, mostrada com a evidência do documento de um lado e o trecho oficial da norma do outro. Quem confirma é o profissional.</div>
<div class="card">
 <h2>1. Envie de 1 a 5 documentos do mesmo projeto</h2>
 <form id="f">
  <label for="docs">Documentos (PDF com texto; escaneado não funciona - sem OCR)</label>
  <input type="file" id="docs" name="docs" accept=".pdf,application/pdf" multiple required>
  <p style="margin-top:16px"><button class="btn" type="submit">Confrontar com as normas</button></p>
 </form>
 <div id="prog" style="display:none;margin-top:14px;font-size:14px;color:#2b3550;font-weight:600"><span class="spin"></span><span id="prog-txt">Confrontando... leva alguns minutos. Não feche esta página.</span><div class="barra"><div></div></div></div>
 <div id="erro" role="alert" style="display:none;background:#fff0ef;color:#a22b28;padding:10px;border-radius:5px;margin-top:12px;font-size:13.5px"></div>
</div>
<div class="warn"><b>O que este módulo faz:</b> a IA extrai os itens quantificados dos documentos e o sistema os casa com os parâmetros de normas públicas da biblioteca (hoje: NR-24 — instalações sanitárias e chuveiros por trabalhador; NR-35 — trabalho em altura acima de 2,00 m). Cada parâmetro sai com status de hipótese, os números encontrados, o trecho oficial da norma e o link da fonte.<br>
<b>O que NÃO cobre:</b> normas ABNT (pagas, não reproduzidas), códigos de obras municipais, o desenho dos documentos (linhas e símbolos não são lidos) e o julgamento de aplicabilidade — que é humano.<br>
<b>Privacidade:</b> trechos dos documentos são enviados a provedor externo de IA (OpenRouter/NVIDIA). Teste um confronto por vez — este ambiente processa uma requisição por vez.</div>
<div class="rodape">__NRM_VERSAO__ &middot; __ORC_RODAPE_TAG__ &middot; <a href="/">início</a> &middot; <a href="/orcamento">extração de checklist</a> &middot; <a href="/cruzamento">cruzamento (Módulo 2)</a></div>
</div>
<script>
var inp=document.getElementById("docs");
var f=document.getElementById("f"),prog=document.getElementById("prog"),ptxt=document.getElementById("prog-txt"),erro=document.getElementById("erro");
f.addEventListener("submit",function(ev){
 ev.preventDefault();erro.style.display="none";
 if(inp.files.length<1){erro.textContent="Envie pelo menos 1 documento PDF.";erro.style.display="block";return;}
 if(inp.files.length>5){erro.textContent="Máximo de 5 documentos neste ambiente de teste.";erro.style.display="block";return;}
 var fd=new FormData(f);prog.style.display="block";
 fetch("/normas/novo",{method:"POST",body:fd}).then(function(r){
  if(!r.ok)return r.text().then(function(t){throw new Error(t)});
  return r.json();}).then(function(d){
  var ini=Date.now();
  var tick=setInterval(function(){
   var s=Math.floor((Date.now()-ini)/1000),m=Math.floor(s/60),ss=("0"+(s%60)).slice(-2);
   ptxt.textContent="Confrontando... há "+m+":"+ss+". Não feche esta página.";
   fetch("/normas/job/"+d.job+"/status").then(function(r){return r.json();}).then(function(st){
    if(st.status==="pronto"){clearInterval(tick);window.location="/normas/resultado/"+d.job;}
    else if(st.status==="erro"){clearInterval(tick);prog.style.display="none";
     erro.textContent="O confronto falhou: "+(st.erro||"erro desconhecido");erro.style.display="block";}
   }).catch(function(){});
  },5000);
 }).catch(function(e){prog.style.display="none";erro.textContent="Falha no envio: "+e.message;erro.style.display="block";});
});
</script></body></html>"""

_STATUS_NRM = {
    "atende_hipotese": ("Hipótese: atende", "#2e7d32"),
    "atencao_hipotese": ("Hipótese: atenção", "#c62828"),
    "aplicavel_hipotese": ("Hipótese: norma se aplica", "#e6a817"),
    "nao_encontrado": ("Dados não encontrados", "#8a93a3"),
}


def _card_norma(res, n):
    docs = res["documentos"]
    rotulo, cor = _STATUS_NRM.get(n["status"], (n["status"], "#8a93a3"))
    evs = []
    for ev in n.get("evidencias", [])[:8]:
        d = docs[ev["doc"]]
        pag = f'página {ev["pagina"]}' if ev.get("pagina") else "página não identificada"
        txt = _esc(ev["evidencia"]) if ev.get("evidencia") else "<i>sem evidência</i>"
        evs.append(f'<tr><td>{_esc(d["nome"])}</td><td>{_esc(ev["rotulo"])}: <b>{_esc(ev["valor"])} {_esc(ev["unidade"])}</b></td>'
                   f'<td style="font-size:12px">{pag} — “{txt}”</td></tr>')
    tab_ev = (f'<table style="margin-top:8px"><tr><th>Documento</th><th>Número encontrado</th><th>Evidência</th></tr>{"".join(evs)}</table>'
              if evs else "")
    return f"""<div class="card">
 <h2 style="margin-bottom:4px">{_esc(n["norma"])} &middot; item {_esc(n["item"])} — {_esc(n["titulo"])}
 <span class="chip" style="background:{cor};vertical-align:2px;margin-left:6px">{rotulo}</span></h2>
 <p style="font-size:13.5px"><b>Regra:</b> {_esc(n["resumo_regra"])}</p>
 <p style="font-size:13.5px"><b>Leitura do sistema:</b> {_esc(n["detalhe"])}</p>
 <blockquote style="margin:10px 0;padding:10px 14px;border-left:4px solid #1f6fb2;background:#f2f6fb;font-size:13px;color:#2b3550">
  <b>Trecho oficial da norma:</b> “{_esc(n["texto"])}”<br>
  <span style="font-size:12px;color:#5a6474">Fonte: {_esc(n["fonte_nome"])} — <a href="{_esc(n["fonte_url"])}" target="_blank" rel="noopener">{_esc(n["fonte_url"])}</a></span>
 </blockquote>
 {tab_ev}
 <p style="font-size:12px;color:#8a93a3;margin-top:8px">{_esc(n["obs"])}</p>
</div>"""


def _render_normas(res):
    docs = res["documentos"]
    linhas_docs = "".join(
        f'<tr><td>{_esc(d["nome"])}</td><td>{d["paginas"]}</td><td>{d["num_itens"]}</td>'
        f'<td style="font-size:11px;font-family:monospace">{d["sha256"][:16]}…</td></tr>'
        for d in docs)
    cards = "".join(_card_norma(res, n) for n in res["normas"])
    nao_cobre = "".join(f"<li>{_esc(x)}</li>" for x in res.get("nao_cobre", []))
    meta = res.get("meta", {})
    avisos = "".join(f'<div class="warn" style="margin-bottom:8px">{_esc(a)}</div>' for a in res.get("avisos", []))
    r = res["resumo"]
    chips = " ".join([
        f'<span class="chip" style="background:#2e7d32">{r["hipoteses_atendimento"]} hipótese(s) de atendimento</span>',
        f'<span class="chip" style="background:#c62828">{r["hipoteses_atencao"]} pedindo atenção</span>',
        f'<span class="chip" style="background:#e6a817">{r["hipoteses_aplicavel"]} norma(s) possivelmente aplicável(is)</span>',
        f'<span class="chip" style="background:#8a93a3">{r["nao_encontrados"]} sem dados no documento</span>'])
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Resultado do confronto | {CLIENTE_NOME} (teste)</title>
<style>{_css_marca()} .warn{{background:#fdf6e3;border:1px solid #e3d193;border-radius:8px;padding:12px 16px;font-size:12.5px;color:#5d5426;line-height:1.55}}</style></head>
<body>
<header class="topo">{_marca_topo()}
<div><div class="t">Resultado do confronto &middot; Módulo 3 (experimental)</div>
<div class="s">{len(docs)} documento(s) &middot; {meta.get("inicio", "")[:19].replace("T", " ")} UTC</div></div></header>
<div class="wrap">
<div class="card">
 <h2>Resumo</h2>
 <p>{chips}</p>
 <p style="font-size:12.5px;color:#5a6474">Toda conclusão é uma <b>hipótese</b>: os números vêm do texto dos
 documentos e a IA pode oscilar. A decisão final é sempre do profissional.</p>
</div>
{avisos}
{cards}
<div class="card">
 <h2>O que este confronto NÃO cobre</h2>
 <ul style="font-size:13.5px;line-height:1.7">{nao_cobre}</ul>
</div>
<div class="card">
 <h2>Documentos confrontados</h2>
 <table><tr><th>Documento</th><th>Páginas</th><th>Itens extraídos</th><th>SHA-256</th></tr>{linhas_docs}</table>
</div>
<div class="card transp" style="margin-top:0">
 <b>Auditoria:</b> {res["versao"]} &middot; execução {meta.get("inicio", "")[:19].replace("T", " ")} →
 {meta.get("fim", "")[:19].replace("T", " ")} UTC ({meta.get("duracao_s", "?")}s,
 {meta.get("ia", {}).get("chamadas", 0)} chamadas de IA, {meta.get("ia", {}).get("falhas", 0)} falhas).
 Textos de norma transcritos dos PDFs oficiais do MTE (links em cada cartão).
</div>
<p style="margin-top:14px"><a class="btn" href="/normas/resultado/{request.path.rsplit('/', 1)[-1]}/json">Baixar JSON de auditoria</a>
<a class="btn" style="background:#5a6474;margin-left:8px" href="/normas">Novo confronto</a>
<a class="btn" style="background:#5a6474;margin-left:8px" href="/">Início</a></p>
<div class="rodape">{res["versao"].split(" (")[0]} &middot; {ORC_RODAPE_TAG}</div>
</div></body></html>"""


@app.route("/normas")
def normas_pagina():
    return (PAG_NRM.replace("__CSS__", _css_marca()).replace("__MARCA__", _marca_topo())
            .replace("__CLIENTE__", CLIENTE_NOME).replace("__ORC_SUB__", ORC_SUB)
            .replace("__ORC_AVISO_TITULO__", ORC_AVISO_TITULO).replace("__ORC_RODAPE_TAG__", ORC_RODAPE_TAG)
            .replace("__NRM_VERSAO__", normas.VERSAO.split(" (")[0]))


@app.route("/normas/novo", methods=["POST"])
def normas_novo():
    _limpar_jobs_nrm()
    arquivos = [a for a in request.files.getlist("docs") if a and a.filename]
    if not arquivos:
        return "Envie pelo menos 1 documento PDF.", 400
    if len(arquivos) > 5:
        return "Máximo de 5 documentos neste ambiente de teste.", 400
    for a in arquivos:
        if os.path.splitext(a.filename)[1].lower() != ".pdf":
            return "Todos os documentos precisam ser PDF.", 400
    jid = uuid.uuid4().hex[:12]
    docs, paths = [], []
    for i, a in enumerate(arquivos):
        p = os.path.join(UPLOADS, f"nrm-{jid}-{i}.pdf")
        a.save(p)
        paths.append(p)
        docs.append({"caminho": p, "nome": a.filename})
    json_path = os.path.join(SAIDA, f"nrm-{jid}.json")
    JOBS_NRM[jid] = {"status": "processando", "criado_em": time.time(),
                     "docs": docs, "paths": paths, "json_path": json_path}
    threading.Thread(target=_roda_normas, args=(jid,), daemon=True).start()
    return {"job": jid}


@app.route("/normas/job/<jid>/status")
def normas_status(jid):
    j = JOBS_NRM.get(jid)
    if not j:
        return {"status": "erro", "erro": "job não encontrado (o serviço pode ter reiniciado; envie de novo)"}, 404
    return {"status": j["status"], "erro": j.get("erro")}


@app.route("/normas/resultado/<jid>")
def normas_resultado(jid):
    j = JOBS_NRM.get(jid)
    res = None
    if j and j.get("status") == "pronto" and os.path.exists(j["json_path"]):
        with open(j["json_path"], encoding="utf-8") as f:
            res = json.load(f)
    if res is None:
        abort(404)
    return _render_normas(res)


@app.route("/normas/resultado/<jid>/json")
def normas_json(jid):
    j = JOBS_NRM.get(jid)
    if not j or j.get("status") != "pronto" or not os.path.exists(j["json_path"]):
        abort(404)
    return send_file(j["json_path"], as_attachment=True,
                     download_name="confronto_normas_auditoria.json")



if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
