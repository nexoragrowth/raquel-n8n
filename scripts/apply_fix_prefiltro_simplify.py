"""
Simplificacion del Pre-filtro Cierre del v6.

Contexto: el nodo tenia 15+ ramas, incluyendo 5 bloques `skip:true`
conversacionales que mataban mensajes legitimos:

  - termina_gracias / solo_gracias
  - cierres exactos (ok, dale, listo, perfecto, joya, copado, ...)
  - te_veo_dia (te veo el lunes, hasta el viernes, ...)
  - ok_plus_short (ok dale, hola listo, ...)
  - short_closing (cualquier frase <18ch con words cortas)

Caso visible (27/05): "Confirmamos turno para esa hora, gracias" -> NO_REPLY
                       3 respuestas idénticas en loop al caso Julieta
                       jujenismos "meta" / "ahre" / "está la papa" -> silencio

Decision: delegar TODA clasificacion conversacional al Router LLM (gpt-5 main).
El pre-filtro queda con SOLO filtros tecnicos/anomalos + fast-paths positivos.

Mantiene:
  - prompt_injection (seguridad)
  - autoresponder_externo (anti spam Sil Odonto / Omar Dental)
  - afirmaciones_negaciones_cortas (skip:false - fast-path positivo)
  - saludo_inicial (skip:false)
  - urgencia (skip:false - defensive, leccion caso Mariela)
  - multimedia_marker (skip:false - passthrough)
  - tiene_pregunta (skip:false)
  - confirmacion_post_recordatorio whitelist (skip:false)
  - emoji_only (skip:true - anti garbage)
  - default_pass (skip:false)

Workflow: v6 main (O155MqHgOSaNZ9ye)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF_ID = os.environ.get("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")

HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}


NEW_JS_CODE = r"""// Pre-filtro deterministico: solo filtros tecnicos/anomalos.
// Toda clasificacion CONVERSACIONAL (cierres, gracias, ok/dale/meta, etc.)
// se delega al Router LLM que tiene contexto de memoria.
//
// Mantiene:
//  - prompt_injection / autoresponder_externo / emoji_only -> skip:true (tecnicos)
//  - urgencias / afirmaciones-negaciones cortas / saludos / multimedia / pregunta
//    / confirmaciones whitelist -> skip:false (fast-path positivo, evita LLM)
//  - todo lo demas -> default_pass (Router decide)
//
// Historia: 27/05 - removidos 5 bloques skip:true conversacionales
// (termina_gracias, cierres_exactos, te_veo_dia, ok_plus_short, short_closing)
// porque mataban "Confirmamos turno gracias", "ok", "dale", "meta", etc.
// El Router LLM (gpt-5 main) ahora clasifica con memoria.

const text = ($('Preparar Mensaje Final').first().json.text || '').trim();
const stripAccents = s => s.normalize('NFD').replace(/\p{Diacritic}/gu, '');
const stripEmoji = s => s.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}‍️☺☹]/gu, '').replace(/\s+/g, ' ').trim();
const norm = s => stripAccents(stripEmoji(s)).toLowerCase().replace(/[!.,;:]+/g, '').trim();

const t = norm(text);
const tLen = text.length;

// === DETECTOR PROMPT INJECTION (silencia) ===
const injectionPatterns = [
  /ignor[ae]\s+(todas?\s+)?tus\s+(instrucciones|reglas)/i,
  /olvid[ae]?\s+(lo\s+que\s+|todas?\s+)?(te\s+dijeron|tus\s+instrucciones|tus\s+reglas)/i,
  /tus?\s+nuevas?\s+(reglas|instrucciones|directivas)\s+(son|es)/i,
  /de\s+ahora\s+en\s+m[áa]s\s+sos\s+(otro|un)/i,
  /actu[áa]\s+como\s+(otro|un|una)/i,
  /pretend[ée]\s+ser\s+/i,
  /modo\s+(developer|admin|dios|dios\s+mode|debug|sudo|root)/i,
  /\[admin\s*mode\]/i,
  /\[system\s*(override|mode|prompt)\]/i,
  /system\s+override/i,
  /(mostrame|repet[íi]|dame|pasame)\s+(tu|el)\s+(system\s+)?prompt/i,
  /(que|cuales)\s+(tools|herramientas)\s+(tenes|tienes)/i,
  /(api\s*key|api_key|apikey|credenciales)\s+(real(es)?|de\s+\w+)/i,
  /(decime|pasame|mostrame)\s+.*(api\s*key|credencial|token|secret)/i,
  /listado\s+(completo\s+)?(de\s+)?pacientes/i,
  /todos?\s+los\s+(pacientes|turnos|datos)/i,
  /cancel[áa]\s+todos?\s+los\s+turnos/i,
  /borr[áa]\s+(todo|todos)/i,
  /soy\s+(el\s+desarrollador|admin|administrador|developer|root)/i,
  /usuario\s+autorizado/i,
];
for (const pat of injectionPatterns) {
  if (pat.test(text)) {
    return [{ json: { skip: true, reason: 'prompt_injection:'+pat.source.slice(0,30), text, output: '[NO_REPLY]' } }];
  }
}

// === AUTORESPONDERS DE OTRAS CLINICAS / SAAS BOTS ===
const autoresponderPatterns = [
  /gracias por comunicarte con\s+\S/i,
  /gracias por (escribir|contactarnos|tu mensaje)\s/i,
  /este es un (mensaje|saludo) (automatico|automático)/i,
  /respuesta automatica|respuesta automática/i,
  /mensaje automatico recibido|mensaje automático recibido/i,
  /horario(s)? de atenci[oó]n.*(lunes|martes|miercoles|jueves|viernes)/i,
  /a la brevedad le responderemos/i,
  /en breve nos comunicaremos/i,
  /instagram\.com\/od\.rodriguezraquel/i,
  /te\s+invitamos\s+a\s+seguirnos\s+en\s+instagram/i,
];
for (const pat of autoresponderPatterns) {
  if (pat.test(text)) {
    return [{ json: { skip: true, reason: 'autoresponder_externo:'+pat.source.slice(0,30), text, output: '[NO_REPLY]' } }];
  }
}

// === AFIRMACIONES/NEGACIONES CORTAS — pasar al Router (fast-path positivo) ===
const afirmaciones_cortas = [
  'si','sí','sii','siii','sis','sip','sipi','si si','sí sí','sip sip',
  'no','nop','nope','nono','no no',
  'claro','claro que si','claro que sí','obvio','obvio si','obvio sí',
  'exacto','correcto','asi es','así es','tal cual eso','tal cual ese',
  'ese','ese mismo','ese si','ese sí','ese era','ese mismo si','ese mismo sí',
  'eso','eso es','eso mismo','eso era',
  'si confirmo','sí confirmo','confirmo eso','confirmo ese',
  'no era','no era ese','ese no','no ese'
];
if (afirmaciones_cortas.includes(t)) {
  return [{ json: { skip: false, reason: 'afirmacion_negacion_corta', text } }];
}

// === SALUDOS — pasar ===
const saludos = ['hola','holaa','holaaa','holis','buenas','buen dia','buenos dias','buenas tardes','buenas noches','que tal','como va','como andas','que onda'];
if (saludos.includes(t)) {
  return [{ json: { skip: false, reason: 'saludo_inicial', text } }];
}

// === URGENCIAS — pasar (defensive, leccion Mariela 09/05) ===
const urgenciaWords = ['dolor','duele','duela','muela','alambre','bracket','arco','sangrado','hinchazon','hinchada','no aguanto','urgent','infeccion','fiebre','golpe','accidente','rompi','pincha','pinchando','medicacion','que tomo','que tomar','que pastilla','pastilla','pastillas','ibuprofeno','paracetamol','antibio'];
for (const w of urgenciaWords) {
  if (t.includes(w)) return [{ json: { skip: false, reason: 'urgencia', text } }];
}

// === MULTIMEDIA markers — pasar ===
if (text.includes('[DOCUMENTO') || text.includes('[IMAGEN') || text.includes('[AUDIO')) {
  return [{ json: { skip: false, reason: 'multimedia_marker', text } }];
}

// === Pregunta — pasar ===
if (text.includes('?')) {
  return [{ json: { skip: false, reason: 'tiene_pregunta', text } }];
}

// === Confirmaciones cortas — pasar al sub-agent ===
const confirmaciones = ['confirmo','si confirmo','confirmado','confirmamelo','dale confirmo','ahi estare','ahi voy','voy','voy a ir','asisto','confirmo doctora','confirmo dra','confirmo gracias','si voy','si asisto'];
if (confirmaciones.includes(t) || confirmaciones.some(c => t === 'si ' + c || t.endsWith(' ' + c))) {
  return [{ json: { skip: false, reason: 'confirmacion_post_recordatorio', text } }];
}

// === Emoji-only — descartar (anti garbage tecnico) ===
if (stripEmoji(text).length === 0 && tLen > 0) {
  return [{ json: { skip: true, reason: 'emoji_only', text, output: '[NO_REPLY]' } }];
}

// === Default: pasar al Router LLM, que decide con memoria ===
return [{ json: { skip: false, reason: 'default_pass', text } }];
"""


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_PREFILTRO_SIMPLIFY_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def find_node(wf: dict, name: str) -> dict:
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    raise SystemExit(f"Node {name!r} not found")


def put_workflow(wf: dict) -> dict:
    allowed_settings = {
        "saveExecutionProgress",
        "saveManualExecutions",
        "saveDataErrorExecution",
        "saveDataSuccessExecution",
        "executionTimeout",
        "errorWorkflow",
        "timezone",
        "executionOrder",
        "callerPolicy",
        "callerIds",
    }
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed_settings}
    body = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    r = requests.put(
        f"{BASE}/api/v1/workflows/{WF_ID}",
        headers=HEADERS,
        json=body,
        timeout=30,
    )
    if not r.ok:
        print("PUT failed:", r.status_code, r.text[:500], file=sys.stderr)
        r.raise_for_status()
    return r.json()


def main():
    dry = "--dry" in sys.argv

    print(f"[1/4] GET workflow {WF_ID}")
    wf = get_workflow()
    print(f"      name={wf['name']!r} nodes={len(wf['nodes'])} active={wf.get('active')}")

    print("[2/4] Backup")
    out = backup(wf)
    print(f"      -> {out}")

    print("[3/4] Patch Pre-filtro Cierre")
    node = find_node(wf, "Pre-filtro Cierre")
    old = node["parameters"]["jsCode"]
    new = NEW_JS_CODE

    # markers anchored to active CODE (not comments) of each removed block
    removed_markers = {
        'termina_gracias':   "if (termGracias",
        'solo_gracias':      "if (soloGracias)",
        'cierres_exactos':   "const cierres = [",
        'te_veo_dia':        "const teVeoRegex",
        'ok_plus_short':     "const okPlusShort",
        'short_closing':     "if (tLen <= 18 &&",
    }
    print(f"      old={len(old)}ch new={len(new)}ch delta={len(new)-len(old):+d}ch")
    for name, marker in removed_markers.items():
        present_old = marker in old
        present_new = marker in new
        ok = present_old and not present_new
        flag = 'OK' if ok else ('SKIP' if not present_old else 'STILL_PRESENT')
        print(f"      {flag:<14s} {name:<20s} marker={marker!r}")

    if dry:
        print("\n=== DRY RUN — not PUTting ===")
        return

    node["parameters"]["jsCode"] = new

    print("[4/4] PUT workflow")
    res = put_workflow(wf)
    print(f"      OK active={res.get('active')} updatedAt={res.get('updatedAt')}")

    wf2 = get_workflow()
    node2 = find_node(wf2, "Pre-filtro Cierre")
    live = node2["parameters"]["jsCode"]
    fail = [name for name, marker in removed_markers.items() if marker in live]
    if fail:
        print(f"[verify] FAIL — active code still present: {fail}")
        sys.exit(2)
    print("[verify] OK — all 6 removed-block markers gone in live workflow")


if __name__ == "__main__":
    main()
