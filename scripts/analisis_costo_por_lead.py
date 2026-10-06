# -*- coding: utf-8 -*-
"""
analisis_costo_por_lead.py — 2026-10-06 · SOLO LECTURA. Cifras agregadas para fijar el costo variable por lead (precio y riesgo).
No imprime ni guarda nombres, telefonos ni textos de pacientes: solo conteos, promedios y percentiles.

DEFINICIONES (las del pedido):
  lead          = contacto unico con >= 1 mensaje suyo en el periodo.
  conversacion  = intercambio con un contacto dentro de una ventana de 24 h: empieza con un mensaje del paciente y dura 24 h; el
                  proximo mensaje del paciente despues de esa ventana abre otra. Los recordatorios que manda la clinica no abren conversacion.
FUENTES:
  A) data/conversaciones/ultimos_90d.json (export local de 3 meses, ya pseudonimizado) → leads, conversaciones, mensajes del bot,
     derivacion y mensajes sin respuesta, POR MES.
  B) ejecuciones de n8n (GET /executions, n8n solo conserva ~2 semanas) → tokens de entrada/salida por modelo y por lead.
     Cubre: Router, sub-agentes, reescritor de formato, banlist en sombra, sub-WF de cambios, triaje (si el nodo expone uso) y audio.
  Los costos en USD se calculan DESPUES con los precios que confirme el dueño: python scripts/analisis_costo_por_lead.py --precios "gpt-5=1.25:10,gpt-5-mini=0.25:2"

USO:  python scripts/analisis_costo_por_lead.py            # corre A y B y guarda data/costo_por_lead_agregado.json
      python scripts/analisis_costo_por_lead.py --solo-a   # solo el export
      python scripts/analisis_costo_por_lead.py --precios "gpt-5=IN:OUT,gpt-5-mini=IN:OUT"   # USD por millon de tokens; usa el agregado guardado
"""
import argparse, collections, concurrent.futures as cf, json, os, re, statistics, sys, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SALIDA = ROOT / "data" / "costo_por_lead_agregado.json"
ADMIN_PHONES = {"5491161461034", "5493885786946", "5493513976787"}   # Lucas, Irina, Dra. (CLAUDE.md): pruebas y staff, no son leads
MODELO_POR_NODO = {"Router LM": "gpt-5-mini", "Router LM1": "gpt-5-mini", "OpenAI Chat Model1": "gpt-5-mini", "LM Sub-Agent Urgencia": "gpt-5-mini",
                   "LM Sub-Agent Confirmar": "gpt-5", "LM Sub-Agent Cancelar": "gpt-5", "LM Sub-Agent Agendar": "gpt-5", "LM Sub-Agent General": "gpt-5-mini"}
ESCALA = re.compile(r"(le paso|le transmito|ya le transmito|le avisamos|le aviso|le dejo una nota|derivando|le pasamos).{0,90}(secretaria|dra\.?|doctora)|TRIAJE ESCALADO", re.I)
CIERRE = re.compile(r"^\W*(ok+|oka|okey|dale|listo|gracias|muchas gracias|mil gracias|genial|perfecto|buen[ií]simo|joya|de nada|chau|adi[oó]s|👍|🙏|❤️|😊)\W*$", re.I)


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    return xs[max(0, min(len(xs) - 1, round(p / 100 * (len(xs) - 1))))]


def stats(xs):
    xs = list(xs)
    return {"n": len(xs), "prom": round(statistics.mean(xs), 2) if xs else None, "p50": pct(xs, 50), "p90": pct(xs, 90), "max": max(xs) if xs else None}


# ------------------------------------------------------------------------------------------------------- A) export
def parte_a():
    d = json.load(open(ROOT / "data" / "conversaciones" / "ultimos_90d.json", encoding="utf-8"))
    por_mes = collections.defaultdict(lambda: {"leads": set(), "convs_por_lead": collections.Counter(), "bot_por_lead": collections.Counter(),
                                               "convs": 0, "convs_bot_derivo": 0, "convs_con_staff": 0, "msgs_pac": 0, "msgs_pac_sin_resp": 0,
                                               "msgs_pac_sin_resp_sin_cierres": 0, "msgs_pac_sin_cierres": 0, "msgs_pac_sin_resp_2h": 0, "msgs_bot": 0})
    for c in d:
        ms = sorted(({"t": datetime.fromisoformat(m["t"]), "rol": m["rol"], "texto": m.get("texto") or ""} for m in c["mensajes"]), key=lambda m: m["t"])
        pac = [m for m in ms if m["rol"] == "paciente"]
        bot = [m for m in ms if m["rol"] == "bot"]
        sal = [m for m in ms if m["rol"] in ("bot", "staff")]
        # conversaciones (ventanas de 24 h abiertas por un mensaje del paciente)
        fin = None
        for m in pac:
            mes = m["t"].strftime("%Y-%m")
            M = por_mes[mes]
            M["leads"].add(c["paciente"])
            if fin is None or m["t"] >= fin:
                fin = m["t"] + timedelta(hours=24)
                M["convs"] += 1
                M["convs_por_lead"][c["paciente"]] += 1
                ventana = [x for x in ms if m["t"] <= x["t"] < fin]
                if any(x["rol"] == "bot" and ESCALA.search(x["texto"]) for x in ventana):
                    M["convs_bot_derivo"] += 1
                if any(x["rol"] == "staff" for x in ventana):
                    M["convs_con_staff"] += 1
            # mensajes del paciente sin respuesta (bot o staff) en 24 h / 2 h
            M["msgs_pac"] += 1
            cierre = bool(CIERRE.match(m["texto"].strip()))
            if not cierre:
                M["msgs_pac_sin_cierres"] += 1
            if not any(m["t"] < x["t"] <= m["t"] + timedelta(hours=24) for x in sal):
                M["msgs_pac_sin_resp"] += 1
                if not cierre:
                    M["msgs_pac_sin_resp_sin_cierres"] += 1
            if not any(m["t"] < x["t"] <= m["t"] + timedelta(hours=2) for x in sal):
                M["msgs_pac_sin_resp_2h"] += 1
        for m in bot:
            mes = m["t"].strftime("%Y-%m")
            if c["paciente"] in por_mes[mes]["leads"]:
                por_mes[mes]["bot_por_lead"][c["paciente"]] += 1
                por_mes[mes]["msgs_bot"] += 1
    out = {}
    for mes in sorted(por_mes):
        M = por_mes[mes]
        leads = sorted(M["leads"])
        cpl = [M["convs_por_lead"][l] for l in leads]
        bpl = [M["bot_por_lead"][l] for l in leads]
        out[mes] = {"leads": len(leads), "conversaciones": M["convs"], "conv_por_lead": stats(cpl), "msgs_bot_por_lead": stats(bpl), "msgs_bot_total": M["msgs_bot"],
                    "pct_conv_donde_bot_derivo": round(100 * M["convs_bot_derivo"] / M["convs"], 1) if M["convs"] else None,
                    "pct_conv_con_staff_en_ventana": round(100 * M["convs_con_staff"] / M["convs"], 1) if M["convs"] else None,
                    "msgs_paciente": M["msgs_pac"],
                    "pct_msgs_sin_respuesta_24h": round(100 * M["msgs_pac_sin_resp"] / M["msgs_pac"], 1) if M["msgs_pac"] else None,
                    "pct_msgs_sin_respuesta_24h_sin_cierres": round(100 * M["msgs_pac_sin_resp_sin_cierres"] / M["msgs_pac_sin_cierres"], 1) if M["msgs_pac_sin_cierres"] else None,
                    "pct_msgs_sin_respuesta_2h": round(100 * M["msgs_pac_sin_resp_2h"] / M["msgs_pac"], 1) if M["msgs_pac"] else None}
    return out


# ------------------------------------------------------------------------------------------------------- B) n8n
def api(path):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", headers={"X-N8N-API-KEY": require("N8N_API_KEY")})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())


def ids_de(wid):
    ids, cur = [], None
    while True:
        r = api(f"/executions?workflowId={wid}&limit=250" + (f"&cursor={cur}" if cur else ""))
        ids += [(e["id"], e["startedAt"][:7]) for e in r["data"]]
        cur = r.get("nextCursor")
        if not cur:
            return ids


def usos_de(runs):
    """[(modelo, nodo, tokens_in, tokens_out)] + segundos de audio + llamadas sin dato. Sin contenido."""
    usos, audio_s, sin_dato, img = [], 0.0, 0, 0
    for nodo, rr in runs.items():
        for r in rr:
            data = (r.get("data") or {})
            ll = (data.get("ai_languageModel") or [[None]])[0]
            if ll and ll[0] and isinstance(ll[0].get("json"), dict) and "tokenUsage" in ll[0]["json"]:
                tu = ll[0]["json"]["tokenUsage"] or {}
                usos.append((MODELO_POR_NODO.get(nodo, "desconocido:" + nodo), nodo, int(tu.get("promptTokens") or 0), int(tu.get("completionTokens") or 0)))
                continue
            if nodo in MODELO_POR_NODO and ll:
                sin_dato += 1
                continue
            try:
                j = data["main"][0][0]["json"]
            except Exception:
                continue
            if isinstance(j, dict) and isinstance(j.get("usage"), dict):
                u = j["usage"]
                if "prompt_tokens" in u:
                    usos.append((re.sub(r"-\d{4}-\d{2}-\d{2}$", "", str(j.get("model") or "desconocido")), nodo, int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)))
                elif u.get("type") == "duration":
                    audio_s += float(u.get("seconds") or 0)
            if nodo == "OpenAI - Analizar Imagen":
                img += 1
    return usos, audio_s, sin_dato, img


def telefono_de(runs):
    for nodo in ("Edit Fields - Extraer Datos", "When called by v6", "Webhook"):
        try:
            j = runs[nodo][0]["data"]["main"][0][0]["json"]
            ph = j.get("phone") or (j.get("body") or {}).get("phone")
            if ph:
                return str(ph), bool(j.get("fromMe"))
        except Exception:
            pass
    return None, False


def una_ejecucion(args):
    eid, wf = args
    try:
        d = api(f"/executions/{eid}?includeData=true")
    except Exception:
        return None
    runs = (d.get("data") or {}).get("resultData", {}).get("runData", {})
    ph, from_me = telefono_de(runs)
    usos, audio_s, sin_dato, img = usos_de(runs)
    proceso_mensaje = "Preparar Mensaje Final" in runs
    return {"wf": wf, "mes": d.get("startedAt", "")[:7], "ph": ph, "from_me": from_me, "usos": usos, "audio_s": audio_s, "sin_dato": sin_dato, "img": img,
            "msg": proceso_mensaje, "triaje_evaluar": "Triaje: Evaluar" in runs}


def parte_b():
    trabajos = [(i, "v6") for i, _ in ids_de("O155MqHgOSaNZ9ye")] + [(i, "subwf_cambios") for i, _ in ids_de("5cAWJxiWJ50hxEq3")] + \
               [(i, "triaje_sombra") for i, _ in ids_de("Gm7ofyGohOJ2bI44")] + [(i, "reportero") for i, _ in ids_de("MJ38kSTRZDPgPCCy")]
    print(f"B) bajando {len(trabajos)} ejecuciones de n8n…", flush=True)
    filas = []
    with cf.ThreadPoolExecutor(8) as ex:
        for k, r in enumerate(ex.map(una_ejecucion, trabajos)):
            if r:
                filas.append(r)
            if k % 400 == 0:
                print(f"   {k}/{len(trabajos)}", flush=True)
    por_lead = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    por_lead_mes = collections.defaultdict(set)
    tot_modelo = collections.defaultdict(lambda: [0, 0, 0])
    tot_wf = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0]))
    sin_dato = img = 0; audio = 0.0; leads_msg = set(); triaje_calls = 0; sin_tel = collections.Counter(); excl_admin = 0
    for f in filas:
        sin_dato += f["sin_dato"]; img += f["img"]; audio += f["audio_s"]
        if f["triaje_evaluar"]:
            triaje_calls += 1
        if f["ph"] in ADMIN_PHONES or f["from_me"]:
            excl_admin += 1
            continue
        for modelo, nodo, ti, to in f["usos"]:
            tot_modelo[modelo][0] += ti; tot_modelo[modelo][1] += to; tot_modelo[modelo][2] += 1
            tot_wf[f["wf"]][modelo][0] += ti; tot_wf[f["wf"]][modelo][1] += to; tot_wf[f["wf"]][modelo][2] += 1
            if f["ph"]:
                por_lead[f["ph"]][modelo][0] += ti; por_lead[f["ph"]][modelo][1] += to
            else:
                sin_tel[f["wf"]] += 1
        if f["ph"] and f["msg"]:
            leads_msg.add(f["ph"]); por_lead_mes[f["mes"]].add(f["ph"])
    leads = sorted(leads_msg)
    def serie(sel):
        return [sum(sel(v) for v in por_lead[l].values()) for l in leads]
    modelos = sorted(tot_modelo)
    res = {"periodo_n8n": "ultimas ~2 semanas (n8n solo conserva ese historial)", "ejecuciones_leidas": len(filas), "ejecuciones_excluidas_admin_o_fromMe": excl_admin,
           "leads_con_mensaje_procesado": len(leads), "leads_por_mes_parcial": {m: len(s) for m, s in sorted(por_lead_mes.items())},
           "tokens_por_lead_total": {"entrada": stats(serie(lambda v: v[0])), "salida": stats(serie(lambda v: v[1]))},
           "tokens_por_lead_por_modelo": {m: {"entrada": stats([por_lead[l][m][0] for l in leads]), "salida": stats([por_lead[l][m][1] for l in leads])} for m in modelos},
           "totales_por_modelo": {m: {"tokens_entrada": tot_modelo[m][0], "tokens_salida": tot_modelo[m][1], "llamadas": tot_modelo[m][2]} for m in modelos},
           "totales_por_workflow_y_modelo": {w: {m: {"tokens_entrada": v[0], "tokens_salida": v[1], "llamadas": v[2]} for m, v in d.items()} for w, d in tot_wf.items()},
           "audio_segundos_transcriptos": round(audio), "imagenes_analizadas": img, "llamadas_modelo_sin_dato_de_tokens": sin_dato,
           "ejecuciones_del_triaje_evaluar (tokens no expuestos por el nodo)": triaje_calls, "usos_sin_telefono_por_workflow": dict(sin_tel)}
    return res


def costo(precios_txt):
    ag = json.load(open(SALIDA, encoding="utf-8"))["n8n"]
    precios = {}
    for par in precios_txt.split(","):
        m, p = par.split("="); i, o = p.split(":"); precios[m.strip()] = (float(i), float(o))
    leads = ag["leads_con_mensaje_procesado"]
    print(f"Costo de OpenAI con los precios dados (USD por millon de tokens) sobre {leads} leads de las ultimas ~2 semanas")
    total = 0.0
    for m, v in ag["totales_por_modelo"].items():
        if m not in precios:
            print(f"   {m}: SIN PRECIO ({v['tokens_entrada']:,} in / {v['tokens_salida']:,} out)"); continue
        c = v["tokens_entrada"] / 1e6 * precios[m][0] + v["tokens_salida"] / 1e6 * precios[m][1]
        total += c
        print(f"   {m:14} {v['tokens_entrada']:>12,} in · {v['tokens_salida']:>10,} out · {v['llamadas']:>6} llamadas → USD {c:,.2f}")
    print(f"   TOTAL USD {total:,.2f}  →  USD {total / max(leads, 1):.3f} por lead (promedio del periodo)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-a", action="store_true")
    ap.add_argument("--precios")
    a = ap.parse_args()
    if a.precios:
        return costo(a.precios)
    out = {"definiciones": {"lead": "contacto unico con >=1 mensaje suyo en el periodo", "conversacion": "ventana de 24 h abierta por un mensaje del paciente",
                            "derivada_por_bot": "el bot dijo explicitamente que pasaba/avisaba a la secretaria o la doctora (o triaje escalado)",
                            "con_staff": "hubo un mensaje de la clinica (humano) dentro de la ventana"}, "export_3_meses": parte_a()}
    print(json.dumps(out["export_3_meses"], ensure_ascii=False, indent=1))
    if not a.solo_a:
        out["n8n"] = parte_b()
        print(json.dumps(out["n8n"], ensure_ascii=False, indent=1))
    SALIDA.parent.mkdir(exist_ok=True)
    json.dump(out, open(SALIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nguardado:", SALIDA)


if __name__ == "__main__":
    main()
