# Informe verify-3-planner-specs

- Change: `cibse-codificacion-ciega`
- Rol: planner (actualización de specs posterior a la construcción, pedida por el orquestador)
- Ejecutor declarado: subagente nativo de Claude Code (role planner), familia Anthropic.
- Revisión leída: árbol de trabajo con la corrección de `informes/apply-3-constructor-F.md` (tasks grupo 15). Solo se modificaron `specs/*`.
- Specs entregadas (sha256, 12 primeros): codebook-versionado `1eef2d2f9937`, entrenamiento-calibracion `5fab20950976`, estudio-codificacion-acceso `003e6da81aae`, estudio-codificacion `78007f1ed8ae`, traza-ciega-episodio `0784c135a7f9`, estudio-codificacion-exportacion `ff8a33476668` (sin cambios).

## Disposición

| Pedido | Spec y ubicación | Forma tomada del código |
|---|---|---|
| N1 primer uso contra revocación | estudio-codificacion-acceso, "Membresía atada al usuario del primer uso", escenario "Primer uso concurrente con una revocación" | `routes/estudio.py:200-243`: `require_membresia(..., bloquear_estudio=...)` toma la fila del estudio antes de leer y atar la membresía. Tests de 15.1: codificador (`PUT mi-etiqueta`) e investigador (`POST /codebook` y alta de membresía) con revocación primero en la cola, resultado `(200, 403)` |
| N2 forma inválida del CTR | traza-ciega-episodio, "Fallas del registro de episodios", escenario "Respuesta con forma inválida"; estudio-codificacion, "Carga de la muestra fija", escenario "Registro de episodios con forma inválida" | `services/ctr_lectura.py:60-121`: `tiene_forma_de_episodio` exige `estado` str, `problema_id` UUID, `events_count` entero, `last_chain_hash` str, `integrity_compromised` bool si viene, `events` lista; por evento `seq` entero, `event_type` str, `ts` ISO 8601 con zona, `chain_hash` str, payload dict o nulo; `ejercicio_id` de `episodio_abierto` nulo o UUID; `duration_seconds` de `lectura_enunciado` nulo o numérico. Forma inválida → `CTRNoDisponibleError` → 502 con `_ERROR_CTR = "El registro de episodios no está disponible"` (`routes/estudio_trabajo.py:92, 176-177, 217`). Carga de muestra con `problema_id` no UUID → 502 y 0 ítems (test de 15.2) |
| O1 anclas completas para congelar | codebook-versionado, "Revalidación de anclas al editar el esquema y al congelar" (texto ampliado y escenarios "Esquema que deja incompleta un ancla" y "Congelar con un ancla incompleta"); entrenamiento-calibracion, "Anclas persistidas por versión del codebook" (escenarios "Ancla incompleta en borrador" y "Edición de un ancla incompleta") | `services/estudio_esquema.py:468-478`: `motivos_ancla_para_congelar` devuelve errores de validez o `incompleta: <código>` con los códigos de `faltantes_cierre` (`regimen`, `dimension:<clave>`, `cita:<clave>`, `notas`, `confianza`). Lo usan el aviso del PUT y el 422 de congelar (`routes/estudio.py:617`). Alta de ancla: 201 con `faltantes = faltantes_cierre(...)` (`routes/estudio_trabajo.py:950, 1004`); edición: 200 con `faltantes` = motivos sin el prefijo `incompleta: ` (l. 1038-1041). Tests de 15.3 en `test_estudio_anclas_db.py:309-395` |

## Diferencia entre código e informe (para el orquestador)

En la edición de un ancla, `faltantes` no trae solo códigos de completitud. El handler calcula `motivos_ancla_para_congelar`, que devuelve primero los **errores de validez** si el ancla guardada no vale contra el esquema actual. Después les quita el prefijo `incompleta: `, que esos errores no tienen.

Caso: el esquema cambió por un PUT que invalida el ancla, y el investigador la edita sin mandar `respuesta_esperada` (por ejemplo, solo `explicacion_md`). Ahí `faltantes` trae textos de error de validez, no códigos como `cita:d1`. El comentario del código afirma que "el ancla guardada vale contra este esquema", y eso no se cumple en ese caso.

El alta no tiene este comportamiento: valida antes de guardar y usa `faltantes_cierre`. El informe del constructor dice "Alta y edición de un ancla devuelven `faltantes` (códigos de `faltantes_cierre`)", lo que es exacto para el alta y no siempre para la edición. No lo escribí en la spec como contrato. No hay test para ese caso. No lo ejecuté: es lectura de código.

## EVIDENCIA

| Comando / lectura | Momento | Resultado |
|---|---|---|
| `tasks.md` grupo 15 y `informes/apply-3-constructor-F.md` (líneas 1-64, búsquedas) | 04/11 ~14:46 | escenarios afectados listados por el constructor en su l. 54 |
| `rg motivos_ancla_para_congelar|errores_respuesta_esperada` en routes | 04/11 | usado en `estudio.py:617` (PUT y congelar) y `estudio_trabajo.py:1038` (edición) |
| `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T14:48:59-03:00 | `Change 'cibse-codificacion-ciega' is valid` |

## JUICIO

Autor: planner. Los tres comportamientos coinciden con el informe del constructor en lo que piden las specs (confianza alta). La única diferencia es la de la edición de anclas descripta arriba (confianza media: lectura de código, no reproducida).

## SUPOSICIÓN

- No ejecuté tests ni Postgres; los resultados RED/GREEN son los registrados por el constructor en tasks 15.
- El escenario de N1 describe el resultado con la revocación primero en la cola, que es la intercalación que fijan los tests; otras intercalaciones válidas (primer uso antes que la revocación) no las describe la spec.

## Fuentes leídas

- `apps/classifier-service/src/classifier_service/{services/ctr_lectura.py:60-121, services/estudio_esquema.py:468-495, routes/estudio.py:200-243 y búsquedas, routes/estudio_trabajo.py:92, 176-217, 950-1045}`.
- `apps/classifier-service/tests/integration/test_estudio_anclas_db.py:309-395`.
- `tasks.md` grupo 15; `informes/apply-3-constructor-F.md` (búsquedas).

## Contaminación por informes ajenos

El encargo proviene del informe del constructor. Contrasté cada afirmación con el código; la discrepancia de la edición de anclas surge de esa contrastación.
