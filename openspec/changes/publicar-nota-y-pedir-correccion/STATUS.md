# STATUS — publicar-nota-y-pedir-correccion

Fecha: 2026-10-28. Rama `feat/publicar-nota-y-pedir-correccion` sobre `origin/main` 18bffe9.

## 1.1 Linea base (antes de tocar codigo)

| Chequeo | Resultado |
|---|---|
| `uv run pytest apps/evaluation-service -q` | 294 passed, 165 skipped (los `tests/integration/*_db.py` piden Postgres: ambientales) |
| web-student `pnpm test` | 63 archivos, 675 passed |
| web-teacher `pnpm test` | 33 archivos, 477 passed |
| `tsc --noEmit` (ambos) | limpio |
| `biome check src` | web-student 18 errores, web-teacher 4 (CRLF preexistente; incluye `index.css`). Ninguno en archivos de este change |

## Final (7.2)

| Chequeo | Resultado |
|---|---|
| evaluation-service | 330 passed (+36), 165 skipped (igual) |
| web-student | 65 archivos, 689 passed (+14) |
| web-teacher | 35 archivos, 489 passed (+12) |
| `tsc --noEmit` | limpio en los dos |
| biome | mismos 18 / 4 de la linea base; cero en archivos tocados |
| `ruff check` / `ruff format --check` (evaluation-service) | verde |

## Tests negativos probados rojos (quitando su guard)

- Guard 409 del PATCH sobre no reabierto: 2 rojos.
- 422 lista vacia: 1 rojo. 422 duplicados: 1 rojo. 422 `orden` inexistente: 2 rojos.
- Rama legacy de `ordenes_a_corregir` (sin marcas = todos): 4 rojos.
- web-student: "sin Volver a abrir en no reabiertos": 1 rojo.

## Desviaciones / decisiones

- Tarea 3.2 pide a la vez "los 5 tests existentes siguen verdes" y "con `ordenes=None` reabre todos y los marca". Chocan en
  `test_no_inventa_claves` (afirmaba el conjunto exacto de claves). Se siguio el design (D2: marcar tambien en la devolucion
  total) y se actualizo ESE test para admitir la unica clave nueva `reabierto_por_docente`. Los otros 4 quedaron intactos.
- Validaciones 422 de `ordenes` en el endpoint (no en pydantic) porque necesitan la entrega; la funcion de ruta queda testeable sin DB.
- Rotulos: primera calificacion "Publicar nota"; en modo cola "Publicar y siguiente". "Guardar y siguiente" de la re-calificacion no cambia.
- 7.5: se cambiaron solo los encabezados de `openspec/specs/{correccion-grading,student-exercise-flow}/spec.md`
  (`## ADDED Requirements` -> `## Purpose` + `## Requirements`). `openspec validate --strict` ahora da valido.
- No hay caso de integracion con DB (4.5): no se agrego, el ciclo completo esta en unit (mock) y en `prueba-local-api.py` contra Postgres real.

## 7.1 Tesis

`git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service` -> VACIO.
Grep de lineas agregadas con `emit`/`ctr_`/`publish_event` en `apps/` -> vacio. El log nuevo `tp_correccion_pedida` es structlog (ADR-010).

## 7.3 Prueba local

Ver `prueba-local.md`. Pasos 1-3 y 5-10 verificados por API contra Postgres real; los clicks de UI quedan para un humano (ver el archivo).

## 7.4 Aviso a Cortez (borrador)

Con "Pedir correccion" parcial, los ejercicios no objetados no se rehacen: hay menos segundos intentos por TP devuelta, y el `episode_id`
de esos ejercicios en la re-entrega sigue apuntando al primer intento. El instrumento no cambia (ni clasificador, ni CTR, ni prompts).
Cualquier analisis que cuente re-intentos post-devolucion debe tomar la fecha de deploy de este change como corte temporal.
