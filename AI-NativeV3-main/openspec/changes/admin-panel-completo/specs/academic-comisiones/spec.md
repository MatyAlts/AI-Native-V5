## MODIFIED Requirements

### Requirement: Vista de detalle de comision con tabs
La ComisionesPage SHALL permitir expandir una comision para ver su detalle con tabs: Docentes y Alumnos.

#### Scenario: Expandir detalle de comision
- **WHEN** el admin hace click en una fila de la tabla de comisiones
- **THEN** se abre un panel debajo de la tabla con tabs "Docentes" y "Alumnos"

#### Scenario: Tab Docentes
- **WHEN** el admin selecciona el tab "Docentes"
- **THEN** se muestra la lista de UsuarioComision de esa comision con formulario inline para agregar

#### Scenario: Agregar docente desde el detalle
- **WHEN** el admin completa user_id (UUID), rol y fecha_desde en el formulario inline y confirma
- **THEN** se crea el UsuarioComision via POST y la lista se refresca

#### Scenario: Quitar docente desde el detalle
- **WHEN** el admin hace click en "Quitar" en una fila de docente y confirma
- **THEN** se elimina via DELETE y la lista se refresca

#### Scenario: Tab Alumnos
- **WHEN** el admin selecciona el tab "Alumnos"
- **THEN** se muestra la lista de Inscripciones con formulario inline para inscribir

#### Scenario: Inscribir alumno desde el detalle
- **WHEN** el admin ingresa student_pseudonym (UUID) y fecha_inscripcion y confirma
- **THEN** se crea la Inscripcion via POST y la lista se refresca

#### Scenario: Quitar alumno desde el detalle
- **WHEN** el admin hace click en "Quitar" en una fila de alumno y confirma
- **THEN** se elimina via DELETE y la lista se refresca
