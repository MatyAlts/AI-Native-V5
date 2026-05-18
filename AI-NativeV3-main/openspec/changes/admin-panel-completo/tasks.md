## 1. Backend — Endpoints individuales (academic-service)

- [x] 1.1 Agregar schemas Pydantic: `UsuarioComisionCreate`, `UsuarioComisionOut`, `InscripcionCreate`, `InscripcionOut` en `academic_service/schemas.py`
- [x] 1.2 Agregar metodos al `ComisionService`: `list_docentes(comision_id)`, `add_docente(comision_id, data)`, `remove_docente(comision_id, uc_id)`
- [x] 1.3 Agregar metodos al `ComisionService` (o nuevo `InscripcionService`): `list_inscripciones(comision_id)`, `add_inscripcion(comision_id, data)`, `remove_inscripcion(comision_id, insc_id)`
- [x] 1.4 Agregar 6 endpoints al `comisiones_router` en `routes/comisiones.py`: GET/POST/DELETE para docentes e inscripciones bajo `/api/v1/comisiones/{id}/docentes` y `/api/v1/comisiones/{id}/inscripciones`
- [x] 1.5 Agregar Casbin policies para `usuario_comision:create/delete` y `inscripcion:create/delete` en `seeds/casbin_policies.py`
- [x] 1.6 Tests unitarios para los 6 endpoints nuevos en `apps/academic-service/tests/unit/`

## 2. Frontend — API client (web-admin)

- [x] 2.1 Agregar tipos TS e interfaces: `ByokKey`, `ByokKeyCreate`, `ByokKeyUsage`, `UsuarioComisionOut`, `InscripcionOut` en `lib/api.ts`
- [x] 2.2 Agregar `byokApi` a `lib/api.ts`: list, create, rotate, revoke, usage
- [x] 2.3 Agregar `comisionDocentesApi` a `lib/api.ts`: list, create, delete (bajo `/comisiones/{id}/docentes`)
- [x] 2.4 Agregar `comisionInscripcionesApi` a `lib/api.ts`: list, create, delete (bajo `/comisiones/{id}/inscripciones`)

## 3. Frontend — Pagina BYOK

- [x] 3.1 Crear `pages/ByokPage.tsx` con tabla de keys, filtro por scope_type y acciones por fila
- [x] 3.2 Agregar modal de crear key (form con scope_type, provider, plaintext, budget)
- [x] 3.3 Agregar modal de rotar key (form con nuevo plaintext, muestra fingerprint actual)
- [x] 3.4 Agregar modal de revocar key (confirmacion destructiva con fingerprint visible)
- [x] 3.5 Agregar panel inline de uso (click en fila -> muestra tokens/cost del mes actual)

## 4. Frontend — Detalle de comision con tabs

- [x] 4.1 Agregar componente `ComisionDetail` en ComisionesPage con estado expandido por comision_id
- [x] 4.2 Implementar tab "Docentes": tabla + formulario inline (user_id UUID, rol select, fecha_desde date)
- [x] 4.3 Implementar tab "Alumnos": tabla + formulario inline (student_pseudonym UUID, fecha_inscripcion date)
- [x] 4.4 Agregar confirmacion en acciones "Quitar" de docente y alumno (window.confirm, patron existente)

## 5. Frontend — Router y sidebar

- [x] 5.1 Agregar route "byok" al type `Route` y al switch de render en `Router.tsx`
- [x] 5.2 Agregar item "BYOK Keys" al sidebar en el grupo "Operacional" con icono `Key` de lucide-react
- [x] 5.3 Import de `ByokPage` en Router.tsx

## 6. Polish — Estados vacios

- [x] 6.1 Revisar y unificar estados vacios en FacultadesPage, MateriasPage, CarrerasPage, PlanesPage, PeriodosPage, UniversidadesPage (mensaje descriptivo + boton de accion)
- [x] 6.2 Agregar estado vacio en ByokPage
- [x] 6.3 Agregar helpContent para BYOK en `utils/helpContent.tsx`
