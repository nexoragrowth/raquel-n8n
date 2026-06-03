"""
Mining del shadow mode: extrae ejecuciones reales de pacientes en los ultimos N dias,
filtra tests sinteticos, agrupa por sub-agent + tools, genera reporte MD.

Uso:
    python scripts/mine_shadow.py [--days 7] [--limit 500]

Output:
    tests/shadow_mining_YYYYMMDD.json  (data cruda)
    tests/shadow_mining_YYYYMMDD.md    (reporte legible)

NO modifica nada en n8n. Solo GET sobre /executions.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
SUB_AGENTS = [
    "Sub-Agent Confirmar", "Sub-Agent Cancelar", "Sub-Agent Agendar",
    "Sub-Agent Urgencia", "Sub-Agent General",
]
TOOL_NAMES = [
    "ver_turnos_paciente", "confirmar_turno", "cancelar_turno", "buscar_horarios",
    "reservar_turno", "buscar_paciente_dentalink", "crear_paciente_dentalink",
    "escalar_a_secretaria", "buscar_conocimiento", "ver_profesionales",
]
# Tests sinteticos del test_100 usan estos prefijos en key_id y rangos de phone.
TEST_KEY_PREFIX = "T100_"
TEST_PHONE_PREFIX = "549120000"


def get_api_key():
    k = os.environ.get("N8N_API_KEY")
    if k:
        return k
    # Fallback: leer del script de Lucas (no commiteado, solo en disco).
    fallback = Path("C:/Users/Lucas/.claude/n8n_backups/test_100_pre_prod.py")
    if fallback.exists():
        m = re.search(r'API_KEY\s*=\s*"([^"]+)"', fallback.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    sys.exit("ERROR: N8N_API_KEY no encontrada (env var ni fallback)")


API_KEY = get_api_key()


def http_get(path):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"X-N8N-API-KEY": API_KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def list_executions(limit_pages=10, page_size=100):
    """Pagina executions hasta limit_pages."""
    out = []
    cursor = None
    for _ in range(limit_pages):
        path = f"/executions?workflowId={WF_ID}&limit={page_size}"
        if cursor:
            path += f"&cursor={cursor}"
        try:
            data = http_get(path)
        except urllib.error.HTTPError as e:
            print(f"HTTPError {e.code} listing executions: {e.read().decode()[:200]}")
            break
        execs = data.get("data", [])
        out.extend(execs)
        cursor = data.get("nextCursor")
        if not cursor or not execs:
            break
    return out


def parse_exec(exec_id):
    """Extrae payload util de una execution con includeData=true."""
    try:
        d = http_get(f"/executions/{exec_id}?includeData=true")
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    runs = d.get("data", {}).get("resultData", {}).get("runData", {}) or {}

    # Extraer datos del Edit Fields
    edit = runs.get("Edit Fields - Extraer Datos", [])
    msg_in = None
    phone = None
    key_id = None
    push_name = None
    from_me = None
    is_group = None
    if edit:
        try:
            j = edit[0]["data"]["main"][0][0]["json"]
            msg_in = j.get("texto_usuario") or j.get("message") or j.get("text")
            phone = j.get("phone") or j.get("from")
            key_id = j.get("key_id") or j.get("messageId")
            push_name = j.get("pushName")
            from_me = j.get("fromMe")
            is_group = j.get("is_group")
        except Exception:
            pass

    # Pre-filtro reason
    pf_skip = None
    pf_reason = None
    if "Pre-filtro Cierre" in runs:
        try:
            j = runs["Pre-filtro Cierre"][0]["data"]["main"][0][0]["json"]
            pf_skip = j.get("skip")
            pf_reason = j.get("reason")
        except Exception:
            pass

    # Sub-agent + output
    sub_run = None
    output = ""
    for s in SUB_AGENTS:
        if s in runs:
            try:
                output = runs[s][0]["data"]["main"][0][0]["json"].get("output", "")
                sub_run = s
                break
            except Exception:
                pass

    # Tools invocadas
    tools_called = [t for t in TOOL_NAMES if t in runs]

    # Output final post-Split (lo que SE HABRIA enviado al paciente)
    split = runs.get("Split en Mensajes", [])
    final = ""
    if split:
        try:
            final = " || ".join(
                it["json"].get("message", "") for it in split[0]["data"]["main"][0]
            )
        except Exception:
            pass

    # Banlist (si bloqueo algo)
    banlist_blocked = None
    if "Banlist Validator" in runs:
        try:
            j = runs["Banlist Validator"][0]["data"]["main"][0][0]["json"]
            banlist_blocked = j.get("blocked") or j.get("violations")
        except Exception:
            pass

    # Router classification (si existe)
    router_intent = None
    if "Router" in runs:
        try:
            j = runs["Router"][0]["data"]["main"][0][0]["json"]
            router_intent = j.get("intent") or j.get("output") or j.get("classification")
        except Exception:
            pass

    return {
        "id": exec_id,
        "msg_in": (msg_in or "")[:300],
        "phone": phone,
        "key_id": key_id,
        "push_name": push_name,
        "from_me": from_me,
        "is_group": is_group,
        "pf_skip": pf_skip,
        "pf_reason": pf_reason,
        "router_intent": router_intent,
        "sub": sub_run,
        "tools": tools_called,
        "agent_output": (output or "")[:500],
        "final_sent": (final or "")[:500],
        "banlist_blocked": banlist_blocked,
        "nodes_run": list(runs.keys()),
    }


def is_test_exec(parsed):
    if not parsed:
        return True
    if parsed.get("error"):
        return True
    kid = parsed.get("key_id") or ""
    if kid.startswith(TEST_KEY_PREFIX):
        return True
    phone = str(parsed.get("phone") or "")
    if phone.startswith(TEST_PHONE_PREFIX):
        return True
    return False


def categorize(p):
    """Categoriza un caso real para el reporte."""
    sub = p.get("sub") or ""
    tools = p.get("tools") or []
    pf = p.get("pf_reason") or ""

    if p.get("from_me"):
        return "outbound_clinic"
    if p.get("is_group"):
        return "group_msg"
    if p.get("pf_skip"):
        return f"prefilter:{pf}"
    if "Confirmar" in sub:
        if "confirmar_turno" in tools:
            return "confirmar_con_tool"
        return "confirmar_sin_tool"
    if "Cancelar" in sub:
        if "cancelar_turno" in tools:
            return "cancelar_con_tool"
        return "cancelar_sin_tool"
    if "Agendar" in sub:
        if "reservar_turno" in tools:
            return "agendar_con_reserva"
        if "buscar_horarios" in tools:
            return "agendar_busqueda"
        return "agendar_pregunta"
    if "Urgencia" in sub:
        return "urgencia"
    if "General" in sub:
        if "escalar_a_secretaria" in tools:
            return "general_escalado"
        return "general_otro"
    if sub:
        return f"sub:{sub}"
    return "sin_sub_agent"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--limit", type=int, default=500, help="max executions to inspect")
    ap.add_argument("--out-dir", default="tests")
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"Cutoff: {cutoff.isoformat()}")

    print(f"Listando executions del workflow {WF_ID}...")
    pages = max(1, args.limit // 100)
    all_execs = list_executions(limit_pages=pages, page_size=100)
    print(f"  {len(all_execs)} executions listadas")

    # Filtrar por fecha
    in_window = []
    for e in all_execs:
        started = e.get("startedAt") or e.get("createdAt")
        if not started:
            continue
        try:
            ts = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except Exception:
            continue
        if ts >= cutoff:
            in_window.append((ts, e))
    in_window.sort(key=lambda x: x[0])
    print(f"  {len(in_window)} dentro de la ventana de {args.days}d")

    print(f"Descargando runData de cada execution (puede tardar)...")
    parsed_all = []
    t0 = time.time()
    for i, (ts, e) in enumerate(in_window, 1):
        if i % 25 == 0:
            print(f"  [{i}/{len(in_window)}] {int(time.time()-t0)}s")
        p = parse_exec(e["id"])
        if not p:
            continue
        p["started_at"] = ts.isoformat()
        p["status"] = e.get("status")
        p["mode"] = e.get("mode")
        parsed_all.append(p)

    # Particion test vs real
    reals = [p for p in parsed_all if not is_test_exec(p)]
    tests = [p for p in parsed_all if is_test_exec(p) and not p.get("error")]
    errs = [p for p in parsed_all if p.get("error")]
    print(f"  total parsed: {len(parsed_all)}  reals: {len(reals)}  tests: {len(tests)}  errors: {len(errs)}")

    # Categorizar reals
    cats = defaultdict(list)
    for p in reals:
        cats[categorize(p)].append(p)

    # Sumarios
    by_cat = {k: len(v) for k, v in cats.items()}

    # Guardar JSON + MD
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = Path(args.out_dir) / f"shadow_mining_{stamp}.json"
    md_path = Path(args.out_dir) / f"shadow_mining_{stamp}.md"

    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "window_days": args.days,
                "total_executions": len(parsed_all),
                "reals": len(reals),
                "tests": len(tests),
                "errors": len(errs),
                "by_category": by_cat,
                "real_executions": reals,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON: {json_path}")

    # Reporte MD
    md = []
    md.append(f"# Shadow mining — ventana {args.days}d")
    md.append(f"_Generado: {datetime.now().isoformat()}_\n")
    md.append(f"**Total executions parseadas:** {len(parsed_all)}")
    md.append(f"**Reales (pacientes):** {len(reals)}")
    md.append(f"**Tests sinteticos descartados:** {len(tests)}")
    md.append(f"**Errores parseo:** {len(errs)}\n")
    md.append("## Categorias\n")
    md.append("| Categoria | Cuenta |")
    md.append("|---|---:|")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        md.append(f"| `{cat}` | {n} |")
    md.append("")

    # Detalle por categoria (top 20 ejemplos por cat)
    md.append("## Detalle por categoria\n")
    for cat in sorted(cats.keys(), key=lambda c: -len(cats[c])):
        rows = cats[cat]
        md.append(f"### `{cat}` ({len(rows)})\n")
        for r in rows[:20]:
            md.append(f"- **{r.get('started_at','?')[:19]}** `{r.get('phone','?')}` ({r.get('push_name','?')})")
            md.append(f"  - IN:  `{r.get('msg_in','')[:160]}`")
            if r.get("tools"):
                md.append(f"  - tools: {r.get('tools')}")
            if r.get("agent_output"):
                md.append(f"  - OUT (agent): `{r.get('agent_output','')[:200]}`")
            if r.get("final_sent"):
                md.append(f"  - OUT (final, NO enviado en shadow): `{r.get('final_sent','')[:200]}`")
            if r.get("banlist_blocked"):
                md.append(f"  - banlist: `{r.get('banlist_blocked')}`")
            md.append("")
        if len(rows) > 20:
            md.append(f"_(+{len(rows)-20} mas)_\n")

    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"MD:   {md_path}")

    # Resumen consola
    print(f"\nResumen por categoria:")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat:35s} {n:>4}")


if __name__ == "__main__":
    main()
