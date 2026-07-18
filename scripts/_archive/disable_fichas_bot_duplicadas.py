"""Deshabilita (reversible, NO DELETE) las 4 fichas duplicadas que creo el bot.
Solo las 4 con patron bot (nac 1901 + afiliacion mayo 2026) y VACIAS (0 turnos).
Salvaguarda: si alguna tiene turnos, ABORTA (no toca nada).

Modos: --dry (muestra) / --apply (backup estado + PUT habilitado=0 + verify)."""
from __future__ import annotations
import argparse, json, os, sys, io
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DL = os.environ["DENTALINK_API_BASE"].rstrip("/"); T = os.environ["DENTALINK_API_TOKEN"]
H = {"Authorization": f"Token {T}", "Content-Type": "application/json"}

FICHAS = [613, 612, 614]  # tanda 2: fichas bot/test con celular falso (549110000010x)


def ficha(pid):
    return requests.get(f"{DL}/pacientes/{pid}", headers=H, timeout=30).json().get("data", {})

def turnos(pid):
    r = requests.get(f"{DL}/pacientes/{pid}/citas", headers=H, timeout=30)
    return r.json().get("data", []) if r.status_code == 200 else []


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    estados = {}
    abort = False
    print("=== Verificacion previa (read-only) ===")
    for pid in FICHAS:
        d = ficha(pid); ts = turnos(pid)
        estados[pid] = d
        nac = d.get("fecha_nacimiento", ""); afi = d.get("fecha_afiliacion", ""); hab = d.get("habilitado")
        es_bot = (nac == "1901-01-01" and afi >= "2026-05-01")
        print(f"  {pid}: {d.get('nombre')} {d.get('apellidos')} | nac={nac} afi={afi} habilitado={hab} | turnos={len(ts)} | patron_bot={es_bot}")
        if len(ts) > 0:
            print(f"  !! ABORTAR: ficha {pid} tiene {len(ts)} turnos, NO se toca."); abort = True
        if not es_bot:
            print(f"  !! ABORTAR: ficha {pid} NO tiene patron bot (1901+mayo). NO se toca."); abort = True

    if abort:
        print("\n[abort] alguna ficha no cumple las condiciones de seguridad. No se aplico nada."); sys.exit(2)

    if args.dry or not args.apply:
        print("\n[dry] las 4 cumplen (vacias + patron bot). Con --apply se deshabilitan (habilitado=0)."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = ROOT / "workflows" / "history" / f"dentalink_fichas_bot_PRE_disable_{ts}.json"
    bak.parent.mkdir(parents=True, exist_ok=True)
    bak.write_text(json.dumps(estados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup estado -> {bak}")

    for pid in FICHAS:
        r = requests.put(f"{DL}/pacientes/{pid}", headers=H, json={"habilitado": 0}, timeout=30)
        ok = r.status_code in (200, 201)
        new_hab = (r.json().get("data", {}) or {}).get("habilitado") if ok else None
        print(f"  PUT {pid} habilitado=0 -> {r.status_code} | habilitado ahora={new_hab}" + ("" if ok else f" | {r.text[:150]}"))

    # verify
    print("\n[verify]")
    for pid in FICHAS:
        d = ficha(pid)
        print(f"  {pid}: habilitado={d.get('habilitado')}")


if __name__ == "__main__":
    main()
