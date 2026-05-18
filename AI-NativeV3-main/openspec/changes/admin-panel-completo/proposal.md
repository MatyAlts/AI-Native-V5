## Why

El web-admin tiene las páginas CRUD de la jerarquía institucional (Facultades, Materias, Comisiones, Periodos, Carreras, Planes) y bulk import para 8 entidades, pero le faltan piezas clave para que un administrador opere el piloto de punta a punta: no hay UI para BYOK (las keys se gestionan solo por API), no hay forma individual de asignar docentes a comisiones ni inscribir alumnos (solo CSV masivo), y las páginas CRUD existentes necesitan polish para producción (filtros, paginación, estados vacíos, confirmaciones de borrado).

Sin esto, el onboarding del piloto UNSL depende de curl + CSV para operaciones que deberían ser 3 clicks en un panel.

## What Changes

- **Página BYOK en web-admin**: listar keys, crear (scoped a materia o tenant), rotar, revocar. Consume los 5 endpoints existentes del ai-gateway (`POST/GET /keys`, `POST /keys/{id}/rotate`, `POST /keys/{id}/revoke`, `GET /keys/{id}/usage`). Muestra scope (materia vs tenant), provider, estado, y uso acumulado.
- **Asignación individual de docentes a comisión**: formulario inline en la vista de detalle de comisión para agregar/quitar docentes (endpoint `POST /api/v1/usuarios-comision` ya existe vía bulk, agregar endpoint individual).
- **Inscripción individual de alumnos a comisión**: mismo patrón — formulario inline para inscribir un alumno por `student_pseudonym` sin necesidad de CSV.
- **Polish de páginas CRUD existentes**: filtros por facultad/materia en cascada, paginación server-side donde falte, estados vacíos informativos, diálogos de confirmación en acciones destructivas, breadcrumbs de navegación jerárquica (Facultad > Materia > Comisión).
- **Navegación jerárquica completa**: desde Facultad se puede drill-down a sus Materias, de ahí a Comisiones, y dentro de cada comisión ver docentes asignados + alumnos inscritos + BYOK override si existe.

## Capabilities

### New Capabilities
- `byok-management-ui`: Página de gestión de BYOK keys en web-admin. CRUD completo contra endpoints existentes del ai-gateway. Tabla con filtro por scope/provider/estado, acciones de rotar/revocar con confirmación, vista de uso por key.
- `individual-assignment`: Endpoints individuales (no bulk) para asignar docente a comisión y para inscribir alumno a comisión. Formularios inline en la vista de detalle de comisión del web-admin.
- `admin-crud-polish`: Filtros cascade, paginación server-side, estados vacíos, confirmaciones destructivas, breadcrumbs jerárquicos para las páginas CRUD existentes del web-admin.

### Modified Capabilities
- `academic-comisiones`: Vista de detalle de comisión se extiende para mostrar docentes asignados, alumnos inscritos, y BYOK override de la materia.

## Impact

- **web-admin**: 1 página nueva (BYOK), extensión de ComisionesPage con sub-vistas de docentes/alumnos, polish general de 6+ páginas existentes.
- **academic-service**: 2 endpoints individuales nuevos (`POST /api/v1/usuarios-comision` individual, `POST /api/v1/inscripciones` individual). Los endpoints bulk y de listado ya existen.
- **ai-gateway**: Sin cambios — los 5 endpoints BYOK ya existen y están cubiertos por Casbin.
- **api-gateway**: Verificar que ROUTE_MAP incluya los prefijos del ai-gateway para BYOK (hoy BYOK no está en ROUTE_MAP — necesita entrada).
- **packages/ui**: Posibles componentes compartidos (ConfirmDialog, EmptyState, Breadcrumbs) si no existen.
