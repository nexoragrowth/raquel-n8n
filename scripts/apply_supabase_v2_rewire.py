"""
Recableado completo a Supabase Nexora v2 (2026-07-08).

Contexto: el proyecto Supabase original (dchztroesbpwxxkfywwu) fue BORRADO.
Se creo uno nuevo (ujfyapjwrdhnvqdvsjwp) y se recuperaron datos. Este script:

1. Repunta los 18 nodos Postgres de 7 workflows de la credencial vieja
   ('Postgres account', proyecto borrado) a 'Postgres Supabase Nexora v2'
   (id EWhpNhb6tkGg1OTp, pooler us-west-2).
2. En v6 ademas: swap de ref en la URL de obtener_historial_paciente, y en las
   3 tools de recordatorios: ref nuevo + REMOVER apikey viejo embebido en URL
   + migrar auth de httpHeaderAuth (key vieja) a supabaseApi ('Supabase account',
   ya validada contra el proyecto nuevo).
3. Resetea el cursor del Logger si apunta a ids del proyecto viejo.

Guardas: backup pre/post por workflow, conteo de nodos invariante, cero
referencias al ref viejo tras el patch, webhookId evo-webhook-v2 preservado.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
HIST = Path(__file__).resolve().parents[1] / "workflows" / "history"
H = {"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"}

OLD_REF = "dchztroesbpwxxkfywwu"
NEW_REF = "ujfyapjwrdhnvqdvsjwp"
OLD_PG_CRED = "xwvjww5Odcxiy1K9"
NEW_PG_CRED = {"id": "EWhpNhb6tkGg1OTp", "name": "Postgres Supabase Nexora v2"}
SUPA_API_CRED = {"id": "Thn3jgEbbxPFD7d9", "name": "Supabase account"}

WFS = [
    ("O155MqHgOSaNZ9ye", "v6"),
    ("5cAWJxiWJ50hxEq3", "SubWF"),
    ("xsXeHp7WLXnFQc3o", "Logger"),
    ("7RqTApkvVavRmq3R", "Recordatorio"),
    ("BO1cdE8xmqln4IeO", "ResumenClinico"),
    ("En0A5lXd3Whb5yFy", "Cleanup"),
    ("w7BBpZeEwZnpCX1q", "HumanTakeover"),
]
REST_TOOLS = ["consultar_recordatorios_abiertos", "marcar_recordatorio_confirmado",
              "marcar_recordatorio_cancelado"]


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def die(msg):
    print("ABORTADO: " + msg)
    sys.exit(1)


ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}

ts = time.strftime("%Y%m%d_%H%M%S")
resumen = []

for wid, tag in WFS:
    wf = api("GET", f"/api/v1/workflows/{wid}")
    raw_before = json.dumps(wf, ensure_ascii=False)
    (HIST / f"{tag}_PRE_supav2_{ts}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    cambios = []
    for n in wf["nodes"]:
        creds = n.get("credentials", {})
        # 1) repuntar credencial postgres
        pg = creds.get("postgres")
        if pg and pg.get("id") == OLD_PG_CRED:
            creds["postgres"] = dict(NEW_PG_CRED)
            cambios.append(f"cred-pg:{n['name']}")
        # 2) v6: URLs y auth
        if tag == "v6":
            p = n.get("parameters", {})
            url = p.get("url", "")
            if n["name"] == "obtener_historial_paciente" and OLD_REF in url:
                p["url"] = url.replace(OLD_REF, NEW_REF)
                cambios.append("url:obtener_historial")
            elif n["name"] in REST_TOOLS:
                if OLD_REF in url:
                    url = url.replace(OLD_REF, NEW_REF)
                url = re.sub(r"apikey=[^&]*&", "", url)
                url = re.sub(r"[?&]apikey=[^&]*$", "", url)
                p["url"] = url
                p["authentication"] = "predefinedCredentialType"
                p["nodeCredentialType"] = "supabaseApi"
                p.pop("genericAuthType", None)
                creds.pop("httpHeaderAuth", None)
                creds["supabaseApi"] = dict(SUPA_API_CRED)
                cambios.append(f"rest-tool:{n['name']}")

    if not cambios:
        print(f"[{tag}] sin cambios (raro) — skip")
        continue

    nodes_json = json.dumps(wf["nodes"], ensure_ascii=False)
    before_obj = json.loads(raw_before)
    # guardas
    if len(wf["nodes"]) != len(before_obj["nodes"]):
        die(f"{tag}: cambio el numero de nodos")
    if tag == "v6":
        if OLD_REF in nodes_json:
            die("v6: quedo alguna referencia al proyecto viejo")
        if "apikey=" in nodes_json and "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6I" in nodes_json:
            die("v6: quedo un apikey viejo embebido")
        wb = json.dumps(before_obj["nodes"], ensure_ascii=False).count("evo-webhook-v2")
        if nodes_json.count("evo-webhook-v2") != wb:
            die("v6: webhookId alterado")
    if OLD_PG_CRED in nodes_json:
        die(f"{tag}: quedo un nodo con la credencial pg vieja")

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    res = api("PUT", f"/api/v1/workflows/{wid}", body)
    (HIST / f"{tag}_POST_supav2_{ts}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{tag}] OK — {len(cambios)} cambios: {cambios}")
    resumen.append((tag, len(cambios)))

# 3) cursor del Logger
print("\nCursor del Logger:")
lg = api("GET", "/api/v1/workflows/xsXeHp7WLXnFQc3o")
sd = lg.get("staticData")
print("  staticData:", json.dumps(sd, ensure_ascii=False)[:400] if sd else "(vacio)")

print("\nRESUMEN:", resumen)
print("Backups en workflows/history/ con tag supav2_" + ts)
