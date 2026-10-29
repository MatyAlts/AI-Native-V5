## Context

Motivación en `proposal.md`. Requisitos en `specs/pedidos-de-ayuda/spec.md`. Estado verificado contra `origin/main` (`18bffe9`) el 2026-10-28:

| Hecho | Dónde |
|---|---|
| `evaluation-service` vive en la base `academic_main` (comparte con academic-service) y ya es el servicio donde **escribe el alumno** (entregas) | `apps/evaluation-service/src/evaluation_service/routes/entregas.py`, `CLAUDE.md` del repo ("Ownership cruzado entregas/calificaciones") |
| Las tablas propias de evaluation se migran con `apps/evaluation-service/alembic/` (tabla de versión `alembic_version_evaluation`). Head actual: `20260902_0001` | `alembic/env.py:91`, `alembic/versions/20260902_0001_correccion_motor_reproducibilidad.py:26` |
| Receta de tabla con RLS a copiar: `ENABLE` + `FORCE` + policy `tenant_id = current_setting('app.current_tenant', true)::uuid` | `alembic/versions/20260818_0003_correcciones_ia.py:143-149` |
| Sesión con tenant por request: `get_db` → `tenant_session(user.tenant_id)` | `auth/dependencies.py:87-89` |
| Scope de comisión del docente: `usuarios_comision` por SQL (`user_id`, `comision_id`, `deleted_at IS NULL`), roles de supervisión pasan, **404 y no 403** | `routes/entregas.py:1237-1265` (`_assert_comision_visible`), `_OVERSIGHT_ROLES` `:56` |
| Comisión de una TP: `_comision_de_la_tp` / `_assert_comision_de_la_tp` (422 si la TP no existe) | `routes/entregas.py:1043-1070` |
| Inscripción del alumno: tabla `inscripciones` (`comision_id`, `student_pseudonym`, `deleted_at`); el `user.id` del alumno es su `student_pseudonym` | `apps/academic-service/.../models/operacional.py:100-130`; `create_entrega` usa `student_id = user.id` |
| `require_permission` del servicio **no tiene Casbin**: roles directos; el alumno sólo puede `read` entrega/calificación y `create` entrega. Para Active-IA se hizo un gate propio | `auth/dependencies.py:92-152` (`require_correccion_ia`) |
| Audit log de la evaluación va por structlog, no CTR (`tp_calificada`) | `routes/entregas.py:603` |
| El gateway sólo expone prefijos del `ROUTE_MAP` | `apps/api-gateway/src/api_gateway/routes/proxy.py:86-97` |
| Pantalla de error "El ejercicio no terminó de abrirse" (404 del estado del episodio): el alumno se queda en la página con Reintentar / Volver; el `episodeId` está en la URL y el contexto del ejercicio (`tarea_id`, `entrega_id`, `ejercicio_orden`) en `sessionStorage` | `apps/web-student/src/pages/EpisodePage.tsx:87, :626-635, :930-955`; `routes/episodio.$id.tsx` (`readEjercicioContext`); `routes/materia.$id.tsx:47-57` |
| Header del episodio con `HelpButton` | `EpisodePage.tsx:1431-1432` |
| Header de la TP en la lista de ejercicios (recibe `tarea`, `comisionId`) | `apps/web-student/src/components/ExerciseListView.tsx:39-43, :392-410` |
| Menú del docente: `NAV_GROUPS`, grupo "Trabajo del docente"; un test verifica que toda ruta esté en el menú | `apps/web-teacher/src/routes/__root.tsx:79-131`; `navegacionAlcanzable.test.ts` |
| Rutas por comisión usan `?comisionId=` y redirigen a `/` sin él | `apps/web-teacher/src/routes/correcciones.tsx` |
| Nombre visible del alumno: `useStudentProfiles` + `studentShortLabel` | `apps/web-teacher/src/hooks/useStudentProfiles.ts`, `utils/docenteLabels.ts:238` |
| Timeline del episodio para el docente: `/episode-timeline?episodeId=` | `apps/web-teacher/src/routes/episode-timeline.tsx` |
| Tarjeta por comisión en "Mis comisiones" | `apps/web-teacher/src/components/ComisionDelDocenteCard.tsx`, `views/HomeView.tsx:231-240` |
| `make check-rls` **no corre en CI** (sólo lo pide el template de PR). El job "RLS isolation tests" del CI prueba **sólo `ctr_store`** (`packages/platform-ops/tests/test_rls_postgres.py`) | `.github/workflows/ci.yml:462-549`, `.github/pull_request_template.md:18` |

## Goals / Non-Goals

**Goals:**
- Que el reclamo llegue con TP, ejercicio, episodio, comisión y hora, sin que el alumno tenga que saber nada de eso.
- Que funcione **justo cuando la plataforma está rota** (CTR caído, episodio que no se abrió).
- Que sólo lo lean los docentes de esa comisión.
- Cero cambio en la tesis.

**Non-Goals:**
- Respuesta escrita del docente al alumno dentro de la plataforma (D7).
- Notificación push / mail / tiempo real (D8).
- Pistas o ayuda pedagógica automática (opción C, descartada por el dueño).
- Ruteo de los "error de la plataforma" a Neyén por un canal aparte (D9: van por el log).
- Incluir los pedidos en el export académico o en analytics.

## Decisions

### D1 — Dueño: `evaluation-service`

| Opción | Veredicto |
|---|---|
| **evaluation-service** | **Elegida.** Ya vive en `academic_main` (lee `inscripciones`, `usuarios_comision`, `tareas_practicas` por SQL sin cruzar bases), ya tiene el guard de comisión del docente y la receta de RLS, ya es donde escribe el alumno, y **no depende del CTR ni del tutor**: si los workers del CTR se caen (el caso del 23/10), el pedido igual se guarda. |
| academic-service | Es el CRUD institucional con Casbin; sumar escritura del alumno ahí implica policies nuevas en el seed (213 → 21x) y reiniciar el enforcer. Más superficie, mismo resultado. |
| tutor-service / ctr-service | Prohibido: zona de la tesis. Y además se caen juntos con el problema que se quiere reportar. |

### D2 — Tabla `pedidos_ayuda` (academic_main), migración `20261028_0001`

`down_revision = "20260902_0001"` (confirmar con `uv run alembic -c apps/evaluation-service/alembic.ini heads` al aplicar; si hay otro head, encadenar ahí).

| Columna | Tipo | Nota |
|---|---|---|
| `id` | UUID PK `gen_random_uuid()` | |
| `tenant_id` | UUID NOT NULL | RLS |
| `comision_id` | UUID NOT NULL | **derivada de la TP por el servidor**, nunca del body |
| `student_pseudonym` | UUID NOT NULL | `user.id` del alumno |
| `tarea_practica_id` | UUID NOT NULL | sin FK (mismo criterio que `entregas` no tiene FK a TP: la TP es de academic) |
| `entrega_id` | UUID NULL, FK `entregas.id` `ON DELETE SET NULL` | |
| `ejercicio_orden` | INT NULL | NULL = TP monolítica o pedido desde la lista sin ejercicio |
| `episode_id` | UUID NULL, **sin FK** | los episodios viven en `ctr_store` (otra base) y en el caso "Episode no encontrado" ni existen: se guarda tal cual, es justamente el dato para diagnosticar |
| `categoria` | VARCHAR(30) NOT NULL, CHECK en los 4 valores | |
| `mensaje` | TEXT NULL, CHECK `char_length <= 1000` | |
| `contexto` | JSONB NOT NULL default `'{}'` | sólo claves permitidas (D5) |
| `estado` | VARCHAR(20) NOT NULL default `pendiente`, CHECK `pendiente`/`resuelto` | |
| `resuelto_por` | UUID NULL | |
| `resuelto_at` | TIMESTAMPTZ NULL | CHECK: `(estado='resuelto') = (resuelto_at IS NOT NULL)` |
| `created_at` | TIMESTAMPTZ NOT NULL `now()` | la hora la pone el servidor |

Índices: `(tenant_id, comision_id, estado, created_at DESC)` para la lista del docente; `(tenant_id, student_pseudonym, created_at DESC)` para el anti-spam y "mis pedidos".

RLS: `ENABLE` + `FORCE` + policy `pedidos_ayuda_tenant_isolation` igual que `correcciones_ia`. El aislamiento **por comisión** va en la aplicación (`WHERE comision_id` + guard), igual que `entregas`: una policy sobre `app.current_user_id` no existe en este servicio y no se inventa acá. Downgrade: drop policy + drop table.

Como `make check-rls` no corre en CI, el change suma la verificación por dos lados: (a) tarea manual `make check-rls` contra la base local migrada, anotada en `STATUS.md`; (b) un test de integración con Postgres real (`EVAL_TEST_DB_URL`, patrón de `tests/integration/test_reconciliador_rls_db.py`) que con usuario NOBYPASSRLS y tenant B no ve filas del tenant A, y sin tenant no ve ninguna. No se toca el job "RLS isolation tests" del CI (es de `ctr_store`).

### D3 — Endpoints (`routes/pedidos_ayuda.py`, prefijo `/api/v1/pedidos-ayuda`)

| Método | Quién | Qué |
|---|---|---|
| `POST /api/v1/pedidos-ayuda` | estudiante | crea; 201 |
| `GET /api/v1/pedidos-ayuda/mios?tarea_practica_id=` | estudiante | los suyos, últimos 20 |
| `GET /api/v1/pedidos-ayuda?comision_id=&estado=` | docente de la comisión / supervisión | lista + `meta.pendientes` |
| `PATCH /api/v1/pedidos-ayuda/{id}/resolver` | docente de la comisión del pedido / supervisión | `pendiente → resuelto`, idempotente |

- **Gates de rol propios** en `auth/dependencies.py` (`require_estudiante`, `require_docente`), siguiendo el precedente de `require_correccion_ia`: `require_permission` no sirve porque sin Casbin el alumno no tiene `create` sobre un recurso nuevo, y meterlo en `STUDENT_READABLE`/excepciones lo vuelve más confuso.
- **Scope del docente**: helper `_assert_docente_de_comision(db, comision_id, user)` con la misma consulta y el mismo **404** que `_assert_comision_visible` (no se reutiliza esa función porque recibe una `Entrega`). Rol docente de `_DOCENTE_ROLES` (incluye `auxiliar` y `jtp`: el ayudante es el que más contesta estas cosas).
- **Validación del POST**, en este orden: comisión de la TP (`_comision_de_la_tp`, 422 si no existe) → inscripción vigente en `inscripciones` (403 "No estás inscripto en la comisión de este trabajo") → si viene `entrega_id`, que sea del alumno y de esa TP (422) → anti-spam (D4). `ejercicio_orden` se acepta si es ≥ 1 y, si la TP tiene ejercicios, si existe entre los esperados (`_ejercicios_esperados`; 422 si no). `episode_id` **no se valida** (ver D2).
- **ROUTE_MAP**: agregar `"/api/v1/pedidos-ayuda": settings.evaluation_service_url` en `apps/api-gateway/src/api_gateway/routes/proxy.py`. Sin esto el endpoint queda inalcanzable desde los frontends.
- **Log**: `pedido_ayuda_creado` y `pedido_ayuda_resuelto` por structlog con `pedido_id`, `tenant_id`, `comision_id`, `tarea_practica_id`, `ejercicio_orden`, `episode_id`, `categoria`. **Nunca el `mensaje`** (texto libre del alumno: puede traer datos personales; los logs de EasyPanel los ve más gente que los docentes de la comisión).

### D4 — Anti-spam en la base, no en Redis

- 429 si el último pedido del alumno (cualquier TP) tiene menos de 60 s.
- 409 si el alumno tiene 3 o más `pendiente` en la misma TP.
- Dos `SELECT` sobre el índice del alumno. Sin Redis: el caso de uso es justamente "la infraestructura está mal"; un rate-limit que dependa de Redis falla cuando Redis está cargando (el `BusyLoadingError` del 16/10 y el 23/10). Una carrera de dos POST simultáneos puede dejar pasar 4 pendientes: aceptable, no se pone lock.
- Frontend: el botón "Enviar" se deshabilita mientras viaja el request y después del éxito (evita el doble clic).

### D5 — `contexto`: diagnóstico mínimo y con lista blanca

Pydantic con `extra="forbid"`: `pantalla` (`"episodio" | "episodio_error" | "lista_ejercicios"`), `error_visible` (string ≤ 300: el texto de error que estaba en pantalla, p. ej. "El ejercicio no terminó de abrirse…"), `user_agent` (≤ 300). Nada de código del alumno, ni conversación con el tutor, ni URL completas: el código y la conversación ya están en el episodio, y el docente llega a ellos por el `episode_id`.

### D6 — UI del alumno

- Componente nuevo `components/PedirAyudaModal.tsx` (usa `Modal` de `@platform/ui`, `size="sm"`). Props: `tareaPracticaId`, `ejercicioOrden?`, `episodeId?`, `entregaId?`, `pantalla`, `errorVisible?`, `getToken`.
- Botón **"Pedir ayuda a tu docente"** (secundario, no compite con el tutor) en:
  1. `EpisodePage.tsx` header, al lado del `HelpButton` (`:1432`). Contexto: `episodeId` (prop), `tarea_practica_id` del estado hidratado o del `ejercicioContext`, `ejercicioOrden`, `entregaId`.
  2. `EpisodePage.tsx` pantalla de error (`:930-955`), al lado de "Reintentar". Contexto: `episodeId` de la URL + `ejercicioContext` de `sessionStorage` (`tarea_id`, `entrega_id`, `ejercicio_orden`). Si no hay `ejercicioContext` (TP monolítica tras un F5) y no hay estado, no se puede saber la TP → el botón **no se muestra** y queda el "Volver"; desde la lista de ejercicios sí puede pedir (caso documentado, ver Riesgos).
  3. `ExerciseListView.tsx` header de la TP (`:392-410`). Contexto: `tarea.id`, `entrega?.id`, sin ejercicio (el modal ofrece un selector opcional "¿En qué ejercicio?" con los ejercicios de la TP).
- Modal: radio de categoría (obligatoria), textarea opcional con contador 0/1000, texto fijo "Esto le llega a tu docente, no al tutor. No es una pista: el tutor sigue siendo tu ayuda para resolver el ejercicio.", y abajo "Tus pedidos en este trabajo" (de `/mios`) con estado *Pendiente* / *Resuelto*. Errores 429/409/403 traducidos a frases.
- **No se pausa ni se cierra el episodio** al abrir el modal: es una superposición; el alumno sigue en el ejercicio.

### D7 — UI del docente: lista + marcar resuelto, sin respuesta escrita

- Ruta `routes/pedidos-ayuda.tsx` (`?comisionId=`, redirige a `/` sin él, como `correcciones.tsx`) y `views/PedidosAyudaView.tsx` con `PageContainer` + `helpContent.pedidosAyuda`.
- Ítem "Pedidos de ayuda" (icono `LifeBuoy` de lucide) en `NAV_GROUPS` → "Trabajo del docente", debajo de "Correcciones".
- Tabla: alumno (`studentShortLabel`), TP, ejercicio, categoría (chip), mensaje (expandible), "hace X", link "Ver episodio" → `/episode-timeline?episodeId=` si hay `episode_id` (si el episodio no existe, la timeline ya muestra su propio vacío: eso **es** el diagnóstico), botón "Marcar resuelto". Pestañas Pendientes / Resueltos. Refresco al entrar y con un botón "Actualizar".
- Contador en `ComisionDelDocenteCard` ("N pedidos de ayuda", link a la vista), desde `meta.pendientes`.
- **Por qué no hay respuesta escrita en el MVP**: una respuesta dentro de la plataforma convierte esto en un canal de mensajería (hilo, notificación al alumno, "leído", moderación), y el alumno tendría que volver a entrar para verla; hoy el docente igual contesta en clase o por Moodle. El valor nuevo es **el dato adjunto**, no el canal. El estado *Resuelto* ya le cierra el círculo al alumno. Si el piloto muestra que hace falta, se suma una columna `respuesta` en otro change (aditivo). Pregunta abierta 1.

### D8 — Sin tiempo real

Polling manual (entrar a la vista / "Actualizar"). Un pedido no es una emergencia de segundos, y SSE/WebSocket acá sería infraestructura nueva para un MVP. Pregunta abierta 2 sobre avisos fuera de la plataforma.

### D9 — "Error de la plataforma" no se rutea aparte

Va al docente como cualquier otro (es quien está con el alumno). Para Neyén queda el log `pedido_ayuda_creado` con `categoria=error_plataforma`, que se filtra desde la consola de logs de EasyPanel sin acceso a la base.

### D10 — Textos de ayuda / onboarding

- web-student `utils/helpContent.tsx`: entrada `episode` suma un párrafo "Si algo no anda o te trabaste, usá 'Pedir ayuda a tu docente': le llega con el ejercicio adjunto. No es una pista." Onboarding del alumno (`onboarding/alumnoOnboarding.tsx`): un paso que señala el botón.
- web-teacher `utils/helpContent.tsx`: key nueva `pedidosAyuda` (qué trae cada pedido, que "Resuelto" lo ve el alumno, que no hay respuesta escrita). Contenido sin tildes (regla del help system, skill `help-system-content`).

## Tesis: qué NO se toca

Restricción del dueño: *nada de la tesis cambia*.

- **Cero cambios** en `apps/ctr-service`, `apps/classifier-service`, `apps/tutor-service`, `packages/contracts`, `ai-native-prompts`, `apps/governance-service`, ni en `LABELER_VERSION` / `classifier_config_hash` / `_EXCLUDED_FROM_FEATURES`.
- **No se emite ningún evento CTR** por pedir ayuda (ni nuevo ni existente). El pedido vive en `academic_main.pedidos_ayuda` + structlog.
- El modal no pausa, no cierra ni abandona el episodio; no toca la sesión Redis del tutor.
- El export académico (`packages/platform-ops/src/platform_ops/academic_export.py`) no incluye pedidos.
- Verificación (tarea 8.1), debe salir **vacío**:

```bash
git diff origin/main --stat -- apps/ctr-service apps/classifier-service apps/tutor-service apps/governance-service packages/contracts ai-native-prompts packages/platform-ops/src/platform_ops/academic_export.py
```

**Nota para Cortez (sin cambio de diseño)**: pedir ayuda a una persona en medio de un episodio es ayuda **fuera de banda**: el CTR no la registra, y un episodio puede verse "autónomo" cuando el alumno en realidad destrabó con el docente. Esto ya pasaba hoy (foro de Moodle, consulta en clase) y no es nuevo; lo nuevo es que ahora el canal es más fácil de usar **y queda registrado con `episode_id` y hora**, así que, si Cortez lo pide, se puede listar qué episodios tuvieron un pedido de ayuda para excluirlos o controlarlos en el análisis. Recomendación: avisarle antes del deploy.

## Risks / Trade-offs

- [El alumno usa el botón como "pedime la respuesta"] → el texto fijo del modal lo aclara; el docente decide qué hacer. Si se vuelve un problema, se ve en los datos (categoría + volumen).
- [Docentes que no entran a web-teacher no ven los pedidos] → contador en "Mis comisiones" y texto de onboarding; pregunta abierta 2.
- [Texto libre con datos personales] → sólo docentes de la comisión + supervisión; no va al log; no va al export. Sin borrado automático en el MVP (igual que las entregas).
- [Pantalla de error de una TP monolítica tras F5 sin contexto] → no hay TP para adjuntar: el botón no aparece ahí y el alumno pide desde la lista de ejercicios (pierde el `episode_id`). Caso raro; documentado.
- [`check-rls` no está en CI] → test de integración propio + tarea manual. No se arregla el CI en este change (fuera de alcance; anotar en `STATUS.md`).
- [Pedidos de una comisión sin docentes asignados] → nadie los ve salvo supervisión. Igual que las entregas hoy.
- [Tests negativos que se vacían solos (lección del repo)] → cada 403/404/409/422/429 se prueba rojo quitando su guard y se anota.

## Migration Plan

1. Deploy de evaluation-service con la migración (aditiva: tabla nueva, nada existente cambia). Correr `alembic upgrade head` de evaluation como en los deploys anteriores.
2. Deploy del api-gateway (ROUTE_MAP) y de los dos frontends.
3. Rollback: frontends viejos no llaman al endpoint; `alembic downgrade -1` borra la tabla (se pierden los pedidos, nada más).

## Prueba local reproducible (para Neyén, sin escribir código)

1. **Levantar el stack** desde `rama desarrollo/` en Git Bash:
   - `DEV_TRUST_HEADERS=true PROMPTS_REPO_PATH="$(cygpath -w "$(pwd)/ai-native-prompts")" bash scripts/dev-start-all.sh`
   - en otra terminal: `pnpm turbo dev`
   - web-student http://localhost:5175, web-teacher http://localhost:5174. Alumno de dev `e19354fb-c05a-4535-a0bf-a7d3ea09692d`, tenant `aaaa…`.
   - Si el Postgres 18 de Windows está prendido, frenarlo (pisa el 5432). Si abrir un episodio da 403: es el tenant `bbbb…` que dejan los smoke (memoria "403 local al abrir episodios").
   - Migrar: `ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main uv run alembic -c apps/evaluation-service/alembic.ini upgrade head`, y `make check-rls` → tiene que decir OK para `pedidos_ayuda`.
2. **Pedido desde un ejercicio**: web-student → una TP publicada → abrir un ejercicio → "Pedir ayuda a tu docente" → "No puedo avanzar" + "no entiendo el while" → Enviar. Ver "Tu pedido le llegó a tu docente" y el pedido como *Pendiente*.
3. **Anti-spam**: enviar otro enseguida → mensaje "Esperá un minuto…". No se crea.
4. **Pedido sin episodio**: volver a la lista de ejercicios → "Pedir ayuda a tu docente" → "Error de la plataforma" → Enviar (pasado el minuto).
5. **Docente**: web-teacher → elegir la comisión → "Mis comisiones" muestra "2 pedidos de ayuda" → menú "Pedidos de ayuda": dos filas con alumno, TP, ejercicio (uno vacío), categoría, mensaje; "Ver episodio" en el primero abre la timeline.
6. **Resolver**: "Marcar resuelto" en uno → pasa a *Resueltos*, contador en 1. En web-student, el pedido figura *Resuelto*.
7. **Privacidad (opcional, con headers)**: con otro docente que no esté en la comisión, la vista da vacío/404.
8. **Tesis**: correr el `git diff` de la sección anterior → vacío.

## Open Questions

1. ¿Hace falta que el docente pueda **escribirle una respuesta** al alumno dentro de la plataforma? Recomendación: no en esta versión (D7); probar dos semanas con "Resuelto" y decidir con datos. Es aditivo, no cambia lo de acá.
2. ¿Los docentes entran seguido a web-teacher como para ver los pedidos a tiempo, o hace falta un **aviso por fuera** (mail/Moodle)? Recomendación: arrancar sin aviso y medir cuánto tardan en marcarlos resueltos (`resuelto_at - created_at`); si es mucho, aviso en otro change.
