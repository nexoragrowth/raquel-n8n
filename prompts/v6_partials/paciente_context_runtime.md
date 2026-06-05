**CONTEXTO DEL PACIENTE QUE ESCRIBE EN ESTE TURNO** (NUEVO 2026-06-03 Fase 4a — uso interno, NO mencionar al paciente):
- phone: {{ $('Edit Fields - Extraer Datos').first().json.phone }}
- phone_last10 (USA ESTE VALOR LITERAL en `buscar_paciente_dentalink`, ya calculado): {{ $('Edit Fields - Extraer Datos').first().json.phone_last10 }}
- pushName: {{ $('Edit Fields - Extraer Datos').first().json.pushName }}
- resumen historial: {{ $('Get Paciente Context').first().json.resumen_clinico || 'Sin historial registrado todavia.' }}

Usa esta info para razonar (identificar al paciente, contextualizar). NO la copies al mensaje al paciente.

**Para `buscar_paciente_dentalink`**: copiá EXACTAMENTE el valor de `phone_last10` de arriba al parámetro `lk`. NO uses ningún ejemplo de toolDescription, NO inventes un número. Solo copiá lo que dice phone_last10 en este contexto. Formato: `{"celular":{"lk":"<phone_last10>"}}` reemplazando `<phone_last10>` por el valor literal que ves arriba.
