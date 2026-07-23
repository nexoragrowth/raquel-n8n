# KB del bot Asiri — base de conocimiento versionada

Backup versionado de la base de conocimiento (RAG) del bot de WhatsApp de la Dra. Raquel.
Se creó tras perderse el KB al borrarse el proyecto Supabase viejo — para que **no se vuelva a perder**.

## Archivos
- `knowledge_base_seed.json` — los 35 docs (formato `{categoria, titulo, contenido, metadata}`,
  mismos nombres de columna que la tabla). Fuente de la reconstrucción: PDF de feedback de Raquel +
  minado de respuestas históricas del bot en Chatwoot.
- `schema.sql` — DDL de la tabla `knowledge_base` + las RPCs `match_documents` / `buscar_conocimiento`
  (el nodo Vector Store de n8n llama `match_documents`).
- `../scripts/reseed_knowledge_base.py` — carga los docs faltantes con embeddings
  (`text-embedding-3-small`, 1536 dims). Idempotente por `titulo`.

## Contenido
- **18 docs operativos/de comportamiento** (escalación, urgencias, voz, privacidad, tipos de turno,
  política de pago) — del cuestionario "Para Lucas Programador".
- **17 docs de cara al paciente** (horarios, precio de consulta, obra social, formas de pago, dirección,
  tratamientos, devolución) — reconstruidos 2026-07-08.

## Cómo recrear el KB desde cero
```bash
# 1. Correr kb/schema.sql en el SQL Editor del proyecto Supabase target.
# 2. Cargar los docs + embeddings:
export SUPABASE_URL="https://<ref>.supabase.co"
export SUPABASE_KEY="<service_role key>"
export OPENAI_API_KEY="sk-..."
python scripts/reseed_knowledge_base.py kb/knowledge_base_seed.json --apply
```

## Privacidad (candado #4)
El doc **"Datos de cuenta para transferencia"** tiene el CUIT, CBU y nro. de cuenta **redactados** en
este repo (es público). Los valores reales viven solo en la tabla `knowledge_base` del proyecto Supabase
privado (y en las respuestas del bot). Si se recrea el KB desde este seed, ese doc queda sin los números
— completarlos a mano desde la fuente privada.

## Mantenimiento
Los **reportes semanales** del bot autodetectan huecos del KB (`[info_faltante]`). Revisarlos de forma
continua es el radar para saber qué docs agregar, sin adivinar.
