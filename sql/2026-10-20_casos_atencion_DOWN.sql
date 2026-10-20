-- sql/2026-10-20_casos_atencion_DOWN.sql  -  vuelta atras de ATE-02 (casos de la bandeja de Atencion).
-- Orden: PRIMERO los triggers sobre las tablas del bot (asi ningun insert del bot vuelve a pasar por codigo de casos),
-- despues las funciones y las tablas. escalaciones_log y triaje_urgencias_log quedan exactamente como estaban (sus filas no se tocan).
-- OJO: DROP TABLE borra los casos y su bitacora. Si ya hubo casos reales y solo hace falta frenar, NO usar esto:
--   alter table public.escalaciones_log disable trigger casos_desde_escalacion_trg;
--   alter table public.triaje_urgencias_log disable trigger casos_desde_triaje_trg;
-- ANTES en el panel: apagar la bandeja (ATENCION_BANDEJA sin 1) para que no consulte una tabla que ya no existe.
begin;
set local lock_timeout = '3s';
drop trigger if exists casos_desde_escalacion_trg on public.escalaciones_log;
drop trigger if exists casos_desde_triaje_trg on public.triaje_urgencias_log;
drop function if exists public.casos_tg_desde_escalacion();
drop function if exists public.casos_tg_desde_triaje();
drop function if exists public.casos_backfill(integer);
drop function if exists public.caso_reabrir(bigint, text);
drop function if exists public.caso_resolver(bigint, text, text, boolean);
drop function if exists public.caso_esperando(bigint, text);
drop function if exists public.caso_soltar(bigint, text);
drop function if exists public.caso_tomar(bigint, text);
drop function if exists public.registrar_aviso(text, text, text, text, text, bigint, text, timestamptz, jsonb, integer);
drop function if exists public.casos_tipo_de_escalacion(text, text, jsonb);
drop function if exists public.casos_actor_ok(text);
drop table if exists public.casos_eventos;
drop table if exists public.casos;               -- sale sola de la publicacion supabase_realtime
drop table if exists public.casos_prefijos;
notify pgrst, 'reload schema';
commit;
