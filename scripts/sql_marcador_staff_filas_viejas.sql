-- sql_marcador_staff_filas_viejas.sql (2026-10-05) — NO ejecutado.
-- Saca la ORDEN DE SILENCIO de los avisos "[ATENCION HUMANA ...]" que ya estan guardados en la memoria del bot
-- (n8n_chat_histories, Supabase v3). Conserva el prefijo y el autor, que el panel necesita. Idempotente.
-- Correr DESPUES de aplicar scripts/apply_fix_marcador_staff_agendar_ventana.py. Requiere OK de Lucas.

-- 0) Tipo de la columna (si es json en vez de jsonb, ajustar el UPDATE)
SELECT data_type FROM information_schema.columns WHERE table_name = 'n8n_chat_histories' AND column_name = 'message';

-- 1) Cuantas filas se tocarian
SELECT count(*) AS filas_a_corregir
FROM n8n_chat_histories
WHERE message->>'content' LIKE '[ATENCION HUMANA%Mantente en silencio y NO respondas%';

-- 2) Correccion (descomentar para ejecutar)
-- UPDATE n8n_chat_histories
-- SET message = jsonb_set(
--       message::jsonb, '{content}',
--       to_jsonb(regexp_replace(
--           message->>'content',
--           ' NO es output tuyo, es un humano atendiendo este chat\. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on\.',
--           ' Mensaje del staff, no es output tuyo.'))
--   )
-- WHERE message->>'content' LIKE '[ATENCION HUMANA%Mantente en silencio y NO respondas%';
