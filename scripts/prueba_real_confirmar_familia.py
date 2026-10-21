# -*- coding: utf-8 -*-
"""
prueba_real_confirmar_familia.py — 2026-10-21 · prueba de PUNTA A PUNTA, con el WhatsApp de Lucas, del caso del incidente de la Dra. (un papá con
dos turnos de la familia recibe dos recordatorios y contesta "Confirmo": tienen que quedar confirmados LOS DOS, en un solo mensaje, sin preguntas).

Todo pasa de verdad: citas reales en Dentalink (fichas de prueba "Test - Lucas" y "Test - Jana", que son del celular de Lucas), el recordatorio con
el formato del workflow de Recordatorios llega al WhatsApp de Lucas, el "Confirmo" entra por el webhook real del v6 (simular_mensaje_lucas.py) y
lo atiende el v7 en vivo (escribe en Dentalink y le contesta a Lucas). Después se verifica en Dentalink y se limpia TODO (regla 9).

SOLO el celular de Lucas (fijo) y SOLO fichas de ese celular. No toca el workflow de Recordatorios ni el v6.

  python scripts/prueba_real_confirmar_familia.py --fichas                                   # fichas del celular de Lucas (id y nombre)
  python scripts/prueba_real_confirmar_familia.py --crear --fecha 2026-10-30 --horas 10:30 11:10 --pacientes 608 <id_jana>
  python scripts/prueba_real_confirmar_familia.py --recordar                                 # manda los 2 recordatorios + memoria + recordatorios_enviados
  python scripts/simular_mensaje_lucas.py "Confirmo" --esperar
  python scripts/prueba_real_confirmar_familia.py --verificar                                # estado de las citas en Dentalink + filas + respuesta de Asiri
  python scripts/prueba_real_confirmar_familia.py --limpiar                                  # anula las citas, borra filas sembradas y memoria (regla 9)
"""
import argparse, json, secrets, sys, urllib.error, urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from crear_cita_prueba_examen import api, llamar_webhook, SETTINGS_MIN  # noqa: E402
from v7_lib import Grafo, DENTALINK  # noqa: E402
from seed_examen_v7 import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
LUCAS = "5491161461034"
MARCA = "prueba-real-lucas"
ESTADO = ROOT / "data" / "prueba_real_confirmar_familia.json"
COMENTARIO = "PRUEBA DEL BOT DE LUCAS (se anula sola al terminar la prueba)"
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def dentalink(metodo, url, body=None, query=None):
    """Un pedido a Dentalink con la credencial de n8n (workflow temporal: crear, activar, llamar, desactivar, borrar)."""
    ruta = "tmp-" + secrets.token_hex(12)
    g = Grafo("TMP prueba real confirmar familia (se borra solo)")
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 0, {"webhookId": secrets.token_hex(8)})
    g.dentalink("Dentalink", metodo, json.dumps(url), ("JSON.stringify(" + json.dumps(body, ensure_ascii=False) + ")") if body is not None else None, 240, 0,
                query_expr=("JSON.stringify(" + json.dumps(query).replace("}}", "} }") + ")") if query is not None else None)   # "}}" cerraría la expresión de n8n
    g.conectar("Webhook", "Dentalink")
    wf = g.json(); wf["settings"] = dict(SETTINGS_MIN)
    wid = None
    try:
        wid = api("/workflows", "POST", wf)["id"]
        api(f"/workflows/{wid}/activate", "POST")
        r = llamar_webhook(ruta)
        return r[0] if isinstance(r, list) and r else r
    finally:
        if wid:
            for f in (lambda: api(f"/workflows/{wid}/deactivate", "POST"), lambda: api(f"/workflows/{wid}", "DELETE")):
                try:
                    f()
                except Exception as e:
                    print(f"  AVISO: no pude limpiar el workflow temporal {wid}: {e}")


def fichas():
    r = dentalink("GET", f"{DENTALINK}/pacientes", query={"celular": {"lk": LUCAS[-10:]}})
    out = [{"id": p.get("id"), "nombre": p.get("nombre"), "apellidos": p.get("apellidos"), "habilitado": p.get("habilitado")} for p in (r or {}).get("data") or []]
    for f in out:
        print(f"  ficha {f['id']}: {f['nombre']} {f['apellidos']} (habilitado={f['habilitado']})")
    return out


def guardar(e):
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def leer():
    if not ESTADO.exists():
        sys.exit("No hay prueba en curso (falta " + str(ESTADO) + ").")
    return json.loads(ESTADO.read_text(encoding="utf-8"))


def crear(fecha, horas, pacientes):
    if len(horas) != len(pacientes):
        sys.exit("--horas y --pacientes tienen que tener el mismo largo")
    propias = {f["id"]: f for f in fichas()}
    citas = []
    for hora, pid in zip(horas, pacientes):
        if pid not in propias:
            sys.exit(f"La ficha {pid} no es del celular de Lucas: no se crea nada más.")
        body = {"id_dentista": 1, "id_sucursal": 1, "id_sillon": 1, "id_paciente": pid, "fecha": fecha, "hora_inicio": hora, "duracion": 40, "comentario": COMENTARIO}
        r = dentalink("POST", f"{DENTALINK}/citas/", body)
        data = (r or {}).get("data") if isinstance(r, dict) else None
        if not (isinstance(data, dict) and data.get("id")):
            print(f"  NO se creó la de las {hora} (ficha {pid}): {json.dumps(r, ensure_ascii=False)[:400]}")
            continue
        citas.append({"id": data["id"], "id_paciente": pid, "nombre": (propias[pid]["nombre"] or "").strip(), "fecha": fecha, "hora": hora})
        print(f"  cita {data['id']} creada: ficha {pid} ({propias[pid]['nombre']}) {fecha} {hora}")
        guardar({"citas": citas})
    return citas


def texto_recordatorio(c):
    """Mismo formato que el recordatorio de 72 h del workflow de Recordatorios (recordatorios/preparar_mensaje.js, control)."""
    d = date.fromisoformat(c["fecha"])
    ult = c["nombre"][-1:].lower()
    trat = "Estimada" if ult == "a" else "Estimado" if ult == "o" else "Estimado/a"
    return ("✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\n" + trat + " " + c["nombre"] + ",\nLe recordamos su turno con la Dra. Rodríguez Raquel:\n\n"
            + f"📅 {DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}\n🕔 {c['hora']} hs\n📍 Balcarce Nº37, 2º piso\n\n"
            + "Le pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno.\n\n⚠️ Importante:\n"
            + "* Si su turno está confirmado y no asiste al mismo, de igual manera deberá abonar el control.\n"
            + "* Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\nEsperamos su confirmación, gracias por elegirnos 💙")


def evolution():
    """URL y clave de envío: las mismas del nodo 'Enviar WhatsApp' del workflow de Recordatorios (copia local, fuera del repo). No se imprimen."""
    w = json.loads((ROOT / "workflows" / "current" / "recordatorios_7RqTApkvVavRmq3R.json").read_text(encoding="utf-8"))
    n = next(x for x in w["nodes"] if x["name"] == "Enviar WhatsApp")["parameters"]
    clave = next(h["value"] for h in n["headerParameters"]["parameters"] if h["name"] == "apikey")
    return n["url"], clave


def recordar():
    e = leer()
    url, clave = evolution()
    con = conectar(); con.autocommit = True; cur = con.cursor()
    for c in e["citas"]:
        msg = texto_recordatorio(c)
        req = urllib.request.Request(url, data=json.dumps({"number": LUCAS, "text": msg}).encode(), method="POST", headers={"apikey": clave, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  recordatorio de la cita {c['id']} ({c['nombre']}) → WhatsApp {r.status}")
        d = date.fromisoformat(c["fecha"])
        nota = (f"[NOTA INTERNA - contexto del último recordatorio enviado, NO mencionar al paciente]\nAcabo de enviar un recordatorio 72h del siguiente turno:\n"
                f"- Cita Dentalink ID: {c['id']}\n- ID Paciente: {c['id_paciente']}\n- Paciente: {c['nombre']}\n- Fecha: {DIAS[d.weekday()].lower()} {d.day} de {MESES[d.month - 1]} de {d.year}\n"
                f"- Hora: {c['hora']}\n- Profesional: Dra. Rodríguez Raquel\nSi el paciente responde sobre este turno, ya conocés todos los datos. NO le pidas que repita fecha/hora/profesional.")
        for contenido in (msg, nota):
            cur.execute("INSERT INTO n8n_chat_histories (session_id, message) VALUES (%s, %s::jsonb)",
                        (LUCAS, json.dumps({"type": "ai", "content": contenido, "tool_calls": [], "additional_kwargs": {"source": "reminder_note"}, "response_metadata": {}, "invalid_tool_calls": []}, ensure_ascii=False)))
        cur.execute("""INSERT INTO recordatorios_enviados (telefono, chat_remote_jid, id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, workflow_execution_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, '72h', %s)""", (LUCAS, LUCAS + "@s.whatsapp.net", c["id"], c["id_paciente"], c["nombre"], c["fecha"], c["hora"], MARCA))
    con.close()
    print("  listo: ahora  python scripts/simular_mensaje_lucas.py \"Confirmo\" --esperar")


def verificar():
    e = leer()
    for c in e["citas"]:
        r = dentalink("GET", f"{DENTALINK}/citas/{c['id']}")
        d = (r or {}).get("data") or {}
        print(f"  cita {c['id']} ({c['nombre']} {c['fecha']} {c['hora']}): id_estado={d.get('id_estado')} «{d.get('estado_cita')}» anulación={d.get('estado_anulacion')}")
    con = conectar(); cur = con.cursor()
    cur.execute("SELECT id_cita_dentalink, confirmado_at, cancelado_at FROM recordatorios_enviados WHERE workflow_execution_id = %s ORDER BY id", (MARCA,))
    for f in cur.fetchall():
        print(f"  recordatorio cita {f[0]}: confirmado_at={f[1]} cancelado_at={f[2]}")
    cur.execute("SELECT id, message->>'type', left(message->>'content', 400), message->'additional_kwargs'->>'source' FROM n8n_chat_histories WHERE session_id = %s ORDER BY id DESC LIMIT 4", (LUCAS,))
    for f in reversed(cur.fetchall()):
        print(f"  [{f[0]}] {f[1]}/{f[3]}: {f[2]!r}")
    con.close()


def limpiar():
    e = leer() if ESTADO.exists() else {"citas": []}
    for c in e["citas"]:
        r = dentalink("PUT", f"{DENTALINK}/citas/{c['id']}/", {"id_estado": 1})
        d = (r or {}).get("data") or {}
        print(f"  cita {c['id']} anulada: id_estado={d.get('id_estado')} {json.dumps(r, ensure_ascii=False)[:160] if not d else ''}")
    con = conectar(); con.autocommit = True; cur = con.cursor()
    cur.execute("DELETE FROM recordatorios_enviados WHERE workflow_execution_id = %s", (MARCA,))
    print(f"  filas de recordatorio sembradas borradas: {cur.rowcount}")
    con.close()
    if ESTADO.exists():
        ESTADO.unlink()
    print("  siguiente: python scripts/limpiar_numero_demo.py --phone " + LUCAS + " --apply --borrar-logs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichas", action="store_true"); ap.add_argument("--crear", action="store_true"); ap.add_argument("--recordar", action="store_true")
    ap.add_argument("--verificar", action="store_true"); ap.add_argument("--limpiar", action="store_true")
    ap.add_argument("--fecha"); ap.add_argument("--horas", nargs="+"); ap.add_argument("--pacientes", nargs="+", type=int)
    a = ap.parse_args()
    if a.fichas:
        fichas()
    elif a.crear:
        crear(a.fecha, a.horas, a.pacientes)
    elif a.recordar:
        recordar()
    elif a.verificar:
        verificar()
    elif a.limpiar:
        limpiar()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
