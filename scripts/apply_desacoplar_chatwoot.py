# -*- coding: utf-8 -*-
"""
apply_desacoplar_chatwoot.py — Desacople definitivo de Chatwoot y unificación en Panel/Supabase.

QUÉ HACE:
1. En Workflow Principal v6 (O155MqHgOSaNZ9ye):
   - Inbound:
     * Reemplaza 'Existe paciente?' + 'Chatwoot - Buscar Conversacion' + 'Verificar Label Humano'
       por 'Consultar Takeover Paciente' (Postgres query directa a Supabase v3:
       SELECT COALESCE(human_takeover, false) AS hasHumanoLabel FROM pacientes WHERE telefono = $1)
     * 'Bot Activo?' lee directamente hasHumanoLabel del Postgres node.
     * Si no existe el paciente en la tabla, el query devuelve 0 filas, continueOnFail/fallback asegura hasHumanoLabel: false.
   - Re-check Banlist:
     * 'Banlist Validator' conecta directo a 'Necesita Formatting?' (elimina Re-check Humano, Hay humano ahora?, Humano aparecio?, Aviso humano tomo chat).
   - Gate Humano Final:
     * En lugar de llamar al HTTP endpoint de Chatwoot /api/v1/accounts/1/contacts/{id}/conversations,
       hace fetch a Supabase PostgREST (o fail-open) para comprobar human_takeover.
   - Outbound fromMe:
     * Elimina los 5 nodos de Chatwoot ('CW Search Contact', 'CW Extract Conv', 'CW Get Conversations', 'CW Pick Conv', 'CW Set Label humano').
     * Inserta 'Activar Takeover (fromMe)' (Postgres query:
       INSERT INTO pacientes (telefono, human_takeover) VALUES ($1, true) ON CONFLICT (telefono) DO UPDATE SET human_takeover = true, updated_at = now())
     * Conecta 'Postgres - Save fromMe' -> 'Activar Takeover (fromMe)' -> 'Media: Preparar (staff)'.
   - Triaje Urgencias:
     * Limpia la llamada a Chatwoot en 'Triaje: Decidir'.

2. En Workflow 'Panel — acciones staff' (jzxb5zUKCaJcvCgp):
   - Reemplaza el nodo 'Label Chatwoot' por 'Sincronizar Takeover Supabase' (Postgres node actualizando pacientes.human_takeover).

3. En Workflow 'Helper - Notify Grupo' (S5U6tSipzlgFHCkf):
   - En lugar de 'Chatwoot Apply' (que ponía label humano en Chatwoot), pone 'Takeover Supabase'
     (INSERT INTO pacientes (telefono, human_takeover) VALUES ($1, true) ON CONFLICT (telefono) DO UPDATE SET human_takeover = true).

4. En Workflows Satélite de Chatwoot:
   - Desactiva 'Human Takeover' (w7BBpZeEwZnpCX1q) que escuchaba webhooks de Chatwoot.
   - Desactiva 'Auto Reactivar' (fosfga62zNaN0qrx) que chequeaba labels de Chatwoot.

REGLAS DURAS:
- Dry-run por defecto.
- Backups timestamped en workflows/history/ antes y después.
- Preservar webhookId 'evo-webhook-v2'.
- Filtrar settings permitidas para evitar 400.
"""

import argparse, copy, difflib, json, os, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env
from apply_media_entrantes import api, clean_settings, PUT_KEYS, WF_ID, PG_CRED_ID

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"

WID_V6 = WF_ID  # O155MqHgOSaNZ9ye
WID_PANEL_STAFF = "jzxb5zUKCaJcvCgp"
WID_HELPER_NOTIFY = "S5U6tSipzlgFHCkf"
WID_HUMAN_TAKEOVER = "w7BBpZeEwZnpCX1q"
WID_AUTO_REACTIVAR = "fosfga62zNaN0qrx"


def backup_workflow(wid, label):
    wf = api(f"/workflows/{wid}")
    ts = int(time.time())
    dest = HIST / f"{wid}_{label}_{ts}.json"
    HIST.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False)
    print(f"  [BACKUP] Guardado {dest.name}")
    return wf


def patch_v6(wf):
    nodes = {n["name"]: n for n in wf["nodes"]}
    conns = wf["connections"]

    # --- 1. INBOUND: Consultar Takeover Paciente ---
    # Creamos el nodo Postgres
    inbound_pg = {
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT COALESCE(human_takeover, false) AS \"hasHumanoLabel\" FROM pacientes WHERE telefono = $1 LIMIT 1",
            "options": {
                "queryReplacement": "={{ $('Preparar Mensaje Final').first().json.phone }}"
            }
        },
        "id": "pg-inbound-takeover",
        "name": "Consultar Takeover Paciente",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [7872, 608],
        "alwaysOutputData": True,
        "continueOnFail": True,
        "credentials": {
            "postgres": {
                "id": PG_CRED_ID,
                "name": "Postgres Supabase Nexora v3"
            }
        }
    }

    # Modificar 'Bot Activo?' para que interprete correctamente si no hay filas (false)
    bot_activo = nodes["Bot Activo?"]
    bot_activo["parameters"] = {
        "conditions": {
            "options": {
                "caseSensitive": True,
                "leftValue": "",
                "typeValidation": "strict"
            },
            "conditions": [
                {
                    "id": "bot-check-condition",
                    "leftValue": "={{ $json.hasHumanoLabel === true }}",
                    "rightValue": True,
                    "operator": {
                        "type": "boolean",
                        "operation": "equals"
                    }
                }
            ],
            "combinator": "and"
        },
        "options": {}
    }

    # Nodos a eliminar del inbound
    del_inbound = {"Existe paciente?", "Chatwoot - Buscar Conversacion", "Verificar Label Humano"}

    # --- 2. RE-CHECK BANLIST: Banlist -> Necesita Formatting? ---
    del_recheck = {"Re-check Humano", "Hay humano ahora?", "Humano aparecio?", "Aviso humano tomo chat"}

    # --- 3. GATE HUMANO FINAL ---
    gate_final = nodes["Gate Humano Final"]
    gate_final_code = """// Gate Humano Final (2026-10-05): chequeo directo en Supabase v3 via PostgREST justo antes de enviar.
const items = $input.all();
const phone = ($('Preparar Mensaje Final').first().json.phone || '').toString();
let hasHumano = false;

try {
  const res = await this.helpers.httpRequest({
    method: 'GET',
    url: 'https://eoizfjsyejixjzwgzwkt.supabase.co/rest/v1/pacientes?select=human_takeover&telefono=eq.' + phone,
    headers: {
      'apikey': 'sb_secret_99fBw8bH9gR-E7W8J_V1fG',
      'Authorization': 'Bearer sb_secret_99fBw8bH9gR-E7W8J_V1fG'
    },
    json: true,
  });
  if (Array.isArray(res) && res.length > 0 && res[0].human_takeover === true) {
    hasHumano = true;
  }
} catch (e) {
  hasHumano = false; // fail-open
}

if (!hasHumano) {
  return items; // sin humano -> enviar normal
}

// Humano tomó durante el tail -> NO enviar y avisar al grupo
const output = ($('Banlist Validator').first().json.output || '').toString().trim();
if (output && output !== '[NO_REPLY]') {
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
      qs: {
        phone: phone,
        resumen: 'El bot detecto que el chat esta en Modo Humano y no envio su respuesta. Tenia listo: «' + output + '»',
        silencioso: 'true'
      },
      json: true,
    });
  } catch (e) {
    console.log('gate humano final aviso fail:', e.message);
  }
}
return [];
"""
    gate_final["parameters"]["jsCode"] = gate_final_code

    # --- 4. OUTBOUND fromMe: Activar Takeover (fromMe) ---
    outbound_pg = {
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO pacientes (telefono, human_takeover, updated_at) VALUES ($1, true, now()) ON CONFLICT (telefono) DO UPDATE SET human_takeover = true, updated_at = now()",
            "options": {
                "queryReplacement": "={{ $json.session_id }}"
            }
        },
        "id": "pg-outbound-takeover",
        "name": "Activar Takeover (fromMe)",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [5200, 752],
        "alwaysOutputData": True,
        "continueOnFail": True,
        "credentials": {
            "postgres": {
                "id": PG_CRED_ID,
                "name": "Postgres Supabase Nexora v3"
            }
        }
    }

    del_outbound = {"CW Search Contact", "CW Extract Conv", "CW Get Conversations", "CW Pick Conv", "CW Set Label humano"}

    # --- 5. TRIAJE DECIDIR ---
    triaje_decidir = nodes["Triaje: Decidir"]
    td_code = triaje_decidir["parameters"]["jsCode"]
    # Reemplazar el bloque de chatwoot en triaje decidir por chequeo supabase
    cw_block_needle = '// ---- Re-check de "humano atendiendo" justo antes de mandar algo al paciente (fail-open, como Gate Humano Final) ----'
    if cw_block_needle in td_code:
        # Reemplazamos la lógica interna del try/catch
        old_part = td_code[td_code.find(cw_block_needle):td_code.find('// ---- Payloads canned (100% de tabla) ----')]
        new_part = """// ---- Re-check de "humano atendiendo" en Supabase v3 (fail-open) ----
if (["video", "pregunta", "cerrar"].includes(d.ruta)) {
  try {
    const res = await this.helpers.httpRequest({
      method: "GET",
      url: "https://eoizfjsyejixjzwgzwkt.supabase.co/rest/v1/pacientes?select=human_takeover&telefono=eq." + (ev.phone || ""),
      headers: {
        apikey: "sb_secret_99fBw8bH9gR-E7W8J_V1fG",
        Authorization: "Bearer sb_secret_99fBw8bH9gR-E7W8J_V1fG"
      },
      json: true,
    });
    if (Array.isArray(res) && res.length > 0 && res[0].human_takeover === true) {
      d.ruta = "silencio";
      d.razon = "humano_atendiendo";
    }
  } catch (e) { /* fail-open */ }
}

"""
        td_code = td_code.replace(old_part, new_part)
        triaje_decidir["parameters"]["jsCode"] = td_code

    # --- FILTRAR NODOS ---
    to_delete = del_inbound | del_recheck | del_outbound
    new_nodes = [n for n in wf["nodes"] if n["name"] not in to_delete]
    new_nodes.append(inbound_pg)
    new_nodes.append(outbound_pg)
    wf["nodes"] = new_nodes

    # --- RECONECTAR ---
    # Limpiar conexiones viejas
    for d in to_delete:
        conns.pop(d, None)
    for src in list(conns.keys()):
        for otype in list(conns[src].keys()):
            new_groups = []
            for g in conns[src][otype]:
                filtered = [c for c in g if c.get("node") not in to_delete]
                if filtered:
                    new_groups.append(filtered)
            conns[src][otype] = new_groups

    # 1. Buffer: Limpiar -> Consultar Takeover Paciente
    conns["Buffer: Limpiar"] = {"main": [[{"node": "Consultar Takeover Paciente", "type": "main", "index": 0}]]}
    # 2. Consultar Takeover Paciente -> Bot Activo?
    conns["Consultar Takeover Paciente"] = {"main": [[{"node": "Bot Activo?", "type": "main", "index": 0}]]}
    # 3. Banlist Validator -> Necesita Formatting? + Banlist Shadow - Prep
    conns["Banlist Validator"] = {"main": [
        [
            {"node": "Necesita Formatting?", "type": "main", "index": 0},
            {"node": "Banlist Shadow - Prep", "type": "main", "index": 0}
        ]
    ]}
    # 4. Postgres - Save fromMe -> Activar Takeover (fromMe) -> Media: Preparar (staff)
    conns["Postgres - Save fromMe"] = {"main": [[{"node": "Activar Takeover (fromMe)", "type": "main", "index": 0}]]}
    conns["Activar Takeover (fromMe)"] = {"main": [[{"node": "Media: Preparar (staff)", "type": "main", "index": 0}]]}

    return wf


def patch_helper_notify(wf):
    nodes = {n["name"]: n for n in wf["nodes"]}
    conns = wf["connections"]

    # Reemplazar 'Chatwoot Apply' por un Postgres node que active takeover
    takeover_pg = {
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO pacientes (telefono, human_takeover, updated_at) VALUES ($1, true, now()) ON CONFLICT (telefono) DO UPDATE SET human_takeover = true, updated_at = now()",
            "options": {
                "queryReplacement": "={{ $('Webhook').first().json.query?.phone || $('Webhook').first().json.body?.phone || '' }}"
            }
        },
        "id": "pg-helper-takeover",
        "name": "Activar Takeover Paciente",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [700, 300],
        "alwaysOutputData": True,
        "continueOnFail": True,
        "credentials": {
            "postgres": {
                "id": PG_CRED_ID,
                "name": "Postgres Supabase Nexora v3"
            }
        }
    }

    # Remover Chatwoot Apply
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Chatwoot Apply"]
    wf["nodes"].append(takeover_pg)

    # Actualizar conexiones
    conns.pop("Chatwoot Apply", None)
    conns["Esperar respuesta del bot (20s)"] = {"main": [[{"node": "Activar Takeover Paciente", "type": "main", "index": 0}]]}

    return wf


def patch_panel_staff(wf):
    nodes = {n["name"]: n for n in wf["nodes"]}
    conns = wf["connections"]

    # Reemplazar 'Label Chatwoot' por 'Sincronizar Takeover Supabase'
    sync_pg = {
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO pacientes (telefono, human_takeover, updated_at) VALUES ($1, $2, now()) ON CONFLICT (telefono) DO UPDATE SET human_takeover = $2, updated_at = now()",
            "options": {
                "queryReplacement": "={{ $('Validar secreto').first().json.telefono }}, ={{ $('Validar secreto').first().json.humano }}"
            }
        },
        "id": "pg-panel-takeover",
        "name": "Sincronizar Takeover Supabase",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [2360, 200],
        "alwaysOutputData": True,
        "continueOnFail": True,
        "credentials": {
            "postgres": {
                "id": PG_CRED_ID,
                "name": "Postgres Supabase Nexora v3"
            }
        }
    }

    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Label Chatwoot"]
    wf["nodes"].append(sync_pg)

    # Conexiones
    conns.pop("Label Chatwoot", None)
    # ¿Es envío? [false] -> Sincronizar Takeover Supabase
    conns["¿Es envío?"] = {
        "main": [
            conns["¿Es envío?"]["main"][0],  # true branch -> ¿Con media?
            [{"node": "Sincronizar Takeover Supabase", "type": "main", "index": 0}]  # false branch
        ]
    }
    # Guardar en memoria -> Sincronizar Takeover Supabase
    conns["Guardar en memoria"] = {"main": [[{"node": "Sincronizar Takeover Supabase", "type": "main", "index": 0}]]}
    # Sincronizar Takeover Supabase -> Responder 200
    conns["Sincronizar Takeover Supabase"] = {"main": [[{"node": "Responder 200", "type": "main", "index": 0}]]}

    return wf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica los cambios a producción")
    args = parser.parse_args()

    print("==================================================================")
    print(" 🚀 DESACOPLE TOTAL DE CHATWOOT -> UNIFICACIÓN EN SUPABASE / PANEL")
    print("==================================================================\n")

    # 1. Backups
    print("📦 [1/5] Realizando backups preventivos...")
    v6_raw = backup_workflow(WID_V6, "PRE_desacoplar_cw")
    helper_raw = backup_workflow(WID_HELPER_NOTIFY, "PRE_desacoplar_cw")
    panel_raw = backup_workflow(WID_PANEL_STAFF, "PRE_desacoplar_cw")

    # 2. Patch v6
    print("\n🔧 [2/5] Modificando workflow principal v6...")
    v6_patched = patch_v6(copy.deepcopy(v6_raw))
    wh = next((n for n in v6_patched["nodes"] if n["name"] == "Webhook - Evolution API"), None)
    assert wh and wh.get("webhookId") == "evo-webhook-v2", "ERROR: evo-webhook-v2 perdido en v6"
    print(f"  • Nodos v6: {len(v6_raw['nodes'])} -> {len(v6_patched['nodes'])} (eliminados 12 nodos CW, sumados 2 PG)")

    # 3. Patch Helper
    print("\n🔧 [3/5] Modificando Helper - Notify Grupo...")
    helper_patched = patch_helper_notify(copy.deepcopy(helper_raw))
    print(f"  • Chatwoot Apply reemplazado por Activar Takeover Paciente (Postgres)")

    # 4. Patch Panel Staff
    print("\n🔧 [4/5] Modificando Panel — acciones staff...")
    panel_patched = patch_panel_staff(copy.deepcopy(panel_raw))
    print(f"  • Label Chatwoot reemplazado por Sincronizar Takeover Supabase (Postgres)")

    if not args.apply:
        print("\n" + "="*50)
        print(" [DRY-RUN] Simulación exitosa. No se realizaron cambios.")
        print(" Ejecuta con --apply para subir cambios y desactivar satélites.")
        print("="*50)
        return

    # 5. Aplicar cambios PUT
    print("\n🚀 [5/5] Aplicando cambios a producción...")

    def put_wf(wid, payload):
        body = {k: payload[k] for k in PUT_KEYS if k in payload}
        body["settings"] = clean_settings(payload.get("settings", {}))
        return api(f"/workflows/{wid}", method="PUT", payload=body)

    # Subir Helper
    put_wf(WID_HELPER_NOTIFY, helper_patched)
    print(f"  ✅ Helper Notify Grupo actualizado.")

    # Subir Panel Staff
    put_wf(WID_PANEL_STAFF, panel_patched)
    print(f"  ✅ Panel Acciones Staff actualizado.")

    # Subir v6
    put_wf(WID_V6, v6_patched)
    print(f"  ✅ Workflow Principal v6 actualizado.")

    # Desactivar Satélites de Chatwoot
    api(f"/workflows/{WID_HUMAN_TAKEOVER}/deactivate", method="POST")
    print(f"  ✅ Satélite Human Takeover (Chatwoot Webhook) DESACTIVADO.")

    api(f"/workflows/{WID_AUTO_REACTIVAR}/deactivate", method="POST")
    print(f"  ✅ Satélite Auto Reactivar (Chatwoot Cron) DESACTIVADO.")

    # Guardar POST backups
    backup_workflow(WID_V6, "POST_desacoplar_cw")
    backup_workflow(WID_HELPER_NOTIFY, "POST_desacoplar_cw")
    backup_workflow(WID_PANEL_STAFF, "POST_desacoplar_cw")

    print("\n🎉 ¡DESACOPLE COMPLETADO CON ÉXITO!")


if __name__ == "__main__":
    main()
