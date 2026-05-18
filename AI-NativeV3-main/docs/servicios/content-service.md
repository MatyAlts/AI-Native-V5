# content-service

## 1. Qué hace (una frase)

Ingesta materiales de cátedra (PDF, Markdown, código, texto) subidos por docentes, los segmenta en chunks embebidos con pgvector, y expone un endpoint de retrieval RAG filtrado estrictamente por comisión que el tutor-service consume para anclar sus respuestas socráticas.

## 2. Rol en la arquitectura

Pertenece al **plano pedagógico-evaluativo**. Materializa el componente "Servicio de contenido/RAG" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: mantener el corpus de material de cátedra vectorizado para retrieval semántico, garantizar que el tutor sólo reciba material de la comisión del estudiante (no leak cross-cátedra), y producir el `chunks_used_hash` que queda embebido en el CTR para auditoría de reproducibilidad.

## 3. Responsabilidades

- Exponer `POST /api/v1/materiales` para que docentes suban archivos (hasta 50 MB en F2; PDF, Markdown, ZIP de código, texto).
- Detectar el formato del archivo (`extractors/base.py::detect_format`) y rutear al extractor correspondiente (`extractors/pdf.py`, `markdown.py`, `code.py`, `text.py`).
- Ejecutar el pipeline de ingesta: extraer secciones → chunker estratificado (`services/chunker.py`) → embedder (`embedding/embedder.py`) → persistir en `content_db`.
- Almacenar el archivo original en MinIO (`storage.py`) con key `materials/{tenant_id}/{comision_id}/{material_id}/{filename}`.
- Exponer `POST /api/v1/retrieve` que recibe `query + comision_id + top_k + score_threshold`, hace búsqueda vectorial con `pgvector` (`<=>` distance), filtra por threshold, re-rankea cross-encoder, y devuelve `chunks + chunks_used_hash + latency_ms + rerank_applied`.
- Computar `chunks_used_hash = sha256("|".join(sorted(str(id) for id in chunk_ids)))` — hash determinista por conjunto (no orden) de chunks usados. Lista vacía → hash del string vacío.
- Aplicar **filtro doble** en retrieval (defensa en profundidad): RLS por `tenant_id` + WHERE explícito por `comision_id`.
- Exponer `GET /api/v1/materiales?comision_id=...` para listar materiales de una cátedra.

## 4. Qué NO hace (anti-responsabilidades)

- **NO invoca LLMs directamente**: cuando el embedder es via API externa (Voyage / OpenAI), pasa por [ai-gateway](./ai-gateway.md). RN-101 lo prohíbe para cualquier servicio del sistema.
- **NO mantiene relación FK a `comisiones`**: esa tabla vive en `academic_main` (ADR-003 — no joins cross-base). La consistencia del `comision_id` se valida en la capa de servicio via HTTP a [academic-service](./academic-service.md) en el upload, o se tolera como "huérfano" si la comisión se archiva después.
- **NO clasifica ni analiza el contenido pedagógicamente**: sólo indexa y recupera por similitud. La interpretación socrática la hace el tutor-service al componer el prompt con el contexto RAG.
- **NO cachea queries**: cada `POST /retrieve` pega contra pgvector. Si el tutor pregunta lo mismo dos veces, son dos queries al índice.
- **NO borra materiales físicamente**: `Material.deleted_at` es soft-delete. La query de retrieval ignora materiales con `deleted_at IS NOT NULL` pero los chunks quedan en la DB.

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `POST` | `/api/v1/materiales` | Sube archivo + corre pipeline de ingesta síncrono (F2). 201 con `MaterialOut`. Status del material progresa `uploaded → extracting → chunking → embedding → indexed` (o `failed`). | Rol en `MATERIAL_UPLOAD_ROLES` (docente, docente_admin, superadmin). |
| `GET` | `/api/v1/materiales?comision_id=...` | Lista materiales de la comisión. | Autenticado. |
| `GET` | `/api/v1/materiales/{id}` | Un material específico. | Autenticado. |
| `DELETE` | `/api/v1/materiales/{id}` | Soft-delete (`deleted_at = now()`). | Rol en `MATERIAL_UPLOAD_ROLES`. |
| `POST` | `/api/v1/retrieve` | RAG: vector search → threshold → rerank → top-k. Devuelve `chunks_used_hash`. | Rol en `RETRIEVAL_ROLES` (tutor via service-to-service + docente). |
| `GET` | `/health`, `/health/ready` | Health real con `check_postgres` + `check_minio` + `check_embedder` (epic `real-health-checks`, 2026-05-04). | Ninguna. |

**Ejemplo — request `POST /api/v1/retrieve`**:

```json
{
  "query": "¿Cómo funciona la recursión de cola en Python?",
  "comision_id": "a1a1a1a1-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "top_k": 5,
  "score_threshold": 0.3
}
```

**Response** (extracto — 2 de los 5 chunks retornados):

```json
{
  "chunks": [
    {
      "id": "f1f1f1f1-1111-...",
      "contenido": "La recursión de cola (tail recursion) ocurre cuando la llamada recursiva es la última operación...",
      "material_id": "m1m1m1m1-...",
      "material_nombre": "Unidad 4 — Recursión.md",
      "position": 7,
      "chunk_type": "prose",
      "meta": { "window": 2 },
      "score_vector": 0.81,
      "score_rerank": 0.93
    },
    {
      "id": "f2f2f2f2-...",
      "contenido": "def factorial_tail(n, acc=1):\n    return acc if n==0 else factorial_tail(n-1, n*acc)",
      "material_id": "m1m1m1m1-...",
      "material_nombre": "Unidad 4 — Recursión.md",
      "position": 8,
      "chunk_type": "code_function",
      "meta": { "lang": "python" },
      "score_vector": 0.78,
      "score_rerank": 0.88
    }
  ],
  "chunks_used_hash": "9f8e7d6c5b4a...64hex",
  "latency_ms": 47.3,
  "rerank_applied": true
}
```

El `chunks_used_hash` viaja de aquí al `payload.chunks_used_hash` del evento `prompt_enviado` del CTR, y también al `tutor_respondio` del mismo turno (RN-026). Ambos eventos del turno **deben llevar el mismo valor**.

**Ejemplo — `POST /api/v1/materiales`** (multipart):

```
POST /api/v1/materiales
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="comision_id"

a1a1a1a1-aaaa-aaaa-aaaa-aaaaaaaaaaaa
--boundary
Content-Disposition: form-data; name="file"; filename="unidad4.md"
Content-Type: text/markdown

# Recursión
...
--boundary--
```

Response `201`:

```json
{
  "id": "m1m1m1m1-...",
  "comision_id": "a1a1a1a1-...",
  "tipo": "markdown",
  "nombre": "unidad4.md",
  "tamano_bytes": 24315,
  "storage_path": "materials/aaaaaaaa-.../a1a1a1a1-.../m1m1m1m1-.../unidad4.md",
  "estado": "indexed",
  "chunks_count": 12,
  "content_hash": "c0c0c0c0...64hex",
  "indexed_at": "2026-04-24T14:32:11Z"
}
```

El upload bloquea hasta que el pipeline completo termine (síncrono en F2). Tiempos típicos: Markdown 24 KB ~1s, PDF de 50 páginas ~8-15s (extract + embed).

## 6. Dependencias

**Depende de (infraestructura):**
- PostgreSQL 16 + extensión `pgvector` — base lógica `content_db` (ADR-003). Usuario dedicado `content_user`.
- MinIO (S3-compatible) — bucket `materials` para los archivos originales.
- Embedder: mock por default en dev (determinista, hash-based); en prod puede ser sentence-transformers local (`intfloat/multilingual-e5-large`, 1024 dims) o API externa vía ai-gateway.
- Reranker: identity por default (no reordena); en prod puede ser cross-encoder local o API.

**Depende de (otros servicios):**
- [ai-gateway](./ai-gateway.md) — si el embedder/reranker está configurado como provider externo.

**Dependen de él:**
- [tutor-service](./tutor-service.md) — consumidor principal, llama `POST /retrieve` con `comision_id` mandatorio antes de cada turno con el LLM.
- [web-teacher](./web-teacher.md) — sube materiales via `POST /materiales` desde la vista Materiales.

## 7. Modelo de datos

Base lógica: **`content_db`** (ADR-003). Migraciones Alembic en `apps/content-service/alembic/versions/`.

**Tablas principales** (`apps/content-service/src/content_service/models/material.py`):

- **`materiales`**
  - PK: `id` UUID.
  - `tenant_id` con RLS policy.
  - `comision_id` (UUID, sin FK — la tabla `comisiones` vive en `academic_main`).
  - `tipo`: `pdf | markdown | code_archive | video | text`.
  - `nombre`, `tamano_bytes`, `storage_path` (ruta en MinIO).
  - `estado`: `uploaded | extracting | chunking | embedding | indexed | failed` (FSM del pipeline).
  - `uploaded_by` UUID del docente que subió.
  - `content_hash` SHA-256 del archivo original — detecta re-uploads idénticos.
  - `chunks_count` desnormalizado.
  - `deleted_at` nullable — soft-delete.

- **`chunks`**
  - PK: `id` UUID.
  - `tenant_id` + RLS.
  - `material_id` FK con `ondelete=CASCADE`.
  - `comision_id` UUID redundante (desnormalizado para filtro directo en retrieval sin join).
  - `contenido` TEXT.
  - `contenido_hash` SHA-256 del texto del chunk.
  - `position` INT — orden dentro del material.
  - `chunk_type`: `prose | heading | table | code_function | code_class | code_header | code_file | video_segment`.
  - `embedding` `Vector(1024)` — columna pgvector (dimensión del modelo e5-large).
  - `meta` JSONB — metadata por tipo (página PDF origen, nombre de función, timestamp del video, etc.).

Append-only **por material**: si un material se re-ingesta, se borran los chunks viejos del material y se insertan nuevos en una sola transacción. A diferencia del CTR, acá el append-only no es invariante criptográfico — es pragmático (evita estados inconsistentes durante re-indexing).

## 8. Archivos clave para entender el servicio

- `apps/content-service/src/content_service/services/retrieval.py` — `RetrievalService.retrieve()` con el filtro doble (RLS + WHERE comision_id) y el pipeline vector search → threshold → rerank. `_hash_chunk_ids()` es la función del `chunks_used_hash` que se propaga al CTR.
- `apps/content-service/src/content_service/services/chunker.py` — chunker estratificado: código = 1 chunk por unidad (función/clase) hasta `MAX_CODE_TOKENS = 1500`; prosa = ventanas con solapamiento de 50 tokens; tablas = 1 chunk por tabla aunque sea larga. `CHARS_PER_TOKEN = 4` como aproximación.
- `apps/content-service/src/content_service/services/ingestion.py` — orquesta `detect_format → extract → chunk → embed → persist`. Idempotente por `content_hash`.
- `apps/content-service/src/content_service/extractors/` — un extractor por formato: `pdf.py` (pypdf), `markdown.py` (custom parser de headings/code fences/tables), `code.py` (tree-sitter o heurísticas), `text.py` (split por párrafos).
- `apps/content-service/src/content_service/embedding/embedder.py` — `BaseEmbedder` + `MockEmbedder` (hash-based determinista para tests) + factory `get_embedder()`. Modelo default prod: `intfloat/multilingual-e5-large` (1024 dims).
- `apps/content-service/src/content_service/embedding/reranker.py` — cross-encoder opcional. `IdentityReranker` no reordena (default dev).
- `apps/content-service/src/content_service/services/storage.py` — wrapper sobre boto3 contra MinIO. `make_storage_key()` arma la key con `tenant_id`/`comision_id`/`material_id`.
- `apps/content-service/src/content_service/routes/retrieve.py` — el endpoint que consume tutor-service. Muy corto: delega todo al service.
- `apps/content-service/alembic/versions/20260521_0001_content_schema_with_rls.py` — schema inicial con RLS (único archivo Alembic del servicio).
- `docs/golden-queries/` — queries de evaluación del retrieval. `make eval-retrieval` las corre como gate de calidad para PRs que toquen este servicio.

**Pipeline de ingesta — flujo paso a paso**:

```
POST /api/v1/materiales (comision_id, file)
  │
  ├─ 1. Validación tamaño (≤50 MB) → 413 si excede
  │
  ├─ 2. detect_format(filename, content) → "pdf" | "markdown" | "code_archive" | "text"
  │                                         → 415 si "unknown"
  │
  ├─ 3. material_id = uuid4()
  │     storage_key = "materials/{tenant_id}/{comision_id}/{material_id}/{filename}"
  │
  ├─ 4. storage.upload(storage_key, content)       ← MinIO
  │
  ├─ 5. INSERT materiales (estado='uploaded', content_hash=sha256(content))
  │
  ├─ 6. UPDATE materiales SET estado='extracting'
  │     sections = extractors[fmt].extract(content)    ← ExtractedSection[]
  │
  ├─ 7. UPDATE materiales SET estado='chunking'
  │     chunks = chunker.chunk_sections(sections)      ← FinalChunk[]
  │
  ├─ 8. UPDATE materiales SET estado='embedding'
  │     vectors = embedder.embed_documents([c.contenido for c in chunks])
  │
  ├─ 9. INSERT chunks (material_id, contenido, embedding=vec, position, chunk_type, meta)
  │     UPDATE materiales SET estado='indexed', chunks_count=N, indexed_at=now()
  │
  └─ 10. Response 201 MaterialOut
```

Si cualquier paso falla, `UPDATE materiales SET estado='failed', error_message=...` y devuelve 500.

**Estrategia de chunking por tipo** (`services/chunker.py`):

| `section_type` | Estrategia | Por qué |
|---|---|---|
| `code_function`, `code_class`, `code_header`, `code_file` | 1 chunk por unidad semántica si `len ≤ MAX_CODE_TOKENS * CHARS_PER_TOKEN` (1500 × 4 = 6000 chars). Si excede, dividir por bloques (`\n\n`). | La función/clase es la unidad atómica — partirla degrada el retrieval. |
| `table` | 1 chunk por tabla (aunque sea muy larga). | Las filas están interrelacionadas; un chunk truncado es irrecuperable semánticamente. |
| `prose`, `heading` | Ventana deslizante `target=512 tokens`, `overlap=50 tokens`, respetando fronteras de oraciones. | El overlap evita perder conceptos que atraviesan el límite de un chunk (ej. definición seguida de ejemplo). |
| `video_segment` | 1 chunk por segmento transcrito. | Cada segmento viene con su timestamp — preservar la unidad de tiempo. |

`CHARS_PER_TOKEN = 4` es una aproximación para español. Si el modelo de embeddings es multilingual-e5-large, la ventana real de 512 tokens (2048 chars) encaja cómoda dentro del contexto máximo del encoder.

**Retrieval — filtro doble y reranking** (`services/retrieval.py:38`):

```
1. Embed query: q_vec = embedder.embed_query(query)

2. Vector search con filtro doble (defensa en profundidad):
     SELECT c.*, m.nombre, 1 - (c.embedding <=> :q) AS score_vector
     FROM chunks c
     JOIN materiales m ON m.id = c.material_id
     WHERE c.comision_id = :comision_id     ← WHERE explícito
       AND c.embedding IS NOT NULL
       AND m.deleted_at IS NULL              ← ignora soft-deleted
     ORDER BY c.embedding <=> CAST(:q AS vector)
     LIMIT :VECTOR_TOP_N                     ← default 20
   -- RLS aplica automáticamente vía current_setting('app.current_tenant')

3. Filtro por score: descartar chunks con score_vector < score_threshold (default 0.3)

4. Reranking cross-encoder:
     rerank_scores = reranker.rerank(query, [c.contenido for c in above_threshold])
   (IdentityReranker devuelve los mismos scores; el real reordena)

5. Ordenar por score_rerank desc, tomar top_k (default 5)

6. chunks_used_hash = sha256("|".join(sorted(str(c.id) for c in top_k)))

7. Return RetrievalResponse(chunks, chunks_used_hash, latency_ms, rerank_applied)
```

**`chunks_used_hash` — fórmula canónica** (RN-026, `retrieval.py:136`):

```python
def _hash_chunk_ids(ids: list[UUID]) -> str:
    sorted_ids = sorted(str(i) for i in ids)
    joined = "|".join(sorted_ids)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
```

- **Ordenado** antes de join → el hash no depende del orden de retrieval (lo que importa es el **conjunto**).
- **Separador `|`** — UUIDs no contienen `|`, no hay colisión.
- **Lista vacía** → `sha256(b"").hexdigest()` = `"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"`. Es el hash estándar del string vacío, no un valor "nulo" simbólico.

## 9. Configuración y gotchas

**Env vars críticas** (`apps/content-service/src/content_service/config.py`):

- `CONTENT_DB_URL` — default `postgresql+asyncpg://content_user:content_pass@127.0.0.1:5432/content_db`.
- `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_MATERIALS` — default apuntan a MinIO local.
- `EMBEDDER` — override del factory. Default `mock` (reproducible, sin red).
- `RERANKER` — default `identity`.
- `STORAGE` — default `mock` en dev (no sube a MinIO; escribe a memoria/tmp).

**Puerto de desarrollo**: `8009`.

**Gotchas específicos**:

- **`comision_id` mandatorio en retrieve**: el schema `RetrievalRequest` lo valida. Omitirlo es 422. El filtro doble (RLS + WHERE) es defensa en profundidad — sin el WHERE explícito, un bug en `SET LOCAL app.current_tenant` dejaría filtrar chunks de otras comisiones del mismo tenant. El test `test_retrieval_comision_isolation.py` bloquea regresiones.
- **`chunks_used_hash` debe viajar idéntico al CTR**: la función `_hash_chunk_ids` en este servicio debe producir el mismo resultado que la implementación en cualquier otro lado que compute el hash. Fórmula canónica (RN-026): `sha256("|".join(sorted(str(id) for id in chunk_ids)))`. Lista vacía → `sha256(b"").hexdigest()` (no es un string literal "vacío" — es el hash real).
- **Ingesta síncrona en F2**: `POST /materiales` puede tardar varios segundos (pipeline completo). En F3+ está previsto mover a job async con polling. Hoy el frontend bloquea la UI durante el upload.
- **`EMBEDDING_DIM = 1024` hardcoded**: cambiar embedder a un modelo con otra dimensión requiere migración de la columna `Vector(1024)` de chunks + re-ingest de todos los materiales. No hay compat shim.
- **Extractors minimalistas**: `markdown.py` parser propio (sin PyMarkdown), `code.py` con heurísticas para detectar funciones/clases (no tree-sitter en todos los lenguajes). Para código Python es razonable; para otros lenguajes la segmentación es peor.
- **Soft-delete + chunks**: `DELETE /materiales/{id}` marca `deleted_at` pero los `chunks` quedan. El retrieval filtra `m.deleted_at IS NULL`, entonces los chunks del material borrado no aparecen — pero ocupan espacio y se cuentan en estadísticas crudas. El cleanup definitivo es manual/batch.
- **Re-upload del mismo archivo**: el `content_hash` permite detectar duplicados. El comportamiento por default **verificar en código**: si es idempotente (reusa el material existente) o crea un material nuevo con el mismo hash. Si hay diferencia entre docentes (mismo archivo subido por dos), la RLS ya los separa por tenant.
- **`score_threshold` en retrieve**: el default del schema es 0.3 (razonable para e5-large). Valores altos (>0.7) devuelven pocos chunks o ninguno; valores bajos (<0.2) devuelven ruido. El `tutor-service` pasa `score_threshold=0.3` hardcoded (`clients.py:98`).
- **`VECTOR_TOP_N = 20` antes del rerank**: se traen 20 candidatos, se filtran por threshold, se re-rankean, y se devuelven `top_k` (default 5). Si `VECTOR_TOP_N == top_k`, el rerank es no-op (no hay material para reordenar). El default preserva 4x para que el rerank pueda hacer trabajo.

**Traceback — retrieve sin comision_id** (pydantic):

```
HTTP/1.1 422 Unprocessable Entity
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "comision_id"],
      "msg": "Field required"
    }
  ]
}
```

**Traceback — upload con formato desconocido**:

```
HTTP/1.1 415 Unsupported Media Type
{
  "detail": "Formato no soportado para 'archivo.xyz'. Tipos válidos: PDF, Markdown, ZIP de código, texto plano."
}
```

## 10. Relación con la tesis doctoral

El content-service es la **puerta de entrada del corpus institucional** al tutor. La Sección 7 de la tesis sostiene que un tutor socrático basado en LLM sólo es pedagógicamente defendible si sus respuestas se anclan en material curado por la cátedra — no en conocimiento general del modelo base. El `chunks_used_hash` en el evento `prompt_enviado` es la prueba de ese anclaje: permite, para cualquier respuesta registrada, recuperar los chunks exactos que se le presentaron al modelo y verificar que eran del material de esa comisión.

El filtro doble (RLS + WHERE `comision_id`) materializa el principio de **aislamiento pedagógico** de la tesis: un estudiante de la comisión A no debe recibir, ni siquiera por error, material de la comisión B. Con RLS solo alcanzaría a nivel `tenant_id`; el WHERE explícito agrega la granularidad de comisión.

**Por qué importa el chunking estratificado, no chunking uniforme**: si todo el material se partiera en ventanas de 512 tokens sin distinguir tipo, una función Python de 100 líneas se partiría por la mitad y el retrieval devolvería "medio definición de función, medio código desparejo". Con el chunker estratificado, la unidad semántica de código (la función completa) queda como un solo chunk y se recupera íntegra. La tesis (Capítulo 7 sección RAG) argumenta que este "respeto a la unidad pedagógica" es lo que hace que el tutor pueda apuntar al material exacto que el docente quiso enseñar.

**Por qué el `chunks_used_hash` es por conjunto y no por secuencia**: si el tutor reordena los chunks al componer el prompt (ej. poner el más relevante al final para el "recency bias" del LLM), el hash debe seguir siendo el mismo — lo que importa auditar es **qué material se presentó**, no el orden. Ordenar los IDs antes de hashear lo garantiza.

La decisión de usar **pgvector dentro de Postgres** (vs. una vector DB externa) viene de [ADR-011](../adr/011-pgvector-rag.md): un solo sistema de persistencia, mismas garantías RLS, mismas migraciones Alembic, y suficiente escala para el piloto UNSL (<100 comisiones, <10k materiales).

**Gap declarado**: el reranking con cross-encoder local está arquitecturalmente previsto pero el default dev es `IdentityReranker` (no-op). La calidad del retrieval hoy depende del score vectorial puro. `make eval-retrieval` con las `golden-queries` es el gate — si el reranker real mejora resultados y se activa, la misma suite lo valida.

## 11. Estado de madurez

**Tests** (5 archivos unit):
- `tests/unit/test_chunker.py` — chunking estratificado, solapamiento, edge cases.
- `tests/unit/test_detect_format.py` — detección de formato por extensión y magic bytes.
- `tests/unit/test_markdown_extractor.py` — parser de headings, code fences, tables.
- `tests/unit/test_code_extractor.py` — segmentación por función/clase.
- `tests/unit/test_mock_embedder.py` — determinismo del embedder mock.

Más `docs/golden-queries/` con queries de evaluación empírica.

**Known gaps**:
- Sin tests de integración contra pgvector real (solo mocks del embedder).
- Ingesta síncrona bloquea el upload (F3+ prevé async).
- Retrieval sin tests de aislamiento cross-comisión/cross-tenant con DB real (sólo revisión de código).
- Soft-delete deja chunks huérfanos.
- `IdentityReranker` como default en dev — calidad real del retrieval depende del embedder solo.
- **4 de 5 materiales en `content_db.materiales` apuntan a `materia_id` huérfana** (no existe en `academic_main.materias`): 22 chunks indexados con embeddings pgvector NUNCA serán retrievados por alumno real con esa `materia_id`. Deuda operacional pre-piloto (corregible con re-import).
- **Bug `GET /api/v1/materiales` 500 con role `docente_admin`** (audit 2026-05-07): verificar si fue fixed; mantener como bug conocido si no.

**Fase de consolidación**:
- F2 — schema inicial, pipeline de ingesta, retrieval con filtro doble (`docs/F2-STATE.md`).
- F3 — integración con tutor-service (el `chunks_used_hash` atraviesa al CTR).
- F8+ — job async de ingesta y cross-encoder real quedan como deuda conocida.
- 2026-06-06 (epic `add-materia-id-to-materiales-and-chunks`, migración `20260606_0001`) — columna `materia_id` agregada a `materiales` y `chunks`. Permite filtrar por materia (no solo por comisión).
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_postgres + check_minio + check_embedder`.
