# -*- coding: utf-8 -*-
"""
analisis_retrospectivo_urgencias.py — "Modo sombra" retrospectivo del triaje de urgencias.

Toma las escalaciones REALES de `escalaciones_log` (temas "Urgencias y dolor" y
"Aparatología", misma regex que lib/escalaciones.ts del panel), las enriquece con los
últimos mensajes crudos del paciente (`conversaciones`) previos a la escalación, y las
clasifica con un LLM en las categorías del triaje diseñado el 2026-09-02:

  red_flag         -> siempre escala (trauma, sangrado abundante, pieza tragada,
                      hinchazón/dificultad respirar-tragar, fiebre, dolor intenso)
  alambre_pincha   -> video (Opción 1 cera / Opción 2 reinsertar con pinza)
  bracket_suelto   -> video (pendiente de Raquel)
  alambre_girado   -> video (pendiente de Raquel)
  ligadura_pincha  -> video (pendiente de Raquel)
  otra_urgencia    -> urgencia real que no cae en los 4 tipos -> escala
  no_urgencia      -> la escalación no era una urgencia de aparatología

SOLO LECTURA sobre la base. No toca n8n ni producción. Sirve para saber, con datos
reales, qué fracción de urgencias se hubiera resuelto con video y con qué tipo
conviene pilotear.

Uso: python scripts/analisis_retrospectivo_urgencias.py [--dias 60] [--limit 200] [--modelo gpt-5-mini]
Salida: docs/analisis-retrospectivo-urgencias-<fecha>.md (teléfonos enmascarados)
"""
import json, re, sys, argparse, urllib.request, urllib.error, datetime as dt
from collections import Counter
from pathlib import Path
import psycopg2

sys.stdout.reconfigure(encoding="utf-8")

def load_env(path, keys):
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if k in keys:
            out[k] = v
    return out

db = load_env(".env", {"SUPABASE_DB_HOST", "SUPABASE_DB_PORT", "SUPABASE_DB_NAME", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD"})
oa = load_env("../nexora-whatsapp-agent/.env.local", {"OPENAI_API_KEY"})
OPENAI_KEY = oa.get("OPENAI_API_KEY")
if not OPENAI_KEY or len(db) < 5:
    print("!! faltan credenciales (SUPABASE_DB_* en .env o OPENAI_API_KEY en panel/.env.local)")
    sys.exit(1)

ap = argparse.ArgumentParser()
ap.add_argument("--dias", type=int, default=60)
ap.add_argument("--limit", type=int, default=200)
ap.add_argument("--modelo", default="gpt-5-mini")
args = ap.parse_args()

# Mismas regex que lib/escalaciones.ts (panel) — si se edita un lado, editar el otro.
RE_RUIDO = re.compile(r"el bot detect[oó] que ya est[aá]s atendiendo", re.I)
RE_OPERATIVO = re.compile(r"comprobante\s+(de\s+pago|por|de\s+\$)|envi[oó]\s+comprobante|verificar que el pago", re.I)
RE_URGENCIA = re.compile(r"\bdolor|molesti|urgen|sangr|hinch|fiebre|inflam", re.I)
RE_APARATO = re.compile(r"bracket|topecito|alambre|\btubo\b|aparatolog|se le sali", re.I)

conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"],
                        user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require", connect_timeout=20)
cur = conn.cursor()

cur.execute("""
    SELECT id, telefono, motivo, origen, created_at
    FROM escalaciones_log
    WHERE created_at > NOW() - (%s || ' days')::interval
    ORDER BY created_at DESC
""", (str(args.dias),))
rows = cur.fetchall()
print(f"escalaciones últimos {args.dias} días: {len(rows)}")

senal, ruido, operativo = [], 0, 0
for r in rows:
    m = r[2] or ""
    if RE_RUIDO.search(m):
        ruido += 1
    elif RE_OPERATIVO.search(m):
        operativo += 1
    else:
        senal.append(r)
print(f"  ruido (ya atendiendo): {ruido} | operativo (comprobantes): {operativo} | señal: {len(senal)}")

candidatas = [r for r in senal if RE_URGENCIA.search(r[2] or "") or RE_APARATO.search(r[2] or "")]
print(f"  señal con tema urgencia/aparatología (candidatas al triaje): {len(candidatas)}")
candidatas = candidatas[: args.limit]

def mensajes_previos(telefono, created_at, minutos=20, n=4):
    """Últimos n mensajes del paciente (no del bot) en la ventana previa a la escalación."""
    cur.execute("""
        SELECT rol, mensaje, "timestamp" FROM conversaciones
        WHERE telefono = %s AND "timestamp" BETWEEN %s - interval '%s minutes' AND %s + interval '1 minute'
        ORDER BY "timestamp" DESC LIMIT 12
    """, (telefono, created_at, minutos, created_at))
    out = []
    for rol, msg, ts in cur.fetchall():
        if (rol or "").lower() in ("user", "human", "paciente", "usuario"):
            out.append(msg.strip())
        if len(out) >= n:
            break
    return list(reversed(out))

SYSTEM = """Sos un clasificador de urgencias de ORTODONCIA para un triaje automático de una clínica (Dra. Raquel, Jujuy).
Recibís el resumen que hizo el bot al escalar + los últimos mensajes crudos del paciente. Clasificá en UNA categoría:

- "red_flag": hay señal que SIEMPRE debe ir a la doctora: golpe/caída/accidente/trauma, sangrado abundante o que no para, pieza o parte del aparato tragada, hinchazón de cara/cuello, dificultad para respirar o tragar, fiebre, dolor intenso que no cede. Si hay red flag, gana sobre cualquier otra categoría.
- "alambre_pincha": el alambre principal (arco) se salió del tubo/bracket o sobresale y pincha mejilla/encía, sin red flags.
- "bracket_suelto": un bracket se despegó del diente (se mueve, "se salió el cuadradito", "se me soltó un bracket"), sin red flags.
- "alambre_girado": el arco se corrió hacia un costado (sobra de un lado, quedó corto del otro), sin red flags.
- "ligadura_pincha": una ligadura (alambrecito finito o gomita de un solo bracket) pincha, sin red flags.
- "otra_urgencia": urgencia/molestia real de ortodoncia que NO cae en los 4 tipos anteriores (ej. dolor por ajuste, aparato removible roto, contención rota, llaga sin alambre involucrado, "me duele" sin más detalle).
- "no_urgencia": la escalación no era una urgencia clínica (turnos, pagos, dudas generales, etc.).

Sé conservador: si la información no alcanza para elegir uno de los 4 tipos con confianza, usá "otra_urgencia".
Respondé SOLO JSON: {"tipo": "...", "red_flags": ["..."], "confianza": "alta|media|baja", "razon": "una oración"}"""

def clasificar(motivo, msgs):
    user = f"RESUMEN DEL BOT AL ESCALAR:\n{motivo}\n\nMENSAJES CRUDOS DEL PACIENTE (previos, más viejo primero):\n" + \
           ("\n".join(f"- {m}" for m in msgs) if msgs else "(no se encontraron mensajes crudos en la ventana)")
    body = {"model": args.modelo, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        txt = json.loads(r.read().decode())["choices"][0]["message"]["content"]
    txt = re.sub(r"^```(json)?|```$", "", txt.strip(), flags=re.M).strip()
    return json.loads(txt)

def mask(tel):
    t = tel or ""
    return ("…" + t[-4:]) if len(t) >= 4 else "…"

resultados = []
for i, (eid, tel, motivo, origen, created_at) in enumerate(candidatas, 1):
    msgs = mensajes_previos(tel, created_at)
    try:
        c = clasificar(motivo or "", msgs)
    except Exception as e:
        c = {"tipo": "error", "red_flags": [], "confianza": "baja", "razon": f"error LLM: {e}"}
    resultados.append({"id": eid, "tel": mask(tel), "fecha": created_at.strftime("%Y-%m-%d %H:%M"), "motivo": (motivo or "").strip(),
                       "msgs": msgs, **c})
    print(f"  [{i}/{len(candidatas)}] {created_at:%d/%m} {c.get('tipo'):16s} ({c.get('confianza')}) — {(motivo or '')[:70]}")

cur.close(); conn.close()

# --- Resumen ---
dist = Counter(r["tipo"] for r in resultados)
video_tipos = {"alambre_pincha", "bracket_suelto", "alambre_girado", "ligadura_pincha"}
con_video = sum(dist[t] for t in video_tipos)
total = len(resultados)
alta = Counter(r["tipo"] for r in resultados if r["confianza"] == "alta")

hoy = dt.date.today().isoformat()
out = Path(f"docs/analisis-retrospectivo-urgencias-{hoy}.md")
L = []
L.append(f"# Análisis retrospectivo de urgencias — modo sombra ({hoy})\n")
L.append(f"Fuente: `escalaciones_log` últimos {args.dias} días ({len(rows)} escalaciones: {ruido} ruido, {operativo} operativo, {len(senal)} señal).")
L.append(f"Candidatas al triaje (señal con tema urgencia/aparatología): **{total}**. Clasificador: `{args.modelo}`, solo lectura.\n")
L.append("## Distribución\n")
L.append("| Tipo | Casos | % | De los cuales confianza alta |")
L.append("|---|---:|---:|---:|")
for t, n in dist.most_common():
    L.append(f"| {t} | {n} | {n*100//max(total,1)}% | {alta.get(t,0)} |")
L.append("")
L.append(f"**Se hubieran resuelto con video (4 tipos): {con_video}/{total} ({con_video*100//max(total,1)}%)** — "
         f"con confianza alta: {sum(alta.get(t,0) for t in video_tipos)}.")
L.append(f"**Red flags (siempre escalan): {dist.get('red_flag',0)}.** Otras urgencias sin video: {dist.get('otra_urgencia',0)}. No urgencia: {dist.get('no_urgencia',0)}.\n")
L.append("## Casos\n")
for r in sorted(resultados, key=lambda x: (x["tipo"], x["fecha"])):
    L.append(f"### #{r['id']} · {r['fecha']} · tel {r['tel']} · **{r['tipo']}** ({r['confianza']})")
    L.append(f"- Motivo del bot: {r['motivo']}")
    if r["msgs"]:
        L.append("- Paciente dijo:")
        for m in r["msgs"]:
            L.append(f"  - «{m[:300]}»")
    if r.get("red_flags"):
        L.append(f"- Red flags: {', '.join(r['red_flags'])}")
    L.append(f"- Razón: {r.get('razon','')}\n")
out.write_text("\n".join(L), encoding="utf-8")

print("\n=== RESUMEN ===")
for t, n in dist.most_common():
    print(f"  {t:16s} {n:3d}  ({n*100//max(total,1)}%)  alta={alta.get(t,0)}")
print(f"\nCon video: {con_video}/{total} | red_flag: {dist.get('red_flag',0)} | otra_urgencia: {dist.get('otra_urgencia',0)} | no_urgencia: {dist.get('no_urgencia',0)}")
print(f"Reporte: {out}")
