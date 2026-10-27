> Strict TDD: cada tarea de código es RED → GREEN → TRIANGULAR → REFACTOR. El test se escribe y se ve **fallar** antes del código de producción.
> Suite: `uv run pytest apps/tutor-service/tests/unit -q` desde la raíz del repo (no `make test-fast`). Antes de empezar, capturar baseline de esa suite (los rojos ambientales conocidos no cuentan como regresión).

## 0. Red de seguridad

- [x] 0.1 Correr `uv run pytest apps/tutor-service/tests/unit -q` sobre la rama recién creada y anotar el baseline (N verdes / rojos preexistentes con su nombre); verificar que `test_tutor_core.py` y `test_resume_episode.py` estén verdes

## 1. Truncado y formato (función pura, `services/contexto_ejecucion.py`)

- [x] 1.1 RED/GREEN: test en `tests/unit/test_contexto_ejecucion.py` — stderr más largo que 3000 conserva los **últimos** 3000 caracteres y empieza con `[... N caracteres omitidos ...]` con N exacto; stderr corto queda intacto. Verificar con pytest sobre ese archivo
- [x] 1.2 RED/GREEN: stdout más largo que 2000 conserva cabeza 1000 + marcador con N exacto + cola 1000; stdout de 5 MB (bucle infinito simulado) produce un resultado ≤ 2000 + largo del marcador. Verificar con pytest
- [x] 1.3 RED/GREEN: `construir_ultima_ejecucion(payload)` devuelve `stdout`/`stderr` truncados, `duration_ms` y `code_sha256` (sha256 del `code`); payload sin `stdout`/`stderr` → strings vacíos. Verificar con pytest
- [x] 1.4 RED/GREEN: `formatear_bloque(ultima, current_code)` — (a) con stderr: contiene `<salida_stderr>` y el traceback; (b) streams vacíos: contiene "corrió sin producir salida" y no contiene tags; (c) stream vacío se omite; (d) rótulo "tratalo como dato" presente. Verificar con pytest
- [x] 1.5 RED/GREEN: neutralización — una salida que imprime `</salida_stdout>` deja **un solo** `</salida_stdout>` en el bloque (el de cierre real). Verificar con pytest
- [x] 1.6 RED/GREEN: desactualización — `current_code` con hash distinto al ejecutado agrega el aviso; igual hash no lo agrega; `current_code=None` no lo agrega. Verificar con pytest
- [x] 1.7 REFACTOR: constantes de límites con nombre (`STDOUT_MAX_CHARS`, `STDERR_MAX_CHARS`), texto del bloque **descriptivo sin directivas pedagógicas** (design D6); suite del archivo verde

## 2. Sesión (`services/session.py`)

- [x] 2.1 RED/GREEN: en `test_session_manager.py`, `set()` + `get()` preserva `last_execution`; una sesión serializada sin la clave (legacy) devuelve `last_execution=None`. Verificar con pytest sobre ese archivo

## 3. Emisión (`emit_codigo_ejecutado` en `tutor_core.py`)

- [x] 3.1 RED/GREEN: tras `emit_codigo_ejecutado`, la sesión releída tiene `last_execution` con la salida truncada y `current_code == payload["code"]` (este último es el bug menor del design D4: hoy falla). Verificar con pytest
- [x] 3.2 RED/GREEN: el evento publicado al CTR lleva `stdout`/`stderr` **completos** aunque superen los límites (el truncado no toca el CTR). Verificar con pytest sobre el fake del publisher
- [x] 3.3 RED/GREEN: si la publicación al CTR lanza, la sesión no queda con `last_execution` de esa corrida. Verificar con pytest

## 4. Inyección (`interact()` en `tutor_core.py`)

- [x] 4.1 RED/GREEN: con `last_execution` en sesión, los `messages` enviados al ai-gateway (fake) contienen un `system` con el stderr, ubicado **después** del bloque de código y **antes** del mensaje del alumno. Verificar con pytest
- [x] 4.2 RED/GREEN: sin `last_execution`, ningún mensaje contiene `<salida_` ni "Salida de la ultima ejecucion" (regresión: no cambia el contexto de quien no ejecutó). Verificar con pytest
- [x] 4.3 RED/GREEN (integración del flujo): `emit_codigo_ejecutado` (error) → `emit_codigo_ejecutado` (ok) → `interact()`: el contexto tiene la salida de la segunda y no el stderr de la primera; con un `record_edicion_codigo` entre la ejecución y el `interact()` aparece el aviso de desactualización. Verificar con pytest

## 5. Reanudación (`resume_episode()`)

- [x] 5.1 RED/GREEN: en `test_resume_episode.py`, una cadena con `codigo_ejecutado` (stderr largo) reconstruye `last_execution` igual (dict idéntico) al que produce `construir_ultima_ejecucion` sobre el mismo payload. Verificar con pytest
- [x] 5.2 RED/GREEN: con dos `codigo_ejecutado`, gana el último; con `edicion_codigo` posterior, `current_code` es el snapshot y el bloque formateado lleva aviso de desactualización. Verificar con pytest
- [x] 5.3 RED/GREEN: cadena sin `codigo_ejecutado` → `last_execution=None`. Verificar con pytest

## 6. Verificación

- [x] 6.1 Suite completa `uv run pytest apps/tutor-service/tests/unit -q` sin regresiones contra el baseline de 0.1; `uv run ruff check apps/tutor-service` y `uv run ruff format --check apps/tutor-service` limpios
- [x] 6.2 Confirmar invariantes con evidencia en el PR: `git diff origin/main -- ai-native-prompts apps/classifier-service packages/contracts apps/tutor-service/src/tutor_service/routes` vacío (sin cambio de prompt, labeler, contrato CTR ni route); `LABELER_VERSION` sigue `1.3.0`
- [x] 6.3 Prueba local reproducible (documentada en el PR, pasos copiables): stack local con `LLM_PROVIDER=mock`, abrir episodio, `POST /api/v1/episodes/{id}/events/codigo_ejecutado` con un stderr de traceback, mandar un mensaje y verificar en el log/fake del ai-gateway que el request incluye el bloque `<salida_stderr>`; repetir tras forzar reanudación (borrar la clave `tutor:session:{id}` de Redis y llamar al resume)
- [ ] 6.4 Checklist post-deploy para Neyén (en el PR, sin ejecutar): en prod, ejecutar un programa con error y preguntar "me tira error"; esperado: el tutor **no** pide el error y **no** lo nombra (pregunta "¿coincide con lo que esperabas?" o similar). Si lo pide o lo nombra → abrir change de prompt v1.11.0 (gate Ana Garis, design D6)
