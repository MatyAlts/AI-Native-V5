## Context

El web-admin tiene 12 paginas CRUD funcionales con selectores cascade, paginacion cursor-based y breadcrumbs. Usa React 19 + TanStack Query + Tailwind 4 con un router basado en useState (no TanStack Router). El backend BYOK (5 endpoints en ai-gateway) ya esta completo y en ROUTE_MAP. Falta UI para BYOK, asignacion individual de docentes/alumnos, y polish general.

Estado actual:
- **BYOK**: endpoints en `/api/v1/byok/keys` (create, list, rotate, revoke, usage) ya ruteados por api-gateway. Casbin `byok_key:CRUD` para superadmin/docente_admin.
- **Asignacion**: `UsuarioComision` y `Inscripcion` solo se crean via bulk CSV. No hay endpoints individuales POST/DELETE.
- **ComisionesPage**: selectores cascade funcionales (Universidad > Carrera > Plan > Materia > Periodo). Solo muestra tabla de comisiones, sin detalle de docentes/alumnos.
- **Router**: basado en useState, sin sub-rutas. Cada pagina es un componente top-level.

## Goals / Non-Goals

**Goals:**
- Pagina BYOK con tabla, filtros y acciones (crear, rotar, revocar) con modales de confirmacion
- Endpoints individuales POST/DELETE para `usuarios_comision` e `inscripciones` en academic-service
- Vista de detalle de comision con tabs (docentes, alumnos) y formularios inline de alta/baja
- Polish minimo: estados vacios consistentes en todas las paginas CRUD

**Non-Goals:**
- Migrar el router a TanStack Router (cambio ortogonal, mucho scope)
- Paginacion server-side donde no la hay (las listas son chicas en piloto)
- UI de BYOK usage con graficos/charts (solo tabla de uso)
- Edicion inline de keys BYOK (rotar = nuevo plaintext, no editar metadata)

## Decisions

### D1: BYOK como pagina nueva vs seccion en comision

**Decision**: pagina nueva `ByokPage` en el grupo "Operacional" del sidebar.

**Razon**: BYOK tiene scope tenant y materia, no solo comision. Meterlo como sub-seccion de comisiones esconde las keys de scope tenant. Pagina propia con filtro por scope_type + scope_id.

**Alternativa descartada**: tab en ComisionesPage. No cubre keys scope=tenant.

### D2: Detalle de comision como modal vs pagina

**Decision**: expandir ComisionesPage con un panel de detalle inline (click en fila -> se abre debajo de la tabla). Tres tabs: Info, Docentes, Alumnos.

**Razon**: el router actual es useState-based, no soporta sub-rutas. Un panel inline es coherente con el patron existente (ej. ComisionForm se muestra/oculta con showForm). Evita crear infraestructura de routing nueva.

**Alternativa descartada**: pagina separada con ruta. Requiere migrar a TanStack Router o hackear el estado global.

### D3: Endpoints individuales — donde ponerlos

**Decision**: agregar 4 endpoints en academic-service bajo los routers existentes:
- `POST /api/v1/comisiones/{id}/docentes` (crea UsuarioComision)
- `DELETE /api/v1/comisiones/{id}/docentes/{usuario_comision_id}`
- `POST /api/v1/comisiones/{id}/inscripciones` (crea Inscripcion)
- `DELETE /api/v1/comisiones/{id}/inscripciones/{inscripcion_id}`

Mas: endpoints GET para listar los existentes:
- `GET /api/v1/comisiones/{id}/docentes`
- `GET /api/v1/comisiones/{id}/inscripciones`

**Razon**: son sub-recursos de comision, quedan bajo el prefix `/api/v1/comisiones` que ya esta en ROUTE_MAP. No necesita nueva entrada en api-gateway.

### D4: Modales BYOK

**Decision**: 3 modales con el `Modal` de `@platform/ui`:
- **Crear key**: form con scope_type (select), scope_id (input UUID, opcional segun scope), provider (select), plaintext_value (password input), monthly_budget_usd (number, opcional).
- **Rotar key**: form con solo el nuevo plaintext_value. Confirma con el fingerprint_last4 visible.
- **Revocar key**: confirmacion destructiva con el fingerprint visible.

### D5: api.ts — nuevas funciones

Agregar a `apps/web-admin/src/lib/api.ts`:
- `byokApi` (list, create, rotate, revoke, usage)
- `comisionDocentesApi` (list, create, delete)
- `comisionInscripcionesApi` (list, create, delete)

Patron identico al existente (funciones que llaman `request<T>`).

## Risks / Trade-offs

- **[BYOK sin ROUTE_MAP test]** → ya esta en ROUTE_MAP, verificado. Si el ai-gateway no esta levantado, la pagina muestra error HTTP — aceptable en dev.
- **[Detalle inline puede crecer mucho]** → mitiga: solo 3 tabs simples. Si en futuro se necesita mas, migrar a TanStack Router.
- **[DELETE de inscripcion no es lo mismo que baja academica]** → DELETE hace soft-delete. Para baja con nota (desaprobado/abandono), usar el flujo existente de bulk update. La UI muestra solo "quitar de comision".
- **[UsuarioComision.user_id no se valida contra Keycloak]** → en piloto, los user_id son UUIDs del seed. El form acepta UUID freeform. Validacion contra Keycloak es scope de F9.
