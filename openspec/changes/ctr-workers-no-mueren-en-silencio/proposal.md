## Why

El 2026-10-16 ningún alumno pudo abrir ejercicios en prod. El ctr-service corre en `CTR_MODE=server`: el entrypoint lanza los 8 `partition_worker` en background y hace `exec uvicorn`. Redis tenía el puerto abierto pero respondía `BusyLoadingError` (cargando el dataset); `wait_for_tcp` lo dio por disponible, `PartitionWorker.ensure_consumer_group` lanzó la excepción y **los 8 workers murieron**. El HTTP siguió aceptando `POST /api/v1/events` con 202, así que nadie persistió `episodes`, el tutor devolvió `episode_id` que no existían y el front sacó al alumno a la lista sin decir nada (404 → `salir()` silencioso).

No se perdieron eventos (el group se crea con `id="0"`; al reiniciar se drenó el stream), pero es la **segunda vez** que los 8 workers mueren al arrancar sin que nada lo detecte (2026-06: `gaierror` de DNS, que motivó `wait_for_tcp` y lo arregló a medias). El problema de fondo no es Redis: es que **un worker muerto no se nota y no vuelve**.

## What Changes

- **Arranque — Redis "listo", no "puerto abierto"**: el entrypoint espera a que Redis responda `PING` OK (no `LOADING`, con auth de `REDIS_URL`) antes de migrar/arrancar, con el mismo tope de ~2 min. Postgres sigue con `wait_for_tcp`.
- **Worker — no muere por un transitorio al arrancar**: `ensure_consumer_group` reintenta con backoff exponencial acotado los errores de infraestructura de Redis (`BusyLoadingError`, `ConnectionError`, `TimeoutError`, `OSError`) usando la misma clasificación que `_es_transitorio`, sin tope y logueando cada vuelta. Los errores permanentes (respuesta de Redis que no sea BUSYGROUP ni transitoria) siguen propagando.
- **Supervisión — si un worker muere igual, vuelve**: en `CTR_MODE=server`, cada partición corre bajo un loop supervisor en sh (`ctr-supervise-worker`) que relanza el proceso con backoff cuando sale. Un loop por partición, relanzo serial (solo después de que el anterior terminó): se preserva el single-writer de ADR-010.
- **Detección — el contenedor deja de decir "sano" con los workers caídos**: cada worker escribe un heartbeat en Redis por partición (`ctr:worker:heartbeat:{p}`, TTL corto) en cada vuelta del loop; `/health/ready` del ctr-service agrega el check `workers` y responde 503 si falta alguno. `/health/live` no cambia.
- **UX defensiva — el alumno no vuelve a la lista en silencio**: si `getEpisodeState` agota sus reintentos con 404 en la hidratación de `EpisodePage`, se muestra un error claro con "Reintentar" y "Volver", en lugar de `salir()` silencioso. El 403 conserva el comportamiento actual.
- Fuera de alcance: migrar prod a `CTR_MODE=http` + `ctr-worker-N` dedicados (queda como alternativa futura en design.md).

## Capabilities

### New Capabilities
- `ctr-worker-resilience`: arranque, reintento, supervisión y heartbeat de los `partition_worker` del ctr-service; cómo se detecta y se recupera un worker caído sin romper el single-writer por partición.

### Modified Capabilities
- `student-exercise-flow`: se agrega el requisito de que un episodio que no se puede cargar (404 tras reintentos) muestre un error explícito en vez de devolver al alumno a la lista en silencio.

## Impact

- **ctr-service**: `apps/ctr-service/docker-entrypoint.sh`, nuevo `apps/ctr-service/ctr-supervise-worker.sh`, `apps/ctr-service/Dockerfile` (COPY del script), nuevo módulo `ctr_service/workers/wait_redis.py`, `ctr_service/workers/partition_worker.py` (`ensure_consumer_group`, `run`, heartbeat), `ctr_service/routes/health.py` (check `workers`).
- **web-student**: `apps/web-student/src/pages/EpisodePage.tsx` (rama 404 de la hidratación, cambio quirúrgico).
- **tutor-service**: sin cambios (se evaluó el poll post-publicación y se descartó; ver design.md).
- **Ops / deploy (gobernanza HIGH)**: cambia el arranque del servicio en prod. Mergear a `main` NO deploya; el deploy es manual por EasyPanel y requiere plan de verificación y rollback (en design.md). Cambia la semántica de `/health/ready` del ctr-service (puede pasar a 503 donde hoy da 200): revisar quién lo consume antes de deployar.
- Sin cambios de schema, de contratos de eventos ni de la cadena CTR.
