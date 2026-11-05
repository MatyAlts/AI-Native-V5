# Informe propose-3-planner

- Change: `cibse-codificacion-ciega`
- Rol: planner (propose, intento 3, último permitido en este gate)
- Ejecutor declarado: subagente nativo de Claude Code (role planner), familia Anthropic, la misma que el plan-reviewer.
- Base: `origin/main @ b32e621`; artefactos sin commitear.
- Entrada: `informes/propose-2-plan-reviewer.md` leído entero; decisiones del orquestador del 04/11 (N-2/B-1 corregida: régimen siempre el de la regla, desacuerdo en `regimen_propuesto` con nota; N-1 según el reviewer; N-3 a N-7 según el reviewer, línea de base 36).
- No se tocaron el bloque "Estado de orquestación" de `tasks.md` (las ediciones se aplicaron solo después del encabezado `## Registro del planner`) ni los informes del reviewer.
- Revisión entregada (sha256, 12 primeros): proposal `ae2cede8d417`, design `d52a5b75d174`, tasks `fa5c49bbbbb2`, specs: codebook-versionado `ade6518708de`, entrenamiento-calibracion `8e5a3f55a496`, estudio-codificacion-acceso `d827a1c86fc9`, estudio-codificacion-exportacion `2716be974337`, estudio-codificacion `62183463233e`, traza-ciega-episodio `aa9a0c3ba14b`. El hash de tasks cambia si el orquestador edita su bloque.

## Disposición por hallazgo

| Hallazgo | Disposición aplicada | Dónde quedó |
|---|---|---|
| N-2 (y cierre de B-1) "disiento" contradice §7 | El `regimen` persistido es siempre el que deriva la regla sobre las dimensiones; único caso no derivado: régimen exento (evidencia insuficiente) elegido explícitamente. Un `regimen` no exento distinto del derivado, o con dimensiones incompletas, da 422. Desacuerdo: `regimen_propuesto` opcional con nota obligatoria; `disiente_de_regla` se deriva. Eliminados la bandera `incoherente`, la advertencia y el cierre con "disiento". Exportación con `regimen`, `regimen_propuesto`, desacuerdo derivado y notas. Con `reglas_regimen` vacía el codificador elige | design D1 (columnas), D9 ("Régimen según la regla"), D10, D11, D12, D13, Riesgos; specs estudio-codificacion ("Régimen derivado por la regla del codebook", "Régimen propuesto por desacuerdo con la regla", "Cierre de la codificación", escenario de reedición), entrenamiento-calibracion ("Respuesta con régimen propuesto"), exportación; tasks 2.1, 3.2 (casos y mutantes nuevos), 8.1, 9.1, 10.1, 11.1, 11.5, 11.6; proposal What Changes y pregunta 6 |
| N-1 abandonados rechazados | "Terminado" = `closed`, o `paused` con `episodio_abandonado` como último evento de cierre. Se rechazan `open`, `paused` sin abandono y, por default, `integrity_compromised` (pregunta al investigador). La evidencia fija de D4b cubre la reanudación posterior | design Context, D4b, D6, D11, Riesgos; specs estudio-codificacion (escenarios "Episodio inexistente o no terminado", "Episodio abandonado en la muestra", "Evento agregado después de la carga" reescrito como reanudación), entrenamiento-calibracion; tasks 7.1 (CSV sintético con un `paused` abandonado aceptado y caso "abandonado y reanudado después de la carga no cambia la traza"), 7.3; proposal pregunta 5 |
| N-3 `traza_version` de anclas previas a la muestra | `traza_version` se fija en el alta del estudio y rige muestra, anclas, entrenamiento y etiquetas | design D1, D4b; specs estudio-codificacion-acceso (escenario de alta), estudio-codificacion ("Evidencia fija desde la carga"), traza-ciega-episodio ("Versión de lista blanca distinta"); task 5.1 |
| N-4 forma canónica de anclas en el sha | Lista explícita de campos `uso, orden, episode_id, respuesta_esperada, explicacion_md, consensuado_por, seq_tope, chain_hash_tope`, sin `item_id`, orden `(uso, orden, episode_id)` | design D8; spec codebook-versionado (escenario "Anclas idénticas dan el mismo sha"); task 5.1 (tres tests de sha) |
| N-5 serialización del orden | `sha256((str(semilla) + ":" + item_id).encode("utf-8"))`, semilla decimal sin relleno, UUID en minúsculas con guiones (36 caracteres), rango ascendente del hex; se copia al ADR | design D7; tasks 7.2 (caso con UUID en mayúsculas en la entrada), 12.1 |
| N-6 latidos de lectura | Latidos `lectura_enunciado` consecutivos, sin otro evento incluido entre ellos, se agrupan en un elemento con la suma de duraciones y localizador `lectura k` | design Context, D4 (tabla y localizadores); spec traza-ciega-episodio (escenario "Latidos de lectura agrupados" y localizador por tipo); tasks 6.1, 11.4 |
| N-7 línea de base | 36 passed con los 4 archivos (E2-3 del reviewer) | task 1.1; design Context |

N-7 también se corrigió en `design.md` Context (la línea de los tests con `create_all` decía 25; ahora 36).

## EVIDENCIA

| Comando / lectura | Momento | Resultado |
|---|---|---|
| Lectura completa de `informes/propose-2-plan-reviewer.md` | 04/11 | 2 BLOQUEANTE (N-1, N-2), 5 MENOR (N-3 a N-7), B-1 parcial |
| `rg` de `incoherente`, `disiente_regla`, `advertencia` en proposal, design, tasks y specs tras editar | 04/11 | solo quedan en el bloque de orquestación de tasks, en la frase de tasks 2.1 que dice que no hay esas columnas, y en design D9, donde se aclara que no existen |
| `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T11:27:44-03:00 | `Change 'cibse-codificacion-ciega' is valid` |
| `rg -c "—"` sobre los artefactos | 04/11 | sin em dashes |

## JUICIO

Autor: planner. Comparación: hallazgos del intento 2 y decisiones del orquestador contra los artefactos del intento 2.

- N-2 queda alineado con la letra del v0 §7: no puede existir una etiqueta cuyo régimen contradiga la regla, y el desacuerdo queda registrado sin tocar la variable del κ (confianza alta).
- Con el régimen derivado, el formulario ya no ofrece elegir régimen salvo los exentos o un esquema sin regla. Eso cambia la experiencia del codificador respecto del piloto; la consecuencia está en la tarea 11.5 (confianza alta).
- N-1: la definición de "terminado" se apoya en la lectura del reviewer de `partition_worker.py` (E2-8), que no reverifiqué; si en datos reales hay `paused` por otra causa con abandono como último cierre, el criterio los acepta, lo que es coherente con "abandonado y no retomado" (confianza media).
- Todos los cambios de spec tienen un caso de test en la tarea correspondiente (confianza alta).

## SUPOSICIÓN

- Que `episodio_abandonado` deja `paused` y la reapertura docente está retirada: tomado de E2-8 del reviewer, no leído por mí.
- Que el investigador acepta rechazar episodios con `integrity_compromised`: default declarado como pregunta, no confirmado.
- No se ejecutó código ni tests: no hay implementación.

## Fuentes leídas

- `informes/propose-2-plan-reviewer.md` (completo); artefactos propios del intento 2.
- `/home/juanisarmiento/Proyectos/AI-Native/codigo/CLAUDE.md` (en contexto).

## Contaminación por informes ajenos

Este intento parte del informe del plan-reviewer, que es su insumo por diseño. Usé sin reverificar E2-3 (36 passed) y E2-8 (estado `paused` tras abandono), marcados en SUPOSICIÓN. No consulté Engram ni otros informes.
