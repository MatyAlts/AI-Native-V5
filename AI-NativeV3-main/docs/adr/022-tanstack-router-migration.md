# ADR-022 — Migración del web-teacher a TanStack Router (file-based) + alertas predictivas

- **Estado**: Propuesto
- **Fecha**: 2026-04-27
- **Deciders**: Alberto Alejandro Cortez, director de tesis
- **Tags**: frontend, routing, dashboard, tesis, piloto-UNSL

## Contexto y problema

Hasta este ADR, el `web-teacher` usa **state-based switching** (`useState<View>` con union type + condicionales en render). Eso funcionó para 6-9 vistas pero introduce 3 limitaciones reales tras cerrar G7 MVP:

1. **Drill-down navegacional imposible**: el patrón natural de uso del docente sería *"viendo Progresión, click en un estudiante → abre StudentLongitudinalView pre-poblada con su student_pseudonym + comision_id"*. Hoy el docente debe **pegar UUIDs manualmente** en `EpisodeNLevelView` y `StudentLongitudinalView` — UX feo y propenso a errores.
2. **No hay shareable URLs**: si el docente encuentra un patrón interesante en un estudiante, no puede mandarle el link al director de tesis. La vista no tiene URL.
3. **Sin browser back/forward**: state-based switching no se integra con el historial del navegador. F5 reinicia todo.

Adicionalmente, el audit G7 pide **alertas predictivas**: *"si algún indicador cae >1σ respecto del propio trayecto del estudiante, sugerir intervención"*. Aunque eso NO requiere routing, el flujo natural ES navegacional (vista de cohorte → ver lista de alertas → click → abre estudiante específico). Sin routing real, tampoco es UX limpio.

Fuerzas en juego:

1. **Refactor sustancial**: migrar todas las vistas existentes (no solo las 3 de G7 MVP) a un router. ~1-2 días de trabajo.
2. **TanStack Router está en el stack documentado** del repo (CLAUDE.md menciona "React 19 + Vite 6 + TanStack Router/Query"). El web-admin probablemente ya lo use; el web-teacher quedó atrasado.
3. **Type-safety de routing**: TanStack Router tiene path types generados automáticamente (similar a Next.js app router). Eso elimina toda la categoría de bugs "broken link interno" que biome no detecta.
4. **Compatibilidad con state actual**: el `selectedComisionId` global del sidebar no debe perderse — debe pasar a ser query param `?comisionId=X` en las URLs relevantes.

## Drivers de la decisión

- **D1** — Habilitar drill-down navegacional desde Progresión hacia las 3 vistas G7 MVP. Sin esto, el dashboard MVP es defendible pero feo.
- **D2** — Shareable URLs para que el docente pueda referenciar un análisis específico (a su director, a un colega).
- **D3** — Browser back/forward + persistence del estado en URL (no solo localStorage).
- **D4** — Type-safe routes: si se renombra una vista o cambia un path param, biome/tsc debe romper la compilación.
- **D5** — Refactor incremental — no romper ninguna funcionalidad existente. Después del refactor, el comportamiento del docente es idéntico salvo que **además** puede compartir URLs.

## Opciones consideradas

### Opción A — File-based routing de TanStack Router (elegida)

Estructura `apps/web-teacher/src/routes/` con un archivo por ruta (similar a Next.js):
- `__root.tsx` — layout con Sidebar.
- `index.tsx` — root, redirect a la primera vista.
- `templates.tsx`, `tareas-practicas.tsx`, etc.
- `student/$studentId/longitudinal.tsx` — drill-down de estudiante con path param.
- `episode/$episodeId/n-level.tsx` — drill-down de episodio con path param.
- `cohort/$comisionId/adversarial.tsx` — drill-down de cohorte.

TanStack generates `routeTree.gen.ts` automáticamente y los `Link to=` quedan type-safe.

Ventajas:
- Type-safety completo en navegación.
- File system mirrors URL structure — bajo overhead cognitivo.
- Drill-down con `<Link to="/student/$studentId/longitudinal" params={{ studentId: "..." }} search={{ comisionId: "..." }}>` es trivial.
- Browser history funciona nativamente.

Desventajas:
- Refactor de TODAS las vistas — ~1-2 días.
- Dependencia nueva al stack (mitigado: ya está en el stack documentado).

### Opción B — Code-based routing programático (descartada)

`createRouter` + `createRoute` definidos en código TS, no archivos.

Ventajas:
- Más cerca del state-based actual.
- Menos cambio inmediato.

Desventajas:
- Pierde la generación automática de tipos.
- No escala — con 9+ rutas se vuelve un walltext.

### Opción C — React Router v6 (descartada)

Stack alternativo conocido.

Ventajas:
- Más popular, más StackOverflow.

Desventajas:
- NO es lo que CLAUDE.md documenta para el repo. Romper esa decisión arquitectónica requeriría justificación que NO existe.
- Type-safety menos pulido que TanStack Router.

### Opción D — Mantener state-based + agregar `useSearchParams` manual (descartada)

Hack: leer/escribir `window.location.search` desde useState para "fakear" URLs.

Ventajas:
- Cero refactor.

Desventajas:
- No type-safe. Cada `<a>` interno es un foot-gun.
- Browser history se rompe de formas raras.
- Es exactamente la deuda que el ADR busca cerrar.

## Decisión

**Opción A — TanStack Router con file-based routing.**

### Estructura de rutas resultante

```
src/routes/
├── __root.tsx                                    # Layout con <Sidebar> + <Outlet />
├── index.tsx                                     # Redirect a /tareas-practicas (default)
├── templates.tsx                                 # /templates
├── tareas-practicas.tsx                          # /tareas-practicas?comisionId=X
├── materiales.tsx                                # /materiales?comisionId=X
├── progression.tsx                               # /progression?comisionId=X
├── kappa.tsx                                     # /kappa
├── export.tsx                                    # /export?comisionId=X
├── student.$studentId.longitudinal.tsx           # /student/$studentId/longitudinal?comisionId=X
├── episode.$episodeId.n-level.tsx                # /episode/$episodeId/n-level
└── cohort.$comisionId.adversarial.tsx            # /cohort/$comisionId/adversarial
```

### Convenciones

- **`comisionId` siempre en query param** (no path) — hereda del selector global del sidebar; mantenerlo en query permite cambiarlo sin re-mount de la vista.
- **`studentId`, `episodeId` en path param** — son IDs del recurso primario de la vista; cambiarlos cambia el recurso completamente.
- **Default redirect**: `/` → `/tareas-practicas` (la primera vista del NAV_GROUPS actual).
- **404 catch-all**: `__root` define un `notFoundComponent` que muestra "Vista no encontrada".

### Drill-down: cómo se ve el flujo

ANTES (estado state-based con UUID input manual):
```
Progresión → docente busca "stud-X-pseudonym" → copia UUID → ve EpisodeNLevelView
   → pega UUID en input → click "Analizar"
```

DESPUÉS (con drill-down navegacional):
```
/progression?comisionId=COM_A → click en fila del estudiante → navega a
/student/UUID/longitudinal?comisionId=COM_A
```

`Link` type-safe:
```tsx
<Link
  to="/student/$studentId/longitudinal"
  params={{ studentId: trajectory.student_alias }}
  search={{ comisionId: comisionId }}
>
  Ver evolución longitudinal
</Link>
```

### Alertas predictivas (audit G7) — independientes del routing

ESTAS NO REQUIEREN ROUTING — son **estadística clásica** sobre los slopes longitudinales (NO ML predictivo). El audit G7 dice literalmente *"si algún indicador cae >1σ respecto del propio trayecto"*. Implementación:

- Función pura `compute_student_alerts(slope, cohort_stats)` en `packages/platform-ops/cii_alerts.py`.
- Tres reglas:
  1. **`regresion_vs_cohorte`**: `slope_estudiante < mean_cohorte - 1σ` → severity `medium`. Si `< -2σ` → `high`.
  2. **`bottom_quartile`**: estudiante en Q1 → severity `low` (informativa, no toda Q1 requiere intervención).
  3. **`slope_negativo_significativo`**: `slope < -0.3` → severity `medium`, independiente de cohorte.
- **Privacidad**: `compute_cohort_slopes_stats` exige `MIN_STUDENTS_FOR_QUARTILES = 5` para reportar cuartiles. Con cohortes <5, devuelve `insufficient_data: true` (cohortes muy chicas son des-anonimizables vía cuartiles — viola RN-094 si se publican).

3 endpoints nuevos:
- `GET /api/v1/analytics/student/{id}/episodes?comision_id=X` — listado para drill-down dropdown (reemplaza pegar UUIDs).
- `GET /api/v1/analytics/cohort/{id}/cii-quartiles` — cuartiles agregados privacidad-safe.
- `GET /api/v1/analytics/student/{id}/alerts?comision_id=X` — alertas + posición en cuartiles del estudiante.

**NO ML predictivo** (forecasting / regresión sobre series temporales). Eso es agenda piloto-2 separada — requiere modelos entrenados, validación cruzada, calibración. Fuera del scope.

## Consecuencias

### Positivas

- **Drill-down trivial**: link de Progresión → vistas individuales pre-pobladas. UX mejorada significativamente.
- **Shareable URLs**: el docente puede mandar `https://piloto/student/UUID/longitudinal?comisionId=X` por email.
- **Browser history**: F5 mantiene la vista; back/forward funciona; bookmarks posibles.
- **Type-safety**: `<Link to>` y `useParams()` son full-typed; no hay broken links.
- **Alertas accionables**: el docente ve a qué estudiantes contactar (severity high/medium) — Sección 17.8 de la tesis se vuelve concreta.
- **Cuartiles privacidad-safe**: el docente ve la posición del estudiante en cohorte (Q1/Q2/Q3/Q4) sin ver slopes individuales de los demás. RN-094 preservada.

### Negativas / trade-offs

- **Refactor de las 9 vistas existentes** — ~1-2 días de trabajo. Mitigado: el cambio es mecánico (state-based → componente de ruta), bajo riesgo de regresión.
- **Tests E2E rotan**: cualquier test que asumía state-based switching debe migrarse. Hoy no hay tests E2E, así que no aplica — pero futuros tests deben usar `createMemoryHistory()` de TanStack Router.
- **Cuartiles requieren toda la cohorte clasificada**: el endpoint `/cohort/{id}/cii-quartiles` itera por cada estudiante de la comisión y computa su `mean_slope`. Para cohortes >100 estudiantes, esto es ~Nx queries cross-DB (lento). **Mitigación**: cache en analytics-service, refresco nightly. Aceptable para piloto inicial (<50 estudiantes/comisión).
- **N+1 query pattern**: el endpoint `/student/{id}/alerts` también itera por la cohorte completa. Mismo problema, misma mitigación.

### Neutras

- **NO requiere migration Alembic** (ningún schema cambia).
- **NO requiere cambios al backend** salvo los 3 endpoints nuevos.
- **NO afecta web-admin ni web-student** (cada frontend tiene su routing propio).
- **Casbin**: los endpoints nuevos usan el mismo patrón de auth (`X-Tenant-Id` + `X-User-Id`) que los demás analytics endpoints.

## API BC-breaks

Ninguno backend. Frontend: las URLs cambian (de "ninguna" a paths reales) pero como nadie tenía URLs guardadas, no rompe nada externo.

## Tasks de implementación

1. **`packages/platform-ops/cii_alerts.py`** (nuevo) + tests con golden cases (cohortes con N<5, N=5, regresión 1σ, regresión 2σ, etc.).
2. **3 endpoints nuevos** en `analytics-service` con tests unit (modo dev devuelve estructura vacía coherente).
3. **Método nuevo `list_episodes_with_classifications_for_student`** en `RealLongitudinalDataSource` para el dropdown de drill-down.
4. **Instalar `@tanstack/react-router` + `@tanstack/router-vite-plugin`** en web-teacher.
5. **Configurar Vite plugin** para generar `routeTree.gen.ts` automáticamente.
6. **Migrar `App.tsx`** → `__root.tsx` con `<RouterProvider>` + Sidebar + `<Outlet>`.
7. **Crear archivos de ruta** para las 9 vistas existentes (sin lógica nueva, solo wrapper).
8. **Crear archivos de ruta nuevos** para los 3 drill-downs (`student.$studentId.longitudinal`, `episode.$episodeId.n-level`, `cohort.$comisionId.adversarial`).
9. **Actualizar `ProgressionView`** para que cada estudiante tenga `<Link>` al drill-down longitudinal.
10. **Reemplazar inputs de UUID** en EpisodeNLevelView y StudentLongitudinalView por dropdowns que consumen `/student/{id}/episodes`.
11. **Mostrar alertas + cuartil** en StudentLongitudinalView (consume `/student/{id}/alerts`).
12. **Tests E2E con vitest + Testing Library** de las 3 vistas G7 MVP.

## Referencias

- ADR-018 (CII evolution longitudinal) — base del cálculo de alertas.
- ADR-016 (TareaPracticaTemplate) — definición de "problemas análogos" usada por las alertas.
- Tesis Sección 17.8 — análisis empírico que requiere las alertas accionables.
- Audit G7 — documenta el dashboard docente como agenda confirmatoria.
- TanStack Router docs — file-based routing.
- RN-094 (privacy) — base para `MIN_STUDENTS_FOR_QUARTILES = 5`.
