# -*- coding: utf-8 -*-
"""
revertir_confirmaciones_sombra.py — 2026-10-08 · deshace el INCIDENTE del 06/10.

QUÉ PASÓ: el workflow "v7 Tool - confirmar_turno" no declaraba `modo` en su trigger; n8n descartaba el campo y la herramienta escribía
aunque el cerebro corriera en sombra. Durante la retrospectiva del v7 (06/10, 22:39–23:22 UTC) puso en 18 ("Confirmado por whatsapp")
11 citas de pacientes reales en Dentalink y marcó `confirmado_at` en el recordatorio de la cita 9064. Ningún paciente recibió mensajes
(la sombra no envía), pero:
  - en la agenda esas citas figuran confirmadas por WhatsApp sin que el paciente haya confirmado;
  - 3 eran del mismo 06/10 y ya estaban "Atendido" (2): perdieron ese estado;
  - el workflow de Recordatorios SALTEA las citas en 18 → las 8 futuras se quedarían sin el recordatorio de 72 h / 24 h.
El arreglo del workflow (solo escribe con modo 'vivo' explícito) está en scripts/v7_workflows_confirmar_clinica.py.

ESTADO AL 08/10 (simulación): las 11 citas YA NO estaban en 18. Según `fecha_actualizacion` de Dentalink, el 07/10 entre 14:51 y 15:13
alguien las corrigió a mano: las 3 del 06/10 volvieron a "Atendido" y las 8 futuras quedaron en 7 "No confirmado" (no en 15 como
antes: se respeta, fue una decisión de una persona). El script las saltea; lo único que quedaba por revertir era el recordatorio de la 9064.

QUÉ HACE: lee cada cita en Dentalink y la devuelve a su estado anterior SOLO si sigue exactamente como la dejó el incidente:
en 18, misma fecha y hora, y sin un recordatorio confirmado de verdad después (eso querría decir que el paciente confirmó por su cuenta).
Si alguien la tocó después, no la toca y lo informa. En Supabase vuelve a NULL el `confirmado_at` que el incidente puso (solo filas de
estas citas marcadas dentro de la ventana del incidente). Al final relee todo y deja un reporte en workflows/history/ (fuera de git: tiene
nombres de pacientes).

POR QUÉ ASÍ: la clave de Dentalink vive cifrada en las credenciales de n8n (no en el .env). Como crear_cita_prueba_examen.py, arma un
workflow TEMPORAL que usa esa credencial, lo llama una vez y lo borra. Las citas y los estados a escribir van FIJOS dentro del workflow
temporal (no los recibe del pedido): ese webhook no puede escribir otra cosa.

USO:  python scripts/revertir_confirmaciones_sombra.py           # LEE y muestra qué haría (no escribe en Dentalink ni en Supabase)
      python scripts/revertir_confirmaciones_sombra.py --apply   # revierte, relee y verifica
No toca el v6 ni los workflows v7. Se puede correr más de una vez: lo ya revertido queda fuera de 18 y se saltea.
"""
import argparse, json, secrets, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require
from v7_lib import Grafo, DENTALINK

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SETTINGS_MIN = {"executionOrder": "v1"}

# Ventana del incidente (UTC): primera y última ejecución de confirmar_turno con PUT durante la retrospectiva, con margen.
VENTANA = ("2026-10-06T22:35:00+00:00", "2026-10-06T23:25:00+00:00")
ESTADOS = {1: "Anulado", 2: "Atendido", 7: "No confirmado", 15: "Notificado por WhatsApp", 18: "Confirmado por whatsapp"}

# (cita, estado ANTES del incidente, fecha, hora, ejecución de n8n que la confirmó) — leído del GET que hizo cada ejecución antes del PUT.
INCIDENTE = [
    (9085, 15, "2026-10-22", "10:00", 301708),
    (9014, 15, "2026-10-19", "15:30", 301751),
    (9105, 7, "2026-10-26", "17:30", 301836),
    (9137, 15, "2026-10-27", "08:40", 301847),
    (9101, 15, "2026-10-26", "18:10", 301887),
    (8947, 2, "2026-10-06", "08:40", 301929),
    (9064, 2, "2026-10-06", "11:00", 301955),
    (9109, 15, "2026-10-20", "10:40", 301980),
    (8919, 2, "2026-10-06", "08:00", 302005),
    (8774, 15, "2026-11-18", "18:20", 302018),
    (9058, 15, "2026-10-15", "08:40", 302400),
]
IDS = [c[0] for c in INCIDENTE]


# ---------- n8n: workflow temporal con la credencial de Dentalink ----------

def base():
    return (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")


def api(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base()}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode() or "{}")


def llamar_webhook(ruta):
    req = urllib.request.Request(f"{base()}/webhook/{ruta}", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return {"error_http": e.code, "cuerpo": e.read().decode()[:800]}


def workflow_temporal(nombre, items, metodo, body_expr, ruta):
    """Webhook → Code (ítems FIJOS) → Dentalink (un pedido por ítem) → Code que junta las respuestas en el mismo orden."""
    g = Grafo(f"TMP {nombre} (incidente 06/10, se borra solo)")
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 0, {"webhookId": secrets.token_hex(8)})
    g.code("Citas", "return " + json.dumps([{"json": i} for i in items]) + ";", 220, 0)
    g.dentalink("Dentalink", metodo, f"'{DENTALINK}/citas/' + $json.id", body_expr, 440, 0)
    g.code("Juntar", "const pedidos = $('Citas').all().map((i) => i.json);\n"
                     "return [{ json: { r: $input.all().map((it, k) => ({ id: pedidos[k].id, resp: it.json })) } }];", 660, 0)
    g.conectar("Webhook", "Citas"); g.conectar("Citas", "Dentalink"); g.conectar("Dentalink", "Juntar")
    wf = g.json()
    wf["settings"] = dict(SETTINGS_MIN)
    return wf


def correr_temporal(nombre, items, metodo, body_expr=None):
    ruta = "tmp-" + secrets.token_hex(12)
    wid = None
    try:
        wid = api("/workflows", "POST", workflow_temporal(nombre, items, metodo, body_expr, ruta))["id"]
        api(f"/workflows/{wid}/activate", "POST")
        out = llamar_webhook(ruta)
    finally:
        if wid:
            for paso, f in (("desactivar", lambda: api(f"/workflows/{wid}/deactivate", "POST")), ("borrar", lambda: api(f"/workflows/{wid}", "DELETE"))):
                try:
                    f()
                except Exception as e:
                    print(f"  AVISO: no pude {paso} el workflow temporal {wid}: {e}. Borralo a mano en n8n.")
    if not isinstance(out, dict) or not isinstance(out.get("r"), list):
        raise SystemExit(f"Respuesta inesperada del workflow temporal ({nombre}): {json.dumps(out, ensure_ascii=False)[:800]}")
    return {x["id"]: x["resp"] for x in out["r"]}


def leer_citas():
    return correr_temporal("leer citas", [{"id": i} for i in IDS], "GET")


def cita_de(resp):
    d = (resp or {}).get("data") if isinstance(resp, dict) else None
    return d if isinstance(d, dict) and d.get("id") else None


# ---------- Supabase ----------

def conectar():
    import psycopg2
    faltan = [k for k in ("SUPABASE_DB_HOST", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD") if not env(k)]
    if faltan:
        raise SystemExit(f"Faltan en el .env: {', '.join(faltan)}")
    return psycopg2.connect(host=env("SUPABASE_DB_HOST"), port=int(env("SUPABASE_DB_PORT", "5432")), dbname=env("SUPABASE_DB_NAME", "postgres"),
                            user=env("SUPABASE_DB_USER"), password=env("SUPABASE_DB_PASSWORD"), connect_timeout=15)


def recordatorios(cur):
    cur.execute("SELECT id, id_cita_dentalink, confirmado_at, cancelado_at, workflow_execution_id FROM recordatorios_enviados "
                "WHERE id_cita_dentalink = ANY(%s) ORDER BY id", (IDS,))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, f)) for f in cur.fetchall()]


def en_ventana(ts):
    return ts is not None and VENTANA[0] <= ts.astimezone(timezone.utc).isoformat() <= VENTANA[1]


# ---------- plan ----------

def planear(citas, filas):
    plan = []
    for cita, antes, fecha, hora, ex in INCIDENTE:
        d = cita_de(citas.get(cita))
        p = {"cita": cita, "antes": antes, "fecha": fecha, "hora": hora, "ejecucion": ex, "accion": "saltear", "motivo": None,
             "paciente": (d or {}).get("nombre_paciente"), "estado_hoy": (d or {}).get("id_estado")}
        despues = [f for f in filas if f["id_cita_dentalink"] == cita and f["confirmado_at"] is not None
                   and f["confirmado_at"].astimezone(timezone.utc).isoformat() > VENTANA[1]]
        if d is None:
            p["motivo"] = f"no pude leerla en Dentalink: {json.dumps(citas.get(cita), ensure_ascii=False)[:200]}"
        elif d.get("id_estado") != 18:
            p["motivo"] = f"ya no está en 18 (hoy: {d.get('id_estado')} {d.get('estado_cita') or ''}): alguien la cambió después o ya se revirtió"
        elif str(d.get("fecha")) != fecha or str(d.get("hora_inicio", ""))[:5] != hora:
            p["motivo"] = f"la cita cambió de fecha/hora (hoy {d.get('fecha')} {str(d.get('hora_inicio'))[:5]}): no se toca"
        elif despues:
            p["motivo"] = f"el paciente la confirmó de verdad después (recordatorio confirmado el {despues[0]['confirmado_at']}): queda en 18"
        else:
            p["accion"] = "revertir"
        plan.append(p)
    marcas = [f for f in filas if en_ventana(f["confirmado_at"])]
    return plan, marcas


def mostrar(plan, marcas):
    print(f"\nDentalink — {len(plan)} citas del incidente:")
    for p in plan:
        hoy = f"{p['estado_hoy']} {ESTADOS.get(p['estado_hoy'], '')}".strip() if p["estado_hoy"] is not None else "?"
        que = f"→ volver a {p['antes']} ({ESTADOS.get(p['antes'], '')})" if p["accion"] == "revertir" else f"SALTEAR: {p['motivo']}"
        print(f"  cita {p['cita']}  {p['fecha']} {p['hora']}  {(p['paciente'] or '?').strip():32.32}  hoy: {hoy:30.30}  {que}")
    print(f"\nSupabase — recordatorios marcados confirmados dentro de la ventana del incidente: {len(marcas)}")
    for f in marcas:
        print(f"  fila {f['id']}  cita {f['id_cita_dentalink']}  confirmado_at {f['confirmado_at']}  → confirmado_at = NULL")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    print("Leyendo las 11 citas en Dentalink (workflow temporal de solo lectura)…")
    citas = leer_citas()
    con = conectar()
    cur = con.cursor()
    filas = recordatorios(cur)
    plan, marcas = planear(citas, filas)
    mostrar(plan, marcas)
    a_revertir = [p for p in plan if p["accion"] == "revertir"]
    reporte = {"cuando": datetime.now(timezone.utc).isoformat(), "apply": a.apply, "plan": plan,
               "marcas": [{**f, "confirmado_at": str(f["confirmado_at"]), "cancelado_at": str(f["cancelado_at"])} for f in marcas]}

    if not a.apply:
        print(f"\n[SIMULACIÓN] no se escribió nada. Para revertir {len(a_revertir)} cita(s) y {len(marcas)} recordatorio(s): agregar --apply")
        return

    if a_revertir:
        print(f"\nRevirtiendo {len(a_revertir)} cita(s) en Dentalink…")
        puts = correr_temporal("revertir confirmaciones", [{"id": p["cita"], "id_estado": p["antes"]} for p in a_revertir], "PUT",
                               "JSON.stringify({ id_estado: $json.id_estado })")
        reporte["puts"] = puts
        for p in a_revertir:
            d = cita_de(puts.get(p["cita"]))
            print(f"  cita {p['cita']}: {'ok' if d and d.get('id_estado') == p['antes'] else 'FALLÓ → ' + json.dumps(puts.get(p['cita']), ensure_ascii=False)[:300]}")
    if marcas:
        cur.execute("UPDATE recordatorios_enviados SET confirmado_at = NULL WHERE id = ANY(%s) AND confirmado_at BETWEEN %s AND %s RETURNING id",
                    ([f["id"] for f in marcas], VENTANA[0], VENTANA[1]))
        print(f"\nSupabase: confirmado_at = NULL en {cur.rowcount} fila(s): {[r[0] for r in cur.fetchall()]}")
        con.commit()

    print("\nVerificación (relectura):")
    finales = leer_citas()
    reporte["final"] = {}
    mal = 0
    for p in plan:
        d = cita_de(finales.get(p["cita"]))
        esperado = p["antes"] if p["accion"] == "revertir" else p["estado_hoy"]
        ok = d is not None and d.get("id_estado") == esperado
        mal += not ok
        reporte["final"][p["cita"]] = (d or {}).get("id_estado")
        print(f"  cita {p['cita']}: {(d or {}).get('id_estado')} {(d or {}).get('estado_cita') or ''}  {'ok' if ok else 'DISTINTO de lo esperado (' + str(esperado) + ')'}")
    quedan = [f for f in recordatorios(cur) if en_ventana(f["confirmado_at"])]
    print(f"  recordatorios aún marcados por el incidente: {len(quedan)}")
    destino = ROOT / "workflows" / "history" / f"revertir_confirmaciones_sombra_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(reporte, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\n{'TODO OK' if not mal and not quedan else 'REVISAR lo marcado arriba'} · reporte: {destino.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
