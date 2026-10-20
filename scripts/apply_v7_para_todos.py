# -*- coding: utf-8 -*-
"""
apply_v7_para_todos.py — 2026-10-19 · el v6 (O155MqHgOSaNZ9ye) aprende a leer una llave GLOBAL de Redis (`v7:global`) además de la marca por
número (`v7:tel:<tel>`). Con `v7:global = 'vivo'` TODOS los pacientes los atiende el cerebro v7 (orquestador + especialistas), no solo los
números marcados con flag_v7.py. Pedido de Lucas del 19/10 (multi-pedidos que el v6 no resuelve: escalación 375).

QUÉ CAMBIA (y nada más):
  1. Nodo nuevo "V7: Redis GET global" (lee `v7:global` → propiedad v7_global; misma credencial que "V7: Redis GET modo", alwaysOutputData,
     onError continueRegularOutput: si Redis falla, vale '' y todo queda como hoy).
  2. Cableado: "V7: Redis GET modo" → "V7: Redis GET global" → "V7: ¿Vivo?" (antes GET modo → ¿Vivo?).
  3. La condición de "V7: ¿Vivo?" y la de "V7: ¿Ruta v7?" pasan de  tel === 'vivo'  a
         tel === 'vivo'  ||  (global === 'vivo' && tel !== 'off')
     o sea: la marca por número sigue mandando; con la global prendida entra todo el mundo, salvo un número con `v7:tel:<tel> = 'off'`
     (forma de dejar a alguien puntual en el v6). "V7: ¿Ruta v7?" conserva el `&& !$('V7: Derivar a Triaje').isExecuted` (sin bucle).

SIN LA LLAVE PRENDIDA NO CAMBIA NADA: `v7:global` no existe → '' → misma decisión que hoy para cada número. Se prende/apaga con
scripts/v7_global.py --on | --off | --estado (sin PUT; vuelta al v6 para todos desde el próximo mensaje).

USO:  python scripts/apply_v7_para_todos.py               # simulación: diff + 12 casos de la regla en node + chequeos de grafo
      python scripts/apply_v7_para_todos.py --apply       # check_triaje → re-GET mismo versionId → backup PRE → PUT → GET → backup POST → verificación
      python scripts/apply_v7_para_todos.py --revertir --apply   # vuelve al último backup PRE de este cambio
"""
import argparse, copy, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api
from check_triaje_grafo import chequear_grafo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
V6 = "O155MqHgOSaNZ9ye"
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
               "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

GM, GG, VIVO, RUTA = "V7: Redis GET modo", "V7: Redis GET global", "V7: ¿Vivo?", "V7: ¿Ruta v7?"
TEL = "($('V7: Redis GET modo').isExecuted ? ($('V7: Redis GET modo').first().json.v7_modo || '') : '')"
GLOB = "($('V7: Redis GET global').isExecuted ? ($('V7: Redis GET global').first().json.v7_global || '') : '')"
REGLA = f"({TEL} === 'vivo' || ({GLOB} === 'vivo' && {TEL} !== 'off'))"
EXPR_VIVO = "={{ " + REGLA + " }}"
EXPR_RUTA = "={{ " + REGLA + " && !$('V7: Derivar a Triaje').isExecuted }}"
VIEJO_VIVO = "($json.v7_modo || '') === 'vivo'"
VIEJO_RUTA = "=== 'vivo' && !$('V7: Derivar a Triaje').isExecuted"


def nodo(w, nombre):
    return next((n for n in w["nodes"] if n["name"] == nombre), None)


def salidas(w, nombre):
    return [[c["node"] for c in (rama or [])] for rama in (w["connections"].get(nombre) or {}).get("main", [])]


def construir(w):
    """Devuelve una copia del v6 con el cambio. Aborta (SystemExit) si el v6 vivo no tiene la forma esperada."""
    if nodo(w, GG):
        raise SystemExit(f"«{GG}» ya existe: el cambio ya está aplicado.")
    gm, vivo, ruta = nodo(w, GM), nodo(w, VIVO), nodo(w, RUTA)
    if not (gm and vivo and ruta):
        raise SystemExit("Faltan nodos del v7 en el v6 (GET modo / ¿Vivo? / ¿Ruta v7?): no toco nada.")
    if salidas(w, GM) != [[VIVO]]:
        raise SystemExit(f"«{GM}» no sale solo a «{VIVO}» ({salidas(w, GM)}): no toco nada.")
    for n, viejo in ((vivo, VIEJO_VIVO), (ruta, VIEJO_RUTA)):
        conds = n["parameters"]["conditions"]["conditions"]
        if len(conds) != 1 or viejo not in conds[0]["leftValue"]:
            raise SystemExit(f"La condición de «{n['name']}» no es la esperada: no toco nada.")
    nuevo = copy.deepcopy(w)
    gm2 = nodo(nuevo, GM)
    x, y = gm2.get("position", [0, 0])
    nuevo["nodes"].append({
        "parameters": {"operation": "get", "propertyName": "v7_global", "key": "v7:global", "keyType": "string", "options": {}},
        "id": "v7-redis-get-global", "name": GG, "type": "n8n-nodes-base.redis", "typeVersion": 1, "position": [x + 110, y + 160],
        "credentials": copy.deepcopy(gm2["credentials"]), "alwaysOutputData": True, "onError": "continueRegularOutput"})
    nuevo["connections"][GM] = {"main": [[{"node": GG, "type": "main", "index": 0}]]}
    nuevo["connections"][GG] = {"main": [[{"node": VIVO, "type": "main", "index": 0}]]}
    nodo(nuevo, VIVO)["parameters"]["conditions"]["conditions"][0]["leftValue"] = EXPR_VIVO
    nodo(nuevo, RUTA)["parameters"]["conditions"]["conditions"][0]["leftValue"] = EXPR_RUTA
    return nuevo


def probar_regla():
    """Evalúa EXPR_VIVO y EXPR_RUTA en node con un $() simulado. True si los 12 casos dan lo esperado."""
    casos = []
    for tel in ("", "vivo", "off"):
        for glob in ("", "vivo", "off", None):           # None = el GET global no corrió (o falló sin salida)
            esperado = tel == "vivo" or (glob == "vivo" and tel != "off")
            casos.append({"tel": tel, "glob": glob, "derivado": False, "vivo": esperado, "ruta": esperado})
    casos.append({"tel": "vivo", "glob": "vivo", "derivado": True, "vivo": True, "ruta": False})   # ya pasó por V7: Derivar a Triaje
    casos.append({"tel": "", "glob": "vivo", "derivado": True, "vivo": True, "ruta": False})
    js = """
const casos = %s; const VIVO = %s; const RUTA = %s; let mal = 0;
for (const c of casos) {
  const $ = (n) => {
    if (n === 'V7: Redis GET modo') return { isExecuted: true, first: () => ({ json: { v7_modo: c.tel } }) };
    if (n === 'V7: Redis GET global') return c.glob === null ? { isExecuted: false, first: () => { throw new Error('no corrió'); } }
                                                            : { isExecuted: true, first: () => ({ json: { v7_global: c.glob } }) };
    if (n === 'V7: Derivar a Triaje') return { isExecuted: c.derivado };
    throw new Error('nodo inesperado ' + n);
  };
  const ev = (e) => Function('$', 'return (' + e.slice(4, -3) + ');')($);
  const v = ev(VIVO), r = ev(RUTA);
  const ok = v === c.vivo && r === c.ruta && typeof v === 'boolean' && typeof r === 'boolean';
  if (!ok) mal++;
  console.log((ok ? 'ok  ' : 'MAL ') + JSON.stringify(c) + ' -> vivo=' + v + ' ruta=' + r);
}
process.exit(mal ? 1 : 0);
""" % (json.dumps(casos), json.dumps(EXPR_VIVO), json.dumps(EXPR_RUTA))
    p = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8")
    print(p.stdout.rstrip() or p.stderr.rstrip())
    return p.returncode == 0


def chequear(pre, post):
    r = []
    def chk(ok, t): r.append((bool(ok), t))
    chk(len(post["nodes"]) == len(pre["nodes"]) + 1, f"un nodo más ({len(pre['nodes'])} → {len(post['nodes'])})")
    chk(salidas(post, GM) == [[GG]] and salidas(post, GG) == [[VIVO]], "GET modo → GET global → ¿Vivo?")
    chk(salidas(post, VIVO) == salidas(pre, VIVO) and salidas(post, RUTA) == salidas(pre, RUTA), "salidas de ¿Vivo? y ¿Ruta v7? sin cambios")
    chk(nodo(post, VIVO)["parameters"]["conditions"]["conditions"][0]["leftValue"] == EXPR_VIVO, "condición nueva en ¿Vivo?")
    chk(nodo(post, RUTA)["parameters"]["conditions"]["conditions"][0]["leftValue"] == EXPR_RUTA, "condición nueva en ¿Ruta v7?")
    gg = nodo(post, GG) or {}
    chk(gg.get("parameters", {}).get("key") == "v7:global" and gg.get("credentials") == nodo(post, GM).get("credentials")
        and gg.get("alwaysOutputData") is True and gg.get("onError") == "continueRegularOutput", "GET global: clave fija, misma credencial, no corta el flujo")
    otros = lambda w: {n["name"]: json.dumps([n.get("type"), n.get("parameters"), n.get("credentials"), n.get("disabled")], sort_keys=True)
                       for n in w["nodes"] if n["name"] not in (VIVO, RUTA, GG)}
    chk(otros(pre) == otros(post), "el resto de los nodos, idéntico")
    cpre = {k: v for k, v in pre["connections"].items() if k != GM}
    cpost = {k: v for k, v in post["connections"].items() if k not in (GM, GG)}
    chk(cpre == cpost, "el resto de las conexiones, idéntico")
    chk({n["name"]: n.get("webhookId") for n in pre["nodes"] if n.get("webhookId")} == {n["name"]: n.get("webhookId") for n in post["nodes"] if n.get("webhookId")}
        and any(n.get("webhookId") == "evo-webhook-v2" for n in post["nodes"]), "webhookIds conservados (evo-webhook-v2 incluido)")
    for ok, t in chequear_grafo(post):
        chk(ok, "check_triaje (grafo): " + t)
    return r


def resumen(r):
    for ok, t in r:
        print(("  ok   " if ok else "  MAL  ") + t)
    return all(ok for ok, _ in r)


def put(w):
    api(f"/workflows/{V6}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
                                     "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK},
                                     "staticData": w.get("staticData")})


def revertir(aplicar):
    pres = sorted(HIST.glob(f"{V6}_PRE_v7_para_todos_*.json"))
    if not pres:
        raise SystemExit("No hay backup PRE de este cambio.")
    pre = json.loads(pres[-1].read_text(encoding="utf-8"))
    print(f"Backup a restaurar: {pres[-1].name} · {len(pre['nodes'])} nodos")
    if not aplicar:
        print("[SIMULACIÓN] Para revertir: --revertir --apply"); return
    vivo = api(f"/workflows/{V6}")
    if not nodo(vivo, GG):
        raise SystemExit("El v6 vivo no tiene el cambio: nada que revertir.")
    ts = int(time.time())
    (HIST / f"{V6}_PRE_revertir_v7_para_todos_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
    put(pre)
    post = api(f"/workflows/{V6}")
    ok = not nodo(post, GG) and post.get("active") is True and any(n.get("webhookId") == "evo-webhook-v2" for n in post["nodes"])
    print(("OK revertido" if ok else "ATENCIÓN") + f": versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    if a.revertir:
        return revertir(a.apply)
    w = api(f"/workflows/{V6}")
    print(f"v6 vivo: versionId {w.get('versionId')} · {len(w['nodes'])} nodos · activo {w.get('active')}")
    nuevo = construir(w)
    print(f"\n«{VIVO}» antes : {nodo(w, VIVO)['parameters']['conditions']['conditions'][0]['leftValue']}")
    print(f"«{VIVO}» ahora : {EXPR_VIVO}")
    print(f"«{RUTA}» antes : {nodo(w, RUTA)['parameters']['conditions']['conditions'][0]['leftValue']}")
    print(f"«{RUTA}» ahora : {EXPR_RUTA}")
    print(f"Cableado: {GM} → {GG} (nuevo, lee v7:global) → {VIVO}")
    print("\nREGLA (14 casos en node):")
    ok_regla = probar_regla()
    print("\nCHEQUEOS sobre el v6 PROPUESTO:")
    ok_chk = resumen(chequear(w, nuevo))
    if not (ok_regla and ok_chk):
        raise SystemExit("ABORTO: hay chequeos en rojo. No se tocó nada.")
    if not a.apply:
        print("\n[SIMULACIÓN] Todo verde. Para aplicar: --apply"); return
    print("\ncheck_triaje (regla del proyecto: antes de cualquier PUT al v6)")
    if subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], cwd=ROOT).returncode != 0:
        raise SystemExit("ABORTO: check_triaje no dio sano. No se tocó nada.")
    w2 = api(f"/workflows/{V6}")
    if w2.get("versionId") != w.get("versionId"):
        raise SystemExit("El v6 cambió mientras tanto: no hago PUT. Volvé a correr.")
    ts = int(time.time()); HIST.mkdir(parents=True, exist_ok=True)
    (HIST / f"{V6}_PRE_v7_para_todos_{ts}.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    put(nuevo)
    post = api(f"/workflows/{V6}")
    (HIST / f"{V6}_POST_v7_para_todos_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nVERIFICACIÓN sobre el v6 vivo después del PUT:")
    ok = resumen(chequear(w, post)) and post.get("active") is True
    print(("OK" if ok else "ATENCIÓN") + f": versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')} · backups _{ts}")
    print("Sin la llave no cambia nada. Prender para todos: python scripts/v7_global.py --on   ·   Revertir: --revertir --apply")


if __name__ == "__main__":
    main()
