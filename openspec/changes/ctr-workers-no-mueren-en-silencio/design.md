## Context

Motivación e incidente: ver `proposal.md` → Why. Estado actual relevante, verificado contra el código de `origin/main` (`e946f63`):

- `apps/ctr-service/docker-entrypoint.sh`: `wait_for_tcp` para Postgres y Redis (sólo abre un socket), `alembic upgrade head`, y según `CTR_MODE`: `worker` (un `exec` de un worker), `http` (sólo uvicorn) o `server` (8 workers con `&` + `exec uvicorn`). Nadie hace `wait` sobre los workers: cuando mueren, el contenedor sigue "sano".
- `PartitionWorker.run()` (`partition_worker.py:144`) llama a `ensure_consumer_group()` **fuera** de cualquier try. Ese es el único punto fatal: el loop principal ya envuelve `_process_batch()` en `except Exception` + `sleep(1)` (no muere por infra), y `_process_message` ya clasifica transitorios con `_es_transitorio` (`:376`, reintento sin tope, no consume presupuesto de DLQ). `BusyLoadingError` hereda de `redis.ConnectionError` → `RedisError`, así que `_es_transitorio` ya lo reconoce como transitorio.
- `routes/health.py` del ctr-service: `/health` y `/health/ready` chequean DB + Redis (503 si falla alguno); `/health/live` siempre 200. **No sabe nada de los workers.** El ctr-service mantiene patrón propio (no usa `platform_observability.health`, ver CLAUDE.md).
- `infrastructure/docker-compose.prod.yml`: el ctr-service declara `CTR_MODE: http` + 8 `ctr-worker-N`, sin `healthcheck` y con `restart: unless-stopped`. **Prod real no coincide con el compose**: según el incidente corre `CTR_MODE=server` (EasyPanel pisa env vars desde su UI). Ver Open Questions.
- `apps/web-student/src/lib/api.ts::getEpisodeState` ya reintenta 404 con backoff `[0,200,400,800,1600]` (~3 s en total). El problema UX no es el reintento sino lo que pasa al agotarlo: `EpisodePage.tsx:618` hace `salir()` silencioso.
- CI: `e2e-smoke.yml` levanta los workers vía `scripts/dev-start-all.sh` y espera `curl -sf :8007/health`. `tests/e2e/global-setup.ts` también pega a `/health` del ctr.

## Goals / Non-Goals

**Goals:**
- Que un Redis "abierto pero no listo" no mate a ningún worker, ni en el arranque del contenedor ni en el del proceso.
- Que un worker muerto por cualquier otra causa vuelva solo en `CTR_MODE=server`, sin dos writers por partición.
- Que "HTTP vivo + workers muertos" sea visible en un endpoint (readiness 503 con detalle), no sólo en logs.
- Que el alumno vea un error accionable en vez de volver a la lista.

**Non-Goals:**
- Migrar prod a `CTR_MODE=http` + `ctr-worker-N` (alternativa futura, abajo).
- Agregar `HEALTHCHECK` al Dockerfile ni healthcheck/autoheal al compose de prod (ver decisión 3).
- Cambiar el tutor-service.
- Alertas (Prometheus/Grafana): en prod no hay stack de observabilidad (OTEL apagado en EasyPanel).

## Decisions

### 1. Arranque: espera de Redis por `PING` en un módulo Python, no en sh

Nuevo módulo `ctr_service/workers/wait_redis.py` (`python -m ctr_service.workers.wait_redis --timeout 120 --interval 2`): crea un cliente con `redis.from_url(settings.redis_url)` (hereda auth/db/TLS de la URL), hace `PING` en loop y sale 0 con `PONG`; ante cualquier `RedisError`/`OSError` loguea `intento i/N: <TipoDeError>: <msg>` y reintenta; al agotar el tope sale 1 con la última causa. La lógica vive en una función pura-ish `esperar_redis(client_factory, timeout, interval, sleep, clock)` testeable con un fake client, sin Redis real.

El entrypoint reemplaza `wait_for_tcp "$RD_HOST" ...` por `"$VENV_PY" -m ctr_service.workers.wait_redis` (Postgres sigue con `wait_for_tcp`).

- *Alternativa descartada*: `redis-cli ping` en sh — el slim no trae `redis-cli`, y parsear auth de la URL en sh es frágil.
- *Alternativa descartada*: un one-liner `python -c` dentro del sh como hoy — no es testeable y ya demostró ser donde se esconden los bugs ("puerto abierto" ≠ "listo").
- Mismo tope de ~2 min (60 × 2 s) que `wait_for_tcp` para no cambiar el perfil de arranque.

### 2. Worker: reintento con backoff en `ensure_consumer_group`, reusando `_es_transitorio`

`ensure_consumer_group` pasa a: intentar `xgroup_create(id="0", mkstream=True)`; BUSYGROUP → return; excepción con `_es_transitorio(exc)` → log warning con partición, intento y causa, `await` de backoff exponencial (1, 2, 4, … tope 30 s) **interrumpible por `self._stop`** (`asyncio.wait_for(self._stop.wait(), timeout=delay)`); cualquier otra → raise. Sin tope de intentos: coherente con la política de `_process_message` ("ante un transitorio se reintenta SIN TOPE", docstring de `_es_transitorio`). El sleep y los delays se inyectan (atributo/parámetro con default) para que los tests no esperen.

`run()`: el loop principal **no cambia** — ya sobrevive a errores de infra. Sólo se le agrega la escritura del heartbeat (decisión 4). Se verifica con un test que un `BusyLoadingError` dentro de `_process_batch` no termina `run()` (cubre la pregunta "¿el loop tiene el mismo riesgo?": no lo tiene, y el test lo deja fijado).

- *Alternativa descartada*: catch genérico `except Exception` en `ensure_consumer_group` — convertiría un error de configuración (p. ej. `WRONGTYPE` sobre la key del stream) en un loop silencioso. Los permanentes tienen que morir y ser vistos (decisión 3/4).
- Nota: `AuthenticationError` también hereda de `ConnectionError`, así que una contraseña mala queda reintentando sin tope. Es aceptable porque el arranque (decisión 1) ya falla antes en ese caso, y el heartbeat ausente lo hace visible.

### 3. Supervisión: loop supervisor por partición en sh (opción a), + detección por heartbeat (opción c). Se descarta (b)

**Elegido — (a) `ctr-supervise-worker.sh <partition>`**: script POSIX nuevo, copiado en el Dockerfile a `/usr/local/bin/ctr-supervise-worker`. Hace:

```
delay=1
while true; do
  "$VENV_PY" -m ctr_service.workers.partition_worker --partition "$p"   # foreground: el loop espera a que termine
  rc=$?; log "partition=$p salio rc=$rc; relanzo en ${delay}s"
  sleep $delay; delay=min(delay*2, MAX)       # reset a 1 si el proceso vivio > N s
done
```

En `CTR_MODE=server` el entrypoint lanza `ctr-supervise-worker $p &` (8 supervisores) en vez de 8 workers sueltos, y sigue con `exec uvicorn`. Parámetros por env con defaults (`CTR_SUPERVISE_BACKOFF_MAX=30`, `CTR_SUPERVISE_RESET_AFTER=60`, `CTR_SUPERVISE_MAX_RESTARTS` vacío = infinito, sólo para tests) y `VENV_PY` sobreescribible (`CTR_VENV_PY`) para que el test inyecte un "worker" falso.

**Por qué preserva single-writer (ADR-010)**: hay exactamente un supervisor por partición y el worker corre en **foreground** dentro de su loop; el siguiente lanzamiento sólo ocurre cuando el anterior ya terminó (`wait` implícito). Nunca hay dos procesos de la misma partición. Un worker *colgado* (vivo pero sin consumir) no se relanza — eso lo detecta el heartbeat, no la supervisión, y es correcto que así sea: relanzar algo vivo sí rompería single-writer.

**Elegido además — (c) heartbeat en Redis + check `workers` en readiness**: la supervisión arregla "se murió", pero sólo la detección arregla "nadie se enteró" (que es el título del change) y cubre lo que (a) no cubre: worker colgado, crash-loop permanente, y el modo `http` con `ctr-worker-N` en otros contenedores. Detalle en decisión 4.

**Descartado — (b) matar el contenedor cuando muere un worker (`wait -n`/trap)**:
- `/bin/sh` del `python:3.12-slim` es dash: no tiene `wait -n`; habría que cambiar a bash y reescribir el entrypoint (más superficie en el componente que justo falló).
- Un worker caído tiraría también el HTTP de ingesta: hoy un worker muerto deja eventos encolados y recuperables; con (b) cada crash corta `POST /events` para todo el sistema durante el reinicio, y un Redis que tarda en cargar se vuelve un crash-loop del contenedor entero.
- Depende de que EasyPanel reinicie el contenedor. `restart: unless-stopped` está en el compose, pero prod no sigue el compose (ver Open Questions), así que no hay garantía verificable desde el repo.

**Descartado — `HEALTHCHECK` en Dockerfile/compose para que Docker reinicie**: Docker standalone no reinicia contenedores `unhealthy` (sólo Swarm o un autoheal), así que agregaría la ilusión de una recuperación que no ocurre. El check de readiness queda disponible para quien lo consuma (EasyPanel monitor, curl manual, futuro autoheal).

### 4. Heartbeat: key por partición con TTL, escrita desde el loop principal

- Key `ctr:worker:heartbeat:{partition}`, valor = timestamp ISO + `consumer_name`, `SET ... EX 60`. Se escribe **al inicio de cada vuelta del loop de `run()`** (no en una task aparte): si el loop se cuelga, el heartbeat vence. Con `block_ms=2000` el loop da vueltas cada ≤2 s en reposo; el TTL de 60 s deja margen para batches lentos (32 mensajes con DB lenta). Fallo al escribirlo → log debug y se sigue (no puede tumbar el worker). Escritura en el mismo `try` que `_process_batch` no: va en su propio `try` para que un fallo del heartbeat no saltee el batch.
- Se escribe recién **después** de que `ensure_consumer_group` tuvo éxito: un worker reintentando el arranque no está consumiendo, y el health lo tiene que decir.
- `health.py` agrega `_check_workers()`: un `MGET` de las 8 keys (`NUM_PARTITIONS` importado de `services/producer.py`, no un 8 literal) con el mismo timeout de 2 s; devuelve `"ok"` o `"fail: sin heartbeat p3,p5"`. Entra al `all(...)` de readiness → 503. `/health/live` no se toca.
- Prefijo propio del CTR (`ctr:`), no colisiona con `tutor:*`.
- *Alternativa descartada*: heartbeat por archivo local (`/tmp/hb-N`) — no sirve en modo `http` (workers en otro contenedor) y no es observable desde afuera.
- *Alternativa descartada*: derivarlo de `XINFO CONSUMERS` (`idle`) — `idle` crece también cuando simplemente no hay tráfico (de noche), así que no distingue "muerto" de "sin trabajo".

### 5. UX: el front muestra error accionable; el tutor-service no cambia

Elegido: en la hidratación de `EpisodePage.tsx`, la rama `e.status === 404` deja de llamar `salir()`: limpia `ACTIVE_EPISODE_KEY` y setea un estado de error de carga ("El ejercicio no terminó de abrirse. Puede ser una demora del sistema: probá de nuevo en unos segundos.") con botones **Reintentar** (re-dispara la hidratación vía un contador `reloadKey` agregado a las deps del effect) y **Volver** (`salir()`, el mismo camino de hoy). El 403 sigue con `salir()`. No se toca `getEpisodeState` (sus ~3 s de backoff siguen), ni los listeners de abandono, ni `salir()`.

- Cambio quirúrgico: una rama del `catch` y un botón. Ya existe el panel a reusar: cuando `!tarea`, `EpisodePage.tsx:~912` renderiza `{error ?? "No pudimos cargar el episodio."}` con el botón "Volver a mis materias" (`onClick={salir}`). La rama 404 pasa a `setError(<mensaje de apertura>)` y ese panel suma un botón "Reintentar" que incrementa `reloadKey`. No se crea un componente nuevo.
- El caso "sessionStorage viejo con un episodio que ya no existe" (recovery de `routes/index.tsx`) ahora muestra el mensaje en vez de volver solo. Es aceptable: el marcador se limpia en el mismo paso, así que "Volver" no hace loop, y es preferible un mensaje de más a un rebote silencioso.

**Descartado — poll en el tutor-service tras publicar `episodio_abierto` (≤3 s, 503 si no aparece)**:
- Suma latencia a **todas** las aperturas normales (el worker tarda ~1 s), para cubrir un caso que después de las capas 1–3 debería ser raro.
- Un 503 no deshace el evento: el `episodio_abierto` ya está en el stream y se va a persistir cuando el worker vuelva. Si el alumno reintenta, `find_open_episode` (que consulta la DB del CTR) no lo encuentra y se abre un **segundo** episodio → dos episodios abiertos del mismo alumno/ejercicio cuando el stream drene. Es peor para la cadena que el síntoma actual.
- Toca `open_episode`, una función con 270 líneas de validaciones, idempotencia y emisión CTR — más riesgo que valor.

### Alternativa futura (fuera de alcance): `CTR_MODE=http` + `ctr-worker-0..7`

Es lo que el compose de prod ya declara: cada partición en su contenedor, reiniciado por el orquestador. Aísla fallas y escala, pero requiere tocar la config de EasyPanel (8 servicios nuevos) y garantizar que no conviva con `server` (doble writer). Este change no lo bloquea: las capas 1, 2 y 4 aplican igual en ese modo.

## Risks / Trade-offs

- [Readiness pasa a 503 donde hoy da 200] → CI (`e2e-smoke.yml`, `tests/e2e/global-setup.ts`) espera `/health` del ctr con los workers de `dev-start-all.sh`; los workers escriben el heartbeat en ≤2 s de arrancar, así que el gate debería seguir pasando. Task explícita para verificarlo en el PR. Si algún consumidor de prod (monitor de EasyPanel) usa `/health` del ctr para decidir tráfico, un worker caído ahora sacaría al HTTP de rotación → Open Question.
- [Crash-loop invisible del supervisor] → cada salida se loguea con rc y el heartbeat vence: el health lo muestra. El backoff con tope evita martillar Redis/Postgres.
- [Supervisor sh muere] → improbable (es un `while` sin lógica), y si pasa, el heartbeat de esa partición vence y readiness da 503.
- [Señales al apagar] → igual que hoy: uvicorn es PID 1 tras el `exec`; al parar el contenedor los supervisores y workers reciben SIGKILL. Sin regresión; el at-least-once + idempotencia por `event_uuid` cubren el reprocesamiento.
- [Reintento sin tope ante `AuthenticationError`] → aceptado (decisión 2); visible por heartbeat.
- [Heartbeat con TTL 60 s] → un worker recién muerto tarda hasta 60 s en verse en readiness. Aceptado: la supervisión lo relanza antes.
- [Mensaje de error UX en el recovery de sessionStorage viejo] → aceptado (decisión 5).

## Migration Plan

Gobernanza HIGH: cambia el arranque del servicio que ingesta la cadena CTR. **Mergear a `main` NO deploya** (el deploy es manual por EasyPanel).

1. **Antes de deployar**: confirmar en EasyPanel el `CTR_MODE` real del ctr-service y si existen servicios `ctr-worker-N` (Open Question 1). Si conviven `server` + `ctr-worker-N`, **no deployar** este change sin resolver eso primero (doble writer ya existente, no lo introduce este change).
2. Deploy del ctr-service y del web-student (independientes; el orden no importa).
3. **Verificación post-deploy** (la corre el humano y pega la salida):
   - Logs del ctr-service: `Redis disponible (PING OK)` y 8 líneas `Worker partition=N ... iniciado`.
   - `curl -s <ctr>/health/ready` → 200 con `checks.workers = "ok"`.
   - Abrir un ejercicio como alumno de prueba → entra.
   - Opcional (ventana tranquila): matar un worker (`kill <pid>` dentro del contenedor) → en el log aparece `partition=N salio rc=...; relanzo` y el heartbeat vuelve.
4. **Rollback**: redeploy en EasyPanel de la imagen/commit anterior. No hay migraciones ni cambios de datos; las keys `ctr:worker:heartbeat:*` vencen solas por TTL. El stream no se ve afectado (mismo consumer group, misma semántica `id="0"`).

## Open Questions

1. ¿Prod corre `CTR_MODE=server` **y además** servicios `ctr-worker-N`? El compose versionado dice `http` + workers dedicados; el incidente dice `server`. No cambia el diseño (las capas aplican en ambos modos), pero si conviven es un doble writer preexistente que hay que cortar antes de este deploy.
2. ¿Algo en EasyPanel consume `/health` del ctr-service para rutear o reiniciar? Si sí, el nuevo 503 por workers caídos cambia su comportamiento (probablemente para bien, pero hay que saberlo).
