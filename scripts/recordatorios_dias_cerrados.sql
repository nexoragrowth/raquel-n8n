-- =============================================================================
-- recordatorios_config.dias_cerrados  —  "Días sin atención" (19/11/2026)
-- =============================================================================
-- Días que la clínica NO atiende (feriados, puentes, vacaciones), ISO YYYY-MM-DD. Los carga la clínica desde el panel.
-- El workflow de Recordatorios los usa así (Gate + "Fecha Mañana", ver recordatorios/gate_dias_cerrados.sql y recordatorios/fecha_manana.js):
--   · la fecha objetivo = 2 DÍAS HÁBILES después, salteando fines de semana Y estos días;
--   · la corrida automática de un día cerrado no corre.
-- Así cada día hábil queda avisado una sola vez (con el lunes cerrado, el jueves avisa el martes).
-- Aditiva e idempotente: con la lista vacía el comportamiento es IDÉNTICO al de antes. Aplicar ANTES de desplegar los dos nodos del workflow
-- (el Gate falla abierto si falta la columna, pero conviene que exista).
-- =============================================================================

alter table public.recordatorios_config
  add column if not exists dias_cerrados date[] not null default '{}';

comment on column public.recordatorios_config.dias_cerrados is
  'Días sin atención (feriados, puentes, vacaciones). El bot cuenta los 2 días hábiles salteándolos y no corre la corrida automática esos días.';
