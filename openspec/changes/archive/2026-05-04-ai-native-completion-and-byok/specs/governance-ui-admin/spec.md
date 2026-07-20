## ADDED Requirements

### Requirement: Página `web-admin` solo lectura de eventos de gobernanza

El `web-admin` SHALL exponer una página `/governance-events` accesible solo para `superadmin` y `docente_admin`. La página SHALL listar eventos `intento_adverso_detectado` agregados por cohorte con filtros: facultad (dropdown), materia (dropdown dependiente), período (selector), severidad (1-5 multi-select), categoría (multi-select). La página SHALL ser solo lectura — sin mutaciones, sin workflow "marcar revisado" (deferido a piloto-2).

#### Scenario: Admin filtra por facultad

- **WHEN** un superadmin selecciona "Ingeniería" en el filtro facultad
- **THEN** la página SHALL pegar al endpoint con `facultad_id` y mostrar solo cohortes de materias bajo esa facultad

#### Scenario: Estudiante intenta acceder a la página

- **WHEN** un estudiante autenticado pega `/governance-events` directo
- **THEN** la página SHALL redirigir o mostrar `403 Forbidden`

### Requirement: Reusa endpoint analytics existente sin cambio de contrato

La página SHALL consumir el endpoint existente `GET /api/v1/analytics/cohort/{id}/adversarial-events` para cada cohorte que matchea los filtros. El endpoint SHALL extenderse con query params opcionales `?facultad_id={uuid}&materia_id={uuid}&periodo_id={uuid}` sin breaking change (todos opcionales). Cuando `facultad_id` está presente sin `cohort_id` específico, SHALL agregarse a través de todas las comisiones de materias bajo la facultad.

#### Scenario: Endpoint con filtros agregados

- **WHEN** la UI pega `GET /api/v1/analytics/adversarial-events?facultad_id=X&periodo_id=Y`
- **THEN** el endpoint SHALL retornar agregación cross-cohort filtrada por facultad+período
- **AND** la response SHALL incluir un breakdown por cohorte además del total agregado

### Requirement: Pagination y export CSV

La página SHALL paginar eventos con `cursor_next` (mismo patrón que `ProgressionView`). Los eventos pueden ser miles a nivel facultad. La página SHALL ofrecer botón "Exportar CSV" que descarga el conjunto filtrado actual en CSV con headers en español (sin tildes, encoding cp1252-safe).

#### Scenario: Exportar CSV desde filtros activos

- **WHEN** el admin tiene filtros aplicados (facultad=Ingeniería, severidad=4-5) y presiona "Exportar CSV"
- **THEN** el sistema SHALL generar un CSV con solo los eventos que matchean
- **AND** el filename SHALL contener el timestamp ISO y los filtros principales (ej: `governance-events-2026-05-04T1430-ingenieria-sev45.csv`)

### Requirement: HelpButton + PageContainer obligatorio

La página SHALL implementar el patrón obligatorio del repo (`HelpButton` + `PageContainer` + entry en `helpContent.tsx`) — ver `.claude/skills/help-system-content/SKILL.md`. El contenido del HelpButton SHALL explicar qué son intentos adversos, qué significa cada categoría, y referenciar ADR-019 + RN-129.

#### Scenario: Help button está presente

- **WHEN** se renderiza la página
- **THEN** el `HelpButton` SHALL estar visible en el header del `PageContainer`
- **AND** click SHALL abrir el modal con el contenido de `helpContent.governanceEvents`
