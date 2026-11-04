# Design: cibse-codificacion-ciega

Revisión 5 (propose, intento 5 por decisión del humano del 04/11/2026 sobre la pregunta 12: el enunciado se carga a mano; se retira todo cambio en academic-service). Los mapas hallazgo → sección están en `informes/propose-{2,3,4,5}-planner.md`.

## Context

Motivación y alcance en `proposal.md`. Estado actual verificado sobre `origin/main @ b32e621`:

- **Inter-jueces del piloto**: `apps/classifier-service/src/classifier_service/routes/interrater.py` (sample dinámico por `appropriation`, `POST /ratings` con una `label`, `GET /my-progress`) y tabla `interrater_ratings` (`models/__init__.py:122-174`), unicidad `(tenant, episode, rater)`.
- **Traza**: el web-teacher la pide a ctr-service (`GET /api/v1/audit/episodes/{id}`, `lib/api.ts:1747`) y `EpisodeProcessTrace` (`views/interraterShared.tsx`) muestra todos los eventos y el payload JSON completo. Eso expone `intento_adverso_detectado` (categoría `overuse`, `jailbreak_*`), `prompt_enviado.prompt_kind`, `tutor_respondio.{socratic_compliance, violations, model_used, provider, tokens_*, cost_usd, chunks_used_hash}`, `edicion_codigo.origin`, `episodio_abierto.{student_pseudonym, comision_id, problema_id, curso_config_hash}`, `tp_calificada`, hashes, y los huecos de `seq` delatan eventos ocultos si solo se filtrara. El CTR devuelve el episodio completo, incluidos eventos posteriores al cierre; `estado` toma `open`, `paused`, `closed`. Un `episodio_abandonado` deja el episodio en `paused` (ADR-055) y actividad posterior lo vuelve `open`; la reapertura docente (`episodio_reabierto`) está retirada desde el 2026-06-19 (`partition_worker.py:677-728`, leído por el plan-reviewer). `lectura_enunciado` es un latido periódico con `duration_seconds`.
- **Gate de lectura del CTR**: `get_episode` exige rol en `READ_ROLES` y, para `docente`, membresía en la comisión (A0.6). `classifier_worker` está en `CTR_OVERSIGHT_ROLES` (`apps/ctr-service/src/ctr_service/auth/dependencies.py:116-129`). Una cuenta de servicio nueva no requiere registro en ctr-service: basta mandar los headers con el rol.
- **Identidad en producción**: Clerk. El gateway asigna a todo usuario logueado `estudiante,docente` (`apps/api-gateway/src/api_gateway/config.py:112`) y suma `superadmin,docente_admin` solo a `CLERK_ADMIN_EMAILS`. Reinyecta `X-User-Email` desde el claim `email` sin chequear `email_verified`; `X-User-Id = uuid5(sub)`. La firma HMAC opcional (`gateway_trust.py:48-90`) cubre `user_id`, `tenant_id`, `roles` y `ts`, **no el email**.
- **Web-teacher**: entra solo quien tiene comisiones (`main.tsx:75-130`; si `listMine()` falla, redirige a `/`). El layout raíz monta `TourAutoStart` (tour docente que navega a `/unidades`, `/ejercicios`, etc.), `OnboardingDocente`, `ComisionSelectorRouted` y `TenantSelector` (`routes/__root.tsx`).
- **Gateway**: `/api/v1/interrater` enruta a classifier-service por `startswith` (`proxy.py:64,120`).
- **Tests que crean el esquema de classifier en SQLite**: `apps/analytics-service/tests/unit/test_cohort_slopes_batch.py:68`, `packages/platform-ops/tests/test_real_datasources.py:67`, `packages/platform-ops/tests/test_ghost_episodes_exclusion.py:56` y `test_language_segmentation.py` hacen `Base.metadata.create_all` de `classifier_service.models` (línea de base del reviewer con los 4 archivos: 36 passed).
- **Codebook v0**: borrador Markdown de 10 secciones fuera del repo (`/home/juanisarmiento/Descargas/CIbSE2027_muestra_150/codebook/codebook_v0_borrador.md`, sha256 `8c20baf7...501b` al 04/11/2026). §3 pide cita por turno o evento; §4 define una regla de decisión ordenada entre dimensiones y régimen; §7 exige coherencia y que el desacuerdo con la regla se codifique igual y se explique en notas; §9 deja puntos abiertos. El texto no se copia acá.
- **Muestra**: CSV fuera del repo, 150 filas, `estrato,origen,tp,episode_id`, sha256 `6a6cc0c7...2137`, sin duplicados ni valores no-UUID; ninguna de las 7 anclas del piloto está en la muestra (verificado por UUID completo).
- **Enunciados** (academic-service, `academic_main`): `TareaPractica.enunciado` (markdown) más `codigo`, `titulo`, `fecha_inicio/fin`, `rubrica`, `test_cases` (con ocultos), `created_by`; `Ejercicio.enunciado_md` más `titulo`, `rubrica`, `test_cases`, `tutor_rules`, `banco_preguntas`, `misconceptions`, `respuesta_pista`, `heuristica_cierre`, `anti_patrones`, `created_by` (`models/operacional.py:230-300, 420-500`). Una TP agrupa varios ejercicios por `tp_ejercicios`. `Episode.problema_id` es la TP y `episodio_abierto.payload.ejercicio_id` el ejercicio (nulo en TPs monolíticas). `GET /tareas-practicas/{id}` exige membresía de comisión salvo `SERVICE_ROLES` u `OVERSIGHT_ROLES`, que reciben la TP sin sanear (tests ocultos incluidos); `GET /ejercicios/{id}` sanea solo para roles fuera de `FULL_CONTENT_ROLES` (`services/content_visibility.py`), y aun saneado conserva `rubrica` y tests públicos. Ningún rol existente lee enunciados de cualquier comisión sin recibir también soluciones; por eso la opción automática exigía cambiar academic-service, y el humano eligió la carga manual (D14).
- **Lo que ve el juez** (`services/regimen_llm.py:398-448`): transcript alumno/tutor, anotaciones, último snapshot y conteos de ejecuciones y prompts. No ve stdout/stderr, snapshots intermedios, copias, pegados ni lecturas del enunciado.

## Goals / Non-Goals

**Goals:**
- Cegamiento aplicado en el servidor, con lista blanca versionada que falla cerrada.
- Evidencia fija por ítem desde la carga.
- Acceso por identidad asignada y atada al `user_id` firmado, nunca por rol de Clerk.
- Formulario, regla de coherencia y codebook definidos por datos versionados, no por código.
- Cero escritura sobre `classifications`, `interrater_ratings` y `classification_reviews`.

**Non-Goals:**
- Cálculo de acuerdo (κ) del estudio dentro del sistema: se hace afuera con la exportación.
- Cualquier cambio en academic-service (decisión del humano, pregunta 12): el enunciado lo carga el investigador a mano (D14).
- Corregir la exposición preexistente de los endpoints del piloto (ver Riesgos).
- Editor visual del codebook: se carga Markdown y esquema; el editor es un textarea.
- Gestión de estudios desde web-admin.

## Decisions

### D1. Tablas nuevas, separadas del piloto

Módulo `classifier_service/models/estudio.py` (importado desde `models/__init__.py`), migración aditiva `20261104_0007_estudio_codificacion.py` con `apply_tenant_rls` en cada tabla:

| Tabla | Contenido |
|---|---|
| `estudio_codificacion` | `clave` única por tenant (patrón y lista reservada, D3), título, `codebook_vigente_id`, `muestra_sha256`, `muestra_cargada_at`, `traza_version` (fijada en el alta del estudio con el valor vigente del código; rige muestra, anclas, entrenamiento y etiquetas), `created_by` |
| `estudio_membresia` | `email` (minúsculas), `rol` (`investigador`/`codificador`), `alias` (C1, C2...), `semilla` (entero aleatorio), `user_id` (atado en el primer uso, D3), `cerrada_at`, `revocada_at`, `created_by`. Una membresía activa por `(estudio, email)` |
| `estudio_muestra` | `item_id` (UUID4 opaco, único), `episode_id`, evidencia fija (D4b): `seq_tope`, `chain_hash_tope`, `events_count_carga`, `last_chain_hash_carga`, `estado_carga`, `problema_id` y `ejercicio_id` leídos del CTR en la carga (D14); unicidad `(estudio, episode_id)` |
| `estudio_enunciado` | (D14) `fuente` (`tp`/`ejercicio`), `fuente_id`, `archivo_sha256`, `cargado_por`, `cargado_at`, `contenido_original_md`, `sha256_original`, `contenido_mostrado_md`, `sha256_mostrado`, `alertas` (JSONB), `revisado_por`, `revisado_at`; unicidad `(estudio, fuente, fuente_id)`. Original inmutable; lo mostrado inmutable una vez revisado |
| `codebook_version` | `etiqueta`, `estado` (`borrador`/`congelada`), `contenido_md`, `esquema_formulario` (JSONB), `contenido_sha256` (al congelar, cubre texto, esquema y anclas, D8), `congelada_at`, `congelada_por` |
| `estudio_ancla` | `item_id` opaco, `codebook_version_id`, `episode_id`, mismos campos de evidencia fija y de enunciado que la muestra, `uso` (`ejemplo`/`practica`), `orden`, `respuesta_esperada` (JSONB, formato D9), `explicacion_md`, `consensuado_por` |
| `estudio_etiqueta` | `membresia_id`, `muestra_item_id`, `codebook_version_id`, `traza_version`, `respuestas` (JSONB, formato D9), `regimen` (derivado por la regla o exento, D9), `regimen_regla`, `regimen_propuesto`, `es_frontera`, `confianza`, `notas`, `created_at`, `updated_at`; unicidad `(membresia, item)`. `disiente_de_regla` no se persiste: se deriva |
| `estudio_etiqueta_historial` | snapshot JSONB de cada guardado, append-only |
| `entrenamiento_respuesta` | `membresia_id`, `ancla_id`, `codebook_version_id`, `traza_version`, mismo formato que la etiqueta (régimen derivado por la regla y `regimen_propuesto`), `respondida_at`; append-only |

**Compatibilidad con SQLite**: los tests listados en Context hacen `create_all` de todo `classifier_service.models.Base`. Por eso el modelo SQLAlchemy usa solo lo que ya usa el módulo (`JSONB`, `PgUUID`, `UniqueConstraint`, `Index` simples), y todo lo específico de Postgres (unicidad parcial de membresía activa, triggers, `CHECK` con funciones) vive solo en la migración, no en la metadata del modelo. La tarea 2.1 corre esos tests como consumidores.

Alternativa rechazada: extender `interrater_ratings` con un `protocol="cibse"`. `analytics.py::interrater_aggregate`, `pedagogia.py:736` y `scripts/exportar-episodios-eje-fino.py` leen esa tabla y el agregado del piloto no tiene control de rol: las etiquetas del estudio quedarían visibles en el κ del piloto y mezcladas con el gold docente.

### D2. Inmutabilidad con triggers

La migración crea triggers que rechazan:
- `UPDATE` o `DELETE` de una fila de `codebook_version` cuyo `estado` ya es `congelada` (el paso borrador a congelada sí se permite).
- `INSERT`, `UPDATE` o `DELETE` de `estudio_ancla` cuya versión (nueva o vieja) está congelada.
- `UPDATE` o `DELETE` en `estudio_etiqueta_historial` y `entrenamiento_respuesta`.
- `UPDATE` de las columnas de evidencia fija y de enunciado de `estudio_muestra` y `estudio_ancla`.
- `UPDATE` de cualquier columna de `estudio_enunciado` cuando `revisado_at` no es nulo, y `DELETE` de enunciados revisados (antes de revisar se permite reemplazar el texto por una carga nueva, D14).

Alternativa rechazada: disciplina de aplicación cubierta por tests, como `classification_reviews`. Para la referencia de un paper y un nivel CRITICAL, el esquema tiene que impedirlo aunque un endpoint futuro se equivoque.

### D3. Acceso por membresía, atada al `user_id` firmado

`require_membresia(estudio, roles)` resuelve la membresía activa por `(tenant, estudio, lower(X-User-Email))`. En el primer uso guarda `X-User-Id` en la membresía; desde ahí, un pedido con el mismo email y otro `user_id` recibe 403 y emite `estudio_membresia_user_id_distinto` (con `membresia_id`, sin email). El email solo sirve para la asignación inicial; la identidad del dato es la membresía y su `user_id`, que es el campo que la firma del gateway sí cubre. Las etiquetas se ligan a `membresia_id`.

- Alta de estudio y gestión de membresías por administrador: `superadmin` o `docente_admin`.
- Gestión de membresías, muestra, codebook, anclas, progreso y exportación: `investigador` del estudio.
- Un email no puede tener dos membresías activas en el mismo estudio (409); nadie codifica y exporta a la vez.
- Revocar fija `revocada_at`; re-asignar un email revocado crea una membresía **nueva** (alias, semilla y `user_id` propios, sin etiquetas). Las etiquetas de la membresía revocada se conservan y se exportan con su `revocada_at`.
- Router nuevo con `dependencies=[Depends(require_gateway_auth)]`, como `interrater.py`, y test con `require_gateway_signature=True` (el test existente `tests/test_auth.py` no enumera routers).
- `clave` valida `^[a-z0-9][a-z0-9-]{2,40}$` y rechaza la lista reservada (`mis-membresias` y cualquier segmento literal de las rutas del router).
- Logs de membresía y de exportación: `membresia_id`, alias, `user_id` del autor; nunca emails.

Alternativas rechazadas: rol nuevo en Clerk o Casbin (Clerk no transporta roles por usuario en este gateway; tocar gateway o academic-service está fuera de alcance); usar `docente` (lo tiene cualquier cuenta); asignar codificadores a una comisión (les daría el CTR completo de esa comisión); llave solo por email (no está firmado).

Supuesto declarado: el email de Clerk es verificado. Atar el `user_id` limita el daño a la primera vez que alguien usa ese email; no lo elimina. Se verifica en el recorrido humano con Clerk real (tasks.md, Workflow follow-up).

### D4. Traza ciega en classifier-service con lista blanca versionada

Endpoint `GET /api/v1/interrater/estudios/{clave}/items/{item_id}/traza`, para ítems de muestra y anclas. classifier-service resuelve `item_id` a `episode_id` (nunca lo devuelve), lee el episodio con una cuenta de servicio propia (`ESTUDIO_LECTOR_SERVICE_USER_ID`, UUID nuevo, rol `classifier_worker`, firma con `sign_headers` si hay `gateway_shared_secret`) y construye la respuesta desde cero.

**Lista blanca `traza_v1`** (constante `TRAZA_VERSION = "traza_v1"` en `services/traza_ciega.py`):

| Tipo CTR | Se muestra como | Campos permitidos |
|---|---|---|
| `episodio_abierto` | inicio | `language` |
| `lectura_enunciado` | lectura de la consigna; latidos consecutivos (sin otro evento incluido entre ellos) se agrupan en un solo elemento con la suma de `duration_seconds` | `duration_seconds` (sumado) |
| `prompt_enviado` | mensaje del alumno | `content` |
| `tutor_respondio` | respuesta del tutor | `content` |
| `edicion_codigo` | estado del código | `snapshot`, `language` |
| `codigo_ejecutado` | ejecución | `code`, `stdout`, `stderr`, `passed`, `failed`, `total`, `failed_test_names` |
| `tests_ejecutados` | corrida de pruebas | `test_count_total`, `test_count_passed`, `test_count_failed`, `tests_publicos`, `tests_hidden` |
| `anotacion_creada` | nota del alumno | `content` |
| `copia_intentada` | intento de copiar | `seleccion_chars`, `metodo` |
| `pega_intentada` | intento de pegar | `contenido_longitud`, `metodo` (**sin** `contenido_preview`) |
| `episodio_cerrado` | fin: cerrado | ninguno |
| `episodio_abandonado` | fin: abandonado | ninguno (sin `reason`: `timeout` y `distraccion_pestana` son marcas del sistema) |
| cualquier otro: `intento_adverso_detectado`, `reflexion_completada`, `tp_entregada`, `tp_calificada`, `episodio_reabierto`, `pestana_perdida`, `pestana_recuperada`, tipos futuros | se omite | n/a |

La lista se arma desde un dict crudo (el CTR manda campos fuera del contrato, p. ej. `execution_engine`): se copian solo las claves permitidas. Omitidos por ser marcas o decisiones automáticas: `prompt_kind`, metadatos del tutor, `edicion_codigo.origin`, `pestana_*` (detección del navegador), `reason` de abandono.

**Localizadores** (asignados después de filtrar): `n` global contiguo desde 1, y uno por tipo: `turno k` (el k-ésimo mensaje del alumno; las respuestas del tutor que le siguen, hasta el próximo mensaje del alumno, llevan el mismo `turno k`), `código k`, `ejecución k`, `prueba k`, `nota k`, `lectura k` (por grupo de latidos). Cada elemento lleva `t_seg` (segundos desde el inicio del episodio), no el `ts` absoluto.

Un test enumera los `event_type` de `platform_contracts.ctr.events` y exige decisión explícita (incluido u omitido) para cada uno.

**Diferencia de evidencia humano/juez (para la sección de método del paper)**: con `traza_v1` el codificador ve, además de lo que ve el juez, stdout/stderr, todos los estados intermedios del código, intentos de copiar y pegar (sin contenido), lecturas de la consigna y si el episodio terminó cerrado o abandonado. El juez ve solo el último snapshot y conteos. La diferencia es deliberada (la evidencia del humano sigue el codebook §2 y §4) y debe declararse en el paper; cambiarla exige una `traza_version` nueva.

Alternativas rechazadas: filtrar en el front (el payload completo viaja al navegador); endpoint filtrado en ctr-service (prohibido); usar la sesión del codificador contra `/api/v1/audit` (externos sin comisión fallan A0.6; docentes recibirían el payload completo).

### D4b. Evidencia fija por ítem

Al cargar la muestra o crear un ancla, classifier-service lee el episodio y guarda `seq_tope` (máximo `seq` en ese momento), `chain_hash_tope` (chain hash del evento con ese `seq`), `events_count_carga`, `last_chain_hash_carga` y `estado_carga`. La `traza_version` del estudio se fija en el alta (D1), así que anclas y entrenamiento previos a la muestra usan la misma versión. Al servir la traza:
- se usan solo eventos con `seq <= seq_tope`;
- si el evento `seq_tope` ya no existe o su chain hash difiere, la respuesta es 409 `evidencia_alterada`, se emite `estudio_evidencia_alterada` (con `item_id`) y no se sirve nada;
- si la `TRAZA_VERSION` del código difiere de la del estudio, 409 `traza_version_distinta`: cambiar la lista blanca a mitad de un estudio exige decisión explícita y un estudio nuevo.

Como el CTR es append-only, la reanudación de un episodio abandonado (o cualquier evento posterior) queda fuera del tope y los localizadores no se corren. Cada etiqueta y cada respuesta de entrenamiento guardan la `traza_version`.

### D5. Identificador opaco

El codificador ve `item_id` (UUID4 aleatorio), nunca `episode_id`. La exportación del investigador sí incluye `episode_id` para unir con los estratos fuera del sistema.

### D6. Muestra cargada por endpoint, nunca en el repo

`POST /api/v1/interrater/estudios/{clave}/muestra` recibe el CSV crudo como texto (investigador), calcula sha256 de los bytes, compara con `sha256_esperado` si viene, extrae solo `episode_id` y descarta el resto sin persistirlo. Valida encabezado, UUID, duplicados, que cada episodio exista en el CTR del tenant y esté **terminado**: `estado == "closed"`, o `estado == "paused"` con `episodio_abandonado` como último evento de cierre de la cadena (abandonado y no retomado). Se rechazan `open`, `paused` sin abandono y episodios con `integrity_compromised` (default; pregunta abierta). Concurrencia 8, y que ninguno sea ancla del estudio. Fija la evidencia de cada ítem (D4b). Todo o nada, bajo el lock del estudio (D10b). Reemplazo permitido solo sin etiquetas del estudio.

Alternativas rechazadas: commitear los IDs (quedan en GitHub junto con estrato y origen); script contra la base de producción (saltea auditoría y exige credenciales fuera de EasyPanel); hash declarado por el navegador (no verificable).

### D7. Orden por codificador reproducible sin depender de la versión de Python

Al dar de alta un codificador se guarda `semilla = secrets.randbits(63)` (se reintenta si colisiona dentro del estudio). La posición de cada ítem es el rango, en orden ascendente del hex, de `sha256((str(semilla) + ":" + item_id).encode("utf-8"))`, donde `semilla` es el entero en decimal sin relleno e `item_id` el UUID en minúsculas con guiones (forma canónica de 36 caracteres). Ese procedimiento se copia tal cual al ADR y al método del paper. Es determinista por definición, documentable en el paper y no depende de `random.shuffle`. La exportación incluye semilla y posición.

### D8. Codebook versionado en la base

Se guarda en `codebook_version` (Markdown + esquema JSONB). Alternativa rechazada: archivo en el repo servido por el backend; cada edición del borrador exigiría commit, PR a `main` y redeploy de classifier-service, y el estado congelado dependería de convenciones de git. A favor del repo quedaba la historia; se compensa con el sha256 al congelar, versiones nunca borradas y la exportación.

Reglas: borrador editable (texto, esquema, anclas); congelar exige texto no vacío y esquema válido, y calcula `contenido_sha256` sobre `{"contenido_md", "esquema", "anclas"}`, donde cada ancla se serializa con exactamente `uso, orden, episode_id, respuesta_esperada, explicacion_md, consensuado_por, seq_tope, chain_hash_tope` (sin `item_id` ni ids internos, que son aleatorios) y la lista se ordena por `(uso, orden, episode_id)` con `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`; congelada no se edita (D2). Versión nueva: borrador, opcionalmente clonando texto, esquema y anclas. `codebook_vigente_id` lo fija el investigador; cambiarlo con etiquetas existentes da 409. El entrenamiento usa la vigente aunque sea borrador; la codificación solo con vigente congelada.

Carga del v0: el investigador sube el `.md` y el esquema JSON desde el panel de administración o por `PUT .../codebook/{version}` (runbook). El código no trae texto de codebook ni esquema por defecto.

### D9. Formulario y regla de coherencia definidos por el esquema de la versión

Alternativa rechazada: formulario fijo en código según el v0 §7; el §9 deja abiertos cambios que lo alteran. Meta-esquema cerrado, validado al guardar el borrador:

- `dimensiones`: 1 a 8 entradas `{clave, nombre, valores[2..6], cita_requerida_si[]}`.
- `regimenes`: 2 a 6 entradas `{clave, nombre}`; `regimen_evidencia_insuficiente` debe ser una de ellas.
- `dimensiones_opcionales_si_regimen[]`, `notas_obligatorias_si_regimen[]`, `marca_frontera` (bool).
- `confianza`: `null` o `{valores[], obligatoria}`.
- `reglas_regimen`: lista ordenada `[{regimen, condicion}]`, `regimen_por_defecto`, `regimenes_exentos[]` (al menos el de evidencia insuficiente). `condicion` es una conjunción de cláusulas; cada cláusula es una disyunción de átomos `{dimension, en: [valores], con_cita: bool?}`. El régimen de la regla es el de la primera cuya condición se cumple, o el por defecto. Esa gramática expresa la §4 del v0 sin poner texto ni claves del codebook en el código. Con `reglas_regimen` vacía, el codificador elige el régimen (no hay regla que aplicar).

**Formato de respuestas** (etiqueta, respuesta de entrenamiento y respuesta esperada del ancla): `respuestas = {"<clave_dimension>": {"valor": str | null, "cita": str | null}}`. La cita es texto libre (el codificador escribe localizadores como "turno 3; ejecución 4"); el sistema no la parsea. Junto a `respuestas`: `regimen`, `regimen_propuesto`, `es_frontera`, `confianza`, `notas`. Exportación: columnas `dim_<clave>_valor` y `dim_<clave>_cita` por dimensión del esquema.

**Régimen según la regla** (decisión del orquestador del 04/11 que corrige la del intento 2, alineada con el v0 §7: "lo codifica igual según la regla y lo explica en las notas"):
- El `regimen` persistido es **siempre** el que da la regla sobre las dimensiones. El servidor lo calcula (función pura) cuando todas las dimensiones que la regla referencia tienen valor; si faltan, queda `null`.
- Única excepción: un régimen de `regimenes_exentos` (evidencia insuficiente), que el codificador elige explícitamente y que la regla no puede derivar.
- `regimen_regla` (R3-1): el régimen que da la regla sobre las dimensiones se calcula y guarda **siempre** que las dimensiones referenciadas tengan valor, también cuando el codificador eligió un régimen exento. Así queda visible el caso "evidencia insuficiente con dimensiones que derivarían otro régimen". Con régimen no exento, `regimen == regimen_regla`.
- Si el pedido trae un `regimen` no exento distinto del calculado, o un régimen no exento con dimensiones incompletas, el servidor lo rechaza (422) y no guarda.
- Si el codificador cree que la regla da un resultado injusto, completa `regimen_propuesto` (opcional, uno de los regímenes del esquema) y la nota es obligatoria (422 si falta). `disiente_de_regla` se deriva: `regimen_propuesto` no nulo y distinto de `regimen`.
- La respuesta del guardado devuelve el `regimen` calculado; el panel lo muestra como resultado de la regla, no como elección.
- Entrenamiento: misma lógica; la devolución compara el régimen derivado con el esperado del ancla.
- No existen la bandera `incoherente` ni el cierre con "disiento": por construcción no hay etiquetas incoherentes.

Guardado parcial: cada valor debe pertenecer al esquema; claves desconocidas, 400. Cierre: completitud según el esquema (régimen; dimensiones salvo las exceptuadas; cita no vacía, sin contar espacios, cuando el valor la requiere; notas cuando el régimen o la frontera lo exigen; confianza si es obligatoria) y `regimen` no nulo (calculado o exento).

### D10. Etiquetado, historial, cierre y aislamiento

`PUT .../items/{item_id}/mi-etiqueta` hace upsert sobre `(membresia, item)` y agrega una fila al historial en la misma transacción; guarda `codebook_version_id` y `traza_version`. Requiere vigente congelada (409) y membresía no cerrada (409). `POST .../mi-codificacion/cerrar` valida completitud de todos los ítems (dimensiones completas y régimen calculado o exento; nota cuando hay `regimen_propuesto`) y fija `cerrada_at`; desde ahí todo guardado da 409. No hay reapertura (pregunta abierta). Ningún endpoint para codificadores acepta otro `membresia_id`. El investigador ve progreso por codificador (completos, parciales, con régimen propuesto, cerrada), nunca valores.

### D10b. Concurrencia

Orden de locks siempre: fila del estudio, luego fila de la membresía.
- `PUT mi-etiqueta` y `POST cerrar`: `SELECT ... FOR SHARE` del estudio y `SELECT ... FOR UPDATE` de la membresía; relee `cerrada_at` y `codebook_vigente_id` bajo lock.
- Cambio de vigente, carga o reemplazo de muestra, alta y baja de anclas: `SELECT ... FOR UPDATE` del estudio.

Así un guardado concurrente con el cierre queda serializado (o entra antes y el cierre lo ve, o después y recibe 409), y un guardado no puede leer una vigente que otro está cambiando. Tests al estilo de `tests/integration/test_submit_review_concurrency_db.py`.

### D11. Entrenamiento

Anclas `ejemplo`: se muestran junto al codebook con traza ciega, respuesta esperada y explicación. Anclas `practica`: a ciegas; `POST .../entrenamiento/{item_id}/respuesta` guarda (append-only) y recién esa respuesta trae la esperada y la explicación. Sin umbral de aprobación en código (pregunta abierta). Las anclas validan que el episodio esté terminado con el mismo criterio que la muestra (D6), fijan evidencia (D4b) y la exclusión con la muestra se valida en ambos sentidos bajo el lock del estudio. Sin anclas en la vigente, estado vacío.

### D12. Exportación

`GET .../exportacion?contenido=etiquetas|entrenamiento|historial&formato=csv|json`, solo investigador. Incluye `episode_id`, `item_id`, alias, `membresia_id`, semilla, posición, versión y sha del codebook, `traza_version`, `dim_<clave>_valor`/`_cita`, `regimen` (persistido: el de la regla o el exento), `regimen_regla` (siempre que sea calculable, R3-1), `regimen_propuesto`, `disiente_de_regla` (derivado), `es_frontera`, `confianza`, notas, timestamps, `cerrada_at`, `revocada_at`. Sin emails ni contenido de episodios. CSV con prefijo `'` para celdas que empiezan con `=`, `+`, `-`, `@`, tab o CR. Log `estudio_exportacion` sin valores.

### D13. Web-teacher

- `src/utils/accesoPanel.ts`: función pura `resolverAcceso({comisiones, membresias})` donde cada entrada es `ok | error` con su dato. Reglas: docente con comisiones entra en modo completo aunque `mis-membresias` falle (las dos secciones muestran el error, el resto del panel no); sin comisiones y con membresía, modo restringido; error de comisiones y membresía válida, modo restringido; sin nada o error en ambos, redirige a `/` como hoy.
- `main.tsx`: pide las dos consultas en paralelo y aplica `resolverAcceso`.
- `routes/__root.tsx` en modo restringido: menú con solo las dos secciones; otra ruta redirige a `/interrater`; **no monta** `TourAutoStart`, `OnboardingDocente`, `ComisionSelectorRouted` ni `TenantSelector`, y no pide comisiones.
- `routes/entrenamiento-recalibracion.tsx` → `views/estudio/EntrenamientoEstudioView.tsx` (codebook con `MarkdownRenderer`, marca de borrador, ejemplos, práctica).
- `routes/interrater.tsx` → `views/estudio/CodificacionEstudioView.tsx` y, para investigadores, `views/estudio/AdministracionEstudioView.tsx` (incluye la revisión de enunciados de D14).
- Componentes: `views/estudio/TrazaCiega.tsx` (enunciado arriba de la línea de tiempo, D14; localizadores por tipo y global, tiempo relativo), `views/estudio/FormularioEsquema.tsx` (muestra el régimen que da la regla, ofrece `regimen_propuesto` con nota obligatoria), `utils/diffLineas.ts`, `lib/estudioApi.ts`.
- Se borran `views/InterraterTraining.tsx`, `views/InterraterCodingView.tsx` y `views/interraterShared.tsx`.
- Docente sin membresía: aviso y enlace a `/interrater-admin`; oculto a miembros.
- `helpContent.tsx`: `interraterCoding` se reescribe sin reglas de clasificación; se agrega `estudioEntrenamiento`.

### D14. Enunciado en la vista ciega (cambio de alcance del 04/11/2026)

**Qué se muestra.** El enunciado de la TP (`TareaPractica.enunciado`) siempre, y además el del ejercicio (`Ejercicio.enunciado_md`) cuando `episodio_abierto.payload.ejercicio_id` no es nulo, en ese orden y rotulados ("Consigna del trabajo práctico", "Consigna del ejercicio"). Justificación: en las TPs con ejercicios del banco, el episodio es sobre un ejercicio y su enunciado es lo que el alumno resolvía; el de la TP es el encuadre que también leyó (y que en las TPs monolíticas es el único). Mostrar solo el de la TP dejaría al codificador sin la consigna real en las TPs con varios ejercicios; mostrar solo el del ejercicio dejaría sin consigna a las monolíticas. Costo: en TPs con varios ejercicios el enunciado de la TP puede nombrar ejercicios que no son los del episodio; se acepta, porque es lo que el alumno tenía delante. No se muestran `codigo` ni `titulo` (pueden identificar comisión o cátedra), fechas, `rubrica`, `inicial_codigo`, `test_cases`, `tutor_rules`, `banco_preguntas`, `misconceptions`, `respuesta_pista`, `heuristica_cierre`, `anti_patrones` ni `created_by`.

**Cómo llega: carga manual del investigador** (decisión de Juani del 04/11/2026, pregunta 12, opción B). No se toca academic-service, tutor-service ni ctr-service.
- Al cargar la muestra o un ancla, classifier-service guarda en el ítem, junto con la evidencia fija (D4b), el `problema_id` del episodio y el `ejercicio_id` del `episodio_abierto` (nulo si no hay). Esos pares definen el **conjunto requerido** de enunciados del estudio.
- El investigador sube un CSV exportado desde la consola de Postgres (la consulta la prepara el orquestador fuera del plan) por `POST /api/v1/interrater/estudios/{clave}/enunciados`, junto con la muestra o después. Columnas: `tipo` (`tp`/`ejercicio`), `tp_id`, `ejercicio_id` (una de las dos según el tipo) y `enunciado`. Se recibe el texto crudo, se guarda su sha256 en `archivo_sha256` y cada fila en `estudio_enunciado` con `sha256_original` (sha256 UTF-8 del texto tal cual).
- Validación, todo o nada por archivo: encabezado; `tipo` válido; id UUID coherente con el tipo; sin dos filas para el mismo `(tipo, id)`; texto no vacío. Filas que no corresponden a ningún ítem de la muestra ni ancla del estudio se ignoran y se informan (minimización: no se guarda texto que nadie va a ver).
- Cargas sucesivas: se pueden subir archivos parciales. Una fila para un `(tipo, id)` que ya existe con el mismo `sha256_original` es no-op; con otro texto, 409 si ya fue revisado y reemplazo si todavía no (se registra `estudio_enunciado_reemplazado` en el log con tipo, id y los dos hashes, sin texto). Así un error de exportación se corrige antes de revisar, y lo revisado no cambia.
- La respuesta informa **cobertura**: enunciados requeridos, cargados, revisados y faltantes (por `tipo` e id), y los ítems afectados por cada faltante.

**Enunciado faltante: se bloquea la codificación de todo el estudio, no del ítem.** Mientras falte o no esté revisado algún enunciado requerido por la muestra, `PUT mi-etiqueta` da 409 `enunciados_pendientes` para todos los ítems. Motivo: los dos codificadores tienen que codificar los 150 con la misma evidencia; un bloqueo por ítem dejaría empezar con una muestra parcial, haría que cada codificador recorra su orden con huecos distintos y complicaría el cierre (que exige los 150). Como la carga es un archivo único preparado de una vez, el costo de esperar es bajo. El entrenamiento, en cambio, se bloquea **por ancla**: un ancla sin enunciado cargado y revisado no se muestra, porque las anclas son independientes y el entrenamiento no es obligatorio (P10). La traza de un ítem con enunciado faltante responde 409 `enunciado_pendiente`.

Alternativas rechazadas: endpoint interno en academic-service con cuenta `estudio_lector` (rechazada por el humano, pregunta 12: amplía el alcance a otro servicio); usar endpoints existentes con `tutor_service` o `superadmin` (suplantan identidad y traen soluciones); leer `academic_main` desde classifier (prohibido por ADR-003); que el codificador lea el enunciado fuera del sistema (sin fijación ni revisión).

**Riesgo propio de la carga manual**: el sistema no puede verificar que el texto subido sea el de academic-service; un error de exportación o de asociación de ids pasa sin aviso técnico. Mitigación: `archivo_sha256` y autor por fila, cobertura explícita, revisión obligatoria del investigador viendo cada enunciado y declaración en el método del paper de que los enunciados se cargaron desde una exportación del investigador.

**Revisión del investigador, porque el contenido no se puede verificar desde el código.** No se puede garantizar por lectura de código que un enunciado no nombre docentes, comisiones o fechas: es texto libre escrito por docentes o generado con IA (ADR-036). Por eso: (1) al fijar, una función pura marca `alertas` con patrones de riesgo (fechas, emails, "prof"/"profesor"/"docente" seguido de nombre propio, "comisión"/"com." con número o letra, horarios); (2) el panel de administración lista cada enunciado distinto con sus alertas; (3) el investigador lo aprueba tal cual o guarda una versión editada (`contenido_mostrado_md`, con `sha256_mostrado`, quién y cuándo); (4) la codificación del estudio da 409 mientras haya enunciados de la muestra faltantes o sin revisar; las anclas se muestran en entrenamiento solo con sus enunciados cargados y revisados. El original nunca se borra y se exporta su hash junto al del texto mostrado. Verificación sobre datos del repo: en los seeds no aparecen nombres ni fechas dentro de `enunciado` (búsqueda del 04/11), pero eso no dice nada de producción; por eso la revisión es obligatoria y no opcional.

**Vista ciega.** La traza (D4) agrega `enunciado: {tp_md, ejercicio_md | null}` con el contenido mostrado, sin ids ni hashes. `traza_v1` se define incluyendo el enunciado (todavía no hay datos con otra versión). La exportación agrega `enunciado_tp_sha256_original`, `enunciado_tp_sha256_mostrado`, los del ejercicio y el `archivo_sha256` de origen.

### Consumidores del piloto y de los módulos tocados

| Consumidor | Qué usa | Estado tras el change |
|---|---|---|
| `GET/POST /api/v1/interrater/{sample,ratings,my-progress}` | `interrater_ratings`, `classifications` | Intactos; pierden su consumidor de UI (decisión del humano). |
| `analytics.py::interrater_aggregate` + `/interrater-admin` | `interrater_ratings` | Intactos; la vista recupera un enlace de entrada. |
| `pedagogia.py:736` | `interrater_ratings` | Intacto; test `apps/analytics-service/tests/unit/test_pedagogia_distribucion.py`. |
| `scripts/exportar-episodios-eje-fino.py` | `interrater_ratings` | Intacto. |
| Tests con `create_all` de `classifier_service.models` (Context) | metadata del módulo | Deben seguir verdes (D1, compatibilidad SQLite). |
| `tests/docenteOnboarding.test.tsx` | rutas registradas y onboarding en el root | Debe seguir verde; el modo restringido no monta onboarding. |
| `tests/navegacionAlcanzable.test.ts` | motivos de rutas fuera del menú | Se agrega el enlace a `/interrater-admin`; se corrige el motivo de `kappa`. |

## Risks / Trade-offs

- [Cuenta de servicio con lectura total del CTR] → la traza solo resuelve `item_id` de muestra o anclas del estudio del caller; cualquier otro, 404. Mutantes sobre ese chequeo.
- [Email no firmado ni verificado] → membresía atada al `user_id` firmado en el primer uso; recorrido humano con Clerk real; si el email no es verificado, bloqueante.
- [Docente codificador ve la etiqueta de la máquina en otras pantallas] → identificador opaco y recomendación de codificadores externos (pregunta 2).
- [Episodio abandonado y reanudado después de la carga, o lista blanca cambiada a mitad del estudio] → evidencia fija y `traza_version` (D4b).
- [Regla mal cargada en el esquema] → validación del meta-esquema, régimen calculado visible al guardar (el codificador lo ve enseguida y puede proponer otro con nota) y tarea de follow-up para validar el esquema del v0 contra las anclas antes de congelar.
- [ctr-service con `REQUIRE_GATEWAY_SIGNATURE` encendido] → el cliente firma si hay secreto; smoke real tras el deploy.
- [Carga de 150 episodios contra el timeout de 120 s del gateway] → no medido; concurrencia 8 y, si excede, la tarea 7.1 lo registra y propone carga por lotes. El reviewer lo dejó como SUPOSICIÓN.
- [Exposición preexistente, fuera de alcance] → con Clerk, `POST /api/v1/interrater/ratings` del piloto acepta a cualquier cuenta y `/api/v1/analytics/interrater/aggregate` no exige rol. Observado por lectura, no reproducido. DEUDA para otro change.
- [Enunciado con nombres, comisión o fechas] → alertas automáticas más revisión obligatoria del investigador antes de habilitar la codificación (D14).
- [Texto cargado a mano que no corresponde al enunciado real] → `archivo_sha256`, cobertura, revisión obligatoria viendo el texto y declaración en el método (D14).
- [Enunciado faltante] → codificación bloqueada para todo el estudio hasta completar y revisar (D14).
- [Tests de integración se saltean sin Postgres] → el constructor registra la corrida con Postgres real.

## Migration Plan

1. Merge a `main` por PR con CI en verde (lint-python, typecheck-python, lint-frontend, test-unit, test-frontend, build-frontend, migrations-dry-run, test-rls).
2. Deploy de classifier-service solo (corre `20261104_0007`). Verificar `/health` y `GET .../mis-membresias` con una cuenta sin membresía (lista vacía).
3. Deploy de web-teacher solo, después del paso 2. Si classifier-service no responde, los docentes siguen entrando (D13) y solo las dos secciones muestran error.
4. Alta del estudio y del investigador por API (runbook en `docs/servicios/classifier-service.md`); carga y validación del esquema y del codebook v0; carga de la muestra con `sha256_esperado`; carga del CSV de enunciados (consulta preparada por el orquestador) y revisión de cada enunciado.
5. Rollback: revertir web-teacher primero; `alembic downgrade` de `0007` solo si no hay datos del estudio. Con datos, rollback de código sin downgrade.

## Open Questions

Las que cambian specs o alcance están en `proposal.md` con default declarado. Diferibles sin cambiar specs:

- Microcopy de avisos y estados vacíos (se valida en el recorrido).
- Concurrencia exacta de la validación contra ctr-service al cargar la muestra.
