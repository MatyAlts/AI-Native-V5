# apply-3-constructor-F: corrección de verify-2 (N1, N2) y decisión O1

- Rol: constructor. Ejecutor: subagente nativo Claude Code (familia Anthropic, la misma que todos los roles previos, incluido el breaker). Gate verify, intento 3 de 3. Nivel CRITICAL.
- Fecha: 04/11/2026, 14:34 a 14:48 (-03:00).
- Revisión de partida: árbol sobre HEAD `b32e621`, sin commits, `arbol=291628b1211abf5a` (la que atacó verify-2).
- Revisión entregada (14:46:49, `scratchpad/hash-arbol.sh`, excluye la carpeta del change): `diff_HEAD_sha256=d4e664d02f90ea5a14ccfc3187389638300fd01f9b78feaa6646ad4b2ba84216 untracked_n=59 untracked_list_sha256=62de33cf8563b29fe392225de3bb654accf985607ebd36b2d805da1c395745be arbol=50fadc6b8a034547`. Sin commits.
- Lecciones L-NNN: no existen en el repo. Ruta leída: ninguna.
- Alcance: solo N1, N2 (resto de F6) y O1. No toqué S2, S3, S4 ni S5 del breaker.

## Archivos tocados

- `routes/estudio.py`: `_buscar_estudio` con modo `share`/`update`; `require_membresia(..., bloquear_estudio=...)`; `_estudio_para_gestionar` e `investigador_con_estudio_bloqueado` toman el estudio en `require_membresia`; `_anclas_invalidas` usa `motivos_ancla_para_congelar`.
- `routes/estudio_trabajo.py`: `bloquear_para_codificar` (share en `require_membresia`); alta y edición de ancla devuelven `faltantes`.
- `services/estudio_esquema.py`: `motivos_ancla_para_congelar`.
- `services/ctr_lectura.py`: `ts`, UUID, `duration_seconds`, `integrity_compromised`.
- web-teacher: `lib/estudioApi.ts` (`AnclaGuardada`), `views/estudio/AdministracionEstudioView.tsx` (aviso de ancla incompleta).
- Tests: `test_estudio_concurrencia_db.py`, `test_estudio_anclas_db.py`, `test_estudio_codebook_db.py` (ancla 1 y literal propio), `test_estudio_traza_db.py`, `test_estudio_muestra_db.py`, `tests/unit/test_ctr_lectura.py`; web-teacher `tests/AdministracionEstudioView.test.tsx`.
- Docs: `docs/servicios/classifier-service.md` §12.2, §12.3, §12.6; ADR-063 D9. `tasks.md` §15 ("Estado de orquestación" sin tocar).

## EVIDENCIA

Detalle completo, con cada salida, en `tasks.md` §15. Resumen:

| Hora | Paso | Resultado |
|---|---|---|
| 14:35:59 | N1 RED (barrera ordenada, 4 vueltas) | `[(200, 500)]*4 != [(200, 403)]*4` en codificador e investigador; 8 `deadlock detected` en el log de Postgres |
| 14:36:29 | N1 GREEN | concurrencia + acceso + etiquetas `66 passed` |
| 14:36:48-14:37:19 | N1 mutantes x3 (orden viejo en cada camino) | muertos, `(200, 500)` |
| 14:38:06 | N2 RED | `13 failed` (`None is CTRNoDisponibleError` x11, `500 == 502` x2) |
| 14:38:27 | N2 GREEN | `106 passed`; 6 mutantes 14:38:45-14:39:17 muertos |
| 14:39:58 | O1 RED | `6 failed` por aserción |
| 14:42:51 | O1 GREEN | estudio + ctr + traza `475 passed`; 3 mutantes 14:43:45-55 muertos |
| 14:44:43 / 14:45:07 | O1 panel RED / GREEN | `Unable to find /quedó incompleta/` / `25 passed`; mutante 14:45:11 muerto |
| 14:45:31-45 | ruff, format, mypy | limpio tras `--fix` de un `I001` en el test; `93 files already formatted`; `Success … 39 source files` |
| 14:45:32 | turbo lint typecheck web-teacher | `2 successful` |
| 14:45:45 | `uv run pytest apps/classifier-service -q -rs` | `4 failed, 708 passed`, sin skips (los 4 ambientales de siempre) |
| 14:46:31 | `pnpm test` web-teacher | `51 files, 687 passed` |
| 14:46:42 | `check-claude-md.py` | `[OK] … sin drift` |
| 14:46:43 | CTR real (`:18087` sobre `cibse-smoke-pg`) | 30/30 episodios aceptados, evidencia y traza sin errores; proceso detenido |

Conteo de tests nuevos (681 -> 708, +27): N1 3, N2 18 (16 unitarios, 2 HTTP), O1 6. Web-teacher 685 -> 687. Mutantes de esta ronda: 13, todos muertos. Migración sin cambios en esta ronda: su ciclo corrió dentro de la suite.

## JUICIO

Autor: constructor F. Confianza alta en N1 (la barrera fija la intercalación: el RED es determinista, no probabilístico), N2 y O1.

- **N1**: tomar el estudio dentro de `require_membresia`, antes de la atadura, alinea los tres caminos con D10b sin cambiar sus resultados válidos. Con la revocación primero en la cola, el primer uso ahora ve la membresía revocada (403) en lugar de morir por deadlock (500).
- **N2**: se valida el formato de lo que se parsea o se computa (`ts`, UUID, `duration_seconds`). Los demás campos del payload se copian tal cual a una respuesta JSON y no pueden romper la traza. Probado contra 30 episodios reales.
- **O1**: misma regla que el cierre (`faltantes_cierre`), misma forma de 422 que F1. El literal de integración cambió porque cambió su entrada; el literal de la unidad, que fija la fórmula, no se tocó, y el procedimiento externo reproduce los dos.

## SUPOSICIÓN (no verificado)

- No corrí `make test-smoke` en esta ronda (el breaker lo corrió sobre `291628b1…`: `100 passed`); N1 cambia locks del codificador y del investigador, cubiertos por los tests de concurrencia y por la suite.
- Escenarios de spec afectados, no editados (son del planner): `codebook-versionado` (congelar rechaza anclas inválidas o incompletas; aviso del PUT), `entrenamiento-calibracion` (ancla incompleta con `faltantes` en borrador), `estudio-codificacion` (409 `sin_muestra`), `estudio-codificacion-acceso` (orden de locks en el primer uso), `traza-ciega-episodio` (formato inválido del CTR -> 502).
- La edición de anclas no tiene UI en el panel: su aviso `faltantes` solo lo ve quien usa la API (runbook).
- No ejecutado: CI, `ruff`/`mypy` del repo entero, Clerk.

## Fuentes leídas

`informes/verify-2-breaker.md` (completo) y `scratchpad/breaker/test_zz_breaker2_{s1_db,unit}.py`; `routes/estudio.py` (membresías, locks, codebook), `routes/estudio_trabajo.py` (`bloquear_para_codificar`, anclas, entrenamiento), `services/{estudio_esquema,ctr_lectura,traza_ciega,estudio_muestra,estudio_codebook}.py`; `tests/integration/test_estudio_concurrencia_db.py`, `test_estudio_codebook_db.py`, `tests/unit/test_estudio_codebook.py`; web-teacher `AdministracionEstudioView.tsx`, `estudioApi.ts`, `tests/_mocks.tsx`; runbook §12 y ADR-063 D9.

## Contaminación

Partí de las reproducciones del breaker y de la decisión O1 del orquestador, por pedido explícito. Mismo proveedor y familia que todos los roles: no hay independencia por proveedor.
