"""
Auto-layout del workflow v6 (O155MqHgOSaNZ9ye).

Reorganiza los 100+ nodos en swim lanes left-to-right, una columna por sticky
note (ENTRADA -> BUFFER -> MULTIMEDIA -> AI AGENT -> SALIDA). Dentro de cada
columna, los nodos se ordenan topologicamente (depth-based) usando solo edges
main; los sub-nodos de IA (lmChat*, memory*, tool*, embeddings*, vectorStore*)
se posicionan debajo de su agent padre.

NO modifica connections, ni parameters, ni nada de logica. Solo `position` de
nodos y `width/height/position` de sticky notes.

Uso:
  N8N_API_KEY=... python scripts/apply_layout_v6.py [--dry-run]
"""
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
DRY_RUN = "--dry-run" in sys.argv

if not API_KEY:
    print("ERROR: set N8N_API_KEY env var")
    sys.exit(1)

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}

# Layout constants
COL_WIDTH = 260
ROW_HEIGHT = 140
GROUP_GAP = 120         # horizontal gap entre sticky notes
AI_CHILD_OFFSET = 200   # cuanto baja un AI child debajo de su agent
AI_CHILD_X_OFFSET = 0   # mismo X que el agent padre
STICKY_PAD_X = 40
STICKY_PAD_Y = 80
BASE_Y = 0

# Tipos de nodos "AI children" (van debajo de su agent padre, no en el flow main)
AI_CHILD_TYPES = {
    "@n8n/n8n-nodes-langchain.lmChatOpenAi",
    "@n8n/n8n-nodes-langchain.lmChatGroq",
    "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "@n8n/n8n-nodes-langchain.memoryPostgresChat",
    "@n8n/n8n-nodes-langchain.memoryBufferWindow",
    "@n8n/n8n-nodes-langchain.embeddingsOpenAi",
    "@n8n/n8n-nodes-langchain.toolHttpRequest",
    "@n8n/n8n-nodes-langchain.toolCode",
    "@n8n/n8n-nodes-langchain.vectorStoreSupabase",
}

# Orden de los swim lanes left-to-right
LANE_ORDER = [
    "Sticky Note - Entrada",
    "Sticky Note - Buffer",
    "Sticky Note - Multimedia",
    "Sticky Note - AI Agent",
    "Sticky Note - Salida",
]


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={
            "X-N8N-API-KEY": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def bbox(sticky):
    x, y = sticky["position"]
    w = sticky["parameters"].get("width", 240)
    h = sticky["parameters"].get("height", 240)
    return (x, y, x + w, y + h)


def heuristic_lane(name):
    """Asignar nodo a una sticky por nombre cuando bbox no alcanza."""
    n = name.lower()
    if any(k in n for k in ["webhook", "edit fields", "filtrar", "kill-switch",
                              "webhook validator", "bot enabled", "bot disabled",
                              "es comando admin", "build redis cmd", "es off u on",
                              "redis set bot", "http send admin", "redis get bot",
                              "redis get dentalink", "dentalink up", "rate limit",
                              "es fromme", "build fromme", "postgres - save fromme",
                              "chatwoot", "verificar label", "bot activo",
                              "humano atendiendo", "check session age",
                              "handle stale", "clear old memory", "es primer"]):
        return "Sticky Note - Entrada"
    if "buffer" in n or "soy el ultimo" in n or "preparar mensaje final" in n or "descartar (no soy" in n:
        return "Sticky Note - Buffer"
    if any(k in n for k in ["switch - tipo mensaje", "analizar imagen", "obtener media",
                              "convert to file", "transcribir audio", "obtener imagen",
                              "convert imagen", "set marker", "set passthrough",
                              "merge multimedia"]):
        return "Sticky Note - Multimedia"
    if any(k in n for k in ["tiene respuesta", "descartar [no_reply]", "evolution - typing",
                              "delay humano", "split en mensajes", "enviar mensaje",
                              "guardar msg"]):
        return "Sticky Note - Salida"
    # default: AI AGENT (catch-all para sub-agents, tools, formatting, etc.)
    return "Sticky Note - AI Agent"


def main():
    print(f"GET workflow {WF_ID}...")
    status, wf = http("GET", f"/workflows/{WF_ID}")
    print(f"  status={status} name={wf['name']!r} active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_LAYOUT_API_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    nodes = wf["nodes"]
    connections = wf["connections"]
    stickies = [n for n in nodes if n["type"] == "n8n-nodes-base.stickyNote"]
    op_nodes = [n for n in nodes if n["type"] != "n8n-nodes-base.stickyNote"]

    sticky_by_name = {s["name"]: s for s in stickies}
    for sname in LANE_ORDER:
        if sname not in sticky_by_name:
            print(f"WARN: sticky {sname!r} not found")

    # 1. Asignar cada nodo a un sticky (por bbox original; fallback heuristic)
    sticky_bboxes = {s["name"]: bbox(s) for s in stickies}
    assigned = {}
    for n in op_nodes:
        nx, ny = n["position"]
        found = None
        for sname, (x1, y1, x2, y2) in sticky_bboxes.items():
            if x1 <= nx <= x2 and y1 <= ny <= y2:
                found = sname
                break
        if found is None:
            found = heuristic_lane(n["name"])
        assigned[n["name"]] = found

    # Stats
    from collections import Counter
    print("\n=== Assignment ===")
    for sname, count in Counter(assigned.values()).items():
        print(f"  {sname:<35} {count}")

    # 2. Identificar AI children y sus padres (via connections reversas)
    # connections[srcNode][outputType][branchIdx] = [{node: tgt, ...}]
    # AI children: tienen outputs ai_languageModel/ai_memory/ai_tool/ai_embedding apuntando al agent
    ai_parent = {}  # child_name -> parent_name
    for src, conns in connections.items():
        for output_type, branches in conns.items():
            if not output_type.startswith("ai_"):
                continue
            for branch in branches or []:
                for edge in branch or []:
                    tgt = edge["node"]
                    # src es el child, tgt es el parent
                    ai_parent[src] = tgt

    print(f"\n  AI children detected: {len(ai_parent)}")

    # 3. Construir DAG con solo edges MAIN para depth
    main_succ = defaultdict(set)
    main_pred = defaultdict(set)
    for src, conns in connections.items():
        for output_type, branches in conns.items():
            if output_type != "main":
                continue
            for branch in branches or []:
                for edge in branch or []:
                    tgt = edge["node"]
                    main_succ[src].add(tgt)
                    main_pred[tgt].add(src)

    # 4. Depth LOCAL por lane (longest path usando solo edges intra-lane)
    op_names = {n["name"] for n in op_nodes}
    flow_names = op_names - set(ai_parent.keys())  # AI children no participan
    lane_flow_nodes = defaultdict(list)
    for name in flow_names:
        lane = assigned.get(name)
        if lane:
            lane_flow_nodes[lane].append(name)

    depths = {}
    lane_columns = {}
    lane_width = {}
    for lane in LANE_ORDER:
        nodes_in_lane = set(lane_flow_nodes.get(lane, []))
        if not nodes_in_lane:
            lane_columns[lane] = {}
            lane_width[lane] = COL_WIDTH
            continue

        local_depths = {}

        def local_depth(name, stack=None):
            if name in local_depths:
                return local_depths[name]
            if stack is None:
                stack = set()
            if name in stack:
                local_depths[name] = 0
                return 0
            stack.add(name)
            preds = [p for p in main_pred[name] if p in nodes_in_lane]
            d = 0 if not preds else 1 + max(local_depth(p, stack) for p in preds)
            local_depths[name] = d
            stack.discard(name)
            return d

        for name in nodes_in_lane:
            local_depth(name)
        depths.update(local_depths)

        cols = defaultdict(list)
        for name in nodes_in_lane:
            cols[local_depths[name]].append(name)
        lane_columns[lane] = dict(cols)
        max_col = max(cols.keys()) if cols else 0
        lane_width[lane] = (max_col + 1) * COL_WIDTH

    # 6. Asignar X start de cada lane
    lane_x_start = {}
    cursor = 0
    for lane in LANE_ORDER:
        lane_x_start[lane] = cursor
        cursor += lane_width[lane] + GROUP_GAP

    total_width = cursor - GROUP_GAP

    # 7. Posicionar nodos main flow
    new_positions = {}
    for lane in LANE_ORDER:
        cols = lane_columns[lane]
        x0 = lane_x_start[lane]
        for col_idx, names in sorted(cols.items()):
            # ordenar nodos dentro de la columna: estables por nombre
            names_sorted = sorted(names)
            for row_idx, name in enumerate(names_sorted):
                x = x0 + col_idx * COL_WIDTH
                y = BASE_Y + row_idx * ROW_HEIGHT
                new_positions[name] = [x, y]

    # 8. Posicionar AI children debajo de sus padres
    # Si un parent tiene varios children del mismo tipo, los apilamos
    children_by_parent = defaultdict(list)
    for child, parent in ai_parent.items():
        children_by_parent[parent].append(child)

    for parent, children in children_by_parent.items():
        if parent not in new_positions:
            continue
        px, py = new_positions[parent]
        # Children abajo del padre, ordenados por tipo + nombre
        children_sorted = sorted(children)
        for i, child in enumerate(children_sorted):
            child_x = px + AI_CHILD_X_OFFSET + (i // 3) * COL_WIDTH
            child_y = py + AI_CHILD_OFFSET + (i % 3) * (ROW_HEIGHT - 20)
            new_positions[child] = [child_x, child_y]

    # 9. Aplicar nuevas posiciones a nodos
    moved = 0
    for n in op_nodes:
        if n["name"] in new_positions:
            old = n["position"]
            new = new_positions[n["name"]]
            if old != new:
                n["position"] = new
                moved += 1
    print(f"\n  Moved {moved}/{len(op_nodes)} nodes")

    # 10. Reposicionar y redimensionar sticky notes
    for lane in LANE_ORDER:
        s = sticky_by_name.get(lane)
        if not s:
            continue
        # Calcular bbox de los nodos asignados a este lane
        lane_nodes = [n for n in op_nodes if assigned.get(n["name"]) == lane]
        if not lane_nodes:
            continue
        xs = [n["position"][0] for n in lane_nodes]
        ys = [n["position"][1] for n in lane_nodes]
        min_x = min(xs) - STICKY_PAD_X
        max_x = max(xs) + COL_WIDTH - 30 + STICKY_PAD_X
        min_y = min(ys) - STICKY_PAD_Y
        max_y = max(ys) + ROW_HEIGHT - 30 + STICKY_PAD_Y
        s["position"] = [min_x, min_y]
        s["parameters"]["width"] = max_x - min_x
        s["parameters"]["height"] = max_y - min_y

    if DRY_RUN:
        print("\nDRY RUN: not PUTting. Lane summary:")
        for lane in LANE_ORDER:
            print(f"  {lane}: x_start={lane_x_start[lane]} width={lane_width[lane]}")
        out = f"workflows/history/v6_LAYOUT_DRY_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"  preview JSON -> {out}")
        return

    # 11. PUT
    settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    print(f"\nPUT workflow {WF_ID}...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  status={status}")

    # 12. Verify
    status2, wf2 = http("GET", f"/workflows/{WF_ID}")
    sample = wf2["nodes"][0]
    print(f"  verified: active={wf2['active']} nodes={len(wf2['nodes'])} sample={sample['name']!r}@{sample['position']}")
    post_path = f"workflows/history/v6_POST_LAYOUT_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post-layout snapshot -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
