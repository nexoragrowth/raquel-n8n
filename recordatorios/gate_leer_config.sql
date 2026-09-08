SELECT COALESCE(bool_or(
    (NOT c.activo)
    OR ((now() AT TIME ZONE 'America/Argentina/Jujuy')::date = ANY(c.dias_suspendidos))
    OR (c.suspender_desde IS NOT NULL
        AND (now() AT TIME ZONE 'America/Argentina/Jujuy')::date
            BETWEEN c.suspender_desde AND c.suspender_hasta)
  ), false) AS suspender,
  (SELECT kb.contenido FROM public.knowledge_base kb WHERE kb.id = 21) AS precio_contenido
FROM public.recordatorios_config c
WHERE c.id = 1;
