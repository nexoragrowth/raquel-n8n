# -*- coding: utf-8 -*-
"""
diff_vivo.py — (12/11/2026) compara lo que genera el repo contra lo VIVO en n8n, nodo por nodo y parámetro por parámetro:
código, prompts, descripciones de herramientas, credenciales, tipo/versión de nodo y conexiones. (Antes los apply_* comparaban
solo el jsCode: un prompt o una descripción de herramienta cambiada en n8n no se veía.) Los uuids que el builder genera al azar
(ids de condiciones/asignaciones, webhookId) no cuentan como cambio.

USO:  python scripts/diff_vivo.py              # todos los workflows del v7 que tienen id en v7/ids.json
      python scripts/diff_vivo.py cerebro …    # solo esas claves
Lo usan los apply_* antes de desplegar: el diff tiene que mostrar SOLO el cambio buscado.
"""
import difflib, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
IGNORAR_NODO = {"id", "position", "webhookId"}
# (12/11) Los webhooks del panel validan un secreto que vive SOLO en n8n (el repo tiene el marcador): no cuenta como cambio y nunca se imprime.
SECRETO = re.compile(r'const SECRET = "[^"]*";')


def _sin_ruido(x):
    if isinstance(x, dict):
        return {k: _sin_ruido(v) for k, v in x.items() if not (k == "id" and isinstance(v, str) and UUID.fullmatch(v))}
    if isinstance(x, list):
        return [_sin_ruido(v) for v in x]
    if isinstance(x, str) and 'const SECRET = "' in x:
        return SECRETO.sub('const SECRET = "__PANEL_SECRET__";', x)
    return x


def _plano(x, pre=""):
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            out.update(_plano(v, f"{pre}.{k}" if pre else str(k)))
        return out or {pre: {}}
    if isinstance(x, list) and x and all(isinstance(v, dict) for v in x):
        out = {}
        for i, v in enumerate(x):
            out.update(_plano(v, f"{pre}[{i}]"))
        return out
    return {pre: x}


def _texto(a, b, sangria, max_lineas):
    out = []
    for l in difflib.unified_diff(str(a).splitlines(), str(b).splitlines(), lineterm="", n=0):
        if not l.startswith(("---", "+++", "@@")):
            out.append(sangria + l[:220])
    return out[:max_lineas] + ([sangria + f"… (+{len(out) - max_lineas} líneas)"] if len(out) > max_lineas else [])


def comparar(vivo, nuevo, max_lineas=40):
    """Devuelve (cantidad_de_cambios, líneas para mostrar)."""
    nv = {n["name"]: n for n in vivo.get("nodes") or []}
    nn = {n["name"]: n for n in nuevo.get("nodes") or []}
    lineas, cambios = [], 0
    for k in sorted(set(nn) - set(nv)):
        cambios += 1; lineas.append(f"   + nodo nuevo: {k}")
    for k in sorted(set(nv) - set(nn)):
        cambios += 1; lineas.append(f"   - nodo que se va: {k}")
    for k in sorted(set(nv) & set(nn)):
        a = _plano(_sin_ruido({x: y for x, y in nv[k].items() if x not in IGNORAR_NODO}))
        b = _plano(_sin_ruido({x: y for x, y in nn[k].items() if x not in IGNORAR_NODO}))
        dif = [p for p in sorted(set(a) | set(b)) if a.get(p) != b.get(p)]
        if not dif:
            continue
        cambios += 1
        lineas.append(f"   ~ «{k}»:")
        for p in dif:
            va, vb = a.get(p, "(no está)"), b.get(p, "(no está)")
            if isinstance(va, str) and isinstance(vb, str) and ("\n" in va or "\n" in vb or len(va) + len(vb) > 200):
                lineas.append(f"      {p}:")
                lineas += _texto(va, vb, "         ", max_lineas)
            else:
                lineas.append(f"      {p}: {json.dumps(va, ensure_ascii=False)[:150]}  →  {json.dumps(vb, ensure_ascii=False)[:150]}")
    if json.dumps(vivo.get("connections") or {}, sort_keys=True) != json.dumps(nuevo.get("connections") or {}, sort_keys=True):
        cambios += 1; lineas.append("   ~ conexiones cambian")
    return cambios, lineas


def conservar_webhooks(vivo, nuevo):
    """El builder genera webhookId al azar; en n8n ese id es la URL del webhook (lección evo-webhook-v2). Se conserva el vivo."""
    wv = {n["name"]: n["webhookId"] for n in vivo.get("nodes") or [] if n.get("webhookId")}
    for n in nuevo.get("nodes") or []:
        if n["name"] in wv:
            n["webhookId"] = wv[n["name"]]
    return nuevo


def generado(clave, ids):
    import build_v7_workflows as B
    txt = json.dumps(B.WORKFLOWS[clave](), ensure_ascii=False)
    for k, v in ids.items():
        txt = txt.replace(f"@@ID:{k}@@", v)
    assert "@@ID:" not in txt, f"{clave}: quedaron marcadores sin resolver"
    return json.loads(txt)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import crear_v7_en_n8n as D
    import build_v7_workflows as B
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    claves = sys.argv[1:] or [k for k in B.WORKFLOWS if ids.get(k) and not str(ids[k]).startswith("PENDIENTE")]
    total = 0
    for k in claves:
        vivo = D.api(f"/workflows/{ids[k]}")
        c, lineas = comparar(vivo, generado(k, ids))
        total += c
        print(f"{'==' if c else 'ok'} {k:22s} {vivo['name']} ({ids[k]}) activo={vivo.get('active')}  → {c} cambio(s)")
        for l in lineas:
            print(l)
    print(f"\n{total} cambio(s) entre el repo y lo vivo.")


if __name__ == "__main__":
    main()
