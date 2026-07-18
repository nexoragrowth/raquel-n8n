"""
Batería E2E parametrizable contra el v6 vivo (creada 2026-07-18 post-migración v3).

Manda mensajes simulados (patrón sim_and_wait) desde el número admin de Lucas y
valida la respuesta final del bot contra regexes. CADA MENSAJE GENERA UNA RESPUESTA
REAL DE WHATSAPP al teléfono admin — usar con criterio (3-6 casos por corrida).

Uso:
    python tests/test_e2e_bateria.py            # corre la batería BASE
    python tests/test_e2e_bateria.py contexto   # corre solo los casos cuyo tag matchee

Para agregar casos pedidos por Lucas: sumar dicts a CASOS. Campos:
    tag      : nombre corto para filtrar
    mensaje  : texto que "envía el paciente"
    espera   : lista de regexes (case-insensitive) que TODOS deben aparecer en la
               respuesta concatenada del bot
    no_espera: (opcional) regexes que NO deben aparecer (banlist propia del test)
    pausa    : segundos a esperar antes del caso (para multi-turn dar tiempo a memoria)
"""
import json
import re
import sys
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "accept": "application/json"}
PHONE = "5491161461034"   # admin Lucas — la respuesta llega a su WhatsApp real

# ────────────────────────────────────────────────────────────────────────────
# BATERÍA BASE — casos multi-turn: el orden importa (comparten sesión = PHONE)
# ────────────────────────────────────────────────────────────────────────────
CASOS = [
    {"tag": "precio", "mensaje": "Hola! cuanto cuesta la primera consulta?",
     "espera": [r"50\.000"], "no_espera": [r"40\.000"]},
    {"tag": "contexto", "mensaje": "y eso incluye el presupuesto?",
     "espera": [r"(incluy|presupuesto|evaluaci)"], "pausa": 5},
    {"tag": "cuota", "mensaje": "ya estoy en tratamiento, cuanto se paga la cuota por mes?",
     "espera": [r"70\.000"], "no_espera": [r"50\.000"], "pausa": 5},
    {"tag": "alias", "mensaje": "pasame el alias para transferir",
     "espera": [r"dra\.raquel\.aurea"], "pausa": 5},
    {"tag": "kb", "mensaje": "mi hijo tiene el frenillo corto, eso lo atienden?",
     "espera": [r"(frenillo|consulta|evaluaci)"], "pausa": 5},
]


def api(path):
    req = urllib.request.Request(N8N + path, headers=H)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def enviar(mensaje, sim_id):
    body = {
        "event": "messages.upsert", "instance": "raquel",
        "data": {
            "key": {"remoteJid": f"{PHONE}@s.whatsapp.net", "fromMe": False, "id": sim_id},
            "pushName": "Lucas (SIM)",
            "message": {"conversation": mensaje},
            "messageType": "conversation",
            "messageTimestamp": int(time.time()),
        },
        "destination": f"{N8N}/webhook/evolution-v2",
        "date_time": datetime.now(timezone.utc).isoformat(),
        "sender": f"{PHONE}@s.whatsapp.net",
    }
    req = urllib.request.Request(f"{N8N}/webhook/evolution-v2", method="POST",
                                 headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


def respuesta_de(sim_id, last_id, timeout_s=60):
    """Espera la exec del SIM_ID y devuelve (status, respuesta_concatenada)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(3)
        for e in api(f"/api/v1/executions?workflowId={WF}&limit=10").get("data", []):
            if int(e["id"]) <= last_id:
                continue
            d = api(f"/api/v1/executions/{e['id']}?includeData=true")
            rd = (d.get("data", {}).get("resultData", {}) or {}).get("runData", {})
            ef = rd.get("Edit Fields - Extraer Datos", [])
            try:
                kid = ef[0]["data"]["main"][0][0]["json"].get("key_id", "")
            except (IndexError, KeyError, TypeError):
                continue
            if kid != sim_id:
                continue
            partes = []
            for run in rd.get("Split en Mensajes", []):
                for it in (run.get("data", {}).get("main", [[]])[0] or []):
                    partes.append(str(it.get("json", {}).get("message", "")))
            return d.get("status"), "\n".join(partes)
    return "timeout", ""


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else None
    casos = [c for c in CASOS if not filtro or filtro in c["tag"]]
    print(f"batería: {len(casos)} casos → respuestas reales al WhatsApp {PHONE}\n")
    resultados = []
    for c in casos:
        time.sleep(c.get("pausa", 0))
        sim_id = f"SIM_{uuid.uuid4().hex[:16].upper()}"
        last = api(f"/api/v1/executions?workflowId={WF}&limit=1").get("data", [])
        last_id = int(last[0]["id"]) if last else 0
        print(f"[{c['tag']}] → {c['mensaje']!r}")
        enviar(c["mensaje"], sim_id)
        status, resp = respuesta_de(sim_id, last_id)
        fallas = [rx for rx in c["espera"] if not re.search(rx, resp, re.I)]
        fallas += [f"NO debia aparecer: {rx}" for rx in c.get("no_espera", [])
                   if re.search(rx, resp, re.I)]
        ok = status == "success" and not fallas
        resultados.append((c["tag"], ok))
        print(f"  status={status} {'PASS ✅' if ok else 'FAIL ❌ ' + str(fallas)}")
        print(f"  bot: {resp[:200]}\n")
    print("=" * 60)
    for tag, ok in resultados:
        print(f"  {'PASS' if ok else 'FAIL'}  {tag}")
    total_ok = sum(1 for _, ok in resultados if ok)
    print(f"\n{total_ok}/{len(resultados)} PASS")
    return 0 if total_ok == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
