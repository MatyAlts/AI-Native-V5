## Why

El content-service hoy scopea materiales y chunks por `comision_id`, pero pedagógicamente el material de referencia pertenece a la **materia** (Algoritmos, Estructura de Datos, etc.), no a una comisión particular. Un profesor que dicta 3 comisiones de la misma materia tiene que subir el mismo PDF 3 veces. Además, no existe UI para subir materiales — solo endpoints crudos sin frontend.

Cambiar el scoping a `materia_id` alinea el modelo de datos con la realidad académica, reduce duplicación de contenido, y habilita que el generador de TPs con IA (`POST /api/v1/tareas-practicas/generate`) recupere contexto RAG relevante al generar ejercicios.

## What Changes

- **Migration de scoping `comision_id` → `materia_id`** en modelos `Material` y `Chunk` del content-service. Alembic migration que agrega `materia_id`, popula desde la comisión asociada, y depreca `comision_id` (nullable transitorio, drop en migration futura).
- **Endpoints de content-service actualizados**: upload, list, retrieve reciben `materia_id` en vez de `comision_id`. El endpoint `/api/v1/retrieve` filtra chunks por `materia_id`.
- **Página de materiales en web-teacher**: upload de archivos (PDF, MD, ZIP, TXT) scoped a la materia de la comisión del docente. Lista de materiales con estado de procesamiento (pending/processing/ready/error). Preview de chunks procesados.
- **Vista de materiales en web-admin**: listado por facultad → materia con conteo de materiales y chunks. Acciones de borrado con confirmación.
- **Integración con TP generator**: `POST /api/v1/tareas-practicas/generate` pasa `materia_id` al governance-service, que a su vez puede hacer retrieve al content-service para enriquecer el prompt de generación con material de referencia.
- **Tutor content client actualizado**: `ContentClient.retrieve()` en tutor-service pasa `materia_id` (ya disponible en `SessionState`) en vez de `comision_id`.

## Capabilities

### New Capabilities
- `material-upload-ui`: Página en web-teacher para subir materiales a la materia del docente. Drag-and-drop, progress bar, lista con estado de ingestion, preview de chunks. Validación de tipos y tamaño (50MB max).
- `material-admin-view`: Vista en web-admin de materiales por facultad → materia. Conteos, estado de ingestion, acciones de borrado.
- `rag-materia-scoping`: Migration y refactor del content-service para scopear materiales y chunks por `materia_id` en vez de `comision_id`. Incluye actualización del endpoint de retrieve y del tutor content client.

### Modified Capabilities
- `academic-comisiones`: La comisión ya no es el scope de materiales — la materia sí. El lookup `comision → materia_id` se usa para resolver el scope en upload y retrieve desde contextos donde solo se tiene `comision_id`.

## Impact

- **content-service**: Migration de modelos (`Material`, `Chunk`), actualización de rutas y servicio de retrieval. Cambio de `comision_id` a `materia_id` en queries SQL con pgvector.
- **tutor-service**: `ContentClient.retrieve()` cambia parámetro `comision_id` → `materia_id`. `SessionState` ya tiene `materia_id` cacheado (ADR-040).
- **academic-service**: Endpoint `/api/v1/tareas-practicas/generate` propaga `materia_id` al retrieve de contexto RAG. Endpoint lookup `comision → materia_id` (ya existe via GET comisión).
- **web-teacher**: 1 página nueva (Materiales) con upload + listado.
- **web-admin**: 1 vista nueva de materiales por materia.
- **content_db**: Alembic migration para agregar `materia_id` FK, popular, y deprecar `comision_id`.
- **api-gateway**: Verificar ROUTE_MAP para content-service (ya debería estar; confirmar paths de upload).
