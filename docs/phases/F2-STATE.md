# Estado del repositorio — F2 completado

F2 implementa **ingesta de materiales multi-formato + RAG retrieval** como
cimiento del tutor socrático (F3). El content-service es el único servicio
que el tutor consultará al responder a estudiantes — por eso su calidad y
su aislamiento son críticos.

## Entregables F2

### Modelos de persistencia

`apps/content-service/src/content_service/models/`:

- `Material` — un archivo subido por un docente a una comisión.
  Estados: `uploaded → extracting → chunking → embedding → indexed | failed`.
- `Chunk` — unidad semántica del material con embedding `Vector(1024)`
  de pgvector, tipo (`prose`/`code_function`/`table`/etc.), posición
  global y metadata rica (`page`, `start_line`, `heading_path`).
- Constraint único `(tenant_id, material_id, position)` para evitar
  duplicados en re-ingestas.

### Schemas Pydantic

`apps/content-service/src/content_service/schemas/__init__.py`:

- `MaterialOut`, `MaterialListOut`, `ChunkOut`, `IngestionStatus`.
- **`RetrievalRequest`** con `comision_id: UUID` marcado MANDATORIO
  (propiedad crítica — sin esto el tutor podría recibir chunks de otras
  comisiones).
- `RetrievalResponse` con `chunks_used_hash` (SHA-256 del conjunto de
  chunks recuperados, ordenados) para que el tutor lo incluya en el
  evento CTR y cualquiera pueda reproducir la misma recuperación.

### Extractores

`apps/content-service/src/content_service/extractors/`, uno por formato con
interfaz uniforme `BaseExtractor.extract(content, filename) → ExtractionResult`:

- **Markdown** — respeta estructura de headings, acumula `heading_path`
  completo (ej. "Capítulo 1 > Sección A > Subtema") para preservar
  contexto.
- **PDF** — preferencia por `unstructured` (detecta tablas, listas, OCR
  automático para escaneados); fallback a `pypdf` (más liviano, suficiente
  en CI).
- **Code ZIP** — descomprime, filtra por extensión (13 lenguajes
  soportados), divide por funciones/clases con regex heurísticas para los
  lenguajes más comunes (Python, JS/TS, Java, Go, Rust). Ignora
  `__MACOSX`, dot-files, entries sin lenguaje conocido.
- **Text** — párrafos por doble salto de línea.
- Factory `get_extractor(format_name)` + `detect_format()` con magic
  bytes (`%PDF-`, `PK\x03\x04`) y fallback por extensión.

### Chunker estratificado

`services/chunker.py`:

- **Código**: 1 sección = 1 chunk salvo que supere `MAX_CODE_TOKENS=1500`;
  entonces se divide por bloques lógicos (doble salto de línea).
- **Prosa**: ventana deslizante con `target=512` tokens y `overlap=50`
  tokens. Respeta límites de oraciones (split heurístico por puntuación
  seguida de mayúscula), conservando las últimas oraciones como
  solapamiento.
- **Tablas**: 1 chunk por tabla (atómica por diseño; la tabla es la
  unidad semántica mínima).
- Hash SHA-256 determinista de cada chunk para idempotencia en re-ingesta.
- Posiciones globales al documento, no por sección.

### Embeddings y re-ranking

`embedding/`:

- `BaseEmbedder` con 3 implementaciones:
  - `MockEmbedder` — hash SHA-512 → 1024 floats normalizados, determinista
    (mismo texto → mismo vector). Para CI rápido.
  - `SentenceTransformerEmbedder` — `intfloat/multilingual-e5-large`
    local con GPU si disponible, convención e5 (`passage:` / `query:`).
  - Factory `get_embedder()` con fallback automático a Mock si no hay
    sentence-transformers instalado.
- `BaseReranker` con `IdentityReranker` (tests) y `CrossEncoderReranker`
  (bge-reranker-base con sigmoid de logits).

### Pipeline de ingesta

`services/ingestion.py`:

- `IngestionPipeline.ingest(material, content, filename)` orquesta:
  `detect_format → extract → chunk → embed en batch → persistir chunks
  (DELETE viejos + INSERT nuevos en misma transacción)`.
- Actualiza `material.estado` en cada paso para que el frontend pueda
  mostrar progreso.
- `try/except` envuelve todo: en error, setea `estado="failed"` con
  `error_message` truncado a 500 chars.

### Servicio de retrieval

`services/retrieval.py`:

- **Filtro doble en defensa en profundidad**:
  1. RLS por `current_setting('app.current_tenant')` → filtra por tenant.
  2. `WHERE c.comision_id = :comision_id` explícito en la query SQL.
- SQL directo con operador `<=>` de pgvector (cosine distance).
- Pipeline: top-20 vector → threshold por `score_vector` → re-ranking
  cross-encoder → top-k final.
- Devuelve `chunks_used_hash = SHA-256(sorted_chunk_ids)` — necesario
  para que el tutor emita eventos CTR reproducibles en F3.
- Mide `latency_ms` en el recorrido completo.

### Storage

`services/storage.py`:

- Abstracto `BaseStorage` con tres implementaciones:
  - `MockStorage` — in-memory, para tests.
  - `S3Storage` — boto3 lazy-loaded (MinIO compatible).
- Convención: `materials/{tenant_id}/{comision_id}/{material_id}/original.{ext}`.
- Factory por env `STORAGE=mock|s3`.

### Routes del content-service

`routes/materiales.py`:
- `POST /api/v1/materiales` — multipart upload con validación de tamaño
  (50 MB max) y formato; ejecuta pipeline completo y devuelve el Material
  con estado final.
- `GET /api/v1/materiales` — listado con filtro opcional por `comision_id`,
  cursor pagination.
- `GET /api/v1/materiales/{id}`.
- `DELETE /api/v1/materiales/{id}` — soft-delete.

`routes/retrieve.py`:
- `POST /api/v1/retrieve` — consume `RetrievalRequest` con `comision_id`
  mandatorio; roles permitidos: `docente`, `docente_admin`, `superadmin`,
  `tutor_service` (este último es service-account del tutor en F3).

### Migración Alembic

`alembic/versions/20260521_0001_content_schema_with_rls.py`:

- `CREATE EXTENSION IF NOT EXISTS vector`.
- Tabla `materiales` con 15 columnas, 5 índices incluyendo compuesto
  `(tenant_id, comision_id)` para listados.
- Tabla `chunks` con columna `embedding vector(1024)` + FK a `materiales`
  con `ondelete CASCADE`.
- **Índice IVFFlat** con `vector_cosine_ops` y `lists=100` para similarity
  search aproximada (recall ~95%, compensado por re-ranker posterior).
- `apply_tenant_rls()` llamado sobre ambas tablas.

### api-gateway actualizado

`apps/api-gateway/src/api_gateway/routes/proxy.py` con 2 rutas nuevas:
- `/api/v1/materiales/*` → content-service
- `/api/v1/retrieve` → content-service

### Golden queries

`docs/golden-queries/programacion-2.yaml`:

- 15 queries curadas sobre temas típicos de Programación 2: recursión
  (3 queries), list comprehensions (2), manejo de excepciones (2), clases
  y herencia (3), testing con pytest (2), estructuras de datos (3).
- Formato: query + `expected_contains_any` (OR) + `min_score` + comisión.
- `scripts/eval-retrieval.py` las ejecuta contra `/api/v1/retrieve` y
  reporta hit rate, latencia P50/P95, y diagnostica cada fallo.
- Objetivo en F3: mantener hit rate ≥90% mientras se itera el chunker/
  embedder/re-ranker.

### Makefile

Nuevos targets:
- `make migrate` — ahora incluye `content-service` además de `academic`,
  `ctr` e `identity`.
- `make eval-retrieval` — corre las golden queries contra el RAG local.

## Tests F2 — 24/24 pasan

```
tests/unit/test_chunker.py .................... 6 tests
  - codigo_corto_es_un_chunk
  - codigo_muy_grande_se_subdivide
  - prosa_usa_ventana_deslizante
  - tabla_es_un_unico_chunk
  - hash_es_determinista
  - posiciones_incrementales_entre_secciones

tests/unit/test_code_extractor.py ............. 4 tests
  - extrae_funciones_python
  - detecta_lenguaje_por_extension (9 langs)
  - ignora_archivos_no_codigo
  - archivo_sin_funciones_detectadas

tests/unit/test_detect_format.py .............. 5 tests
  - pdf_por_magic_bytes
  - markdown_por_extension
  - zip_de_codigo
  - texto_plano
  - formato_desconocido

tests/unit/test_markdown_extractor.py .......... 4 tests
  - extrae_secciones_por_headings
  - acumula_heading_path
  - maneja_documento_sin_headings
  - preserva_utf8

tests/unit/test_mock_embedder.py ............... 5 tests
  - es_determinista
  - textos_distintos_producen_vectores_distintos
  - dimension_correcta
  - vector_normalizado (norma = 1.0)
  - batch_de_documentos
```

## Suite completa del repo — 64/64 pasan

```
packages/contracts/tests/test_hashing.py .......................... 7  (CTR)
apps/academic-service/tests/unit/test_schemas.py .................. 10 (F1)
apps/academic-service/tests/integration/test_casbin_matrix.py ..... 23 (F1)
apps/content-service/tests/unit/*.py .............................. 24 (F2)
──────────────────────────────────────────────────────────────────────
                                                                    64
```

## Cómo validar F2 localmente

```bash
# Asegurarse de tener infra con pgvector
make dev-bootstrap

# Aplicar migraciones (incluye el schema del content-service)
make migrate

# Arrancar servicios
make dev

# Subir un material (ejemplo con un PDF)
curl -X POST http://localhost:8000/api/v1/materiales \
  -H 'X-User-Id: 10000000-0000-0000-0000-000000000001' \
  -H 'X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' \
  -H 'X-User-Email: docente@uni-demo.edu' \
  -H 'X-User-Roles: docente' \
  -F 'comision_id=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \
  -F 'file=@apunte_recursion.pdf'

# Hacer un retrieval
curl -X POST http://localhost:8000/api/v1/retrieve \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: 10000000-0000-0000-0000-000000000001' \
  -H 'X-Tenant-Id: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' \
  -H 'X-User-Email: docente@uni-demo.edu' \
  -H 'X-User-Roles: docente' \
  -d '{
    "query": "qué es la recursión",
    "comision_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "top_k": 5
  }'

# Evaluar calidad contra las golden queries
make eval-retrieval
```

## Correr tests rápidos sin Docker

```bash
EMBEDDER=mock RERANKER=identity STORAGE=mock \
PYTHONPATH=apps/academic-service/src:apps/content-service/src:packages/contracts/src:packages/test-utils/src \
  python3 -m pytest \
  apps/academic-service/tests/unit/ \
  apps/academic-service/tests/integration/test_casbin_matrix.py \
  apps/content-service/tests/unit/ \
  packages/contracts/tests/ -v

# Esperado: 64 passed
```

## Qué queda fuera de F2

- **Integration test end-to-end** del retrieval con testcontainers +
  pgvector real: diseñado pero no escrito en este turno. Requiere levantar
  imagen `pgvector/pgvector:pg16`, aplicar migración, insertar materiales
  y chunks, verificar aislamiento entre 2 tenants. Se escribe al inicio
  de F3 como complemento.
- **web-teacher** con gestión de materiales (list/upload/delete):
  pospuesto por ahora; la funcionalidad core (API del content-service)
  está lista y puede consumirse con `curl` mientras tanto.
- **Ingesta asíncrona con Redis Streams** para archivos grandes (>10 MB
  PDF o videos): hoy es síncrona dentro del request HTTP. Llega en F3.

## Próxima fase — F3 (meses 7-10)

El motor pedagógico completo. Esta es la fase densa donde vive el núcleo
de la tesis:

1. **CTR criptográfico** — workers particionados de Redis Streams,
   cadena SHA-256 con verificación al consumir, DLQ con flag
   `integrity_compromised=true`.
2. **Tutor socrático** — FastAPI + SSE streaming, prompt cargado desde
   Git con verificación de hash (PromptLoader fail-loud), invocación
   via ai-gateway con budget, retrieval previo al content-service,
   emisión de eventos al CTR.
3. **governance-service** — clone del repo de prompts, verificación GPG
   de commits, API `/active_configs` que expone hash actual.
4. **Clasificador N4** — árbol de decisión sobre episodio cerrado,
   cálculo de las 3 coherencias (temporal, código-discurso,
   inter-iteración), clasificación `delegacion_pasiva | apropiacion_superficial
   | apropiacion_reflexiva` con reference_profiles por curso.
5. **web-student** — editor Monaco, chat con el tutor, visualización
   de las 3 coherencias post-episodio.
6. **Tests**:
   - Reproducibilidad: dado un episodio, verificar que re-clasificando
     con el mismo `classifier_config_hash` da el mismo resultado.
   - Integridad de cadena: manipular eventos y verificar detección.
   - Calidad del retrieval: correr golden queries sobre cursos reales.
