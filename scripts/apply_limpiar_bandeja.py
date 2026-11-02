# -*- coding: utf-8 -*-
"""
apply_limpiar_bandeja.py — 2026-11-01 · limpia la bandeja de Atención antes de la capacitación (OK de Lucas: "ok limpiar").

CIERRA (public.caso_resolver, actor "cierre-automatico", sin devolver el chat al bot) los casos abiertos que cumplen TODO:
  · tipo distinto de urgencia (una urgencia no se cierra por proxy: la confirma una persona),
  · la clínica escribió por WhatsApp (wa_outbound) DESPUÉS del último aviso del caso,
  · el paciente NO volvió a escribir después de esa respuesta.
Deja abiertos: urgencias, casos donde el paciente volvió a escribir y casos sin ninguna respuesta de la clínica.
Reversible: guarda el estado previo en workflows/history/casos_PRE_limpiar_<ts>.json y con --revertir reabre (public.caso_reabrir) los cerrados por este script.

USO:  python scripts/apply_limpiar_bandeja.py              # simulación: lista qué cerraría
      python scripts/apply_limpiar_bandeja.py --apply      # cierra
      python scripts/apply_limpiar_bandeja.py --revertir <archivo_PRE.json> --apply
"""
import argparse, json, re, sys, time
from pathlib import Path
import psycopg2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
ACTOR = "cierre-automatico"
NOTA = "Cierre 01/11: la clínica ya contestó por WhatsApp y el paciente no volvió a escribir."

SQL = """
SELECT c.id, c.tipo, c.estado, c.dueno,
  (SELECT count(*) FROM public.n8n_chat_histories h WHERE h.session_id = c.telefono AND h.message->'additional_kwargs'->>'source' = 'wa_outbound' AND h.created_at > c.ultimo_aviso_at) AS staff_despues,
  (SELECT count(*) FROM public.n8n_chat_histories h WHERE h.session_id = c.telefono AND h.message->>'type' = 'human'
     AND h.created_at > coalesce((SELECT max(x.created_at) FROM public.n8n_chat_histories x WHERE x.session_id = c.telefono AND x.message->'additional_kwargs'->>'source' = 'wa_outbound' AND x.created_at > c.ultimo_aviso_at), c.ultimo_aviso_at)) AS paciente_despues
FROM public.casos c WHERE c.estado <> 'resuelto' ORDER BY c.id
"""


def conectar():
    env = {}
    for l in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*(SUPABASE_DB_[A-Z]+)\s*=\s*(.*)", l)
        if m:
            env[m.group(1)] = m.group(2).strip().strip("'\"")
    return psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"], user=env["SUPABASE_DB_USER"],
                            password=env["SUPABASE_DB_PASSWORD"], sslmode="require", connect_timeout=15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revertir", metavar="ARCHIVO_PRE")
    a = ap.parse_args()
    c = conectar()
    cur = c.cursor()
    if a.revertir:
        ids = [r["id"] for r in json.loads(Path(a.revertir).read_text(encoding="utf-8"))["cerrados"]]
        print(f"Revertir: {len(ids)} casos a reabrir")
        if not a.apply:
            print("[SIMULACIÓN] Correr con --apply.")
            return
        for i in ids:
            cur.execute("SELECT public.caso_reabrir(%s, %s)", (i, ACTOR))
        c.commit()
        print("reabiertos:", len(ids))
        return
    cur.execute(SQL)
    cols = [d[0] for d in cur.description]
    filas = [dict(zip(cols, r)) for r in cur.fetchall()]
    cerrar = [f for f in filas if f["tipo"] != "urgencia" and f["staff_despues"] > 0 and f["paciente_despues"] == 0]
    quedan = [f for f in filas if f not in cerrar]
    print(f"Abiertos: {len(filas)} · a cerrar: {len(cerrar)} · quedan abiertos: {len(quedan)}")
    por_tipo = {}
    for f in cerrar:
        por_tipo[f["tipo"]] = por_tipo.get(f["tipo"], 0) + 1
    print("a cerrar por tipo:", por_tipo)
    razon = lambda f: "urgencia (la confirma una persona)" if f["tipo"] == "urgencia" else ("el paciente volvió a escribir" if f["staff_despues"] > 0 else "sin respuesta de la clínica")
    print("quedan abiertos:", [(f["id"], f["tipo"], razon(f)) for f in quedan])
    if not a.apply:
        print("\n[SIMULACIÓN] No se escribió nada. Correr con --apply.")
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    pre = HIST / f"casos_PRE_limpiar_{ts}.json"
    pre.write_text(json.dumps({"nota": NOTA, "cerrados": [{"id": f["id"], "tipo": f["tipo"], "estado": f["estado"], "dueno": f["dueno"]} for f in cerrar]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("backup PRE:", pre.name)
    for f in cerrar:
        cur.execute("SELECT public.caso_resolver(%s, %s, %s, false)", (f["id"], ACTOR, NOTA))
        r = cur.fetchone()[0]
        if not r.get("ok"):
            c.rollback()
            raise SystemExit(f"Falló el caso {f['id']}: {r}. Se deshizo todo.")
    c.commit()
    cur.execute("SELECT count(*) FILTER (WHERE estado <> 'resuelto'), count(*) FILTER (WHERE estado = 'resuelto' AND resuelto_por = %s) FROM public.casos", (ACTOR,))
    abiertos, cerrados = cur.fetchone()
    print(f"verificación: abiertos ahora = {abiertos} · cerrados por este script = {cerrados}")


if __name__ == "__main__":
    main()
