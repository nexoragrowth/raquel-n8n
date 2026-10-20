# -*- coding: utf-8 -*-
"""
check_triaje_grafo.py — los chequeos de GRAFO de scripts/check_triaje.py, como función pura sobre un dict de workflow (sin red).

Por qué existe: check_triaje.py hace GET del v6 VIVO, así que antes de un PUT solo puede mirar el grafo que se va a reemplazar.
Los scripts apply_* importan chequear_grafo() y la corren sobre el workflow PROPUESTO (antes del PUT) y sobre el GET posterior.
Una sola fuente: si se agrega un chequeo de grafo, se agrega ACÁ y lo ven check_triaje.py y todos los apply_*.
"""


def _main(conns, s, i):
    salidas = (conns.get(s) or {}).get("main") or []
    return [t["node"] for t in (salidas[i] or [])] if len(salidas) > i else []


def chequear_grafo(wf):
    """Lista de (ok, mensaje). No lanza: un nodo faltante es un chequeo en rojo."""
    r = []
    names = {n["name"] for n in wf.get("nodes", [])}
    conns = wf.get("connections") or {}
    r.append(("Triaje: Evaluar" in names and "Triaje: Decidir" in names, "nodos Triaje presentes en el v6"))
    r.append((_main(conns, "Switch sobre Intent", 2)[:1] == ["Triaje: Cargar Config"], "Switch sobre Intent[2] -> Triaje: Cargar Config"))
    if "V7: ¿Vivo?" in names:  # conexión v7 por flag (scripts/apply_v7_flag_lucas.py): la rama de los teléfonos sin flag sigue al v6
        ent_router = sorted((s, i) for s, d in conns.items() for i, o in enumerate(d.get("main") or []) for t in (o or [])
                            if t["node"] == "Router - Clasificar Intent")
        r.append((_main(conns, "V7: ¿Vivo?", 1) == ["Pre-filtro Cierre"] and _main(conns, "V7: ¿Vivo?", 0) == ["Triaje: Redis GET estado"],
                  "fork v7: ¿Vivo?[no] -> Pre-filtro Cierre, [sí] -> Triaje: Redis GET estado"))
        r.append((ent_router == [("V7: ¿Ruta v7?", 1)], f"fork v7: el Router recibe solo desde V7: ¿Ruta v7?[no] ({ent_router})"))
        r.append((_main(conns, "V7: Derivar a Triaje", 0) == ["Triaje: Cargar Config"], "fork v7: V7: Derivar a Triaje -> Triaje: Cargar Config"))
    if "Seg: Consultar Tipo" in names:  # Día 1 de la segmentación (scripts/apply_dia1_segmentacion.py)
        r.append(("Seg: ¿Silenciar?" in names and "Consultar Takeover Paciente" in _main(conns, "Seg: ¿Silenciar?", 1),
                  "segmentación: Seg: ¿Silenciar?[no] -> Consultar Takeover Paciente (los que no se silencian siguen al v6)"))
    return r
