# -*- coding: utf-8 -*-
"""
Comparativa de cerebros en SOMBRA con el modelo real y el número de Lucas (nunca pacientes). No manda WhatsApp ni escribe en la agenda.
Destinos: cerebro (v7 vivo) · cerebro_agente (v7 con agente padre) · v6_orquestador_sombra (v6 con agente padre).
Enciende los agentes SOLO durante la prueba (sin aviso de errores al grupo) y al final apaga y restaura todo. Limpia la memoria de sombra entre casos.

USO: python tests/comparativa/correr.py <salida.json> [destino1,destino2,...] [id1,id2,... (filtro)]
"""
import datetime, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D
from casos import CASOS
import os
CON_CONTEXTO = os.environ.get("COMPARATIVA_CASOS") == "contexto"
if CON_CONTEXTO:   # (11/11) contexto armado a mano: fichas, turnos y recordatorios inventados (casos_contexto.py)
    from casos_contexto import CASOS
elif os.environ.get("COMPARATIVA_CASOS"):   # casos reales armados por extraer_reales.py (archivo fuera del repo)
    CASOS = json.loads(Path(os.environ["COMPARATIVA_CASOS"]).read_text(encoding="utf-8"))
    # (12/11) Casos reales CON su contexto (extraer_reales.py --contexto): sus fichas y turnos van como escenario al celular SINTÉTICO.
    CON_CONTEXTO = any("escenario" in x for x in CASOS)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TEL = "5490000000777" if CON_CONTEXTO else "5491161461034"   # con contexto: celular SINTÉTICO (sin fichas reales en Dentalink)
MARCA_REC = "comparativa_ctx"
IDS = json.loads(D.IDS.read_text(encoding="utf-8"))
PROBAR = [sys.executable, "-W", "ignore", str(ROOT / "scripts" / "probar_v7.py")]
LIMPIAR = Path(sys.argv[0]).resolve().parent / "limpiar_sombra.py"
MAPA_SOURCE = {"paciente": ("human", "wa_inbound"), "asiri": ("ai", "asiri_v7"), "staff": ("ai", "wa_outbound"), "recordatorio": ("ai", "reminder_note")}


def historial(hist):
    ahora = datetime.datetime.now(datetime.timezone.utc)
    out = []
    for h in hist:
        tipo, src = MAPA_SOURCE[h["quien"]]
        out.append({"message": {"type": tipo, "content": h["texto"], "additional_kwargs": {"source": src}},
                    "created_at": (ahora - datetime.timedelta(minutes=h["hace_min"])).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out


def sh(*a):
    r = subprocess.run(PROBAR + list(a), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout + r.stderr


def limpiar_memoria():
    subprocess.run([sys.executable, str(LIMPIAR)], capture_output=True)


def db():
    import re, psycopg2
    env = {}
    for l in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*(SUPABASE_DB_[A-Z]+)\s*=\s*(.*)", l)
        if m: env[m.group(1)] = m.group(2).strip().strip("'\"")
    return psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"], user=env["SUPABASE_DB_USER"], password=env["SUPABASE_DB_PASSWORD"], sslmode="require")


def recordatorios(filas):
    """Borra los recordatorios de prueba del celular sintético y siembra los del caso (marca MARCA_REC)."""
    c = db(); cur = c.cursor()
    cur.execute("DELETE FROM recordatorios_enviados WHERE telefono = %s AND workflow_execution_id = %s", (TEL, MARCA_REC))
    for r in filas or []:
        cur.execute("INSERT INTO recordatorios_enviados (telefono, chat_remote_jid, id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, workflow_execution_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s::date, %s::time, '48h', %s)",
                    (TEL, TEL + "@s.whatsapp.net", r["id_cita_dentalink"], r["id_paciente_dentalink"], r["nombre_paciente"], r["fecha_turno"], r["hora_turno"], MARCA_REC))
    c.commit(); c.close()


def escenario(e):
    f = Path(os.environ.get("TEMP", ".")) / "escenario_comparativa.json"
    f.write_text(json.dumps({"destino": "escenario", "tel": TEL, "escenario": e or {"fichas": [], "citas": {}}}, ensure_ascii=False), encoding="utf-8")
    return sh("--archivo", str(f))


def put_sin_error_wf(wid):
    w = D.api(f"/workflows/{wid}")
    s = {k: v for k, v in (w.get("settings") or {}).items() if k in D.SETTINGS_OK}
    s.pop("errorWorkflow", None)
    D.api(f"/workflows/{wid}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"], "settings": s})


def main():
    salida = Path(sys.argv[1])
    destinos = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else ["cerebro", "cerebro_agente", "v6_orquestador_sombra"]
    filtro = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
    casos = [c for c in CASOS if not filtro or c["id"] in filtro]
    resultados = json.loads(salida.read_text(encoding="utf-8")) if salida.exists() else {}
    agentes = [d for d in destinos if d != "cerebro"]
    test_orig = D.api(f"/workflows/{IDS['test']}")
    try:
        for d in agentes:
            put_sin_error_wf(IDS[d])
        put_sin_error_wf(IDS["test"])
        for d in agentes:
            D.api(f"/workflows/{IDS[d]}/activate", "POST")
        print(sh("--activar").strip().splitlines()[-1], "· agentes encendidos:", agentes, flush=True)
        for c in casos:
            for d in destinos:
                clave = f"{c['id']}|{d}"
                if clave in resultados:
                    continue
                limpiar_memoria()
                sh("--destino", "reset", "--campo", f"tel={TEL}")
                if CON_CONTEXTO:
                    if c.get("escenario"):
                        escenario(c["escenario"])
                    recordatorios(c.get("recordatorios"))
                campos = ["--destino", d, "--campo", f"phone={TEL}", "--campo", "modo=sombra", "--campo", f"texto={c['texto']}"]
                if c["hist"]:
                    campos += ["--campo", "historial_json=" + json.dumps(historial(c["hist"]), ensure_ascii=False)]
                t0 = time.time()
                out = sh(*campos)
                seg = round(time.time() - t0, 1)
                try:
                    j = json.loads(out[out.index("{"): out.rindex("}") + 1])
                    j = j[0] if isinstance(j, list) else j
                    res = {"texto": j.get("texto"), "silencio": j.get("silencio"), "derivar_triaje": j.get("derivar_triaje"), "respaldo": j.get("usado_respaldo"),
                           "motivo": j.get("motivo_verificador") or j.get("motivo_chequeo"), "avisos": [a.get("texto", "")[:120] for a in (j.get("avisos") or [])], "seg": seg}
                except Exception:
                    res = {"error": out[:300], "seg": seg}
                resultados[clave] = res
                salida.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"{c['id']:14} {d:24} {seg:5}s  {'SILENCIO' if res.get('silencio') else (res.get('texto') or res.get('error') or '')[:90]!r}", flush=True)
    finally:
        limpiar_memoria()
        if CON_CONTEXTO:
            recordatorios([])
            sh("--destino", "reset", "--campo", f"tel={TEL}")
        for d in agentes + ["test"]:
            try:
                D.api(f"/workflows/{IDS[d]}/deactivate", "POST")
            except Exception as e:
                print("deactivate", d, str(e)[:60])
        s = {k: v for k, v in (test_orig.get("settings") or {}).items() if k in D.SETTINGS_OK}
        D.api(f"/workflows/{IDS['test']}", "PUT", {"name": test_orig["name"], "nodes": test_orig["nodes"], "connections": test_orig["connections"], "settings": s})
        sh("--desactivar")
        print("estado final:", {n: D.api(f"/workflows/{IDS[n]}").get("active") for n in agentes + ["test", "cerebro"]}, flush=True)


if __name__ == "__main__":
    main()
