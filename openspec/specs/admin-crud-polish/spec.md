## ADDED Requirements

### Requirement: Estados vacios consistentes en todas las paginas CRUD
Todas las paginas CRUD del web-admin SHALL mostrar un mensaje informativo cuando la tabla este vacia, orientando al admin sobre que hacer.

#### Scenario: Tabla vacia sin filtros
- **WHEN** una pagina CRUD no tiene datos y no hay filtros aplicados
- **THEN** se muestra un estado vacio con texto descriptivo y un boton de accion principal (ej. "Crear primera facultad")

#### Scenario: Tabla vacia con filtros
- **WHEN** una pagina CRUD no tiene datos porque los filtros no matchean
- **THEN** se muestra un estado vacio indicando que no hay resultados para los filtros seleccionados

### Requirement: BYOK en nav del sidebar
El sidebar SHALL incluir "BYOK Keys" en el grupo "Operacional" con icono Key.

#### Scenario: Navegacion a BYOK
- **WHEN** el admin hace click en "BYOK Keys" en el sidebar
- **THEN** se renderiza la ByokPage
