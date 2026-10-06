# -*- coding: utf-8 -*-
"""
status.py — Tablero de Control de Emergencia y Visibilidad en 1 Comando.
Te dice exactamente dónde estás parado en 3 segundos sin tener que acordarte de nada:
- Estado del workflow en n8n (vivo, activo, versión, webhook).
- Estado de los 6 Prompts (tamaño, salud, curados).
- Estado de Supabase (filas de KB, embeddings nulos, historial de chats).
- Estado del Triaje de Urgencias (videos activos y modo).
- Últimos errores o ejecuciones en n8n.

USO:
  python scripts/status.py
"""
import json, sys, urllib.request, psycopg2
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env
from apply_media_entrantes import api, WF_ID

def main():
    print("==================================================================")
    print(" 🏥 TABLERO DE CONTROL ÁUREA / NEXORA — ESTADO DEL SISTEMA")
    print("==================================================================\n")

    # 1. n8n WORKFLOW PRINCIPAL
    try:
        wf = api(f"/workflows/{WF_ID}")
        wh = next((n for n in wf["nodes"] if n["name"] == "Webhook - Evolution API"), None)
        active = wf.get("active", False)
        nodes_count = len(wf.get("nodes", []))
        webhook_ok = wh and wh.get("webhookId") == "evo-webhook-v2"
        
        print("🟢 [N8N WORKFLOW]")
        print(f"  • Workflow ID:    {WF_ID}")
        print(f"  • Estado:         {'✅ ACTIVO' if active else '❌ INACTIVO'}")
        print(f"  • Total Nodos:    {nodes_count}")
        print(f"  • Webhook ID:     {'✅ evo-webhook-v2 (OK)' if webhook_ok else '❌ PERDIDO / PELIGRO'}")
        print(f"  • Versión viva:   {wf.get('versionId')}")
    except Exception as e:
        print(f"🔴 [N8N WORKFLOW] ERROR: {e}")

    # 2. SALUD DE PROMPTS
    print("\n🟢 [PROMPTS Y AGENTES]")
    try:
        prompts = {}
        for n in wf.get("nodes", []):
            if "systemMessage" in n.get("parameters", {}).get("options", {}):
                prompts[n["name"]] = len(n["parameters"]["options"]["systemMessage"])
        
        for name in ["Router - Clasificar Intent", "Sub-Agent General", "Sub-Agent Agendar", 
                     "Sub-Agent Confirmar", "Sub-Agent Cancelar", "Sub-Agent Urgencia"]:
            size = prompts.get(name, 0)
            status_prompt = "✅ CURADO" if size < 5000 else "⚠️ PESADO"
            print(f"  • {name.ljust(28)}: {str(size).rjust(5)} chars  [{status_prompt}]")
    except Exception as e:
        print(f"🔴 [PROMPTS] ERROR: {e}")

    # 3. SUPABASE BASE DE DATOS & KB
    print("\n🟢 [SUPABASE DATA LAYER]")
    try:
        conn = psycopg2.connect(
            host=env("SUPABASE_V3_DB_HOST"), port=env("SUPABASE_V3_DB_PORT"),
            dbname=env("SUPABASE_V3_DB_NAME"), user=env("SUPABASE_V3_DB_USER"),
            password=env("SUPABASE_V3_DB_PASSWORD"), sslmode="require", connect_timeout=5
        )
        cur = conn.cursor()
        
        # Knowledge base
        cur.execute("SELECT count(*) FROM knowledge_base;")
        kb_total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM knowledge_base WHERE embedding IS NULL;")
        kb_nulls = cur.fetchone()[0]
        
        # Chat histories
        cur.execute("SELECT count(DISTINCT session_id), count(*) FROM n8n_chat_histories;")
        sesiones, mensajes = cur.fetchone()

        # Triaje
        cur.execute("SELECT count(*) FROM triaje_videos WHERE activo = true;")
        videos_activos = cur.fetchone()[0]

        conn.close()

        print(f"  • Knowledge Base: {kb_total} filas oficiales (Embeddings nulos: {kb_nulls})")
        print(f"  • Triaje Videos:  {videos_activos} videos activos")
        print(f"  • Conversaciones: {sesiones} pacientes registrados ({mensajes} mensajes guardados)")
    except Exception as e:
        print(f"🔴 [SUPABASE] ERROR: {e}")

    # 4. ÚLTIMAS EJECUCIONES EN N8N
    print("\n🟢 [ÚLTIMAS EJECUCIONES]")
    try:
        execs = api(f"/executions?workflowId={WF_ID}&limit=5").get("data", [])
        for ex in execs:
            eid = ex.get("id")
            st = ex.get("status")
            mode = ex.get("mode")
            started = ex.get("startedAt", "")[:19].replace("T", " ")
            icon = "✅" if st == "success" else ("⏳" if st == "running" else "❌")
            print(f"  • Exec #{eid} | {icon} {st.ljust(8)} | Modo: {mode.ljust(8)} | {started}")
    except Exception as e:
        print(f"🔴 [EJECUCIONES] ERROR: {e}")

    print("\n==================================================================")
    print(" 📖 SISTEMA DE REFERENCIA RÁPIDA:")
    print("   1. Para incidentes:       docs/checklist-casos-tipo.md")
    print("   2. Para estado de memoria: memory/current-state.md")
    print("   3. Para correr tests:     python tests/test_e2e_bateria.py")
    print("==================================================================")

if __name__ == "__main__":
    main()
