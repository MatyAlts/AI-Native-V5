# Proposal: juez-estudio-codebook-v1

## Why

El estudio CIbSE 2027 (change `cibse-codificacion-ciega`) hace que dos codificadores humanos etiqueten a ciegas 150 episodios con el codebook MTAC v1. El paper compara un juez LLM contra esa referencia humana, pero el único juez que existe (`regimen_llm.py`, prompt `eje_fino_v1.2.0`) es el de PRODUCCIÓN: aplica otra regla, no conoce las decisiones del 04/11 y su salida se persiste donde la leen consumidores de producción. No hay ningún juez que aplique el codebook v1 como lo aplican los humanos, con la misma entrada (traza ciega), la misma regla de régimen y citas verificables. Sin ese juez, T-002 (correrlo sobre los 150) no tiene qué correr.

## Decisión humana (Juani, 06/11/2026): opción B, sin calibración

Registrada acá porque cambia el método del paper:

- **Sin calibración.** No hay conjunto de ajuste ni de prueba, ni episodios nuevos de calibración, ni sorteo, ni umbrales de acuerdo, ni variantes de prompt.
- **Prompt fijado de antemano** desde el codebook v1 congelado (secciones 1 a 9) más instrucciones mínimas de formato y de citas, y el contrato de salida derivado del esquema del estudio, sin ejemplos sacados de resultados.
- **Sin ajuste por resultados, y su límite (lo que firma Juani)**: antes de congelar solo se admite corregir fallas técnicas de formato. Cada corrida muestra la coincidencia con la respuesta consensuada ANTES de que alguien decida si cambia el prompt o el modelo, y el código NO puede impedir ese cambio: solo lo hace visible. Cambiar el prompt O el modelo respecto de la corrida anterior exige un `motivo` (422 si falta), y la configuración congelada guarda cuántas corridas, prompts y modelos la precedieron y cuántos cambios se hicieron cuando la corrida anterior ya cumplía todo lo técnico (es decir, sin falla técnica que corregir). Hay una sola configuración por versión de codebook: tras congelar no se crean corridas nuevas de esa versión ni se vuelve a congelar (409 `ya_congelada`; decisión 10).
- **Ante un ancla de frontera que oscila entre repeticiones** (regla fijada de antemano): no se toca el prompt ni el modelo. La corrida queda como no cumplida y se puede repetir la misma configuración; cada repetición queda registrada y el paper la declara.
- **Las 5 anclas son solo una prueba técnica**: esquema válido, citas válidas, modelo efectivo correcto y estabilidad entre repeticiones. La coincidencia de contenido con la respuesta consensuada se registra y se muestra, pero no decide el congelado ni habilita ajustar el prompt.
- **Congelar** = fijar hash de prompt, hash de codebook, modelo efectivo y parámetros, con fecha, tras pasar una prueba técnica con condiciones medibles (cantidad mínima de repeticiones que no se puede degradar a 1; los episodios sin llamada al modelo no suman como éxito).

**Consecuencia para el método del paper**: el juez no queda calibrado ni validado antes de correr sobre los 150. El paper puede describirlo como un juez con prompt y modelo fijados antes de ver resultados y evaluado una única vez contra la referencia humana SOLO si en la configuración congelada `n_prompts_previos`, `n_modelos_previos` y `n_cambios_tras_cumplir` valen 0. Si no, debe declarar esos números y que los cambios se hicieron con la coincidencia a la vista; tampoco puede afirmar un acuerdo previo con los humanos. Que la configuración haya pasado la prueba técnica informa "cumplió una vez" (y cuántas corridas hubo antes, en `corridas_previas`), no "es estable". Cinco anclas con tres repeticiones prueban formato y estabilidad técnica, no validez de contenido.

## What Changes

- Un **juez del estudio** que trata al LLM como un codificador más: recibe lo que vería un humano para un ancla (traza ciega `traza_v1` con el tope de evidencia fijado, enunciado revisado, texto del codebook vigente congelado) y nada más: nunca el `episode_id`, etiquetas humanas, veredictos de producción ni las explicaciones de las anclas.
- **Vía de acceso (decisión de trabajo, SUPOSICIÓN hasta que firme Juani)**: endpoints nuevos del propio estudio (`routes/estudio_juez.py`, bajo `/api/v1/interrater/estudios/{clave}/juez/...`) con membresía ACTIVA de rol `investigador` del estudio. No hay script que hable con la base ni con el CTR. El pedido nunca trae `episode_id` ni `item_id`: el servidor resuelve las anclas de la versión vigente congelada del estudio.
- **Qué lee**: solo las anclas del propio estudio. No hay lectura de episodios fuera del estudio ni registro de episodios. La muestra de 150 queda bloqueada por construcción: no existe modo, columna ni FK hacia `estudio_muestra`, y cada paso verifica contra la base, antes de leer el CTR, que el episodio del ancla no esté en la muestra de NINGÚN estudio del tenant (dentro de un estudio ya lo impiden las escrituras; entre estudios no).
- **Corrida sin proceso de fondo**: `POST /corridas` crea la corrida; `POST /corridas/{id}/siguiente` procesa un par ancla-repetición por request (5 anclas x 3 repeticiones = 15 pasos), reanudable desde lo persistido.
- **Contrato de salida en el prompt**: el esquema de salida (derivado de `construir_json_schema`, con los nombres exactos de claves) viaja en el mensaje de sistema en todos los proveedores y forma parte de `prompt_sha256`; `response_format` se manda sin `strict` y no es la garantía. `prompt_sha256` cubre el armado completo de los mensajes y los parámetros de llamada. El juez no emite `regimen_propuesto` (decisión 9).
- La regla de régimen y la completitud se **reutilizan** de `services/estudio_esquema.py`; se admiten dimensiones vacías cuando el esquema declara `dimensiones_opcionales_si_regimen` para el régimen elegido (evidencia insuficiente legítima).
- **Citas** con gramática compatible con las humanas, validadas contra la traza; forma canónica y texto original.
- **Modelo efectivo**: se registra modelo, proveedor, `cache_hit` y `cost_usd`; mock, otro modelo o caché no cuentan y bloquean el congelado. Lista permitida de modelos en configuración. Referencia aleatoria por intento contra la caché del gateway.
- **Persistencia**: 3 tablas (`estudio_juez_corrida`, `estudio_juez_veredicto`, `estudio_juez_config`), RLS, inmutables; `raw_llm_output` no sale por la API.
- **Congelado** con criterio técnico recalculado en el servidor (design D8; exige exactamente 5 anclas x 3 repeticiones), coincidencia de contenido solo informativa, rastro de cada corrida y de cada cambio de prompt o de modelo.
- **Fuera de alcance**: correr sobre los 150 (T-002; ver design D13, "Qué le va a pedir T-002 a este diseño"), calibración, kappa, exportación humano+juez, cambios al codebook, UI, proceso de fondo.

## Capabilities

### New Capabilities
- `juez-estudio-acceso`: quién dispara y lee el juez, qué ítems puede leer (solo anclas), bloqueo de la muestra, lista de modelos, validaciones de entrada heredadas del codificador.
- `juez-estudio-codificacion`: el motor que produce un veredicto con misma entrada, regla y formulario que un codificador humano, con citas verificadas, modelo efectivo registrado y persistencia separada.
- `juez-estudio-congelado`: la prueba técnica paso a paso, el criterio técnico, la coincidencia informativa, el rastro y la configuración única por versión que habilitan fijar el juez.

### Modified Capabilities
- Ninguna. `cibse-codificacion-ciega` está en `main` (`178c343`) pero su change no está archivado: se trata como dependencia de código.

## Impact

- **classifier-service**:
  - Nuevos: `services/juez_estudio.py` (motor puro), `services/juez_corrida.py` (firewall, paso, resumen, criterio, congelado), `services/estudio_traza.py` (extracción mínima), `routes/estudio_juez.py`, `models/estudio_juez.py` (3 tablas), migración Alembic aditiva `0008`.
  - **Modificado sin cambio de comportamiento**: `routes/estudio_trabajo.py::traza_ciega` llama a `services/estudio_traza.py` (`enunciados_revisados`, `enunciado_del_item`, `comprobar_evidencia`); `_item_del_estudio` NO se mueve. `test_estudio_traza_db.py` y `test_estudio_separacion_db.py` deben pasar sin editarse. Es alcance a aprobar (decisión 4). `main.py`, `models/__init__.py` y `config.py` (lista permitida de modelos) registran lo nuevo.
  - `services/clients.py` NO se toca.
- **api-gateway**: sin cambios (`/api/v1/interrater` ya apunta a classifier-service). **ai-gateway**: sin cambios; se usa `/api/v1/complete`.
- **Datos**: envía el contenido de 5 episodios de alumnos (las anclas, ya vistos por los codificadores) al proveedor LLM vía ai-gateway; guarda salidas del modelo en `classifier_db` bajo RLS. Nunca lee contenido de los 150.
- **No se tocan**: `regimen_llm.py`, `routes/classify_ep.py`, `services/review.py`, `correccion_nativa.py`, `apps/web-teacher`, `tutor-service`, `ctr-service`, `academic-service`, `estudio_esquema.py`, `traza_ciega.py`, `estudio.py`.
- **Deploy**: classifier-service con una migración aditiva; `verificar_esquema_juez` falla cerrado si faltan tablas.

## Clasificación

**CRITICAL** (propuesta; la decide Juani). Reevaluada con la superficie reducida por la opción B.

Lo que se achicó: sin registro de episodios con `episode_id` del pedido, sin lectura fuera del estudio, sin proceso de fondo que siga leyendo tras el request, sin muestra, un solo flujo de 15 llamadas sobre 5 episodios ya vistos por los codificadores.

Lo que se mantiene y justifica CRITICAL por riesgo y no por líneas:
- Autorización nueva: endpoints que, bajo identidad de usuario, activan la cuenta de servicio `ESTUDIO_LECTOR_SERVICE_USER_ID` (lee cualquier episodio del tenant) y envían contenido de alumnos a un proveedor externo. Es la frontera de datos sensibles y de cuenta de servicio que la regla del proyecto fija como CRITICAL aunque el diff sea chico.
- Integridad de lo que mide el paper: el congelado fija la configuración que T-002 correrá sobre los 150; un firewall o un hash roto contamina la validez metodológica en silencio.
- Persistencia auditable nueva con triggers de inmutabilidad y RLS.

Juicio (role-planner, confianza media): HIGH sería defendible por el radio de impacto de 5 episodios, pero el cruce de la cuenta lectora con el proveedor externo y el carácter de registro de auditoría del congelado se mantienen. Si Juani prefiere HIGH, lo escribe en `## Aprobación`; el planner no lo decide.

Qué implica CRITICAL: cinco roles separados; aprobación humana fechada en `## Aprobación`; **un mutante por cada aserción de seguridad/datos** (tabla aserción-mutante-test en tasks.md sección 8); verificación en rondas hasta limpio con chequeos independientes del auditor; **recorrido humano real con el proveedor de identidad (Clerk)** antes de archivar (ambiente: decisión 6); caminos no recorridos son DEUDA con nombre.

## Decisiones pendientes para Juani

Cada una trae la recomendación del planner; la decisión es de Juani.

1. **Vía de acceso y nivel**: endpoint del estudio con membresía de investigador (base de este plan) y clasificación CRITICAL (o HIGH). Recomendación: como está.
2. **Proveedor, modelo y consentimiento**: ¿qué modelo(s) entran en `JUEZ_MODELOS_PERMITIDOS`? ¿el convenio del estudio cubre enviar trazas de las 5 anclas a ese proveedor? ¿de dónde sale la key (tenant o env; el juez pasa `materia_id=None`)? Nota: un modelo con namespace (`google/gemini-2.5-flash`) sale por OpenRouter si hay key y por el proveedor nativo si no; por cada modelo hay que decir qué ruta toma. El contrato de salida viaja en el prompt, así que el plan vale por cualquiera de las dos rutas.
3. **Valores técnicos y qué pasa si la estabilidad falla**:
   - `REPETICIONES_V1 = 3` (15 llamadas) y `N_ANCLAS_V1 = 5` (exactas; con menos no se congela).
   - `ESTABILIDAD_MIN_V1`: propuesto 1.0 (las 5 anclas con el mismo régimen en las 3 repeticiones). Es coherente pero frágil: 2 de las 5 anclas son de frontera, la referencia cambia en cada repetición (se mide sensibilidad, no determinismo), la condición exige además 15 de 15 `ok` (un `llm_caido` transitorio la rompe) y, sin tope de corridas, se pasa repitiendo. **Recomendación: 0.8** (4 de 5), con el ancla inestable nombrada en el criterio. Con 1.0 la única salida ante una ancla de frontera que oscila es repetir la corrida.
   - **Regla ante inestabilidad de una ancla de frontera** (arriba, "Ante un ancla de frontera que oscila"): no se toca prompt ni modelo; se repite la misma configuración y se declara. Recomendación: aceptar la regla.
   - **Tope de corridas por configuración**: el plan no lo tiene (elegiste dejar rastro). Si lo querés, se recomienda 3 corridas de la misma configuración antes de exigir `motivo`. Recomendación: sin tope, con el rastro de `corridas_previas` y la regla del paper.
   - Aviso: si algún ancla produce `sin_contenido`, el criterio es inalcanzable.
4. **Alcance ampliado**: autorizar tocar `routes/estudio_trabajo.py::traza_ciega` (extracción de 3 piezas, sin cambio de comportamiento).
5. **T-002** queda como change aparte con migración, firewall inverso, ejecutor a escala y aprobación propios (design D13).
6. **Ambiente del recorrido con Clerk**: EasyPanel deploya `main`, y la regla de publicación pide archivar antes de publicar, mientras el recorrido pide código desplegado antes de archivar. Opciones: (a) excepción documentada: merge a `main`, deploy de classifier-service, recorrido, archivo; (b) un ambiente de pruebas con Clerk si existe (no sé si existe); (c) archivar con el recorrido como DEUDA con nombre. El recorrido envía contenido real de 5 anclas al proveedor, así que depende de la decisión 2.
7. **CI**: hoy CI no corre la integración de classifier ni `check-rls` sobre `classifier_db`. ¿Se agrega un job (alcance nuevo) o queda como DEUDA con dueño Juani? Por defecto: DEUDA. Consecuencia que se firma: las garantías de acceso, firewall, inmutabilidad, RLS y persistencia de abortos quedan sin red ante regresiones futuras (solo se prueban en la revisión entregada); la lógica pura sí corre en CI.
8. **Operación sin UI**: se opera por API con el Bearer de un investigador (runbook). ¿Alcanza?
9. **`regimen_propuesto`**: el humano puede discrepar de la regla proponiendo otro régimen (se persiste y se exporta). El juez NO tiene ese canal en este plan: si afirma un régimen distinto del que da la regla, queda `inconsistente` y cuenta contra el criterio. Recomendación: dejarlo fuera (el juez aplica la regla). Si lo querés incluir, el campo entra al contrato, al hash y a la tabla de veredictos (design D7).
10. **Qué configuración rige y si se puede volver a congelar**: el plan dice una sola por versión de codebook (409 `ya_congelada`, y no se crean corridas nuevas de esa versión). Alternativa: reemplazo con `motivo`, rige la más reciente y cada reemplazo cuenta como ajuste en el paper. Recomendación: una sola.

## Respuestas de Juani a las decisiones (06/11/2026, en el chat)

Juani respondió "acepto todo, se usa el gemini flash lite 2.5". Registro del orquestador, no reemplaza `## Aprobación`:

1. Acceso por endpoint del estudio con membresía de investigador; nivel CRITICAL.
2. Modelo: `google/gemini-2.5-flash-lite` (lista permitida de un solo modelo). Distinto del juez de producción (`google/gemini-2.5-flash`): la comparación entre jueces no aísla el efecto de las reglas, porque cambian reglas y modelo a la vez; el paper lo declara. Consentimiento del convenio: SIN CONFIRMAR, se confirma en `## Aprobación`.
3. `N_ANCLAS_V1 = 5`, `REPETICIONES_V1 = 3`, `ESTABILIDAD_MIN_V1 = 0.8`. Ante un ancla de frontera que oscila no se toca prompt ni modelo, se repite la misma configuración y se declara. Sin tope de corridas.
4. Autorizado tocar `traza_ciega` (extracción de 3 piezas, sin cambio de comportamiento).
5. T-002 es un change aparte.
6. Recorrido con Clerk: excepción documentada, deploy de `main` coordinado, recorrido y recién después archivar.
7. CI: DEUDA con dueño Juani; acceso, firewall, inmutabilidad, RLS y persistencia de abortos quedan sin red ante regresiones futuras.
8. Operación por API con Bearer, sin UI.
9. `regimen_propuesto` fuera del contrato del juez.
10. Una sola configuración por versión (409 `ya_congelada`).

## Knowledge Base Impact

- `docs/adr/064-juez-estudio-codebook-v1.md`: NUEVO (APPEND). Decisiones de design.md, incluida la opción B y su consecuencia para el método del paper. No se toca `docs/adr/README.md` (índice congelado, deuda conocida).
- `CLAUDE.md` del repo: **REWRITE** de dos invariantes ADR-063: (a) «Las tablas del estudio de codificación solo las leen endpoints del estudio» pasa a nombrar `routes/estudio_juez.py` y las tres tablas nuevas; (b) la regla de la cuenta lectora agrega que `routes/estudio_juez.py` la usa solo con `episode_id` de anclas del estudio del caller, tras el firewall, y que ese contenido termina en un proveedor externo. **REWRITE** de «63 ADRs» a 64 (lo exige `check-docs`/`scripts/check-claude-md.py`). **APPEND**: invariante del juez del estudio y constantes `PROMPT_VERSION` y `prompt_sha256` golden.
- `docs/servicios/classifier-service.md`: REWRITE de tablas y endpoints; APPEND del runbook (obtención del Bearer, 15 pasos, lectura del resumen, congelado) y de la verificación post-deploy.
- `docs/SESSION-LOG.md`: APPEND.
- `../obsidian.md`: el planner no lo edita. Para el orquestador: REWRITE de `Estado actual`/`Últimos avances`/`Próximos pasos` (juez construido, congelado o no; T-002 pendiente) y APPEND en `Decisiones clave` de la opción B, con su consecuencia para el método del paper.
- Lecciones L-NNN: ausentes (ruta buscada `docs/`).

## Aprobación

<!-- Sección reservada para el humano. El planner no la completa. -->

Aprobado por Juani Sarmiento el 06/11/2026. Alcance: change juez-estudio-codebook-v1, nivel CRITICAL, con las 10 decisiones registradas en este proposal y modelo google/gemini-2.5-flash-lite. Confirmo que el convenio del estudio permite enviar las trazas de las 5 anclas a ese proveedor. La corrida sobre los 150 no queda aprobada: va en T-002.
