# -*- coding: utf-8 -*-
"""
guarda_vivo.py — (12/11/2026) freno para no pisar en n8n cambios que este repo no conoce.

Por qué: el 05/11 se desplegó desde OTRA compu código que nunca llegó a este repo (propuesta de la clínica, incidente José).
El 12/11 la simulación mostró que desplegar desde acá lo borraba sin aviso; se recuperó desde n8n (commit 7d48bc0).
Despliegan dos compus: esto lo frena por código, no por memoria.

Cómo: todos los `api()` de scripts/ pasan por `envolver()`. En cada PUT/PATCH a /workflows/<id>:
  ANTES    la huella de lo vivo (nodos + conexiones, sin ids ni posiciones) tiene que ser la que registró el último despliegue
           en workflows/vivo_huellas.json. Si no coincide, alguien lo cambió por otro lado (otra compu, la UI de n8n): se frena
           y dice qué nodos cambiaron.
  DESPUÉS  registra la huella nueva. Ese archivo se commitea y se sube: la compu que no hizo `git pull` queda frenada.
Escape, SOLO después de traer lo vivo al repo y revisar el diff:  N8N_ACEPTAR_VIVO=<id>[,<id>…]   o   N8N_ACEPTAR_VIVO=todos

USO:  python scripts/guarda_vivo.py                    # informe: qué workflows cambiaron fuera de este repo
      python scripts/guarda_vivo.py --aceptar <id> …   # registra lo vivo de esos ids como conocido (tras revisarlos)
"""
import datetime as dt, hashlib, inspect, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUELLAS = ROOT / "workflows" / "vivo_huellas.json"
HIST = ROOT / "workflows" / "history"
_RUTA = re.compile(r"/workflows/([A-Za-z0-9]{10,})/?$")


def _limpio(wf):
    nodos = sorted(({k: v for k, v in n.items() if k not in ("id", "position")} for n in wf.get("nodes") or []), key=lambda n: str(n.get("name")))
    return {"nodes": nodos, "connections": wf.get("connections") or {}}


def huella(wf):
    return hashlib.sha256(json.dumps(_limpio(wf), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def _leer():
    try:
        return json.loads(HUELLAS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _commit():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _nombre(n):
    """El repo es público: los números largos de los nombres (p. ej. "TEST - Check Memory 549…") se enmascaran."""
    return re.sub(r"\d{7,}", lambda m: m.group(0)[:3] + "…" + m.group(0)[-2:], str(n or ""))


def registrar(wid, wf, por):
    d = _leer()
    d[wid] = {"huella": huella(wf), "nombre": _nombre(wf.get("name")), "fecha": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "script": por, "commit": _commit()}
    HUELLAS.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"   [guarda_vivo] huella de «{wf.get('name')}» registrada: commiteá y subí workflows/vivo_huellas.json (git push)")


def _sello(p):
    m = re.search(r"(\d{8})_(\d{6})", p.name)
    if m:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
    m = re.search(r"_(1\d{9})\.json$", p.name)
    return float(m.group(1)) if m else p.stat().st_mtime


def _backups(wid, solo_post=False):
    ps = [p for p in HIST.glob(f"*{wid}*.json") if not solo_post or "post" in p.name.lower()]
    return sorted(ps, key=_sello, reverse=True)


def _wf(x):
    if isinstance(x, dict) and "nodes" in x:
        return x
    if isinstance(x, (list, tuple)):
        return next((y for y in x if isinstance(y, dict) and "nodes" in y), None)
    return None


def _cargar(p):
    try:
        return _wf(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


def _que_cambio(ref, vivo):
    a, b = _limpio(ref), _limpio(vivo)
    na, nb = {n["name"]: n for n in a["nodes"]}, {n["name"]: n for n in b["nodes"]}
    out = [f"+ {k}" for k in sorted(set(nb) - set(na))] + [f"- {k}" for k in sorted(set(na) - set(nb))]
    out += [f"~ {k}" for k in sorted(set(na) & set(nb)) if json.dumps(na[k], sort_keys=True) != json.dumps(nb[k], sort_keys=True)]
    if json.dumps(a["connections"], sort_keys=True) != json.dumps(b["connections"], sort_keys=True):
        out.append("~ conexiones")
    return out


def estado(wid, vivo):
    """(ok, detalle, referencia). ok=None: no hay con qué comparar."""
    reg, h = _leer().get(wid), huella(vivo)
    if reg:
        if reg["huella"] == h:
            return True, "igual a lo último registrado", None
        ref = next((w for w in map(_cargar, _backups(wid)) if w and huella(w) == reg["huella"]), None)
        return False, f"distinto de lo registrado el {reg['fecha']} por {reg['script']} (commit {reg.get('commit') or '?'})", ref
    posts = _backups(wid, solo_post=True)
    ref = _cargar(posts[0]) if posts else None
    if ref is None:
        return None, "sin registro ni backup POST", None
    if huella(ref) == h:
        return True, f"igual al último backup ({posts[0].name})", ref
    return False, f"distinto del último backup ({posts[0].name})", ref


def revisar(wid, vivo):
    """Antes de un PUT: frena si lo vivo no es lo último que este repo desplegó."""
    acept = {x.strip() for x in os.environ.get("N8N_ACEPTAR_VIVO", "").split(",") if x.strip()}
    if "todos" in acept or wid in acept:
        print(f"   [guarda_vivo] {wid}: aceptado a mano (N8N_ACEPTAR_VIVO): se reemplaza lo vivo tal como está")
        return
    ok, detalle, ref = estado(wid, vivo)
    if ok:
        return
    if ok is None:
        print(f"   [guarda_vivo] aviso: «{vivo.get('name')}» ({wid}) {detalle}; no hay con qué comparar")
        return
    lineas = ["", f"⛔ [guarda_vivo] «{vivo.get('name')}» ({wid}) cambió en n8n por fuera de este repo: {detalle}.",
              "   Se desplegó desde otra compu o se editó en la UI de n8n. Desplegar ahora borraría esos cambios."]
    if ref:
        lineas.append("   Nodos que cambiaron: " + ", ".join(_que_cambio(ref, vivo)[:25]))
    lineas += ["   Qué hacer: git pull; si sigue, traer lo vivo al repo (memoria feedback-diff-vivo-antes-de-desplegar), simular y revisar",
               f"   el diff; recién ahí repetir con N8N_ACEPTAR_VIVO={wid}. No se cambió nada."]
    raise SystemExit("\n".join(lineas))


def envolver(api):
    """Devuelve api() con el freno puesto. Sirve para las dos firmas del repo: (path, method, payload) y (method, path, body)."""
    if getattr(api, "_guarda_vivo", False):
        return api
    metodo_primero = next(iter(inspect.signature(api).parameters)) == "method"
    por = Path(sys.argv[0]).name or "?"

    def leer(path):
        return _wf(api("GET", path) if metodo_primero else api(path))

    def w(*a, **k):
        if metodo_primero:
            method, path = k.get("method", a[0] if a else "GET"), k.get("path", a[1] if len(a) > 1 else "")
        else:
            path, method = k.get("path", a[0] if a else ""), k.get("method", a[1] if len(a) > 1 else "GET")
        method = str(method).upper()
        if method == "DELETE" and _RUTA.search(str(path)):
            res = api(*a, **k)
            d = _leer()
            if d.pop(_RUTA.search(str(path)).group(1), None):
                HUELLAS.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            return res
        m = _RUTA.search(str(path)) if method in ("PUT", "PATCH") else None
        if not m:
            res = api(*a, **k)
            if method == "POST" and str(path).rstrip("/").endswith("/workflows"):
                nuevo = _wf(res)
                if nuevo and nuevo.get("id"):
                    registrar(nuevo["id"], nuevo, por)
            return res
        wid = m.group(1)
        vivo = leer(path)
        if vivo is None:
            raise SystemExit(f"[guarda_vivo] no pude leer el workflow {wid} antes del PUT: no se cambia nada")
        revisar(wid, vivo)
        res = api(*a, **k)
        post = leer(path)
        if post:
            registrar(wid, post, por)
        return res

    w._guarda_vivo = True
    return w


def _get(path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lib_env import env, require
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if args[:1] == ["--aceptar"]:
        for wid in args[1:]:
            registrar(wid, _get(f"/workflows/{wid}"), "guarda_vivo.py --aceptar")
        return
    todos, cursor = [], None
    while True:
        r = _get("/workflows?limit=250" + (f"&cursor={cursor}" if cursor else ""))
        todos += r.get("data", [])
        cursor = r.get("nextCursor")
        if not cursor:
            break
    for w in sorted(todos, key=lambda w: (not w.get("active"), w.get("name") or "")):
        ok, detalle, ref = estado(w["id"], w)
        marca = {True: "ok ", False: "⛔ ", None: "?  "}[ok]
        print(f"{marca} {'ACTIVO ' if w.get('active') else 'inact. '} {w['id']}  {w.get('name')}  — {detalle}")
        if ok is False and ref:
            print("        " + ", ".join(_que_cambio(ref, w)[:15]))


if __name__ == "__main__":
    main()
