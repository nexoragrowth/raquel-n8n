# -*- coding: utf-8 -*-
"""
conversar_v7.py — conversa con el v7 (cerebro, MODO SOMBRA: lecturas reales de la agenda, escrituras/avisos/memoria simulados) con un guion de mensajes del paciente.
Arma el historial turno a turno (historial_json) y muestra, por turno: lo que le diría Asiri, las herramientas que usó y los motivos de chequeo/banlist.
Necesita el webhook de prueba activo (scripts/probar_v7.py --activar --activar-subs). Usa el celular de prueba por defecto.

  python scripts/conversar_v7.py "Hola, quiero sacar un turno" "Es para Lucas" "El jueves 22 a las 8" "Sí"
  python scripts/conversar_v7.py --archivo guion.json      # {"phone": "...", "pushName": "...", "mensajes": ["...", "..."]}
"""
import argparse, json, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
RUTA = (ROOT / "data" / "v7_test_ruta.txt").read_text(encoding="utf-8").strip()


def llamar(body):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/webhook/{RUTA}", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=170) as r:
            return json.loads(r.read().decode()), time.time() - t0
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:600]}"}, time.time() - t0


def corrida(phone, push, mensajes, verbose=True):
    historial = []          # filas tipo n8n_chat_histories, MÁS NUEVA PRIMERO
    resultados = []
    for i, texto in enumerate(mensajes, 1):
        r, seg = llamar({"destino": "cerebro", "phone": phone, "texto": texto, "pushName": push, "modo": "sombra", "historial_json": json.dumps(historial, ensure_ascii=False)})
        if isinstance(r, list):
            r = r[0] if r else {}
        resp = r.get("texto")
        resultados.append({"turno": i, "paciente": texto, "asiri": resp, "segundos": round(seg, 1), "tools": r.get("tools"), "motivo_chequeo": r.get("motivo_chequeo"), "motivo_banlist": r.get("motivo_banlist"), "fallo_agente": r.get("fallo_agente"), "enviar": r.get("enviar"), "error": r.get("error")})
        if verbose:
            print(f"\n[{i}] PACIENTE: {texto}")
            if r.get("error"):
                print("    ERROR:", r["error"])
            else:
                print(f"    ASIRI ({seg:.1f} s): {resp}" if r.get("enviar") else f"    ASIRI ({seg:.1f} s): (silencio)")
                for t in (r.get("tools") or []):
                    print(f"      · {t.get('tool')}({json.dumps(t.get('input'), ensure_ascii=False)[:140]}) → {str(t.get('obs'))[:150].replace(chr(10), ' ')}")
                if r.get("motivo_chequeo") or r.get("motivo_banlist") or r.get("fallo_agente"):
                    print(f"      ! chequeo={r.get('motivo_chequeo')} banlist={r.get('motivo_banlist')} fallo_agente={r.get('fallo_agente')}")
        historial.insert(0, {"message": {"type": "human", "content": texto, "additional_kwargs": {"source": "wa_inbound"}}})
        if r.get("enviar") and resp:
            historial.insert(0, {"message": {"type": "ai", "content": resp, "additional_kwargs": {"source": "wa_outbound"}}})
    return resultados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mensajes", nargs="*"); ap.add_argument("--archivo"); ap.add_argument("--phone", default="5491161461034"); ap.add_argument("--push", default="Lucas Test")
    a = ap.parse_args()
    phone, push, mensajes = a.phone, a.push, a.mensajes
    if a.archivo:
        g = json.loads(Path(a.archivo).read_text(encoding="utf-8")); phone, push, mensajes = g.get("phone", phone), g.get("pushName", push), g["mensajes"]
    corrida(phone, push, mensajes)


if __name__ == "__main__":
    main()
