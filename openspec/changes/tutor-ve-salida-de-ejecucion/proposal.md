## Why

El tutor socrático **no ve la salida** de lo que el alumno ejecuta. El frontend manda `code`/`stdout`/`stderr` en cada corrida (`routes/episodes.py:759-804`) y eso se persiste en la cadena CTR, pero **nunca vuelve al contexto del LLM**: `interact()` arma los `messages` con RAG, código del editor, rúbrica y refuerzo adverso, y nada de la ejecución (`tutor_core.py:820-881`).

Consecuencia: ante "me tira error", el tutor pide el error que no tiene, y el alumno no puede traérselo porque **el código y la salida no salen del editor** (bloqueo del portapapeles, commit `9a7206a`). Es un callejón sin salida que ningún cambio de prompt arregla: el dato tiene que llegar.

Decisión ya tomada (opción B): el tutor recibe **automáticamente** la salida de la **última** ejecución. Sin desbloquear copiar/pegar y sin botón "mandar error al tutor".

## What Changes

- La sesión del tutor guarda un resumen de la **última ejecución** del alumno (stdout y stderr **truncados**, duración, huella del código ejecutado), actualizado en cada `codigo_ejecutado`.
- En cada turno, `interact()` inyecta ese resumen como mensaje `system` adicional, **delimitado como dato** (no instrucciones) y marcado como **desactualizado** si el alumno editó el código después de correrlo.
- `resume_episode()` reconstruye la última ejecución desde el último evento `codigo_ejecutado` de la cadena, para que una sesión reanudada no la pierda.
- Bug menor que se arregla de paso: `emit_codigo_ejecutado` no actualiza `current_code`, aunque el payload trae `code` y `resume()` sí lo lee de ese evento. Hoy la sesión viva y la reanudada divergen.
- **Sin cambios** en: payload del evento CTR (byte a byte igual; el classifier lee `stdout`/`stderr` crudos en `subgrupo.py:157,186`), `LABELER_VERSION`, `classifier_config_hash`, prompt del tutor (`system.md`), frontend, portapapeles.

## Capabilities

### New Capabilities
- `tutor-contexto-ejecucion`: el tutor recibe en su contexto la salida de la última ejecución del alumno, truncada, delimitada como dato, con aviso de desactualización y persistente a través de la reanudación del episodio.

### Modified Capabilities
(ninguna — no hay spec previa del contexto del tutor en `openspec/specs/`)

## Impact

- `apps/tutor-service/src/tutor_service/services/session.py` — campo nuevo en `SessionState` + mapeo en `get()`/`set()` (sesiones legacy → `None`).
- `apps/tutor-service/src/tutor_service/services/tutor_core.py` — `emit_codigo_ejecutado` (guardar última ejecución + `current_code`), `interact()` (inyección), `resume_episode()` (reconstrucción), helper puro de truncado/formato.
- `apps/tutor-service/tests/unit/` — tests nuevos (`test_contexto_ejecucion.py`) y extensión de `test_resume_episode.py`.
- Gobernanza: **no** requiere bump de versión del prompt ni gate de Ana Garis, siempre que el texto inyectado sea descriptivo y no agregue directivas pedagógicas (ver `design.md`, D6).
- Deploy: sólo `tutor-service`. No hace falta reconstruir la imagen del governance-service.
