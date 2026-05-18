## ADDED Requirements

### Requirement: Endpoint individual para asignar docente a comision
El academic-service SHALL exponer `POST /api/v1/comisiones/{id}/docentes` para crear un UsuarioComision con user_id, rol y fecha_desde.

#### Scenario: Asignar docente exitosamente
- **WHEN** se envia POST con user_id, rol (titular|adjunto|jtp|ayudante|corrector) y fecha_desde
- **THEN** se crea el UsuarioComision y se retorna 201 con los datos

#### Scenario: Duplicado por constraint unique
- **WHEN** ya existe un UsuarioComision con el mismo (tenant_id, comision_id, user_id, rol)
- **THEN** se retorna 409 Conflict

### Requirement: Endpoint individual para quitar docente de comision
El academic-service SHALL exponer `DELETE /api/v1/comisiones/{id}/docentes/{uc_id}` para soft-delete de UsuarioComision.

#### Scenario: Quitar docente exitosamente
- **WHEN** se envia DELETE con un uc_id valido
- **THEN** se soft-deleta y se retorna 204

### Requirement: Endpoint para listar docentes de una comision
El academic-service SHALL exponer `GET /api/v1/comisiones/{id}/docentes` con paginacion cursor.

#### Scenario: Listar docentes asignados
- **WHEN** se envia GET a la comision
- **THEN** se retorna la lista de UsuarioComision con user_id, rol, fecha_desde, fecha_hasta

### Requirement: Endpoint individual para inscribir alumno a comision
El academic-service SHALL exponer `POST /api/v1/comisiones/{id}/inscripciones` para crear Inscripcion con student_pseudonym y fecha_inscripcion.

#### Scenario: Inscribir alumno exitosamente
- **WHEN** se envia POST con student_pseudonym (UUID) y fecha_inscripcion
- **THEN** se crea la Inscripcion con rol=regular, estado=activa y se retorna 201

#### Scenario: Duplicado por constraint unique
- **WHEN** ya existe inscripcion con el mismo (tenant_id, comision_id, student_pseudonym)
- **THEN** se retorna 409 Conflict

### Requirement: Endpoint individual para quitar alumno de comision
El academic-service SHALL exponer `DELETE /api/v1/comisiones/{id}/inscripciones/{insc_id}` para soft-delete.

#### Scenario: Quitar alumno exitosamente
- **WHEN** se envia DELETE con un insc_id valido
- **THEN** se soft-deleta y se retorna 204

### Requirement: Endpoint para listar alumnos de una comision
El academic-service SHALL exponer `GET /api/v1/comisiones/{id}/inscripciones` con paginacion cursor.

#### Scenario: Listar alumnos inscritos
- **WHEN** se envia GET a la comision
- **THEN** se retorna la lista de Inscripcion con student_pseudonym, rol, estado, fecha_inscripcion
