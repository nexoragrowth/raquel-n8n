# -*- coding: utf-8 -*-
"""
apply_precios_solo_consulta.py — 2026-10-16 · pedido de la Dra. (grupo, 16/10 8:27): "en precios y formas de pago solo que vaya el valor de la
consulta y especificar que aceptamos efectivo y transferencia. Lo de la cuota mensual y el retenedor NO debe decirse."

QUÉ CAMBIA:
  A) knowledge_base (la leen el v6, el v7 y el panel): 23 formas de pago → "efectivo y transferencia"; 36 cuota mensual y 39 retenedor/contención →
     "no se informa por WhatsApp; lo informa la secretaria". Se regeneran sus embeddings (misma receta que reembed_kb_nulls.py).
  B) v6 (O155MqHgOSaNZ9ye), nodo "Sub-Agent General": en DATOS OFICIALES se sacan las líneas de cuota y retenedor y se agregan "Formas de pago:
     efectivo y transferencia" y la regla de no informar esos valores. Nada más del grafo.
Backups: data/kb_backup_precios_<ts>.json y workflows/history/O155MqHgOSaNZ9ye_PRE/POST_precios_solo_consulta_<ts>.json.

USO:  python scripts/apply_precios_solo_consulta.py            # simula (muestra antes/después)
      python scripts/apply_precios_solo_consulta.py --apply
"""
import argparse, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api
import lista_semilla_contactos as L

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
V6 = "O155MqHgOSaNZ9ye"
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
               "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

KB_NUEVO = {
    23: "Formas de pago: efectivo y transferencia. Para transferencia se envían los datos de cuenta de la Dra. y se pide enviar el comprobante por este medio.",
    36: "El valor de la cuota mensual del tratamiento NO se informa por WhatsApp: lo informa la secretaria. Importante para desambiguar: muchos pacientes le dicen \"consulta\" o \"control\" a la cuota mensual que abonan en cada visita durante el tratamiento; si un paciente YA en tratamiento pregunta cuánto se paga por mes o en cada control, no se le da un monto: se le dice que ese valor se lo informa la secretaria.",
    39: "El valor del retenedor / contención NO se informa por WhatsApp: lo informa la secretaria.",
}

P_VIEJO = """- Cuota mensual tratamiento: {{ $('Extraer Horarios y Precio').item.json.cuota_mensual }}
- Retenedor / contención: {{ $('Extraer Horarios y Precio').item.json.precio_contencion }}
"""
P_NUEVO = """- Formas de pago: efectivo y transferencia.
- Cuota mensual del tratamiento, retenedor / contención y precios de tratamientos: NO se informan por WhatsApp (pedido de la Dra., 16/10). Si los preguntan, NO des ningún monto: respondé "Ese valor se lo informa la secretaria." y avisá con escalar_a_secretaria.
"""


def embed(texto, key):
    req = urllib.request.Request("https://api.openai.com/v1/embeddings", data=json.dumps({"model": "text-embedding-3-small", "dimensions": 1536, "input": texto}).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["data"][0]["embedding"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); a = ap.parse_args()
    from lib_env import require
    ts = int(time.time())
    # --- A) KB
    c = L.conectar(); c.set_session(readonly=not a.apply, autocommit=False); cur = c.cursor()
    cur.execute("SELECT id, categoria, titulo, contenido FROM knowledge_base WHERE id = ANY(%s) ORDER BY id", (list(KB_NUEVO),))
    filas = cur.fetchall()
    if len(filas) != len(KB_NUEVO): raise SystemExit(f"Esperaba {len(KB_NUEVO)} filas de la KB y hay {len(filas)}: no toco nada.")
    for i, cat, tit, cont in filas:
        print(f"KB {i} ({cat} | {tit})\n  ANTES:   {cont[:200]}\n  DESPUÉS: {KB_NUEVO[i][:200]}")
    # --- B) v6
    w = api(f"/workflows/{V6}")
    n = next(x for x in w["nodes"] if x["name"] == "Sub-Agent General")
    sm = n["parameters"]["options"]["systemMessage"]
    if sm.count(P_VIEJO) != 1: raise SystemExit("El texto de cuota/retenedor en «Sub-Agent General» no aparece exactamente 1 vez: el vivo cambió, no toco nada.")
    print(f"\nv6 «Sub-Agent General»: se reemplazan 2 líneas de DATOS OFICIALES (versionId {w.get('versionId')}).")
    if not a.apply:
        print("\n[SIMULACIÓN] Para aplicar: --apply"); c.close(); return
    # backup KB y v6
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / f"kb_backup_precios_{ts}.json").write_text(json.dumps([{"id": i, "categoria": cat, "titulo": tit, "contenido": cont} for i, cat, tit, cont in filas], ensure_ascii=False, indent=1), encoding="utf-8")
    hist = ROOT / "workflows" / "history"; hist.mkdir(parents=True, exist_ok=True)
    (hist / f"{V6}_PRE_precios_solo_consulta_{ts}.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    # KB: contenido + embedding (receta del panel: 'categoria | titulo\ncontenido')
    key = require("OPENAI_API_KEY")
    for i, cat, tit, _ in filas:
        vec = embed(f"{cat} | {tit}\n{KB_NUEVO[i]}", key)
        cur.execute("UPDATE knowledge_base SET contenido = %s, embedding = %s::vector WHERE id = %s", (KB_NUEVO[i], "[" + ",".join(str(x) for x in vec) + "]", i))
    c.commit(); c.close(); print("KB actualizada (3 filas) con embeddings nuevos.")
    # v6
    n["parameters"]["options"]["systemMessage"] = sm.replace(P_VIEJO, P_NUEVO)
    if any(x.get("webhookId") == "evo-webhook-v2" for x in w["nodes"]) is False: raise SystemExit("No encuentro webhookId evo-webhook-v2: no hago PUT.")
    otra = api(f"/workflows/{V6}")
    if otra.get("versionId") != w.get("versionId"): raise SystemExit("El v6 cambió mientras tanto: no hago PUT (la KB ya quedó cambiada).")
    api(f"/workflows/{V6}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
                                     "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK}, "staticData": w.get("staticData")})
    post = api(f"/workflows/{V6}")
    (hist / f"{V6}_POST_precios_solo_consulta_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    sm2 = next(x for x in post["nodes"] if x["name"] == "Sub-Agent General")["parameters"]["options"]["systemMessage"]
    ok = P_NUEVO in sm2 and len(post["nodes"]) == len(w["nodes"]) and post.get("active") is True and any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"])
    print(("OK" if ok else "ATENCIÓN") + f": v6 versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')} · backups _{ts}")


if __name__ == "__main__":
    main()
