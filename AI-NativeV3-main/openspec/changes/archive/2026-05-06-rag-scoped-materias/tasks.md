## 1. Content-service model + migration

- [x] 1.1 Agregar `materia_id` al modelo `Material` en `models/material.py` (UUID, NOT NULL, indexed). Hacer `comision_id` nullable.
- [x] 1.2 Agregar `materia_id` al modelo `Chunk` en `models/material.py` (UUID, NOT NULL, indexed). Hacer `comision_id` nullable.
- [x] 1.3 Crear Alembic migration que agrega `materia_id` a `materiales` y `chunks`, con indices.

## 2. Content-service schemas

- [x] 2.1 Agregar `materia_id` a `MaterialOut` y `ChunkOut` en `schemas/__init__.py`.
- [x] 2.2 Cambiar `RetrievalRequest` para aceptar `materia_id` (principal) y `comision_id` (opcional deprecated).

## 3. Content-service routes + services

- [x] 3.1 Actualizar `routes/materiales.py`: upload acepta `materia_id` como Form field, list filtra por `materia_id`.
- [x] 3.2 Actualizar `services/ingestion.py`: propagar `materia_id` del material a los chunks.
- [x] 3.3 Actualizar `services/retrieval.py`: filtrar por `materia_id` en la query SQL.
- [x] 3.4 Actualizar `routes/retrieve.py` docstring para reflejar filtro por materia.

## 4. Tutor-service content client

- [x] 4.1 Actualizar tutor-service content clients (`services/clients.py` + `services/content_client.py`) y caller en `tutor_core.py`: pasar `materia_id` preferido, `comision_id` como fallback.

## 5. Academic-service content client

- [x] 5.1 Actualizar `academic-service/services/ai_clients.py` `ContentClient.retrieve()`: cambiar `comision_id` a `materia_id`.
- [x] 5.2 Actualizar `routes/tareas_practicas.py` `_retrieve_rag_context()`: pasar `materia_id` directo en vez de `comision_id`.

## 6. Web-teacher API client

- [x] 6.1 Actualizar `Material` interface en `api.ts` para incluir `materia_id`.
- [x] 6.2 Actualizar `listMateriales` y `uploadMaterial` para usar `materia_id`.

## 7. Web-teacher MaterialesView

- [x] 7.1 Actualizar `MaterialesView.tsx`: resolver `materia_id` de la comision y usarlo en upload/list.
- [x] 7.2 No requiere cambios: la ruta pasa `comisionId` y el view resuelve `materia_id` internamente via `useMateriaId` hook.
