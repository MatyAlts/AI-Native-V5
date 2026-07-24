## ADDED Requirements

### Requirement: Material model includes materia_id
El modelo `Material` SHALL incluir un campo `materia_id: UUID` **nullable** con indice (`ix_materiales_materia_id` y el compuesto `ix_materiales_tenant_materia`). El campo `comision_id` pasa a nullable y queda deprecated.

La columna es nullable **solo para las filas anteriores a la migracion `20260606_0001`**: el camino de escritura SI exige el campo — `POST /api/v1/materiales` declara `materia_id: UUID = Form(...)`, o sea obligatorio. Todo material creado por la API tiene `materia_id`.

El `NOT NULL` a nivel columna esta **diferido a proposito** y el paso queda comentado en la migracion (`20260606_0001`, paso 3): poblar `materia_id` de las filas legacy exige resolver `comision -> materia` contra `academic_main`, y ADR-003 prohibe joins cross-base. Cerrarlo requiere un backfill via HTTP a academic-service, y eso es una change propia.

#### Scenario: New material has materia_id
- **WHEN** se sube un material via `POST /api/v1/materiales`
- **THEN** `materia_id` es obligatorio en el Form y el registro se persiste con ese valor

#### Scenario: Legacy material sin materia_id
- **WHEN** se lee un material creado antes de la migracion `20260606_0001`
- **THEN** `materia_id` puede venir `null` y el consumidor NO debe asumir que esta presente

### Requirement: Chunk model includes materia_id
El modelo `Chunk` SHALL incluir un campo `materia_id: UUID` **nullable** denormalizado, con indice (`ix_chunks_materia_id` y el compuesto `ix_chunks_tenant_materia`). El campo `comision_id` pasa a nullable y queda deprecated.

Aplica la misma razon que en `Material`: los chunks derivados de materiales legacy heredan el `materia_id` nulo de su padre.

#### Scenario: Chunk inherits materia_id from material
- **WHEN** la ingestion pipeline crea chunks para un material
- **THEN** cada chunk tiene `materia_id` igual al del material padre — incluido el caso `null` de un material legacy

### Requirement: Retrieval filters by materia_id
El `RetrievalService` SHALL filtrar chunks por `materia_id` en vez de `comision_id`.

#### Scenario: Retrieve with materia_id
- **WHEN** se invoca retrieve con `materia_id = X`
- **THEN** solo se devuelven chunks donde `materia_id = X`

### Requirement: RetrievalRequest accepts materia_id
El schema `RetrievalRequest` SHALL aceptar `materia_id` como campo principal. `comision_id` se mantiene como opcional deprecated.

#### Scenario: Request with materia_id only
- **WHEN** se envia `RetrievalRequest` con `materia_id` y sin `comision_id`
- **THEN** el retrieve filtra por `materia_id`

### Requirement: Upload endpoint accepts materia_id
El endpoint `POST /api/v1/materiales` SHALL aceptar `materia_id` como Form field.

#### Scenario: Upload with materia_id
- **WHEN** se sube un archivo con `materia_id = X`
- **THEN** el material se crea con `materia_id = X`

### Requirement: List endpoint filters by materia_id
El endpoint `GET /api/v1/materiales` SHALL aceptar `materia_id` como query param.

#### Scenario: List by materia_id
- **WHEN** se lista materiales con `materia_id = X`
- **THEN** solo se devuelven materiales donde `materia_id = X`

## MODIFIED Requirements

### Requirement: ContentClient in tutor-service passes materia_id
El `ContentClient.retrieve()` del tutor-service SHALL pasar `materia_id` en vez de `comision_id`.

#### Scenario: Tutor retrieval uses materia_id
- **WHEN** el tutor-service hace retrieve para un episodio
- **THEN** el request al content-service incluye `materia_id` del SessionState

### Requirement: ContentClient in academic-service passes materia_id
El `ContentClient.retrieve()` del academic-service SHALL pasar `materia_id` en vez de `comision_id`.

#### Scenario: TP-gen retrieval uses materia_id
- **WHEN** el endpoint TP-gen hace retrieve de contexto RAG
- **THEN** el request al content-service incluye `materia_id`
