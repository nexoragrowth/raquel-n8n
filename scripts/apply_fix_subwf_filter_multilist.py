"""Fix: el match de Step 4 contaba el mensaje del bot 'tengo registradas a Jana y Lucas'
y eso hacia que AMBAS fichas matchearan. Filtrar esos mensajes del searchPool."""
import os, sys, json, requests
from dotenv import load_dotenv
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

wf = requests.get(f"{BASE}/api/v1/workflows/5cAWJxiWJ50hxEq3", headers=H, timeout=60).json()
n = next(x for x in wf["nodes"] if x["name"] == "Step 4: Identificar Turno + Decision")
js = n["parameters"]["jsCode"]

OLD = "  let chatHistoryText = '';\n  try {\n    const chMem = $('Step 0a: Read Chat Memory').all() || [];\n    chatHistoryText = chMem.map(it => {\n      const m = it.json && it.json.message ? it.json.message : {};\n      return (m.content || '').toString();\n    }).join('\\n').toLowerCase();\n  } catch(e) { chatHistoryText = ''; }"

NEW = "  let chatHistoryText = '';\n  try {\n    const chMem = $('Step 0a: Read Chat Memory').all() || [];\n    // FIX 2026-06-04: excluir mensajes del bot listando multiples pacientes\n    const isMultiList = (txt) => /tengo\\s+registrad[ao]s?\\s+a\\b|con\\s+este\\s+n[u\\u00fa]mero\\s+(figura|tengo|tiene)/i.test(txt);\n    chatHistoryText = chMem.map(it => {\n      const m = it.json && it.json.message ? it.json.message : {};\n      const c = (m.content || '').toString();\n      if (isMultiList(c)) return '';\n      return c;\n    }).filter(Boolean).join('\\n').toLowerCase();\n  } catch(e) { chatHistoryText = ''; }"

if OLD not in js:
    print("!! anchor no match"); sys.exit(2)

n["parameters"]["jsCode"] = js.replace(OLD, NEW)
allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings, "staticData": wf.get("staticData")}
r = requests.put(f"{BASE}/api/v1/workflows/5cAWJxiWJ50hxEq3", headers=H, json=body, timeout=40)
print(f"PUT {r.status_code}")
