-- Vuelta atrás de sql/2026-10-20_panel_seguimientos_citas.sql
drop function if exists public.panel_seguimientos_citas(date);
notify pgrst, 'reload schema';
