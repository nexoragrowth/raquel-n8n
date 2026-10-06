# -*- coding: utf-8 -*-
"""
apply_takeover_24h_window.py — Ajuste de ventana de 24 horas para human_takeover.

1. Actualiza nodo 'Consultar Takeover Paciente' en v6:
   Evalúa que human_takeover sea true Y que human_takeover_at esté dentro de las últimas 24h.
2. Actualiza 'Activar Takeover (fromMe)' en v6:
   Guarda human_takeover = true y human_takeover_at = now().
3. Actualiza 'Activar Takeover Paciente' en Helper Notify:
   Guarda human_takeover = true y human_takeover_at = now().
4. Actualiza 'Sincronizar Takeover Supabase' en Panel Staff:
   Si humano=true guarda human_takeover_at = now(). Si humano=false guarda human_takeover_at = null.
"""

import argparse, copy, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env
from apply_media_entrantes import api, clean_settings, PUT_KEYS, WF_ID

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"

WID_V6 = WF_ID
WID_PANEL_STAFF = "jzxb5zUKCaJcvCgp"
WID_HELPER_NOTIFY = "S5U6tSipzlgFHCkf"


def backup_workflow(wid, label):
    wf = api(f"/workflows/{wid}")
    ts = int(time.time())
    dest = HIST / f"{wid}_{label}_{ts}.json"
    HIST.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False)
    print(f"  [BACKUP] Guardado {dest.name}")
    return wf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    print("==================================================================")
    print(" ⏰ APLICANDO VENTANA DE 24 HORAS EN TAKEOVER (n8n + Supabase)")
    print("==================================================================\n")

    # 1. Backups
    print("📦 [1/4] Backups...")
    v6_raw = backup_workflow(WID_V6, "PRE_takeover_24h")
    helper_raw = backup_workflow(WID_HELPER_NOTIFY, "PRE_takeover_24h")
    panel_raw = backup_workflow(WID_PANEL_STAFF, "PRE_takeover_24h")

    # 2. Modificar v6
    print("\n🔧 [2/4] Modificando v6...")
    v6_patched = copy.deepcopy(v6_raw)
    nodes_v6 = {n["name"]: n for n in v6_patched["nodes"]}

    # A) Consultar Takeover Paciente (Inbound)
    ct = nodes_v6.get("Consultar Takeover Paciente")
    if ct:
        ct["parameters"]["query"] = (
            "SELECT (COALESCE(human_takeover, false) = true AND "
            "COALESCE(human_takeover_at, now() - interval '48 hours') > now() - interval '24 hours') "
            "AS \"hasHumanoLabel\" FROM pacientes WHERE telefono = $1 LIMIT 1"
        )
        print("  • 'Consultar Takeover Paciente' actualizado con ventana de 24h.")

    # B) Activar Takeover (fromMe) (Outbound Staff)
    at = nodes_v6.get("Activar Takeover (fromMe)")
    if at:
        at["parameters"]["query"] = (
            "INSERT INTO pacientes (telefono, human_takeover, human_takeover_at, updated_at) "
            "VALUES ($1, true, now(), now()) "
            "ON CONFLICT (telefono) DO UPDATE SET "
            "human_takeover = true, human_takeover_at = now(), updated_at = now()"
        )
        print("  • 'Activar Takeover (fromMe)' actualizado con human_takeover_at = now().")

    # 3. Modificar Helper Notify Grupo
    print("\n🔧 [3/4] Modificando Helper Notify...")
    helper_patched = copy.deepcopy(helper_raw)
    nodes_helper = {n["name"]: n for n in helper_patched["nodes"]}
    hp = nodes_helper.get("Activar Takeover Paciente")
    if hp:
        hp["parameters"]["query"] = (
            "INSERT INTO pacientes (telefono, human_takeover, human_takeover_at, updated_at) "
            "VALUES ($1, true, now(), now()) "
            "ON CONFLICT (telefono) DO UPDATE SET "
            "human_takeover = true, human_takeover_at = now(), updated_at = now()"
        )
        print("  • 'Activar Takeover Paciente' (Helper) actualizado con human_takeover_at = now().")

    # 4. Modificar Panel Acciones Staff
    print("\n🔧 [4/4] Modificando Panel Acciones Staff...")
    panel_patched = copy.deepcopy(panel_raw)
    nodes_panel = {n["name"]: n for n in panel_patched["nodes"]}
    pp = nodes_panel.get("Sincronizar Takeover Supabase")
    if pp:
        pp["parameters"]["query"] = (
            "INSERT INTO pacientes (telefono, human_takeover, human_takeover_at, updated_at) "
            "VALUES ($1, $2, (CASE WHEN $2 = true THEN now() ELSE null END), now()) "
            "ON CONFLICT (telefono) DO UPDATE SET "
            "human_takeover = $2, "
            "human_takeover_at = (CASE WHEN $2 = true THEN now() ELSE null END), "
            "updated_at = now()"
        )
        print("  • 'Sincronizar Takeover Supabase' (Panel) actualizado.")

    if not args.apply:
        print("\n" + "="*50)
        print(" [DRY-RUN] Simulación completa. Corre con --apply para subir a n8n.")
        print("="*50)
        return

    def put_wf(wid, payload):
        body = {k: payload[k] for k in PUT_KEYS if k in payload}
        body["settings"] = clean_settings(payload.get("settings", {}))
        return api(f"/workflows/{wid}", method="PUT", payload=body)

    print("\n🚀 Aplicando a n8n...")
    put_wf(WID_HELPER_NOTIFY, helper_patched)
    print("  ✅ Helper actualizado.")
    put_wf(WID_PANEL_STAFF, panel_patched)
    print("  ✅ Panel Staff actualizado.")
    put_wf(WID_V6, v6_patched)
    print("  ✅ v6 Principal actualizado.")

    # POST Backups
    backup_workflow(WID_V6, "POST_takeover_24h")
    print("\n🎉 ¡Ventana de 24 horas implementada con éxito en n8n y Supabase!")


if __name__ == "__main__":
    main()
