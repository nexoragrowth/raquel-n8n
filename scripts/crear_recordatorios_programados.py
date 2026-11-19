# -*- coding: utf-8 -*-
"""
crear_recordatorios_programados.py — (19/11/2026) workflow de n8n "Recordatorios programados": ejecuta los envíos que la clínica programa desde el panel
(tabla public.recordatorios_programados, scripts/recordatorios_programados.sql). Mismo mecanismo que el envío del 19/11 08:01 (verificado en vivo).

Cada 2 minutos (zona Jujuy):
  1) vence lo viejo: pendientes cuyo turno ya llegó o que llevan > 12 h atrasadas → 'vencido'; 'enviando' colgados > 30 min → 'error';
  2) toma UNA fila vencida (FOR UPDATE SKIP LOCKED → 'enviando');
  3) cuenta avisos ya enviados para esa fecha y lee de Dentalink cuántos corresponden (mismo filtro que "Solo citas activas");
  4) si no había avisos y hay algo para mandar: POST al webhook manual de Recordatorios (el mismo del botón Adelantar), espera 90 s;
  5) cuenta los avisos registrados; solo si salieron TODOS y no_repetir: suspende la corrida automática que los repetiría (dias_suspendidos);
  6) guarda estado y resultado en la fila.
Lógica en recordatorios/programados.js (tests/test_recordatorios_programados.js).

USO:  python scripts/crear_recordatorios_programados.py --json         # escribe el JSON generado (v7/workflows/recordatorios_programados.json), sin red
      python scripts/crear_recordatorios_programados.py --seco         # crea una copia de PRUEBA con webhook (no dispara avisos ni suspende), la corre y la borra
      python scripts/crear_recordatorios_programados.py --crear        # crea el workflow real INACTIVO y guarda el id en v7/ids.json
      python scripts/crear_recordatorios_programados.py --activar      # lo activa
Regla: --crear/--activar solo con el "desplegá" de Lucas, y después de aplicar recordatorios_programados.sql.
"""
import argparse, json, secrets, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from v7_lib import Grafo, CRED_POSTGRES
import crear_cita_prueba_examen as C

ROOT = Path(__file__).resolve().parent.parent
CORE = (ROOT / "recordatorios" / "programados.js").read_text(encoding="utf-8").rstrip() + "\n"
NOMBRE = "Recordatorios programados (panel)"
SETTINGS = {"executionOrder": "v1", "timezone": "America/Argentina/Jujuy", "errorWorkflow": "yop6TIVoKiWUxfEn"}
FILA = "$('Tomar uno').first().json"

SQL_VENCER = """update public.recordatorios_programados set
  estado = case when estado = 'enviando' then 'error' else 'vencido' end,
  resultado = coalesce(resultado, '{}'::jsonb) || jsonb_build_object('motivo', case when estado = 'enviando' then 'se cortó a mitad del envío: revisar' else 'no se mandó a tiempo' end)
where (estado = 'pendiente' and (fecha_turno <= (now() at time zone 'America/Argentina/Jujuy')::date or enviar_el < now() - interval '12 hours'))
   or (estado = 'enviando' and ejecutado_at < now() - interval '30 minutes')
returning id"""
SQL_TOMAR = """with c as (
  select id from public.recordatorios_programados
  where estado = 'pendiente' and enviar_el <= now()
  order by enviar_el, id
  for update skip locked
  limit 1
)
update public.recordatorios_programados p set estado = 'enviando', ejecutado_at = now()
from c where p.id = c.id
returning p.id, to_char(p.fecha_turno, 'YYYY-MM-DD') as fecha_turno, p.no_repetir"""
SQL_CONFIG = "select to_jsonb(c) as cfg from public.recordatorios_config c where id = 1"
SQL_YA = "select count(*)::int as ya from public.recordatorios_enviados where fecha_turno = $1::date"
SQL_VERIFICAR = "select count(*)::int as enviados from public.recordatorios_enviados where fecha_turno = $1::date"
SQL_SUSPENDER = ("update public.recordatorios_config set dias_suspendidos = (select coalesce(array_agg(distinct d order by d), '{}'::date[]) "
                 "from unnest(coalesce(dias_suspendidos, '{}'::date[]) || array[$1::date]) as d), updated_at = now(), updated_by = 'programado-panel' "
                 "where id = 1 returning dias_suspendidos")
SQL_SUSPENDER_SECO = "select array(select distinct d from unnest(coalesce(dias_suspendidos, '{}'::date[]) || array[$1::date]) d order by d) as quedaria from public.recordatorios_config where id = 1"
SQL_GUARDAR = "update public.recordatorios_programados set estado = $1, resultado = $2::jsonb where id = $3::bigint returning id, estado"

JS_DECIDIR = CORE + """const ya = Number($('Ya enviados').first().json.ya || 0);
const est = ProgramadosCore.esperado($('Citas del día').first().json);
return [{ json: { ...ProgramadosCore.decidir(ya, est), ya, est } }];"""
JS_CERRAR = CORE + """const fila = """ + FILA + """;
const d = $('Decidir').first().json;
const enviados = Number($('Verificar').first().json.enviados || 0);
const cfg = ($('Config').first().json || {}).cfg || {};
const ahora = new Date(Date.now() - 3 * 3600 * 1000);
const r = ProgramadosCore.cerrar({ ya: d.ya, est: d.est, enviados, disparado: d.disparar === true, noRepetir: fila.no_repetir === true,
  fechaTurno: fila.fecha_turno, cerrados: Array.isArray(cfg.dias_cerrados) ? cfg.dias_cerrados : [], hoy: ahora.toISOString().slice(0, 10),
  hora: ahora.getUTCHours(), horaEnvio: Number(cfg.hora_envio || 8) });
return [{ json: { id: fila.id, ...r } }];"""


def pg(g, nombre, query, x, y, params=None):
    p = {"operation": "executeQuery", "query": query, "options": ({"queryReplacement": "={{ " + params + " }}"} if params else {})}
    return g._nodo(nombre, "n8n-nodes-base.postgres", 2.5, p, x, y, {"credentials": CRED_POSTGRES, "alwaysOutputData": True, "executeOnce": True})


def construir(seco=False, ruta=None):
    g = Grafo(NOMBRE if not seco else "TMP prueba en seco recordatorios programados (se borra solo)")
    if seco:
        g._nodo("Cada 2 minutos", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 0, {"webhookId": secrets.token_hex(8)})
    else:
        g._nodo("Cada 2 minutos", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "cronExpression", "expression": "*/2 * * * *"}]}}, 0, 0)
    pg(g, "Vencer viejos", SQL_VENCER, 220, 0)
    pg(g, "Tomar uno", SQL_TOMAR, 440, 0)
    g.si("¿Hay uno?", "Number($json.id) > 0", 660, 0)
    pg(g, "Config", SQL_CONFIG, 880, 0)
    pg(g, "Ya enviados", SQL_YA, 1100, 0, f"[{FILA}.fecha_turno]")
    g.dentalink("Citas del día", "GET", "'https://api.dentalink.healthatom.com/api/v1/sucursales/1/citas'", x=1320, y=0,
                query_expr=f"JSON.stringify({{ fecha: {{ eq: {FILA}.fecha_turno }}, id_estado: {{ neq: 1 }} }})")
    g.code("Decidir", JS_DECIDIR, 1540, 0)
    g.si("¿Disparar?", "$json.disparar === true", 1760, 0)
    base = C.base().rstrip("/")
    if seco:
        g._nodo("Disparar avisos", "n8n-nodes-base.httpRequest", 4.2, {"method": "GET", "url": base + "/healthz", "options": {"timeout": 15000}}, 1980, -120, {"alwaysOutputData": True, "onError": "continueRegularOutput"})
    else:
        g._nodo("Disparar avisos", "n8n-nodes-base.httpRequest", 4.2, {"method": "POST", "url": base + "/webhook/trigger-recordatorios-manual", "sendBody": True, "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ fecha_target: " + FILA + ".fecha_turno }) }}", "options": {"timeout": 20000}}, 1980, -120, {"alwaysOutputData": True, "onError": "continueRegularOutput"})
    g._nodo("Esperar", "n8n-nodes-base.wait", 1.1, {"resume": "timeInterval", "amount": 1 if seco else 90, "unit": "seconds"}, 2200, -120, {"webhookId": secrets.token_hex(8)})
    pg(g, "Verificar", SQL_VERIFICAR, 2420, 0, f"[{FILA}.fecha_turno]")
    g.code("Cerrar", JS_CERRAR, 2640, 0)
    g.si("¿Suspender?", "!!$json.suspender", 2860, 0)
    pg(g, "Suspender corrida", SQL_SUSPENDER_SECO if seco else SQL_SUSPENDER, 3080, -120, "[$json.suspender]")
    pg(g, "Guardar resultado", SQL_GUARDAR, 3300, 0, "[$('Cerrar').first().json.estado, JSON.stringify($('Cerrar').first().json.resultado), $('Cerrar').first().json.id]")
    for a, b, s in (("Cada 2 minutos", "Vencer viejos", 0), ("Vencer viejos", "Tomar uno", 0), ("Tomar uno", "¿Hay uno?", 0), ("¿Hay uno?", "Config", 0),
                    ("Config", "Ya enviados", 0), ("Ya enviados", "Citas del día", 0), ("Citas del día", "Decidir", 0), ("Decidir", "¿Disparar?", 0),
                    ("¿Disparar?", "Disparar avisos", 0), ("¿Disparar?", "Verificar", 1), ("Disparar avisos", "Esperar", 0), ("Esperar", "Verificar", 0),
                    ("Verificar", "Cerrar", 0), ("Cerrar", "¿Suspender?", 0), ("¿Suspender?", "Suspender corrida", 0), ("¿Suspender?", "Guardar resultado", 1),
                    ("Suspender corrida", "Guardar resultado", 0)):
        g.conectar(a, b, s)
    wf = g.json(); wf["settings"] = dict(SETTINGS)
    return wf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true"); ap.add_argument("--seco", action="store_true"); ap.add_argument("--crear", action="store_true"); ap.add_argument("--activar", action="store_true")
    a = ap.parse_args()
    if a.json:
        out = ROOT / "v7" / "workflows" / "recordatorios_programados.json"
        out.write_text(json.dumps(construir(), ensure_ascii=False, indent=1), encoding="utf-8"); print("escrito", out); return
    if a.seco:
        ruta = "tmp-seco-" + secrets.token_hex(10)
        wid = C.api("/workflows", "POST", construir(True, ruta))["id"]; C.api(f"/workflows/{wid}/activate", "POST")
        try:
            r = C.llamar_webhook(ruta); print("respuesta:", json.dumps(r, ensure_ascii=False)[:600])
            time.sleep(2)
            ex = C.api(f"/executions?workflowId={wid}&limit=1&includeData=true")["data"][0]
            rd = ex["data"]["resultData"]["runData"]
            print("estado de la ejecución:", ex.get("status"))
            for n in ("Vencer viejos", "Tomar uno", "Config", "Ya enviados", "Decidir", "Disparar avisos", "Verificar", "Cerrar", "Suspender corrida", "Guardar resultado"):
                it = (rd.get(n, [{}])[0].get("data", {}).get("main", [[]]) or [[]])[0] if n in rd else None
                print(f"  {n:18}:", "(no corrió)" if it is None else (json.dumps(it[0]["json"], ensure_ascii=False)[:260] if it else "(sin salida)"))
        finally:
            for f in (lambda: C.api(f"/workflows/{wid}/deactivate", "POST"), lambda: C.api(f"/workflows/{wid}", "DELETE")):
                try: f()
                except Exception as e: print("aviso:", str(e)[:80])
            print("copia de prueba borrada")
        return
    ids_p = ROOT / "v7" / "ids.json"; ids = json.loads(ids_p.read_text(encoding="utf-8"))
    if a.crear:
        if ids.get("recordatorios_programados"): sys.exit("ya existe: " + ids["recordatorios_programados"])
        wid = C.api("/workflows", "POST", construir())["id"]
        ids["recordatorios_programados"] = wid; ids_p.write_text(json.dumps(ids, ensure_ascii=False, indent=1), encoding="utf-8")
        print("creado INACTIVO:", wid)
    if a.activar:
        C.api(f"/workflows/{ids['recordatorios_programados']}/activate", "POST"); print("activado:", ids["recordatorios_programados"])


if __name__ == "__main__":
    main()
