# -*- coding: utf-8 -*-
"""
apply_cerebro_auditoria.py — 2026-10-28 (2.ª tanda) · actualiza SOLO "v7 Cerebro" (NBHzj8ar2XuSvyIY) con los arreglos de la auditoría v6→v7:
  · comprobante marcado ("[IMAGEN] TIPO: COMPROBANTE") siempre pasa por Pagos; agente "payments"/"appointments"... se entiende (alias);
  · prompt del orquestador: sin "informa algo" que derivaba de más, sticker/emoji = silencio, mensaje mixto (info + fuera de alcance) se parte;
  · el audio transcripto se detecta aunque venga con texto escrito antes en el buffer.
(Cambios anteriores del mismo script, 1.ª tanda:)

  1. AUDIOS (bug real 27/10 12:18): un audio que SÍ se transcribió ("[AUDIO] ...la tomografía con o sin braquets?") recibía "no puedo escuchar audios".
     Prompt del orquestador (pedir_texto solo si el audio llegó SIN transcripción) + red por código (audio transcripto + pedir_texto → se deriva con lo que dijo)
     + el texto de pedir_texto ya no afirma que Asiri no escucha audios.
  2. MENSAJES FIJOS EDITABLES desde el panel (filas msg_<CLAVE> de agente_directrices): vacío/inválido/sin filas = sale el estándar (hoy no hay filas: sin cambio).

No toca el v6, ni las herramientas, ni los sub-agentes, ni Recordatorios. Backup PRE/POST en workflows/history/. Se vuelve atrás con scripts/restaurar_workflow.py.

USO:  python scripts/apply_cerebro_auditoria.py             # simulación: qué nodos cambian (no escribe nada)
      python scripts/apply_cerebro_mensajes_audio.py --apply     # check_triaje -> backup PRE -> PUT -> GET -> backup POST -> verificación
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D   # api(), SETTINGS_OK, IDS, ROOT (no ejecuta main)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CEREBRO = "NBHzj8ar2XuSvyIY"
PUT_KEYS = ("name", "nodes", "connections", "settings")


def generado():
    """El cerebro generado por el repo, con los ids de sub-agentes y herramientas resueltos (igual que crear_v7_en_n8n.py)."""
    subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "scripts" / "build_v7_workflows.py")], check=True, capture_output=True)
    txt = (ROOT / "v7" / "workflows" / "cerebro.json").read_text(encoding="utf-8")
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    for k, v in ids.items():
        txt = txt.replace(f"@@ID:{k}@@", v)
    assert "@@ID:" not in txt, "quedaron marcadores sin resolver"
    return json.loads(txt)


def _sin_uuid(x):
    """El generador pone un UUID aleatorio a cada condición de los nodos IF en cada corrida: es ruido, no un cambio."""
    if isinstance(x, dict):
        return {k: _sin_uuid(v) for k, v in x.items() if not (k == "id" and isinstance(v, str) and len(v) == 36 and v.count("-") == 4)}
    if isinstance(x, list):
        return [_sin_uuid(v) for v in x]
    return x


def firma(n):
    return json.dumps(_sin_uuid(n.get("parameters", {})), ensure_ascii=False, sort_keys=True)


def diferencias(vivo, nuevo):
    a = {n["name"]: n for n in vivo["nodes"]}
    b = {n["name"]: n for n in nuevo["nodes"]}
    out = {"agregados": sorted(set(b) - set(a)), "sacados": sorted(set(a) - set(b)), "cambiados": sorted(k for k in set(a) & set(b) if firma(a[k]) != firma(b[k]))}
    out["conexiones_iguales"] = json.dumps(vivo["connections"], sort_keys=True) == json.dumps(nuevo["connections"], sort_keys=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    nuevo = generado()
    vivo = D.api(f"/workflows/{CEREBRO}")
    d = diferencias(vivo, nuevo)
    print(f"v7 Cerebro ({CEREBRO}) · vivo: {len(vivo['nodes'])} nodos · generado: {len(nuevo['nodes'])} nodos · activo={vivo.get('active')}")
    print("  nodos AGREGADOS :", d["agregados"] or "—")
    print("  nodos SACADOS   :", d["sacados"] or "—")
    print("  nodos CAMBIADOS :", d["cambiados"] or "—")
    print("  conexiones      :", "iguales" if d["conexiones_iguales"] else "DISTINTAS")
    # (los que llevan el núcleo orquestador_core.js embebido + la consulta de datos)
    inesperados = [n for n in d["cambiados"] if n not in ("Armar contexto", "Despacho", "Reunir", "Ver urgencia", "Salida", "Datos del consultorio")]
    if inesperados or d["agregados"] or d["sacados"] or not d["conexiones_iguales"]:
        print("\n  ATENCIÓN: cambia algo más de lo previsto (", inesperados, d["agregados"], d["sacados"], "): revisar antes de aplicar.")
    if not apply:
        print("\n[SIMULACIÓN] No se escribió nada. Correr con --apply.")
        return
    if inesperados or d["agregados"] or d["sacados"] or not d["conexiones_iguales"]:
        raise SystemExit("Aborto: el diff trae cambios no previstos (el repo y el vivo no coinciden). Revisar a mano.")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("check_triaje:", "OK" if r.returncode == 0 else "FALLÓ\n" + (r.stdout + r.stderr)[-800:])
    if r.returncode != 0:
        raise SystemExit("Aborto: check_triaje no pasa.")
    ts = time.strftime("%Y%m%d_%H%M%S")
    pre = HIST / f"v7_{CEREBRO}_PRE_auditoria_{ts}.json"
    pre.write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
    print("backup PRE:", pre.name)
    body = {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"], "settings": {k: v for k, v in (nuevo.get("settings") or D.SETTINGS).items() if k in D.SETTINGS_OK}}
    assert set(body) <= set(PUT_KEYS)
    D.api(f"/workflows/{CEREBRO}", "PUT", body)
    post = D.api(f"/workflows/{CEREBRO}")
    (HIST / f"v7_{CEREBRO}_POST_auditoria_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    d2 = diferencias(post, nuevo)
    ok = not d2["cambiados"] and not d2["agregados"] and not d2["sacados"] and d2["conexiones_iguales"] and post.get("active") == vivo.get("active")
    print(f"verificación: vivo == generado → {'OK' if ok else 'DIFIERE ' + json.dumps(d2, ensure_ascii=False)} · activo={post.get('active')}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
