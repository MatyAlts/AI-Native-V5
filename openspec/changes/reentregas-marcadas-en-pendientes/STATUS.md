# STATUS — reentregas-marcadas-en-pendientes

Fecha: 2026-10-28. Rama `feat/reentregas-marcadas-en-pendientes`, APILADA sobre `feat/publicar-nota-y-pedir-correccion` (PR #126, `448cc21`). Mergear después de #126.

## Línea base (HEAD de #126, antes de tocar código)
| Chequeo | Resultado |
|---|---|
| `uv run pytest apps/evaluation-service -q` | 334 passed, 163 skipped |
| web-teacher `pnpm exec vitest run` | verde (489 tests) |
D5: se aplicó la opción A (marca persiste, la reescribe cada devolución) en #126.

## Final
| Chequeo | Resultado |
|---|---|
| `uv run pytest apps/evaluation-service -q` | 340 passed, 172 skipped (+6 unit `test_reentrega.py`; +9 integración `test_listado_reentregas_db.py`, skipean sin `EVAL_TEST_DB_URL`) |
| Integración con `EVAL_TEST_DB_URL` (docker postgres) | los 9 nuevos pasan; 6 rojos ambientales preexistentes en `test_activeia_payload_db.py` / `test_reconciliador_rls_db.py` (también rojos sin mis cambios) |
| ruff check / format, mypy (evaluation-service) | limpio |
| web-teacher vitest | 37 archivos, 502 passed (+13 nuevos) |
| `tsc --noEmit` web-teacher | limpio |
| biome | los rojos son CRLF del working copy (falso positivo conocido); normalizado a LF, los archivos tocados quedan sin diferencias |

## Notas de implementación
- `reentrega` en `list_entregas` es `bool | None = None` plano (no `Query(None)`): con `Query` las llamadas directas sin el kwarg recibían un objeto truthy y filtraban de más (lo detectó el test "sin parámetro es igual que antes").
- Tests negativos probados en rojo: quitando `es_reentrega &&` del badge fallan 3 tests (nueva sin badge, graded sin badge, marca vieja sin detalle).
- Tesis: `git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/evaluation-service/alembic` → vacío.
- Tarea 3.4 (ciclo completo) cubierta por la prueba local por API (ver `prueba-local.md`), no como test automatizado nuevo.
- Sin verificar: conteo de eventos CTR antes/después (el diff de tesis vacío lo garantiza por construcción, pero no corrí el SQL).
