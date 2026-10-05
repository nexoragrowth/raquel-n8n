# -*- coding: utf-8 -*-
"""
exportar_conversaciones_periodos.py — exporta las conversaciones REALES de los ultimos 30 / 60 / 90 dias a archivos
locales para que una IA (o una persona) las analice: casos normales y casos borde por funcion (agendar, confirmar,
cancelar/reprogramar, precios/pagos, urgencias, etc.).

FUENTE: tabla `conversaciones` de Supabase v3 (copia que hace el Logger de TODO lo que pasa por el chat: paciente, bot,
staff y recordatorios). OJO: NO se usa `n8n_chat_histories`, porque el bot borra de ahi los mensajes viejos de cada chat
y conserva los del staff: el histórico queda sesgado (75% mensajes del staff, casi sin mensajes del paciente).

SOLO LECTURA: una conexion con `default_transaction_read_only = on` y un unico SELECT. No escribe nada en la base.

SALIDA (carpeta data/conversaciones/, ignorada por git porque tiene datos de pacientes):
    ultimos_30d.json  ultimos_60d.json  ultimos_90d.json   conversaciones agrupadas por paciente, mensajes en orden
    LEEME.md                                                formato, conteos, cobertura real y avisos de privacidad
    mapa_pacientes.json                                     seudonimo -> telefono real (SOLO para uso local de Lucas;
                                                            no se lo pases a la IA si no hace falta)

Los telefonos se reemplazan por un seudonimo estable (p_ab12cd; tel_LUCAS / tel_IRINA / tel_DRA para el staff).
Los textos NO se tocan (pueden traer nombres que escribio el paciente): son datos personales y de salud, mantenelos locales.

USO:
    python scripts/exportar_conversaciones_periodos.py              # 30, 60 y 90 dias
    python scripts/exportar_conversaciones_periodos.py --dias 45    # un periodo a medida
"""
import argparse, hashlib, json, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "conversaciones"
ART = timezone(timedelta(hours=-3))
STAFF = {"5491161461034": "tel_LUCAS", "5493885786946": "tel_IRINA", "5493513976787": "tel_DRA"}
RX_PREFIJO_STAFF = re.compile(r"^\[ATENCION HUMANA[^\]]*\]:?\s*", re.I)
# El sub-flujo Cancelar/Reprogramar del bot guarda sus respuestas con source='wa_outbound' (la misma marca que los mensajes del
# staff), asi que llegan como "staff". Se reclasifican como bot por su voz inconfundible (plantillas de Asiri).
RX_VOZ_BOT = re.compile(
    r"soy asiri|secretaria virtual|tengo disponibles en dentalink|tenemos los pr[oó]ximos turnos disponibles|"
    r"con este n[uú]mero tengo registrad|no te encuentro turnos|no encuentro un turno|^listo, su turno .{0,60}(queda|qued[oó]) (cancelado|confirmado)|"
    r"^le confirmo:|ese horario no est[aá] disponible", re.I)
RX_NUMEROS = re.compile(r"\d{7,}")  # telefonos, DNI, CBU, ids: no hacen falta para analizar y son datos personales


def seudonimo(tel):
    tel = re.sub(r"\D", "", tel or "")
    return STAFF.get(tel) or ("p_" + hashlib.sha1(tel[-10:].encode()).hexdigest()[:6])


def rol_normalizado(rol, fuente, texto_original, meta):
    """El Logger marca fuente='bot' para CUALQUIER fila type=ai, incluidos los mensajes del staff y las notas de
    recordatorio: se distinguen por el marcador interno del texto o por metadata.source (como hace el panel)."""
    source = (meta or {}).get("source")
    if rol == "user":
        return "paciente"
    if rol == "human":
        return "staff"
    if rol == "assistant":
        if fuente == "bot_reminder" or source == "reminder_note":
            return "recordatorio"
        if RX_PREFIJO_STAFF.match(texto_original or "") or source in ("wa_outbound", "human_takeover") or fuente == "whatsapp_secretaria":
            return "staff"
        return "bot"
    if rol == "system":
        # filas internas del bot: las notas de recordatorio llevan el texto del recordatorio enviado al paciente
        t0 = (texto_original or "").lstrip()
        if t0.startswith("[NOTA INTERNA"):
            return "interno"  # contexto que el bot guarda tras enviar un recordatorio: no lo vio el paciente
        if t0.startswith("[TEST"):
            return "recordatorio_test"  # pruebas del workflow de recordatorios (no son pacientes reales)
        if fuente == "bot_reminder" or source == "reminder_note" or re.search(r"recordamos su turno|recordatorio", t0, re.I):
            return "recordatorio"
        return "interno"
    return rol or "desconocido"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, nargs="+", default=[30, 60, 90])
    args = ap.parse_args()
    periodos = sorted(set(args.dias))
    maximo = periodos[-1]

    import psycopg2
    conn = psycopg2.connect(host=env("SUPABASE_V3_DB_HOST"), port=env("SUPABASE_V3_DB_PORT"), dbname=env("SUPABASE_V3_DB_NAME"),
                            user=env("SUPABASE_V3_DB_USER"), password=env("SUPABASE_V3_DB_PASSWORD"), sslmode="require",
                            connect_timeout=15, options="-c default_transaction_read_only=on")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, telefono, rol, mensaje, fuente, timestamp, metadata FROM public.conversaciones "
            "WHERE timestamp >= now() - (%s || ' days')::interval "
            "ORDER BY telefono, timestamp, id", (str(maximo),))
        filas = cur.fetchall()
        cur.execute("SELECT min(timestamp), max(timestamp), count(*) FROM public.conversaciones")
        cobertura = cur.fetchone()
    finally:
        conn.close()

    ahora = datetime.now(timezone.utc)
    vistos, mensajes, mapa = set(), [], {}
    for id_, tel, rol, texto, fuente, ts, meta in filas:
        meta = meta or {}
        clave = ("h", meta.get("chat_history_id")) if meta.get("chat_history_id") else (tel, rol, texto, ts)
        if clave in vistos:
            continue
        vistos.add(clave)
        txt = RX_NUMEROS.sub("<nº>", RX_PREFIJO_STAFF.sub("", texto or "").strip())
        if not txt:
            continue
        rol_final = rol_normalizado(rol, fuente, texto, meta)
        if rol_final == "staff" and RX_VOZ_BOT.search(txt):
            rol_final = "bot"
        p = seudonimo(tel)
        mapa[p] = re.sub(r"\D", "", tel or "")
        mensajes.append({"p": p, "ts": ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc), "rol": rol_final,
                         "texto": txt, "fuente": fuente, "id": id_})

    OUT.mkdir(parents=True, exist_ok=True)
    resumen = []
    for dias in periodos:
        desde = ahora - timedelta(days=dias)
        por_pac = defaultdict(list)
        for m in mensajes:
            if m["ts"] >= desde:
                por_pac[m["p"]].append(m)
        convs = []
        for p, ms in sorted(por_pac.items(), key=lambda kv: kv[1][0]["ts"]):
            ms.sort(key=lambda m: (m["ts"], m["id"]))
            convs.append({
                "paciente": p, "n_mensajes": len(ms),
                "desde": ms[0]["ts"].astimezone(ART).isoformat(timespec="minutes"),
                "hasta": ms[-1]["ts"].astimezone(ART).isoformat(timespec="minutes"),
                "hubo_staff": any(m["rol"] == "staff" for m in ms), "hubo_bot": any(m["rol"] == "bot" for m in ms),
                "mensajes": [{"t": m["ts"].astimezone(ART).strftime("%Y-%m-%d %H:%M"), "rol": m["rol"], "texto": m["texto"]} for m in ms],
            })
        (OUT / f"ultimos_{dias}d.json").write_text(json.dumps(convs, ensure_ascii=False, indent=1), encoding="utf-8")
        roles = Counter(m["rol"] for m in mensajes if m["ts"] >= desde)
        resumen.append((dias, len(convs), sum(roles.values()), roles,
                        sum(1 for c in convs if c["hubo_staff"]), sum(1 for c in convs if c["hubo_bot"])))
        print(f"  ultimos_{dias}d.json: {len(convs)} conversaciones, {sum(roles.values())} mensajes {dict(roles)}")

    (OUT / "mapa_pacientes.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1), encoding="utf-8")
    primero = cobertura[0].astimezone(ART).strftime("%Y-%m-%d") if cobertura[0] else "?"
    leeme = [
        "# Conversaciones reales exportadas (datos de pacientes: NO subir al repo ni compartir)", "",
        f"Exportado el {ahora.astimezone(ART).strftime('%Y-%m-%d %H:%M')} (hora Argentina) desde la tabla `conversaciones` de Supabase v3.",
        f"La tabla tiene {cobertura[2]} mensajes en total; el mas viejo es del **{primero}**. "
        "Si un periodo pide mas dias que los que hay, el archivo solo trae lo que existe.", "",
        "## Archivos", "",
        "| archivo | conversaciones | mensajes | por rol | con staff | con bot |", "|---|---|---|---|---|---|"]
    for dias, nc, nm, roles, ns, nb in resumen:
        leeme.append(f"| ultimos_{dias}d.json | {nc} | {nm} | {dict(roles)} | {ns} | {nb} |")
    leeme += [
        "", "## Formato", "",
        "Cada archivo es una lista de conversaciones (una por paciente, ordenadas por inicio):",
        "```", '{ "paciente": "p_ab12cd", "n_mensajes": 12, "desde": "2026-09-30T21:42-03:00", "hasta": "...",',
        '  "hubo_staff": true, "hubo_bot": true,',
        '  "mensajes": [ { "t": "2026-09-30 21:42", "rol": "paciente|bot|staff|recordatorio", "texto": "..." } ] }', "```", "",
        "- **rol**: `paciente` escribio el paciente · `bot` respondio Asiri · `staff` escribio la Dra./secretaria (desde el celular del consultorio o el panel) · `recordatorio` mensaje automatico del cron de recordatorios.",
        "- Los telefonos son seudonimos (`p_xxxxxx`; `tel_LUCAS`, `tel_IRINA`, `tel_DRA` son el staff). `mapa_pacientes.json` dice a quien corresponde cada uno: es solo para uso local.",
        "- Se quito el prefijo interno `[ATENCION HUMANA ...]` de los mensajes del staff. Los marcadores `[IMAGEN]`, `[AUDIO]`, `[DOCUMENTO]`, `[MEDIA:id]` quedan tal cual (describen adjuntos).",
        "- Los textos casi no se tocaron: se tapan las secuencias de 7 o mas digitos (telefonos, DNI, CBU) como `<nº>`; los NOMBRES y datos de salud que escribio el paciente siguen ahi.",
        "- Ojo con `staff` vs `bot`: el sub-flujo de cancelar/reprogramar del bot guarda sus respuestas con la marca de los mensajes del staff (bug conocido). Se reclasificaron como `bot` las que tienen voz inconfundible de Asiri; puede quedar alguna sin detectar.",
        "- `recordatorio` = el mensaje automatico que recibio el paciente; `interno` = nota del bot (no la vio el paciente); `recordatorio_test` = pruebas del workflow (ignorar).", "",
        "## Para que sirve", "",
        "Armar la matriz de casos normales y casos borde por funcion (agendar, confirmar, cancelar/reprogramar, precios y pagos, urgencias, general) "
        "y ver en que punto el bot deja de convertir (silencio, modo humano, derivacion) cuando el paciente ya queria cerrar.", "",
        "## Regenerar", "", "`python scripts/exportar_conversaciones_periodos.py` (solo lectura).", ""]
    (OUT / "LEEME.md").write_text("\n".join(leeme), encoding="utf-8")
    print(f"\nListo en {OUT}. Cobertura real de la tabla: desde {primero}.")


if __name__ == "__main__":
    main()
