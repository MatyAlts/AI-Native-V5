# ADR-025 — Política de cierre de episodios y emisión de `episodio_abandonado`

- **Estado**: Aceptado
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: ctr, frontend, instrumentación, tesis
- **Cierra**: G10-A del audi2.md (decisión opción A — emitir efectivamente).

## Contexto y problema

`EpisodioAbandonado` está declarado en `packages/contracts/src/platform_contracts/ctr/events.py:69-76` con payload `(reason, last_activity_seconds_ago)` desde F3. La Sección 7.2 de la tesis lo lista entre los 8 eventos instrumentados de v1.0.0. **Antes de este ADR, en runtime ningún servicio backend ni frontend lo emitía** — verificado con grep sobre la base de código. Era la asimetría más visible entre la tesis y el código (audi2.md G10).

El gap pedagógico es relevante: `episodio_abandonado` distingue "el estudiante cerró la pestaña / se quedó sin conexión" de "el estudiante terminó deliberadamente con `episodio_cerrado`". Esa distinción es informativa para CCD y para el árbol de apropiación — sin ella, todo cierre que no sea `student_finished` queda como dato faltante.

## Drivers de la decisión

- **Honestidad académica**: la tesis no debe seguir afirmando instrumentación falsa sobre v1.0.0.
- **Cobertura del caso real**: `beforeunload` no se dispara en mobile, en crashes, ni cuando se pierde conexión. Necesitamos un mecanismo server-side que cubra esos casos.
- **Idempotencia**: si tanto el frontend (`beforeunload`) como el server (timeout) detectan abandono para el mismo episodio, NO debe haber doble emisión al CTR.
- **No tocar el contract**: el payload ya existe y el labeler ya cataloga el evento como `meta`. Sumar emisores no requiere cambio de contract ni migración.
- **Reproducibilidad bit-a-bit**: el cálculo de `last_activity_seconds_ago` no entra en ningún hash determinista (es del payload, no afecta `classifier_config_hash`). No hay impacto sobre auditabilidad.

## Opciones consideradas

### Opción A — emitir efectivamente (elegida)

Dos triggers complementarios:

1. **Frontend (`beforeunload`)**: cuando el usuario cierra la pestaña o navega afuera con un episodio abierto, el web-student dispara un POST al endpoint `/api/v1/episodes/{id}/abandoned` con `reason="beforeunload"`. Usa `navigator.sendBeacon` cuando no hay token (proxy dev) y `fetch` con `keepalive: true` cuando hay token (prod OIDC).
2. **Worker server-side (timeout)**: tarea async que cada `abandonment_check_interval_seconds` (default 60s) escanea las sesiones activas en Redis. Para cada `last_activity_at` con `now - last_activity_at >= episode_idle_timeout_seconds` (default 30 min), emite `episodio_abandonado(reason="timeout")` y borra el state.

**Idempotencia**: ambos caminos llaman a `TutorCore.record_episodio_abandonado()`, que devuelve `None` si la sesión ya no existe. La primera emisión gana, la segunda es no-op silenciosa.

**Caller del CTR**:
- `reason="beforeunload"` / `"explicit"` → `caller_id` = UUID del estudiante (su acción).
- `reason="timeout"` → `caller_id` = `TUTOR_SERVICE_USER_ID` (servicio detectó inactividad).

### Opción B — eliminar del contract y declarar en tesis

Quitar `EpisodioAbandonado` del Pydantic, renumerar la 7.2 a 7 instrumentados, declarar como agenda piloto-2.

**Descartada porque**: pedagógicamente perdemos la distinción entre cierre intencional y cierre por inactividad, que es información valiosa para CCD. Y el contract ya estaba — es menos costoso emitirlo que justificar su ausencia.

## Decisión

Opción **A** — emitir efectivamente con doble trigger (frontend + worker server-side) y idempotencia por estado de sesión.

### Cambios concretos

| Archivo | Cambio |
|---|---|
| [`apps/tutor-service/src/tutor_service/services/session.py`](../../apps/tutor-service/src/tutor_service/services/session.py) | Campo `last_activity_at: float` en `SessionState`; `set()` lo refresca; nuevo `iter_active_sessions()` con SCAN. |
| [`apps/tutor-service/src/tutor_service/services/tutor_core.py`](../../apps/tutor-service/src/tutor_service/services/tutor_core.py) | Método `record_episodio_abandonado(episode_id, reason, last_activity_seconds_ago, user_id)` idempotente. |
| [`apps/tutor-service/src/tutor_service/services/abandonment_worker.py`](../../apps/tutor-service/src/tutor_service/services/abandonment_worker.py) | Nuevo. `_sweep_once()` + `run_abandonment_worker()` (loop cancelable). |
| [`apps/tutor-service/src/tutor_service/routes/episodes.py`](../../apps/tutor-service/src/tutor_service/routes/episodes.py) | Endpoint `POST /api/v1/episodes/{id}/abandoned` con schema `AbandonedEpisodeRequest`. |
| [`apps/tutor-service/src/tutor_service/main.py`](../../apps/tutor-service/src/tutor_service/main.py) | Lifespan arranca/cancela el worker según `enable_abandonment_worker`. |
| [`apps/tutor-service/src/tutor_service/config.py`](../../apps/tutor-service/src/tutor_service/config.py) | Settings `episode_idle_timeout_seconds=1800`, `abandonment_check_interval_seconds=60`, `enable_abandonment_worker=True`. |
| [`apps/web-student/src/lib/api.ts`](../../apps/web-student/src/lib/api.ts) | Función `emitEpisodioAbandonado()` con sendBeacon + fetch keepalive fallback. |
| [`apps/web-student/src/pages/EpisodePage.tsx`](../../apps/web-student/src/pages/EpisodePage.tsx) | `useEffect` que registra listener `beforeunload` mientras hay `episodeId` activo. |

### Constantes inmutables documentadas

- `TUTOR_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000010")` — caller_id para emisiones server-side (worker timeout). Ver invariante en CLAUDE.md "Constantes que NO deben inventarse".
- `episode_idle_timeout_seconds = 1800` — 30 min de inactividad. Decisión arbitraria del piloto. Cambios futuros: pueden requerir bumpear `LABELER_VERSION` si afectaran el etiquetado de N-level (no aplica hoy — el labeler trata `episodio_abandonado` como `meta`).
- `abandonment_check_interval_seconds = 60` — sweep cada 1 min. Si Redis tiene N sesiones activas el sweep es O(N) — para tamaños de piloto (≤500 estudiantes concurrentes) es trivial. Si crece, pasar a notificación pull-push o keyspace events.

## Consecuencias

### Positivas

- **Cierra G10 del audi2.md** sin tocar contract. La tesis 7.2 puede afirmar honestamente "8 eventos instrumentados v1.0.0".
- **Distingue cierre intencional de cierre por inactividad** — input pedagógicamente rico para CCD y para análisis longitudinal del piloto.
- **Idempotencia por diseño**: `record_episodio_abandonado` devuelve `None` si el state ya no existe. La carrera entre worker y frontend nunca produce doble emisión al CTR.
- **Falla soft**: si el publish al CTR falla, el worker logea y continúa con la próxima sesión. El frontend usa `sendBeacon` que es fire-and-forget — no bloquea el unload.
- **Cero impacto en reproducibilidad bit-a-bit**: el `payload.last_activity_seconds_ago` no entra en `classifier_config_hash` ni en `self_hash` del CTR de manera que afecte cadenas existentes.

### Negativas / trade-offs

- **`last_activity_seconds_ago` desde el frontend no es confiable**: el browser no tiene baseline de "última acción del estudiante" sin instrumentación adicional (mousemove, keystroke). El frontend manda `0` por default — el backend acepta el valor y queda como signal honesta. Mejorable en agenda futura.
- **Worker single-instance friendly pero no exclusivo**: si hay 2 réplicas del tutor-service, ambas escanean las mismas keys; pierde una sola, la otra es no-op por idempotencia. NO requiere lock distribuido, pero sí desperdicia trabajo redundante. Para pasajes a alta concurrencia: pasar a Redis Streams con consumer groups (mismo patrón que ctr-service).
- **Mid-cohort introduce sesgo declarable**: episodios anteriores al deploy de este ADR no tienen el evento. El piloto debe documentar la fecha del cutover en el reporte empírico (principio P6 de la tesis 21.4).
- **`sendBeacon` no soporta Authorization header**: en producción con OIDC habrá que firmar la URL o usar cookies con el JWT. Hoy en dev mode el proxy de Vite inyecta `X-User-Id` automáticamente.

### Neutras

- El labeler (ADR-020) ya cataloga `episodio_abandonado` como `meta` — no requiere bump de `LABELER_VERSION`.
- El `event_type` ya estaba en el contract — sin migración Pydantic ni TypeScript.
- El integrity-attestation-service (ADR-021) firma todos los eventos del CTR independientemente del tipo — las attestations cubren `episodio_abandonado` desde el primer evento emitido sin cambios.

## Coordinación con piloto

- **Cutover**: aplicar al cierre del cuatrimestre vigente o entre cuatrimestres. El reporte empírico declara la fecha y trata episodios pre-cutover como "abandono no observable" (consistente con principio de no-modificación de eventos históricos del CTR, ADR-010).
- **Defensa de tesis (>6 semanas)**: hay margen para validar el flujo en producción antes de la defensa. El comité no debe encontrar la asimetría tesis-código documentada en audi2.md.

## Referencias

- audi2.md G10 — decisión bifurcada A vs B (raíz del repo).
- ADR-010 — append-only del CTR (cero `UPDATE`/`DELETE` de eventos).
- ADR-020 — etiquetador N1-N4: trata `episodio_abandonado` como `meta`.
- ADR-021 — integrity-attestation-service: firma todos los eventos del CTR.
- Tests: `apps/tutor-service/tests/unit/test_episodio_abandonado.py` (7 tests pasando).
- Tesis Sección 7.2 — eventos instrumentados v1.0.0.
- Tesis principio 21.4 P6 — declaración de versiones en reportes empíricos.
