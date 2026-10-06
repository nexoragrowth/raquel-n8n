# -*- coding: utf-8 -*-
"""
test_matriz_casos.py — Runner automatizado de la Matriz Oficial de 12 Casos de Prueba.
Envía payloads reales formato Evolution GO directamente a n8n, espera la respuesta y valida
contra los criterios de aceptación y prohibiciones de la tabla.

USO:
    python tests/test_matriz_casos.py              # Corre los casos clave
    python tests/test_matriz_casos.py onboarding   # Corre solo onboarding
    python tests/test_matriz_casos.py --all        # Corre la matriz completa
"""

import argparse, json, os, re, sys, time, uuid, urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib_env import env, require
from apply_media_entrantes import api, WF_ID

N8N = require("N8N_BASE_URL").rstrip("/")
PHONE_TEST = "5491161461034"  # Teléfono de pruebas admin

CASOS_MATRIZ = [
    {
        "id": "TC-01",
        "tag": "onboarding",
        "categoria": "Onboarding y Menú Guiado",
        "mensaje": "Buenas tardes",
        "espera": [r"(Asiri|Áurea|opci[oó]n|Tratamientos|Agendar|Precios|Ubicaci[oó]n)"],
        "no_espera": [r"derivar|secretaria\s+humana"],
        "pausa": 2
    },
    {
        "id": "TC-02",
        "tag": "ubicacion",
        "categoria": "Ubicación y Horarios (Fijo)",
        "mensaje": "Quisiera saber dónde queda el consultorio y los horarios de atención",
        "espera": [r"(Balcarce\s*(N[º°]?\s*)?37|2[º°]\s*piso|lunes\s+a\s+viernes)"],
        "no_espera": [r"derivar", r"derivando su caso"],
        "pausa": 3
    },
    {
        "id": "TC-05",
        "tag": "precios",
        "categoria": "Precios y Datos Bancarios",
        "mensaje": "Hola! Cuánto cuesta la primera consulta y a qué alias puedo transferir?",
        "espera": [r"50\.000", r"dra\.raquel\.aurea"],
        "no_espera": [r"40\.000"],
        "pausa": 3
    },
    {
        "id": "TC-06",
        "tag": "blanqueamiento",
        "categoria": "Tratamientos y Alcance Dental",
        "mensaje": "Hola, hacen blanqueamiento o limpieza profunda?",
        "espera": [r"(ortodoncia|valoraci[oó]n|50\.000)"],
        "pausa": 3
    },
    {
        "id": "TC-07",
        "tag": "cuota",
        "categoria": "Cuota Mensual Ortodoncia",
        "mensaje": "Ya estoy con los brackets puestos, cuánto se paga la cuota por mes?",
        "espera": [r"70\.000"],
        "no_espera": [r"50\.000"],
        "pausa": 3
    },
    {
        "id": "TC-09",
        "tag": "urgencia_guardia",
        "categoria": "Urgencias / Sin Guardia (Mariela Safe)",
        "mensaje": "Se me salió el alambre un domingo y me pincha, puedo ir ya a la clínica?",
        "espera": [r"(privado|turno previo|guardia)"],
        "no_espera": [r"venite", r"los esperamos", r"ahora mismo", r"salgan ya"],
        "pausa": 3
    },
    {
        "id": "TC-10",
        "tag": "cierre",
        "categoria": "Cierre y Silencio ([NO_REPLY])",
        "mensaje": "Muchas gracias por la información, que tengas buen día!",
        "espera": [],
        "es_silencio": True,
        "pausa": 3
    }
]


def enviar_msg(mensaje, sim_id, phone=PHONE_TEST):
    body = {
        "event": "messages.upsert",
        "instanceId": "raquel",
        "instanceName": "raquel",
        "data": {
            "Info": {
                "ID": sim_id,
                "Chat": f"{phone}@s.whatsapp.net",
                "Sender": f"{phone}@s.whatsapp.net",
                "IsFromMe": False,
                "IsGroup": False,
                "PushName": "Paciente Testing",
                "Timestamp": datetime.now(timezone.utc).isoformat(),
                "Type": "text"
            },
            "Message": {
                "conversation": mensaje
            }
        }
    }
    req = urllib.request.Request(
        f"{N8N}/webhook/evolution-v2",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status


def esperar_respuesta(sim_id, last_id, timeout_s=65):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(2)
        execs = api(f"/executions?workflowId={WF_ID}&limit=8").get("data", [])
        for e in execs:
            if int(e["id"]) <= last_id:
                continue
            edata = api(f"/executions/{e['id']}?includeData=true")
            rd = edata.get("data", {}).get("resultData", {}).get("runData", {})
            ef = rd.get("Edit Fields - Extraer Datos", [])
            try:
                kid = ef[0]["data"]["main"][0][0]["json"].get("key_id", "")
            except (IndexError, KeyError, TypeError):
                continue
            if kid != sim_id:
                continue
            partes = []
            for run in rd.get("Split en Mensajes", []):
                for it in (run.get("data", {}).get("main", [[]])[0] or []):
                    partes.append(str(it.get("json", {}).get("message", "")))
            return edata.get("status"), "\n".join(partes)
    return "timeout", ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filtro", nargs="?", default=None)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    casos = CASOS_MATRIZ
    if args.filtro:
        casos = [c for c in CASOS_MATRIZ if args.filtro.lower() in c["tag"] or args.filtro.upper() in c["id"]]
    elif not args.all:
        # Default: correr un subconjunto rápido y seguro
        casos = [c for c in CASOS_MATRIZ if c["tag"] in ["onboarding", "ubicacion", "precios", "urgencia_guardia"]]

    print("==================================================================")
    print(" 🏥 EJECUTOR DE PRUEBAS DE LA MATRIZ OFICIAL — BOT DRA. RAQUEL")
    print(f" Corriendo {len(casos)} casos de prueba | Teléfono destino: {PHONE_TEST}")
    print("==================================================================\n")

    resultados = []
    for c in casos:
        time.sleep(c.get("pausa", 0))
        sim_id = f"SIM_{uuid.uuid4().hex[:14].upper()}"
        last_execs = api(f"/executions?workflowId={WF_ID}&limit=1").get("data", [])
        last_id = int(last_execs[0]["id"]) if last_execs else 0

        print(f"[{c['id']}] {c['categoria']}")
        print(f"  • Mensaje: {c['mensaje']!r}")

        enviar_msg(c["mensaje"], sim_id)
        status, resp = esperar_respuesta(sim_id, last_id)

        fallas = []
        if c.get("es_silencio"):
            if resp.strip() != "":
                fallas.append(f"Se esperaba silencio total pero respondió: {resp[:100]}")
        else:
            fallas += [rx for rx in c["espera"] if not re.search(rx, resp, re.I)]
            fallas += [f"PROHIBIDO encontrado ({rx})" for rx in c.get("no_espera", []) if re.search(rx, resp, re.I)]

        ok = status == "success" and not fallas
        resultados.append((c["id"], c["categoria"], ok, resp, fallas))

        badge = "✅ PASS" if ok else "❌ FAIL"
        print(f"  • Resultado: {badge} (Status: {status})")
        if resp.strip():
            print(f"  • Respuesta bot: {resp.strip()[:180]}...")
        if fallas:
            print(f"  • Errores detectados: {fallas}")
        print("-" * 65)

    print("\n==================================================================")
    print(" 📊 RESUMEN FINAL DE LA BATERÍA")
    print("==================================================================")
    for cid, cat, ok, _, _ in resultados:
        print(f"  {'✅' if ok else '❌'} {cid} | {cat.ljust(35)} : {'APROBADO' if ok else 'FALLÓ'}")
    total_pass = sum(1 for _, _, ok, _, _ in resultados if ok)
    print(f"\nTotal: {total_pass}/{len(resultados)} Casos Aprobados.")


if __name__ == "__main__":
    main()
