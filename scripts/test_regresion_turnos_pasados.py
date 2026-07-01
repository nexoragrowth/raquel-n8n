"""
Test de regresion: "Confirmar nunca actua sobre un turno con fecha pasada".

Raiz del bug (19/6, caso Delfina/Geronimo/Diego): los lookups de turnos del
flujo de confirmacion no tenian scope de fecha -> traian turnos pasados y el
bot los confirmaba (id_estado=18) + los recitaba.

Doble capa fixeada:
  A. Supabase PASO 0  -> consultar_recordatorios_abiertos  +fecha_turno=gte hoy   (fix Lucas/Claude)
  B. Dentalink legacy -> ver_turnos_paciente               q={"fecha":{"gte":hoy}} (fix Cogne)

Este test es READ-ONLY (no toca prod salvo crear/borrar un workflow throwaway
para usar la credencial de Dentalink). Valida:
  1. CONFIG: que los dos filtros sigan DESPLEGADOS en el v6 vivo (guardia anti-revert).
  2. BEHAVIOR-A: la query real de Supabase no devuelve filas con fecha pasada.
  3. BEHAVIOR-B: la expresion n8n real de Dentalink resuelve en runtime y filtra
     a futuro (paciente con turnos pasados + futuros -> solo futuros).

Exit code 0 = todo PASS. !=0 = alguna regresion.

Uso:  python scripts/test_regresion_turnos_pasados.py
"""
import sys, json, time, re, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
sys.path.insert(0, 'scripts')
from lib_env import env, require

WID = 'O155MqHgOSaNZ9ye'
DT_CRED = 'TwN6eBWsydjMdsCM'          # Header Auth account 3 (Dentalink)
TEST_PID = 110                         # Geronimo: tiene muchos turnos pasados + futuros
TODAY_ARG = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d')

BASE = require('N8N_BASE_URL').rstrip('/')
NKEY = require('N8N_API_KEY')
SB   = (env('SUPABASE_URL') or 'https://dchztroesbpwxxkfywwu.supabase.co').rstrip('/')
SK   = require('SUPABASE_SERVICE_ROLE_KEY')
NH = {'X-N8N-API-KEY': NKEY, 'Content-Type': 'application/json'}

results = []  # (name, passed, detail)
def check(name, passed, detail=''):
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ''))

def get_json(req):
    return json.load(urllib.request.urlopen(req, timeout=60))

print(f"== Test regresion turnos pasados (hoy ARG = {TODAY_ARG}) ==\n")

# ---------- 0. pull live workflow ----------
wf = get_json(urllib.request.Request(f'{BASE}/api/v1/workflows/{WID}', headers=NH))
nodes = {n['name']: n for n in wf['nodes']}

# ---------- 1. CONFIG (guardia anti-revert) ----------
print("[1] CONFIG desplegada (anti-revert):")
ct_url = nodes['consultar_recordatorios_abiertos']['parameters'].get('url', '')
check("Supabase: consultar tiene fecha_turno=gte", 'fecha_turno=gte' in ct_url)
check("Supabase: url es expresion n8n (= prefix)", ct_url.startswith('='))
vtp = nodes['ver_turnos_paciente']['parameters']
vtp_q = json.dumps(vtp.get('parametersQuery', {}), ensure_ascii=False)
check("Dentalink: ver_turnos sendQuery=true", vtp.get('sendQuery') is True)
check("Dentalink: ver_turnos q filtra fecha gte", ('fecha' in vtp_q and 'gte' in vtp_q))
sm_conf = nodes['Sub-Agent Confirmar']['parameters']['options']['systemMessage']
check("Prompt: regla anti-pasados (2da capa) presente", 'NUNCA CONFIRMES TURNOS PASADOS' in sm_conf)

# ---------- 2. BEHAVIOR-A: Supabase query real ----------
print("\n[2] BEHAVIOR Supabase (PASO 0) — query real read-only:")
# resolver la expresion {{ $now... }} a hoy ARG y pegar el endpoint EXACTO desplegado
resolved = re.sub(r'\{\{.*?\}\}', TODAY_ARG, ct_url[1:] if ct_url.startswith('=') else ct_url)
# quitar filtro de telefono no aplica (la url no lo tiene; el LLM lo agrega). Pegamos tal cual (todas las filas abiertas).
rows_filtered = get_json(urllib.request.Request(resolved, headers={'apikey': SK, 'Authorization': 'Bearer ' + SK}))
past_leak = [r for r in rows_filtered if r.get('fecha_turno') and r['fecha_turno'] < TODAY_ARG]
check("Supabase: query desplegada NO devuelve filas pasadas", len(past_leak) == 0,
      f"{len(rows_filtered)} filas, {len(past_leak)} pasadas")
# probar que el filtro hace algo: sin filtro existen pasadas
nofilter = re.sub(r'&fecha_turno=gte\.[^&]+', '', resolved)
rows_all = get_json(urllib.request.Request(nofilter, headers={'apikey': SK, 'Authorization': 'Bearer ' + SK}))
past_all = [r for r in rows_all if r.get('fecha_turno') and r['fecha_turno'] < TODAY_ARG]
check("Supabase: el filtro elimina pasadas reales (no es no-op)", len(past_all) > 0,
      f"sin filtro hay {len(past_all)} pasadas; con filtro 0")

# ---------- 3. BEHAVIOR-B: Dentalink expresion real (resuelve en runtime + filtra) ----------
print("\n[3] BEHAVIOR Dentalink (ver_turnos) — expresion n8n real via workflow throwaway:")
# tomamos la EXPRESION LITERAL desplegada (no la pre-resolvemos: probamos que n8n la resuelve)
expr_q = nodes['ver_turnos_paciente']['parameters']['parametersQuery']['values'][0]['value']
wh = f"regtest-{int(time.time())}"
tmp = {"name": f"TEMP-REGTEST-{int(time.time())}", "nodes": [
    {"parameters": {"httpMethod": "POST", "path": wh, "responseMode": "lastNode", "options": {}},
     "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
     "position": [240, 300], "webhookId": wh},
    {"parameters": {"url": f"https://api.dentalink.healthatom.com/api/v1/pacientes/{TEST_PID}/citas",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth", "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "q", "value": expr_q}]}, "options": {}},
     "id": "h", "name": "GetCitas", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [460, 300], "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
     "continueOnFail": True, "alwaysOutputData": True}],
    "connections": {"Webhook": {"main": [[{"node": "GetCitas", "type": "main", "index": 0}]]}},
    "settings": {"executionOrder": "v1"}}
twf = get_json(urllib.request.Request(f'{BASE}/api/v1/workflows', method='POST', headers=NH, data=json.dumps(tmp).encode()))
TID = twf['id']
try:
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/api/v1/workflows/{TID}/activate', method='POST', headers=NH), timeout=20)
    time.sleep(2)
    body = urllib.request.urlopen(urllib.request.Request(
        f'https://n8n.raquelrodriguez.com.ar/webhook/{wh}', method='POST',
        headers={'Content-Type': 'application/json'}, data=b'{}'), timeout=40).read().decode()
    r = json.loads(body)
    citas = r.get('data', r if isinstance(r, list) else [])
    fechas = sorted({c.get('fecha') for c in citas}) if isinstance(citas, list) else []
    past_dent = [f for f in fechas if f and f < TODAY_ARG]
    check("Dentalink: expresion resolvio y devolvio turnos", isinstance(citas, list) and len(citas) > 0,
          f"{len(citas)} citas, fechas={fechas}")
    check("Dentalink: NO devuelve turnos pasados", len(past_dent) == 0, f"pasadas={past_dent}")
finally:
    try: urllib.request.urlopen(urllib.request.Request(f'{BASE}/api/v1/workflows/{TID}/deactivate', method='POST', headers=NH), timeout=15)
    except Exception: pass
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/api/v1/workflows/{TID}', method='DELETE', headers=NH), timeout=15)
    print(f"  (throwaway wf {TID} eliminado)")

# ---------- summary ----------
failed = [r for r in results if not r[1]]
print(f"\n== RESULTADO: {len(results)-len(failed)}/{len(results)} PASS ==")
if failed:
    print("REGRESIONES:")
    for n, _, d in failed: print(f"  - {n} ({d})")
    sys.exit(1)
print("OK — el flujo de confirmacion no puede actuar sobre turnos pasados (ambas capas).")
