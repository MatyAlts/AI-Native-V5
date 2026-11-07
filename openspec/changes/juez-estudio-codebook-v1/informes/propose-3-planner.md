# Informe: propose-3-planner - juez-estudio-codebook-v1

Autor: role-planner. Ejecutor: Claude Sonnet 5.5, subagente nativo de Claude Code (sin tabla "Role executors" en el proyecto).
Intento: 3 (último antes de ofrecer las tres opciones a Juani). Corrige `propose-2-plan-reviewer.md` bajo la decisión humana B (06/11/2026). Revisión: worktree `agent-a377c2107a7f2b43a`, rama `feat/juez-estudio-codebook-v1`, HEAD `178c343`; artefactos sin commitear. Fecha: 2026-11-06.
No se implementó producción, no hubo commits, push, deploy ni acceso a bases. Firewall del estudio respetado: no abrí contenido, trazas, etiquetas ni veredictos de los 150, ni nada bajo `analisis_produccion/`, ni `muestra_150.csv`, ni `anclas_v1.json`, ni el codebook.

## EVIDENCIA

- E1 `openspec validate juez-estudio-codebook-v1 --strict --json` (2026-11-06 21:12:08 -03, tras los últimos ajustes): `"valid": true`, `issues: []`. Una corrida previa (21:11:55) dio WARNING de requisito muy largo en el spec de congelado; corregido y revalidado. Alcance: formato, no contenido.
- E2 `openspec status --change juez-estudio-codebook-v1 --json` (21:12:08): ejecutado; el changeRoot es el correcto (no se inspeccionó el resto de la salida más allá de las rutas).
- E3 `rg -c "—"` sobre artefactos del change (21:12:08): sin em dashes en proposal, design, tasks ni specs. Los hay en informes previos (`propose-1-planner.md` 5, `propose-2-planner.md` 1), que no se reescriben.
- E4 Lectura de código en el worktree: `routes/estudio_trabajo.py` 95-200 (`_item_del_estudio`, `_enunciados_revisados`, `_enunciado_del_item`, `traza_ciega`): `_enunciado_del_item` acepta `EstudioMuestra | EstudioAncla` y las dos funciones de enunciado no dependen de `_item_del_estudio`, así que la extracción mínima de D3 es factible sin mover ese resolvedor. El bloque de evidencia es inline (se extrae como `comprobar_evidencia`).
- E5 `models/estudio.py`: `EstudioAncla` tiene `item_id`, `estudio_id`, `codebook_version_id`, `episode_id`, `seq_tope`, `chain_hash_tope`, `problema_id`, `ejercicio_id`; `EstudioMuestra` tiene `estudio_id`, `episode_id`. Alcanza para la consulta `EXISTS` de D5 y para resolver anclas por `estudio_id` y versión vigente.
- E6 `services/clients.py`: `CompleteResult` ya trae `model`, `provider`, `cache_hit`, `cost_usd`, tokens. `cost_usd` no requiere cambio de cliente. `AIGatewayClient.__init__` acepta `timeout` (default 60 s).
- E7 `rg` sobre `routes/estudio_trabajo.py`: aparecen `EstudioAncla.episode_id.in_(episodios)` en la carga de muestra (línea ~264, la verificación de anclas que ya describía el revisor, E6 de su informe) y `EstudioMuestra.episode_id == body.episode_id` en `crear_ancla` (línea ~971). Sostiene la afirmación de D5 de que las dos escrituras existentes impiden la superposición. No ejecuté esos caminos.
- E8 Del informe del revisor (propose-2, reutilizados sin reverificar salvo lo indicado en E4 a E7): E3 proxy, E7/E8 caché y `CompleteResponse`, E9 `res.model` es eco, E11 y E12 esquema y `evaluar_pedido`, E13 `respuesta_tutor` hereda `k`, E14 CI, E15 conftest, E16 patrón de `evaluation-service`, E18 `check-claude-md`.
- No ejecutado: tests, `alembic`, `make check-rls` (no hay código nuevo; prohibido tocar bases). No hay comportamiento runtime probado.

## Qué se recortó

- Calibración completa: tabla `estudio_juez_calibracion_item`, particiones `ajuste`/`prueba`, sorteo con semilla, registro de episodios (`POST/GET calibracion/items`), umbrales de acuerdo (85%, 90%), 16+3 ítems, `MIN_ITEMS_PRUEBA`, `MAX_VARIANTES_PRUEBA`, `modo` en el contrato, cobertura por régimen, spec `juez-estudio-calibracion` (reemplazada por `juez-estudio-congelado`).
- Proceso de fondo `asyncio` y sus 120 llamadas: reemplazado por corrida paso a paso (un par por request, 15 pasos).
- `corrida_ajuste_id` en config; sección 5.6 (test de ruteo; queda un comentario en `main.py`); preflight de citas humanas; `muestra_sha256` en la corrida; `MUESTRA_ESPERADA`.
- Extracción D3 reducida a 3 piezas; `_item_del_estudio` no se mueve. `verificar_esquema_juez` reducido a `to_regclass` de 3 tablas.
- Tablas: de 4 a 3. Endpoints: de 7 a 5 rutas.

## Disposición hallazgo por hallazgo (propose-2-plan-reviewer)

| Hallazgo | Disposición | Dónde quedó |
|---|---|---|
| B-N1 conjunto de calibración inconstruible | **Desaparece por opción B**: no hay conjunto de calibración, ni registro, ni lectura fuera del estudio | proposal (decisión humana), design D2, spec acceso |
| B-N2 firewall con foto vieja, sin lock, sin recheck al congelar | **Resuelto en versión mínima**: lectura fresca por par antes del CTR, re-chequeo al congelar, sin foto ni `muestra_sha256`; la superposición ancla-muestra ya la impiden `cargar_muestra` y `crear_ancla` (E7); muestra vacía no es error y se declara por qué; lock no necesario (ventana de ms sobre estado imposible) | design D5; spec acceso (4 escenarios de muestra); tasks 4.1, 4.5; mutantes F1 a F6 |
| B-N3 congelado sin medir (una repetición, reruns, sin_contenido) | **Resuelto**: `REPETICIONES_V1` constante fuera del pedido y comparada con `corrida.repeticiones` y con el conteo de pares; `sin_contenido`/`entrada_no_disponible` no suman; estabilidad por ancla; reruns sin tope pero con rastro (`motivo`, `n_corridas_previas`, `n_prompts_previos`) como pidió Juani | design D8; spec congelado; tasks 4.5; mutantes P5 a P11 |
| I1 preflight síncrono vs fondo | **Resuelto**: fase síncrona de `POST /corridas` (4xx/503 sin fila) vs `siguiente` (aborta con fila); no hay fondo | design D6; spec congelado "Creación" y acceso; tasks 4.2, 4.3 |
| I2 `dimensiones_opcionales_si_regimen` | **Resuelto**: dimensiones no requeridas en el esquema JSON; presencia chequeada en el paso 3.3; evidencia insuficiente con `notas` -> `ok`, sin `notas` -> `incompleto`; dimensión faltante con régimen no exento -> `incompleto` (mapeo único) | spec codificación (régimen y completitud); design D4/D7 nota; tasks 3.1, 3.3 |
| I3 corrida única y UNIQUE | **Resuelto simple**: sin fondo; `UNIQUE(corrida_id, ancla_item_id, repeticion)`; 409 `par_ya_procesado`; sin índice parcial de `en_curso` (una corrida abandonada no consume ni bloquea); duplicado de llamada acotado a 15 pares | design D6, D9; tasks 2.3, 4.3; mutante P2 |
| I4 referencia anti caché | **Resuelto**: nonce aleatorio por INTENTO, sin ids ni ordinales, guardado en el veredicto, distinto en reintentos | design D7; spec codificación "Referencia distinta por intento"; tasks 3.5; mutantes C6, C7 |
| I5 `raw_llm_output` y registro de calibración | **Resuelto / desaparece en parte**: el registro desaparece; `raw_llm_output` no sale por la API ni por logs (schemas explícitos, test); log estructurado sin contenido del alta | design D9; spec codificación; tasks 5.2; mutante C4 |
| I6 cita humana bloquea para siempre | **Desaparece por opción B**: sin preflight de citas humanas; la coincidencia es informativa y una cita humana mala no frena nada. `VALIDADOR_VERSION` persistido en corrida y veredicto | design D4; spec codificación (reproducibilidad) |
| I7 lista de modelos, `materia_id`, 429, `cost_usd` | **Resuelto**: `JUEZ_MODELOS_PERMITIDOS` (422, vacía -> 503); `materia_id=None` decidido y capturado en test, con consecuencia sobre la key y pregunta a Juani; 429 aborta sin reintento; `cost_usd` por veredicto y suma en el resumen | design D7, D10; spec acceso (lista) y codificación (429); tasks 3.5, 4.2, 5.4; mutantes A8, M4 |
| I8 realidad de CI | **Resuelto como plan honesto**: Migration Plan corregido (CI no corre integración de classifier ni `check-rls` sobre `classifier_db`); tarea 8.3 exige integración local con 0 skipped, `check-rls.py` y RLS con rol no superuser (2.3); job de CI es alcance: decisión 7, por defecto DEUDA con dueño Juani | design Migration Plan; tasks 2.3, 8.3; proposal decisión 7 |
| I9 mutantes por aserción, incluido el orden | **Resuelto**: tabla de 37 filas aserción -> mutante -> test; incluye el mutante de ORDEN (F2), falso positivo (F3), lectura fresca (F4), re-chequeo al congelar (F5), RLS (P12), esquema en runtime (P13); reemplaza la frase al revés del plan anterior | tasks 8.1 |
| I10 ambiente del recorrido con Clerk | **Pasa a decisión de Juani** con tres opciones (excepción de orden con deploy de `main`, ambiente de pruebas si existe, archivar con DEUDA); runbook con obtención del Bearer; SUPOSICIÓN de token de vida corta, mitigada porque la corrida es reanudable; aclara que el recorrido envía datos reales al proveedor | proposal decisión 6; design Migration Plan, Risks; tasks 8.5 |
| M1 conteo de la muestra | **Desaparece**: la entrada ya no es una lista de la muestra | design D5 |
| M2 cifras que aprueba Juani | **Resuelto**: una sola cifra por constante (`REPETICIONES_V1 = 3`, `ESTABILIDAD_MIN_V1 = 1.0`) en proposal y design; la opción "solo 5 anclas" es ahora el plan, no una alternativa sin diseño | proposal decisión 3; design D8 |
| M3 `res.model` es eco | **Resuelto**: wording corregido; límite declarado; `proveedores_respondieron` en config | design D7, D9 |
| M4 sobre de `response_format` y `jsonschema` | **Resuelto**: sobre `{"type":"json_schema","json_schema":{...}}` fijado; validador propio `validar_forma`, sin dependencia nueva | design D7; tasks 3.1 |
| M5 citas: `turno k` y prosa | **Resuelto**: `turno k` guarda todos los elementos; palabra de tipo + número en prosa es localizador | design D4; spec codificación; tasks 3.2 |
| M6 `modelo_respondio` nulo | **Resuelto**: nulo en `sin_contenido`, `entrada_no_disponible`, `llm_caido` | spec codificación; design D9; tasks 3.6 |
| M7 403 vs 422 | **Resuelto**: escenario "Cuerpo inválido de un no miembro" con test | spec acceso; tasks 5.1 |
| M8 tareas no ejecutables | **Resuelto**: migración en dos tramos para REDs por aserción; concurrencia 1 y excepción no prevista determinista; `hay_contenido` separado de `evaluar_item` | tasks 2.2, 2.3, 3.3, 4.3 |
| M9 versión de codebook y conteo | **Resuelto**: anclas filtradas por `codebook_version_id` vigente; congelar verifica `n_items x R` | design D6, D8; tasks 4.2, 4.5; mutantes A4, P6 |
| M10 `check-docs` (63 -> 64 ADRs) y smoke | **Resuelto**: el cambio de «63 ADRs» a 64 entra en 7.2 y en KB Impact, y `check-claude-md.py` en 7.2 y 8.3; smoke no se agrega con justificación y DEUDA nombrada | tasks 7.2, 8.3, 8.4 |
| M11 exposición del autor del framing | **Resuelto como regla**: el brief del constructor que redacte el `FRAMING` no incluye veredictos de producción ni etiquetas; el orquestador lo registra | design D11; tasks (reglas del constructor, estado de orquestación) |
| R1 lotes del cliente | **Tomado** (un par por request) | design D6 |
| R2 no mover `item_del_estudio` | **Tomado** | design D3 |
| R3 simplificar `verificar_esquema_juez` | **Tomado** (`to_regclass`) | design D9 |
| R4 sacar 5.6 | **Tomado** | design D2.4 |
| R5 sacar `corrida_ajuste_id` | **Tomado** | design D9 |

## JUICIO

- (role-planner, confianza media-alta) La opción B elimina de raíz tres bloqueantes y dos importantes; lo que sobrevive es el control de acceso, el firewall mínimo y un criterio técnico que sí se puede medir. Es el plan más chico que cumple "misma entrada, misma salida, misma regla, citas válidas, reproducible, auditable, separado de producción".
- (role-planner, confianza media) CRITICAL se mantiene por la frontera de cuenta lectora más proveedor externo y por el carácter de registro auditable del congelado, aunque el radio de impacto bajó a 5 episodios. HIGH es defendible; lo decide Juani.
- (role-planner, confianza media) `ESTABILIDAD_MIN_V1 = 1.0` con 5 anclas es estricto pero es lo único coherente con "estabilidad medida de verdad" con N tan chico; si el proveedor muestra variación a temperatura 0, la prueba técnica fallará y hará falta una decisión de Juani, no un ajuste silencioso.
- (role-planner, confianza media) El límite más importante que no se pudo cerrar por código: quien tenga acceso puede cambiar el prompt después de ver la coincidencia informativa. Se deja rastro (`motivo`, hashes, `n_prompts_previos`, git), no impedimento. Mostrar la coincidencia es parte de la decisión humana.
- (role-planner, confianza media) Para el paper: cinco anclas con tres repeticiones no validan el juez. Está dicho en proposal.

## SUPOSICIÓN

- La vía de acceso (D2) es la recomendada; Juani no firmó.
- `contenido_md` del codebook equivale a las secciones 1 a 9 del codebook v1 congelado; sin verificar (requiere comparar `contenido_sha256` con el archivo, verificación humana).
- Las 5 anclas tienen contenido (no son `sin_contenido`); sin verificar (no abrí anclas).
- `mensaje k` = `turno k` en cómo citaron los humanos: solo afecta la lectura de la coincidencia informativa, no bloquea.
- La clave de caché del gateway incluye los mensajes (revisor E7 por lectura); la defensa real es el chequeo de `cache_hit`.
- Con `materia_id=None` hay una key utilizable a nivel tenant o env; sin verificar. Si no, el primer paso lo muestra.
- El Bearer de Clerk se obtiene de la sesión del web-teacher y es de vida corta; sin verificar.
- Un paso (una llamada, timeout 40 s, un reintento) entra en los 120 s del proxy: estimación razonada, sin medir latencias.
- `cargar_muestra` y `crear_ancla` impiden la superposición ancla-muestra: leído, no ejecutado; el test 4.1 inserta la fila directamente para probar el guard.
- No sé si hay otro ambiente con Clerk además de `main`.
- Todo lo dicho sobre el juez futuro es diseño, no comportamiento observado.

## Fuentes leídas

Completos: `informes/propose-2-plan-reviewer.md`, `informes/propose-2-planner.md`, `informes/LEEME.md`, `tasks.md`, `proposal.md`, `design.md` y los tres specs previos (todos reescritos o reemplazados). Código (lectura, no datos): `routes/estudio_trabajo.py` 95-200 y rg de `episode_id`, `models/estudio.py` (`EstudioMuestra`, `EstudioAncla`), `services/clients.py` (`CompleteResult`). CLAUDE.md global, de proyecto y de repo. No abrí `propose-1-*` en esta vuelta (lo cubre el revisor del intento 2). Lecciones L-NNN: ausentes (ruta buscada `docs/`, por el revisor E21).

## Contaminación por otros informes

Leí por encargo `propose-2-plan-reviewer.md` (autoridad de esta vuelta) y `propose-2-planner.md` (mi intento previo). Los hechos de código que reuso sin reverificar están listados en E8; los que cambian el diseño (E4 a E7) los reverifiqué con lectura propia. Misma familia (Claude) que el revisor: la independencia es de rol y contexto, no de proveedor. No consulté Engram ni informes de otros changes.

## Chequeos no ejecutados

Suites, baseline, `alembic`, `make check-rls`, prueba contra ai-gateway real, medición de latencias.
