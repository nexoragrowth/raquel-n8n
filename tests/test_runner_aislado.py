# -*- coding: utf-8 -*-
"""
test_runner_aislado.py — Runner de testing sintético con Context-Seeding y Wipeout por ronda.

POR CADA CASO:
  1. Wipeout: Limpia la memoria (n8n_chat_histories) y takeover del teléfono de prueba.
  2. Seed: Inyecta historial conversacional sintético previo (si el caso lo requiere).
  3. Disparo: Envía el mensaje del paciente a probar a través del webhook de n8n.
  4. Aserción: Valida en vivo que la respuesta cumpla las reglas estrictas (espera, no_espera, sin silencio accidental).
  5. Cleanup final: Deja el teléfono limpio para la siguiente ronda.

USO:
    python tests/test_runner_aislado.py              # Corre casos clave aislados
    python tests/test_runner_aislado.py --all        # Corre la suite completa (10 casos)
    python tests/test_runner_aislado.py TC-04        # Corre solo el caso TC-04
"""

import argparse, json, re, sys, time, uuid, urllib.request, psycopg2
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib_env import env, require

N8N = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
KEY = require("N8N_API_KEY")
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PHONE_TEST = "5491161461034"  # Teléfono de prueba aislado (Lucas admin)

# Definición de Casos con Context-Seeding
SUITE_AISLADA = [
    {
        "id": "TC-01",
        "tag": "onboarding",
        "categoria": "Primer Contacto (Onboarding)",
        "contexto_previo": [],  # Memoria limpia
        "mensaje": "Buenas tardes",
        "espera": [r"(Asiri|Áurea|opci[oó]n|Tratamientos|Agendar|Precios|Ubicaci[oó]n)"],
        "no_espera": [r"derivar", r"secretaria\s+humana"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-02",
        "tag": "ubicacion",
        "categoria": "Ubicación Física del Consultorio",
        "contexto_previo": [],
        "mensaje": "Hola, en qué dirección atienden y cuáles son los horarios?",
        "espera": [r"(Balcarce\s*(N[º°]?\s*)?37|2[º°]\s*piso)"],
        "no_espera": [r"derivar", r"derivando su caso"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-03",
        "tag": "anuncio",
        "categoria": "Lead de Anuncio de Instagram",
        "contexto_previo": [],
        "mensaje": "¡Hola! Quiero más información",
        "espera": [r"(Asiri|Raquel|ortodoncia|consulta|50\.000|opci[oó]n)"],
        "no_espera": [r"\[NO_REPLY\]"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-04",
        "tag": "agendar_eleccion",
        "categoria": "Elección de Turno tras Oferta de Horarios (Anti-Silencio)",
        "contexto_previo": [
            {"role": "human", "text": "Quisiera agendar un turno para consulta"},
            {"role": "ai", "text": "Tenemos los próximos turnos disponibles:\nMartes 20 de Octubre a las 8:00 hs\nMiércoles 21 de Octubre a las 15:00 hs\n¿Cuál de estos horarios le queda cómodo?"}
        ],
        "mensaje": "El martes 20 a las 8",
        "espera": [r"(nombre|apellido|dni|datos|agendamos|confirmar|8:00)"],
        "no_espera": [r"\[NO_REPLY\]", r"opci[oó]n 1"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-05",
        "tag": "reprogramar_duda",
        "categoria": "Consulta de Posibilidad de Cambio (Caso Julieta Limpitay)",
        "contexto_previo": [
            {"role": "ai", "text": "Su turno de control está programado para el Jueves a las 09:00 hs."}
        ],
        "mensaje": "Buenos días quería consultar qué posibilidad hay de cambiar el turno para el horario de la tarde?",
        "espera": [r"(tarde|horario|disponib|cambiar|reprogramar|secretaria)"],
        "no_espera": [r"\[NO_REPLY\]"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-06",
        "tag": "urgencia",
        "categoria": "Urgencia / Dolor (Guardia Privada)",
        "contexto_previo": [],
        "mensaje": "Se me despegó el bracket y me está pinchando y sangrando, puedo ir ahora?",
        "espera": [r"(video|cera|guardia|consultorio privado|turno previo|avisamos|Dra)"],
        "no_espera": [r"venite\s+ahora", r"los\s+esperamos", r"venga\s+ya"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-07",
        "tag": "precios",
        "categoria": "Precios Oficiales y Datos Bancarios",
        "contexto_previo": [],
        "mensaje": "Cuánto cuesta la primera consulta y a qué alias puedo transferir?",
        "espera": [r"50\.000", r"dra\.raquel\.aurea"],
        "no_espera": [r"40\.000"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-08",
        "tag": "blanqueamiento",
        "categoria": "Tratamientos Fuera de Foco (Blanqueamiento / Limpieza)",
        "contexto_previo": [],
        "mensaje": "Hola! Hacen limpiezas dentales comunes o blanqueamiento?",
        "espera": [r"(ortodoncia|valoraci[oó]n|50\.000)"],
        "no_espera": [r"no hacemos nada"],
        "prohibir_silencio": True,
    },
    {
        "id": "TC-09",
        "tag": "cierre",
        "categoria": "Cierre Conversacional (Silencio Intencional o Despedida Breve)",
        "contexto_previo": [
            {"role": "human", "text": "¿Dónde queda el consultorio?"},
            {"role": "ai", "text": "Nos encontramos en Balcarce Nº37, 2º piso."}
        ],
        "mensaje": "Muchas gracias, impecable!",
        "espera": [],
        "no_espera": [r"¿En qué puedo ayudarte hoy\? Podés elegir una opción:", r"opci[oó]n 1"],
        "es_cierre": True,
    }
]

def get_db_conn():
    conn = psycopg2.connect(
        host=env("SUPABASE_V3_DB_HOST"),
        port=env("SUPABASE_V3_DB_PORT"),
        dbname=env("SUPABASE_V3_DB_NAME"),
        user=env("SUPABASE_V3_DB_USER"),
        password=env("SUPABASE_V3_DB_PASSWORD"),
        sslmode="require"
    )
    conn.autocommit = True
    return conn

def api(path):
    req = urllib.request.Request(
        f"{N8N}/api/v1{path}",
        headers={"X-N8N-API-KEY": KEY, "accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def wipeout_memoria_y_takeover(phone):
    conn = get_db_conn()
    cur = conn.cursor()
    # 1. Borrar memoria n8n LangChain
    cur.execute("DELETE FROM n8n_chat_histories WHERE session_id = %s;", (phone,))
    # 2. Resetear takeover en pacientes
    cur.execute("UPDATE pacientes SET human_takeover = false, human_takeover_at = NULL WHERE telefono = %s;", (phone,))
    cur.close()
    conn.close()

def seed_contexto(phone, mensajes):
    if not mensajes:
        return
    conn = get_db_conn()
    cur = conn.cursor()
    for m in mensajes:
        tipo = m["role"] # 'human' o 'ai'
        content = m["text"]
        payload = {
            "type": tipo,
            "content": content,
            "additional_kwargs": {"seeded_test": True},
            "response_metadata": {}
        }
        cur.execute(
            "INSERT INTO n8n_chat_histories (session_id, message) VALUES (%s, %s::jsonb);",
            (phone, json.dumps(payload))
        )
    cur.close()
    conn.close()

def enviar_webhook(texto, sim_id):
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = int(time.time())
    payload = {
        "event": "messages.upsert",
        "instance": "raquel",
        "data": {
            "source": "test_e2e_suite",
            "Info": {
                "ID": sim_id,
                "Chat": f"{PHONE_TEST}@s.whatsapp.net",
                "Sender": f"{PHONE_TEST}@s.whatsapp.net",
                "IsFromMe": False,
                "IsGroup": False,
                "PushName": "Lucas Test",
                "Timestamp": now_iso
            },
            "Message": {
                "conversation": texto
            }
        },
        "destination": f"https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2",
        "date_time": now_iso,
        "sender": f"{PHONE_TEST}@s.whatsapp.net",
        "server_url": "http://127.0.0.1:8080",
        "apikey": "local-test-key"
    }

    url = f"{N8N}/webhook/evolution-v2"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status

def esperar_ejecucion(sim_id, last_id, timeout_s=70):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(2)
        execs = api(f"/executions?workflowId={WF_ID}&limit=5").get("data", [])
        for e in execs:
            eid = int(e["id"])
            if eid <= last_id:
                continue
            edata = api(f"/executions/{eid}?includeData=true")
            rd = edata.get("data", {}).get("resultData", {}).get("runData", {})
            ef = rd.get("Edit Fields - Extraer Datos", [])
            try:
                kid = ef[0]["data"]["main"][0][0]["json"].get("key_id", "")
            except (IndexError, KeyError, TypeError):
                continue
            if kid != sim_id:
                continue
            
            # Buscar el output real generado en los diferentes nodos de salida
            partes = []
            for run in rd.get("Split en Mensajes", []):
                for it in (run.get("data", {}).get("main", [[]])[0] or []):
                    partes.append(str(it.get("json", {}).get("message", "")))
            
            # Chequear si triaje o router mandaron texto canned o video
            if not partes:
                for nname in [
                    "Triaje: Enviar Video",
                    "Triaje: Enviar Texto Escalada",
                    "Triaje: Enviar Texto Canned",
                    "Triaje: Preparar Video",
                    "Triaje: Preparar Pregunta",
                    "Triaje: Preparar Escalada",
                    "Gate Canned Directo",
                    "Evolution: Enviar Texto"
                ]:
                    for run in rd.get(nname, []):
                        for it in (run.get("data", {}).get("main", [[]])[0] or []):
                            j = it.get("json", {})
                            msg_data = j.get("data", {}).get("Message", {})
                            txt = (
                                j.get("send", {}).get("text") or
                                msg_data.get("videoMessage", {}).get("caption") or
                                msg_data.get("extendedTextMessage", {}).get("text") or
                                j.get("caption") or
                                j.get("texto") or
                                j.get("message") or
                                j.get("content") or
                                j.get("text")
                            )
                            if txt:
                                partes.append(str(txt))

            return edata.get("status"), "\n".join(partes)
    return "timeout", ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("filtro", nargs="?", default=None)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    casos = SUITE_AISLADA
    if args.filtro:
        casos = [c for c in SUITE_AISLADA if args.filtro.upper() in c["id"] or args.filtro.lower() in c["tag"]]
    elif not args.all:
        # Por defecto corre los 4 casos más sensibles a la memoria
        casos = [c for c in SUITE_AISLADA if c["id"] in ["TC-01", "TC-03", "TC-04", "TC-05"]]

    print("==================================================================")
    print(" 🧪 SUITE DE TESTING AISLADO CON CONTEXT-SEEDING & WIPEOUT")
    print(f" Corriendo {len(casos)} caso(s) en ambiente estéril | Tel: {PHONE_TEST}")
    print("==================================================================\n")

    aprobados = 0
    total = len(casos)

    # Wipeout preventivo inicial antes de comenzar la suite
    wipeout_memoria_y_takeover(PHONE_TEST)
    time.sleep(2)

    for c in casos:
        cid = c["id"]
        print(f"── [{cid}] {c['categoria']} ──")
        
        # 1. Wipeout previo
        wipeout_memoria_y_takeover(PHONE_TEST)
        
        # 2. Seed contextual si aplica
        if c.get("contexto_previo"):
            seed_contexto(PHONE_TEST, c["contexto_previo"])
            print(f"  🌱 Sembrado contexto previo ({len(c['contexto_previo'])} mensajes)")
        else:
            print("  ✨ Memoria estéril inicial (Wipeout completado)")

        # 3. Disparo del mensaje
        sim_id = f"SIM_{uuid.uuid4().hex[:12].upper()}"
        last_execs = api(f"/executions?workflowId={WF_ID}&limit=1").get("data", [])
        last_id = int(last_execs[0]["id"]) if last_execs else 0

        print(f"  📨 Mensaje enviado: \"{c['mensaje']}\"")
        enviar_webhook(c["mensaje"], sim_id)

        # 4. Esperar y auditar resultado
        status, resp = esperar_ejecucion(sim_id, last_id)
        
        errores = []
        if status == "timeout":
            errores.append("Execution Timeout (el webhook no terminó en 70s)")
        elif c.get("es_cierre"):
            # En cierre se tolera silencio total o una despedida cordial breve
            if resp.strip() != "":
                for nexp in c.get("no_espera", []):
                    if re.search(nexp, resp, re.IGNORECASE):
                        errores.append(f"Disparó patrón PROHIBIDO en cierre: /{nexp}/")
                if len(resp.split()) > 45:
                    errores.append(f"Respuesta de cierre demasiado larga ({len(resp.split())} palabras)")
        elif c.get("es_silencio"):
            if resp.strip() != "":
                errores.append(f"Se esperaba silencio total pero respondió: {resp[:120]}")
        else:
            if not resp or resp.strip() == "":
                errores.append("El bot clavó el visto (0 respuestas o [NO_REPLY] accidental)")
            else:
                for exp in c.get("espera", []):
                    if not re.search(exp, resp, re.IGNORECASE):
                        errores.append(f"Falta patrón esperado: /{exp}/")
                for nexp in c.get("no_espera", []):
                    if re.search(nexp, resp, re.IGNORECASE):
                        errores.append(f"Disparó patrón PROHIBIDO: /{nexp}/")

        if not errores:
            aprobados += 1
            print("  ✅ [PASS] Comportamiento esperado verificado")
            if resp:
                print(f"     Respuesta: {resp[:120].replace(chr(10), ' ')}...")
            else:
                print("     Respuesta: (Silencio intencional respetado)")
        else:
            print("  ❌ [FAIL] Fallas detectadas:")
            for err in errores:
                print(f"     • {err}")
            if resp:
                print(f"     Respuesta real: {resp[:150].replace(chr(10), ' ')}...")

        print()
        # 5. Cleanup final + sleep de estabilización por llamadas async a notify-grupo
        if cid == "TC-06":
            print("  ⏳ Esperando que 'Helper - Notify Grupo' complete su timer interno de 20s...")
            time.sleep(22)
        else:
            time.sleep(2)
            
        wipeout_memoria_y_takeover(PHONE_TEST)
        time.sleep(1)

    print("==================================================================")
    print(f" 📊 RESULTADOS SUITE: {aprobados}/{total} CASOS EXITOSOS")
    print("==================================================================")

if __name__ == "__main__":
    main()
