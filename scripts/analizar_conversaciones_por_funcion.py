# -*- coding: utf-8 -*-
"""
analizar_conversaciones_por_funcion.py — a partir de data/conversaciones/ultimos_<N>d.json (ver exportar_conversaciones_periodos.py)
clasifica cada mensaje de paciente por FUNCION (usando el mensaje anterior como contexto) y mide quien le contesto primero
(bot / persona del consultorio / nadie) y cuanto tardo. Sirve para ver donde se pierde la conversion y para sacar frases reales
para los casos de prueba. Sin red, sin base.

SALIDA: data/conversaciones/resumen_por_funcion.md (local, ignorado por git: lleva frases reales de pacientes)

USO:
    python scripts/analizar_conversaciones_por_funcion.py            # usa ultimos_90d.json
    python scripts/analizar_conversaciones_por_funcion.py 30
"""
import json, re, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
DATA = Path(__file__).resolve().parent.parent / "data" / "conversaciones"
T = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")


def funcion(texto, rol_previo, comprobante_real):
    t = texto.lower()
    if comprobante_real:
        return "pago: comprobante"
    if re.search(r"\[imagen|\[documento|\[contacto|\[audio|\[video|\[sticker", t):
        return "adjunto (imagen/documento/audio)"
    if re.search(r"transfer|pagu[eé]|abon[eé]|deposit|comprobante", t):
        return "pago: avisa que pagó"
    if rol_previo == "recordatorio":
        if re.search(r"cancel|no (voy a )?pod|no puedo|no llego|reprogram|cambiar|mover|otro d[ií]a|posterg|surgi|imposible", t):
            return "recordatorio: no puede / cambia"
        if re.search(r"confirm|^\W*(si|sí|ok|dale|oka|okey|listo|perfecto|gracias|buenas?|hola)\W*$|👍|✅|🙏|voy|asist|estar", t):
            return "recordatorio: confirma"
        return "recordatorio: otra respuesta"
    if re.search(r"cancel|no (voy a )?pod|no puedo|no llego|reprogram|cambiar|mover|otro d[ií]a|otro horario|posterg|adelantar|surgi|imposible", t):
        return "cancela / reprograma"
    if re.search(r"dolor|duele|pincha|sangr|bracket|alambre|se (me |le )?(salio|salió|despeg|rompi|solt|cay)|urgenc|inflam|hinch", t):
        return "urgencia"
    if re.search(r"turno|agend|cita\b|consulta para|primera vez|sacar|disponib|lugar", t) or re.search(r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado)\b|a las \d|\d{1,2}(:\d\d)? ?hs", t):
        return "agenda / elige horario"
    if re.search(r"precio|cuanto|cuánto|vale|costo|alias|cbu|efectivo|tarjeta|cuota", t):
        return "precio / forma de pago"
    if re.search(r"obra social|isj|osde|swiss|reintegro|factura|prepaga|cobertura", t):
        return "obra social / factura"
    if re.search(r"hola|buen[oa]s|m[aá]s info|informaci", t):
        return "saludo / pide información"
    return "otro"


def main():
    dias = sys.argv[1] if len(sys.argv) > 1 else "90"
    d = json.loads((DATA / f"ultimos_{dias}d.json").read_text(encoding="utf-8"))
    filas, familia = defaultdict(list), set()
    for c in d:
        ms = c["mensajes"]
        recs = [m for m in ms if m["rol"] == "recordatorio"]
        for a, b in zip(recs, recs[1:]):
            if (T(b["t"]) - T(a["t"])).total_seconds() < 600:
                familia.add(c["paciente"])
                break
        for i, m in enumerate(ms):
            if m["rol"] != "paciente":
                continue
            prev = next((x for x in reversed(ms[:i]) if x["rol"] in ("bot", "staff", "recordatorio")), None)
            rol_previo = prev["rol"] if prev and (T(m["t"]) - T(prev["t"])).total_seconds() < 172800 else None
            j = i + 1
            while j < len(ms) and ms[j]["rol"] in ("paciente", "interno", "recordatorio_test"):
                j += 1
            sig = ms[j] if j < len(ms) and ms[j]["rol"] != "recordatorio" else None
            mins = (T(sig["t"]) - T(m["t"])).total_seconds() / 60 if sig else None
            comp = "TIPO: COMPROBANTE" in m["texto"]
            filas[funcion(m["texto"], rol_previo, comp)].append(
                {"c": c["paciente"], "t": m["t"], "txt": m["texto"], "next": sig["rol"] if sig else None, "min": mins, "nt": sig["texto"] if sig else ""})
    out = [f"# Resumen por función — últimos {dias} días (datos reales, local)", "",
           "Quién le contestó PRIMERO a cada mensaje del paciente. `espera` = mediana de minutos hasta que contestó una persona del consultorio.", "",
           "| función | mensajes | bot | persona | nadie | % bot | espera persona (min) |", "|---|---|---|---|---|---|---|"]
    for k, v in sorted(filas.items(), key=lambda kv: -len(kv[1])):
        b = sum(1 for r in v if r["next"] == "bot")
        s = sum(1 for r in v if r["next"] == "staff")
        esp = sorted(r["min"] for r in v if r["next"] == "staff" and r["min"] is not None)
        out.append(f"| {k} | {len(v)} | {b} | {s} | {len(v) - b - s} | {100 * b // len(v)}% | {int(esp[len(esp) // 2]) if esp else '-'} |")
    out += ["", f"Conversaciones con 2 o más recordatorios en menos de 10 minutos (familia / varios turnos): **{len(familia)}**", ""]
    for k, v in sorted(filas.items(), key=lambda kv: -len(kv[1])):
        top = Counter(re.sub(r"\W+", " ", r["txt"].lower()).strip()[:70] for r in v).most_common(8)
        out.append(f"## {k}\nFrases más repetidas: " + " · ".join(f"«{t}» ×{n}" for t, n in top if t) + "\n")
    (DATA / "resumen_por_funcion.md").write_text("\n".join(out), encoding="utf-8")
    json.dump(filas, open(DATA / "_clasificado.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("\n".join(out[:22]))
    print(f"\nEscrito: {DATA / 'resumen_por_funcion.md'}")


if __name__ == "__main__":
    main()
