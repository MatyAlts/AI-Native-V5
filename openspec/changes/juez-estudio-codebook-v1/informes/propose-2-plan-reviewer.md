# Informe: propose-2-plan-reviewer - juez-estudio-codebook-v1

Autor: role-plan-reviewer, subagente nativo de Claude Code, modelo Claude Opus 5.5 (sin tabla "Role executors" en el proyecto). Misma familia que el planner (Claude): la independencia es de rol y contexto, no de proveedor.
Revisión: worktree `agent-a377c2107a7f2b43a`, rama `feat/juez-estudio-codebook-v1`, HEAD `178c343bac96be4f71ac1da4e2bc2b770365d72f` (= `origin/main`). Artefactos del change sin commitear, leídos el 2026-11-06 entre 20:51 y 20:59 -03 (`git status`: solo `?? openspec/changes/juez-estudio-codebook-v1/`).
Intento: 2 de la compuerta de plan.

## Veredicto

**VUELVE AL PLANNER** (CORRECCIONES). 3 BLOQUEANTES, 10 IMPORTANTES, 11 MENORES.

No es APTO PARA APROBACIÓN HUMANA todavía. `## Aprobación` sigue vacía (solo el comentario reservado): correcto. Ningún visto bueno de este informe reemplaza la firma de Juani.
Aviso de compuerta: este es el intento 2. Si el intento 3 no pasa, el contrato obliga a frenar y ofrecerle a Juani nuevo alcance aprobado, deuda aceptada o parar el change.

Lo central del rediseño es correcto y lo confirmé contra código: la vía por endpoints con membresía, la clasificación CRITICAL, la extracción de la traza, la detección de `cache_hit`, mock y fallback. Los bloqueantes son otros tres: el conjunto de calibración no se puede construir con lo planificado, el firewall trabaja con una foto vieja de la muestra, y el criterio de congelado tiene dos agujeros que anulan la protección que declara.

## EVIDENCIA

Todo el 2026-11-06, sobre HEAD `178c343`. Salvo que se indique, es lectura de código.

- E1 `openspec validate juez-estudio-codebook-v1 --strict --json` (20:51:21 y 20:58:40): `"valid": true`, 0 failed. `openspec status`: 4 artefactos `done`. Alcance: formato, no contenido.
- E2 `routes/estudio.py:150-229`: `_prohibido()` da 403 con `_SIN_ACCESO`; `require_membresia(session, user, clave, roles, *, bloquear_estudio=None)` se llama DENTRO del handler, no como `Depends` (docstring). `investigador_con_estudio_bloqueado` (505-513) toma `FOR UPDATE` sobre el estudio.
- E3 `apps/api-gateway/.../routes/proxy.py:64,118-123`: `"/api/v1/interrater"` -> `classifier_service_url`, `resolve_target` por `path.startswith`. Cubre `/api/v1/interrater/estudios/{clave}/juez/...`. Timeout del proxy: 120 s (`config.py:75`).
- E4 `routes/estudio_trabajo.py:99-120` `_item_del_estudio` resuelve SOLO `EstudioMuestra` o `EstudioAncla`. `:155-191` `traza_ciega` depende de eso. `apps/web-teacher/src/lib/estudioApi.ts:440` es el único consumidor de `/items/{id}/traza`.
- E5 `routes/estudio_trabajo.py:391-414` `requeridos()` lee solo `EstudioMuestra` y `EstudioAncla`. `:457-503` `cargar_enunciados`: una fila cuya clave no está en `requeridos` va a `ignoradas` y no se guarda (docstring: "Filas sin uso en la muestra ni en las anclas no se guardan").
- E6 `routes/estudio_trabajo.py:232-296` `cargar_muestra`: bajo lock del estudio; rechaza si `hay_etiquetas`; verifica anclas; borra y reinserta; no conoce otras tablas.
- E7 `apps/ai-gateway/.../services/budget_and_cache.py:86-99`: la clave de caché incluye `messages`, `model`, `temperature`, `max_tokens`, NO `response_format` ni tenant. `:101` cachea solo con `temperature == 0.0`. TTL 7 días. Presupuesto por `(tenant, feature, mes)`.
- E8 `apps/ai-gateway/.../routes/complete.py`: `CompleteResponse` tiene `cache_hit`, `provider`, `model`. `AIGatewayClient.complete` (classifier `services/clients.py`) los mapea. Budget excedido: HTTP 429. Default `default_monthly_budget_usd = 100.0` (`config.py:49`), `llm_fallback_model` vacío por default, `llm_stream_max_attempts = 3`.
- E9 `apps/ai-gateway/.../providers/base.py`: todos los proveedores devuelven `model=request.model` (líneas 65, 125, 194, 280, 405, 514): es un eco de lo pedido, no lo que informa el proveedor. `MockProvider` usa `provider="mock"` (66). `GeminiProvider` con `json_schema` solo pone `response_mime_type` e ignora el esquema (376-389). `AnthropicProvider` no usa `response_format`.
- E10 `apps/ai-gateway/.../services/byok.py:236-248`: resolución materia -> facultad -> tenant -> env. `routes/classify_ep.py:187-196`: el juez de producción pasa `materia_id` del episodio. `AIGatewayClient.__init__`: timeout default 60 s.
- E11 Esquema real: `~/Documentos/MTAC/CIbSE2027_muestra_150/codebook/esquema_v1.json` (solo esquema, sin datos de episodios): 4 regímenes (`reflexiva, superficial, pasiva, evidencia_insuficiente`), `dimensiones_opcionales_si_regimen: ["evidencia_insuficiente"]`, `notas_obligatorias_si_regimen: ["evidencia_insuficiente"]`, `notas_obligatorias_si_frontera: true`, `marca_frontera: true`, `confianza.obligatoria: true`, `reglas_regimen` con 2 reglas.
- E12 `services/estudio_esquema.py` `evaluar_pedido`: `regimen` no exento con `regimen_regla is None` da 422 ("con dimensiones incompletas solo se admite un régimen exento"). `faltantes_cierre`: dimensión faltante solo se reporta si `regimen` no está en `dimensiones_opcionales_si_regimen`.
- E13 `services/traza_ciega.py:107-115`: `respuesta_tutor` hereda `k` del turno, así que `turno k` resuelve a dos o más elementos.
- E14 `.github/workflows/ci.yml:383-389`: `test-unit` corre `apps/*/tests/*.py`, `apps/*/tests/unit/`, integración de evaluation y dos de academic, con `-m "not integration"`. NO incluye `apps/classifier-service/tests/integration/`. `:~549` `test-rls` corre solo `packages/platform-ops/tests/test_rls_postgres.py` sobre `ctr_store`. `rg "check-rls" ci.yml e2e-smoke.yml`: sin resultados. `migrations-dry-run` (551-589): solo el paso academic. `e2e-smoke.yml:96` corre `scripts/migrate-all.sh` con usuario `postgres`.
- E15 `tests/integration/conftest.py:31-60`: default `classifier_user` (owner no superuser, `init-dbs.sql:21,30`; FORCE RLS en `20260902_0002`) y skip si no hay Postgres. `docker ps` funciona en esta máquina.
- E16 `rg "create_task\(|BackgroundTasks|add_task\("` en `apps/classifier-service/src`: sin resultados (solo un `Semaphore` y `gather` en `leer_episodios`). Sí hay patrón en el repo: `evaluation-service` (`correccion_ejecutor.py`: `BackgroundTasks`, sesión propia corta y semáforo; `correccion_worker.py:298-305` y `main.py:60-85`: reconciliador al arrancar y periódico). El docstring registra el incidente: una corrección `running` para siempre tras un deploy.
- E17 `20261104_0007`: `revision = "20261104_0007"`, es el head; `alembic/env.py` sin `version_table` ni `transaction_per_migration`. Dockerfile: `alembic upgrade head || echo WARN`.
- E18 `python3 scripts/check-claude-md.py` (20:56:23): `[OK] 3 claims verificados, 2 skip, sin drift`, exit 0. Claim controlado: `\b(\d+) ADRs\b`, hoy `CLAUDE.md:213` dice 63 y hay 63 archivos. Job `check-docs` en CI (`ci.yml:48-61`).
- E19 `rg` sobre `apps/classifier-service/tests` y `src` de `_item_del_estudio|_enunciado_del_item|_enunciados_revisados`: solo `routes/estudio_trabajo.py`. Ningún test depende de los nombres privados: la extracción es factible.
- E20 `rg "jsonschema" apps/classifier-service/pyproject.toml`: sin resultados.
- E21 `rg "L-[0-9]{3}"` en `docs` y proposal: solo aparece la mención del proposal a su ausencia. Lecciones L-NNN: ausentes; ruta buscada `docs/`.
- E22 Cálculo propio (`python3`, binomial exacta, Wilson 95%, 20:56:27). Con N=16: umbral real de acuerdo 14/16 (87,5%), de estabilidad 15/16 (93,75%). IC Wilson de 14/16: 0,64 a 0,965. P(pasar una corrida) según acuerdo verdadero p: 0,70 -> 9,9%; 0,75 -> 19,7%; 0,80 -> 35,2%; 0,85 -> 56,1%; 0,90 -> 78,9%; 0,95 -> 95,7%. Con 3 corridas independientes, p=0,70 -> 26,9%; p=0,80 -> 72,8%. Con N=12 (`MIN_ITEMS_PRUEBA`): umbral 11/12. 10/12 tiene IC 0,55 a 0,95. Supuesto del cálculo: ítems independientes y misma p; las repeticiones reales están correlacionadas.
- E23 `proposal.md:81-83`: `## Aprobación` contiene solo el comentario reservado. Búsqueda de em dashes con `rg -c` sobre proposal, design y tasks: sin resultados.
- No ejecutado: suites de tests (el worktree no tiene pytest, E17 del intento 1; no se hizo `uv sync`), `alembic`, `make check-rls` (requieren base; prohibido en este encargo). No hay comportamiento runtime probado: el juez no existe.

## Estado de los hallazgos del intento 1

| Hallazgo | Estado verificado | Comprobación |
|---|---|---|
| B1 citas | Resuelto en el plan, con residuales | D4, 3.2 y spec coherentes con las 5 citas. Residuales en I6 y M5 |
| B2 modelo efectivo | Resuelto, con límite no declarado | `cache_hit`, `provider="mock"` y fallback detectables (E8, E9). `res.model` es eco (M3) |
| B3 vía de acceso | Resuelto | Sin script; patrones reales de `require_membresia` (E2). Residual en I5 |
| B4 persistencia | Resuelto | Spec, D8 y D9 ya no se contradicen. Falta UNIQUE (I3) |
| I1 criterio engañoso | **Parcial** | Separación ajuste/prueba sí; repeticiones y reruns no (B-N3) |
| I2 firewall | **Parcial** | Fuente en base y fail-closed sí; foto vieja y conteo no (B-N2, M1) |
| I3 completitud | **Parcial** | `faltantes_cierre` llamado; `incompleto` por dimensión faltante inalcanzable (I2) |
| I4 misma fuente | Resuelto | Extracción factible (E19). Recorte en R2 |
| I5 hash de prompt | Resuelto | `prompt_sha256` y golden alineados en D9, spec y 3.6 |
| I6 migración | **Parcial** | Tareas sí; los gates de CI que cita no cubren el cambio (I8) |
| I7 escenarios sin tarea | Resuelto | 3.4, 4.5 y 5.x los cubren |
| I8 baseline | Resuelto como plan | Paso 0. No ejecutado por este revisor |
| M1, M2, M3, M4, M6 | Resueltos | D5, 5.5, D6, D2 y D10 |
| M5 contrato LLM | Parcial | Falta `materia_id`, sobre de `response_format` y trato del 429 (I7, M4) |

## Hallazgos

### B-N1. BLOQUEANTE - El conjunto de calibración no se puede construir con lo planificado, y sin él no existe ningún congelado

- Fuente: design D6 (`respuesta_esperada` obligatoria al registrar, "consensuados por los dos codificadores", sorteo "contra la base"), D8 (`ajuste` nunca habilita congelar), proposal decisión 3, "Fuera de alcance: UI", tasks 5.5; E4, E5.
- Observación: tres huecos encadenados, verificados por lectura.
  (a) **Sin vía de codificación ciega.** Los codificadores ven trazas solo por `/items/{id}/traza`, que resuelve muestra o ancla (E4). Un episodio de calibración no es ninguna de las dos, y además el registro exige la etiqueta YA consensuada: para etiquetar hay que ver, y para ver por la vía ciega hay que estar registrado. El plan no dice cómo los dos humanos leen esos 19 episodios con la misma entrada que el juez.
  (b) **Enunciados inalcanzables.** D6 paso 5 exige enunciado revisado, pero `cargar_enunciados` descarta toda fila que no esté en muestra o anclas (E5). Un episodio de otro TP o ejercicio termina siempre en 409 `enunciado_pendiente`. Eso limita el universo a TPs y ejercicios de muestra y anclas, cosa que el sorteo "entre episodios cerrados del tenant" no dice.
  (c) **Sorteo sin herramienta.** No hay endpoint ni tarea que liste episodios cerrados; los episodios viven en `ctr_store` y la exclusión en `classifier_db`, sin joins entre bases (regla del repo).
- Impacto: `prueba` queda vacía, `cobertura_insuficiente` para siempre, ninguna configuración se congela y T-002 no tiene qué correr. Si se improvisa etiquetando fuera de la traza ciega, la referencia de `prueba` deja de ser comparable con la entrada del juez, que es la promesa central del change.
- Criterio incumplido: viabilidad de dependencias; spec "Registro de episodios de calibración" y "Entrada idéntica a la de un codificador humano".
- Corrección verificable: definir de punta a punta cómo nace un ítem de `prueba`: selección (quién, con qué consulta, dónde queda la semilla), lectura ciega por los codificadores (por ejemplo, registro en dos pasos con etiqueta posterior y traza por `item_id` opaco, o una vía equivalente), carga de enunciados, consenso. Lo que toque `requeridos`, `_item_del_estudio` o `cargar_enunciados` es alcance nuevo y va a Juani. Test de aceptación: flujo de integración desde "episodio sin registrar" hasta "corrida de `prueba` aceptada" usando solo endpoints del plan. Declarar en D6 la restricción de universo a TPs con enunciado cargable.

### B-N2. BLOQUEANTE - El firewall usa una foto de la muestra: no protege durante la corrida ni al congelar, y no toma el lock

- Fuente: design D7 ("la función que lee la traza repite la pertenencia (`item.episode_id not in muestra`...)"; "el chequeo corre en cada corrida"), D8 paso 0, D9 (`POST /configuraciones`), tasks 4.1, 4.5, 8.2(d); E2, E6.
- Observación: `muestra` es un `frozenset` calculado una vez en el preflight. La "repetición por lectura" compara contra esa misma foto, así que frente a una recarga es tautológica. Una corrida dura minutos. `cargar_muestra` puede recargar en esa ventana (E6) porque D2 y D8 no dicen que el POST ni la corrida tomen el lock del estudio. Además `congelar` no revisa la exclusión: una recarga entre el cierre de la corrida y el congelado deja una configuración justificada por un episodio que ya es de la muestra, sin aviso. Y el mutante 8.2(d) se mata con un test unitario que pasa una foto distinta, sin demostrar la falla real.
- Escenario razonado (no ejecutado): corrida `prueba` en curso, recarga que incluye un ítem pendiente, y la traza de ese episodio de la muestra se envía al proveedor con el firewall "aprobado".
- Atenuante no verificado: `cargar_muestra` rechaza si hay etiquetas. Si los codificadores ya etiquetaron, la recarga está cerrada en producción. No consulté la base, y el plan no se apoya en eso.
- Impacto: viola la restricción central ("Nunca lee contenido de los 150") en la frontera que justifica CRITICAL, y contamina el resultado en silencio.
- Criterio incumplido: spec "Firewall contra la muestra"; "fail-closed"; mutante que prueba falla real.
- Corrección verificable: (1) el POST toma el lock del estudio al validar, como `crear_ancla`; (2) `estudio_juez_corrida` guarda `muestra_sha256`; (3) cada lectura de ítem relee en base: pertenencia por `episode_id` y `muestra_sha256` igual al de la corrida, si no aborta (`muestra_cambiada`); (4) `congelar` repite ambos chequeos y rechaza con 409; (5) test de integración que recarga la muestra entre dos ítems y otro entre cierre y congelado; (6) 8.2(d) reescrito sobre esos tests.

### B-N3. BLOQUEANTE - El criterio de congelado se puede cumplir sin medir lo que dice: una repetición, reruns sin tope y evidencia insuficiente sin modelo

- Fuente: design D8 ("`repeticiones` (1 a 5...)", `MAX_VARIANTES_PRUEBA` cuenta pares distintos, Migration Plan paso 5 "una corrida de `prueba` por variante"), D5 paso 1, spec calibración "Tope de variantes", proposal "Criterio de congelado sin autoengaño", tasks 4.2-4.5; E22.
- Observación:
  (a) `repeticiones=1` es válido y el criterio no exige un mínimo: `estabilidad` da 1,0 por construcción y pasa. El proposal le ofrece a Juani "3 repeticiones".
  (b) El tope cuenta pares `(modelo, prompt_sha256)`, así que la MISMA variante corre sobre `prueba` sin límite, y `POST /configuraciones` acepta cualquier corrida. El Migration Plan dice "una por variante", pero nada lo aplica. Con la referencia por llamada las corridas no son idénticas, y según E22 un juez de p=0,70 pasa 9,9% por intento y 26,9% en tres intentos independientes. Las corridas reales están correlacionadas, así que el efecto es menor, pero va en esa dirección. Es el "garden of forking paths" de B4/I1, solo que registrado en vez de impedido.
  (c) `sin_contenido` cuenta como acierto sin llamar al modelo: los ítems de evidencia insuficiente que exige la cobertura pueden ser triviales y estables. Con 4 de 16 así, el acuerdo real medido es sobre 12 (10/12: IC 0,55 a 0,95).
- Impacto: se puede congelar con la apariencia de "3 repeticiones, retención y tope" sin que ninguna de esas tres cosas haya operado. Es lo que Juani aprobaría creyendo otra cosa.
- Criterio incumplido: I1; spec "Congelar exige un criterio medible superado"; criterio de aceptación no engañoso.
- Corrección verificable: (1) `prueba` exige `repeticiones == CRITERIO_V1.repeticiones` (test: `repeticiones=1` da 422 o no congela); (2) una sola corrida `prueba` válida por variante; rerun solo si la anterior terminó `abortada` o interrumpida sin resultado evaluable, con razón registrada (test: segunda corrida cerrada de igual variante da 409); (3) congelar solo desde la primera corrida evaluable de la variante; (4) el criterio informa y exige por separado el acuerdo sobre ítems con llamada real, y excluye `sin_contenido` de `estabilidad` (test con fixture). Los valores los decide Juani.

### I1. IMPORTANTE - El preflight es síncrono en la spec y de fondo en el diseño, y aborta sobre una fila que todavía no existe

- Fuente: design D8 ("Pasos (en un proceso de fondo...)", paso 0 antes del paso 1 de inserción), spec calibración (409, `cobertura_insuficiente` "antes de leer el CTR", "no crea la corrida"), spec acceso (409 `traza_version_distinta`, 503), spec codificación ("termina `abortada` con `gramatica_incompatible`"), tasks 4.4, 5.1.
- Observación: una tarea de fondo no puede responder 409 ni 503. Y `abortada` requiere una fila que D8 inserta después del preflight. Tasks 4.4 pone todo el preflight dentro de `ejecutar_corrida`.
- Impacto: el constructor elige en silencio cuáles rechazos dejan rastro y cuáles se ven como 202.
- Corrección verificable: partir explícitamente: fase síncrona bajo lock (membresía, vigente, traza, esquema, firewall, cobertura, tope) que responde 4xx/503 sin fila; inserción; fase de fondo (lecturas, preflight de gramática, llamadas) que cierra `abortada`. Una tabla código a fase en D8 y una tarea por fase.

### I2. IMPORTANTE - El flujo D5 no llega a `incompleto` por dimensión faltante y rechaza la evidencia insuficiente legítima

- Fuente: design D5 paso 3 y `construir_json_schema` ("requerida por dimensión"), spec codificación "Falta una dimensión..." y "Régimen exento", tasks 3.3; E11, E12.
- Observación: una dimensión omitida cae en el paso 3 como `respuesta_malformada`. Si pasara al paso 5, con régimen no exento da 422, `inconsistente` (E12). `incompleto` por dimensión faltante, que spec y 3.3 exigen, es inalcanzable. Peor: el esquema real declara `dimensiones_opcionales_si_regimen: ["evidencia_insuficiente"]` (E11). Un juez que elige bien ese régimen y deja dimensiones vacías, como el humano, queda `respuesta_malformada`. Con cero estados no válidos y cobertura obligatoria de ese régimen, eso bloquea el congelado. El plan no menciona esa clave.
- Corrección verificable: el contrato admite `valor` nulo u omitido cuando corresponda; el paso 3 valida forma y claves ajenas, no presencia de dimensiones; fijar el mapeo final. Tests con `esquema_v1.json` como fixture: `evidencia_insuficiente` sin dimensiones y con `notas` da `ok`; sin `notas` da `incompleto`; dimensión faltante con régimen no exento da el estado acordado, igual en D5, spec y 3.3.

### I3. IMPORTANTE - Proceso de fondo sin guarda ni cierre, ignorando el patrón y el incidente que ya tiene el repo

- Fuente: design D8, D9, Risks ("queda `en_curso` visible; se relanza"), proposal, `informes/propose-2-planner.md` JUICIO; E16.
- Respuesta a lo pedido: ¿es necesario? No en un solo POST (proxy 120 s; 48 llamadas no entran, estimación razonada), pero no exige tarea suelta. ¿Sobrevive a un reinicio? No: muere y no se reanuda. ¿Hay patrón? En classifier-service no; en evaluation-service sí, con un incidente documentado por `running` eterno. "Proceso de fondo `asyncio`" no nombra mecanismo.
- Observación: sin índice único, dos POST lanzan dos corridas (costo doble, sin tope conjunto). No hay forma de cerrar una `en_curso` muerta. `estudio_juez_veredicto` no tiene UNIQUE por `(corrida, ítem, repetición)`. Un deploy de classifier-service mata la corrida y Migration Plan no lo avisa, aunque el deploy de a un servicio se respeta.
- Impacto: filas `en_curso` eternas, conteos duplicados y gasto no acotado.
- Corrección verificable: elegir y justificar. Opción A: `BackgroundTasks` con sesión corta y semáforo; índice único parcial de una `en_curso` por estudio; al lanzar, cerrar como `abortada` `proceso_interrumpido` las `en_curso` vencidas del estudio (sin loop periódico ni policy entre tenants). Opción B, más simple (ver R1). En ambas: UNIQUE de veredicto (dos índices parciales) y runbook "no deployar classifier-service con corrida en curso".

### I4. IMPORTANTE - La referencia de ejecución contradice la ceguera y no sirve para reintentos

- Fuente: design D10 (`<corrida_id>/<item>/<repetición>`, "cambia la clave de caché"), spec codificación ("excluye... el `item_id`"), D11, tasks 3.4-3.5; E7, E8, E10.
- Respuesta a lo pedido: la técnica es factible. E7 confirma que la clave incluye `messages` y E8 que `cache_hit` existe en la respuesta real. La SUPOSICIÓN del design queda verificada por lectura, sin correr un gateway.
- Observación: (a) `<item>` no está definido; si es `item_id`, viola la spec y el test 3.4. (b) Es la misma referencia en los reintentos. Si el cliente corta a los 60 s y el gateway termina y cachea (razonado; no probé que el handler siga tras la desconexión), el reintento recibe `cache_hit=True` y un estado no ok que bloquea el congelado.
- Corrección verificable: `referencia` = nonce aleatorio por INTENTO de llamada, sin ids ni ordinales, guardado en el veredicto. Test: nonces distintos en reintentos; el texto del prompt no contiene `item_id` ni `episode_id`, con el valor real de la fixture y no un literal corto.

### I5. IMPORTANTE - El registro de calibración abre una lectura amplia del tenant, y D2/Risks la describen como inocua

- Fuente: design D2 regla 5, D6, Risks ("solo fija evidencia"), tasks 5.3, CLAUDE.md invariante ADR-063; E2.
- Observación: el `episode_id` del pedido no "solo fija evidencia": el ítem queda elegible para corridas, su contenido viaja al proveedor y `GET .../calibraciones/{id}` expone veredictos con `notas`, citas y `raw_llm_output` derivados del episodio. El precedente `crear_ancla` solo opera sobre versión en borrador; esta vía queda abierta con versión congelada. El único acotamiento efectivo es indirecto: D6 paso 5 exige enunciado revisado, lo que hoy ata a TPs de muestra y anclas (E5). El CTR se lee antes, y arreglar B-N1 puede ensancharlo sin que nadie lo note. No hay exigencia de log de auditoría del alta.
- Respuesta a lo pedido: las corridas sí usan solo IDs resueltos del estudio (D2.2, D2.5, `extra="forbid"`, 4.3, 8.1c). El agujero es el registro, no la corrida.
- Corrección verificable: regla explícita de universo admitido, con test que rechaza un episodio fuera de él y no devuelve datos; `raw_llm_output` no sale por la API (test); log estructurado del alta sin contenido; texto del Risk corregido. La enmienda a CLAUDE.md debe decir que este `episode_id` termina en un proveedor externo.

### I6. IMPORTANTE - El preflight de gramática puede bloquear para siempre por una cita humana

- Fuente: design D4 "Paso 0", D6 (inmutable), Risks ("se corrige con una migración operativa"), SUPOSICIÓN `mensaje = turno`.
- Observación: anclas de versión congelada y calibración son inmutables, y UNA cita humana sin validar aborta toda corrida. Un error de tipeo, o que `mensaje k` no signifique `turno k` (no verificado), deja `ajuste` y `prueba` inutilizables sin arreglo por API. Además la versión del validador no entra en `prompt_sha256`: cambiar la gramática no se refleja en lo persistido.
- Corrección verificable: distinguir incompatibilidad de forma (no parsea, aborta) de localizador inexistente en un ítem (el ítem se excluye con razón o bloquea solo `prueba`, decidido y reportado); persistir `VALIDADOR_VERSION` en corrida y veredicto. Test con una cita humana que apunta a un localizador inexistente.

### I7. IMPORTANTE - Frontera con el proveedor sin control técnico: `modelo` libre y `materia_id` indefinido

- Fuente: design D2, D10, proposal decisión 2; E9, E10.
- Observación: `modelo` del pedido es texto libre. Cualquier investigador puede mandar trazas de alumnos a cualquier destino que la key permita (un nombre con `/` va a OpenRouter), aunque Juani apruebe uno solo. Un nombre mal tipeado además consume un cupo de `MAX_VARIANTES_PRUEBA`. D10 no menciona `materia_id`: el juez de producción lo pasa y el nuevo caería a tenant o env, con otra key o sin key. Si no hay key, todas las llamadas dan `modelo_no_pinneado`, y el plan lo descubriría recién en la corrida. La respuesta del convenio queda solo en un papel. "Como ya hace el juez de producción" es cierto para el canal, no prueba cobertura del consentimiento.
- Presupuesto: bucket propio `estudio_juez` con 100 USD/mes por default, suficiente como freno pero sin estimación de costo. Un 429 entra como "error de infraestructura": 3 intentos por ítem hasta terminar la corrida.
- Corrección verificable: lista permitida de modelos en config (422 si no está), fijada con la respuesta a la decisión 2; decisión explícita de `materia_id` y test que captura el valor; 429 aborta la corrida con `presupuesto_excedido`, sin reintento; `cost_usd` en veredicto y reporte (hoy no está en D9).

### I8. IMPORTANTE - Los gates de CI que cita el plan no cubren este cambio

- Fuente: design Migration Plan paso 1, tasks 8.6, proposal "Deploy"; E14, E15.
- Observación: (a) `apps/classifier-service/tests/integration/` no corre en CI: acceso, 403, firewall, inmutabilidad y RLS de este change quedan afuera, y localmente se saltean si no hay Postgres. (b) `check-rls` no aparece en ningún workflow, aunque CLAUDE.md y el plan dicen que corre en CI. (c) `test-rls` mira solo `ctr_store`: no dice nada de `classifier_db`, y 8.6 lo lista como si cubriera las tablas nuevas. (d) `migrations-dry-run` no migra classifier; lo más cercano es `e2e-smoke` con superusuario, que solo prueba `upgrade`.
- Impacto: PR verde sin haber ejecutado ninguna garantía de seguridad; regresiones futuras sin red.
- Corrección verificable: corregir Migration Plan; exigir en 8.6 evidencia local con `CLASSIFIER_TEST_DB_URL` y **0 skipped** en los archivos del juez (conteo registrado), `scripts/check-rls.py` con salida, y test RLS propio con rol no superuser. Agregar a CI un job de integración classifier, o decidir DEUDA nombrada con dueño. Cambiar CI es alcance: lo decide Juani.

### I9. IMPORTANTE - Sección 8 no cubre "un mutante por cada aserción de seguridad o datos"

- Fuente: tabla CRITICAL del workflow; proposal; tasks 8.1-8.4; design D7.
- Sobre los cinco mutantes del firewall: (1) `return`: falla real. (2) sin normalizar: real solo si se define qué se muta. (3) vacía aceptada: real, pero `ids_muestra` tiene su propio fail-closed, así que hace falta un test directo del guard. (4) repetición: vacuo frente a recarga (B-N2). (5) invertir: lo mata cualquier test; no aporta, como ya dijo I2 del intento 1. La frase "cada uno debe matar al menos un test" está al revés.
- Faltan: guard después de la lectura del CTR (mutante de ORDEN, el más realista); `ids_muestra` sin filtro `estudio_id`; `muestra_cargada_at` sin chequear; 409 `episodio_en_muestra` y `episodio_es_ancla` del registro; `muestra_no_cargada`; `evidencia_alterada` e `enunciado_pendiente` sin chequear; cobertura y tope de variantes; RLS (policy quitada, test con rol no superuser); `episode_id` en `GET items`; `verificar_esquema_juez`; los mutantes de B-N2 y B-N3.
- Corrección verificable: tabla aserción -> mutante -> test que lo mata, que recorra specs de acceso y calibración; 8.2(e) se reemplaza por el de orden.

### I10. IMPORTANTE - El recorrido con Clerk no tiene ambiente viable antes de archivar

- Fuente: tasks 8.7, proposal; CLAUDE.md del proyecto ("EasyPanel deploya `main`"), regla global de publicación ("Before any push require archived/closed change").
- Observación: el recorrido real exige código desplegado con Clerk, el único deploy conocido es `main`, y la regla pide archivar antes de publicar, mientras 8.7 debe ocurrir antes de archivar. El plan no lo resuelve ni dice cómo un investigador obtiene el Bearer sin UI. Tampoco que el recorrido envía datos reales al proveedor y requiere decisión 2. `cibse-codificacion-ciega` está en `main` sin archivar: hay precedente, no decisión.
- Corrección verificable: agregar una decisión para Juani: ambiente de 8.7 y orden merge, recorrido, archivo. Runbook con la obtención del token. SUPOSICIÓN: el token de Clerk es de vida corta; no verificado.

### Menores

- **M1 Conteo de la muestra.** I2 pedía error ante conteo distinto; quedó en verificación humana. `ids_muestra` acepta cualquier cantidad mayor que 0. Fijar `MUESTRA_ESPERADA` o declarar por qué no.
- **M2 Cifras que Juani aprueba distintas de las del código.** Proposal: 16 ítems y 4 por régimen; D8: `MIN_ITEMS_PRUEBA = 12` y 1 por régimen. Con 12 el umbral real es 11/12. Alinear y declarar umbrales en conteos. La opción "solo las 5 anclas" de la decisión 3 no tiene diseño: `prueba` no admite anclas y nada se congelaría. Decirlo o quitarla.
- **M3 "Modelo que respondió" es una exageración.** `res.model` es eco de lo pedido al proveedor (E9). Detecta fallback y mock, no alias ni ruteo interno. Corregir wording en D10 y guardar `proveedores_respondieron` en config.
- **M4 Salida estructurada.** Fijar el sobre `{"type":"json_schema","json_schema":...}`. Gemini y Anthropic no aplican el esquema (E9): la validación es local, y classifier no declara `jsonschema` (E20). Decidir dependencia o validador propio.
- **M5 Citas.** "`n` inequívoco" es falso para `turno k` (E13): definir si guarda todos los elementos. Palabras de tipo en prosa libre ("la lectura 3 veces") darían `cita_invalida`; agregar caso a 3.2 y regla.
- **M6 "En cualquier estado".** `modelo_respondio` no existe en `sin_contenido`, `entrada_no_disponible` ni `llm_caido`. Spec y 3.6 deben admitir nulo.
- **M7 403 frente a 422.** FastAPI valida el body antes del handler (E2): un no miembro con body inválido recibe 422, no el 403 que promete la spec "todo otro caller". No revela el estudio; ajustar el texto y agregar el test. `extra="forbid"` no se usa hoy en estas rutas: es nuevo, y coherente.
- **M8 Tareas no ejecutables como están.** 2.3 pide RED por aserción antes de la migración, pero sin tablas es error de setup, que no cuenta: separar tablas y triggers. 4.4 "excepción en el 3er llamado deja 2 veredictos" no es determinista con concurrencia 4 y contradice "un error no detiene": usar concurrencia 1 y excepción no prevista. `evaluar_item(esquema, elementos, raw)` recibe `raw`, pero su paso 1 evita llamar al modelo: separar.
- **M9 Versión de codebook.** `items_del_modo` no filtra `codebook_version_id`, y `UNIQUE(estudio_id, episode_id)` impide re-registrar bajo otra versión. Congelar debe además verificar veredictos = `n_items x repeticiones` ("sin ítems abortados" no está definido).
- **M10 CI de docs y smoke.** ADR-064 lleva a 64 archivos y `CLAUDE.md:213` dice 63: `check-docs` falla (E18), y 7.2 ordena "no tocar otra sección". Incluir ese cambio y `check-claude-md.py` en 8.6. CLAUDE.md pide smoke al cerrar: agregar o justificar.
- **M11 Exposición del autor del framing.** tasks.md línea 11 dice que el orquestador consulta veredictos de producción de los 150 en otro ticket. Quien escriba `FRAMING` y ajuste variantes no debería tener esa exposición. Declarar el aislamiento en el brief del constructor y en el rastro, o decidir si importa.

## Recortes posibles sin perder garantías

- **R1 Reemplazar el proceso de fondo por lotes del cliente:** `POST /calibraciones` crea la corrida; `POST /calibraciones/{id}/lote` procesa unas pocas llamadas dentro del timeout y devuelve avance; lo pendiente se calcula con el UNIQUE de veredictos. Sobrevive a reinicios, no deja `en_curso` zombi sin reanudar y hace deterministas los tests. Costo: un cliente que itera con token fresco (ver I10). Lo decide el planner con Juani.
- **R2 Achicar la extracción D3:** el juez solo necesita enunciado y chequeo de evidencia. `item_del_estudio` no debe moverse: resuelve ítems de la muestra, y llevarlo a un servicio compartido acerca al juez el único resolvedor que no debe usar.
- **R3 Simplificar `verificar_esquema_juez`:** Postgres aplica la migración en una transacción (E17, default de alembic; no probado), así que tablas y triggers llegan juntos, y si faltan las tablas la operación falla igual. Con la verificación post-deploy, alcanza un chequeo de `alembic_version`. Si se conserva, debe cubrir también `POST items` (lee CTR, D9 vs spec) y mirar `tgenabled`.
- **R4 Test 5.6:** una prueba que lee texto de otro servicio aporta poco; alcanza con el comentario de `main.py` y una línea en ADR.
- **R5 `corrida_ajuste_id` en config:** "la última de ajuste de la misma variante" no agrega garantía sobre `n_corridas_ajuste`.

No recortaría: las 4 tablas (si Juani elige retención), `prompt_sha256` y el rastro de corridas.

## Respuesta al punto 3

- **Clasificación CRITICAL:** justificada. Cuenta de servicio que lee cualquier episodio del tenant, identidad de usuario nueva y envío a proveedor externo: frontera de datos sensibles según la regla, aun con diff chico. La decide Juani en `## Aprobación`.
- **Mutantes:** exigencia declarada pero no satisfecha (I9).
- **Recorrido con Clerk:** presente en 8.7, con DEUDA nombrada, pero sin ambiente viable (I10).
- **`## Aprobación`:** vacía (E23). Las seis decisiones siguen abiertas, y esta revisión suma preguntas: B-N1 (cómo nace `prueba`), I7 (lista de modelos), I8 (CI), I10 (ambiente).

## JUICIO

- (role-plan-reviewer, plan contra código y esquema real, confianza alta) B-N1, I2, I8, M10 y las partes (a) y (b) de B-N3 salen de lectura directa y se reproducen con los mismos archivos.
- (role-plan-reviewer, confianza alta sobre el hueco, media sobre su probabilidad) B-N2: el hueco de diseño es claro; la probabilidad depende de si ya hay etiquetas, y no lo verifiqué.
- (role-plan-reviewer, confianza media) Severidad de B-N3: bloqueante porque Juani aprobaría una protección que no opera. El efecto numérico de los reruns es menor que el cálculo independiente, porque las corridas están correlacionadas.
- (role-plan-reviewer, confianza media) Con N=16 el criterio es un filtro grueso, no una validación: aprueba 56% de las veces a un juez de 85% real, rechaza 21% de las veces a uno de 90% y deja pasar 10% a uno de 70%. Sirve para descartar un juez malo, no para afirmar "85% de acuerdo" en el paper. El reporte debería llevar conteo e intervalo, y el acuerdo no corrige por azar. Con cobertura forzada por régimen, tampoco estima el acuerdo sobre la distribución real de los 150. Es medible, y la decisión es de Juani.
- (role-plan-reviewer, confianza media) El alcance creció más de lo necesario en proceso de fondo, verificación runtime y extracción; y menos de lo necesario en cómo se produce la referencia humana de calibración.

## SUPOSICIÓN

- No consulté ninguna base: no sé si la muestra está cargada ni si hay etiquetas, ni si `esquema_v1.json` es igual al esquema cargado.
- No probé el gateway: que el handler siga tras un corte del cliente (I4) es razonado.
- Duración de corridas (I3) estimada, sin medir latencias reales.
- Vida del token de Clerk (I10) no verificada.
- No sé si hay otro ambiente desplegado además de `main`.
- Todo lo dicho sobre el juez futuro es análisis de plan, no comportamiento observado.

## Fuentes leídas

Completos: `proposal.md`, `design.md`, `tasks.md`, los tres `specs/*/spec.md`, `informes/propose-1-plan-reviewer.md`, `informes/propose-2-planner.md`, `informes/LEEME.md`.
Código en la revisión indicada: `routes/estudio.py` (55-75, 135-260, 500-515, mapa), `routes/estudio_trabajo.py` (1-330, 384-530, 855-1030, mapa), `services/ctr_lectura.py`, `services/clients.py`, `services/estudio_muestra.py`, `services/estudio_esquema.py` (395-509, rg), `services/traza_ciega.py` (23-50, 92-132), `services/regimen_llm.py` (625-660), `routes/classify_ep.py` (rg), `main.py`, `models/estudio.py` (rg), `db/__init__.py` (rg), `tests/integration/conftest.py` (31-90), `Dockerfile`, alembic 0007 y `env.py` (rg); `apps/ai-gateway/.../routes/complete.py` (200-520), `services/budget_and_cache.py` (25-135), `providers/base.py` (rg, 95-112, 372-395), `services/byok.py` (rg), `config.py` (rg); `apps/api-gateway/.../routes/proxy.py` (25-150), `config.py` (rg); `evaluation-service` `correccion_ejecutor.py`, `correccion_worker.py`, `main.py` (tramos); `.github/workflows/ci.yml` y `e2e-smoke.yml` (tramos y rg); `scripts/check-rls.py`, `scripts/check-claude-md.py`, `Makefile` (rg); `docs/servicios/classifier-service.md` (rg); `infrastructure/postgres/init-dbs.sql` (rg). CLAUDE.md global, de proyecto y de repo; memoria `aserciones-que-pasan-sin-medir.md`.
Datos: solo `codebook/esquema_v1.json`. Listé nombres de archivo de esa carpeta. **Firewall:** no abrí `muestra_150.csv`, trazas, etiquetas humanas, `analisis_produccion/` ni veredictos de producción. No abrí `anclas_v1.json`: sus citas salen de E13 del intento 1.
Lecciones L-NNN: ausentes (E21).

## Contaminación por otros informes

Leí por encargo `propose-1-plan-reviewer.md` y `propose-2-planner.md`. Usé la disposición del planner como lista de afirmaciones a comprobar, y reverifiqué contra código lo que uso acá. De E13 y E14 del intento 1 (citas de anclas y codebook) dependo sin reverificar. Soy el mismo rol y modelo que escribió el informe del intento 1: esta no es una segunda opinión independiente de aquel. No consulté Engram ni informes de otros changes.

## Chequeos no ejecutados

- Suites de regresión y baseline: pytest ausente, y sin `uv sync` para no alterar el worktree.
- `make check-rls`, `make test-rls`, `alembic upgrade/downgrade`: requieren base; prohibido.
- Prueba contra ai-gateway real: fuera de alcance.
