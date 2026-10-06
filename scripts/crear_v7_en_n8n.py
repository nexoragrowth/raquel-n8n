# -*- coding: utf-8 -*-
"""
crear_v7_en_n8n.py — crea (o actualiza) en n8n los workflows del v7, SIEMPRE INACTIVOS y SIN TOCAR el v6 ni ningún otro workflow existente.

  1) las 7 herramientas (sub-workflows)  →  2) el cerebro (con los ids de las herramientas)  →  3) "v7 Test (sombra)": un webhook con ruta secreta para probar
     el cerebro y cada herramienta en MODO SOMBRA desde esta máquina. El test queda INACTIVO: se activa solo mientras se prueba (scripts/probar_v7.py --activar / --desactivar).
Si un workflow con ese nombre ya existe, lo actualiza en su lugar (PUT con las claves permitidas). Nunca borra nada.

USO:  python scripts/crear_v7_en_n8n.py              # simulación: muestra qué crearía/actualizaría
      python scripts/crear_v7_en_n8n.py --aplicar    # crea/actualiza (inactivos) + verifica + guarda v7/ids.json
Regla del proyecto: con OK de Lucas (dado el 06/10: "si podés, armá el v7").
"""
import argparse, json, secrets, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require
from v7_lib import Grafo, SETTINGS
import build_v7_workflows as B

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
IDS = ROOT / "v7" / "ids.json"
RUTA_TEST = ROOT / "data" / "v7_test_ruta.txt"     # data/ está en .gitignore: la ruta secreta del webhook de prueba no se commitea
PUT_KEYS = ("name", "nodes", "connections", "settings")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
HERRAMIENTAS = ["ejecutar_propuesta", "ver_turnos", "elegir_ficha", "proponer", "buscar_horarios", "confirmar_turno", "clinica"]


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method, headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def wf_test(ids, ruta):
    """Webhook de prueba (ruta secreta, inactivo por defecto): body {destino: 'cerebro'|<herramienta>, ...campos de entrada}. Nunca escribe nada en modo sombra."""
    g = Grafo("v7 Test (sombra)")
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 200, {"webhookId": secrets.token_hex(8)})
    g.code("Despachar", "const ids = " + json.dumps(ids) + ";\nconst b = $input.first().json.body || {};\nconst destino = String(b.destino || 'cerebro');\nif (destino === 'reset') return [{ json: { reset: true, tel: String(b.tel || '') } }];\nconst wid = ids[destino];\nif (!wid) return [{ json: { error: 'destino desconocido: ' + destino, destinos: Object.keys(ids) } }];\nconst { destino: _d, modo: _m, ...entrada } = b;\n// SIEMPRE sombra: este webhook existe solo para probar; nadie puede pedirle una ejecución en vivo desde afuera.\nreturn [{ json: { ...entrada, modo: 'sombra', workflow_id: wid } }];", 220, 200)
    g._nodo("Ejecutar", "n8n-nodes-base.executeWorkflow", 1.2, {"workflowId": {"__rl": True, "value": "={{ $json.workflow_id }}", "mode": "id"}, "workflowInputs": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": [], "attemptToConvertTypes": False, "convertFieldsToString": False}, "options": {}}, 440, 200, {"alwaysOutputData": True})
    g.si("¿Reinicio?", "$json.reset === true", 330, 200)
    claves = ["ficha", "turnos_vistos", "ofertas", "lotes", "bloque", "bloque_req", "propuesta", "pago"]
    x = 440
    for c in claves:
        g.redis_del(f"Redis DEL {c}", f"'{c}:' + $('Despachar').first().json.tel", x, 60)
        x += 160
    g.code("Reinicio listo", "return [{ json: { reinicio: 'ok', tel: $('Despachar').first().json.tel } }];", x, 60)
    g.conectar("Webhook", "Despachar")
    g.conectar("Despachar", "¿Reinicio?")
    g.conectar("¿Reinicio?", "Redis DEL " + claves[0], 0)
    g.conectar("¿Reinicio?", "Ejecutar", 1)
    for a_, b_ in zip(["Redis DEL " + c for c in claves], ["Redis DEL " + c for c in claves[1:]] + ["Reinicio listo"]):
        g.conectar(a_, b_)
    return g.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    aplicar = ap.parse_args().aplicar
    existentes = {w["name"]: w["id"] for w in api("/workflows?limit=250")["data"]}
    ids = {}
    plan = []

    def plantilla(nombre_clave, wf_json):
        nombre = wf_json["name"]
        plan.append((nombre_clave, nombre, existentes.get(nombre)))

    herramientas_json = {k: json.loads((ROOT / "v7" / "workflows" / f"{ {'ejecutar_propuesta': 'ejecutar_propuesta'}.get(k, k) }.json").read_text(encoding="utf-8")) for k in HERRAMIENTAS}
    cerebro = json.loads((ROOT / "v7" / "workflows" / "cerebro.json").read_text(encoding="utf-8"))
    for k in HERRAMIENTAS:
        plantilla(k, herramientas_json[k])
    plantilla("cerebro", cerebro)
    plantilla("test", {"name": "v7 Test (sombra)"})
    print("Plan (nada toca el v6 ni otros workflows):")
    for clave, nombre, wid in plan:
        print(f"  {'ACTUALIZA' if wid else 'CREA     '} {nombre}" + (f"  ({wid})" if wid else ""))
    if not aplicar:
        print("\n[SIMULACION] No se creó nada. Correr con --aplicar.")
        return

    def subir(nombre, wf, wid):
        body = {"name": nombre, "nodes": wf["nodes"], "connections": wf["connections"], "settings": {k: v for k, v in (wf.get("settings") or SETTINGS).items() if k in SETTINGS_OK}}
        if wid:
            api(f"/workflows/{wid}", "PUT", body)
            return wid
        return api("/workflows", "POST", body)["id"]

    for k in HERRAMIENTAS:
        wf = herramientas_json[k]
        ids[k] = subir(wf["name"], wf, existentes.get(wf["name"]))
        print(f"  ok {wf['name']} → {ids[k]}")
    txt = json.dumps(cerebro, ensure_ascii=False)
    for k in HERRAMIENTAS:
        txt = txt.replace(f"@@ID:{k}@@", ids[k])
    assert "@@ID:" not in txt, "quedaron marcadores sin resolver"
    cer = json.loads(txt)
    ids["cerebro"] = subir(cer["name"], cer, existentes.get(cer["name"]))
    print(f"  ok {cer['name']} → {ids['cerebro']}")
    ruta = RUTA_TEST.read_text(encoding="utf-8").strip() if RUTA_TEST.exists() else "v7-" + secrets.token_hex(20)
    RUTA_TEST.parent.mkdir(exist_ok=True)
    RUTA_TEST.write_text(ruta, encoding="utf-8")
    test = wf_test({**ids}, ruta)
    ids["test"] = subir(test["name"], test, existentes.get(test["name"]))
    print(f"  ok {test['name']} → {ids['test']}  (inactivo; ruta secreta guardada en data/)")
    IDS.write_text(json.dumps(ids, indent=1, ensure_ascii=False), encoding="utf-8")

    # verificación: existen, mismos nodos, sin marcadores. 'activo' es informativo: los sub-workflows tienen que estar activos para ejecutarse; el único con puerta de entrada es el de prueba (ruta secreta)
    print("\nVerificación:")
    ok = True
    for clave, wid in ids.items():
        w = api(f"/workflows/{wid}")
        esperado = len((cer if clave == 'cerebro' else test if clave == 'test' else herramientas_json[clave])["nodes"])
        bien = (len(w["nodes"]) == esperado) and "@@ID:" not in json.dumps(w)
        ok = ok and bien
        print(f"  {'OK ' if bien else 'MAL'} {w['name']:34} nodos {len(w['nodes'])}/{esperado} activo={w.get('active')}{'  <- WEBHOOK DE PRUEBA ABIERTO (probar_v7.py --desactivar al terminar)' if clave == 'test' and w.get('active') else ''}")
    v6 = api("/workflows/O155MqHgOSaNZ9ye")
    print(f"  v6 intacto: activo={v6.get('active')} nodos={len(v6['nodes'])} versionId={v6.get('versionId')[:8]}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
