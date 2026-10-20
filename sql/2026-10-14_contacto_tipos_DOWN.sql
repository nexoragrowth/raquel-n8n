-- sql/2026-10-14_contacto_tipos_DOWN.sql  -  vuelta atras de la ESTRUCTURA del Dia 1.
-- ANTES: el v6 sin PUT-B (restaurar el backup PRE) o con seg:off puesto; si no, cada mensaje llama a una funcion que ya no existe
-- (el v6 deja pasar por continueOnFail y 'Seg: Aviso tecnico' avisa al grupo cada 6 h que la segmentacion no rige).
-- OJO: DROP TABLE borra el historial de tipos. Si ya hubo tipos reales, NO usar esto: deshacer = cerrar los tipos
-- (cargar_lista_semilla.py --deshacer) y dejar la tabla. Los defaults de permisos cerrados NO se revierten (cerrarlos es lo correcto).
begin;
set local lock_timeout = '3s';
drop function if exists public.contacto_tipo_cerrar(text, text, text, text, text, uuid);
drop function if exists public.contacto_tipo_poner(text, text, text, text, text, text, text, uuid, boolean);
drop function if exists public.contacto_ruta(text);
drop function if exists public.contacto_tel_normalizar(text);
drop table if exists public.contacto_roles_notas;
drop table if exists public.contacto_roles;            -- se lleva sus triggers, indices y la FK hacia pacientes
drop function if exists public.contacto_roles_tg_inmutable();
drop function if exists public.contacto_roles_tg_no_truncate();
notify pgrst, 'reload schema';
commit;
