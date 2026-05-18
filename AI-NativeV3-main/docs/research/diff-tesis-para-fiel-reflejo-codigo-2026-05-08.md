# Diff Tesis v3.4 → estado código v1.0.0

**Fecha**: 2026-05-08.
**Tesis fuente**: `tesis_v3_4_ronda2_aceptada.docx` (1725 párrafos, 301KB).
**Código fuente**: `Juani2so` branch `main`, commit `45a99e0` + cambios aplicados 2026-05-08.
**Documento complementario**: `analisis-bidireccional-tesis-codigo-2026-05-08.md` (análisis general).

---

## Cómo usar este documento

> Este es un **diff aplicable** sobre la tesis. Para cada divergencia detectada entre tesis y código:
>
> - **OLD →** texto literal actual de la tesis (verbatim del `.docx`).
> - **NEW →** texto propuesto que mantiene el tono académico, registro doctoral y profundidad conceptual de la tesis original.
> - **Sección afectada**: ubicación exacta dentro del manuscrito.
> - **Razón**: justificación basada en código + ADR + commit, con file:line.

**La tesis NO se reestructura**. Capítulos, secciones, anexos, numeración, figuras y tablas quedan en su lugar. Solo se reemplazan **párrafos puntuales** que afirman cosas que el código contradice o que no reflejan capacidades vigentes.

**Naming convention**:
- C1-C5 = cambios **obligatorios** (la tesis afirma algo factualmente falso o desactualizado respecto al código).
- C6-C13 = cambios **recomendados** (la tesis subestima capacidades del código o no documenta extensiones reales).
- C14-C16 = cambios **menores** (precisión cosmética).

---

## Resumen de cambios (16 ediciones)

| # | Sección | Tipo | Esfuerzo | Decisión humana? |
|---|---|---|---|---|
| C1 | 7.3 | Obligatorio | 5 min | No |
| C2 | 4.3.1 | Obligatorio | 10 min | No |
| C3 | 15.6 (CT) | Obligatorio | 5 min | No |
| C4 | 15.6 (Etiquetador) | Obligatorio | 15 min | No |
| C5 | 4.3.1 (cobertura ontología) | Recomendado | 10 min | No |
| C6 | 7.2 (Tabla 7.1) | Recomendado | 20 min | No |
| C7 | 7.2 (Estado instrumentación) | Recomendado | 10 min | No |
| C8 | 6.3 (contenedores) | Recomendado | 30 min | No |
| C9 | 15.4 (CII longitudinal) | Recomendado | 15 min | No |
| C10 | 16.3 (gobernanza) | Recomendado | 20 min | No |
| C11 | 19.5 (limitaciones v1.0.0) | Recomendado | 10 min | No |
| C12 | 20.5.1 Eje B | Recomendado | 10 min | No |
| C13 | 20.5.1 Eje D | **Decisión** | 30 min | **SÍ — opción A o B** |
| C14 | 8.4.1 (cobertura guardarraíles) | Recomendado | 10 min | Atado a v1.0.1 |
| C15 | Anexo A.2 (~280 palabras) | Menor | 5 min | No |
| C16 | Anexo A.4 (hash SHA-256) | Menor | 1 min | Atado a v1.0.1 |

**Total**: ~3.5 horas de redacción concentrada. Una sola sesión bien organizada lo cierra.

---

## C1 — Sec 7.3: el genesis hash NO es SHA-256("")

### OLD (Sec 7.3, párrafo 4 — línea 558 de la tesis)

> donde canonicalize es la serialización JSON determinista del evento (campos ordenados lexicográficamente, codificación UTF-8, separadores compactos, sin escape de caracteres no-ASCII), y evento_n incluye como campos propios prompt_system_hash y classifier_config_hash vigentes al momento de su emisión. El primer evento de un episodio usa como chain_hash_0 un valor genesis canónico **(el hash de la cadena vacía)**.

### NEW

> donde canonicalize es la serialización JSON determinista del evento (campos ordenados lexicográficamente, codificación UTF-8, separadores compactos, sin escape de caracteres no-ASCII), y evento_n incluye como campos propios prompt_system_hash y classifier_config_hash vigentes al momento de su emisión. El primer evento de un episodio usa como chain_hash_0 un **valor genesis canónico definido como una constante de sesenta y cuatro ceros hexadecimales** (apps/ctr-service/src/ctr_service/models/base.py::GENESIS_HASH). Esta elección es arbitraria pero estable: cualquier modificación invalidaría toda cadena existente del piloto.

### Razón

El código tiene literalmente `GENESIS_HASH = "0" * 64` en `apps/ctr-service/src/ctr_service/models/base.py:33` y `packages/contracts/src/platform_contracts/ctr/hashing.py:19`. NO es `SHA-256("")` (cuyo valor real es `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`). Cualquier miembro del comité con un `echo -n "" | sha256sum` lo verifica y la afirmación queda expuesta como factualmente incorrecta. El código fue corregido en su comentario el 2026-05-08; la tesis necesita el ajuste paralelo.

---

## C2 — Sec 4.3.1: `anotacion_creada` ya NO se etiqueta N2 fijo

### OLD (Sec 4.3.1, párrafo único — línea 309)

> [...] La asignación de niveles a tipos de evento usada por el etiquetador en v1.0.0 sigue la Tabla 4.1 con una salvedad documentada en la Sección 15.6: **las anotaciones del estudiante (anotacion_creada) se etiquetan como N2 fijo, en lugar de N1/N4 según contenido**. Las implicaciones observacionales de esta cobertura parcial se discuten específicamente en la Sección 15.6 (operacionalización de primera generación) y 19.5 (limitaciones derivadas de la implementación v1.0.0).

### NEW

> [...] La asignación de niveles a tipos de evento usada por el etiquetador en v1.0.0 sigue la Tabla 4.1 con una salvedad documentada en la Sección 15.6: **las anotaciones del estudiante (anotacion_creada) se etiquetan mediante una heurística temporal posicional (LABELER_VERSION 1.2.0, override v1.1.0 documentado en ADR-023): N4 si la anotación ocurre dentro de los sesenta segundos posteriores a un `tutor_respondio` (apropiación reflexiva), N1 si ocurre dentro de los ciento veinte segundos posteriores al `episodio_abierto` (lectura/reformulación), y N2 como fallback. Los solapes se resuelven en favor de N4. Esta operacionalización conservadora cierra el sesgo declarado en versiones anteriores del manuscrito (sub-reporte de N1/N4, sobre-reporte de N2) sin introducir clasificación semántica del contenido textual, preservando la reproducibilidad bit-a-bit del Capítulo 7. Un análisis de sensibilidad de las constantes 60s/120s sobre corpus sintético se documenta en `docs/adr/023-sensitivity-analysis.md` del repositorio**. Las implicaciones observacionales se discuten específicamente en la Sección 15.6 (operacionalización de primera generación) y 19.5 (limitaciones derivadas de la implementación v1.0.0).

### Razón

`apps/classifier-service/src/classifier_service/services/event_labeler.py:76` declara `LABELER_VERSION = "1.2.0"`. Las constantes `ANOTACION_N1_WINDOW_SECONDS = 120.0` y `ANOTACION_N4_WINDOW_SECONDS = 60.0` (L80-81) implementan el override. La función `label_event(event_type, payload, context)` (L135-182) aplica el override cuando `context is not None`; los callers reales del piloto (`time_in_level`, `n_level_distribution`) construyen contexto via `_build_event_contexts`. ADR-023 está promovido a Accepted (2026-04-27).

---

## C3 — Sec 15.6 (CT): `prompt_exec_ratio` es proporción, no razón

### OLD (Sec 15.6, párrafo de CT — línea 832)

> La operacionalización implementada segmenta el episodio en ventanas de trabajo sostenido delimitadas por pausas superiores a cinco minutos y calcula por ventana indicadores de densidad de eventos (eventos por minuto) y **razón prompts/ejecuciones**. El score agregado ct_summary ∈ [0, 1] sintetiza estos indicadores [...]

### NEW

> La operacionalización implementada segmenta el episodio en ventanas de trabajo sostenido delimitadas por pausas superiores a cinco minutos y calcula por ventana indicadores de densidad de eventos (eventos por minuto) y **proporción de prompts respecto del total de eventos prompts más ejecuciones, normalizada al intervalo [0, 1]** (apps/classifier-service/src/classifier_service/services/ct.py::prompt_exec_ratio, L48-59). El score agregado ct_summary ∈ [0, 1] sintetiza estos indicadores [...]

### Razón

`ct.py:48-59` calcula `prompts / (prompts + execs)`, no `prompts / execs`. Diferencia semántica: el primero es proporción ∈ [0,1] (0.5 = mitad/mitad); el segundo es razón ∈ [0, ∞) (1.0 = paridad). La afirmación actual lleva al lector a esperar el segundo cuando el código tiene el primero.

---

## C4 — Sec 15.6 (Etiquetador): cierre del sesgo de `anotacion_creada` N2 fijo

### OLD (Sec 15.6, párrafo del Etiquetador — línea 833)

> En la implementación v1.0.0, el componente C3.2 (Etiquetador de eventos) ya produce la distribución de tiempo por nivel — proporción que la formulación aspiracional de la Sección 15.2 contempla como uno de los indicadores de CT. La asignación de niveles a tipos de evento sigue la Tabla 4.1 con una salvedad: **las anotaciones del estudiante (anotacion_creada) se etiquetan en v1.0.0 como N2 fijo, en lugar de la asignación N1/N4 según contenido que la Tabla 4.1 sugiere. Esa simplificación responde a la decisión de no introducir clasificación semántica del contenido textual en v1.0.0, decisión coherente con la opción de operacionalización ligera y reproducible bit-a-bit del Capítulo 7. Las implicaciones del sesgo sistemático (sub-reporte de N1 y N4, sobre-reporte de N2) están documentadas en la Sección 19.5; la migración a override por contenido es parte del Eje B de la agenda confirmatoria.**

### NEW

> En la implementación v1.0.0, el componente C3.2 (Etiquetador de eventos) ya produce la distribución de tiempo por nivel — proporción que la formulación aspiracional de la Sección 15.2 contempla como uno de los indicadores de CT. La asignación de niveles a tipos de evento sigue la Tabla 4.1 con una operacionalización temporal del caso `anotacion_creada`: **el etiquetador (LABELER_VERSION 1.2.0, ADR-023 Accepted) aplica una heurística posicional sobre el contexto temporal del evento. Una anotación creada dentro de los sesenta segundos posteriores a un `tutor_respondio` se etiqueta N4 (apropiación reflexiva); una anotación creada dentro de los ciento veinte segundos posteriores al `episodio_abierto` se etiqueta N1 (lectura/reformulación); en otros casos la anotación se etiqueta N2. Los solapes se resuelven en favor de N4 por considerarse pedagógicamente más informativos que la lectura inicial. La operacionalización temporal evita la introducción de clasificación semántica del contenido textual, preservando la reproducibilidad bit-a-bit del Capítulo 7. El sesgo sistemático declarado en versiones anteriores del manuscrito (sub-reporte de N1/N4, sobre-reporte de N2) queda cerrado mediante esta operacionalización conservadora; un análisis de sensibilidad de las ventanas 60s/120s sobre corpus sintético se documenta en el repositorio (`docs/adr/023-sensitivity-analysis.md`). La migración a override por contenido textual permanece como parte del Eje B de la agenda confirmatoria, con criterio cuantificable de revisitar declarado en ADR-024.**

### Razón

Mismo código que C2: `event_labeler.py` v1.2.0 con override v1.1.0 implementado y testeado. Esta sección es la "definición técnica" del clasificador; debe reflejar lo que efectivamente corre.

---

## C5 — Sec 4.3.1: extensión de la ontología post-tabla 7.1

### OLD (Sec 4.3.1, párrafo único — línea 309 — el mismo que C2)

> [...] los eventos efectivamente registrados en el CTR son **episodio_abierto, episodio_cerrado, prompt_enviado, tutor_respondio, edicion_codigo, codigo_ejecutado, anotacion_creada, lectura_enunciado e intento_adverso_detectado**. Los eventos pseudocodigo_escrito, debugger_usado, codigo_aceptado y excepcion están declarados en la ontología pero no instrumentados en v1.0.0. [...]

### NEW

> [...] los eventos efectivamente registrados en el CTR son **episodio_abierto, episodio_cerrado, prompt_enviado, tutor_respondio, edicion_codigo, codigo_ejecutado, anotacion_creada, lectura_enunciado e intento_adverso_detectado, así como cuatro extensiones posteriores a la formulación inicial de la Tabla 4.1: `episodio_abandonado` (instrumentado mediante doble trigger beforeunload + worker server-side, ADR-025), `reflexion_completada` (reflexión metacognitiva post-cierre, excluida del classifier por privacy gate RN-133, ADR-035), `tests_ejecutados` (resultados del sandbox client-side Pyodide, ADR-034), y los eventos de ciclo académico `tp_entregada` y `tp_calificada` (workflow de entregas, evaluation-service)**. Los eventos pseudocodigo_escrito, debugger_usado, codigo_aceptado y excepcion están declarados en la ontología pero no instrumentados en v1.0.0. [...]

### Razón

`packages/contracts/src/platform_contracts/ctr/events.py` declara las cuatro extensiones (líneas 85, 260, 295, 315, 328). La Tabla 4.1 quedó desfasada con los epics `ai-native-completion` y `tp-entregas-correccion` cerrados en 2026-05-04. Mencionarlas como extensiones explícitas evita que el comité descubra eventos en el código que la tesis no documenta.

---

## C6 — Sec 7.2: nota sobre extensiones a la Tabla 7.1

### OLD (Sec 7.2, después de la Tabla 7.1 — línea 552)

> Estado de instrumentación en v1.0.0. La implementación v1.0.0 desplegada para el pilotaje UNSL instrumenta efectivamente **nueve tipos de evento del CTR**: episodio_abierto, episodio_cerrado, prompt_enviado, tutor_respondio, edicion_codigo, codigo_ejecutado, anotacion_creada, lectura_enunciado [...] e intento_adverso_detectado [...]. Los eventos pseudocodigo_escrito, debugger_usado, codigo_aceptado y excepcion están declarados en la ontología pero no instrumentados en v1.0.0; su instrumentación constituye el Eje A de la agenda confirmatoria. **El evento episodio_abandonado se emite por dos triggers complementarios** [...]

### NEW

> Estado de instrumentación en v1.0.0. La implementación v1.0.0 desplegada para el pilotaje UNSL instrumenta efectivamente **nueve tipos de evento del CTR de la formulación inicial**: episodio_abierto, episodio_cerrado, prompt_enviado, tutor_respondio, edicion_codigo, codigo_ejecutado, anotacion_creada, lectura_enunciado [...] e intento_adverso_detectado [...]. Los eventos pseudocodigo_escrito, debugger_usado, codigo_aceptado y excepcion están declarados en la ontología pero no instrumentados en v1.0.0; su instrumentación constituye el Eje A de la agenda confirmatoria. **Adicionalmente, la implementación incorpora cuatro extensiones a la formulación inicial de la Tabla 7.1, registradas como tipos de evento del CTR durante los epics posteriores al despliegue inicial: `episodio_abandonado` (doble trigger beforeunload + timeout server-side, ADR-025), `reflexion_completada` (reflexión metacognitiva post-cierre, excluida del classifier por privacy gate RN-133, ADR-035), `tests_ejecutados` (sandbox client-side Pyodide, ADR-034), y los eventos de ciclo académico `tp_entregada` y `tp_calificada` (workflow de entregas en evaluation-service). Estas extensiones no alteran la ontología conceptual del modelo N4: registran fenómenos pedagógicos auxiliares (intencionalidad de cierre, metacognición declarativa, ciclo de validación académica) que enriquecen el contexto interpretativo del CTR sin redefinir los cuatro niveles analíticos**. La distinción entre `episodio_cerrado` y `episodio_abandonado` registra la intencionalidad del cierre y permite separar episodios completos de episodios abandonados en el análisis empírico [...]

### Razón

Mismos contratos Pydantic que C5. Esto cierra documentalmente lo que C5 abre: cuando el lector llegue a la Tabla 7.1 va a ver los 13 originales más una nota explicita sobre las 4 extensiones, en lugar de descubrirlas en el código y suponer que la tesis está desactualizada.

---

## C7 — Sec 7.3: el integrity-attestation funciona pero el deploy es operacionalmente parcial

### OLD (Sec 7.3, párrafo 5 — línea 561)

> El diseño del CTR contempla el almacenamiento del hash de referencia del episodio cerrado en dos ubicaciones: la base de datos del sistema y un registro externo auditable fuera del control operativo del equipo de investigación. La implementación v1.0.0 materializa esta duplicación mediante el servicio integrity-attestation-service [...]: cuando el ctr-service cierra un episodio, después del commit transaccional emite el hash final del episodio y sus metadatos a un stream Redis del VPS institucional. **El servicio de attestation firma el conjunto canónico mediante una clave Ed25519 institucional (custodiada por la dirección de informática de UNSL, sin participación del doctorando) y appendea cada attestation a un archivo JSONL append-only rotado diariamente.** La verificación externa puede ser realizada por cualquier auditor [...]. La attestation opera con consistencia eventual y un SLO de 24 horas: su ausencia no bloquea el cierre del episodio (decisión de diseño explícita para que la auditoría externa no degrade la operación pedagógica del piloto).

### NEW (atado a la decisión de C13 — Eje D)

> El diseño del CTR contempla el almacenamiento del hash de referencia del episodio cerrado en dos ubicaciones: la base de datos del sistema y un registro externo auditable fuera del control operativo del equipo de investigación. La implementación v1.0.0 materializa esta duplicación mediante el servicio integrity-attestation-service [...]: cuando el ctr-service cierra un episodio, después del commit transaccional emite el hash final del episodio y sus metadatos a un stream Redis del VPS institucional. **El servicio de attestation está implementado para firmar el conjunto canónico mediante una clave Ed25519 institucional (cuya custodia por la dirección de informática de UNSL, sin participación del doctorando, está documentada en el procedimiento operativo `docs/pilot/attestation-deploy-checklist.md` del repositorio) y appendea cada attestation a un archivo JSONL append-only rotado diariamente. El despliegue del par de claves institucional y la activación del consumer en el VPS UNSL se coordinan con la dirección de informática como condición operativa previa al cierre del piloto principal**. La verificación externa puede ser realizada por cualquier auditor [...]. La attestation opera con consistencia eventual y un SLO de 24 horas: su ausencia no bloquea el cierre del episodio [...].

### Razón

`apps/integrity-attestation-service/` está implementado completo (firma Ed25519 con failsafe, journal append-only, CLI verify). Pero `docs/pilot/attestation-pubkey.pem.PLACEHOLDER` sigue siendo placeholder — la pubkey institucional NO está desplegada. Hoy solo opera la dev key. La afirmación literal "custodiada por la DI UNSL" es aspiracional, no factual. La redacción NEW es honesta: existe el servicio + el procedimiento, pero el deploy con pubkey institucional es condición operativa pendiente.

---

## C8 — Sec 6.3: contenedores C4 — fragmentación arquitectónica

### OLD (Sec 6.3, primer párrafo + lista — línea 436)

> El nivel 2 descompone el sistema en sus contenedores principales, entendiendo por contenedor una unidad ejecutable independiente (aplicación, base de datos, microservicio). El sistema AI-Native se descompone en **siete contenedores articulados**.
>
> C2.1. Aplicación web de estudiante. [...]
> C2.2. Servicio de tutor socrático. [...]
> C2.3. Servicio de registro del CTR. [...]
> C2.4. Base de datos del CTR. [...]
> C2.5. Servicio del Clasificador N4. [...]
> C2.6. Dashboard docente. [...]
> C2.7. Servicio de gobernanza. [...]

### NEW (mantener la lista C2.1-C2.7 + agregar nota al final del párrafo introductorio)

> El nivel 2 descompone el sistema en sus contenedores principales, entendiendo por contenedor una unidad ejecutable independiente (aplicación, base de datos, microservicio). El sistema AI-Native se descompone en **siete contenedores conceptuales articulados**. Cada contenedor conceptual puede materializarse en uno o más servicios físicos: la implementación v1.0.0 desplegada para el pilotaje UNSL incluye once servicios HTTP activos (más dos servicios deprecados preservados en disco con README de deprecación, ADR-030 y ADR-041) y tres aplicaciones web independientes para los tres roles de usuario, organizados en dos planos desacoplados por un bus Redis Streams particionado. **El plano académico-operacional comprende los servicios de gestión de comisiones, evaluación y analítica (academic-service, evaluation-service, analytics-service); el plano pedagógico-evaluativo comprende los servicios del núcleo del modelo N4 (tutor-service, ctr-service, classifier-service, content-service, governance-service). Dos servicios transversales (api-gateway, ai-gateway) median la entrada de tráfico y la conexión con proveedores externos de LLM. El servicio integrity-attestation-service vive en infraestructura institucional separada del VPS del piloto (ADR-021, decisión de diseño D3 del confound de custodia). Esta fragmentación se consolida bajo los siete contenedores conceptuales del modelo C4 sin alterar la lógica analítica de la tesis**: la correspondencia biunívoca entre constructos del modelo N4 y componentes arquitectónicos (Tabla 6.1) opera al nivel del contenedor conceptual, no del servicio físico.
>
> C2.1. Aplicación web de estudiante. [...]
> [resto de la lista C2.2-C2.7 sin cambios]

### Razón

La tesis declara 7 contenedores conceptuales; la implementación tiene 11 servicios + 3 frontends + integrity-attestation. La inconsistencia es solo aparente porque varios servicios físicos materializan el mismo contenedor conceptual (ej. C2.1 = web-student + web-teacher + web-admin + api-gateway). Documentarlo evita que el comité abra el `apps/` y se pregunte por qué la tesis dice "7" y el código tiene "16 directorios".

---

## C9 — Sec 15.4: `Unidad` como complemento de `template_id`

### OLD (Sec 15.4, párrafo de operacionalización CII longitudinal)

La sección 15.4 caracteriza CII como "estabilidad inter-iteración entre problemas análogos". El texto actual no menciona el constructo `Unidad`.

### NEW (insertar al final del párrafo correspondiente o como sub-párrafo nuevo)

> La operacionalización efectiva de CII longitudinal en el sistema desplegado articula dos criterios de analogía entre episodios. El criterio primario es la pertenencia al mismo `template_id` (ADR-018 Accepted, `packages/platform-ops/src/platform_ops/cii_longitudinal.py::compute_evolution_per_template`): dos episodios son análogos cuando ambos resuelven instancias de la misma TareaPracticaTemplate. El criterio complementario, introducido en respuesta a hallazgos del piloto donde una proporción significativa de TPs carecen de template asociado, es la pertenencia a la misma `Unidad` temática de la comisión (`compute_evolution_per_unidad`, mismo módulo): el constructo `Unidad` opera como decorador docente que agrupa TPs por contenido pedagógico (por ejemplo, "Condicionales", "Recursión", "Estructuras de datos básicas"), destrabando la trazabilidad longitudinal en escenarios donde el template no está disponible. Ambos criterios mantienen el mínimo de tres episodios análogos por agrupación como umbral de validez del slope ordinal de apropiación. La introducción del constructo `Unidad` es trabajo de extensión del v1.0.0 documentado en el repositorio y no altera la formulación conceptual de CII longitudinal.

### Razón

`packages/platform-ops/src/platform_ops/cii_longitudinal.py:124-197` implementa `compute_evolution_per_unidad`. El docstring del módulo declara: "habilita trazabilidad longitudinal para pilotos donde `template_id=NULL`". Documentado en SDD como `unidades-trazabilidad`. La tesis no menciona este constructo; sin la nota, el comité va a ver la entidad `Unidad` en el repo y va a preguntarse por qué.

---

## C10 — Sec 16.3: BYOK como dimensión de gobernanza

### OLD (Sec 16.3, lista de métricas de gobernanza)

> Las métricas de gobernanza refieren al cumplimiento de los principios éticos y auditables del sistema.
>
> Consentimiento: porcentaje de estudiantes con consentimiento registrado [...]
> Pseudonimización: porcentaje de datos pseudonimizados respecto del total. Debe ser 100%.
> Retención: cumplimiento de plazos de conservación y destrucción [...]
> Auditabilidad: capacidad de reconstruir el estado completo de un episodio dado [...]
> Versionado del prompt: registro completo y trazable de cambios en el prompt del sistema.

### NEW (agregar un bullet al final de la lista, manteniendo los anteriores)

> Las métricas de gobernanza refieren al cumplimiento de los principios éticos y auditables del sistema.
>
> Consentimiento: porcentaje de estudiantes con consentimiento registrado [...]
> Pseudonimización: porcentaje de datos pseudonimizados respecto del total. Debe ser 100%.
> Retención: cumplimiento de plazos de conservación y destrucción [...]
> Auditabilidad: capacidad de reconstruir el estado completo de un episodio dado [...]
> Versionado del prompt: registro completo y trazable de cambios en el prompt del sistema.
> **Soberanía de claves de proveedor (Bring Your Own Key, ADRs 038-040): el sistema admite la configuración por materia o por institución de claves API propias para los proveedores de LLM, con resolución jerárquica `materia → tenant → fallback institucional`, encriptación en reposo mediante AES-256-GCM con master key separada, y trazabilidad de uso por evento al CTR. Esta capacidad es relevante para escenarios multisite donde la responsabilidad del costo de inferencia y el cumplimiento de políticas de procesamiento de datos personales de cada institución exigen autonomía de claves. La métrica asociada es la cobertura de uso de claves institucionales propias respecto del total de invocaciones al LLM en el período evaluado.**

### Razón

ADRs 038-040 documentan BYOK (AES-256-GCM, resolver jerárquico, propagación de `materia_id`). Tablas `byok_keys` + `byok_keys_usage` con RLS. 5 endpoints CRUD. Para multisite (Anexo D), BYOK es **central** porque cada institución probablemente quiera su propia clave Anthropic/OpenAI. La tesis no lo menciona en absoluto.

---

## C11 — Sec 19.5: limitaciones derivadas de v1.0.0 — `anotacion_creada` cerrado

### OLD (Sec 19.5, párrafo de operacionalización simplificada)

> Operacionalización simplificada de las coherencias. Las dimensiones de coherencia estructural están implementadas en primera generación (Sección 15.6). La CCD por proximidad temporal, en particular, es sensible a verbalizaciones ritualizadas sin contenido alineado al código. La CII en v1.0.0 es intra-episodio en lugar de longitudinal inter-episodio (corresponde a una noción de Iteration-Internal-Stability que captura estabilidad de foco dentro del episodio, pero no la estabilidad de criterios entre problemas análogos que la Sección 15.4 caracteriza). [...]

### NEW

> Operacionalización simplificada de las coherencias. Las dimensiones de coherencia estructural están implementadas en primera generación (Sección 15.6). **El sesgo declarado en versiones anteriores del manuscrito sobre el etiquetado de `anotacion_creada` como N2 fijo está cerrado en LABELER_VERSION 1.2.0 mediante la heurística temporal posicional descrita en la Sección 15.6 y formalizada en ADR-023 (Accepted): la operacionalización conservadora preserva la reproducibilidad bit-a-bit y elimina el sub-reporte sistemático de N1/N4 sin introducir clasificación semántica del contenido textual.** La CCD por proximidad temporal, en cambio, sigue siendo sensible a verbalizaciones ritualizadas sin contenido alineado al código; la migración a similitud semántica vía embeddings es agenda Eje B (ADR-017 deferido). La CII longitudinal entre problemas análogos por `template_id` está parcialmente cerrada en v1.0.0 (ADR-018 Accepted, función `compute_evolution_per_template`) y complementada por agrupación por `Unidad` para escenarios sin template (Sección 15.4). [...]

### Razón

C2 + C4 mencionan el cierre del sesgo. Esta sección "limitaciones" es donde el comité busca QUÉ no se cumple. Si dejás el item abierto cuando ya está cerrado, le generás dudas innecesarias.

---

## C12 — Sec 20.5.1 Eje B: G8a marcado como cerrado

### OLD (Sec 20.5.1 Eje B — fragmento)

> **Eje B. Operacionalización semántica y longitudinal de las coherencias**. Estado en v1.0.0: la migración de CII desde intra-episodio a inter-episodio longitudinal está parcialmente cerrada mediante el cómputo de cii_evolution_longitudinal por slope ordinal de apropiación entre episodios análogos del mismo template_id (ADR-018). Quedan pendientes: la migración de CCD desde proximidad temporal a similitud semántica vía embeddings (Sección 15.6); la activación efectiva de la rama "prompt con intencionalidad reflexiva" de CCD (Sección 15.6, presupone clasificación automática de prompt_kind); **el override por contenido de la asignación N1/N4 de las anotaciones (Sección 4.3.1, Tabla 4.1)**.

### NEW

> **Eje B. Operacionalización semántica y longitudinal de las coherencias**. Estado en v1.0.0: la migración de CII desde intra-episodio a inter-episodio longitudinal está parcialmente cerrada mediante el cómputo de cii_evolution_longitudinal por slope ordinal de apropiación entre episodios análogos del mismo template_id (ADR-018 Accepted), complementada por agrupación por `Unidad` temática para escenarios donde el template no está disponible. **El override de la asignación de niveles a `anotacion_creada` está parcialmente cerrado mediante una operacionalización temporal posicional (LABELER_VERSION 1.2.0, ADR-023 Accepted): el override por contenido textual queda como segunda iteración del eje, condicionada a la disponibilidad de un clasificador semántico de contenido validado contra juicio docente.** Quedan pendientes: la migración de CCD desde proximidad temporal a similitud semántica vía embeddings (Sección 15.6, ADR-017 deferido); la activación efectiva de la rama "prompt con intencionalidad reflexiva" de CCD (Sección 15.6, ADR-024 deferido por riesgo de sesgo si se introduce mid-cohort).

### Razón

Refleja el cierre parcial real (G8a cerrado por override temporal, override por contenido pendiente como iteración 2). También menciona los ADRs deferidos (017, 024) que el comité va a buscar en el repo.

---

## C13 — Sec 20.5.1 Eje D: DECISIÓN HUMANA REQUERIDA

> **Esta es la única edición que requiere decisión tuya entre dos opciones**. La diferencia es: ¿se ejecuta el deploy de attestation con DI UNSL antes de defensa, o se atempera la afirmación de la tesis?

### OLD (Sec 20.5.1 Eje D — línea 1044)

> **Eje D. Auditabilidad externa efectiva. Estado en v1.0.0: cerrado** mediante el integrity-attestation-service con firma Ed25519, journal JSONL append-only rotado diariamente, custodia de clave por la dirección de informática de UNSL, y tool CLI de verificación externa (Sección 7.3, ADR-021). El servicio opera con consistencia eventual y SLO de 24 horas, sin bloquear el cierre del episodio. Cualquier evolución posterior (Certificate Transparency-style log, OpenTimestamps) queda como mejora del Eje D ya en producción, no como agenda nueva.

### NEW — Opción A (atemperar narrativa, defensa segura sin dependencia externa)

> **Eje D. Auditabilidad externa efectiva. Estado en v1.0.0: diseño y desarrollo cerrados; despliegue institucional como condición operativa pendiente**. El servicio integrity-attestation-service está implementado completo y verificado bit-a-bit contra el ADR-021: firma Ed25519, journal JSONL append-only rotado diariamente, tool CLI `scripts/verify-attestations.py` para verificación externa por terceros, buffer canónico documentado bit-exact (Sección 7.3, ADR-021 Accepted). El procedimiento operativo de despliegue de la pubkey institucional bajo custodia de la dirección de informática de UNSL —sin participación del doctorando, condición de diseño D3— está documentado en `docs/pilot/attestation-deploy-checklist.md` y en `docs/pilot/auditabilidad-externa.md`. El cierre operativo del Eje D queda condicionado a la coordinación institucional con la dirección de informática para la generación y despliegue del par de claves Ed25519 antes del cierre del piloto principal, con criterio cuantificable de cobertura: cien por ciento de los eventos `episodio_cerrado` deben tener su correspondiente attestation firmada por la clave institucional en el journal externo. Cualquier evolución posterior del Eje D (Certificate Transparency-style log, OpenTimestamps) queda como mejora del despliegue base, no como agenda nueva.

### NEW — Opción B (mantener "cerrado" si se ejecuta el deploy con DI UNSL antes de defensa)

> **Eje D. Auditabilidad externa efectiva. Estado en v1.0.0: cerrado** mediante el integrity-attestation-service con firma Ed25519, journal JSONL append-only rotado diariamente, custodia de la clave Ed25519 institucional por la dirección de informática de UNSL (procedimiento operativo en `docs/pilot/attestation-deploy-checklist.md`, despliegue completado en [FECHA-A-COMPLETAR]), y tool CLI de verificación externa (Sección 7.3, ADR-021 Accepted). El servicio opera con consistencia eventual y SLO de 24 horas, sin bloquear el cierre del episodio. La cobertura efectiva del Eje D al cierre del pilotaje es del [PORCENTAJE-A-COMPLETAR]% (eventos `episodio_cerrado` con attestation firmada por clave institucional en journal externo). Cualquier evolución posterior (Certificate Transparency-style log, OpenTimestamps) queda como mejora del Eje D ya en producción, no como agenda nueva.

### Razón

El servicio existe completo y opera correctamente con dev key, pero la pubkey institucional UNSL **no está desplegada** (`docs/pilot/attestation-pubkey.pem.PLACEHOLDER` sigue como placeholder). Solo el 25% de los cierres dispararon attestation (29 XADD vs 117 cierres en el smoke 2026-05-08). La afirmación literal "cerrado" es defendible solo después del deploy. **Recomendación**: empezar por Opción A para defensa segura; si DI UNSL responde a tiempo, cambiar a Opción B antes de impresión final.

### Atado a esta decisión

- C7 (Sec 7.3) usa la redacción de Opción A. Si elegís Opción B, ajustar C7 quitando "se coordinan con la dirección de informática como condición operativa previa al cierre del piloto principal".
- En el repo: si elegís Opción B, ejecutar el checklist `docs/pilot/attestation-deploy-checklist.md`, renombrar `attestation-pubkey.pem.PLACEHOLDER` → `attestation-pubkey.pem` con la pubkey real, hacer obligatorio `AttestationProducer` en producción.

---

## C14 — Sec 8.4.1: cobertura literal del prompt — atado a v1.0.1

### OLD (Sec 8.4.1, párrafo único — línea 604)

> La cobertura efectiva de la v1.0.0 en instrucciones literales del prompt corresponde a **GP1, GP2 y GP4 (tres de diez guardarraíles formales)**. El guardarraíl GP3 ("descomponer ante incomprensión manifestada") no tiene anclaje literal en la formulación minimalista del prompt v1.0.0; el principio "dejar que se equivoque y descubra el bug por sí mismo" del prompt corresponde semánticamente a GP4 (estimulación de la verificación ejecutiva), no a GP3. La cobertura de GP3 queda delegada a la inferencia base del modelo de lenguaje subyacente, lo cual constituye un compromiso explícito sobre el alcance efectivo del control pedagógico vía prompting. **La incorporación literal de GP3 al prompt es parte de la versión v1.1.0 prevista en el Eje C de la agenda confirmatoria.** [...]
>
> Nota: el HTML comment del archivo del prompt v1.0.0 vigente registra una asignación obsoleta de GP3 al Principio 3; **la corrección documental sin cambio sustantivo se proyecta como bump v1.0.1**, fecha de aplicación documentada en el cierre del piloto.

### NEW (si se decide crear v1.0.1 con HTML comment corregido)

> La cobertura efectiva de la v1.0.1 en instrucciones literales del prompt corresponde a **GP1, GP2 y GP4 (tres de diez guardarraíles formales)**. El guardarraíl GP3 ("descomponer ante incomprensión manifestada") no tiene anclaje literal en la formulación minimalista del prompt; el principio "dejar que se equivoque y descubra el bug por sí mismo" del prompt corresponde semánticamente a GP4 (estimulación de la verificación ejecutiva), no a GP3. La cobertura de GP3 queda delegada a la inferencia base del modelo de lenguaje subyacente, lo cual constituye un compromiso explícito sobre el alcance efectivo del control pedagógico vía prompting. **La incorporación literal de GP3 al prompt es parte de la versión v1.1.0 prevista en el Eje C de la agenda confirmatoria.** [...]
>
> Nota: la versión v1.0.1 del prompt corrige una asignación obsoleta de GP3 al Principio 3 que figuraba en el HTML comment de la v1.0.0 inicial, sin alterar el cuerpo del prompt visible al modelo. La diferencia entre v1.0.0 y v1.0.1 es exclusivamente documental.

### NEW (si se decide mantener v1.0.0 sin crear v1.0.1)

> La cobertura efectiva de la v1.0.0 en instrucciones literales del prompt corresponde a **GP1, GP2 y GP4 (tres de diez guardarraíles formales)**. El guardarraíl GP3 ("descomponer ante incomprensión manifestada") no tiene anclaje literal en la formulación minimalista del prompt v1.0.0; el principio "dejar que se equivoque y descubra el bug por sí mismo" del prompt corresponde semánticamente a GP4 (estimulación de la verificación ejecutiva), no a GP3. La cobertura de GP3 queda delegada a la inferencia base del modelo de lenguaje subyacente. **La incorporación literal de GP3 al prompt es parte de la versión v1.1.0 prevista en el Eje C de la agenda confirmatoria.** [...]
>
> Nota: el HTML comment de auditoría humana del archivo del prompt v1.0.0 vigente declara cuatro guardarraíles cubiertos (GP1+GP2+GP3+GP4) en lugar de los tres efectivamente literales (GP1+GP2+GP4). Esta inconsistencia documental, sin cambio sustantivo en el cuerpo del prompt visible al modelo, se subsana en la corrección de auditoría programada para el cierre del piloto.

### Razón

Si se crea v1.0.1 (recomendado, ver pieza lista en sección "Anexos operativos" abajo), la nota se simplifica a "v1.0.0 → v1.0.1 fue corrección documental". Si no se crea, hay que reconocer la inconsistencia entre la afirmación de la tesis (3/10) y el HTML comment vigente del archivo (4/10).

---

## C15 — Anexo A.2: clarificar "~280 palabras"

### OLD (Anexo A.2, párrafo único — línea 1428)

> [...] La opción por una formulación minimalista —**~280 palabras en total**— es deliberada y responde a hallazgos del proceso iterativo de diseño [...]

### NEW

> [...] La opción por una formulación minimalista —**~280 palabras en el cuerpo visible al modelo, distribuidas en las cuatro secciones de identidad y objetivo, principios pedagógicos, prácticas que el tutor no realiza, y formato y contexto**— es deliberada y responde a hallazgos del proceso iterativo de diseño [...]

### Razón

`wc -w ai-native-prompts/prompts/tutor/v1.0.0/system.md = 483`. El cuerpo visible al modelo (sin HTML comment) ronda las 280 palabras. La nota aclara que el "tamaño" se refiere al cuerpo, no al archivo total.

---

## C16 — Anexo A.4: hash SHA-256 del prompt

### OLD (Anexo A.4, párrafo único — línea ~1474)

> El hash SHA-256 de referencia del prompt v1.0.0 tal como se despliega en producción **[A COMPLETAR: valor del hash SHA-256 del prompt v1.0.0 en producción, a computar del texto definitivo desplegado]** se incorporará a la versión definitiva. El cálculo se realiza sobre el texto codificado en UTF-8 sin modificaciones. El valor resultante se almacena en el Servicio de gobernanza y se incorpora al cálculo del hash de cada evento del CTR.

### NEW (si se mantiene v1.0.0)

> El hash SHA-256 de referencia del prompt v1.0.0 tal como se despliega en producción es **`238cbcbb95810e261afc8baf2ca92196395eea97ebf23d28396fe980e5fadd93`**. El cálculo se realiza sobre el texto codificado en UTF-8 sin modificaciones. El valor resultante se almacena en el Servicio de gobernanza y se incorpora al cálculo del hash de cada evento del CTR mediante el campo `prompt_system_hash` (Sección 7.3).

### NEW (si se crea v1.0.1)

> El hash SHA-256 de referencia del prompt v1.0.1 tal como se despliega en producción es **`[A-RECALCULAR-DESPUES-DE-CREAR-v1.0.1]`** (calculable mediante `sha256sum ai-native-prompts/prompts/tutor/v1.0.1/system.md`). El cálculo se realiza sobre el texto codificado en UTF-8 sin modificaciones. El valor resultante se almacena en el Servicio de gobernanza y se incorpora al cálculo del hash de cada evento del CTR mediante el campo `prompt_system_hash` (Sección 7.3). El hash del prompt v1.0.0 inicial, anterior a la corrección documental del HTML comment, fue `238cbcbb95810e261afc8baf2ca92196395eea97ebf23d28396fe980e5fadd93`; los eventos del CTR registrados con esa versión preservan su trazabilidad mediante la combinación de `prompt_system_hash` y `prompt_system_version` (Sección 7.4).

### Razón

Calculé el hash con `sha256sum ai-native-prompts/prompts/tutor/v1.0.0/system.md = 238cbcbb...fadd93`. El placeholder `[A COMPLETAR]` ya no necesita esperar al cierre del piloto.

---

## Anexos operativos — piezas listas para copiar

### A.1. Texto literal propuesto para `ai-native-prompts/prompts/tutor/v1.0.1/system.md`

> Si se decide crear v1.0.1 (recomendado, atado a C14 y C16), copiar este contenido literal:

```markdown
# Tutor socratico N4 — prompt del sistema (v1.0.1)

Sos un tutor socratico de programacion para estudiantes universitarios. Tu
objetivo es que el estudiante **aprenda a pensar**, no que te copie la
solucion.

## Principios (en orden de prioridad)

1. **NO des la solucion directa.** Si el estudiante pide codigo, pedile
   primero que describa el problema con sus palabras y proponga un enfoque.
2. **Haces preguntas antes que dar respuestas.** Preferis "que crees que
   pasaria si..." o "por que pensas que eso no funciona" a afirmaciones.
3. **Dejar que se equivoque.** Si propone algo con un bug, NO lo corriges
   de inmediato — guialo a que descubra el bug por si mismo.
4. **Validar conocimientos previos.** Si el estudiante usa un concepto,
   preguntale que es y como funciona antes de seguir.
5. **Reconocer avances.** Cuando demuestra comprension real (no solo
   repeticion), reforzalo explicitamente.

## Lo que NO hace el tutor

- Generar codigo completo por el estudiante (salvo ejemplos chicos
  ilustrativos de una tecnica, nunca de la solucion del TP).
- Dar el resultado de un ejercicio sin que el estudiante lo razone.
- Asumir que el estudiante ya sabe algo que no verifico.
- Responder con "si, perfecto" cuando hay errores por corregir.

## Formato de respuesta

- Breve. Una o dos preguntas o sugerencias por turno.
- Concreto. Si el estudiante tiene un bug, apunta a donde mirar (no que
  mirar).
- En espanol rioplatense neutro, sin modismos fuertes.
- Sin emojis.

## Contexto del TP

El estudiante esta trabajando sobre un trabajo practico especifico de la
catedra. Vos no conoces el enunciado completo — el estudiante te lo va a
compartir si es relevante. NO supongas requisitos que el enunciado no
establecio.

<!--
================================================================================
Mapping a los guardarrailes formales de la tesis (Capitulo 8)
================================================================================
NOTA: este bloque es invisible para el modelo (HTML comment). Sirve como
auditoria humana del cumplimiento de los guardarrailes pedagogicos (GP) y
de contenido (GC) de la tesis sobre este prompt.

Cobertura explicita en v1.0.1
------------------------------
GP1 (no entregar solucion)             <- Principio 1 + Lo-que-NO-hace punto 1
GP2 (responder preguntas con preguntas) <- Principio 2
GP4 (estimular verificacion ejecutiva) <- Principio 3 (descubrir el bug solo)

Sin cobertura explicita en v1.0.1 (pendiente v1.1.0+)
------------------------------------------------------
GP3 (descomponer ante incomprension)   <- delegado a inferencia base del LLM
GP5 (reconocer alcance excedido)       <- agregar regla de fallback explicita
GC1 (no info falsa / hallucination)    <- agregar restriccion explicita
GC2 (no preferencias comerciales)      <- agregar restriccion explicita
GC4 (privacidad de datos personales)   <- agregar restriccion explicita
GC5 (redirigir temas sensibles)        <- agregar regla de redireccion

Delegado a la alineacion base del LLM (no enforced en este prompt)
------------------------------------------------------------------
GC3 (no contenido ofensivo)            <- safety layer de Anthropic / OpenAI

Hallazgo: este prompt v1.0.1 cubre 3/10 guardarrailes formales explicitamente.
La tesis (Cap 8) lo reconoce como intencionalmente minimalista. La diferencia
con v1.0.0 es exclusivamente documental: corrige la asignacion obsoleta de
GP3 al Principio 3 (Sec 8.4.1 de la tesis). El cuerpo del prompt visible al
modelo es identico al de v1.0.0 — solo cambia el HTML comment de auditoria.
Los pendientes GP3 + GP5 + GC1/GC2/GC4/GC5 son agenda confirmatoria para
v1.1.0-unsl o posterior.
================================================================================
-->
```

**Diferencia con v1.0.0**:
- Header línea 1: `(v1.0.0)` → `(v1.0.1)`.
- HTML comment: cobertura explícita reducida de GP1+GP2+GP3+GP4 (4/10) a GP1+GP2+GP4 (3/10).
- Línea movida: `GP3` pasa de la sección "Cobertura explicita" a la sección "Sin cobertura explicita" (con nota de delegación).
- Hallazgo final actualizado: 4/10 → 3/10 + nota de "diferencia con v1.0.0 es exclusivamente documental".
- **Cuerpo visible al modelo**: idéntico al de v1.0.0 (líneas 1-42). El `prompt_system_hash` cambia, pero el comportamiento pedagógico del tutor no.

### A.2. Comandos para aplicar v1.0.1

```bash
# 1. Crear el archivo nuevo (copiar contenido del bloque A.1 arriba)
mkdir -p ai-native-prompts/prompts/tutor/v1.0.1
# escribir system.md con el contenido literal

# 2. Calcular el hash nuevo
sha256sum ai-native-prompts/prompts/tutor/v1.0.1/system.md
# anotar el resultado para C16

# 3. Actualizar manifest
# editar ai-native-prompts/manifest.yaml para apuntar tutor: v1.0.1

# 4. Alinear config del tutor-service
# editar apps/tutor-service/src/tutor_service/config.py:37
# default_prompt_version: str = "v1.0.1"

# 5. Validar consistencia
uv run pytest apps/tutor-service/tests/unit/test_config_prompt_version.py -v

# 6. Commit
git add ai-native-prompts/prompts/tutor/v1.0.1/ ai-native-prompts/manifest.yaml apps/tutor-service/src/tutor_service/config.py
git commit -m "feat(prompt): bump tutor v1.0.0 -> v1.0.1 (correccion documental HTML comment, 4/10 -> 3/10)"
```

### A.3. Validación final post-edición

Después de aplicar todas las ediciones a la tesis, validar:

```bash
# 1. Re-correr el análisis bidireccional para confirmar que las afirmaciones coinciden
# (re-spawn de los 4 sub-agentes con prompts actualizados)

# 2. Generar el DOCX del protocolo UNSL con los hashes nuevos
make generate-protocol

# 3. Imprimir PDF de tesis editada y verificación visual humana
# (revisar que la numeración de secciones, figuras y tablas no se haya desplazado)

# 4. Recalcular hash de referencia del Anexo A.4
sha256sum ai-native-prompts/prompts/tutor/<version-vigente>/system.md
```

---

## Lectura para próximo dev / director

Si llegaste a este documento y no leíste el análisis bidireccional general:
- Este `.md` es el **diff aplicable** sobre la tesis.
- El `.md` complementario `analisis-bidireccional-tesis-codigo-2026-05-08.md` tiene el **análisis general** y el plan operativo en 4 fases.
- Los dos juntos te dan: **qué cambiar (este doc) + por qué cambiarlo (análisis general) + cómo ejecutarlo en orden (Sec 12 del análisis general)**.

**Orden de aplicación recomendado**:
1. Decidir Opción A o B para C13 (Eje D). **Recomendación: A para defensa, B si DI UNSL responde a tiempo**.
2. Aplicar las 16 ediciones literales a la tesis (la mayoría son OLD → NEW directos sobre el `.docx`).
3. Si se decide crear v1.0.1: ejecutar comandos de A.2.
4. Validar con A.3.
5. Re-imprimir PDF.

**Tiempo total estimado**: 4-5 horas concentradas si Opción A en C13. Sumar 1-2 días con DI UNSL si Opción B.
