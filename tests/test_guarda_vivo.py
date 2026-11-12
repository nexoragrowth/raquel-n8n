# -*- coding: utf-8 -*-
"""
test_guarda_vivo.py — (12/11) el freno de scripts/guarda_vivo.py, sin red (api falsa) y con archivos temporales.
Caso real que lo motiva: el 05/11 se desplegó desde otra compu código que no estaba en este repo; desplegar desde acá lo borraba.
"""
import copy, json, os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import guarda_vivo as G

tmp = Path(tempfile.mkdtemp())
G.HUELLAS = tmp / "vivo_huellas.json"
G.HIST = tmp / "history"
G.HIST.mkdir()
G._commit = lambda: "abc1234"

WID = "AbCdEfGhIjKlMnOp"
WF = {"id": WID, "name": "v7 Cerebro", "active": True,
      "nodes": [{"id": "1", "name": "Salida", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 0], "parameters": {"jsCode": "return 1;"}}],
      "connections": {}}
fallos, n = 0, 0


def t(nombre, ok, extra=""):
    global fallos, n
    n += 1
    if not ok:
        fallos += 1
        print(f"FALLA {nombre} {extra}")


class N8nFalso:
    """n8n de mentira: guarda un workflow por id; permite simular que otra compu lo cambió."""
    def __init__(self, wf):
        self.w = {wf["id"]: copy.deepcopy(wf)}
        self.puts = 0

    def api(self, path, method="GET", payload=None):
        wid = path.rstrip("/").split("/")[-1]
        if method == "GET":
            return copy.deepcopy(self.w[wid])
        if method == "PUT":
            self.puts += 1
            nuevo = copy.deepcopy(payload)
            for i, nd in enumerate(nuevo["nodes"]):     # n8n reasigna ids y posiciones: no tienen que cambiar la huella
                nd["id"] = f"x{i}{self.puts}"
            self.w[wid].update(nuevo)
            return copy.deepcopy(self.w[wid])
        if method == "DELETE":
            return self.w.pop(wid)
        if method == "POST":
            nuevo = dict(copy.deepcopy(payload), id="NuevoNuevoNuevo1")
            self.w[nuevo["id"]] = nuevo
            return nuevo


def cambiar(wf, codigo):
    w = copy.deepcopy(wf)
    w["nodes"][0]["parameters"]["jsCode"] = codigo
    return w


def put(api, wf):
    return api(f"/workflows/{WID}", "PUT", {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": {}})


# 1) sin registro ni backups: deja pasar con aviso y registra
f = N8nFalso(WF); api = G.envolver(f.api)
put(api, cambiar(WF, "return 2;"))
reg = json.loads(G.HUELLAS.read_text(encoding="utf-8"))
t("G1 primer despliegue registra la huella", reg[WID]["huella"] == G.huella(f.w[WID]) and reg[WID]["commit"] == "abc1234", reg)

# 2) despliegue siguiente con n8n intacto: pasa
put(api, cambiar(WF, "return 3;"))
t("G2 n8n igual a lo registrado: despliega", f.puts == 2)

# 3) otra compu cambió n8n: frena y no hace el PUT
f.w[WID] = cambiar(f.w[WID], "return 'de la otra compu';")
try:
    put(api, cambiar(WF, "return 4;")); frenado, msg = False, ""
except SystemExit as e:
    frenado, msg = True, str(e)
t("G3 cambio por fuera del repo: frena", frenado and f.puts == 2, msg)
t("G3b el aviso dice qué hacer (git pull) y no cambió nada", "git pull" in msg and "No se cambió nada" in msg, msg)

# 4) con backup de lo registrado, el aviso nombra el nodo que cambió
(G.HIST / f"{WID}_POST_algo_20261112_100000.json").write_text(json.dumps(cambiar(WF, "return 3;")), encoding="utf-8")
try:
    put(api, cambiar(WF, "return 4;")); msg = ""
except SystemExit as e:
    msg = str(e)
t("G4 el aviso nombra el nodo cambiado", "~ Salida" in msg, msg)

# 5) escape explícito tras revisar: N8N_ACEPTAR_VIVO=<id>
os.environ["N8N_ACEPTAR_VIVO"] = WID
put(api, cambiar(WF, "return 5;"))
del os.environ["N8N_ACEPTAR_VIVO"]
t("G5 N8N_ACEPTAR_VIVO deja pasar y registra lo nuevo", f.puts == 3 and json.loads(G.HUELLAS.read_text(encoding="utf-8"))[WID]["huella"] == G.huella(f.w[WID]))

# 6) ids y posiciones de nodos no cuentan (n8n los reasigna)
w = copy.deepcopy(f.w[WID]); w["nodes"][0]["id"] = "otro"; w["nodes"][0]["position"] = [999, 999]
t("G6 huella ignora id y posición", G.huella(w) == G.huella(f.w[WID]))

# 7) firma (method, path, body) de los scripts viejos
f2 = N8nFalso(WF)
api2 = G.envolver(lambda method, path, body=None: f2.api(path, method, body))
f2.w[WID] = cambiar(f2.w[WID], "return 'cambio ajeno';")
try:
    api2("PUT", f"/api/v1/workflows/{WID}", {"name": "x", "nodes": WF["nodes"], "connections": {}}); frenado = False
except SystemExit:
    frenado = True
t("G7 firma (method, path, body) también frena", frenado and f2.puts == 0)

# 8) PUT que no es a un workflow (p. ej. Dentalink) pasa derecho; GET no se toca
t("G8 activar/otros caminos no pasan por el freno", G._RUTA.search("/workflows/AbCdEfGhIjKlMnOp/activate") is None)

# 9) crear y borrar workflows temporales: registra y después limpia
api("/workflows", "POST", {"name": "temporal", "nodes": WF["nodes"], "connections": {}})
t("G9 crear registra", "NuevoNuevoNuevo1" in json.loads(G.HUELLAS.read_text(encoding="utf-8")))
api("/workflows/NuevoNuevoNuevo1", "DELETE")
t("G9b borrar limpia la huella", "NuevoNuevoNuevo1" not in json.loads(G.HUELLAS.read_text(encoding="utf-8")))

# 10) envolver dos veces no duplica el freno
t("G10 envolver es idempotente", G.envolver(api) is api)

print(f"{n - fallos}/{n} " + ("TODO OK" if not fallos else "CON FALLOS"))
sys.exit(1 if fallos else 0)
