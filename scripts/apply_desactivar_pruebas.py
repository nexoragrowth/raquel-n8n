# -*- coding: utf-8 -*-
"""
apply_desactivar_pruebas.py — 2026-10-31 · DESACTIVA (no borra) los workflows de prueba/legado que siguen activos con webhooks sin autenticación, más los
cerebros v7 retirados. Hallazgo de la auditoría v6→v7 (v6-otros, sección 5): 21 de prueba/legado (uno, "TEST Cleanup Basura Historica", borra filas de
n8n_chat_histories; otros leen la memoria de chat de números fijos) + 4 cerebros retirados. OK de Lucas: 28/10 ("sí" al punto 3).

Antes de tocar nada verifica, por cada uno: que ningún workflow ACTIVO que no esté en la lista lo referencie (por id o por la ruta de su webhook) y que ningún
archivo del repo (scripts/, tests/, data/, v7/) use la ruta de su webhook. Si algo lo usa, aborta.
Con --apply: backup completo de cada uno en workflows/history/ (…_PRE_desactivar_…json), POST /workflows/<id>/deactivate, y verificación (active=false).
Volver atrás: POST /workflows/<id>/activate (o restaurar el backup con scripts/restaurar_workflow.py).

USO:  python scripts/apply_desactivar_pruebas.py            # simulación (plan + chequeos)
      python scripts/apply_desactivar_pruebas.py --apply    # desactiva
"""
import argparse, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D   # api() con GET/POST

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"

PRUEBAS = {   # id -> nombre esperado ('*' donde el nombre real lleva un número de teléfono: no se escribe en el repo) (si el nombre vivo no coincide, aborta: no desactivar algo que cambió de identidad)
    "vmku7s93ksPNcQ5g": "AUDIT - basura n8n_chat_histories",
    "MvwET1EiyOinNgw0": "EXPLORE - Dentalink Citas",
    "kXgqUFfXJAvdnZAu": "TEST - Check Memory *",
    "AzDNfhfB8bGMALEJ": "TEST - Check Memory *",
    "S5XfpxHbm5cMx3Hq": "TEST - Cron Iter",
    "NDwKeIgcZtFt736Q": "TEST - Mock Recordatorio Lucas",
    "SSROJTB8gsmgchQr": "TEST - Reconcile Memory Post-Banlist",
    "fnrO0eoflJfePX7S": "TEST - Repoblar Reminders 03-06",
    "1lFMb5C8OljC0hv9": "TEST - Reset RL Lucas",
    "lskP0Cfwb1RajUDa": "TEST - SELECT Reminder 5498",
    "2jbYXjYaLrcKlPEr": "TEST - Select Chat History",
    "4Pum74HeOhk0kQco": "TEST - Sub-WF Writeback Memory Fix",
    "RBbTTcvBzDm7gmN7": "TEST - Update Literal",
    "L1EdJ3K0fRnnkH5K": "TEST - Update Template Embed",
    "xsXr4gV9QXJYRaML": "TEST - Where Debug",
    "zFtNDRUlN8n2Na71": "TEST Cleanup Basura Historica",
    "cip3czHqhLdaDgPd": "TEST View Lucas Memory",
    "E4GMd7K1It0iPHVD": "TEST View Mem Now",
    "MBQ1lczhrzp6K188": "TEST View Memory Fase4a",
    "h7HzwrQipcwMgL8G": "[ADMIN] Reset Memory (Lucas + Valentino)",
    "ahJzS48esjdmD4GH": "Áurea — TEST Triaje (webhook aislado)",
    # cerebros v7 retirados (los reemplazó "v7 Cerebro" NBHzj8ar2XuSvyIY el 08/10)
    "moIPDqrnY0SPIve9": "v7 Cerebro (minimal)",
    "UxdAuycDHMejecSr": "v7 Cerebro (orquestador mixto)",
    "DT408ysLhDgeqJyK": "v7 Cerebro (orquestador)",
    "zwAznFcbqANDAULn": "v7 Agente Clinica",
}


def rutas_webhook(wf):
    return sorted({str(n.get("parameters", {}).get("path", "")) for n in wf.get("nodes", []) if n.get("type", "").endswith(".webhook") and n.get("parameters", {}).get("path")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    todos = D.api("/workflows?limit=250")["data"]
    por_id = {w["id"]: w for w in todos}
    problemas, plan = [], []
    completos = {}
    for wid, nombre in PRUEBAS.items():
        w = por_id.get(wid)
        if not w:
            print(f"  (ya no existe) {wid} {nombre}")
            continue
        if not (w["name"].startswith(nombre[:-1]) if nombre.endswith("*") else w["name"] == nombre):   # '*' = el nombre lleva un teléfono que no va al repo
            problemas.append(f"{wid}: el nombre cambió ({w['name']!r} != {nombre!r})")
            continue
        completos[wid] = D.api(f"/workflows/{wid}")
        plan.append((wid, w["name"], w.get("active"), rutas_webhook(completos[wid])))
    # ¿Algún workflow ACTIVO fuera de la lista los referencia (id o ruta de webhook)?
    otros_activos = [w for w in todos if w.get("active") and w["id"] not in PRUEBAS]
    textos = {w["id"]: (w["name"], json.dumps(D.api(f"/workflows/{w['id']}"), ensure_ascii=False)) for w in otros_activos}
    repo = []
    for carpeta in ("scripts", "tests", "data", "v7"):
        for p in (ROOT / carpeta).rglob("*"):
            if p.is_file() and p.suffix in (".py", ".js", ".mjs", ".json", ".txt", ".md") and p.name != Path(__file__).name and not p.name.startswith("create_"):   # create_* crea el workflow, no lo usa
                try:
                    repo.append((p, p.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    pass
    print(f"Plan: {len(plan)} workflows a desactivar (de {len(PRUEBAS)} listados); {len(otros_activos)} activos quedan.")
    for wid, nombre, activo, rutas in plan:
        refs = [n for i, (n, t) in textos.items() if wid in t or any(r and (f"/{r}" in t or f'"{r}"' in t) for r in rutas)]
        refs_repo = [str(p.relative_to(ROOT)) for p, t in repo if any(r and len(r) > 6 and r in t for r in rutas)]
        estado = "activo" if activo else "ya inactivo"
        print(f"  - {wid} | {nombre} | {estado} | webhooks: {', '.join(rutas) or '—'}")
        if refs:
            problemas.append(f"{nombre}: lo referencia el workflow activo {refs}")
        if refs_repo:
            problemas.append(f"{nombre}: su webhook lo usa el repo: {refs_repo[:3]}")
    if problemas:
        print("\nPROBLEMAS (no se desactiva nada):")
        for p in problemas:
            print("  !", p)
        raise SystemExit(1)
    if not apply:
        print("\n[SIMULACIÓN] Sin referencias desde workflows activos ni desde el repo. Correr con --apply.")
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    hechos = []
    for wid, nombre, activo, _ in plan:
        (HIST / f"{wid}_PRE_desactivar_{ts}.json").write_text(json.dumps(completos[wid], ensure_ascii=False, indent=1), encoding="utf-8")
        if activo:
            D.api(f"/workflows/{wid}/deactivate", "POST")
            hechos.append(wid)
    mal = [wid for wid in hechos if D.api(f"/workflows/{wid}").get("active")]
    print(f"backups: workflows/history/<id>_PRE_desactivar_{ts}.json ({len(plan)})")
    print(f"desactivados: {len(hechos) - len(mal)} de {len(hechos)}" + (f" · SIGUEN ACTIVOS: {mal}" if mal else " · verificado active=false"))
    if mal:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
