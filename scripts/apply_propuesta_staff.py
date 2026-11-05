# -*- coding: utf-8 -*-
"""
apply_propuesta_staff.py — 2026-11-05 · el paciente ACEPTA un cambio de turno que le propuso la clínica a mano (incidente José, ejecución 331590/331596).

Qué cambia (detalle y porqué en memory/decisions.md, entrada 05/11):
  · agenda_core.js: aceptar_propuesta_clinica (decidirPropuestaStaff): el modelo COPIA fecha/hora/turno viejo/para del mensaje de la clínica y el código los
    verifica (horaEnTexto, fechaEnTexto, nombre de la ficha, agenda). Si la agenda ya está así → texto del código sin escribir (salvo posible duplicado → deriva);
    si no → read-back del cambio y recién con el "sí" se escribe por la tubería de siempre. Al ejecutar se re-chequea que el horario no haya pasado;
    un cambio de la clínica conserva la duración de la cita original. confirma acepta "si".
  · historial_core.js + cerebro: el último mensaje CRUDO del staff (propuesta de MOVER un turno con hora, < 48 h, sin respuesta del paciente según
    mensajes_entrantes_live — nodo nuevo "Entrantes") llega a Turnos como propuesta_staff + bloque de contexto.
  · Agente Turnos: herramienta nueva aceptar_propuesta_clinica (4 datos texto); confirma se pide como la palabra "si" (el booleano tumbó al agente).
  · orquestador_core.js: textos/derivación/FYI de la ruta nueva; rechazo a la propuesta = silencio; saludo solo tras la propuesta = sin menú;
    el [ACCIÓN] de un agente caído trae el detalle técnico.
  · ejecutar_propuesta: FYI "aplicó el cambio que propuso la clínica"; si ese cambio falla, [ACCIÓN] a la secretaria.

Workflows que toca (de abajo hacia arriba: cada disparador declara los campos nuevos antes de que el que lo llama los mande):
  ejecutar_propuesta → gestionar_turno → proponer → agentes Pagos/Información/Urgencias → agente Turnos → cerebro.
  (proponer y Pagos/Información/Urgencias solo cambian porque llevan agenda_core.js / orquestador_core.js embebidos: misma fuente que el resto.)
No toca el v6, ni Recordatorios, ni ver_turnos, buscar_horarios, confirmar_*, clinica, elegir_ficha.

USO:  python scripts/apply_propuesta_staff.py              # simulación: qué nodos cambian en cada workflow (no escribe nada)
      python scripts/apply_propuesta_staff.py --apply      # check_triaje → backup PRE de TODOS → PUT de a uno → GET → backup POST → vivo == generado
Vuelta atrás: el script imprime los comandos de scripts/restaurar_workflow.py con los backups PRE, en orden inverso.
Regla del proyecto: --apply solo con OK explícito de Lucas.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D   # api(), SETTINGS_OK, IDS, ROOT (no ejecuta main)
from apply_cerebro_auditoria import diferencias

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"

# (clave en v7/ids.json, archivo generado, nodos que se ESPERA que cambien, nodos que se espera agregar, ¿cambian las conexiones?)
_PASOS_EJEC = {"Armar reserva", "Final", "Paso DNI", "Paso alta", "Paso alta (sin DNI)", "Paso anulación", "Paso cita", "Paso cita (sin cita)", "Paso consumo", "Paso inicial", "Paso reserva"}
ORDEN = [
    ("ejecutar_propuesta", "ejecutar_propuesta", _PASOS_EJEC, set(), False),
    ("gestionar_turno", "gestionar_turno", {"Entrada", "Decidir"}, set(), False),
    ("proponer", "proponer", {"Proponer"}, set(), False),
    ("agente_pagos", "agente_pagos", {"Entrada", "Armar salida"}, set(), False),
    ("agente_informacion", "agente_informacion", {"Entrada", "Armar salida"}, set(), False),
    ("agente_urgencias", "agente_urgencias", {"Entrada", "Armar salida"}, set(), False),
    ("agente_turnos", "agente_turnos", {"Entrada", "Agente", "Armar salida", "gestionar_turno"}, {"aceptar_propuesta_clinica"}, True),
    # el cerebro suma el nodo Postgres "Entrantes" (lee mensajes_entrantes_live: ¿el paciente ya contestó la propuesta?) entre "Primer mensaje" y "Datos del consultorio"
    ("cerebro", "cerebro", {"Armar contexto", "Despacho", "Ver urgencia", "Reunir", "Salida", "Agente Turnos", "Agente Pagos", "Agente Información", "Agente Urgencias"}, {"Entrantes"}, True),
]


def generados():
    subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "scripts" / "build_v7_workflows.py")], check=True, capture_output=True)
    ids = json.loads(D.IDS.read_text(encoding="utf-8"))
    out = {}
    for clave, archivo, *_ in ORDEN:
        txt = (ROOT / "v7" / "workflows" / f"{archivo}.json").read_text(encoding="utf-8")
        for k, v in ids.items():
            txt = txt.replace(f"@@ID:{k}@@", v)
        assert "@@ID:" not in txt, f"{archivo}: quedaron marcadores sin resolver"
        out[clave] = (json.loads(txt), ids[clave])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sin-check-triaje", action="store_true", help="solo en una máquina sin SUPABASE_DB_* en el .env: correr antes a mano los chequeos de check_triaje que no usan la DB")
    a = ap.parse_args()
    gen = generados()
    plan, raros = [], []
    for clave, _, esperados, agregar, con_conexiones in ORDEN:
        nuevo, wid = gen[clave]
        vivo = D.api(f"/workflows/{wid}")
        d = diferencias(vivo, nuevo)
        print(f"\n{vivo['name']} ({wid}) · activo={vivo.get('active')} · vivo {len(vivo['nodes'])} nodos → generado {len(nuevo['nodes'])}")
        print("  CAMBIADOS :", d["cambiados"] or "—")
        if d["agregados"] or d["sacados"]:
            print("  AGREGADOS :", d["agregados"] or "—", "· SACADOS:", d["sacados"] or "—")
        print("  conexiones:", "iguales" if d["conexiones_iguales"] else "DISTINTAS")
        fuera = [n for n in d["cambiados"] if n not in esperados] + [n for n in d["agregados"] if n not in agregar] + d["sacados"]
        if not d["conexiones_iguales"] and not con_conexiones:
            fuera.append("(conexiones)")
        if fuera:
            raros.append((clave, fuera))
            print("  ATENCIÓN, cambia algo fuera de lo previsto:", fuera)
        if d["cambiados"] or d["agregados"] or d["sacados"] or not d["conexiones_iguales"]:
            plan.append((clave, wid, vivo, nuevo))
    if not a.apply:
        print(f"\n[SIMULACIÓN] {len(plan)} workflows cambiarían. No se escribió nada. Correr con --apply (con OK de Lucas).")
        return
    if raros:
        raise SystemExit(f"Aborto: hay cambios fuera de lo previsto {raros}. Revisar a mano (¿alguien tocó n8n o el repo?).")
    if not plan:
        print("Nada que cambiar.")
        return
    if a.sin_check_triaje:
        print("\ncheck_triaje: SALTEADO (--sin-check-triaje)")
    else:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("\ncheck_triaje:", "OK" if r.returncode == 0 else "FALLÓ\n" + (r.stdout + r.stderr)[-800:])
        if r.returncode != 0:
            raise SystemExit("Aborto: check_triaje no pasa.")
    ts = time.strftime("%Y%m%d_%H%M%S")
    HIST.mkdir(parents=True, exist_ok=True)
    pres = []
    for clave, wid, vivo, _ in plan:   # TODOS los backups antes de la primera escritura
        f = HIST / f"v7_{wid}_PRE_propuesta_staff_{clave}_{ts}.json"
        f.write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
        pres.append(f)
    print("backups PRE:", *[p.name for p in pres], sep="\n  ")
    rollback = "\n".join(f"  python scripts/restaurar_workflow.py workflows/history/{p.name} --apply" for p in reversed(pres))
    hechos = []
    for (clave, wid, vivo, nuevo), pre in zip(plan, pres):
        body = {"name": nuevo["name"], "nodes": nuevo["nodes"], "connections": nuevo["connections"],
                "settings": {k: v for k, v in (nuevo.get("settings") or D.SETTINGS).items() if k in D.SETTINGS_OK}}
        try:
            D.api(f"/workflows/{wid}", "PUT", body)
            post = D.api(f"/workflows/{wid}")
        except Exception as e:   # noqa: BLE001
            print(f"\nFALLÓ el PUT de {clave}: {e}\nYa aplicados: {hechos}. Para volver atrás TODO (en este orden):\n{rollback}")
            raise SystemExit(1)
        (HIST / f"v7_{wid}_POST_propuesta_staff_{clave}_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        d2 = diferencias(post, nuevo)
        ok = not d2["cambiados"] and not d2["agregados"] and not d2["sacados"] and d2["conexiones_iguales"] and post.get("active") == vivo.get("active")
        print(f"  {clave}: vivo == generado → {'OK' if ok else 'DIFIERE ' + json.dumps(d2, ensure_ascii=False)} · activo={post.get('active')}")
        if not ok:
            print(f"\nVerificación fallida en {clave}. Ya aplicados: {hechos + [clave]}. Para volver atrás TODO (en este orden):\n{rollback}")
            raise SystemExit(1)
        hechos.append(clave)
    print(f"\nListo: {len(hechos)} workflows actualizados. Vuelta atrás, si hiciera falta (en este orden):\n{rollback}")


if __name__ == "__main__":
    main()
