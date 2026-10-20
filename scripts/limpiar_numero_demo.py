# -*- coding: utf-8 -*-
"""
limpiar_numero_demo.py — deja un teléfono limpio para probar/demostrar el triaje desde un WhatsApp real.

Qué frena al bot para un teléfono: (1) modo humano en Supabase (pacientes.human_takeover, ventana 1 h; Chatwoot
se eliminó el 05/10); (2) memoria en n8n_chat_histories (filas
[ATENCION HUMANA]/[TEST 72h] contaminan el contexto y piden silencio al LLM); (3) estado
`triaje:{phone}` en Redis (no accesible desde acá: expira por TTL ≤2 h, o se pisa al escalar/cerrar).

Solo con --apply borra. Sin --apply muestra qué haría.

Segmentación (Día 1, --seg): cierra los tipos de contacto puestos para una prueba de punta a punta (motivo 'prueba_e2e', p. ej. con
`apply_dia1_segmentacion.py --e2e-on`) con motivo_baja 'fin_prueba', y al final verifica con contacto_ruta que el teléfono NO quede
silenciado (sale con error si sigue silenciado). Sin --apply solo muestra, en una sesión de solo lectura.

Uso: python scripts/limpiar_numero_demo.py --phone 5491161461034 [--apply] [--solo-label] [--borrar-logs] [--seg]
"""
import argparse, json, os, sys, urllib.request, psycopg2
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--phone", required=True)
ap.add_argument("--apply", action="store_true")
ap.add_argument("--solo-label", action="store_true", help="solo quitar el label humano en Chatwoot")
ap.add_argument("--borrar-logs", action="store_true", help="además borrar sus filas de escalaciones_log/triaje_urgencias_log/conversaciones de prueba (últimos 7 días)")
ap.add_argument("--seg", action="store_true", help="cerrar los tipos de contacto de la prueba E2E (prueba_e2e → fin_prueba) y verificar que no silencia")
args = ap.parse_args()
PHONE = args.phone.strip()

def n8n(path):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", headers={"X-N8N-API-KEY": require("N8N_API_KEY")})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

# 1) Chatwoot: ELIMINADO del VPS el 05/10 (el nodo "Re-check Humano" ya no existe; antes este paso crasheaba con StopIteration).
#    El "modo humano" hoy vive en Supabase: pacientes.human_takeover / human_takeover_at (lo leen Consultar Takeover, Gate Humano Final y el triaje).
if args.solo_label:
    print("--solo-label ya no aplica (Chatwoot eliminado el 05/10): el modo humano se limpia en pacientes.human_takeover (paso 2).")

# 2) memoria + logs
def load_env(path, keys):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k in keys: out[k] = v.strip().strip('"').strip("'")
    return out
db = load_env(str(ROOT / ".env"), {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"], user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require")
conn.autocommit = True
if not args.apply:
    conn.set_session(readonly=True, autocommit=True)   # sin --apply: imposible escribir
cur = conn.cursor()
cur.execute("SELECT human_takeover, human_takeover_at FROM pacientes WHERE telefono=%s", (PHONE,))
fila = cur.fetchone()
print(f"pacientes.human_takeover: {fila[0] if fila else '(sin fila)'} (desde {fila[1] if fila else '-'})")
if args.apply and fila and fila[0]:
    cur.execute("UPDATE pacientes SET human_takeover=false, human_takeover_at=NULL WHERE telefono=%s", (PHONE,))
    print(f"  -> modo humano apagado ({cur.rowcount} fila)")
cur.execute("SELECT count(*) FROM n8n_chat_histories WHERE session_id=%s", (PHONE,))
n_mem = cur.fetchone()[0]
print(f"n8n_chat_histories: {n_mem} filas de la sesión {PHONE}")
if args.apply:
    cur.execute("DELETE FROM n8n_chat_histories WHERE session_id=%s", (PHONE,))
    print(f"  -> borradas {cur.rowcount} (memoria limpia; el Router arranca sin contexto)")
if args.borrar_logs:
    for tabla, col in (("escalaciones_log", "telefono"), ("triaje_urgencias_log", "telefono")):
        cur.execute(f"SELECT count(*) FROM {tabla} WHERE {col}=%s AND created_at > NOW() - INTERVAL '7 days'", (PHONE,))
        n = cur.fetchone()[0]; print(f"{tabla}: {n} filas de los últimos 7 días")
        if args.apply and n:
            cur.execute(f"DELETE FROM {tabla} WHERE {col}=%s AND created_at > NOW() - INTERVAL '7 days'", (PHONE,)); print(f"  -> borradas {cur.rowcount}")
    cur.execute("SELECT count(*) FROM conversaciones WHERE telefono=%s AND \"timestamp\" > NOW() - INTERVAL '7 days'", (PHONE,))
    n = cur.fetchone()[0]; print(f"conversaciones: {n} filas de los últimos 7 días")
    if args.apply and n:
        cur.execute("DELETE FROM conversaciones WHERE telefono=%s AND \"timestamp\" > NOW() - INTERVAL '7 days'", (PHONE,)); print(f"  -> borradas {cur.rowcount}")
    # Bandeja de Atención (ATE-02, sql/2026-10-20_casos_atencion.sql): los casos que crearon los avisos de la prueba (la bitácora se va en cascada).
    cur.execute("SELECT to_regclass('public.casos') IS NOT NULL")
    if cur.fetchone()[0]:
        cur.execute("SELECT count(*) FROM public.casos WHERE telefono=public.contacto_tel_normalizar(%s) AND created_at > NOW() - INTERVAL '7 days'", (PHONE,))
        n = cur.fetchone()[0]; print(f"casos (bandeja de Atención): {n} de los últimos 7 días")
        if args.apply and n:
            cur.execute("DELETE FROM public.casos WHERE telefono=public.contacto_tel_normalizar(%s) AND created_at > NOW() - INTERVAL '7 days'", (PHONE,)); print(f"  -> borrados {cur.rowcount}")
    else:
        print("casos (bandeja de Atención): la tabla no existe todavía")
seg_sigue_silenciado = False
if args.seg:
    cur.execute("SELECT to_regprocedure('public.contacto_ruta(text)') IS NOT NULL")
    if not cur.fetchone()[0]:
        print("segmentación: la migración no está aplicada (no hay tipos que cerrar)")
    else:
        # De prueba = los de la prueba E2E (motivo prueba_e2e) Y los que se pusieron desde el PANEL en las últimas 12 h
        # (CRM-01: el recorrido del selector de tipo en el navegador escribe motivo 'clasificacion_manual', origen 'panel';
        # antes este cierre no los veía y un recorrido cortado a la mitad dejaba el número silenciado).
        cur.execute("""SELECT r.tipo FROM public.contacto_roles r JOIN public.pacientes p ON p.id = r.contacto_id
                        WHERE p.telefono = public.contacto_tel_normalizar(%s) AND r.hasta IS NULL
                          AND (r.motivo = 'prueba_e2e' OR (r.origen = 'panel' AND r.desde > NOW() - INTERVAL '12 hours'))
                        ORDER BY r.tipo""", (PHONE,))
        tipos = [x[0] for x in cur.fetchall()]
        print(f"segmentación: tipos vigentes de prueba (E2E o panel < 12 h): {tipos or 'ninguno'}")
        if args.apply:
            for t in tipos:
                cur.execute("SELECT public.contacto_tipo_cerrar(%s, %s, 'fin_prueba', 'lucas')", (PHONE, t))
                print(f"  -> {t} cerrado: {cur.fetchone()[0].get('ok')}")
        cur.execute("SELECT public.contacto_ruta(%s)", (PHONE,))
        ruta = cur.fetchone()[0]
        seg_sigue_silenciado = ruta.get("silencia") is True
        print(f"  contacto_ruta: tipo={ruta.get('tipo')} silencia={ruta.get('silencia')} tipos={ruta.get('tipos')}")
        if seg_sigue_silenciado:
            print("  ❌ el teléfono SIGUE SILENCIADO" + (" (tiene otro tipo vigente que no es de la prueba: revisar a mano)" if args.apply else
                                                      " (correr con --apply para cerrar los de la prueba)"))
cur.close(); conn.close()
print("Redis (no accesible desde acá; en el VPS por SSH):")
print(f"  docker exec redis-rwlw-redis-1 redis-cli DEL triaje:{PHONE} v7:tel:{PHONE}")
print(f"  claves del v7 (ficha/turnos_vistos/ofertas/lotes/bloque/propuesta/pago): python scripts/probar_v7.py --activar ; --destino reset --campo tel={PHONE} ; --desactivar")
print("  ratelimit: 10 msgs/15 min.")
if args.seg: print("  segmentación: no hay claves Redis por teléfono (el aviso al grupo no tiene tope); los avisos de la prueba quedan en"
                  " escalaciones_log: usar --borrar-logs")
if not args.apply: print("\n[DRY-RUN] nada borrado. Para aplicar: --apply")
if seg_sigue_silenciado and args.apply: sys.exit(1)
