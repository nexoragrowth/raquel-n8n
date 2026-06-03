"""Find n8n workflow listening on webhook path 'notify-grupo'."""
import sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require  # noqa: E402

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

r = requests.get(f"{N8N}/api/v1/workflows?limit=100", headers=H, timeout=30)
r.raise_for_status()
items = r.json().get("data", [])
print(f"Total workflows: {len(items)}")

# Now fetch each and look for webhook nodes with path notify-grupo
for it in items:
    wid = it["id"]
    r2 = requests.get(f"{N8N}/api/v1/workflows/{wid}", headers=H, timeout=30)
    if not r2.ok:
        continue
    wf = r2.json()
    for n in wf.get("nodes", []):
        if n.get("type") == "n8n-nodes-base.webhook":
            path = n.get("parameters", {}).get("path", "")
            if "notify-grupo" in path or "notify_grupo" in path:
                print(f"FOUND: workflow '{wf.get('name')}' (id={wid}, active={wf.get('active')}) — node '{n['name']}' path='{path}'")
                # Print other key nodes
                for n2 in wf.get("nodes", []):
                    print(f"  - {n2['name']}  [{n2.get('type')}]")
