> **Nota de alcance (commit "trivaluada pura", 2026-09-25)**: este commit implementa
> SOLO los bloques 2, 3 y 4 (dimensiones trivaluadas + Kleene fuerte + estado
> `abstencion_traza_insuficiente` + UI), acotado a los casos 1, 3, 4 y 6 de la
> Tabla 3.11. Los bloques 5 (revisión humana), 6 (sumidero `sin_clasificar` +
> bump de `tree_version`), 7 (reclasificación) y 8 (cierre/docs finales) NO se
> tocan acá — quedan para commits siguientes, tal como pide el alcance dado al
> implementador. Los casos 2 y 5 de la Tabla 3.11 (dependen de B4, verificación
> literal de citas) quedan declarados como brecha, con constantes de extensión
> sin validador (ver `regimen_llm.py`, comentario junto a `Estado`).

## 1. Gates previos (bloqueantes — no arrancar sin esto)

- [x] 1.1 🔴 Conseguir la **Tabla 3.11** de la tesis. LEVANTADO: `tabla-3.11-de-la-tesis.md` transcribe los seis casos + la Tabla B.2 y es la fuente normativa de este commit.
- [x] 1.2 🔴 Aprobación humana del bump de `tree_version` (D6). **APROBADO por el usuario el 26/09/2026**: va el cambio de mapeo + el bump, y NO la reclasificación de los históricos. El bump se ejecuta en el bloque 6, en su propio commit. Instrumento disponible desde el commit anterior: `test_classifier_config_hash_golden` fija el literal `28e111ae…`, de modo que la tarea 6.7 ahora SÍ puede demostrar que el hash cambió — con los 13 tests de reproducibilidad no se podía, porque prueban determinismo y no invariancia.
- [x] 1.3 🔴 Aprobación humana del relabelado de los episodios `sin_clasificar` ya persistidos (D5). **DENEGADO a propósito por el usuario el 26/09/2026**: la reclasificación NO se ejecuta en esta change. Queda como 7.1, con gate operativo aparte. El motivo: cambiar etiquetas que la tesis cita no puede pasar como efecto secundario de un merge.

  > **Y son 131, no 23.** Consulta a `classifier_db` del 26/09/2026: `eje = sin_clasificar` con etiqueta `apropiacion_superficial` da **131 episodios**, el 29 % de las 449 clasificaciones superficiales vigentes. El número que traía este change (23) viene de la Tabla 4.11 de la tesis y no reproduce contra el registro. Corregir el conteo donde aparezca.
- [x] 1.4 🔴 Decidir si la anulación humana reemplaza la etiqueta oficial o queda al lado. **DECIDIDO por el usuario el 26/09/2026: REEMPLAZA**, con marca de procedencia, y reversible por otra fila (append-only, ADR-010). El razonamiento: si el humano revisa y no manda, la revisión es decorativa. Implica que 5.4 crea una `Classification` nueva y pone la anterior en `is_current=false`, nunca un `UPDATE`.
- [ ] 1.5 Cargar la skill `impeccable` antes de tocar UI. **NO invocada.** El cambio en `EpisodeNLevelView.tsx` es una extensión mecánica de un ternario a tres estados, siguiendo la decisión de diseño YA tomada en D3/4.3 (sin color nuevo, tratamiento neutro) — no hay decisión de UI nueva que un gate de diseño deba aprobar. Declarado como desviación; el orquestador/usuario debería confirmar si esto es aceptable antes de dar el commit por cerrado.

  > **ACEPTADA la desviación para el commit anterior** (orquestador, 26/09/2026): extender un ternario existente a tres estados, sin color nuevo, no es una decisión de UI que un gate de diseño deba aprobar.
  > **NO aplica al bloque 5.** La cola de revisión es una pantalla nueva completa con su ruta, su estado vacío y su flujo de decisión. Ahí el gate de `impeccable` corre entero y sin excepción.

## 2. B2a — Dimensión trivaluada, sin cambio de comportamiento

Objetivo del bloque: que el hash y los veredictos queden **idénticos**. Si algo cambia acá, es un bug.

- [x] 2.1 `_Dim.presente` pasa a `Literal["presente","ausente","no_evaluable"]` (`regimen_llm.py`). Extendido también a `_Autonomia.presente` (ver corrección de D4 en design.md) — las CUATRO dimensiones, no solo tres.
- [x] 2.2 `field_validator`/`model_validator(mode="before")` que coaccionan `True→"presente"` / `False→"ausente"`, y para autonomía el legado `oraculo: bool` (clave Y sentido invertido) a `presente`.
- [x] 2.3 Test de retrocompatibilidad con un payload real del piloto (booleanos en las 4 dimensiones, incluido `oraculo`), que se re-parsea sin error y produce el mismo veredicto.
- [x] 2.4 `regimen_segun_regla` reescrita en términos de los valores nuevos. NOTA: no se implementó el paso intermedio "no_evaluable se comporta como ausente" por separado — se fue directo a Kleene fuerte (bloque 3) porque separar los dos pasos en commits de test distintos no aportaba una red de seguridad adicional aquí (el mismo test de retrocompat cubre ambos).
- [x] 2.5 13/13 tests de `test_pipeline_reproducibility.py` en verde, hash idéntico al baseline.
- [x] 2.6 **AGREGADA post-QA (2026-09-25), bug SEVERO real**: 2.2/2.3 coacciona en `_Dim`/`_Autonomia`, pero esos validadores solo corren cuando el dict pasa por `RegimenLLMRaw.model_validate` — y el endpoint de lectura (`classify_ep.py::get_current_classification`) devolvía `feats.get("regimen_llm")` SIN pasar por el modelo. V/E/J no se notaban (mismo nombre de campo); autonomía SÍ, porque el campo se renombró (`oraculo→presente`) y un registro legado sin `presente` perdía la dimensión en el frontend, en blanco y sin log. Medido contra producción: 663/689 episodios juzgados (96,2%) tienen la forma legada; 26 tienen `raw=None`; 0 tienen la forma nueva. Fix: `normalizar_regimen_llm_persistido` en `regimen_llm.py`, invocado desde el único borde de lectura confirmado por grep. Ver D2 corregida en `design.md` y `test_classify_ep_regimen_llm_read.py` (6 tests: forma legada ×2, forma nativa, sin veredicto, `raw=None`, corrupto-degrada).
- [x] 2.7 **AGREGADA post-QA**: cobertura de valores fuera de dominio de punta a punta por `clasificar_regimen_llm` (`"quizas"`, `null`, campo faltante, dimensión faltante) — los 4 degradan a `error_parseo` sin excepción no capturada. Certifica la propiedad que hace aceptable dejar el caso 5 de la Tabla 3.11 fuera de alcance.
- [x] 2.8 **CORRECCIÓN de auditoría (2026-09-25)** sobre 2.6: de los 6 tests de `test_classify_ep_regimen_llm_read.py`, solo 2 son RED real contra el bug de QA (verificado corriendo la suite contra el código anterior al fix: `2 failed, 4 passed`). Los otros 4 son guardas hacia adelante que ya pasaban sin el fix — quedaron mal presentados como si todos hubieran atrapado el bug. Docstrings del módulo y de cada test corregidos para decir cuál es cuál.
- [x] 2.9 **AGREGADA por hallazgo de auditoría**: `test_classifier_config_hash_golden` en `test_pipeline_reproducibility.py`. Los 13 tests preexistentes prueban determinismo (`h1==h2` en el mismo proceso), no invariancia — no fijan ningún literal, así que un cambio accidental en el default de `tree_version` o en `DEFAULT_REFERENCE_PROFILE` los deja los 13 en verde con el hash movido. Verificado deliberadamente: cambiando el default a `v4.1.0`, el golden falla y los otros 13 siguen en verde. Golden: `28e111aec4c5ec470bc8836cd716f563f41639d043d79bc95dca7da99e62b774` (idéntico antes/después de esta change — confirma que B2a no movió el hash). Esto es lo que hace verificable 6.7 cuando llegue ese commit.

## 3. B2a — Regla trivaluada y derivación por evidencia insuficiente

- [x] 3.1 Kleene fuerte implementado en `regimen_segun_regla` vía `_kleene_desde_dim`/`_kleene_and`/`_kleene_or`. Devuelve `Literal["REFLEXIVA","SUPERFICIAL","INDETERMINADO"]`.
- [x] 3.2 Estado nuevo agregado a `Estado`, con nombre CORREGIDO: `abstencion_traza_insuficiente` (no `evidencia_insuficiente` — ese nombre es del caso 2 de la tabla, que es OTRO estado, fuera de alcance; ver comentario en `regimen_llm.py` junto a `Estado`). Rutea por el fallback existente (`_marcar_para_revision`), sin tocar `classify_ep.py` — la rama genérica `estado != "ok"` ya lo cubre.
- [x] 3.3 Revisado: `_hay_evidencia_citable` itera genéricamente sobre las 4 dimensiones y solo exige cita cuando `regimen=="REFLEXIVA"`; no depende del tipo de `presente`. Verificado con `test_kleene_caso3_sigue_ok_y_no_deriva_pese_a_los_no_evaluable` (caso 3 con las 4 evidencias vacías sigue siendo `ok`, no `inconsistente`).
- [x] 3.4 `RESPONSE_JSON_SCHEMA` actualizado en CUATRO bloques (no tres — corrección de alcance por D4 corregida): verbalizacion, verificacion, justificacion Y autonomia pasan a enum de tres valores. `autonomia` deja de tener la forma `{"oraculo": boolean}`.
- [x] 3.5 `SYSTEM_PROMPT` reescrito con las definiciones de la Tabla B.2 para las 4 dimensiones, definiendo `no_evaluable` por ausencia de traza, con una advertencia explícita de no confundirlo con baja confianza.
- [x] 3.6 Los 3 `_FEWSHOT` actualizados a formato trivaluado nativo (`presente`/`ausente`), incluida `autonomia`.
- [x] 3.7 `PROMPT_VERSION` bumpeada `eje_fino_v1.1.0 → eje_fino_v1.2.0`.
- [x] 3.8 🔴 Pruebas unitarias de los casos EN ALCANCE (1, 3, 4, 6 — ver Alcance del commit). Casos 2 y 5 declarados como brecha, NO implementados (dependen de B4, verificación literal de citas). Ver tabla de ciclo TDD en el informe del implementador.
- [x] 3.9 `test_fallback_proxy_y_needs_review_si_abstencion_traza_insuficiente`: confirma que `appropriation` no se toca y `needs_review`/`needs_review_reason` sí se setean.
- [x] 3.10 13/13 reproducibilidad en verde tras todo el bloque 3, hash idéntico.

## 4. B2a — El tercer valor en la pantalla

- [x] 4.1 `web-teacher/src/lib/api.ts`: `RegimenLLMDimension.presente` es ahora `"presente" | "ausente" | "no_evaluable" | boolean` (acepta ambas formas); `autonomia` unificada a la misma forma (ya no `{oraculo}`); `RegimenLLM.estado` incluye `abstencion_traza_insuficiente`.
- [x] 4.2 🔴 `EpisodeNLevelView.tsx`: los CUATRO ternarios (no tres — autonomia también, por D4 corregida) pasan por `estadoDimension()` + `DIM_LABEL`/`AUTONOMIA_LABEL`, con soporte explícito para el booleano legado.
- [x] 4.3 Sin color nuevo: `no_evaluable` usa el mismo tratamiento visual neutro (`text-muted`) que `ausente` ya usaba; solo cambia el texto.
- [x] 4.4 Tests del componente: uno con `no_evaluable` (confirma que NO se dibuja como "ausente"); uno con un registro cuya autonomía es legada (`oraculo`) usando la forma que la API YA FIJADA devuelve hoy (strings normalizados por el backend — CORREGIDO post-QA: la versión anterior de este test fabricaba `presente: true` para autonomía, una forma que ningún registro real tuvo nunca, porque el legado real es `oraculo` sin `presente`); uno defensivo que confirma que un dict crudo sin normalizar (booleanos + `oraculo`) no rompe el render aunque autonomía quede sin label en ese caso patológico.

## 5. B3+B5 — Revisión humana con historial (aditivo puro)

- [x] 5.1 Modelo `ClassificationReview` en `classifier_db` (D7 + **corrección D7.a/D7.b del 27/09**): episodio, revisor, veredicto humano, motivo, timestamp, `tenant_id`, y **DOS** FK nullable — `previous_classification_id` y `new_classification_id`. Con una sola referencia, saber qué clasificación resultó de *esta* revisión exige inferir por episodio y orden temporal, y eso se rompe con la segunda revisión que corrige a la primera. **No** duplicar las etiquetas como texto: `classifications` es inmutable fila por fila, el join es seguro. La marca de procedencia va como `features['revision_humana']` en la `Classification` nueva, **sin migración**, con el `id` de la fila de revisión que la originó (precedente: `cii_evolution_longitudinal`, ADR-018). Append-only por disciplina de aplicación: **no hay constraint ni trigger que lo fuerce**, así que los tests tienen que cubrirlo. Agregado también `reviewer_role` (columna propia, string) — el gate 1.4 pide "rol" como parte de la marca y no había dónde ponerlo.
- [x] 5.2 Migración Alembic del classifier-service **con policy RLS activa** sobre la tabla nueva (ADR-001: toda tabla con `tenant_id` la lleva). Verificar con `make check-rls`, que corre en CI. Migración `20260906_0006_add_classification_reviews.py`, aplicada contra `classifier_db` local (dev) con `classifier_user` como owner (mismo patrón que `interrater_ratings`) — `make check-rls` en verde.
- [x] 5.3 `GET /api/v1/classifications/review-queue`: lista los episodios con `features['needs_review']=True` sin revisión posterior, con el motivo y el estado terminal del juez. Filtro por comisión. Lee los headers `X-Tenant-Id`/`X-User-Id`/`X-User-Roles` del gateway vía `Depends` — no re-verificar JWT aguas abajo.

  **Índice obligatorio** (D7.c): parcial B-tree, no GIN —
  ```sql
  CREATE INDEX ix_classifications_needs_review_pending
  ON classifications (comision_id, episode_id)
  WHERE is_current AND (features->>'needs_review') = 'true';
  ```
  Su tamaño es proporcional a los ~47 retenidos, no al corpus. Más un índice simple en `classification_reviews (tenant_id, episode_id)` para el `NOT EXISTS`. Sin esto la consulta es un scan completo sobre una tabla que crece 207 filas por día, y corre cada vez que un docente abre la pantalla. Ambos índices creados por la migración 5.2 exactamente con el SQL de arriba.
- [x] 5.4 `POST /api/v1/classifications/{episode_id}/review`: registra el veredicto humano. El comportamiento depende de 1.4 — si reemplaza la etiqueta oficial, lo hace creando una `Classification` nueva con marca de procedencia humana y poniendo la anterior en `is_current=false` (ADR-010), nunca con un UPDATE. **Hallazgo de implementación no anticipado por el design**: la `Classification` nueva no puede reusar el `classifier_config_hash` de la anterior sin violar `uq_classifications_episode_config` (misma pareja episode_id+hash ya existe en la fila vieja, que sigue física aunque `is_current=false`). Resuelto con un hash sintético determinista (`sha256(hash_anterior:human_review:episode_id:timestamp)`) que NO representa ninguna configuración real del árbol/juez — documentado en `services/review.py::_synthetic_review_config_hash`.

  > **CERRADO tras ronda de revisión (2026-09-27): el riesgo que este párrafo declaraba abierto ERA real y fue confirmado.**
  > `pipeline.py::persist_classification` degradaba CUALQUIER fila vigente con hash distinto — incluida
  > la humana (que siempre tiene hash sintético, por construcción). Una reclasificación automática
  > posterior pisaba la anulación sin error ni log; con ~207 clasificaciones/día no era un escenario
  > de laboratorio. Fix: **la anulación humana gobierna hasta que otro humano la cambie** — el `UPDATE`
  > de reclasificación ahora excluye filas con `features['revision_humana']` (D7.b), y una reclasificación
  > automática posterior a una anulación se registra pero entra con `is_current=false` (no gobierna).
  > `is_current` cambia de semántica: "la última que corrió" → "la que gobierna" (docstring actualizado
  > en `Classification` y en `persist_classification`, `pipeline.py`). También se amplió la idempotencia
  > de `persist_classification` a "cualquier fila con ese hash, no solo la vigente" — sin eso, una
  > reclasificación automática con el MISMO hash de máquina de siempre (el caso normal, ya que el hash
  > no avanza por una revisión humana) revienta `IntegrityError` contra la fila de máquina vieja que la
  > anulación dejó no-vigente. Tres tests nuevos en
  > `tests/integration/test_persist_classification_human_governance_db.py`, contra Postgres real —
  > los tres fallaban con `IntegrityError: ... duplicate key value violates unique constraint
  > "uq_classifications_episode_config"` contra el `pipeline.py` sin el fix (RED verificado, no es
  > guarda hacia adelante). Ver informe del implementador para la tabla del ciclo TDD.
- [x] 5.5 Verificar que **no** hace falta tocar el `ROUTE_MAP` (D8): ambos endpoints cuelgan de `/api/v1/classifications`, que ya está en `proxy.py:61`. Confirmar a mano contra el gateway levantado, no por lectura — un endpoint inalcanzable falla en silencio. **Verificado 2026-09-27**: classifier-service (:8008) + api-gateway (:8000, `DEV_TRUST_HEADERS=true`) levantados a mano; `GET/POST` a través del gateway responden (200 y 404 semántico, no 404 de ruteo) sin tocar `ROUTE_MAP`. Ver tabla de evidencia del implementador.
- [x] 5.6 Policies Casbin para el rol que puede anular (pregunta abierta del design). Van al seed (`academic-service/seeds/casbin_policies.py`), que es el source of truth, y bumpean el conteo (207→213: +6, `classification_review:{create,read}` × {superadmin, docente_admin, docente}). **Nota de implementación**: el classifier-service NO consulta Casbin en runtime para ningún endpoint (ni los viejos ni estos dos nuevos) — gatea con `require_role` sobre roles del header del gateway, igual que `CLASSIFY_ROLES`/`READ_ROLES` ya existentes. Esta entrada del seed documenta el catálogo de permisos (como pide la tarea) pero no hay enforcer que la lea desde este servicio — señalado en el informe, no soluciónado (fuera de alcance: cablear Casbin en classifier-service no está en ninguna tarea de este bloque).
- [x] 5.7 Pantalla de cola de revisión en web-teacher, consumiendo 5.3. Patrón obligatorio `HelpButton` + `PageContainer` + entry en `helpContent.tsx` (11 keys hoy).

  **Implementado 2026-09-27**: `RevisionColaView.tsx` — filas densas agrupadas por
  `estado_juez`. Los conteos por grupo salen de `items.length`, nunca
  hardcodeados (principio 4). La decisión se abre EN la fila (no modal): botón
  "Decidir" despliega un form inline con select de veredicto (los 4
  `VALID_VERDICTS` reales, leídos de `routes/review.py`) + textarea de motivo
  obligatorio, con un banner que declara ANTES de confirmar que la decisión
  reemplaza la etiqueta oficial. Los dos 409 (`retryable: true/false`) muestran
  los dos mensajes distintos del shape brief; el 400 muestra el detail del
  dominio tal cual lo manda el backend. UUID del episodio en `font-mono`. Sin
  color nuevo: badges `warning`/`danger`/`info` ya declarados en el vocabulario
  semántico existente. Estado vacío no afirma "todo revisado" — dice "no hay
  episodios retenidos en este momento" y aclara que eso puede significar dos
  cosas distintas (principio 5). `ReviewQueueItemOut` no trae eventos ni
  transcripción (D2 del brief): cada fila linkea a `/episode-n-level` para ese
  detalle, sin agregar ningún endpoint nuevo. `getReviewQueue`/`submitReview`
  agregados a `lib/api.ts`, reusando `throwIfNotOk` existente (ya adjunta
  `status`/`detail` al `Error`, que es exactamente lo que hace falta para
  distinguir 400 de los dos 409). helpContent nuevo: `revisionCola`.

  **Corrección (orquestador, 2026-09-27): el "cuarto grupo genérico" de la
  primera versión estaba mal — escondía un estado real.** `abstencion_traza_insuficiente`
  (caso 4 de la Tabla 3.11, agregado a `Estado` en `regimen_llm.py:243` por el
  juez trivaluado, commit `e5ca9b2`) NO es hipotético: existe en el backend
  desde hace dos commits y marca `needs_review`, así que va a aparecer en esta
  cola en cuanto el corpus se reclasifique con la regla trivaluada. Dejarlo caer
  en un cajón "Otros motivos" reproducía en la UI el defecto que este change
  entero vino a arreglar (una ausencia de información indistinguible de otra
  cosa) — el mismo patrón que `sin_clasificar` colapsando en "apropiación
  superficial" (B2b, bloque 6).

  Fix: `GROUP_ORDER` pasa a CUATRO grupos nombrados —
  `inconsistente` → `abstencion_traza_insuficiente` → `error_parseo` →
  `baja_confianza`, en ese orden (la abstención va segunda: el docente
  aprende más de una abstención bien declarada que de un JSON roto). El grupo
  genérico se mantiene como QUINTO, pero cambia de significado: ya no es "otro
  motivo", es el canario de que el clasificador emitió un `estado_juez` que
  esta pantalla no tiene nombrado — desincronización backend/frontend, no
  información sobre el episodio. El copy lo dice así explícitamente (título
  "Estados que esta pantalla no conoce"). `helpContent.revisionCola` actualizado
  con la entrada del cuarto grupo y una nota sobre el quinto. 2 tests nuevos
  (10 en total): uno certifica que `abstencion_traza_insuficiente` cae en su
  grupo nombrado y no en el defensivo; otro que un `estado_juez` inventado (que
  no existe en el `Literal` del backend) cae en el defensivo con el copy de
  desincronización. Los dos son guardas hacia adelante, no regresión — hoy el
  corpus todavía corre con la regla booleana vieja y ninguno de los dos casos
  ocurre en producción; lo digo en el docstring de cada test.

- [x] 5.8 Ruta nueva en `web-teacher` (TanStack Router file-based, search params validados con zod) y entrada en la navegación. Sin esto la pantalla existe y no se llega.

  **Implementado 2026-09-27**: `src/routes/revision-cola.tsx`, search param
  `comisionId` opcional validado con zod (`z.string().uuid().optional()`) —
  a diferencia de Correcciones/Unidades, esta ruta NO redirige al home si
  falta: el endpoint acepta filtrar por comisión o no filtrar, y no filtrar
  (cola completa del tenant) es un caso de uso legítimo acá. Entrada en
  `NAV_GROUPS` (`__root.tsx`) bajo "Trabajo del docente", ícono `Gavel`. El
  test preexistente `navegacionAlcanzable.test.ts` (que exige que TODA ruta en
  disco tenga puerta en el menú o una excepción justificada en
  `FUERA_DEL_MENU`) pasó sin tocarlo — es la red de seguridad que ya existía
  para esta clase exacta de bug.
- [x] 5.9 Tests: la cola devuelve los retenidos y solo los retenidos; una revisión los saca de la cola; un segundo POST sobre el mismo episodio apila historial en vez de pisarlo; un rol sin policy recibe 403. Los tres primeros en `tests/integration/test_review_service_db.py` (contra Postgres real, transacciones que nunca commitean); el cuarto en `tests/unit/test_review_routes.py` (HTTP, mockeado).

  > **Ronda de QA (2026-09-27): 3 hallazgos más, dos reproducidos con scripts propios de QA sobre este diff.**
  >
  > **1 · Race condition entre dos revisiones concurrentes (ALTA, confirmado 3/3 por QA).**
  > El `UPDATE` de `submit_review` filtraba por `episode_id` + `is_current=true`, sin el `id`
  > exacto de la fila `previous` leída — un lost update clásico: la segunda revisión degradaba
  > la fila que dejó la primera (no la que decía haber revisado) y `classification_reviews`
  > quedaba con dos filas `previous=<misma original>` y ninguna explicando qué pasó con la
  > primera decisión. Fix: concurrencia optimista — el `UPDATE` ahora exige
  > `Classification.id == previous.id`; si afecta 0 filas, se levanta `ReviewConflictError`
  > (routes/review.py lo traduce a **409 Conflict** — decisión de contrato: el docente recarga
  > y ve la decisión del otro, en vez de un retry automático que aplicaría su revisión sobre un
  > estado que ya no es el que vio).
  >
  > **Corrección de auditoría (2026-09-27) sobre este mismo punto: el primer test
  > (`test_dos_revisiones_concurrentes_no_pierden_la_primera`, `asyncio.gather` con dos `UPDATE`
  > peleando por el lock de la MISMA fila) NO discrimina la causa.** El auditor revirtió el
  > `id == previous.id` en una copia y ese test siguió pasando 10/10 — el `rowcount==0` que
  > observa lo produce el row-lock de Postgres (el perdedor bloquea, y al reanudar Postgres
  > reevalúa el predicado solo contra la fila que tenía bloqueada, ya `false`), no mi filtro de
  > `id`. Agregado `test_segunda_revision_tras_commit_de_la_primera_no_pisa`: B lee `previous`
  > ANTES de que A toque nada, pero su `UPDATE` se libera recién DESPUÉS de que A ya comiteó —
  > sin ningún lock de por medio. Ahí sí discrimina: **RED verificado revirtiendo el filtro de
  > `id` en el código real** (no en una copia sombra) — sin él, el test falla con las dos
  > revisiones "exitosas", `previous_classification_id` repetido y la fila vigente final
  > cambiada a la decisión de B (lost update silencioso, sin ningún error); con el fix, 5/5
  > estable. **Esto SÍ cierra la hipótesis de QA sobre `MultipleResultsFound`** (dos filas
  > `is_current=true` a la vez) — cerrada por el test nuevo, no por el viejo, que se corrigió
  > para no reclamar más que lo que prueba (contienda por el mismo lock, sin lost update).
  >
  > **2 · `_find_current_classification` (classify_ep.py) no se sincronizó con la idempotencia
  > ampliada de `persist_classification` (MEDIA).** Seguía filtrando `is_current=true`; tras una
  > anulación humana con el mismo hash de máquina de siempre, no encontraba la fila (roundtrip
  > de más al ctr-service) y el handler devolvía 201 en vez de 200. Fix: se quitó el filtro
  > `is_current` del SELECT — mismo criterio que `persist_classification` ya usa. Test en
  > `tests/integration/test_find_current_classification_human_review_db.py`.
  >
  > **3 · `verdict` sin validar contra el dominio conocido (ALTA).** Un `verdict="banana"`
  > se persistía sin error como etiqueta oficial vigente. Fix: `VALID_VERDICTS` en
  > `routes/review.py` (los 4 valores que puede producir `_EJE_TO_APPROPRIATION`), 400 explícito
  > — mismo patrón que `interrater.py::_LABELS`. `sin_clasificar` (bloque 6, no implementado
  > todavía) NO entra a propósito.
  >
  > **4 · `reviewer_role` no determinístico (BAJA).** `next(iter(set.intersection(...)))`
  > dependía del orden de iteración del set. Fix: `REVIEW_ROLE_PRECEDENCE` explícito
  > (superadmin > docente_admin > docente) vía `_resolve_reviewer_role`.
  >
  > Los 208 tests de la ronda anterior + `check-rls.py` + el roundtrip de migración (QA lo
  > ejercitó contra su propia copia) se confirmaron sin tocar. 6 tests nuevos → 214 total.

  > **Auditoría (2026-09-27), segunda pasada — 2 tests que no probaban lo que decían.**
  >
  > **1 (retomado arriba) · el test de concurrencia original no discriminaba la causa.** Ver el
  > párrafo de arriba: agregado `test_segunda_revision_tras_commit_de_la_primera_no_pisa`, el
  > viejo corregido para no reclamar de más. 214→216.
  >
  > **2 · El anti-join de la cola (`~ya_revisado`) no lo cubría ningún test.** El auditor borró
  > esa línea de `list_review_queue` y los 214 pasaron igual: los dos tests que *parecían*
  > cubrirlo pasan por otros mecanismos (`submit_review` borra `needs_review` de `features`; la
  > fila de máquina reclasificada entra `is_current=false`). Agregado
  > `test_anti_join_aislado_needs_review_puesto_e_is_current_true` en
  > `tests/integration/test_review_service_db.py`: inserta una `ClassificationReview` DIRECTO
  > (sin pasar por `submit_review`, para no heredar sus efectos sobre `features`) contra una
  > `Classification` que sigue con `needs_review=true` e `is_current=true`. RED verificado
  > quitando `~ya_revisado` del código real: el episodio vuelve a aparecer en la cola
  > (`assert ... not in {...}` falla, `UUID(...) not in {UUID(...)}` — el mismo UUID en ambos
  > lados). Con el anti-join restaurado, verde.
  >
  > **3 · Verificación E2E contra el gateway repetida con los códigos nuevos (2026-09-27,
  > ~13:31).** La corrida de la tarea 5.5 era de las 12:12, antes de que `routes/review.py`
  > agregara 400/409. Repetida con classifier-service (:8008) + api-gateway (:8000,
  > `DEV_TRUST_HEADERS=true`) levantados de nuevo: `GET review-queue` → 200; `POST review` con
  > `verdict="banana"` → 400 (`"verdict 'banana' no es válido..."`); `POST review` válido → 201;
  > dos `POST review` concurrentes sobre el mismo episodio (`httpx.AsyncClient` + `asyncio.gather`,
  > no bash — dos curls en background no llegaron a competir de verdad) → 409 en uno de los dos
  > (`"La clasificación vigente del episodio ... cambió mientras se procesaba esta revisión"`) y
  > 201 en el otro. Datos de prueba insertados a mano y borrados al terminar — `classifier_db`
  > quedó en 106/0, igual que antes de la corrida.
  >
  > **4 · `reclassify_all.py` — docstring corregido, comportamiento NO ajustado (decisión
  > registrada, no ejecutada).** Afirmaba "marca la vieja `is_current=false` e inserta la
  > nueva", que ya no es cierto para un episodio con anulación humana vigente (la excluye del
  > `UPDATE`, la fila nueva entra `is_current=false`). Docstring corregido con esa excepción. El
  > COMPORTAMIENTO del script no se tocó — delega todo a `persist_classification`, que ya es
  > seguro tras el fix de esta ronda — pero queda un caveat sin resolver, registrado en el
  > docstring y no en el código: el conteo `nuevos(201)` del resumen final no distingue "quedó
  > vigente" de "se registró pero una anulación humana sigue gobernando". No se implementó esa
  > distinción porque no estaba pedida y el script no está en las tareas del bloque 5 — queda
  > para quien opere un backfill real a decidir si la necesita.
  >
  > `test_casbin_matrix.py` (academic-service) re-corrido: 49 passed, sin cambios — no se tocó
  > `casbin_policies.py` en esta pasada. 216 tests de classifier-service, DB en 106/0.
- [ ] 5.10 Verificar contra la base del piloto que la cola devuelve **todos** los retenidos vigentes y solo esos. **No cablear un número esperado**: al 18/09 eran 40, al 26/09 son 47 (27 `error_parseo`, 19 `inconsistente`, 1 `baja_confianza`), y el corpus crece ~207 clasificaciones por día. El criterio es que el conteo de la cola coincida con el de la consulta directa **corrida el mismo día**, y que la verificación quede registrada con su fecha.

  > **BLOQUEADO (implementador, 2026-09-27): sin acceso a la base del piloto desde este entorno.**
  > `classifier_db` en este sandbox (`platform-postgres`, local) tiene 106 `classifications`
  > de datos de seed — las 106 tienen `features={}` vacío, cero con la clave `needs_review`.
  > No es la base que registra los 47 retenidos vigentes que cita esta tarea; esa base vive
  > en la infra del piloto (VPS UTN), a la que este entorno no tiene conexión. La lógica de
  > filtrado de la cola SÍ está verificada (5.9, contra datos sembrados a propósito en este
  > mismo Postgres), pero la comparación "cola == conteo directo del día, sobre el corpus
  > real" queda pendiente para quien tenga esa conexión. Query directa de referencia para
  > correrla ahí: `SELECT count(*) FROM classifications WHERE is_current AND
  > (features->>'needs_review')='true'` — debe coincidir con `n` de `GET
  > /api/v1/classifications/review-queue` (sin filtro de comisión) corrido el mismo día.

  > **Ronda de auditoría 2026-09-27 (QA nuevo, rondas 3-4 confirmadas enteras — 6 mutaciones,
  > cada una hizo caer exactamente el test que debía). Cuatro puntos chicos, cerrados:**
  >
  > **1 · El 409 no distinguía al robot del colega.** `ReviewConflictError` ahora lleva
  > `retryable: bool`: `False` si ganó otro docente (fila ganadora con `features['revision_humana']`
  > — hay que leer su decisión antes de insistir) y `True` si ganó una reclasificación automática
  > (la decisión del docente sigue siendo válida, puede reintentar). El mensaje distingue "otro
  > docente" de "el sistema reclasificó". `routes/review.py` expone `{"message", "retryable"}` en
  > el `detail` del 409. La carrera en el sentido que faltaba (`submit_review` vs
  > `persist_classification`, máquina gana) tiene test nuevo en
  > `test_submit_review_concurrency_db.py::test_conflicto_contra_reclasificacion_automatica_sugiere_reintentar`
  > — RED verificado (`AttributeError: no attribute 'retryable'` contra el código sin el fix).
  > El sentido humano-vs-humano ya tenía test (ronda 4); se le agregaron las aserciones de
  > `retryable`/mensaje.
  >
  > **2 · Nivel de aislamiento documentado, no fijado.** `db/__init__.py::get_engine` no fija
  > `isolation_level` — corre bajo el default de Postgres. Confirmado contra el servidor real:
  > `SHOW default_transaction_isolation` → `read committed`. Comentario en `get_engine()` +
  > docstring extenso en `submit_review` explicando qué garantiza READ COMMITTED (snapshot por
  > statement, no por transacción) y qué rompería si alguien pasa a REPEATABLE READ/SERIALIZABLE.
  > No se cambió nada del comportamiento.
  >
  > **3 · `reclassify_all.py`: el conteo SÍ distingue las dos cosas ahora.** `ClassificationOut.is_current`
  > ya viajaba en la respuesta HTTP (`routes/classify_ep.py:69`) — no era un cambio de contrato.
  > Función pura `_classify_response(status_code, body)` con 4 tests en
  > `tests/unit/test_reclassify_all.py` (RED verificado: `ImportError` contra el código sin la
  > función). El resumen final ahora reporta `nuevos_vigentes` separado de
  > `nuevos_no_vigentes` (201 pero una anulación humana sigue gobernando) — relevante para la
  > reclasificación masiva del bloque 6.
  >
  > **4 · El hueco end-to-end, cerrado (no solo declarado por cuarta vez).** Nuevo
  > `tests/integration/test_classify_episode_review_composition_e2e_db.py`: los DOS routers HTTP
  > reales en secuencia (`POST classify_episode` → `POST review` → `POST classify_episode` con
  > hash nuevo, vía `ASGITransport` contra la app real, solo `_fetch_episode_from_ctr` mockeado)
  > contra Postgres real. RED verificado revirtiendo a mano la exclusión `revision_humana` en
  > `pipeline.py`: `assert True is False` en `is_current` de la respuesta HTTP real de la tercera
  > llamada — la composición bajo el router SÍ podía romperse aunque las dos mitades pasaran
  > por separado. Con el fix, 3/3 estable.
  >
  > Gotcha propio de esta ronda: los dos tests nuevos con `commit()` real (el de la carrera
  > máquina-vs-docente y el end-to-end) dejaron residuos en `classifier_db` la primera vez que
  > fallaron a propósito para verificar el RED — el `finally` de cleanup no envolvía el cuerpo
  > completo. Corregido (mismo patrón que la ronda 4) y re-verificado forzando un fallo: la DB
  > queda en 106/0 igual. 224 tests de classifier-service, DB en 106/0 al cierre.
  >
  > **Lo que NO se re-verificó en esta ronda, declarado:** el roundtrip de `alembic downgrade`
  > (no se tocó `pipeline.py`/`review.py` de forma que afecte la migración; se leyó, no se
  > re-ejecutó). La verificación E2E contra el gateway real (200/201/400/409) sigue siendo la de
  > la ronda 4, ~13:31 — **una sola fuente**, nadie la confirmó de forma independiente en esta
  > ronda ni en la anterior.

- [x] 5.11 **`downgrade()` escrito Y ejercitado** (D7.d). Para una tabla nueva es un `drop_table`, pero «trivial de escribir» no es «ejercitado»: aplicar y revertir contra una **copia**, nunca contra la base del piloto, y registrar los dos comandos con su salida. El repo **no tiene ningún target de CI ni de `Makefile`** que corra `alembic downgrade`, así que nada obliga a este paso salvo esta línea. Ejercitado 2026-09-27 contra `classifier_db_downgrade_copy` (`CREATE DATABASE ... TEMPLATE classifier_db`, nunca contra `classifier_db` real): upgrade→downgrade→upgrade roundtrip completo, copia borrada al final. Ver tabla de evidencia del implementador.

## 6. B2b — El sumidero de `sin_clasificar` (aislado, último)

- [x] 6.1 🔴 **Antes de tocar el mapeo**: rastrear los consumidores del valor de `appropriation` y anotar cuáles rompen o cuentan mal con un quinto valor. El riesgo no es un crash — es un `.get(valor, 0)` que lo suma a otra cosa. Incluye κ (`platform_ops/kappa_analysis.py`), el mapa ordinal de CII longitudinal (`cii_longitudinal.py`), el export académico (`academic_export.py`), analytics (`routes/analytics.py`, `routes/pedagogia.py`) y los tres frontends.

  **Hecho por un relevamiento independiente previo a este commit** (no repetido acá, usado como entrada): ~50 archivos de código real tocan estos valores, no los ~20 estimados. Cuatro guardas silenciosas priorizadas y arregladas en 6.4 (`aggregation.py`, `academic_export.py`, `pedagogia.py`, `PedagogiaPage.tsx`), dos crashes visibles benignos en 6.4/6.5 (`EpisodeNLevelView.tsx`, `TareaSelector.tsx` + 3 uniones de tipo), un bug preexistente no introducido por esta change arreglado y declarado como tal (`ab_testing.py` — `compute_cohen_kappa` sin `categories` explícito, ya rompía con `autonomo`), y dos exclusiones ya correctas hechas explícitas con comentario (`longitudinal.py`/`cii_longitudinal.py`). `review.py`, `interrater.py`, `regimen_llm.py`, `real_datasources.py`, `guardrail_signals.py`, `MiProgresoPage.tsx`, `EpisodePage.tsx` ya filtran/validan/tienen default seguro — no tocados a propósito.

  **CORRECCIÓN de QA (2026-09-27): `KappaRatingView.tsx` estaba MAL clasificado como "ya protegido".** El relevamiento asumió que el filtro de subgrupo de `/interrater/sample` lo cubría, pero esa pantalla, en modo episodios reales (`isTraining=false`), consume `GET /api/v1/analytics/kappa/sample` — trae `Classification.appropriation` de TODAS las filas `is_current=true` de la comisión, sin excluir `autonomo` ni `sin_clasificar`. Ver el fix en 6.5 (`appropriationDotColor`).
- [x] 6.2 `_EJE_TO_APPROPRIATION["sin_clasificar"]` pasa a `"sin_clasificar"` (`pipeline.py:86`). La columna es `String(40)` sin enum: **no hay migración de esquema**.
- [x] 6.3 Excluir explícitamente el valor nuevo del mapa ordinal `APPROPRIATION_ORDINAL`. No es un punto del continuo: es la ausencia de medición. Misma disciplina con la que el CII longitudinal ya excluye TPs huérfanas.

  Ya era correcto por membership check (`in APPROPRIATION_ORDINAL`) en cada consumidor — comentario agregado en `longitudinal.py` (junto a la constante) y `cii_longitudinal.py` (junto al list comprehension) dejando escrito el porqué, antes implícito. Sin cambio de comportamiento, sin test nuevo (no hay comportamiento que cubrir que los tests existentes de `autonomo` no cubrieran ya).
- [x] 6.4 Guardas en los consumidores de 6.1, cada una con su test.

  Cuatro guardas silenciosas, cada una con test RED→GREEN:
  - `aggregation.py` (`AppropriationCounts` sin bucket propio → `total_episodes` descuadrado con `distribution.total`). Test: `test_aggregation.py::test_agregacion_cuenta_sin_clasificar_y_no_descuadra_el_total`.
  - `academic_export.py` (colisión de CENTINELA — renombrado a `clasificacion_ausente`, el valor real sigue el vocabulario del árbol). Test: `test_academic_export.py::test_sin_clasificar_del_arbol_no_colisiona_con_episodio_sin_fila_de_clasificacion` + `test_distribution_summary_correcto` actualizado.
  - `pedagogia.py` (caía en `n_indeterminados`, rama genérica, descripción falsa en el frontend). Extraída `_compute_distribucion` (pura, testeable sin las 3 bases) + bucket propio `n_sin_clasificar`. Test: `test_pedagogia_distribucion.py` (2 tests, incluye triangulación con un valor realmente desconocido).
  - `PedagogiaPage.tsx` (`order` hardcodeado de 5 claves sin `sin_clasificar` → barra no suma el total mostrado). `DistribucionSection` exportada para test directo + entrada propia en `APR` (no reusa `APR.indeterminado`). Test: `PedagogiaPageDistribucion.test.tsx` (2 tests).
- [x] 6.5 Etiqueta legible en los frontends. «Sin clasificar» no es un estado de error: es información sobre el episodio.

  `docenteLabels.ts` (`APPROPRIATION_DOCENTE`/`APPROPRIATION_INVESTIGADOR`, antes mostraban la clave cruda vía el fallback `?? category`) + `EpisodeNLevelView.tsx` (`APPROPRIATION_DISPLAY_FALLBACK`, ver 6.4/crash abajo) + `PedagogiaPage.tsx` (entrada propia en `APR`, ver 6.4). Tests: `docenteLabels.test.ts` (3 tests).

  **Crash benigno arreglado de paso (no en la lista de 6.4, hallado al revisar `EpisodeNLevelView.tsx`)**: `APPROPRIATION_DISPLAY` era un `Record<AppropriationLabel, ...>` de 4 claves SIN fallback — indexar con `sin_clasificar` devolvía `undefined` y `display.container` (línea 605) rompía con `TypeError`. Es la vista a la que linkea la cola de revisión humana (bloque 5): el docente que hacía click desde la cola se comía el crash. Fix: `Partial<Record<...>>` + `?? APPROPRIATION_DISPLAY_FALLBACK`, mismo patrón de `docenteLabels.ts`. Test: `EpisodeNLevelView.test.tsx::"appropriation sin_clasificar no rompe el render y muestra label propio"` — RED verificado con `TypeError: Cannot read properties of undefined (reading 'container')` en `EpisodeNLevelView.tsx:605` contra el código sin el fix (hubo que forzar `analytics-view-mode=docente` en el test: el componente que rompía sólo se renderiza en ese modo, no en "investigador", el default del archivo).

  **Segundo crash benigno, mismo hallazgo (item 7 del brief)**: `TareaSelector.tsx::appropriationLabel` — switch exhaustivo sin `default` sobre un tipo literal, mismo patrón que BUG-04 (QA 2026-09-23, ya documentado en el propio archivo). Actualizadas las TRES uniones de tipo que declaran estos valores en el mismo commit: `web-student/src/lib/api.ts` (`Classification.appropriation` y `StudentEpisode.appropriation`) y `web-teacher/src/lib/api.ts` (`AppropriationLabel`, nuevo `AppropriationSinClasificar`). Test: `appropriationLabel.test.ts` (+1 caso). `tsc --noEmit` limpio en los tres frontends tras el cambio.

  **Bug preexistente, declarado como tal (no arreglo de esta change, item 6 del brief)**: `packages/platform-ops/src/platform_ops/ab_testing.py:124` — `compare_profiles` llamaba `compute_cohen_kappa(ratings)` sin `categories` explícito, así que usaba el default de 3 valores del módulo y **ya rompía hoy con `autonomo`** (eje v4.0.0, no introducido por esta change). Fix: `categories` explícito derivado de los datos (`sorted({rater_a}|{rater_b})`), mismo patrón que ya usan `analytics.py`/`pedagogia.py`. Test RED verificado contra el código preexistente (`ValueError: Categoría inválida en rater_a: autonomo`): `test_ab_testing.py::test_compare_profiles_no_rompe_con_autonomo`.

  **Segundo bug preexistente, hallado por QA y declarado como tal**: `apps/web-teacher/src/views/KappaRatingView.tsx::appropriationDotColor` — `if/if/else` de 3 ramas (verde/ámbar/rojo-para-cualquier-otra-cosa). `autonomo` (PREEXISTENTE, ya rompía hoy) y `sin_clasificar` (introducido por B2b) caían en el `else` y salían con el color rojo de `delegacion_pasiva` — mintiendo la categoría en la única pantalla donde se valida el acuerdo entre codificadores para la tesis. El fix de 6.5 (etiqueta legible) lo empeoró sin querer: quedaba un texto verdadero al lado de un color falso. Fix: casos explícitos para `autonomo` y `sin_clasificar` (gris neutro, mismo que `docenteLabels.ts`/`PedagogiaPage.tsx`/`EpisodeNLevelView.tsx`), y el `else` deja de significar "delegación pasiva" para significar "valor que esta función no conoce" (gris distinto, mismo razonamiento que el grupo defensivo de `RevisionColaView`). Test RED verificado (`TypeError: appropriationDotColor is not a function` — no estaba exportada — y luego contra el código con el `else` viejo): `KappaRatingViewDotColor.test.ts` (5 tests).
- [x] 6.6 🔴 Bump de `tree_version` `v4.0.0 → v4.1.0` en los **dos** sitios: `pipeline.py:41` (default de `compute_classifier_config_hash`) y `routes/health.py:59` (`_TREE_VERSION`). Más el test que afirma el valor (`tests/test_health.py:104`).

  **Hallazgo no anticipado por el design: había un TERCER sitio.** `classify_ep.py:262` (el handler real de `POST /classify_episode/{id}`, el que persiste de verdad) llamaba `compute_classifier_config_hash(profile, "v4.0.0")` con el literal hardcodeado, IGNORANDO el default de `pipeline.py`. Sin arreglarlo, el hash que el endpoint `/api/v1/classifier/config-hash` reporta (`v4.1.0`) habría quedado desincronizado del hash que el handler real persiste — exactamente la propiedad que el propio docstring de `health.py` promete ("el hash que el endpoint expone DEBE ser el mismo que la fila persiste", invariante ADR-020). Fix: se saca el literal y se usa el default de `compute_classifier_config_hash` (sin segundo argumento), para que un futuro bump no pueda volver a desincronizar los tres sitios. RED verificado en `test_classify_episode_idempotent.py::test_classify_episode_201_cuando_cambia_config_hash` (aserción actualizada del hardcode viejo al default vigente) contra el código sin este fix adicional.
- [x] 6.7 Verificar que el hash **cambió** y que el valor nuevo es estable entre corridas. Los 13 tests de reproducibilidad tienen que seguir pasando con el hash nuevo.

  Golden actualizado en `test_classifier_config_hash_golden` (`test_pipeline_reproducibility.py`): viejo `28e111aec4c5ec470bc8836cd716f563f41639d043d79bc95dca7da99e62b774` (regía hasta v4.0.0, citado en el docstring del test) → nuevo `56f3905858c19def2f20741a03378e9d5e3dfe1a4f0e4dd75d7440367fdc1180`. Verificado: el golden FALLÓ tras el bump (`AssertionError: ... golden=28e111ae... actual=56f39058...`) con los otros 13 tests de reproducibilidad (determinismo) en verde — es la prueba de que el hash se movió por el bump deliberado, no por un efecto colateral.
- [x] 6.8 Este bloque va en su propio commit. Es el único que mueve el hash, y el diff que lo mueve tiene que ser legible de un vistazo dentro de seis meses.

  Todos los archivos tocados en este bloque son los enumerados en 6.1-6.7 (classifier-service: `pipeline.py`, `health.py`, `classify_ep.py`, `aggregation.py` + tests; platform-ops: `academic_export.py`, `longitudinal.py`, `cii_longitudinal.py`, `ab_testing.py` + tests; analytics-service: `pedagogia.py` + test nuevo; frontends: `PedagogiaPage.tsx`, `EpisodeNLevelView.tsx`, `docenteLabels.ts`, `TareaSelector.tsx`, `KappaRatingView.tsx`, `api.ts` ×2 + tests; `design.md` para cerrar la pregunta abierta de intercoder) — ninguno fuera del alcance de B2b. El commit lo hace el usuario.

## 7. NO se ejecuta en esta change (operativo, gate aparte)

- [ ] 7.1 ⛔ Reclasificar los 23 episodios `sin_clasificar` ya persistidos. Corre contra la base real del piloto, con `persist_classification` idempotente como precondición (ya verificada). **Fuera de alcance.**
- [ ] 7.2 ⛔ Reclasificar las 106 clasificaciones con hash legacy `9dd96894...`, más las que esta change deja legacy. Es el backlog A1 del plan de acción, ya abierto. **Fuera de alcance.**
- [ ] 7.3 ⛔ El segundo sumidero: 21 de 105 episodios (20%) donde los dos codificadores humanos coincidieron en superficial-o-reflexiva y el árbol mandó al eje `autonomo`; `autonomo` es la categoría con más discrepancia humana (38% sobre 182 episodios doblemente codificados, contra 0% de delegación pasiva). Registrado como contexto, **no como alcance**.

## 8. Cierre

- [x] 8.1 Smoke test del flujo: episodio que deriva por evidencia insuficiente → aparece en la cola → un docente lo revisa → sale de la cola con historial. Va en `tests/e2e/smoke/` **antes** de declarar la change cerrada.

  **Hecho el 2026-09-28.** `tests/e2e/smoke/test_smoke_review_queue.py`, 2 tests contra el
  stack real (api-gateway + classifier-service + ctr-service + Postgres, `LLM_PROVIDER=mock`).
  El episodio de prueba se siembra DIRECTO en `ctr_store` (misma función de hashing SHA-256
  que `scripts/seed-smoke.py`) porque la persistencia vía tutor-service depende de los
  partition workers async, no garantizados en el ambiente de smoke (limitación ya declarada
  en `tests/e2e/smoke/README.md`). Tenant/comisión/episodio son UUIDs frescos por test (no el
  tenant demo compartido) — la auth de classifier-service/ctr-service es 100% por headers
  X-*, sin lookup a academic-service para los roles usados (`docente_admin`/`docente`, que
  caen en `CTR_OVERSIGHT_ROLES`), así que no hace falta jerarquía académica ni tenant
  preexistente.

  `test_episodio_deriva_a_revision_aparece_en_cola_docente_revisa_sale_con_historial`: deriva
  por `error_parseo` (el juez con `LLM_PROVIDER=mock` no devuelve JSON — mismo camino de
  fallback que la abstención por traza insuficiente, caso 4 de la Tabla 3.11) → aparece en la
  cola → verdict fuera de dominio da 400 sin sacarlo de la cola → revisión válida da 201 con
  historial verificado por lectura directa de `classification_reviews` → sale de la cola
  (needs_review limpio) → anti-join aislado: con `needs_review` reforzado a mano a `true` en
  la fila ya revisada, la cola lo sigue excluyendo (solo por `~ya_revisado`, sin depender del
  mecanismo anterior) — mismo hallazgo que el audit de 5.9 sobre `list_review_queue`.

  `test_dos_revisiones_concurrentes_dan_409_y_distinguen_retryable`: dos POSTs `/review`
  concurrentes de verdad (`httpx.AsyncClient` + `asyncio.gather`, un solo cliente compartido
  para evitar que el jitter de dos handshakes TCP nuevos rompa la carrera — con threads o con
  `curl &` en bash, que el audit de la ronda 3 ya había descartado, no llegan a competir).
  Exactamente uno gana (201) y el otro pierde (409) con `detail.retryable=False` (ganó un
  docente, no una reclasificación automática) — Postgres serializa el `UPDATE` optimista de
  `submit_review` a nivel de fila real, no hay mock de por medio.

  **Declarado fuera de alcance de este smoke, con el porqué**: que la anulación humana siga
  gobernando frente a una reclasificación automática POSTERIOR con un `classifier_config_hash`
  NUEVO (bump de `tree_version`) ya está cubierto por
  `test_classify_episode_review_composition_e2e_db.py` (integración, mockea
  `compute_classifier_config_hash` para forzar el segundo hash). Un smoke caja-negra contra el
  proceso real no puede forzar un segundo hash sin reiniciar el servicio con otro
  `tree_version` — `classify_episode` es determinista dado el mismo código corriendo, así que
  un segundo POST siempre pega el mismo hash y cae en el atajo de idempotencia (200 no-op) sin
  tocar la exclusión de la fila humana en `persist_classification`.

  **RED verificado de verdad, no supuesto**: se revirtió a mano el `~ya_revisado` de
  `list_review_queue` (`review.py`), se reinició classifier-service, y el smoke falló en el
  assert del paso 7 (anti-join aislado) — no en el setup. Restaurado el guard y confirmado en
  verde de nuevo. Detalle completo en el informe del implementador.
- [x] 8.2 Suites corridas y registradas sobre **SHA `81979a1b5e67963b27d42ea8070554a97f859104`** (2026-09-28).

  | paquete | resultado |
  |---|---|
  | classifier-service | **227 passed** |
  | analytics-service | **175 passed** |
  | tutor-service | **490 passed** |
  | platform-ops | **298 passed**, 4 skipped |
  | academic-service | 305 passed, **4 failed preexistentes** |
  | evaluation-service | 332 passed, **5 failed preexistentes**, 94 skipped |
  | web-teacher | **398 passed** |
  | web-student | **573 passed** |
  | web-admin | **19 passed** |
  | smoke E2E | 78 passed, **12 failed preexistentes**, 6 skipped |

  Los fallos **se verificaron preexistentes por reversión**, no por suposición: `git stash -u` de
  todo nuestro diff y re-corrida, con conteo idéntico. Los 4 de academic-service son de
  `test_tareas_practicas_templates_crud`; los 5 de evaluation-service, de `test_recalificar_estado`
  y `test_scope_comision_submit`. Los 12 del smoke son servicios Java sin levantar, el deadline del
  seed vencido contra el reloj de la VM, y un 401 de BYOK del tenant demo.

  `evaluation-service` necesita `OTEL_SDK_DISABLED=true` sin un colector en `127.0.0.1:4317`, o la
  suite muere antes de correr.

  **Pendiente sin resolver:** un test flaky en web-teacher, 1 fallo en 22 corridas, bajo carga. No se
  pudo reproducir en 21 corridas limpias posteriores ni en 12 adicionales. Sin identificar.
- [ ] 8.3 Verificar que `LABELER_VERSION` **no** se movió: esta change no toca el etiquetador N4.
- [ ] 8.4 Verificar que `git diff` sobre `packages/contracts/.../ctr/` está vacío: el hashing de eventos no se toca.
- [x] 8.5 Actualizar `CLAUDE.md`: `_TREE_VERSION` y los valores de `appropriation` en «Constantes que NO deben inventarse» (REWRITE); el porqué de la regla trivaluada en gotchas (APPEND); conteo de smoke tests si cambió.

  **Hecho el 2026-09-28.** Constantes: tres entradas nuevas — `tree_version = "v4.1.0"` con los **dos** literales vigentes (`pipeline.py:46` default, `health.py:64`) y la advertencia sobre el tercer sitio (`classify_ep.py`, que hoy usa el default a propósito y no debe volver a hardcodearlo); el hash de referencia `56f39058…` como vigente y `28e111ae…` declarado explícitamente como ya-no-válido; y los **cinco** valores de `appropriation` con `sin_clasificar` declarado como ausencia de clasificación y excluido del mapa ordinal. **Nota sobre el REWRITE**: en `CLAUDE.md` no había nada viejo que borrar — el archivo nunca documentó `tree_version`, los valores de `appropriation` ni el hash de referencia (verificado con `rg`). El único sitio donde el hash viejo quedó citado es el docstring de `test_classifier_config_hash_golden`, y ahí es historia deliberada, no valor esperado. APPEND en «Propiedades críticas»: `is_current` = «la que gobierna»; el append-only de `classifications` no es estricto (UPDATE de la bandera + INSERT); los 13 tests de reproducibilidad prueban determinismo y no invariancia, y el golden es el que avisa; la cola de revisión depende de READ COMMITTED sin fijar; y la regla trivaluada de Kleene fuerte con su porqué y su versionado. **Conteo de smoke tests NO tocado**: `CLAUDE.md` declara 56 (verificado 2026-07-29) y hoy hay 76 `def test_` en `tests/e2e/smoke/`, pero 8.1 está agregando uno en ese mismo directorio — el número final no se puede confirmar todavía y escribir uno que caduca en minutos es peor que dejar el viejo con su fecha. Queda para quien cierre 8.1.
- [x] 8.6 ADR nuevo por la regla trivaluada versionada y por el bump de `tree_version`. El ADR-057 describe el contrato v4.0.0 que esta change modifica — referenciarlo, no reescribirlo.

  **Hecho el 2026-09-28**: [`docs/adr/062-regla-trivaluada-kleene-y-bump-tree-version.md`](../../../docs/adr/062-regla-trivaluada-kleene-y-bump-tree-version.md), formato MADR del `_template.md`. ADR-057 referenciado en el encabezado (`Relacionado`) y en Referencias, **no editado**. Registra: la decisión (Kleene fuerte, siguiendo los seis casos de la Tabla 3.11) con las cuatro alternativas rechazadas —Kleene débil por inflar la cola que B5 vino a construir, `no_evaluable ≡ ausente`, `no_evaluable ≡ presente` por sesgar hacia arriba, y v5.0.0 por el precedente de `LABELER_VERSION`—; los casos 2 y 5 fuera de alcance por depender de B4 con sus constantes declaradas y fuera de `Estado`; el costo asumido (corpus con hash legacy, sumado al backlog de 106); y lo que NO se hizo, con motivo: los 131 episodios sin reclasificar por gate operativo aparte, y el segundo sumidero `autonomo` (21 de 105, acuerdo 0,160 con intervalo que cruza el cero). **No se tocó el índice de `docs/adr/README.md`**: está congelado en ADR-028 y los 33 ADR posteriores tampoco están ahí — agregar solo el 062 rompería la consistencia del archivo sin arreglar el índice. Reportado como deuda, no arreglado de paso.
- [ ] 8.7 Actualizar `obsidian.md` en el lugar: frontmatter (`estado`, `ultimo`), `Estado actual` y `Próximos pasos` se **reescriben**; `Gotchas y aprendizajes` se **apila**. Si solo apilaste, no la actualizaste.
