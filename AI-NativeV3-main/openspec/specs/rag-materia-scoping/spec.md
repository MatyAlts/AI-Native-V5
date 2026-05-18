## ADDED Requirements

### Requirement: Material model includes materia_id
El modelo `Material` SHALL incluir un campo `materia_id: UUID` NOT NULL con indice. El campo `comision_id` pasa a nullable.

#### Scenario: New material has materia_id
- **WHEN** se crea un Material con `materia_id` valido
- **THEN** el registro se persiste con `materia_id` NOT NULL

### Requirement: Chunk model includes materia_id
El modelo `Chunk` SHALL incluir un campo `materia_id: UUID` NOT NULL denormalizado. El campo `comision_id` pasa a nullable.

#### Scenario: Chunk inherits materia_id from material
- **WHEN** la ingestion pipeline crea chunks para un material
- **THEN** cada chunk tiene `materia_id` igual al del material padre

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
