"""
Setup multi-confirm test REAL:
1. Buscar pacientes Lucas + Jana en Dentalink por phone
2. Buscar slots libres prox dias
3. Crear 2 citas
4. Insertar 2 filas en recordatorios_enviados (simular cron)
5. Quitar label humano + clear ratelimit
6. Simular "Confirmados"
7. Verificar flow multi-confirm
8. Cleanup: anular citas + borrar filas tabla
"""
import json
import sys
import time
import urllib.request
import urllib.parse
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env

N8N_BASE = require("N8N_BASE_URL").rstrip("/")
N8N_API = N8N_BASE + "/api/v1"
N8N_KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}
DT_CRED = "TwN6eBWsydjMdsCM"
REDIS_CRED = "kdtSKwGbN1xAZeUh"
PHONE = "5491161461034"

def run_temp(name, nodes, conns, hit_path, timeout=30, hit_body=None):
    """Crear workflow temporal, activarlo, hittear webhook, devolver response."""
    wf = {"name": name, "nodes": nodes, "connections": conns,
          "settings": {"executionOrder": "v1"}}
    req = urllib.request.Request(f"{N8N_API}/workflows", method="POST", headers=HEADERS,
                                  data=json.dumps(wf).encode())
    twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
    WID = twf["id"]
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/activate", method="POST", headers=HEADERS), timeout=20)
        time.sleep(2)
        hit = urllib.request.Request(f"{N8N_BASE}/webhook/{hit_path}",
                                      method="POST",
                                      headers={"Content-Type": "application/json"},
                                      data=(json.dumps(hit_body).encode() if hit_body else b"{}"))
        with urllib.request.urlopen(hit, timeout=timeout) as r:
            return r.read().decode()
    finally:
        try: urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/deactivate", method="POST", headers=HEADERS), timeout=15)
        except: pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}", method="DELETE", headers=HEADERS), timeout=15)

def dt_get(path):
    """GET a Dentalink API via temp workflow."""
    wh = f"dtget-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "options":{}},
         "id":"h","name":"Get","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Get","type":"main","index":0}]]}}
    return run_temp(f"dtget-{wh}", nodes, conns, wh)

def dt_post(path, body):
    """POST a Dentalink API via temp workflow."""
    wh = f"dtpost-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"POST",
                       "url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps(body),
                       "options":{}},
         "id":"h","name":"Post","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Post","type":"main","index":0}]]}}
    return run_temp(f"dtpost-{wh}", nodes, conns, wh)

def dt_put(path, body):
    """PUT a Dentalink (para anular cita o cambiar estado)."""
    wh = f"dtput-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"PUT",
                       "url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps(body),
                       "options":{}},
         "id":"h","name":"Put","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Put","type":"main","index":0}]]}}
    return run_temp(f"dtput-{wh}", nodes, conns, wh)

# ==========================================
# PASO 1: Buscar pacientes Lucas + Jana
# ==========================================
print("PASO 1: Buscar pacientes en Dentalink por phone")
print("=" * 60)
# Dentalink: buscar paciente por celular usando query parameter
body = dt_get(f"/pacientes?q={PHONE}")
try:
    data = json.loads(body)
    pacs = data.get("data", []) if isinstance(data, dict) else []
    print(f"Pacientes encontrados con celular={PHONE}: {len(pacs)}")
    for p in pacs:
        print(f"  id={p.get('id')} nombre={p.get('nombre')!r} apellidos={p.get('apellidos')!r} celular={p.get('celular')!r}")
except Exception as e:
    print(f"Error parsing: {e}")
    print(f"body: {body[:500]}")
