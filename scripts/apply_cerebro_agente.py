# -*- coding: utf-8 -*-
"""
apply_cerebro_agente.py — 2026-11-02 · crea (o actualiza) el workflow "v7 Cerebro Agente" en n8n, SIEMPRE INACTIVO, y registra su id en v7/ids.json
para poder probarlo en SOMBRA por el webhook de prueba ("destino": "cerebro_agente"). NO toca el cerebro vivo (NBHzj8ar2XuSvyIY), la entrada,
los sub-agentes ni las herramientas. Backup del workflow si ya existe. Si "v7 Test (sombra)" existe, se actualiza (inactivo) para que conozca el destino nuevo.

USO:  python scripts/apply_cerebro_agente.py            # simulación
      python scripts/apply_cerebro_agente.py --apply    # crea/actualiza (inactivo) + verifica
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D   # api(), SETTINGS_OK, IDS, RUTA_TEST, wf_test, ROOT
import build_v7_workflows as B

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
CEREBRO_VIVO = "NBHzj8ar2XuSvyIY"


def cuerpo(wf):
    return {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": {k: v for k, v in (wf.get("settings") or {}).items() if k in D.SETTINGS_OK}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    B_wf = json.loads((ROOT / "v7" / "workflows" / "cerebro_agente.json").read_text(encoding="utf-8"))
    txt = json.dumps(B_wf, ensure_ascii=False)
    for k, v in ids.items():
        txt = txt.replace(f"@@ID:{k}@@", v)
    assert "@@ID:" not in txt, "quedaron marcadores sin resolver"
    wf = json.loads(txt)
    existentes = {w["name"]: w for w in D.api("/workflows?limit=250")["data"]}
    ya = existentes.get(wf["name"])
    print(f"{wf['name']}: {'ACTUALIZA ' + ya['id'] if ya else 'CREA (inactivo)'} · {len(wf['nodes'])} nodos")
    test = existentes.get("v7 Test (sombra)")
    print("v7 Test (sombra):", f"ACTUALIZA {test['id']} (inactivo) con destino cerebro_agente" if test else "no existe: no se toca")
    assert existentes.get("v7 Cerebro", {}).get("id") == CEREBRO_VIVO
    if not apply:
        print("\n[SIMULACIÓN] No se escribió nada. Correr con --apply.")
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    if ya:
        (HIST / f"v7_{ya['id']}_PRE_agente_{ts}.json").write_text(json.dumps(D.api(f"/workflows/{ya['id']}"), ensure_ascii=False, indent=1), encoding="utf-8")
        wid = ya["id"]
        D.api(f"/workflows/{wid}", "PUT", cuerpo(wf))
    else:
        wid = D.api("/workflows", "POST", cuerpo(wf))["id"]
    vivo = D.api(f"/workflows/{wid}")
    print(f"ok {wf['name']} → {wid} · activo={vivo.get('active')} · nodos={len(vivo['nodes'])}")
    assert not vivo.get("active"), "tiene que quedar INACTIVO"
    ids["cerebro_agente"] = wid
    D.IDS.write_text(json.dumps(ids, indent=1, ensure_ascii=False), encoding="utf-8")
    if test:
        ruta = D.RUTA_TEST.read_text(encoding="utf-8").strip()
        (HIST / f"v7_{test['id']}_PRE_agente_{ts}.json").write_text(json.dumps(D.api(f"/workflows/{test['id']}"), ensure_ascii=False, indent=1), encoding="utf-8")
        nuevo = D.wf_test({**ids}, ruta)
        D.api(f"/workflows/{test['id']}", "PUT", cuerpo(nuevo))
        t = D.api(f"/workflows/{test['id']}")
        print(f"ok v7 Test (sombra) actualizado · activo={t.get('active')}")
        assert not t.get("active")
    cer = D.api(f"/workflows/{CEREBRO_VIVO}")
    print("cerebro vivo intacto · activo =", cer.get("active"))


if __name__ == "__main__":
    main()
