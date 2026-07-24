## Context

El content-service scopea materiales y chunks por `comision_id`. Un docente que dicta 3 comisiones de la misma materia tiene que subir el mismo PDF 3 veces. Pedagogicamente, el material de referencia pertenece a la **materia**, no a una comision particular.

Estado actual:
- `Material.comision_id` y `Chunk.comision_id` son NOT NULL en `content_db`.
- El retrieval filtra por `comision_id` en la query SQL (`WHERE c.comision_id = :comision_id`).
- El tutor-service `ContentClient.retrieve()` y el academic-service `ContentClient.retrieve()` pasan `comision_id`.
- El frontend web-teacher ya tiene `MaterialesView` con upload/list/delete, pero scoped a comision.
- La comision ya tiene `materia_id` como campo (visible en `api.ts: Comision.materia_id`).

## Goals / Non-Goals

**Goals:**
- Agregar `materia_id` a `Material` y `Chunk`, poblar desde la comision asociada via migration.
- Actualizar endpoints de content-service (upload, list, retrieve) para usar `materia_id`.
- Actualizar `ContentClient` en tutor-service y academic-service para pasar `materia_id`.
- Actualizar `MaterialesView` y `api.ts` en web-teacher para pasar `materia_id`.
- Mantener `comision_id` como nullable (transitorio) para backwards-compat.

**Non-Goals:**
- Drop de `comision_id` (migration futura separada).
- Vista de materiales en web-admin (deferida).
- Upload resumable para archivos >50MB.
- Cambio de storage_path pattern (sigue usando comision_id en el path para no reescribir objetos existentes).

## Decisions

### D1: Agregar `materia_id` como columna NOT NULL, `comision_id` pasa a nullable

La migration agrega `materia_id UUID NOT NULL` a `materiales` y `chunks`. No hay FK fisica porque la tabla `materias` vive en `academic_main` (ADR-003 — bases separadas). Se agrega un indice compuesto `(tenant_id, materia_id)` para el retrieval.

`comision_id` pasa a `nullable=True` para backwards-compat. Los registros existentes conservan su `comision_id` original. El drop definitivo queda como migration futura.

**Alternativa descartada**: crear tabla intermedia `material_materia`. Sobre-ingenieria para el piloto — la relacion es 1:1 (un material pertenece a exactamente una materia).

### D2: Lookup `comision -> materia_id` en el frontend

El frontend ya tiene `Comision.materia_id` en el response de `listMyComisiones()`. Cuando el docente selecciona una comision en el sidebar, el `materia_id` esta disponible sin llamada extra. El upload y list de materiales pasan `materia_id` directamente.

### D3: Retrieval filtra por `materia_id` en vez de `comision_id`

La query SQL del `RetrievalService` cambia `WHERE c.comision_id = :comision_id` a `WHERE c.materia_id = :materia_id`. El docstring de aislamiento pedagogico se mantiene — el aislamiento ahora es por materia (mas amplio pero correcto: todas las comisiones de la misma materia comparten el corpus).

El `RetrievalRequest` schema cambia `comision_id` a `materia_id`. Backward-compat: se acepta `comision_id` como alias deprecated (resuelve materia_id en capa de servicio via lookup si no esta presente `materia_id`).

### D4: ContentClients actualizados

- `tutor-service/ContentClient.retrieve()`: pasa `materia_id` (ya disponible en `SessionState.materia_id` via ADR-040).
- `academic-service/ContentClient.retrieve()`: cambia `comision_id` a `materia_id` (ya tiene `materia_id` del request de TP-gen).

### D5: web-teacher MaterialesView pasa `materia_id`

La ruta `/materiales` recibe `comisionId` del search param. El view resuelve `materia_id` de la comision seleccionada (disponible en el context global de comisiones). Upload y list usan `materia_id`. El cambio es transparente al docente.

## Risks / Trade-offs

- **[Risk] Materiales existentes sin `materia_id`** -> Mitigacion: la migration los deja con `materia_id` null hasta que se populen manualmente o via script. Los endpoints nuevos rechazan requests sin `materia_id`. Para el piloto con data limpia del seed, no hay materiales preexistentes.
- **[Risk] Retrieval mas amplio (materia vs comision)** -> Trade-off aceptable: el material de referencia es de la materia, no de la comision. Todas las comisiones de la misma materia deberian compartir el corpus RAG. Esto es una mejora, no un riesgo.
- **[Risk] `storage_path` sigue usando comision_id** -> No se migran objetos existentes. Nuevos uploads pueden usar materia_id en el path, pero para simplificar se mantiene el patron actual. Sin impacto funcional.
