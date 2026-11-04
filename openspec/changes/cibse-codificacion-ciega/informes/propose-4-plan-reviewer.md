# Informe propose-4-plan-reviewer

- Change: `cibse-codificacion-ciega`
- Rol: plan-reviewer, verificación del cambio de alcance decidido por el humano (Juani, 04/11/2026: P2, P4, P10, P12 = B) y del menor R3-1. No es un intento fallido de gate.
- Ejecutor: subagente nativo de Claude Code (role plan-reviewer), familia Anthropic, la misma que el planner.
- Revisión revisada: `origin/main @ b32e621` (código sin cambios: `git status` solo muestra `openspec/` y el `scripts/backfill-attestations.py` preexistente). sha256 (12 primeros): proposal `37a59893694b`, design `32c88f7d1742`, tasks `3da4401611b8`, specs: codebook-versionado `ade6518708de`, entrenamiento-calibracion `a2db7a1ab33a`, estudio-codificacion-acceso `d827a1c86fc9`, estudio-codificacion-exportacion `ff8a33476668`, estudio-codificacion `68483d8a2711`, traza-ciega-episodio `e0be95216dc7`. Coinciden con propose-5-planner salvo tasks (`faefbecc656a` según él): el bloque de orquestación lo edita el orquestador (SUPOSICIÓN).
- Fecha: 2026-11-04. No edité el plan ni código.

## Veredicto

**APTO CON CORRECCIONES menores. No hay bloqueantes.** El alcance quedó en classifier-service y web-teacher. La carga, el hash, la cobertura, las alertas, la revisión obligatoria y el bloqueo de todo el estudio están especificados, tienen escenario y tarea con mutante, y no rompen la evidencia fija ni el ciego. R3-1 está resuelto. `## Aprobación` sigue vacía.

Hallazgos nuevos: 1 MAYOR (A4-1) y 2 MENOR. Ninguno exige cambiar código ni specs: A4-1 se corrige con una instrucción en Workflow follow-up para la consulta SQL que prepara el orquestador fuera del plan. **Se puede pedir la aprobación humana**, con A4-1 agregado al follow-up o aceptado explícitamente como riesgo.

## EVIDENCIA

| # | Comando / lectura | Momento | Resultado |
|---|---|---|---|
| E4-1 | `sha256sum` de los 9 artefactos; `eza specs` | 04/11 ~11:40 | hashes de arriba; 6 specs, no existe `academic-enunciados-lectura` |
| E4-2 | `rg -n -i 'academic'` en proposal, design, tasks y specs | 04/11 | proposal 43 ("No se tocan") y 71 (P12 "No se toca"); design 3, 18 (descripción del modelo de origen), 32 (Non-Goal), 82 (alternativa rechazada), 209 y 218 (D14: no se toca, alternativa rechazada), 220 (riesgo de la carga manual); tasks 6 y 24 (decisión y retiro). Specs: 0. **Ninguna mención implica modificar academic-service** |
| E4-3 | `rg 'apps/(academic|tutor|ctr|api-gateway|analytics)-service|casbin|estudio_lector|## 14'` | 04/11 | solo rutas de lectura (Context), comandos de regresión de analytics y la nota del retiro en tasks 24. Ninguna tarea escribe fuera de `apps/classifier-service` y `apps/web-teacher` (más docs) |
| E4-4 | Lectura de design D14 completo, D1 (`estudio_enunciado`), D2 (triggers), D9 (`regimen_regla`), D12; specs estudio-codificacion ("Carga manual de enunciados con cobertura", "Revisión de enunciados antes de codificar", régimen), traza-ciega-episodio ("Enunciado del episodio en la traza"), entrenamiento-calibracion ("Enunciado de las anclas"), exportación; tasks 2.1, 2.2, 3.2, 6.3, 7.0, 7.2b, 7.3, 10.1, 11.8, Workflow follow-up | 04/11 | base de la verificación |
| E4-5 | Lectura `apps/academic-service/src/academic_service/services/ejercicio_service.py:58-75` y `packages/contracts/src/platform_contracts/academic/ejercicio.py:201-209` | b32e621 | `EjercicioService.update` pisa atributos en el lugar; `EjercicioUpdate` admite `enunciado_md`. No hay versión ni `updated_at` (el `TimestampMixin` de `models/base.py:45-47` trae `created_at` y `deleted_at`). Cada cambio queda en `AuditLog` con `action="ejercicio.update"` y `changes.after` |
| E4-6 | `rg` en `services/tarea_practica_service.py` | b32e621 | una TP `published` no se edita (409; línea 268-272): su enunciado es estable |
| E4-7 | `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T11:45:30-03:00 | `Change 'cibse-codificacion-ciega' is valid` |
| E4-8 | `awk '/## Aprobación/,0' proposal.md` | idem | solo el comentario reservado: vacía |
| Reusado | E3-5 (38 passed) y E2-5 (182 passed) | 04/11 | el código no cambió (`git rev-parse` = b32e621), los resultados siguen valiendo |

## Verificación pedida

1. **Alcance** (EVIDENCIA E4-2, E4-3): solo classifier-service y web-teacher, más documentación. proposal Impact (41-43) y "No se tocan" lo dicen; no queda capability, tarea, Casbin ni deploy de academic-service.
2. **Carga, hash, cobertura, alertas y revisión** (E4-4):
   - Especificado y testeable. Funciones puras en 7.0, con CSV con comillas y saltos de línea, sha literal con tildes, alertas por patrón y mutantes. Endpoints en 7.2b, con 403 para codificador, carga parcial, 409 sobre revisado, reemplazo antes de revisar con log de hashes y mutante "bloquear solo el ítem". Panel en 11.8.
   - Evidencia fija (M-1): sin contradicción. `problema_id` y `ejercicio_id` se fijan con la evidencia del ítem y quedan protegidos por trigger (2.2). Lo revisado es inmutable (D2, trigger UPDATE/DELETE). Los hashes original, mostrado y de archivo se exportan.
   - Ciego: sin contradicción. La traza agrega `enunciado: {tp_md, ejercicio_md}` sin ids ni hashes. Excluye título, código, fechas, rúbrica, casos de prueba y material del tutor (spec traza, D14). El texto es lo que el alumno tenía delante, así que no revela decisiones de la máquina.
   - Rúbrica, pistas y tests: el plan no los toma de columnas, pero el CSV trae texto libre. Si la consulta exporta la columna equivocada o el docente pegó tests en la consigna, el sistema no lo detecta. Ver A4-2.
3. **Bloqueo de todo el estudio** (JUICIO, confianza alta): está bien justificado en D14 (misma evidencia para los dos codificadores en los 150, cierre que exige los 150, carga única de bajo costo). Tiene escenario ("Codificar con un enunciado faltante", spec estudio-codificacion 93-95) y mutante (7.2b). La asimetría con las anclas (bloqueo por ancla porque el entrenamiento no es obligatorio, P10) es coherente y tiene escenario propio.
4. **R3-1**: resuelto. D9 guarda `regimen_regla` siempre que sea calculable, también con exento. Escenario en spec estudio-codificacion:166, caso y mutante en 3.2, columna y caso en 10.1, export en D12 y spec de exportación.
5. **Contradicciones y Aprobación**: no encontré contradicciones nuevas entre proposal, design, specs y tasks (ver A4-3 por una omisión). Aprobación vacía (E4-8).

## Hallazgos nuevos

### MAYOR

**A4-1. El enunciado de un ejercicio del banco se edita en el lugar: la exportación puede traer un texto distinto del que vio el alumno.**
- Fuente: E4-5 (código de academic-service, no runtime); design D14 "Riesgo propio de la carga manual" (genérico, no nombra este mecanismo); Workflow follow-up (la consulta la prepara el orquestador sin criterio de versión).
- Observación: las TP publicadas son estables (E4-6), pero `Ejercicio.enunciado_md` se pisa con `update` y no hay versión ni `updated_at`. Una consulta que lea el valor actual muestra la consigna de hoy, no la de la fecha del episodio. No verifiqué si algún ejercicio de la muestra se editó después de sus episodios.
- Impacto: es el mismo tipo de falla que M-1 (evidencia fija), aplicada al enunciado. El sistema lo fija bien una vez cargado, pero puede fijar el texto equivocado sin que nadie lo vea.
- Disposición sugerida, sin cambiar código ni specs: agregar en Workflow follow-up y en el runbook que la consulta (a) detecte en `audit_log` los `ejercicio.update` con `changes.after.enunciado_md` posteriores al primer `opened_at` de los episodios de la muestra y de las anclas que usan ese ejercicio, y (b) en ese caso exporte el texto vigente a la fecha del episodio, reconstruido desde el `audit_log`, o lo marque para que el investigador lo resuelva en la revisión. Declararlo en el método del paper junto con la carga manual.

### MENOR

- **A4-2. Las alertas no cubren rúbrica, tests ni pistas.** D14 y 7.0 alertan por fechas, emails, docentes, comisiones y horarios, pero no por material que no debe verse: palabras como "rúbrica", "test", `assert`, "salida esperada" de casos ocultos, "pista", "solución" o JSON con `input`/`expected`. Disposición: sumar esos patrones a `alertas_enunciado` con un caso en 7.0, y agregar a la revisión del investigador (follow-up, línea 117) "confirmar que no hay rúbrica, tests ocultos ni pistas del tutor".
- **A4-3. Impacto y KB no nombran lo nuevo de D14.** proposal Impact de classifier-service (línea 41) no menciona la tabla `estudio_enunciado` ni los endpoints de enunciados; el Knowledge Base Impact (ADR-063, runbook) no incluye la carga manual de enunciados ni su riesgo de fidelidad, aunque el Migration Plan paso 4 y D14 sí. Disposición: agregarlos a Impact, a la lista de decisiones del ADR-063 y al runbook.

Observación sin severidad: P2 dice "dos profesores que no conocen los episodios". La recomendación técnica era además que no sean docentes de las comisiones de la muestra, porque verían la etiqueta de la máquina en otras pantallas. Conviene que la aprobación lo confirme de forma explícita.

## JUICIO

Autor: plan-reviewer. Comparación: decisiones del humano del 04/11 y R3-1 contra los artefactos de la revisión 5 y el código de academic-service en b32e621.

- El retiro de academic-service es completo y limpio (confianza alta).
- El diseño de D14 es consistente con la evidencia fija, el ciego y la inmutabilidad ya revisados (confianza alta); su punto débil es la fidelidad del texto, que depende de la consulta fuera del plan (A4-1, confianza alta en el mecanismo, desconocida en la frecuencia real).
- El plan está en condiciones de pasar a la aprobación humana. Mi visto bueno no la reemplaza: la aprobación tiene que nombrar el nivel (CRITICAL recomendado), el alcance con D14 y responder las preguntas 5 y 6 (defaults del orquestador) y, antes del alta de externos, la 1.

## SUPOSICIÓN

- Que la diferencia de hash de tasks se debe solo al bloque de orquestación.
- Que existen ejercicios del banco editados después de episodios de la muestra: posible por código, no consultado en producción.
- Que el investigador revisará los enunciados con el criterio pedido; el sistema solo puede exigir que los marque como revisados.
- No reejecuté las suites: el código no cambió desde E3-5 y E2-5.

## Fuentes leídas

- Artefactos del change (secciones de E4-4), proposal completo de 40 a 83.
- `apps/academic-service/src/academic_service/services/ejercicio_service.py:50-100`, `models/base.py:45-47`, `services/tarea_practica_service.py` (búsqueda), `packages/contracts/src/platform_contracts/academic/ejercicio.py:201-209`.
- `informes/propose-4-planner.md` y `informes/propose-5-planner.md` (búsquedas y encabezados), después de redactar los hallazgos.

## Contaminación por informes ajenos

Leí los informes 4 y 5 del planner después de verificar los artefactos y redactar A4-1 a A4-3. Tomé de ellos solo los hashes declarados y la confirmación de que no trataron la edición en el lugar de `Ejercicio` (A4-1 es independiente). Su insumo incluye mi R3-1. Misma familia de modelo. No consulté Engram.
