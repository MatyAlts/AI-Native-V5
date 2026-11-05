# Informe propose-4-planner

- Change: `cibse-codificacion-ciega`
- Rol: planner (propose, intento 4 por cambio de alcance del humano; no es intento fallido de gate)
- Ejecutor declarado: subagente nativo de Claude Code (role planner), familia Anthropic, la misma que el plan-reviewer.
- Base: `origin/main @ b32e621`; artefactos sin commitear.
- Entrada: respuestas de Juani del 04/11/2026 (P2, P4, P10 respondidas; P1 sin responder), pedido del orquestador de diseñar el enunciado en la vista ciega sin tocar tutor-service ni ctr-service, y menor R3-1 de `informes/propose-3-plan-reviewer.md` (veredicto APTO).
- No se tocó el bloque "Estado de orquestación" de `tasks.md` (ediciones solo después de `## Registro del planner`) ni los informes del reviewer.
- Revisión entregada (sha256, 12 primeros): proposal `d217b64ad2c7`, design `10cf6c4548ae`, tasks `6c4684d20a42`, specs: academic-enunciados-lectura `8b11c284bb1d` (nueva), codebook-versionado `ade6518708de` (sin cambios), entrenamiento-calibracion `9e1359b5f20f`, estudio-codificacion-acceso `d827a1c86fc9` (sin cambios), estudio-codificacion-exportacion `2da3d1836cc2`, estudio-codificacion `0b50f7b777fa`, traza-ciega-episodio `9760e6c862d0`.

## Disposición por pedido

| Pedido | Disposición | Dónde quedó |
|---|---|---|
| Registrar P2, P4, P10 respondidas y P1 abierta | Con fecha y autor (Juani, 04/11/2026). P2: dos profesores que no conocen los episodios; queda pendiente nombrar al investigador. P4: sí, en codificación y en anclas. P10: no obligatorio (coincide con el default). P1: sin responder; no bloquea construcción, sí el alta de externos en producción | proposal, Preguntas abiertas 1, 2, 4, 10; tasks Workflow follow-up |
| Qué enunciado se muestra | El de la TP siempre y el del ejercicio cuando `episodio_abierto.payload.ejercicio_id` no es nulo, rotulados. Justificación: el ejercicio es lo que el alumno resolvía; la TP es su encuadre y la única consigna en las monolíticas. No se muestran `codigo` ni `titulo` (pueden identificar comisión o cátedra) | design D14 "Qué se muestra"; spec traza-ciega-episodio "Enunciado del episodio en la traza" |
| Cómo llega sin tocar tutor ni ctr | classifier toma `problema_id` y `ejercicio_id` del episodio que ya lee del CTR y pide los textos a un endpoint interno nuevo de academic-service (`GET /api/v1/estudio-lectura/enunciados`, fuera del ROUTE_MAP) que devuelve solo los dos enunciados | design D14 "Cómo llega"; spec nueva `academic-enunciados-lectura`; tasks 7.0, 14.1, 14.2 |
| Cuenta de servicio propia y de solo lectura | `ESTUDIO_LECTOR_ACADEMIC_USER_ID` nuevo, rol `estudio_lector` con una sola política Casbin `enunciado:read`, fuera de `SERVICE_ROLES`, `OVERSIGHT_ROLES` y `FULL_CONTENT_ROLES`. **Requiere cambios en academic-service** (ruta, política, tests, deploy); queda como pregunta 12 con fallback de carga manual | design D14, Consumidores, Migration Plan paso 0; proposal Impact, Deploy, Capabilities, KB Impact, pregunta 12; tasks grupo 14 |
| Fijar con la evidencia (M-1) y hash | Al cargar muestra o ancla se guardan en `estudio_enunciado` (dedup por origen) con `sha256_original`; carga todo o nada; triggers impiden cambiar original y texto revisado | design D1, D2, D14 "Fijación"; spec estudio-codificacion "Enunciados fijados con la muestra"; tasks 2.1, 2.2, 7.1, 7.3 |
| Que no filtre máquina, comisión o docente | La máquina no participa (los enunciados son de academic-service). Para nombres, comisiones y fechas: alertas automáticas por patrones y revisión obligatoria del investigador (aprobar o editar, con original y hash conservados); la codificación da 409 mientras falten revisiones; anclas visibles en entrenamiento solo revisadas. Campos prohibidos nunca salen de academic-service | design D14 "Revisión"; specs estudio-codificacion "Revisión de enunciados antes de codificar", entrenamiento-calibracion "Enunciado de las anclas", academic-enunciados-lectura "Sin material de solución"; tasks 7.0, 7.2b, 11.8, 14.1 |
| R3-1 `regimen_regla` | Se guarda y exporta siempre que sea calculable, también con régimen exento | design D1, D9, D12; specs estudio-codificacion (escenario "Régimen exento"), exportación; tasks 3.2, 10.1 |

## EVIDENCIA

| Comando / lectura | Momento | Resultado |
|---|---|---|
| `apps/academic-service/src/academic_service/models/operacional.py:230-300, 420-500` | b32e621 | `TareaPractica`: `codigo`, `titulo`, `enunciado`, `fecha_inicio/fin`, `rubrica`, `test_cases`, `created_by`. `Ejercicio`: `enunciado_md`, `rubrica`, `test_cases`, `tutor_rules`, `banco_preguntas`, `misconceptions`, `respuesta_pista`, `heuristica_cierre`, `anti_patrones`, `created_by` |
| `routes/tareas_practicas.py:104-125`, `services/comision_service.py:105-128` | b32e621 | `GET /tareas-practicas/{id}` exige comisión salvo `SERVICE_ROLES`/`OVERSIGHT_ROLES`; para staff no sanea (tests ocultos incluidos) |
| `services/content_visibility.py` | b32e621 | `FULL_CONTENT_ROLES` incluye `tutor_service` y `execution_service`; el saneo del alumno conserva `rubrica` y tests públicos |
| `seeds/casbin_policies.py:240-260` | b32e621 | precedente de rol de servicio con una sola política de lectura (`execution_service`, ADR-059) |
| `apps/api-gateway/.../proxy.py:33-60` | b32e621 | academic expuesto por prefijos como `/api/v1/tareas-practicas` y `/api/v1/ejercicios`; `/api/v1/estudio-lectura` no figura |
| `rg -i` de nombres, comisión o fechas dentro de `enunciado` en `scripts/` y seeds de academic | 04/11 | sin coincidencias en el texto de enunciados (solo nombres de columnas en INSERT) |
| `openspec validate cibse-codificacion-ciega --strict` | 2026-11-04T11:38:38-03:00 | `Change 'cibse-codificacion-ciega' is valid` |
| `rg -c "—"` sobre artefactos | 04/11 | sin em dashes |

## JUICIO

Autor: planner. Comparación: pedido del orquestador y respuestas del humano contra el código de academic-service y gateway en b32e621.

- No hay forma de mostrar el enunciado sin tocar academic-service que respete mínimo privilegio: todo rol que cruza comisiones recibe soluciones (confianza alta, por lectura de código). Por eso el cambio en academic-service es necesario y pide decisión humana (pregunta 12).
- El endpoint dedicado de dos campos es preferible a reutilizar los existentes con un rol nuevo, porque el saneo actual conserva `rubrica` y el camino de staff no sanea (confianza alta).
- La ausencia de nombres y fechas no se puede verificar desde el repo para producción; la revisión humana obligatoria es el control real, y las alertas solo ayudan (confianza alta).
- Mostrar el enunciado de la TP en TPs con varios ejercicios agrega texto que no corresponde al episodio; lo acepto como fiel a lo que vio el alumno (confianza media; el investigador puede editar el texto mostrado si molesta).

## SUPOSICIÓN

- Que `episodio_abierto.payload.ejercicio_id` está presente en los episodios de TPs con ejercicios del banco del S2 2026: no consultado en producción; si falta, se muestra solo el enunciado de la TP.
- Que la TP publicada no cambia su `enunciado` (CLAUDE.md dice que una vez `published` no se edita); no importa para el estudio porque el texto se fija en la carga.
- Que academic-service enforcea `require_gateway_signature` igual que classifier; no verificado, el cliente firma si hay secreto.
- No se ejecutó código ni tests.

## Fuentes leídas

- `apps/academic-service/src/academic_service/{models/operacional.py, routes/tareas_practicas.py, routes/ejercicios.py (búsquedas), services/content_visibility.py, services/comision_service.py, seeds/casbin_policies.py, config.py}` (fragmentos citados).
- `apps/api-gateway/src/api_gateway/routes/proxy.py:33-60`.
- `informes/propose-3-plan-reviewer.md` (R3-1 y veredicto) y artefactos propios.

## Contaminación por informes ajenos

Tomé R3-1 y el veredicto APTO de `propose-3-plan-reviewer.md` como insumo. Todo lo de academic-service lo leí directamente en el código. No consulté Engram ni otros informes.
