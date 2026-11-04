# Informe propose-3-plan-reviewer

- Change: `cibse-codificacion-ciega`
- Rol: plan-reviewer (propose, intento 3, último del gate)
- Ejecutor: subagente nativo de Claude Code (role plan-reviewer), familia Anthropic, la misma que el planner. Sin independencia de proveedor.
- Revisión revisada: `origin/main @ b32e621` (código sin cambios: `git status` solo muestra `openspec/` y el `scripts/backfill-attestations.py` sin trackear que ya estaba al inicio). sha256 (12 primeros) de lo que leí: proposal `ae2cede8d417`, design `d52a5b75d174`, tasks `ffc65a69e7c3`, specs: codebook-versionado `ade6518708de`, entrenamiento-calibracion `8e5a3f55a496`, estudio-codificacion-acceso `d827a1c86fc9`, estudio-codificacion-exportacion `2716be974337`, estudio-codificacion `62183463233e`, traza-ciega-episodio `aa9a0c3ba14b`. Coinciden con los que declara el planner, salvo tasks (`fa5c49bbbbb2` según él): el bloque de orquestación lo edita el orquestador (SUPOSICIÓN, sin copia para diffear).
- Fecha: 2026-11-04. No edité el plan ni código.

## Veredicto

**APTO.** No hay bloqueantes ni mayores abiertos. B-1 y N-1 a N-7 están resueltos. Queda 1 hallazgo nuevo MENOR (R3-1), que se puede resolver en construcción o registrar como DEUDA sin replanificar. `## Aprobación` sigue vacía (solo el comentario reservado): verificado. El plan está en condiciones de pedir la aprobación humana. La aprobación tiene que nombrar el nivel (CRITICAL recomendado) y responder al menos las preguntas 5 y 6, que fijan defaults del orquestador sin confirmación humana.

## EVIDENCIA

| # | Comando / lectura | Momento | Resultado |
|---|---|---|---|
| E3-1 | `sha256sum` de los 9 artefactos | 04/11 ~11:27 | hashes de arriba |
| E3-2 | `rg -n -i 'incoherent|disiente|disiento|advertencia'` en proposal, design, tasks y specs | 04/11 | solo quedan menciones que dicen que esas columnas no existen (design D1 y D9, tasks 2.1) y `disiente_de_regla` como valor derivado; ningún requisito ni tarea conserva la variante del intento 2 |
| E3-3 | Lectura de design D4, D4b, D6 a D9 completos; specs estudio-codificacion (régimen, propuesto, cierre, muestra), traza-ciega-episodio (latidos, abandonado), entrenamiento-calibracion, exportación; proposal preguntas 5, 6 y `## Aprobación`; tasks 1.1, 2.1, 3.2, 6.1, 7.1, 7.3, 10.1 | 04/11 | base de la tabla de disposición |
| E3-4 | `git rev-parse --short HEAD`; `git status --short` sin `openspec/` | 2026-11-04T11:29:25-03:00 | `b32e621`; solo `scripts/backfill-attestations.py` sin trackear (preexistente). El código bajo prueba no cambió desde E2-3 a E2-5 |
| E3-5 | `uv run pytest` de los 4 archivos con `create_all` + `test_pedagogia_distribucion.py` | 2026-11-04T11:29:25-03:00 | `38 passed` (36 + 2, coincide con E2-3 y E2-4) |
| Reusado | `uv run pytest apps/analytics-service -q` (E2-5 del intento 2) | 2026-11-04T11:21 | `182 passed`. No lo reejecuté porque el código no cambió (E3-4) |
| Reusado | E2-8 (`partition_worker.py:677-728`: abandono deja `paused`, actividad posterior lo vuelve `open`) | intento 2 | base para N-1 |

No ejecuté nada contra Postgres, CTR, Clerk ni producción. No hay código nuevo.

## Disposición de hallazgos previos

| Hallazgo | Estado | Verificado en | Comentario |
|---|---|---|---|
| B-1 (parcial en intento 2) | Resuelto | D9 "Régimen según la regla"; spec estudio-codificacion "Régimen derivado por la regla del codebook" (4 escenarios), "Régimen propuesto por desacuerdo" (2), "Cierre"; task 3.2 con casos y mutantes (aceptar régimen distinto del derivado, aceptar propuesto sin nota) | El régimen persistido es el de la regla y el desacuerdo va a `regimen_propuesto` con nota. Coincide con la letra de la §7 del v0 |
| N-1 abandonados | Resuelto | D6, D11, D4b; specs "Episodio inexistente o no terminado", "Episodio abandonado en la muestra", reanudación posterior; entrenamiento-calibracion; tasks 7.1 (CSV sintético con un `paused` abandonado aceptado, reanudación tras la carga) y 7.3 | El criterio por último evento de cierre es consistente con E2-8; `integrity_compromised` queda como default con pregunta 5 |
| N-2 contradicción con §7 | Resuelto | igual que B-1; proposal pregunta 6 explica la alternativa descartada | |
| N-3 `traza_version` previa a la muestra | Resuelto | D1, D4b ("se fija en el alta") | |
| N-4 forma canónica de anclas | Resuelto | D8 (lista de campos, sin `item_id`, orden `(uso, orden, episode_id)`); task 5.1 | |
| N-5 serialización del orden | Resuelto | D7 (semilla decimal, UUID minúsculas con guiones, utf-8, rango del hex); task 7.2 | |
| N-6 latidos | Resuelto | D4 tabla y localizador `lectura k`; spec "Latidos de lectura agrupados"; tasks 6.1, 11.4 | |
| N-7 línea de base | Resuelto | task 1.1 y design Context dicen 36; reejecutado 36 (E3-5) | |
| Intento 1 (M-1 a M-8, m-1 a m-11) | Siguen resueltos | sin regresiones en las secciones tocadas (D1-D4b, D10, D10b, D13 leídos) | |

## Verificación pedida: "evidencia insuficiente a mano" contra la regla y la §4

- Contra la regla de coherencia (JUICIO, confianza alta): no la rompe en lo formal. El exento está declarado en el meta-esquema (`regimenes_exentos`, D9), la §4 lo deja fuera del orden de la regla ("cuando no hay material para aplicar la regla") y la §7 exige notas para ese caso (`notas_obligatorias_si_regimen`). Un régimen no exento distinto del derivado sigue dando 422.
- Contra la §4 (JUICIO, confianza media): el plan no impide elegir evidencia insuficiente cuando las dimensiones sí tienen material (por ejemplo, D1 presente con cita), y en ese caso el régimen que da la regla no se persiste ni se exporta. Eso lo registro como R3-1. No es bloqueante: la nota es obligatoria por esquema, las dimensiones y citas se exportan, y el investigador puede recalcular la regla afuera.

## Hallazgo nuevo

### MENOR

**R3-1. Evidencia insuficiente elegida con material citado no deja rastro del régimen de la regla.**
- Fuente: design D9 ("Única excepción: un régimen de `regimenes_exentos` ... que el codificador elige explícitamente"), spec estudio-codificacion "Régimen exento"; codebook v0 §4 punto 4 (insuficiente "cuando no hay material para aplicar la regla") y §6.6.
- Observación (razonada, no ejecutada): un codificador puede salir de la regla eligiendo evidencia insuficiente aunque haya dimensiones `presente` con cita. Queda un régimen que la §4 no contempla para ese caso, y en la exportación no figura qué habría dado la regla.
- Impacto: posible inflación de "insuficiente" en la referencia, detectable solo si se recalcula afuera.
- Disposición sugerida, sin replanificar: calcular y exportar siempre `regimen_regla` cuando las dimensiones que la regla usa estén completas, también si se eligió el exento. Opcionalmente, devolver una advertencia en el guardado si se elige exento con alguna dimensión que tenga cita. Un caso más en 3.2 y una columna más en 10.1. Si no se hace en construcción, queda como DEUDA del change.

## JUICIO

Autor: plan-reviewer. Comparación: hallazgos de los intentos 1 y 2 contra los artefactos del intento 3, el codebook v0 §4 y §7, y el código en b32e621.

- El plan es internamente consistente: no encontré contradicciones nuevas entre proposal, design, specs y tasks (confianza alta, lectura de las secciones tocadas y `rg` de restos de la variante anterior).
- Las tareas con comportamiento nuevo (3.2, 7.1, 7.3, 6.1) tienen RED identificable por aserción y mutantes declarados para las aserciones de datos y seguridad, como exige CRITICAL (confianza alta).
- Un visto bueno de este rol no reemplaza la aprobación humana. Quedan defaults del orquestador sin confirmar (preguntas 5 y 6) y las preguntas 1 y 2, que bloquean el alta de codificadores externos en producción, aunque no la construcción.

## SUPOSICIÓN

- Que la diferencia de hash de tasks se debe solo al bloque de orquestación.
- Siguen sin verificar en producción: que el email de Clerk sea verificado, la configuración de `REQUIRE_GATEWAY_SIGNATURE`, el tiempo de carga de 150 episodios contra 120 s y cuántos episodios de la muestra están `paused` o `integrity_compromised`. Todo está en Workflow follow-up o en la tarea 7.1.
- D4b y D10b son diseño razonado; su comportamiento recién se prueba en construcción (6.3, 7.1, 8.2).

## Fuentes leídas

- Artefactos del change (secciones listadas en E3-3) y proposal `## Aprobación`.
- Codebook v0 §4, §6 y §7 (mismo sha `8c20baf7...` que en el intento 1).
- `informes/propose-2-plan-reviewer.md` (propio) y `informes/propose-3-planner.md` (líneas 1-40).

## Contaminación por informes ajenos

Leí `informes/propose-3-planner.md` después de verificar los artefactos y redactar R3-1. De ahí tomé solo los hashes declarados (para la nota sobre tasks). El insumo del planner es mi informe del intento 2, así que comparto origen con sus correcciones; las verifiqué sobre los artefactos, no sobre su tabla. Misma familia de modelo. No consulté Engram.
