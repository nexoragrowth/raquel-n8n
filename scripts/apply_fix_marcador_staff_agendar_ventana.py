# -*- coding: utf-8 -*-
"""
apply_fix_marcador_staff_agendar_ventana.py — tres arreglos que van JUNTOS (2026-10-05).

PARTE 1 · El aviso "[ATENCION HUMANA ...]" que se guarda en la memoria cuando escribe el staff incluye una
  ORDEN ("Mantente en silencio y NO respondas ... hasta que un admin diga /bot on"). El LLM la obedece:
  con el aviso en los ultimos 4 turnos callo el 78% de las veces (vs 20% sin el), sin vencer nunca y sin
  depender de la ventana de 24 h (ej. exec 289847: la paciente elige un horario y recibe [NO_REPLY]).
  Se saca SOLO la orden. Se conserva el prefijo "[ATENCION HUMANA" y "enviado por <autor> desde el PANEL",
  porque el panel (chat-view.tsx, chat-data.ts, conversaciones-data.ts, media-entrantes.ts) detecta y
  parsea los mensajes del staff por ahi. Nodos: v6 "Build fromMe AI memory" y panel "Armar fila memoria".

PARTE 2 · Sub-Agent Agendar no tiene conectada `ver_turnos_paciente`, aunque su prompt le pide usarla antes
  de reservar (doble reserva). Se conecta la herramienta y se aclara en el prompt que cuenta solo un turno
  activo (ni anulado ni pasado), porque la herramienta devuelve todas las citas.

PARTE 3 · Ventana de 24 h coherente. Hoy solo "Consultar Takeover Paciente" (entrada) respeta la ventana;
  "Gate Humano Final" y "Triaje: Decidir" leen el booleano crudo. Sin esta parte, la PARTE 1 empeora las
  cosas: pasadas las 24 h el agente corre (reservar_turno incluido), el gate final descarta la respuesta y
  el turno queda reservado sin aviso al paciente. Ademas "Helper - Notify Grupo / Activar Takeover Paciente"
  hacia human_takeover_at = now() incluso cuando lo llama el gate (silencioso), extendiendo la ventana con
  cada mensaje del paciente: ahora conserva la hora de inicio si la ventana sigue vigente.

NO toca: credenciales (las claves escritas a mano en los Code nodes se conservan tal cual: se edita por
reemplazo de cadenas y nunca se leen ni imprimen), el resto de nodos, ni datos en la base. Las filas viejas
de memoria conservan el texto anterior hasta que salgan de la ventana de 10 mensajes; para corregirlas ya,
ver scripts/sql_marcador_staff_filas_viejas.sql (separado, requiere OK).

USO:
    python scripts/apply_fix_marcador_staff_agendar_ventana.py                    # simulacion (solo GET): muestra el diff
    python scripts/apply_fix_marcador_staff_agendar_ventana.py --apply            # backup PRE + PUT + verificacion + backup POST
    python scripts/apply_fix_marcador_staff_agendar_ventana.py --partes 1,2       # (NO recomendado sin la 3)

Regla del proyecto: NUNCA --apply sin OK explicito de Lucas. Despues: prueba real (mensaje de Lucas -> la
respuesta llega) y limpiar el numero de prueba (scripts/limpiar_numero_demo.py).
"""
import argparse, copy, difflib, json, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
V6, PANEL, HELPER = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye"), "jzxb5zUKCaJcvCgp", "S5U6tSipzlgFHCkf"

OLD_ORDEN = " NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on."
NEW_ORDEN = " Mensaje del staff, no es output tuyo."
OLD_DOBLE = "Si ya tiene turno activo en +/- 7 días"
NEW_DOBLE = "Si ya tiene un turno activo (no anulado ni pasado) en +/- 7 días"
VENTANA = "(res[0].human_takeover === true && res[0].human_takeover_at && (Date.now() - new Date(res[0].human_takeover_at).getTime()) < 24 * 3600 * 1000)"
OLD_HELPER_Q = ("INSERT INTO pacientes (telefono, human_takeover, human_takeover_at, updated_at) VALUES ($1, true, now(), now()) "
                "ON CONFLICT (telefono) DO UPDATE SET human_takeover = true, human_takeover_at = now(), updated_at = now()")
NEW_HELPER_Q = ("INSERT INTO pacientes (telefono, human_takeover, human_takeover_at, updated_at) VALUES ($1, true, now(), now()) "
                "ON CONFLICT (telefono) DO UPDATE SET human_takeover_at = CASE WHEN pacientes.human_takeover = true "
                "AND pacientes.human_takeover_at > now() - interval '24 hours' THEN pacientes.human_takeover_at ELSE now() END, "
                "human_takeover = true, updated_at = now()")


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"),
                                          "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def backup(wid, wf, label):
    HIST.mkdir(parents=True, exist_ok=True)
    dest = HIST / f"{wid}_{label}_{int(time.time())}.json"
    dest.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup: workflows/history/{dest.name}")


def nodo(wf, nombre):
    n = next((n for n in wf["nodes"] if n["name"] == nombre), None)
    if not n:
        sys.exit(f"ABORTO: falta el nodo '{nombre}' en {wf.get('name')}.")
    return n


def reemplazar_unico(texto, viejo, nuevo, donde):
    if texto.count(viejo) != 1:
        sys.exit(f"ABORTO: en {donde} la cadena a reemplazar aparece {texto.count(viejo)} veces (esperaba 1). "
                 "Otra sesion cambio el nodo: revisar a mano.")
    return texto.replace(viejo, nuevo)


def redactar(linea):
    return re.sub(r"sb_secret_[A-Za-z0-9_\-]+", "<KEY>", linea)


def mostrar_diff(titulo, a, b):
    print(f"\n--- {titulo}")
    for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
        if l.startswith(("---", "+++", "@@")):
            continue
        print("   ", redactar(l)[:420])


def preparar(partes, v6, panel, helper):
    cambios = {"v6": [], "panel": [], "helper": []}
    nv6, npa, nhe = copy.deepcopy(v6), copy.deepcopy(panel), copy.deepcopy(helper)
    if 1 in partes:
        for wf, nombre, tag, ws in ((nv6, "Build fromMe AI memory", "v6", "v6"), (npa, "Armar fila memoria", "panel", "panel")):
            n = nodo(wf, nombre)
            viejo = n["parameters"]["jsCode"]
            n["parameters"]["jsCode"] = reemplazar_unico(viejo, OLD_ORDEN, NEW_ORDEN, nombre)
            cambios[ws].append(nombre)
            mostrar_diff(f"P1 · {nombre}", viejo, n["parameters"]["jsCode"])
    if 2 in partes:
        ag = nodo(nv6, "Sub-Agent Agendar")
        viejo = ag["parameters"]["options"]["systemMessage"]
        ag["parameters"]["options"]["systemMessage"] = reemplazar_unico(viejo, OLD_DOBLE, NEW_DOBLE, "Sub-Agent Agendar")
        cambios["v6"].append("Sub-Agent Agendar")
        mostrar_diff("P2 · prompt de Sub-Agent Agendar", viejo, ag["parameters"]["options"]["systemMessage"])
        nodo(nv6, "ver_turnos_paciente")
        lista = nv6["connections"]["ver_turnos_paciente"]["ai_tool"][0]
        if any(c["node"] == "Sub-Agent Agendar" for c in lista):
            print("\n--- P2 · conexion: ver_turnos_paciente ya estaba conectada a Sub-Agent Agendar (sin cambio)")
        else:
            antes = [c["node"] for c in lista]
            lista.append({"node": "Sub-Agent Agendar", "type": "ai_tool", "index": 0})
            print(f"\n--- P2 · conexion ai_tool de ver_turnos_paciente\n    antes: {antes}\n    ahora: {[c['node'] for c in lista]}")
    if 3 in partes:
        for nombre in ("Gate Humano Final", "Triaje: Decidir"):
            n = nodo(nv6, nombre)
            viejo = n["parameters"]["jsCode"]
            nuevo = reemplazar_unico(viejo, "select=human_takeover&", "select=human_takeover,human_takeover_at&", nombre)
            nuevo = reemplazar_unico(nuevo, "res[0].human_takeover === true", VENTANA, nombre)
            n["parameters"]["jsCode"] = nuevo
            cambios["v6"].append(nombre)
            mostrar_diff(f"P3 · {nombre}", viejo, nuevo)
        n = nodo(nhe, "Activar Takeover Paciente")
        if n["parameters"]["query"] != OLD_HELPER_Q:
            sys.exit("ABORTO: la query de 'Activar Takeover Paciente' no es la esperada. Revisar a mano.")
        n["parameters"]["query"] = NEW_HELPER_Q
        cambios["helper"].append("Activar Takeover Paciente")
        mostrar_diff("P3 · Helper - Notify Grupo · Activar Takeover Paciente", OLD_HELPER_Q.replace(" ON CONFLICT", "\nON CONFLICT"), NEW_HELPER_Q.replace(" ON CONFLICT", "\nON CONFLICT"))
    return {"v6": nv6, "panel": npa, "helper": nhe}, cambios


def put(wid, wf):
    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{wid}", method="PUT", payload=body)


def verificar(nombre, antes, despues, esperados, conexion_extra=None):
    ok = True
    a, d = {n["name"]: n for n in antes["nodes"]}, {n["name"]: n for n in despues["nodes"]}
    cambiados = sorted(k for k in a if a[k] != d.get(k))
    chequeos = {
        "misma cantidad de nodos": len(antes["nodes"]) == len(despues["nodes"]),
        "solo cambiaron los nodos previstos": cambiados == sorted(esperados),
        "workflow sigue activo": despues.get("active") == antes.get("active"),
    }
    ca = {k: v for k, v in antes["connections"].items() if k != conexion_extra}
    cd = {k: v for k, v in despues["connections"].items() if k != conexion_extra}
    chequeos["resto de conexiones identico"] = ca == cd
    if nombre == "v6":
        chequeos["webhookId evo-webhook-v2 intacto"] = nodo(despues, "Webhook - Evolution API").get("webhookId") == "evo-webhook-v2"
    for k, v in chequeos.items():
        print(f"  {'OK   ' if v else 'FALLA'} [{nombre}] {k}" + ("" if v or k != "solo cambiaron los nodos previstos" else f"  (cambiaron: {cambiados})"))
        ok &= v
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--partes", default="1,2,3")
    args = ap.parse_args()
    partes = {int(x) for x in args.partes.split(",")}
    if partes != {1, 2, 3}:
        print("AVISO: aplicar la parte 1 sin la 3 deja el agujero 'agente corre y el gate final descarta' (ver cabecera).")

    v6, panel, helper = api(f"/workflows/{V6}"), api(f"/workflows/{PANEL}"), api(f"/workflows/{HELPER}")
    for w in (v6, panel, helper):
        print(f"{w['name'][:48]:<48} active={w.get('active')} nodos={len(w['nodes'])} versionId={w.get('versionId')}")
    nuevos, cambios = preparar(partes, v6, panel, helper)
    print("\nResumen de nodos que cambian:", json.dumps(cambios, ensure_ascii=False))

    if not args.apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return

    for wid, previo in ((V6, v6), (PANEL, panel), (HELPER, helper)):
        if api(f"/workflows/{wid}").get("versionId") != previo.get("versionId"):
            sys.exit("ABORTO: un workflow cambio mientras preparaba el fix (otra sesion hizo un PUT). Volver a correr.")
    for wid, previo in ((V6, v6), (PANEL, panel), (HELPER, helper)):
        backup(wid, previo, "PRE_fix_marcador_ventana")
    # el panel y el helper primero (cambios chicos); el v6 al final
    todo_ok = True
    plan = [("panel", PANEL, panel, nuevos["panel"], cambios["panel"], None),
            ("helper", HELPER, helper, nuevos["helper"], cambios["helper"], None),
            ("v6", V6, v6, nuevos["v6"], cambios["v6"], "ver_turnos_paciente" if 2 in partes else None)]
    for nombre, wid, previo, nuevo, esperados, extra in plan:
        if not esperados and extra is None:
            continue
        put(wid, nuevo)
        post = api(f"/workflows/{wid}")
        backup(wid, post, "POST_fix_marcador_ventana")
        todo_ok &= verificar(nombre, previo, post, esperados, extra)
    if not todo_ok:
        sys.exit("VERIFICACION FALLIDA: revisar ya. Los backups PRE estan en workflows/history/.")
    print("\nAplicado. Falta la prueba real: un mensaje de Lucas debe llegar al WhatsApp; despues limpiar el numero de prueba.")


if __name__ == "__main__":
    main()
