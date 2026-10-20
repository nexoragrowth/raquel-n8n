# -*- coding: utf-8 -*-
"""
lista_semilla_contactos.py — 2026-10-14 · arma la LISTA SEMILLA de contactos que no son pacientes (Día 1 de la segmentación,
docs/plan-contactos-conversion-dentalink-2026-10-13.md §2.6): la Dra., el staff, proveedores, colegas y centros de imágenes, para que el bot
deje de contestarles. SOLO LECTURA (sesión read-only contra el Supabase v3). No escribe nada en la base ni en n8n.

Cómo decide: NO decide. Junta, por teléfono que le escribió a la clínica y que NO tiene ficha (no le llegó ningún recordatorio):
nombre de WhatsApp, alias del panel, cuántos mensajes, desde/hasta, si la clínica escribió primero, cuántas veces le contestó el bot,
avisos al grupo y los últimos 3 mensajes recortados. Unas palabras clave SOLO ORDENAN la lista (las más sospechosas arriba);
el tipo lo elige una persona en el HTML.

Privacidad (plan §4.6): los mensajes NO se imprimen en la consola ni se mandan a ningún modelo; van solo al HTML local en data/contactos/
(data/ está en .gitignore). La consola muestra únicamente totales.

USO:  python scripts/lista_semilla_contactos.py
      → data/contactos/lista_semilla_<fecha>.html  (abrirlo en el navegador, elegir el tipo de cada uno y "Guardar resultado")
"""
import html, json, re, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
ART = timezone(timedelta(hours=-3))

LUCAS, IRINA, DRA = "5491161461034", "5493885786946", "5493513976787"
PRESELECCION = {DRA: "interno", IRINA: "interno", LUCAS: "prueba"}
RX_SINTETICO = re.compile(r"^549(0000000\d{3}|999\d{7})$")

TIPOS = [("", "Paciente / prospecto (el bot lo atiende)"), ("interno", "Interno (Dra., staff)"), ("proveedor", "Proveedor / comercio"),
         ("colega", "Colega / centro de imágenes"), ("no_paciente", "No paciente (conocido, spam, empresa)"), ("prueba", "Prueba"),
         ("dudoso", "No sé (lo ve Irina)")]

# Pistas: solo para ORDENAR. (palabra, etiqueta). En el nombre pesan 3, en el texto 1.
PISTAS = [
    (r"laborator|\blab\b", "laboratorio"), (r"dep[oó]sito|insumo|distribuid|droguer", "insumos"), (r"\bs\.?\s?r\.?\s?l\b|\bs\.?\s?a\.?\b(?!\w)", "empresa"),
    (r"factura|remito|cotizaci|mercader|lista de precios|cat[aá]logo|\bsu pedido\b|\bel pedido\b|despacho|cadete", "pedido/factura"),
    (r"radiolog|im[aá]genes|tomograf|resonancia|ecograf", "imágenes"), (r"\bdr\.?\b|\bdra\.?\b|\bod\.?\b|odont[oó]log", "dr./od."),
    (r"colega|tu paciente|su paciente|te derivo|le derivo", "colega"),
    (r"gracias por comunicarte|gracias por contactarte|mensaje autom[aá]tico|respuesta autom[aá]tica|en breve te", "autorespuesta"),
    (r"\bbanco\b|seguros?\b|\bpromo|https?://", "empresa/publicidad"),
]
PISTAS = [(re.compile(p, re.I), e) for p, e in PISTAS]


def conectar():
    env = {}
    for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    c = psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"],
                         user=env["SUPABASE_DB_USER"], password=env["SUPABASE_DB_PASSWORD"], sslmode="require")
    c.set_session(readonly=True)
    return c


def norm(tel):
    t = (tel or "").split("@")[0]
    return t if re.fullmatch(r"\d{8,15}", t) else None


def juntar(cur):
    C = defaultdict(lambda: {"msgs": [], "n_in": 0, "primero_in": None, "ultimo_in": None, "primero_clinica": None, "push": "", "bot": 0, "avisos": 0,
                             "nombre": "", "alias": ""})
    descartados = defaultdict(int)

    def entrante(tel, ts, texto, push=""):
        c = C[tel]
        c["n_in"] += 1
        c["primero_in"] = min(filter(None, [c["primero_in"], ts]))
        c["ultimo_in"] = max(filter(None, [c["ultimo_in"], ts]))
        if texto:
            c["msgs"].append((ts, texto))
        if push:
            c["push"] = push

    cur.execute("SELECT telefono, texto, from_me, push_name, created_at FROM mensajes_entrantes_live ORDER BY created_at")
    vistos = set()
    for tel_raw, texto, from_me, push, ts in cur.fetchall():
        if (tel_raw or "").endswith("@g.us"):
            descartados["grupo"] += 1; continue
        tel = norm(tel_raw)
        if not tel or len(tel) > 13:
            descartados["@lid / formato raro"] += 1; continue
        if from_me:
            c = C[tel]; c["primero_clinica"] = min(filter(None, [c["primero_clinica"], ts]))
        else:
            entrante(tel, ts, texto, push); vistos.add((tel, (texto or "")[:60], ts.replace(microsecond=0)))
    # conversaciones (desde el 18/07): los mensajes del paciente anteriores a la bandeja y lo que el bot le contestó
    cur.execute("SELECT telefono, rol, mensaje, \"timestamp\" FROM conversaciones WHERE rol IN ('user','assistant') ORDER BY \"timestamp\"")
    for tel_raw, rol, msg, ts in cur.fetchall():
        tel = norm(tel_raw)
        if not tel or len(tel) > 13:
            continue
        if rol == "assistant":
            C[tel]["bot"] += 1
        elif ts < datetime(2026, 9, 6, tzinfo=timezone.utc):   # lo posterior ya está en la bandeja (evita contar dos veces)
            entrante(tel, ts, msg)
    cur.execute("SELECT telefono, count(*) FROM escalaciones_log GROUP BY 1")
    for tel_raw, n in cur.fetchall():
        if norm(tel_raw):
            C[norm(tel_raw)]["avisos"] += n
    cur.execute("SELECT telefono, coalesce(nombre,''), coalesce(alias_panel,'') FROM pacientes")
    for tel_raw, nombre, alias in cur.fetchall():
        t = norm(tel_raw)
        if t in C:
            C[t]["nombre"], C[t]["alias"] = nombre if nombre != "Paciente WhatsApp" else "", alias
    cur.execute("SELECT DISTINCT telefono FROM recordatorios_enviados")
    con_ficha = {norm(t) for (t,) in cur.fetchall()}
    return C, con_ficha, descartados


def pistas(c):
    hits, score = [], 0
    nombre = " ".join([c["push"], c["alias"], c["nombre"]])
    textos = " ".join(t for _, t in c["msgs"][-30:])
    for rx, et in PISTAS:
        if rx.search(nombre):
            hits.append(et + " (nombre)"); score += 3
        elif rx.search(textos):
            hits.append(et); score += 1
    return score, hits


def fecha(ts):
    return ts.astimezone(ART).strftime("%d/%m") if ts else "—"


def fila(tel, c, score, hits):
    e = html.escape
    pre = PRESELECCION.get(tel, "")
    nombre = c["alias"] or c["push"] or c["nombre"] or "(sin nombre)"
    extra = [x for x in (c["push"], c["nombre"]) if x and x != nombre]
    inicio = "la clínica escribió primero" if c["primero_clinica"] and c["primero_in"] and c["primero_clinica"] < c["primero_in"] else ""
    datos = [f"{c['n_in']} mensaje{'s' if c['n_in'] != 1 else ''}", f"{fecha(c['primero_in'])} → {fecha(c['ultimo_in'])}"]
    if inicio: datos.append(inicio)
    if c["bot"]: datos.append(f"el bot le contestó {c['bot']} {'vez' if c['bot'] == 1 else 'veces'}")
    if c["avisos"]: datos.append(f"{c['avisos']} aviso{'s' if c['avisos'] != 1 else ''} al grupo")
    msgs = "".join(f"<li><time>{fecha(ts)}</time> {e(re.sub(r'\s+', ' ', t)[:140])}{'…' if len(t) > 140 else ''}</li>" for ts, t in c["msgs"][-3:])
    opts = "".join(f'<option value="{v}"{" selected" if v == pre else ""}>{e(l)}</option>' for v, l in TIPOS)
    chips = "".join(f'<span class="chip">{e(h)}</span>' for h in hits)
    tel_fmt = f"+{tel[:2]} {tel[2]} {tel[3:6]} {tel[6:9]}-{tel[9:]}" if len(tel) == 13 else tel
    grupo = "pista" if score or pre else "resto"
    return (f'<article class="c" data-tel="{tel}" data-grupo="{grupo}"><header><div class="who"><b>{e(nombre)}</b>'
            f'{"".join(f"<span class=alt>{e(x)}</span>" for x in extra)}<span class="tel">{tel_fmt}</span></div>'
            f'<select aria-label="Tipo de {e(nombre)}">{opts}</select></header>'
            f'<p class="datos">{" · ".join(datos)}</p>{f"<p class=chips>{chips}</p>" if chips else ""}'
            f'{f"<ul class=msgs>{msgs}</ul>" if msgs else ""}</article>')


CSS = """
:root{--bg:#f6f5f2;--card:#fff;--fg:#1f2421;--muted:#5d655f;--line:#dedbd3;--accent:#2f6f5e;--chip:#e8f0ec;--chipfg:#24564a;--warn:#8a5a12;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#141716;--card:#1c201e;--fg:#e7ebe8;--muted:#9aa49e;--line:#2d3330;--accent:#7cc4ad;--chip:#22332d;--chipfg:#a9dccb;--warn:#e0b467;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding-inline:16px}
main{max-width:820px;margin:0 auto;padding-block:28px 120px;display:grid;gap:14px}
h1{font-size:1.45rem;margin:0;text-wrap:balance}h2{font-size:1.05rem;margin:18px 0 0;letter-spacing:.02em}
.lead{color:var(--muted);margin:0;max-width:65ch}.lead b{color:var(--fg)}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;gap:6px;min-width:0}
.c.marcado{border-color:var(--accent);box-shadow:inset 3px 0 0 var(--accent)}
.c header{display:flex;gap:10px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}
.who{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline;min-width:0}.alt{color:var(--muted);font-size:.9em}
.tel{font-variant-numeric:tabular-nums;color:var(--muted);font-size:.9em}
select{font:inherit;font-size:.92rem;padding:5px 8px;border-radius:7px;border:1px solid var(--line);background:var(--bg);color:var(--fg);max-width:100%}
.datos{margin:0;color:var(--muted);font-size:.88rem}.chips{margin:0;display:flex;flex-wrap:wrap;gap:6px}
.chip{background:var(--chip);color:var(--chipfg);border-radius:99px;padding:1px 9px;font-size:.8rem}
.msgs{margin:0;padding:0;list-style:none;display:grid;gap:3px;font-size:.9rem;overflow-wrap:anywhere}
.msgs time{color:var(--muted);font-variant-numeric:tabular-nums;margin-right:6px;font-size:.85em}
details>summary{cursor:pointer;color:var(--accent);font-weight:600;padding:8px 0}details[open]>summary{margin-bottom:10px}
.lista{display:grid;gap:10px}
.barra{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px calc(10px + env(safe-area-inset-bottom,0px))}
.barra div{max-width:820px;margin:0 auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.barra span{flex:1;min-width:160px;color:var(--muted);font-variant-numeric:tabular-nums}
button{font:inherit;font-weight:600;border:0;border-radius:8px;padding:8px 14px;background:var(--accent);color:var(--bg);cursor:pointer}
button.sec{background:transparent;color:var(--accent);border:1px solid var(--accent)}
textarea{width:100%;min-height:90px;font:12px/1.4 ui-monospace,Consolas,monospace;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:8px}
.aviso{color:var(--warn);font-size:.9rem;margin:0}
"""

JS = """
const sel=[...document.querySelectorAll('article.c select')];
function resultado(){const t={};for(const s of sel){const c=s.closest('article');c.classList.toggle('marcado',!!s.value);if(s.value)t[c.dataset.tel]=s.value}return t}
function pintar(){const t=resultado();const n=Object.keys(t).length;const por={};for(const v of Object.values(t))por[v]=(por[v]||0)+1;
document.getElementById('cuenta').textContent=n+' marcados'+(n?' · '+Object.entries(por).map(([k,v])=>v+' '+k).join(' · '):'');
document.getElementById('out').value=JSON.stringify({generado:document.body.dataset.generado,tipos:t},null,1)}
sel.forEach(s=>s.addEventListener('change',pintar));pintar();
document.getElementById('guardar').onclick=()=>{const b=new Blob([document.getElementById('out').value],{type:'application/json'});const a=document.createElement('a');
a.href=URL.createObjectURL(b);a.download='lista_semilla_confirmada.json';a.click()};
document.getElementById('copiar').onclick=async()=>{const o=document.getElementById('out');try{await navigator.clipboard.writeText(o.value);document.getElementById('copiar').textContent='Copiado'}catch(e){o.closest('details').open=true;o.focus();o.select()}};
"""


def main():
    con = conectar()
    with con.cursor() as cur:
        C, con_ficha, descartados = juntar(cur)
    con.close()
    hoy = datetime.now(ART).strftime("%Y-%m-%d")
    candidatos, con_ficha_n, sinteticos = [], 0, 0
    for tel, c in C.items():
        if RX_SINTETICO.match(tel):
            sinteticos += 1; continue
        if tel not in PRESELECCION and (c["n_in"] == 0 or tel in con_ficha):
            con_ficha_n += tel in con_ficha and c["n_in"] > 0; continue
        score, hits = pistas(c)
        candidatos.append((-(score + (10 if tel in PRESELECCION else 0)), -(c["ultimo_in"] or datetime.min.replace(tzinfo=timezone.utc)).timestamp(), tel, c, score, hits))
    candidatos.sort(key=lambda x: (x[0], x[1]))
    arriba = [fila(t, c, s, h) for _, _, t, c, s, h in candidatos if s or t in PRESELECCION]
    resto = [fila(t, c, s, h) for _, _, t, c, s, h in candidatos if not (s or t in PRESELECCION)]
    cuerpo = f"""<title>Lista semilla de contactos</title><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>{CSS}</style>
<body data-generado="{hoy}"><main>
<h1>Contactos a los que el bot no tiene que contestar</h1>
<p class="lead">Números que le escribieron a la clínica <b>sin ficha en Dentalink</b> (no les llegó ningún recordatorio), del 18/07 al {datetime.now(ART).strftime('%d/%m')}.
Elegí el tipo solo de los que <b>no</b> son pacientes: la Dra. y el staff, proveedores, colegas y centros de imágenes, conocidos o empresas.
Los demás dejalos en “Paciente / prospecto”. Las etiquetas verdes son pistas por palabras para ordenar la lista: no deciden nada.</p>
<p class="aviso">Archivo local con mensajes de pacientes: no lo compartas ni lo subas a ningún lado.</p>
<h2>Con pistas ({len(arriba)})</h2><div class="lista">{''.join(arriba)}</div>
<details><summary>Sin pistas: probablemente pacientes o prospectos ({len(resto)}). Revisalos rápido por el nombre.</summary><div class="lista">{''.join(resto)}</div></details>
<details><summary>Resultado (JSON)</summary><textarea id="out" readonly></textarea></details>
</main><div class="barra"><div><span id="cuenta"></span><button class="sec" id="copiar">Copiar</button><button id="guardar">Guardar resultado</button></div></div>
<script>{JS}</script></body>"""
    out = ROOT / "data" / "contactos" / f"lista_semilla_{hoy}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("<!doctype html>" + cuerpo, encoding="utf-8")
    print(f"Contactos que escribieron: {sum(1 for c in C.values() if c['n_in'])} (descartados: {dict(descartados)}; sintéticos {sinteticos})")
    print(f"Con ficha (pacientes, quedan fuera): {con_ficha_n}")
    print(f"En la lista: {len(candidatos)} → con pistas o preseleccionados {len(arriba)}, sin pistas {len(resto)}")
    print(f"Preseleccionados: {sum(1 for t in PRESELECCION if any(x[2] == t for x in candidatos))} (Dra. e Irina como interno, Lucas como prueba)")
    print(f"Archivo: {out}")


if __name__ == "__main__":
    main()
