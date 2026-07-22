## MODIFIED Requirements

### Requirement: MaterialesView uploads scoped to materia
La vista de materiales del web-teacher SHALL subir materiales con `materia_id` derivado de la comision seleccionada, en vez de `comision_id`.

#### Scenario: Upload resolves materia_id from comision
- **WHEN** el docente sube un archivo desde MaterialesView
- **THEN** el upload envia `materia_id` de la comision actual al backend

### Requirement: MaterialesView lists by materia
La vista de materiales SHALL listar materiales filtrados por `materia_id` de la comision seleccionada.

#### Scenario: List shows materials for the materia
- **WHEN** el docente navega a /materiales con una comision seleccionada
- **THEN** se muestran todos los materiales de la materia de esa comision (incluyendo los subidos desde otras comisiones de la misma materia)

### Requirement: API client uses materia_id
Las funciones `listMateriales` y `uploadMaterial` en `api.ts` SHALL usar `materia_id` como parametro principal.

#### Scenario: listMateriales sends materia_id
- **WHEN** se invoca `listMateriales({ materia_id: "X" })`
- **THEN** el request incluye `materia_id=X` como query param

#### Scenario: uploadMaterial sends materia_id
- **WHEN** se invoca `uploadMaterial(materiaId, file)`
- **THEN** el FormData incluye `materia_id` como field

### Requirement: Material type includes materia_id
La interface `Material` en api.ts SHALL incluir `materia_id: string`.

#### Scenario: Material response has materia_id
- **WHEN** se recibe un Material del backend
- **THEN** el objeto incluye `materia_id` como string UUID
