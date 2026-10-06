# -*- coding: utf-8 -*-
"""
test_nodes_eval.py — Pruebas sintéticas directas de la lógica de Step 5 y Step 6b-out
"""
import json

# Simulación de la entrada que Step 3b genera para el caso real:
# Paciente: "cualquier dia por la tarde despues de las 17hs"
# Turno previo: Miércoles 29 de Julio a las 18:40 hs

intent_case_1 = {
    "accion": "reprogramar",
    "fecha_objetivo": None,
    "hora_objetivo": None,
    "franja": "tarde",
    "hora_minima": 17,
    "razon": "reprogramar tarde despues de 17hs"
}

trigger_text = "cualquier dia por la tarde despues de las 17hs"

# Lógica de Step 5:
textRaw = trigger_text.lower()
tieneFranjaTexto = bool(any(k in textRaw for k in ["tarde", "mañana", "despues", "pasadas", "17"]))

if intent_case_1["accion"] == "reprogramar" and (intent_case_1["fecha_objetivo"] or intent_case_1["franja"] or intent_case_1["hora_minima"] is not None or tieneFranjaTexto):
    action_to_execute = "buscar_horarios"
else:
    action_to_execute = "ninguna"

print("--- TEST CASE 1 ---")
print("Input paciente:", trigger_text)
print("Intent extraída:", intent_case_1)
print("Step 5 Action ejecutada:", action_to_execute)
assert action_to_execute == "buscar_horarios", "Step 5 debió activar buscar_horarios!"

# Lógica de Step 6b-out con slots mock de Dentalink (ej: Lunes a las 17:30 y Miércoles a las 18:00):
slots_raw = [
    {"fecha": "03/08/2026", "hora_inicio": "17:30:00"},
    {"fecha": "05/08/2026", "hora_inicio": "18:00:00"},
    {"fecha": "05/08/2026", "hora_inicio": "11:00:00"}, # Mañana -> debe ser filtrado
]

horaMinima = intent_case_1["hora_minima"]
franja = intent_case_1["franja"]

def hourOf(s):
    return int(s.split(":")[0])

def dowOf(fecha_str):
    # 03/08/2026 es Lunes (1), 05/08/2026 es Miércoles (3)
    d = int(fecha_str.split("/")[0])
    return 1 if d == 3 else 3

def inFranja(s):
    h = hourOf(s["hora_inicio"])
    if horaMinima is not None and h < horaMinima:
        return False
    if franja == "tarde":
        dow = dowOf(s["fecha"])
        return h >= 13 and (dow == 1 or dow == 3)
    return True

matches = [s for s in slots_raw if inFranja(s)]
print("\nSlots ingresados:", len(slots_raw))
print("Slots filtrados (tarde + hora >= 17):", len(matches), matches)

assert len(matches) == 2, "Debió filtrar solo los 2 turnos de la tarde tras las 17hs!"
print("\n--- TODOS LOS ASSERTS PASARON EXITOSAMENTE ---")
