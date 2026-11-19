SELECT COALESCE(bool_or(
    (NOT c.activo)
    OR ((now() AT TIME ZONE 'America/Argentina/Jujuy')::date = ANY(c.dias_suspendidos))
    OR ((now() AT TIME ZONE 'America/Argentina/Jujuy')::date = ANY(c.dias_cerrados))
    OR (c.suspender_desde IS NOT NULL
        AND (now() AT TIME ZONE 'America/Argentina/Jujuy')::date
            BETWEEN c.suspender_desde AND c.suspender_hasta)
  ), false) AS suspender,
  COALESCE((SELECT array_agg(to_char(d, 'YYYY-MM-DD') ORDER BY d)
            FROM public.recordatorios_config c2, unnest(c2.dias_cerrados) AS d
            WHERE c2.id = 1), '{}'::text[]) AS dias_cerrados
FROM public.recordatorios_config c
WHERE c.id = 1;
