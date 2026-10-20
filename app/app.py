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

import auditoria, relatorio, relatorio_html

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
# Hash falso para equalizar tempo de resposta quando o usuario nao existe.
_HASH_FALSO = "scrypt:32768:8:1$Xq0Yy7p9mJ3kQ2wE$f8d0d3a1c5e6b7a9c0d2e4f6a8b0c1d3e5f7a9b1c3d5e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c3d5e7f9"
LOGIN = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Acesso | Demo AP Projetos</title>
<style>*{box-sizing:border-box}body{margin:0;font-family:Calibri,Segoe UI,Arial,sans-serif;background:#f2f4f8;color:#243148}.top{padding:30px 24px;background:linear-gradient(135deg,#2b3550,#131a27)}.top img{width:255px;max-width:100%;height:auto}.brand{color:#b8c8df;font-size:15px;margin:16px 0 0}.wrap{padding:30px 20px;max-width:460px;margin:auto}.card{background:#fff;border-radius:12px;padding:28px;box-shadow:0 4px 20px #17213112}h1{font-size:26px;margin:0 0 12px}p{font-size:15px;line-height:1.5;color:#586579}label{display:block;font-size:15px;font-weight:600;margin:22px 0 8px}input{width:100%;padding:14px;border:1px solid #a8b6ca;border-radius:6px;font-size:16px}button{width:100%;margin:26px 0 10px;padding:15px;background:#1f6fb2;color:white;border:0;border-radius:6px;font-size:16px;font-weight:600}.note{font-size:13px;color:#6d7788;text-align:center;line-height:1.6}.error{background:#fff0ef;color:#a22b28;padding:12px;border-radius:5px}.show{font-size:14px;display:flex;gap:8px;align-items:center;font-weight:400}.show input{width:18px;height:18px}input:focus,button:focus{outline:3px solid #9ac8ed;outline-offset:2px}</style></head><body>
<header class="top"><img src="/static/logo_ap.png" alt="AP Consultoria e Projetos"><p class="brand">Verificação de documentos de engenharia</p></header>
<main class="wrap"><section class="card"><h1>Entrar na demonstração</h1><p>Use o usuário <b>ap</b> e a senha que você definiu no link seguro.</p>
{% if error %}<p class="error" role="alert">{{error}}</p>{% endif %}
<form method="post" action="/login"><input type="hidden" name="csrf" value="{{csrf}}"><label for="username">Usuário</label><input id="username" name="username" value="ap" autocomplete="username" required>
<label for="password">Senha</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<label class="show"><input type="checkbox" onclick="document.getElementById('password').type=this.checked?'text':'password'">Mostrar senha</label>
<button type="submit">Entrar na plataforma</button></form></section>
<p class="note">MVP • Módulo 1 • Parecer Técnico<br>Acesso restrito. Endereço temporário para testes.<br>Com IA ligada, trechos são enviados à NVIDIA.</p></main></body></html>"""

@app.before_request
def _auth_demo():
    public = request.endpoint == "login" or request.path == "/static/logo_ap.png"
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
    return render_template_string(LOGIN, error=error, csrf=session["csrf"])

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


@app.route("/")
def home():
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
    modo_ia = "ligada" if os.environ.get("NVIDIA_API_KEY") else "desligada (heurística simulada nos itens de classe B)"
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AP - Verificação de Documentos de Engenharia</title><style>{CSS}</style></head>
<body>
<header class="topo">
  <img src="/static/logo_ap.png" alt="AP Consultoria e Projetos">
  <div><div class="t">Verificação de Documentos de Engenharia</div>
  <div class="s">Módulo 1 &middot; Check-list FRM-SEMEC-001 - Parecer Técnico &middot; MVP</div></div>
</header>
<div class="wrap">
<div class="card">
 <h2>Verificar um documento</h2>
 <form method="post" action="/verificar" enctype="multipart/form-data">
  <div class="drop">
   <input type="file" name="arquivo" accept=".pdf,.docx,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/msword,application/vnd.ms-excel" required>
   <p style="color:#667;font-size:12.5px;margin:12px 0">PDF, DOCX ou XLSX. O documento é processado localmente.</p>
   <button class="btn" type="submit">Verificar documento</button>
  </div>
 </form>
 <p class="modo">IA nesta instância: <b>{modo_ia}</b> &middot; cada item do relatório mostra quem decidiu: regra determinística, IA (NVIDIA NIM), heurística simulada ou humano.</p>
</div>
<div class="card" style="margin-top:18px">
 <h2>Verificar vários documentos (até 5)</h2>
 <div class="drop">
  <input type="file" id="fila-input" multiple accept=".pdf,.docx,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/msword,application/vnd.ms-excel">
  <div id="fila-selecao" style="font-size:13px;color:#445;margin-top:6px">Nenhum arquivo selecionado.</div>
  <p style="color:#667;font-size:12.5px;margin:12px 0">Selecione até 5 arquivos (PDF, DOCX ou XLSX). Eles são enviados <b>um por vez</b>, nesta ordem, e cada relatório é liberado assim que fica pronto. Cada documento leva cerca de 1 a 2 minutos.</p>
  <button class="btn" id="fila-btn" type="button">Verificar em fila</button>
 </div>
 <div id="fila-progresso" style="font-size:13.5px;margin-top:10px"></div>
 <ul id="fila-lista" style="list-style:none;padding:0;margin:10px 0 0;font-size:13.5px"></ul>
</div>
<script>
(function(){{
 var inp=document.getElementById("fila-input"),btn=document.getElementById("fila-btn"),
     prog=document.getElementById("fila-progresso"),lista=document.getElementById("fila-lista"),
     sel=document.getElementById("fila-selecao");
 function mostraSel(){{
  var fs=inp.files||[];
  if(!fs.length){{sel.textContent="Nenhum arquivo selecionado.";return;}}
  var nomes=[];
  for(var k=0;k<fs.length;k++){{nomes.push((k+1)+". "+fs[k].name+" ("+(fs[k].size/1048576).toFixed(1)+" MB)");}}
  sel.innerHTML="<b>"+fs.length+" arquivo(s) selecionado(s)"+(fs.length>5?" - só os 5 primeiros entram na fila":"")+":</b><br>"+nomes.join("<br>");
 }}
 inp.addEventListener("change",mostraSel);mostraSel();
 btn.addEventListener("click",function(){{
  var arqs=Array.prototype.slice.call(inp.files||[]).slice(0,5);
  if(!arqs.length){{prog.textContent="Selecione de 1 a 5 arquivos primeiro.";return;}}
  if((inp.files||[]).length>5){{prog.textContent="Mais de 5 selecionados: só os 5 primeiros entram na fila.";}}
  btn.disabled=true;lista.innerHTML="";
  var itens=arqs.map(function(a,i){{
   var li=document.createElement("li");li.style.cssText="padding:7px 0;border-bottom:1px solid #e6eaf1";
   li.textContent=(i+1)+". "+a.name+" - aguardando";lista.appendChild(li);return li;}});
  var i=0;
  function passo(){{
   if(i>=arqs.length){{prog.innerHTML="<b>Fila concluída.</b> Os relatórios ficam no histórico abaixo enquanto o serviço estiver acordado.";btn.disabled=false;return;}}
   var a=arqs[i],li=itens[i],n=i+1,ini=Date.now(),tent=0;
   function rot(){{
    var s=Math.floor((Date.now()-ini)/1000),m=Math.floor(s/60),ss=("0"+(s%60)).slice(-2);
    prog.textContent="Processando "+n+" de "+arqs.length+": "+a.name+" (há "+m+":"+ss+(n===1?"; o primeiro pode demorar mais se o serviço estiver em repouso":"")+")...";
    li.innerHTML="<b>"+n+". "+a.name+"</b> - processando há "+m+":"+ss+"..."+(tent?" (nova tentativa)":"");
   }}
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
    registro, _ = auditoria.verificar_reprodutibilidade(caminho, origem="upload via interface web")
    registro["documento"]["nome"] = arq.filename
    with open(os.path.join(SAIDA, f"{slug}.json"), "w") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    relatorio.gerar_relatorio(registro, os.path.join(SAIDA, f"{slug}.pdf"))
    if request.args.get("modo") == "json":
        return {"slug": slug, "url": f"/relatorio/{slug}", "resumo": auditoria.resumo_status(registro["resultados"])}
    session["ultimo_relatorio"] = slug
    return redirect(f"/relatorio/{slug}")


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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
