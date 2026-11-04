# Informe propose-2-planner

- Change: `cibse-codificacion-ciega`
- Rol: planner (propose, intento 2: corrección)
- Ejecutor declarado: subagente nativo de Claude Code (role planner), familia Anthropic, la misma que el plan-reviewer.
- Base: `origin/main @ b32e621`; artefactos sin commitear.
- Entrada: `informes/propose-1-plan-reviewer.md` leído entero, más decisiones del orquestador del 04/11 (B-1 opción a; M-1 evidencia fija y `traza_version`; M-2 default de evidencia ampliada; M-3 a M-8 según el reviewer; menores m-1 a m-11 con m-1 por localizador por tipo y m-10 como follow-up más runbook).
- No se tocaron el bloque "Estado de orquestación" de `tasks.md` (verificado con `diff` de las 14 primeras líneas antes de reescribir) ni el informe del reviewer.
- Revisión entregada (sha256, 12 primeros): proposal `af9eeeda4279`, design `96981e2f4fa0`, tasks `6c405ca0f707`, specs: codebook-versionado `c713711144ee`, entrenamiento-calibracion `0893de58fbd3`, estudio-codificacion-acceso `6933102dd2a9`, estudio-codificacion-exportacion `e924c0fab0c2`, estudio-codificacion `ba6b55497228`, traza-ciega-episodio `354306dd7959`.

## Disposición por hallazgo

| Hallazgo | Disposición aplicada | Dónde quedó |
|---|---|---|
| B-1 coherencia régimen/dimensiones | Opción (a), decidida por el orquestador. `reglas_regimen` en el meta-esquema: lista ordenada de reglas `{regimen, condicion}` en forma conjunción de disyunciones de átomos `{dimension, en, con_cita}`, `regimen_por_defecto`, `regimenes_exentos`. Al guardar: advertencia con régimen esperado. Al cerrar: 422 salvo `disiente_regla` con nota; se persiste y exporta `incoherente`. También en entrenamiento. Sin texto del codebook en el código. Default registrado como pregunta 6 con la alternativa (b) | design D9; specs estudio-codificacion ("Advertencia de coherencia al guardar", "Cierre de la codificación"), codebook-versionado ("Validación del esquema", escenarios de regla), entrenamiento-calibracion ("Respuesta incoherente con la regla"), exportación; tasks 3.1, 3.2 (incluye el caso D1/D2 presentes, D4 interlocutor, régimen superficial), 8.1, 9.1, 10.1, 11.5; proposal Preguntas 6 |
| M-1 evidencia no fija | Al cargar muestra o ancla se guardan `seq_tope`, `chain_hash_tope`, `events_count_carga`, `last_chain_hash_carga`, `estado_carga`; se sirven solo eventos hasta el tope; tope alterado da 409 `evidencia_alterada` con log; `TRAZA_VERSION = "traza_v1"` fijada en el estudio y guardada en cada etiqueta, respuesta de entrenamiento y exportación; versión distinta da 409. Triggers impiden modificar las columnas de evidencia | design D1, D2, D4b; specs traza-ciega-episodio ("Evidencia acotada al tope"), estudio-codificacion ("Evidencia fija desde la carga"), entrenamiento-calibracion ("Evidencia del ancla fija"); tasks 2.1, 2.2, 6.1, 6.3 (caso "evento agregado después de la carga no aparece"), 7.1, 7.3 |
| M-2 lista blanca vs codebook | Default del orquestador: se incluyen `lectura_enunciado`, `copia_intentada`, `pega_intentada` sin `contenido_preview`, y se distingue fin cerrado de fin abandonado (sin `reason`). Diferencia de evidencia humano/juez documentada para el método del paper. Pregunta abierta con ese default | design D4 (tabla y párrafo "Diferencia de evidencia humano/juez"); spec traza-ciega-episodio; proposal Preguntas 5; tasks 6.1, 12.1 |
| M-3 modo restringido | En modo restringido no se montan `TourAutoStart`, `OnboardingDocente`, `ComisionSelectorRouted` ni `TenantSelector`, ni se piden comisiones | design D13; spec estudio-codificacion-acceso ("Entrada al panel docente"); task 11.2 con `docenteOnboarding.test.tsx` como consumidor |
| M-4 disponibilidad del panel | Requisito nuevo: docente con comisiones entra aunque falle `mis-membresias`; error de comisiones con membresía da modo restringido. `resolverAcceso` recibe `ok/error` por consulta | design D13 y Migration Plan paso 3; spec estudio-codificacion-acceso ("Disponibilidad del panel..."); task 11.2 |
| M-5 consumidores de `classifier_service.models` | Comando vacío reemplazado por `pytest apps/analytics-service -q` completo y los 4 archivos con `create_all`; `test_pedagogia_distribucion.py` nombrado. Regla de diseño: nada exclusivo de Postgres en la metadata del modelo, solo en la migración | design D1 ("Compatibilidad con SQLite") y tabla de consumidores; tasks 1.1, 2.1, 8.4, 13.2 |
| M-6 concurrencia | Orden de locks estudio luego membresía; `FOR SHARE` del estudio y `FOR UPDATE` de la membresía en guardado y cierre; `FOR UPDATE` del estudio en vigente, muestra y anclas. Escenarios de resultado válido y test con dos sesiones | design D10b; spec estudio-codificacion ("Operaciones concurrentes serializadas"); task 8.2 nueva |
| M-7 identidad por email | Membresía atada al `user_id` firmado en el primer uso; otro `user_id` con el mismo email da 403 y log. Router con `require_gateway_auth` y test con firma exigida | design D3; spec estudio-codificacion-acceso ("Procedencia de las llamadas", "Membresía atada al usuario del primer uso"); task 4.1 (mutantes d y e) |
| M-8 inmutabilidad de anclas | Trigger `INSERT/UPDATE/DELETE` sobre `estudio_ancla` de versión congelada; `contenido_sha256` cubre texto, esquema y anclas canónicas | design D2, D8; spec codebook-versionado ("Congelamiento e inmutabilidad", escenario "El sha cubre las anclas"); tasks 2.2, 5.1 |
| m-1 unidad de cita | Localizador global más uno por tipo: turno k (mensaje del alumno y respuestas del tutor que le siguen), código k, ejecución k, prueba k, nota k | design D4; spec traza-ciega-episodio ("Localizadores y tiempo relativo"); tasks 6.1, 11.4 |
| m-2 tiempo absoluto | `t_seg` desde el inicio en lugar de `ts`; `ts` agregado a las claves prohibidas | design D4; spec traza-ciega-episodio; task 6.1 |
| m-3 formato de respuestas | `{clave: {valor, cita}}`, cita en texto libre sin parseo; columnas `dim_<clave>_valor`/`_cita` | design D9, D12; spec estudio-codificacion ("Guardado incremental"); tasks 3.2, 10.1 |
| m-4 estado del episodio | `estado == "closed"` para muestra y anclas; `open` y `paused` rechazados | design D6, D11; specs estudio-codificacion, entrenamiento-calibracion; tasks 7.1, 7.3 |
| m-5 colisión de ruta | Clave con patrón `^[a-z0-9][a-z0-9-]{2,40}$` y lista reservada; 422 | design D3; spec estudio-codificacion-acceso (escenario "Clave reservada o inválida"); task 4.1 |
| m-6 re-alta tras revocación | Crea membresía nueva con alias, semilla y `user_id` propios; la revocada conserva y exporta sus etiquetas | design D3; spec estudio-codificacion-acceso (escenario "Re-asignación después de revocar"); task 4.1 |
| m-7 reproducibilidad del orden | Posición = rango de `sha256(f"{semilla}:{item_id}")`, independiente de la versión de Python; test con orden literal calculado aparte | design D7; spec estudio-codificacion (escenario "Orden recomputable"); task 7.2 |
| m-8 logs con PII | Logs con `membresia_id`, alias y `user_id` del autor, sin emails | design D3, D12; specs estudio-codificacion-acceso ("Registro de cambios de membresía sin emails"), exportación; tasks 4.1, 10.2 |
| m-9 tests con modelos del contrato | Tests con dicts crudos con claves extra (`execution_engine`) y conjunto exacto de claves por tipo | design D4; spec traza-ciega-episodio (escenario "Campos fuera del contrato"); task 6.1 |
| m-10 esquema v0 y límites de evidencia | Tarea de follow-up para preparar y validar el esquema v0 (y la coherencia de las anclas) antes de congelar; nota en el runbook sobre `tests_ejecutados` solo con conteos | tasks Workflow follow-up y 12.2; proposal Knowledge Base Impact |
| m-11 KB incompleto | REWRITE de la lista de keys de `helpContent` y de la lista de rutas del web-teacher en `CLAUDE.md` | proposal Knowledge Base Impact; task 12.3 |
| Observación del reviewer sobre pregunta 1 | Agregada la mención de que el change da cuentas de Clerk a externos y que toda cuenta recibe `docente` | proposal Preguntas 1 |

## EVIDENCIA

| Comando / lectura | Momento | Resultado |
|---|---|---|
| Lectura completa de `informes/propose-1-plan-reviewer.md` | 04/11 | 1 BLOQUEANTE, 8 MAYOR, 11 MENOR, clasificación CRITICAL confirmada (J-1) |
| Lectura codebook v0 §3, §4 y §5 (líneas 28-110) | 04/11 | §4: regla ordenada (reflexiva, pasiva, superficial por defecto, evidencia insuficiente fuera de la regla); la gramática de D9 la expresa |
| Lectura `packages/contracts/.../ctr/events.py` 129-150, 295-300, 503-560 | b32e621 | `EpisodioAbandonadoPayload.reason` incluye `timeout` y `distraccion_pestana` (marcas del sistema); `PegaIntentadaPayload.contenido_preview` hasta 200 chars; `CopiaIntentadaPayload` solo `seleccion_chars` y `metodo` |
| `diff` de las 14 primeras líneas de `tasks.md` contra la copia guardada | 04/11 | sin diferencias antes de reescribir |
| `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T11:19-03:00 | primera corrida: advertencia por requisito de más de 500 caracteres en traza-ciega-episodio; corregido; segunda corrida: `Change 'cibse-codificacion-ciega' is valid` |
| `rg -c "—"` sobre los artefactos | 04/11 | sin em dashes |

## JUICIO

Autor: planner. Comparación: hallazgos del reviewer y decisiones del orquestador contra los artefactos del intento 1.

- Todas las disposiciones quedaron aplicadas en specs, design y tasks; ninguna quedó solo en design (confianza alta).
- B-1: la gramática conjunción de disyunciones alcanza para la §4 del v0 tal como está escrita; si el investigador agrega condiciones que no se pueden expresar así (p. ej. "en algún tramo del episodio", §5), la regla no las cubre y quedan como criterio del codificador con desacuerdo declarado (confianza media).
- M-1: la protección depende de que el CTR sea append-only; un episodio con `integrity_compromised` podría dar `evidencia_alterada`, que es el comportamiento buscado (confianza alta).
- M-6: el diseño de locks está razonado, no probado; los escenarios de spec fijan los dos resultados válidos para que el test discrimine (confianza media hasta la tarea 8.2).
- m-7: el orden por hash cambia el procedimiento respecto del intento 1 (`random.shuffle`); es más simple de describir en el paper.

## SUPOSICIÓN

- Que `EpisodeOut.estado` es `closed` también para episodios abandonados; tomado de E18 del reviewer, no verificado por mí. Si los abandonados quedan con otro estado, la validación de la muestra los rechazaría; la tarea 7.1 lo detecta con datos reales del seed.
- Que la carga de 150 episodios con evidencia fija entra en el timeout de 120 s del gateway: no medido (la tarea 7.1 lo registra).
- Que `test_language_segmentation.py` hace `create_all` como los otros tres: lo afirma el reviewer (E7); no lo abrí.
- No se ejecutó código ni tests: no hay implementación.

## Fuentes leídas

- `informes/propose-1-plan-reviewer.md` (completo); artefactos propios del intento 1.
- Codebook v0 §3 a §5.
- `packages/contracts/src/platform_contracts/ctr/events.py` (fragmentos citados).
- `/home/juanisarmiento/Proyectos/AI-Native/codigo/CLAUDE.md` (en contexto).

## Contaminación por informes ajenos

Este intento parte por diseño del informe del plan-reviewer, que es su insumo. Las afirmaciones del reviewer que usé sin verificar yo (E5-E7, E9, E11-E13, E15-E19) se tratan como evidencia ajena y están marcadas así cuando no las reverifiqué (ver SUPOSICIÓN). No consulté Engram ni otros informes.
