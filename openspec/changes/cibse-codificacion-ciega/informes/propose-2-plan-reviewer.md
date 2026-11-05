# Informe propose-2-plan-reviewer

- Change: `cibse-codificacion-ciega`
- Rol: plan-reviewer (propose, intento 2: verificación de la corrección)
- Ejecutor: subagente nativo de Claude Code (role plan-reviewer), familia Anthropic, la misma que el planner. Sin independencia de proveedor.
- Revisión revisada: `origin/main @ b32e621f992a`, rama `feat/cibse-codificacion-ciega`, artefactos sin commitear. sha256 (12 primeros) de lo que revisé: proposal `af9eeeda4279`, design `96981e2f4fa0`, tasks `1af8c586ddd5`, specs: codebook-versionado `c713711144ee`, entrenamiento-calibracion `0893de58fbd3`, estudio-codificacion-acceso `6933102dd2a9`, estudio-codificacion-exportacion `e924c0fab0c2`, estudio-codificacion `ba6b55497228`, traza-ciega-episodio `354306dd7959`.
- Nota: el planner declara tasks `6c405ca0f707`; yo leí `1af8c586ddd5`. Lo atribuyo a la edición posterior del bloque "Estado de orquestación" por el orquestador (líneas 5-12); no tengo copia previa para diffear (SUPOSICIÓN).
- Fecha: 2026-11-04. No edité el plan ni código.

## Veredicto

**APTO CON CORRECCIONES** (equivale a CORRECCIONES). De los 20 hallazgos del intento 1: 19 resueltos, 1 parcial (B-1). Nuevos: 2 BLOQUEANTE, 0 MAYOR, 5 MENOR. `## Aprobación` sigue vacía (solo el comentario reservado): verificado.

Clasificación: sigue **CRITICAL**.

## EVIDENCIA (chequeos de este intento)

| # | Comando / lectura | Momento | Resultado |
|---|---|---|---|
| E2-1 | `sha256sum` de los 9 artefactos | 04/11 ~11:15 | hashes de arriba |
| E2-2 | Lectura completa de proposal (40-83), design, tasks y los 6 specs | 04/11 | base de la tabla de disposición |
| E2-3 | `uv run pytest apps/analytics-service/tests/unit/test_cohort_slopes_batch.py packages/platform-ops/tests/test_real_datasources.py packages/platform-ops/tests/test_ghost_episodes_exclusion.py packages/platform-ops/tests/test_language_segmentation.py -q` | 2026-11-04T11:21:19-03:00 | `36 passed` (con `test_language_segmentation.py`, que el planner no abrió; la línea de base de 25 era sin él) |
| E2-4 | `uv run pytest apps/analytics-service/tests/unit/test_pedagogia_distribucion.py -q` | idem | `2 passed` |
| E2-5 | `uv run pytest apps/analytics-service -q` | idem | `182 passed, 18 warnings in 92.15s`: el comando de 2.1/8.4 ahora selecciona tests reales |
| E2-6 | `rg` en `apps/classifier-service/tests/integration/test_submit_review_concurrency_db.py` | idem | existe, 3 tests concurrentes: el patrón citado por 8.2 es real |
| E2-7 | `rg` de imports en `apps/classifier-service/src/classifier_service/models/__init__.py` | idem | usa `JSONB`, `PgUUID`, `UniqueConstraint`, `Index` simples: la regla "nada exclusivo de Postgres en la metadata" de D1 es coherente con el módulo |
| E2-8 | Lectura `apps/ctr-service/src/ctr_service/workers/partition_worker.py:677-728` | b32e621 | **`episodio_abandonado` deja el episodio en `estado = "paused"` (ADR-055)**, no `closed`; actividad posterior lo vuelve `open` (reanudación); `episodio_reabierto` es una rama inerte: la reapertura docente fue retirada el 2026-06-19 |
| E2-9 | Lectura `packages/contracts/.../ctr/events.py:129-135` | b32e621 | `reason` de abandono: `timeout`, `beforeunload`, `explicit`, `distraccion_pestana` |
| E2-10 | `rg -n 'latido' event_labeler.py` | b32e621 | `lectura_enunciado` es un latido periódico con `duration_seconds` (v1.3.0) |
| E2-11 | Conteo `estrato|origen` de la muestra | 04/11 | 100 `gris`, 50 `pasiva_sobreuso`; ninguna columna indica abandono, no se puede saber desde el CSV cuántos están `paused` |

Lo reusé sin reejecutar porque los archivos no cambiaron: E1 a E22 del intento 1 (hash de muestra y codebook, lecturas de gateway, CTR y web-teacher). No ejecuté Postgres, CTR, Clerk ni producción.

## Disposición de los hallazgos del intento 1

| Hallazgo | Estado | Dónde se verificó | Comentario |
|---|---|---|---|
| B-1 coherencia régimen/dimensiones | **PARCIAL** | design D9; spec estudio-codificacion ("Advertencia de coherencia", "Cierre"); codebook-versionado ("Regla de régimen válida"); tasks 3.1, 3.2, 8.1 | La gramática expresa bien la §4 (reflexiva y pasiva tal como están, superficial por defecto, insuficiente exenta), la advertencia y el 422 son efectivos y tienen tests nombrados. Pero la salida "disiento de la regla" deja cerrar con un régimen distinto al de la regla, y eso contradice la §7. Ver N-2 |
| M-1 evidencia no fija | Resuelto | D4b, D2 (trigger sobre columnas de evidencia), spec "Evidencia acotada al tope" y "Evidencia fija desde la carga", tasks 6.1 (`seq_tope`), 6.3 (evento extra) | Efectivo. E2-8 muestra que la reapertura docente está retirada, pero la reanudación tras abandono sigue viva, así que el tope sigue haciendo falta |
| M-2 lista blanca vs codebook | Resuelto (con decisión pendiente) | D4 tabla `traza_v1`, párrafo humano/juez, proposal pregunta 5, spec traza (pega sin preview, fin abandonado sin motivo) | Default aplicado y escrito como pregunta. Ver N-6 sobre latidos |
| M-3 modo restringido | Resuelto | D13, spec acceso ("Entrada al panel"), task 11.2 con test de root y `docenteOnboarding.test.tsx` | |
| M-4 disponibilidad del panel | Resuelto | D13 (`ok/error`), spec "Disponibilidad del panel", task 11.2 (7 casos), Migration Plan 3 | |
| M-5 consumidores de models | Resuelto | tasks 1.1, 2.1, 8.4, 13.2; D1 "Compatibilidad con SQLite" | Reejecutado: 36 + 2 + 182 passed (E2-3 a E2-5). La línea de base de 1.1 dice "25 passed sin `test_language_segmentation.py`"; con él son 36 |
| M-6 concurrencia | Resuelto (diseño) | D10b, spec "Operaciones concurrentes serializadas" con resultados válidos, task 8.2 con mutante | Razonado, no probado; los escenarios discriminan |
| M-7 identidad por email | Resuelto | D3, spec acceso ("Procedencia", "Membresía atada"), task 4.1 mutantes (d) y (e) | Riesgo residual del primer uso declarado |
| M-8 anclas de versión congelada | Resuelto | D2 (INSERT/UPDATE/DELETE), D8, spec "El sha cubre las anclas", tasks 2.2 y 5.1 | Ver N-4 sobre la forma canónica |
| m-1 unidad de cita | Resuelto | D4 localizadores por tipo, spec "Turnos del chat", "Ejecuciones numeradas" | |
| m-2 tiempo absoluto | Resuelto | `t_seg`, `ts` en claves prohibidas | |
| m-3 formato de respuestas | Resuelto | D9 `{clave:{valor,cita}}`, D12 columnas | |
| m-4 estado del episodio | **Resuelto pero mal calibrado por mi sugerencia** | D6, D11, specs | Exigir `closed` excluye abandonados. Ver N-1: el error de origen es mío (intento 1, m-4), que asumí que "terminado" era `closed` sin leer ADR-055 |
| m-5 colisión de ruta | Resuelto | D3 patrón y lista reservada, escenario 422 | |
| m-6 re-alta | Resuelto | D3, escenario "Re-asignación después de revocar" | |
| m-7 orden reproducible | Resuelto | D7 rango de sha256, escenario "Orden recomputable", task 7.2 | Ver N-5 |
| m-8 logs con PII | Resuelto | D3, specs acceso y exportación | |
| m-9 tests con dicts crudos | Resuelto | task 6.1, escenario "Campos fuera del contrato" | |
| m-10 esquema v0 y límites | Resuelto | Workflow follow-up, task 12.2, KB impact | |
| m-11 KB | Resuelto | proposal KB impact, task 12.3 | |

## Hallazgos nuevos

### BLOQUEANTE

**N-1. La muestra rechaza episodios abandonados, que la propia traza prevé mostrar.**
- Fuente: design D6 y D11 (`estado == "closed"`, `open` y `paused` se rechazan), spec estudio-codificacion "Episodio inexistente o no cerrado", entrenamiento-calibracion (anclas), task 7.1; contra spec traza-ciega-episodio "Fin abandonado", design D4 (`episodio_abandonado` como "fin: abandonado") y E2-8 (abandono deja `paused`, ADR-055).
- Observación (por lectura de código, no ejecutada contra producción): un episodio abandonado y no retomado queda `paused`; la carga, que es todo o nada, rechazaría la muestra entera si contiene uno solo. El codebook §4 nombra el "abandono tras baja implicación" como marcador de pasiva, así que es esperable que el estrato `pasiva_sobreuso` tenga abandonados. No consulté cuántos hay (E2-11).
- Impacto: la carga de los 150 reales puede ser inviable; contradicción interna del plan. Origen: mi sugerencia m-4 del intento 1.
- Disposición sugerida (planner): definir "terminado" por la cadena y no solo por el `estado`: aceptar `closed` y `paused` cuyo último evento sea `episodio_abandonado`; rechazar `open` e `integrity_compromised` (o decidir este último con el investigador). Como un `paused` puede reanudarse (E2-8), la evidencia fija de D4b ya cubre ese caso; agregar escenario "abandonado y reanudado después de la carga no cambia la traza". Escenario y caso en 7.1 y 7.3 con un episodio abandonado.

**N-2. "Disiento de la regla" contradice la §7 del codebook v0.**
- Fuente: codebook v0 §7 ("Si el codificador cree que la regla da un resultado injusto en un caso, lo codifica igual según la regla y lo explica en las notas"); contra design D9 (cierre permitido con etiqueta incoherente si `disiente_regla` y notas), spec estudio-codificacion "Incoherente con desacuerdo declarado", tasks 3.2 y 8.1, proposal pregunta 6 (que no menciona la contradicción).
- Observación: con el diseño actual, el régimen exportado de un ítem con desacuerdo es el que el codificador cree justo, no el de la regla. El codebook pide lo contrario: régimen según la regla y el desacuerdo en notas. Además la exportación no trae el régimen que da la regla, así que hay que recalcularlo afuera para usar esos ítems.
- Impacto: la variable sobre la que se calcula el κ contra C0/C1 puede apartarse del codebook en los ítems de desacuerdo, que son justo los de frontera. Es la misma clase de defecto que B-1.
- Disposición sugerida (decisión humana, la presenta el planner): (a) alinear con la §7: el régimen tiene que ser coherente para cerrar; `disiente_regla` + notas + un campo opcional `regimen_propuesto` registran el desacuerdo sin cambiar el régimen; o (b) mantener el diseño y cambiar el texto de la §7 del codebook antes de congelar, con decisión fechada. En ambos casos exportar `regimen_regla` junto al régimen. La pregunta 6 tiene que decir explícitamente que la variante actual contradice la §7. Test en 3.2 según la opción elegida.

### MENOR

- **N-3. `traza_version` de anclas creadas antes de la muestra.** D1 fija `traza_version` en el estudio "al cargar la muestra", pero las anclas (y el entrenamiento) existen antes. No está definido contra qué versión se valida la traza de un ancla ni qué se guarda en la respuesta de entrenamiento si la muestra todavía no se cargó. Disposición: fijar `traza_version` en el alta del estudio o en cada ancla y decirlo en D4b.
- **N-4. Forma canónica de las anclas en el sha.** D8 dice "anclas ordenadas por `item_id` sin ids internos": `item_id` es un UUID aleatorio, así que dos versiones con anclas idénticas dan sha distinto, y no queda claro si entran `episode_id` y las columnas de evidencia fija. Disposición: lista explícita de campos (por ejemplo `uso, orden, episode_id, respuesta_esperada, explicacion_md, consensuado_por, seq_tope, chain_hash_tope`) y orden por `(uso, orden, episode_id)`; el test literal de 5.1 lo fija.
- **N-5. Serialización de `item_id` en el hash del orden.** D7 usa `sha256(f"{semilla}:{item_id}")` sin fijar el formato del UUID (minúsculas con guiones) ni la codificación; el escenario "Orden recomputable" depende de eso. Disposición: escribirlo en D7 y en el ADR.
- **N-6. Latidos de lectura.** `lectura_enunciado` es un latido periódico (E2-10): incluido tal cual, puede dominar la traza y el localizador global. Disposición: agrupar latidos consecutivos en un solo elemento "lectura de la consigna (N s)" con su propio localizador, o decidir mostrarlos sueltos; escenario en traza-ciega-episodio.
- **N-7. Línea de base desactualizada en 1.1.** Dice "25 passed sin `test_language_segmentation.py`"; con los 4 archivos son 36 (E2-3). Disposición: corregir el número o quitarlo, para que el constructor no lo tome como esperado.

Observación sin severidad: el bloque "Estado de orquestación" de tasks.md dice en "Próxima acción" que el planner corrige, lo cual ya pasó. Es del orquestador.

## JUICIO

Autor: plan-reviewer. Comparación: hallazgos del intento 1 y decisiones del orquestador contra los artefactos corregidos, el codebook v0 §4 y §7, y el código en b32e621.

- La corrección es sustantiva y no cosmética: cada disposición aparece en design, spec y tarea con test y, donde correspondía, mutante (confianza alta).
- No encontré contradicciones nuevas entre proposal, design, specs y tasks salvo N-1. Con el codebook, la única es N-2 (confianza alta en la lectura de §7; la decisión es humana).
- N-1 la introduje yo con m-4 en el intento 1: la registro como defecto nuevo sin atenuarlo.
- Las tareas nuevas o modificadas (2.2 con INSERT, 3.2 con casos de regla, 6.3 con evento extra, 8.2 de concurrencia, 11.2 con 7 casos) tienen RED identificable por aserción o por mutante declarado, y los comandos de regresión seleccionan tests reales (E2-3 a E2-5).

## SUPOSICIÓN

- Que la diferencia de hash de tasks.md se debe solo al bloque de orquestación; sin copia previa no lo verifiqué.
- Que la muestra real contiene episodios `paused`; no consulté producción (E2-11).
- Que `integrity_compromised` como estado aparece en S2 2026; no consultado.
- M-6 y D4b son diseño razonado; nada de esto se ejecutó porque no hay código.

## Fuentes leídas

- Artefactos del change completos (proposal 40-83 y encabezado ya conocido, design, tasks, 6 specs).
- Codebook v0 §4 y §7 (ya leído completo en el intento 1, sin cambios: mismo sha `8c20baf7...`).
- `apps/ctr-service/src/ctr_service/workers/partition_worker.py:674-730`; `packages/contracts/src/platform_contracts/ctr/events.py:129-137`; `apps/classifier-service/src/classifier_service/services/event_labeler.py` (búsqueda de latido); `apps/classifier-service/src/classifier_service/models/__init__.py` (imports y table_args); `apps/classifier-service/tests/integration/test_submit_review_concurrency_db.py` (nombres de tests); muestra (conteo de estratos).
- `informes/propose-1-plan-reviewer.md` (propio) y `informes/propose-2-planner.md`.

## Contaminación por informes ajenos

Leí `informes/propose-2-planner.md` después de verificar los artefactos y redactar los hallazgos N-1 a N-7. De ahí tomé solo el hash declarado de tasks (para la nota de discrepancia) y su SUPOSICIÓN de que los abandonados quedan `closed`, que yo ya había refutado leyendo el código (E2-8). El insumo del planner es mi propio informe del intento 1, así que comparto origen con sus correcciones; la verificación de este intento se hizo sobre los artefactos y el código, no sobre su tabla. Misma familia de modelo que el planner. No consulté Engram.
