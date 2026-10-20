# -*- coding: utf-8 -*-
"""
simular_mensaje_lucas.py — 2026-10-14 · simula que el celular de Lucas le escribe al número de la clínica: POSTea al webhook del v6
(/webhook/evolution-v2) un mensaje de TEXTO con el formato EXACTO de Evolution GO (copiado de un mensaje real). El bot lo procesa como
cualquier mensaje y la respuesta (del v7 si el número tiene la marca, ver flag_v7.py) le llega de verdad al WhatsApp de Lucas.

SOLO el número de Lucas (fijo): no sirve para hacerse pasar por pacientes. El token de la instancia se toma de la última ejecución real del v6
(viene en el cuerpo que manda Evolution) y no se imprime.

USO:  python scripts/simular_mensaje_lucas.py "hola"
      python scripts/simular_mensaje_lucas.py "¿cuánto sale la primera consulta?" --esperar   # espera la ejecución y muestra qué camino siguió
Después de probar: limpieza (regla 9) con scripts/limpiar_numero_demo.py y flag_v7.py --off.
"""
import argparse, json, sys, time, urllib.request, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tiempos_v7 import api

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
V6 = "O155MqHgOSaNZ9ye"
LUCAS = "5491161461034"
WEBHOOK = "https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2"


def instancia():
    """instanceId / instanceName / instanceToken del cuerpo de un mensaje real reciente (Evolution los manda en cada webhook)."""
    for e in api(f"/executions?workflowId={V6}&limit=10").get("data", []):
        try:
            rd = api(f"/executions/{e['id']}?includeData=true")["data"]["resultData"]["runData"]
            b = rd["Webhook - Evolution API"][0]["data"]["main"][0][0]["json"].get("body", {})
            if b.get("instanceToken") and b.get("event") == "Message":
                return {k: b[k] for k in ("instanceId", "instanceName", "instanceToken")}
        except Exception:
            continue
    raise SystemExit("No encontré una ejecución real reciente del v6 para copiar los datos de la instancia.")


def cuerpo(texto, inst):
    ahora = datetime.now(timezone(timedelta(hours=-3))).replace(microsecond=0).isoformat()
    jid = f"{LUCAS}@s.whatsapp.net"
    return {
        "data": {
            "Info": {"AddressingMode": "", "BroadcastListOwner": "", "BroadcastRecipients": None, "Category": "", "Chat": jid, "DeviceSentMeta": None, "Edit": "",
                     "ID": "SIMV7" + uuid.uuid4().hex[:15].upper(), "IsFromMe": False, "IsGroup": False, "MediaType": "",
                     "MsgBotInfo": {"EditSenderTimestampMS": "0001-01-01T00:00:00Z", "EditTargetID": "", "EditType": ""},
                     "MsgMetaInfo": {"DeprecatedLIDSession": None, "TargetChat": "", "TargetID": "", "TargetSender": "", "ThreadMessageID": "", "ThreadMessageSenderJID": ""},
                     "Multicast": False, "PushName": "Lucas", "RecipientAlt": "", "Sender": jid, "SenderAlt": "", "ServerID": 0, "Timestamp": ahora, "Type": "text", "VerifiedName": None},
            "IsBotInvoke": False, "IsDocumentWithCaption": False, "IsEdit": False, "IsEphemeral": False, "IsLottieSticker": False, "IsViewOnce": False,
            "IsViewOnceV2": False, "IsViewOnceV2Extension": False,
            "Message": {"conversation": texto},
            "NewsletterMeta": None, "RetryCount": 0, "SourceWebMsg": None, "UnavailableRequestID": "",
        },
        "event": "Message", **inst,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("texto"); ap.add_argument("--esperar", action="store_true")
    a = ap.parse_args()
    ultimo = int((api(f"/executions?workflowId={V6}&limit=1").get("data") or [{"id": 0}])[0]["id"])
    req = urllib.request.Request(WEBHOOK, data=json.dumps(cuerpo(a.texto, instancia())).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        print(f"enviado «{a.texto}» → webhook {r.status}")
    if not a.esperar:
        return
    for _ in range(36):   # hasta ~3 min (buffer de 22 s + cerebro)
        time.sleep(5)
        for e in api(f"/executions?workflowId={V6}&limit=5").get("data", []):
            if int(e["id"]) <= ultimo or e.get("status") == "running":
                continue
            rd = api(f"/executions/{e['id']}?includeData=true")["data"]["resultData"]["runData"]
            try:
                tel = rd["Preparar Mensaje Final"][0]["data"]["main"][0][0]["json"].get("phone", "")
            except Exception:
                tel = ""
            if not str(tel).endswith(LUCAS[-7:]):
                continue
            rama = "v7" if "V7: ¿Vivo?" in rd and rd["V7: ¿Vivo?"][0]["data"]["main"][0] else "v6"
            salida = ""
            if "V7: Adaptador" in rd:
                try:
                    salida = rd["V7: Adaptador"][0]["data"]["main"][0][0]["json"].get("output", "")
                except Exception:
                    pass
            print(f"ejecución {e['id']} ({e.get('status')}) → {rama}" + (f"\nrespuesta: {salida}" if salida else ""))
            return
    print("no apareció la ejecución en 3 min (puede seguir procesando; revisá el WhatsApp).")


if __name__ == "__main__":
    main()
