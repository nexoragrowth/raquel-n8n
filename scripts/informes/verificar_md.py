# -*- coding: utf-8 -*-
"""Verifica los documentos para la Dra. antes de pasarlos a PDF.
USO: python verificar_md.py <archivo.md> [<archivo2.md> ...]
Chequea: palabras técnicas prohibidas, teléfonos, nombres completos que coincidan con pacientes reales (la lista de nombres se lee de la
base en modo solo lectura y NO se imprime; solo se muestran las coincidencias que ya están en el documento), ids de gráficos y esquemas,
tablas con distinta cantidad de columnas, línea de portada."""
import json, re, sys, unicodedata
from pathlib import Path

import psycopg2

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"C:\Users\not\Desktop\proyectos\raquel-n8n")
GRAFICOS = {"lo_que_hace_asiri", "temas_pacientes", "quienes_escriben", "info_faltante", "embudo_nuevos", "avisos_grupo_tipo", "resueltas_sin_persona"}
DIAGRAMAS = {"antes_y_ahora", "tipos_contacto", "sistema_unico", "recorrido_paciente"}
PROHIBIDAS = [r"\bn8n\b", r"\bworkflows?\b", r"\bsupabase\b", r"\bAPIs?\b", r"\bwebhooks?\b", r"\bredis\b", r"\bflags?\b", r"\bPUT\b", r"\bregex\w*\b",
              r"\bprompts?\b", r"\bLLMs?\b", r"\borquestador\w*\b", r"\bsub-?agentes?\b", r"\bsombra\b", r"\bespejo\b", r"\bpipelines?\b",
              r"\bremarketing\b", r"\bleads?\b", r"\bescal(ar|a|aci[oó]n|aciones|ó|amos)\b", r"\bevolution\b", r"\bdeploy\w*\b", r"\bendpoints?\b",
              r"\bJSON\b", r"\bv6\b", r"\bv7\b", r"\bel modelo\b", r"\bbanlist\b", r"\bDentalink up\b"]
PERMITIDOS = {"ana pérez", "juan pérez", "raquel rodríguez", "dra raquel"}


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def nombres_reales():
    env = {}
    for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
    c = psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"], user=env["SUPABASE_DB_USER"],
                         password=env["SUPABASE_DB_PASSWORD"], sslmode="require")
    c.set_session(readonly=True)
    cur = c.cursor()
    cur.execute("SELECT nombre FROM pacientes WHERE nombre IS NOT NULL UNION SELECT nombre_paciente FROM recordatorios_enviados WHERE nombre_paciente IS NOT NULL")
    pares = set()
    for (n,) in cur.fetchall():
        t = [x for x in re.findall(r"[a-záéíóúñü]+", sin_tildes(n)) if len(x) > 2]
        for a, b in zip(t, t[1:]):
            pares.add(f"{a} {b}")
    c.close()
    return pares - {sin_tildes(p) for p in PERMITIDOS} - {"paciente whatsapp", "test lucas", "lucas silva"}


def revisar(md, pares):
    txt = md.read_text(encoding="utf-8")
    lineas = txt.splitlines()
    print(f"\n=== {md.name}: {len(lineas)} líneas, {len(txt.split())} palabras")
    prob = []
    if not re.match(r"#\s+\S", lineas[0]): prob.append("línea 1 no es el título '# ...'")
    m = re.match(r"\s*<!--\s*portada:\s*(\{.*\})\s*-->\s*$", lineas[1] if len(lineas) > 1 else "")
    if not m: prob.append("línea 2 no es el comentario de portada")
    else:
        try: json.loads(m.group(1))
        except Exception as e: prob.append(f"portada: JSON inválido ({e})")
    for i, l in enumerate(lineas, 1):
        if i == 2: continue
        for p in PROHIBIDAS:
            for mm in re.finditer(p, l, re.I):
                prob.append(f"L{i}: palabra técnica «{mm.group(0)}» → {l.strip()[:110]}")
        for mm in re.finditer(r"\+?\d[\d \-]{8,}\d", l):
            if len(re.sub(r"\D", "", mm.group(0))) >= 9: prob.append(f"L{i}: posible teléfono «{mm.group(0)}»")
        for mm in re.finditer(r"\[(GRAFICO|DIAGRAMA):\s*([^\]]+)\]", l):
            ok = GRAFICOS if mm.group(1) == "GRAFICO" else DIAGRAMAS
            if mm.group(2).strip() not in ok: prob.append(f"L{i}: {mm.group(1)} desconocido «{mm.group(2)}»")
        if "<" in l and i != 2 and re.search(r"<[a-zA-Z/!]", l): prob.append(f"L{i}: HTML en el texto → {l.strip()[:80]}")
    # tablas: misma cantidad de celdas por fila
    bloque = []
    for i, l in enumerate(lineas + [""], 1):
        if l.strip().startswith("|"):
            bloque.append((i, l.strip().strip("|").count("|") + 1 - l.count("\\|")))
        elif bloque:
            cols = {c for _, c in bloque}
            if len(cols) > 1: prob.append(f"L{bloque[0][0]}-{bloque[-1][0]}: tabla con filas de distinta cantidad de columnas {sorted(cols)}")
            bloque = []
    norm = sin_tildes(txt)
    vistos = sorted({p for p in pares if re.search(r"\b" + re.escape(p) + r"\b", norm)})
    for p in vistos: prob.append(f"nombre completo que coincide con un paciente real: «{p}» (revisar si es un ejemplo inventado)")
    usados = re.findall(r"\[(?:GRAFICO|DIAGRAMA):\s*([^\]]+)\]", txt)
    print("gráficos/esquemas:", usados)
    print("☐:", txt.count("☐"), "| tablas:", sum(1 for l in lineas if re.match(r"\s*\|[-: |]+\|\s*$", l)), "| citas:", sum(1 for l in lineas if l.startswith(">")))
    print("\n".join(prob) if prob else "SIN PROBLEMAS")
    return len(prob)


if __name__ == "__main__":
    pares = nombres_reales()
    total = sum(revisar(Path(a), pares) for a in sys.argv[1:])
    print(f"\nTOTAL problemas: {total}")
