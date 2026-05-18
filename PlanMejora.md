# Plan de Mejora — paper_conaiisi.pdf vs implementación AI-Native N4

**Fecha**: 2026-05-17
**Autor del análisis**: auditoría asistida por Claude (instrucción del autor de tesis, Alberto Cortez).
**Objeto**: contrastar la versión 2026-05-16 (tercera ronda de consolidación) del paper *"Modelo N4 de trazabilidad cognitiva para la enseñanza universitaria de programación con asistentes de IA generativa"* (Cortez & Garis, UTN-FRM + UNSL) contra el código del monorepo `AI-NativeV3-main/` y producir un plan de mejoras priorizado.

**Insumos**:
- `paper_conaiisi.pdf` (1241 líneas extraídas con `pdftotext`, 10 secciones + Apéndice A).
- `docs/research/ppconarev.md` (2026-05-10) — revisó la versión vieja del paper (`ppcona.docx`).
- `docs/research/audi2.md` (2026-05-10) — auditoría de 20 capabilities × 4 criterios.
- `docs/research/plan-accion.md` — plan operativo de 26 acciones, 23 cerradas.
- Auditoría técnica fresca del código `AI-NativeV3-main/` (este informe).

---

## 0. Resumen ejecutivo

Antes que nada, lo que ya está bien: la versión 2026-05-16 del paper alineó dos divergencias críticas que `ppconarev.md` había levantado contra `ppcona.docx` — el umbral del kappa pasó a **κ ≥ 0,70** (paper §6.1, §7.1, Tabla 5) consistente con el código tras ADR-046, y el protocolo muestral quedó formalmente dual (Protocolo A 200 eventos estratificados + Protocolo B 50 episodios). El paper hoy publica lo que el código opera. Esto es importante: la conversación de divergencia paper/código en su forma "el paper miente sobre el código" está cerrada.

La auditoría técnica de las constantes del Apéndice A.4, las fórmulas de hashing (incluyendo la fórmula exacta de `chunks_used_hash`), el sharding del CTR a nivel de bus (`NUM_PARTITIONS = 8`, streams `ctr.p0..ctr.p7`, fix Windows `asyncio.add_signal_handler`), la dualidad manifest-config y la regla N3/N4 de `tests_ejecutados` post-v1.2.0 **devolvió match exacto en los 12 puntos críticos**. La integridad técnica de las afirmaciones del paper sobre el sistema instrumental no tiene falsos positivos visibles.

Lo que sigue son las **mejoras reales** organizadas en cuatro niveles:

| Nivel | Categoría | Cantidad |
|---|---|---|
| **P0** | Bloqueadores de defensa doctoral ya identificados por `audi2.md` y `plan-accion.md` | 3 ítems |
| **P1** | Brechas conceptuales nuevas — lenguaje del paper no migrado a código/UI/ADRs | 4 ítems |
| **P2** | Instrumentos del diseño cuasi-experimental (§6.2) en estado de draft o ausentes | 4 ítems |
| **P3** | Agenda de extensión explícitamente declarada por el paper (no urgente) | 5 ítems |

**Conclusión central de cara a la defensa**: la tesis es defendible hoy con los disclaimers acotados que `audi2.md` ya identificó. Las brechas P1 son cosméticas pero **importantes para la coherencia paper↔código que el comité va a inspeccionar**. Las P2 son la deuda metodológica más sustantiva — los instrumentos del diseño quasi-experimental existen como drafts pero no están operacionalizados, y para validar H1/H2 hace falta cerrarlos. Las P3 son honestas: el paper las declara como agenda y no hay que tocarlas para defender.

---

## 1. Metodología de la auditoría

### 1.1 Criterio de clasificación

Cada claim del paper se evaluó contra el código real con uno de cinco estados:

- ✅ **IMPLEMENTADO**: el código materializa el claim con file_path verificable.
- ⚠️ **PARCIAL**: existe pero le falta algo específico (test stale, feature-flag OFF, draft sin operacionalizar).
- ❌ **FALTANTE**: el paper afirma o presupone algo que no está en código/docs/UI.
- 📋 **AGENDA**: el paper explícitamente declara el ítem como extensión futura — no es bug.
- ❓ **NO VERIFICABLE**: requiere acceso a sistema externo (VPS UNSL, DB del piloto real).

### 1.2 Insumos cruzados

`audi2.md` ya cubre la dimensión **capability funcional × 4 criterios estrictos**. `ppconarev.md` cubre el **paper viejo (ppcona.docx) vs código**. Este plan de mejora se concentra en lo **nuevo de la versión 2026-05-16 del paper** y en lo que las auditorías previas no cubrieron, evitando duplicar trabajo.

---

## 2. Lo que está fiel al 100% (no requiere acción)

Esta sección existe explícitamente como contrapeso: el sistema honra el paper en su núcleo técnico con un grado de fidelidad poco común. Antes de discutir mejoras, conviene fijar la base.

### 2.1 Constantes auditables del Apéndice A.4 (Tabla A.1 del paper)

| Constante | Valor paper | Valor código | Ubicación verificada |
|---|---|---|---|
| `LABELER_VERSION` | "1.2.0" | ✅ "1.2.0" | `apps/classifier-service/src/classifier_service/services/event_labeler.py:76` |
| `GUARDRAILS_CORPUS_VERSION` | "1.2.0" | ✅ "1.2.0" | `apps/tutor-service/src/tutor_service/services/guardrails.py:36` |
| `MIN_STUDENTS_FOR_QUARTILES` | 5 | ✅ 5 | `packages/platform-ops/src/platform_ops/cii_alerts.py:30` |
| `MIN_EPISODES_FOR_LONGITUDINAL` | 3 | ✅ 3 | `packages/platform-ops/src/platform_ops/cii_longitudinal.py` (test ref `tests/test_cii_longitudinal.py:296`) |
| `NUM_PARTITIONS` | 8 | ✅ 8 | `apps/ctr-service/src/ctr_service/services/producer.py:22` |
| `ANOTACION_N1_WINDOW_SECONDS` | 120 | ✅ 120.0 | `event_labeler.py:80` |
| `ANOTACION_N4_WINDOW_SECONDS` | 60 | ✅ 60.0 | `event_labeler.py:81` |
| `GENESIS_HASH` | "0" * 64 | ✅ | `packages/contracts/src/platform_contracts/ctr/hashing.py` |

### 2.2 Hashes versionados (§7.2 + Apéndice A.4)

| Hash | Paper afirma | Verificado |
|---|---|---|
| `classifier_config_hash` | Persiste con cada Classification | ✅ UNIQUE constraint `(episode_id, classifier_config_hash)` en migration `20260901_0001_classifier_schema.py:50`; emitido en `routes/classify_ep.py:109`. |
| `guardrails_corpus_hash` | Persiste en payload `intento_adverso_detectado` | ✅ `apps/tutor-service/src/tutor_service/services/guardrails.py:210`. |
| `chunks_used_hash` | Fórmula EXACTA `sha256("\|".join(sorted(str(id) for id in chunk_ids))...)` (RN-026); viaja `prompt_enviado` → `tutor_respondio` del mismo turno | ✅ Fórmula coincide bit a bit en `apps/content-service/src/content_service/services/retrieval.py::_hash_chunk_ids`; propagación verificada por test `chunks_used_hash_se_propaga` marcado CRÍTICO en `tutor_core.py::interact`. |
| `prompt_system_hash` | Persiste en Episode y en cada evento del CTR | ✅ Field declarado con `min_length=64, max_length=64` en `docs/specs/reglas.md:659`; embebido en payload por el productor. |

### 2.3 Sharding del CTR (Apéndice A.1)

- ✅ Fórmula exacta `int.from_bytes(sha256(str(episode_id).encode("utf-8")).digest()[:4], "big") % NUM_PARTITIONS` en `producer.py:28-29`.
- ✅ Stream naming `ctr.p0..ctr.p7` en `producer.py:43` y `partition_worker.py:54`; test `test_partition_worker.py:65` valida la lista completa.
- ✅ Single-writer enforce: `consumer_group: str = "ctr_workers"` en `partition_worker.py:53`, `xgroup_create` en `:88-90`.
- ✅ Fix Windows `try/except NotImplementedError` envolviendo `asyncio.add_signal_handler` en `partition_worker.py:464-465`.

### 2.4 Manifest-config dualidad (Apéndice A.3)

- ✅ Archivo `ai-native-prompts/manifest.yaml` existe (32 líneas, declara tutor v1.1.0, classifier v1.0.0, reflection v1.0.0, tp_generator v1.0.0, ejercicio_generator v1.0.0).
- ✅ Constante `default_prompt_version` en `apps/tutor-service/src/tutor_service/config.py` (drift con manifest documentado en `docs/servicios/tutor-service.md:175`).
- ✅ Endpoint `GET /api/v1/active_configs` en `apps/governance-service/src/governance_service/routes/prompts.py:43-45`.
- ✅ Test `test_manifest_yaml_existe_y_se_parsea` en `apps/tutor-service/tests/unit/test_config_prompt_version.py:42`.

### 2.5 Reglas del labeler v1.2.0

- ✅ Override `tests_ejecutados` N3/N4 (§7.2): `test_count_failed > 0 → N3`; `failed == 0` con ventana ≥ 60s desde último `tutor_respondio → N4`; else `N3`. Implementado exacto en `event_labeler.py:185-201`.
- ✅ `_EXCLUDED_FROM_FEATURES` con `reflexion_completada`, `tp_entregada`, `tp_calificada` (§5.2): `pipeline.py:63-69`, filtrado aplicado en `pipeline.py:86-88`.

### 2.6 Distinción CCD-piloto-1 vs CCD-conceptual (§4.5 footnote)

Esta es la única distinción introducida en la tercera ronda de consolidación del paper que **sí migró al código**. Documentada en `apps/classifier-service/src/classifier_service/services/ccd.py:43-67` con plan de activación explícito. Bien hecho — es el modelo a seguir para resolver las brechas P1.

### 2.7 Casbin policies (Apéndice A.2)

Paper afirma 170 policies (verificado 2026-05-09 por el paper). Coincidente con `CLAUDE.md` interno del repositorio. Bumpeos atribuidos correctamente a ADR-016 (14), ADR-039 (8), ADR-041 (7). ✅

---

## 3. P0 — Bloqueadores de defensa doctoral

Estos NO son hallazgos nuevos: `audi2.md` y `plan-accion.md` ya los identificaron. Los listo acá con el cruce de impacto sobre claims específicos del paper.

### 3.1 [P0-1] Re-clasificar 106 classifications con hash legacy pre-v1.2.0

- **Impacto en paper**: §7.2 declara honestamente la deuda — *"el sistema acumuló un conjunto de 106 clasificaciones cuyo hash fue computado con una versión anterior del etiquetador (previa al bumpeo a LABELER_VERSION = "1.2.0")"*. El paper dice también: *"El plan de re-clasificación masiva está formalizado como acción A1 del plan operativo del proyecto y requiere acceso a la base de datos real del piloto"*.
- **Bloquea**: H1 y H2 (Tabla 6 del paper marca ambas como "Pendiente").
- **Estado actual**: pre-condición A12 (idempotencia de `persist_classification`) cumplida. Falta ejecución sobre DB real del piloto.
- **Acción**: ejecutar A1 del `plan-accion.md` — worker batch que re-clasifica los 106 con `LABELER_VERSION = "1.2.0"` vigente.
- **Esfuerzo**: ~1h con script + verificación, depende de acceso a DB del piloto UNSL.
- **Owner**: Cortez + DI UNSL.

### 3.2 [P0-2] Cierre del protocolo dual de validación intercoder κ ≥ 0,70

- **Impacto en paper**: §7.1 prescribe Protocolo A (200 eventos estratificados 50/nivel N1-N4) + Protocolo B (50 episodios cerrados en 3 categorías), totalizando 250 unidades por anotador + 20 episodios de calibración. La Tabla 6 marca el componente como "En ejecución".
- **Bloquea**: H3, además de las features `socratic_compliance` (ADR-044) y `lexical_anotacion_override` (ADR-045) que siguen en feature-flag OFF.
- **Estado actual**: A2 del `plan-accion.md` pendiente. Cuello de botella académico más grande del proyecto (≈25-30h por docente × 2 docentes).
- **Acción**: coordinar 2 docentes auxiliares UNSL, ejecutar capacitación + sesión calibración 20 episodios + Protocolo A (200 eventos) + Protocolo B (50 episodios), reportar κ con IC95% por par (Clasificador vs Anotador 1, Clasificador vs Anotador 2, Anotador 1 vs Anotador 2), por separado para A y para B.
- **Esfuerzo**: semanas de coordinación humana.
- **Owner**: Cortez + Ana Garis (co-autora) + 2 docentes UNSL a designar.

### 3.3 [P0-3] Levantar `integrity-attestation-service` con consumer activo en VPS UNSL

- **Impacto en paper**: §5.2 enumera attestations Ed25519 como capacidad de plataforma. El `audi2.md §3.2` declara: *"NO se levanta en dev local. Los eventos se acumulan en Redis hasta que el consumer institucional viene online. Sin evidencia de firmas Ed25519 reales en piloto."*
- **Bloquea**: criterio C3 (producción piloto) de la capability "CTR cadena criptográfica" — el CTR funciona, pero la segunda capa criptográfica Ed25519 no produce firmas reales en el piloto.
- **Acción**: deployar servicio en VPS UNSL, cuantificar XLEN del stream `attestation.requests`, registrar firmas reales producidas.
- **Esfuerzo**: coordinación DI UNSL para VPS + verificación.
- **Owner**: Cortez + DI UNSL.

---

## 4. P1 — Brechas conceptuales del paper no migradas al código

Acá viven los **hallazgos nuevos de esta auditoría** que no aparecen en `ppconarev.md` ni en `audi2.md`. Son brechas de **vocabulario/documentación**, no de funcionalidad. Bajo costo, alto valor para coherencia ante el comité doctoral.

### 4.1 [P1-1] Marcador anti-reificación "perfil tipológico de apropiación X" no llegó a UI

- **Claim del paper (§4.4)**: la tercera ronda de consolidación introdujo el marcador léxico *"perfil tipológico de apropiación X"* como anti-reification marker, alineado con el principio "no-etiquetado individual" del protocolo interpretativo. El paper insiste en que **las categorías describen episodios, no estudiantes**.
- **Realidad código**: `apps/web-teacher/src/utils/docenteLabels.ts:7-11` usa etiquetas planas — "Delegacion pasiva", "Apropiacion superficial", "Apropiacion reflexiva". Sin el marcador "perfil tipológico de".
- **Impacto académico**: si un docente abre el dashboard y ve "Apropiación reflexiva" como un atributo del estudiante, está haciendo precisamente la reificación que el paper §4.4 explícitamente quiere prevenir. Un revisor del comité que cruce paper con UI puede señalarlo.
- **Acción**: actualizar `docenteLabels.ts` para que el copy diga *"Perfil tipológico: apropiación reflexiva (este episodio)"* o equivalente. Adicionalmente, en cualquier vista cohortal que agregue categorías de apropiación por estudiante, agregar disclaimer textual: *"Las categorías describen episodios, no estudiantes — no usar para diagnóstico individual"*.
- **Esfuerzo**: 30-60 min (1 archivo principal + búsqueda de otros lugares que usen los labels).
- **Owner**: dev frontend.

### 4.2 [P1-2] Marcos interpretativos MI1, MI2, MI3 no documentados en ADRs ni código

- **Claim del paper (§4.3)**: la tercera ronda explicitó tres marcos interpretativos de tercer orden — **MI1** (calidad epistémica de la trayectoria), **MI2** (apropiación reflexiva en sentido fuerte), **MI3** (coherencia estructural multidimensional como horizonte evaluativo). El paper insiste en que son horizontes interpretativos, NO hipótesis contrastables (esas son H1-H3 sobre indicadores de segundo orden).
- **Realidad código**: búsqueda por `MI1|MI2|MI3` en código + comments + ADRs devolvió 0 archivos. La distinción no llegó al repositorio.
- **Impacto académico**: si el comité pregunta "¿cómo se distingue en el código un indicador de segundo orden contrastable de un constructo sintético?", no hay nada a qué apuntar más que el JSONB de coherencias y el árbol de decisión. La distinción epistemológica que el paper §4.3 pone en el centro queda sólo en prosa.
- **Acción**: crear **ADR-047 "Marcos interpretativos MI1, MI2, MI3"** que documente la distinción, indique qué indicadores operacionales del código contribuyen a cada MI (sin pretender medirlos directamente), y referencie que MI1-MI3 NO se validan empíricamente sino por triangulación con juicio docente + auto-reconstrucción estudiantil. Adicional: agregar comments en `ccd.py`, `pipeline.py`, `tree.py` mencionando qué MI orienta la lectura de los indicadores que ese archivo computa.
- **Esfuerzo**: ADR-047 (~2h escritura + 1h revisión coautoral con Garis) + comments en código (~30 min).
- **Owner**: Cortez (ADR) + dev (comments).

### 4.3 [P1-3] Siete principios interpretativos (§7.3) no documentados en ADRs

- **Claim del paper (§7.3)**: el protocolo interpretativo incorpora **7 principios rectores**:
  1. **Contextualidad**: toda lectura considera el contexto institucional.
  2. **No-reducción**: los constructos sintéticos no se reducen a indicadores.
  3. **Triangulación obligatoria**: toda inferencia involucra ≥2 fuentes independientes.
  4. **No-etiquetado individual**: las categorías describen episodios, no estudiantes.
  5. **No-uso para alto stake sin triangulación**.
  6. **Explicitación de versión**: todo reporte incluye `classifier_config_hash`.
  7. **Apertura a la crítica**: los datos están disponibles para reanálisis externo.
- **Realidad código**: búsqueda por `contextualidad|no-reduccion|triangulacion obligatoria|no-etiquetado individual` en `docs/` + ADRs devolvió 0 archivos. Sólo viven en la prosa del paper.
- **Impacto académico**: el principio 6 (explicitación de versión) está perfectamente operacionalizado por el `classifier_config_hash`; los principios 1-5, 7 son posturas declaradas que ningún ADR ni doc del repo registra. Si el comité pregunta "¿dónde está formalizado el protocolo interpretativo?", la respuesta hoy es "en el paper, no en el repo".
- **Acción**: agregar al **ADR-047** propuesto en P1-2 (o crear ADR-048 separado) la enunciación de los 7 principios con su correspondencia operacional. Indicar para cada uno: (a) afirmación del principio, (b) si está operacionalizado en código y dónde, (c) si requiere disciplina pedagógica del docente (principios 1, 3, 5, 7 son más actitudinales que técnicos), (d) si requiere comunicación explícita al estudiante (principio 4 implica disclaimers en UI).
- **Esfuerzo**: ~2h escritura ADR.
- **Owner**: Cortez.

### 4.4 [P1-4] Cinco riesgos a priori (§8) no documentados en ADRs ni `docs/limitaciones-declaradas.md`

- **Claim del paper (§8)**: se declaran **5 riesgos a priori con mitigaciones**:
  1. **Efecto Hawthorne** — mitigación por extensión temporal del piloto.
  2. **Performatividad cognitiva** — mitigación por análisis intra-grupo.
  3. **Deriva comportamental del LLM subyacente** — mitigación por versionado del prompt.
  4. **Brecha digital previa** — mitigación por observación longitudinal antes que diagnóstico prematuro.
  5. **Sobrecarga cognitiva** — mitigación por diseño de la interfaz con feedback continuo.
- **Realidad código**: búsqueda por `Hawthorne|performatividad|deriva LLM|brecha digital|sobrecarga cognitiva` devolvió 0 archivos en `docs/` + ADRs + `docs/limitaciones-declaradas.md`. No están documentados como limitaciones del sistema.
- **Impacto académico**: `docs/limitaciones-declaradas.md` existe como inventario de gates pendientes (intercoder, content_db vacía, etc.) pero NO declara los 5 riesgos a priori que el paper formula. Discrepancia clara entre lo que el paper pone como riesgos honestos del estudio y lo que el repositorio declara como sus propias limitaciones.
- **Acción**: ampliar `docs/limitaciones-declaradas.md` con sección **"Riesgos a priori del diseño cuasi-experimental"** que enumere los 5 con su mitigación y, donde aplique, link a la implementación que materializa la mitigación (ej.: para Hawthorne, link al ciclo lectivo completo 2026; para deriva LLM, link al manifest.yaml del prompt; etc.).
- **Esfuerzo**: ~1h escritura.
- **Owner**: Cortez.

---

## 5. P2 — Instrumentos del diseño cuasi-experimental (§6.2 Tabla 4)

El paper §6.2 enumera instrumentos de medición que el diseño quasi-experimental requiere. La auditoría confirmó: 2 existen como drafts no operacionalizados, 2 están ausentes. Esta es la **deuda metodológica más sustantiva** después de los P0.

### 5.1 [P2-1] Pretest estandarizado de nivel inicial de competencia

- **Claim del paper (Tabla 4)**: variable de control "Nivel inicial de competencia" se mide con "Pretest estandarizado".
- **Realidad código**: draft existe en `docs/research/protocolo-autoeficacia-programacion.md` (v1.0.0 pendiente revisión coautoral + comité ético). NO operacionalizado como módulo/endpoint/seed.
- **Acción**:
  1. Cerrar revisión coautoral con Garis + comité ético.
  2. Operacionalizar como módulo del `academic-service` o servicio nuevo: endpoint para crear instancia de pretest, persistir respuestas (con `tenant_id`, RLS), generar score normalizado por cohorte.
  3. Seedear pretest por defecto en `seed-3-comisiones.py`.
  4. Agregar vista en `web-student` para que el estudiante lo complete antes del primer TP.
- **Esfuerzo**: ~16-24h (depende de profundidad del pretest).
- **Owner**: Cortez + dev backend + dev frontend.

### 5.2 [P2-2] Cuestionario inicial sobre experiencia previa con IA

- **Claim del paper (Tabla 4)**: variable de control "experiencia previa con IA" se mide con "cuestionario inicial".
- **Realidad código**: ❌ no encontrado en `docs/research/` ni en código.
- **Acción**:
  1. Escribir cuestionario (5-10 ítems Likert + 2-3 abiertas) que capture: meses de uso de asistentes IA, frecuencia, tipos de tarea, autopercepción de dependencia, episodios previos de delegación.
  2. Misma operacionalización que P2-1: módulo backend + persistencia + vista frontend.
- **Esfuerzo**: ~8-12h.
- **Owner**: Cortez + dev.

### 5.3 [P2-3] Pruebas comunes de transferencia (medida dependiente para H2)

- **Claim del paper (§6.1 H2, Tabla 4)**: H2 postula asociación entre coherencia estructural y desempeño en tareas de transferencia. La medida dependiente es "pruebas comunes a ambos grupos".
- **Realidad código**: draft existe en `docs/research/diseno-test-transfer.md` (v1.0.0, 5 problemas de 3-5 min — pendiente validación de contenido). NO operacionalizado.
- **Acción**:
  1. Validar contenido de los 5 problemas con cátedra UNSL.
  2. Operacionalizar como serie de TP "transfer" en el banco de ejercicios, marcados con flag específico (`is_transfer_task=True` o similar), ejecutables tanto por grupo experimental (con CTR activo) como por grupo de comparación (sin CTR).
  3. Diseñar cómo se recolectan las respuestas del grupo de comparación (¿formulario fuera del sistema? ¿módulo separado?). Decisión crítica: el grupo de comparación NO usa el sistema instrumentado — esto excluye el flujo normal de TP.
  4. Definir scoring común para ambos grupos.
- **Esfuerzo**: ~24-40h (la decisión de cómo recolectar del grupo de comparación es la parte más cara).
- **Owner**: Cortez + Garis + cátedra UNSL.

### 5.4 [P2-4] Protocolo de entrevistas semi-estructuradas

- **Claim del paper (Tabla 4)**: medidas cualitativas "Reconstrucción del proceso por el estudiante" + "juicio docente sobre trayectoria" se obtienen mediante "Entrevistas semi-estructuradas con submuestra estratificada, análisis temático".
- **Realidad código**: ❌ no encontrado script de entrevistas, ni protocolo de muestreo estratificado, ni guía de análisis temático en `docs/research/`. Presumir que es parte del protocolo del piloto general no documentado.
- **Acción**:
  1. Escribir guía de entrevista (10-15 preguntas semi-estructuradas — apertura, reconstrucción del proceso por episodio, percepción del tutor, percepción de IA en general, cierre).
  2. Definir criterios de muestreo estratificado (¿por tipo de apropiación? ¿por desempeño en pretest? ¿por género/edad?).
  3. Definir protocolo de análisis temático (¿qué framework — Braun & Clarke 2006? ¿cuántos codificadores? ¿con qué software — NVivo, Atlas.ti, manual?).
  4. Documentar todo en `docs/research/protocolo-entrevistas-piloto.md`.
- **Esfuerzo**: ~12-16h escritura + acuerdo con cátedra.
- **Owner**: Cortez + Garis.

---

## 6. P3 — Agenda explícitamente declarada (no urgente)

El paper declara estos ítems como "agenda de extensión" o "trabajo futuro" — están alineados, no son bugs. Listados para completitud y para que el comité los vea como deliberados.

### 6.1 [P3-1] Exporter Caliper Analytics 1.2 / xAPI

- **Claim del paper (§5.1)**: *"La compatibilidad técnica con un exporter conforme a Caliper Analytics o xAPI es agenda de extensión del sistema instrumental, no compromiso del presente paper"*.
- **Estado código**: ❌ no existe (búsqueda por `caliper|xapi|Caliper|xAPI` devolvió 0 archivos).
- **Estado**: 📋 AGENDA — alineado con paper.
- **Cuándo implementar**: post-defensa, si hay interés en interoperabilidad cross-platform con LMS estándar.

### 6.2 [P3-2] Similitud semántica vía embeddings (override léxico de anotaciones — G8c)

- **Claim del paper (§4.5 final)**: declarada como "agenda explícita de las líneas confirmatorias".
- **Estado código**: 🔵 SKELETON OFF — feature-flag `lexical_anotacion_override_enabled = False`. Gate κ ≥ 0,70 sobre 50+ anotaciones (P0-2).
- **Estado**: 📋 AGENDA + bloqueada por P0-2.

### 6.3 [P3-3] Postprocesamiento textual del contenido de anotaciones (socratic_compliance — Fase B)

- **Claim del paper (§4.5 final)**: declarada como agenda confirmatoria.
- **Estado código**: 🔵 SKELETON OFF — feature-flag `socratic_compliance_enabled = False` (ADR-044). Bloqueado por P0-2.

### 6.4 [P3-4] Sandbox Pyodide en cliente

- **Claim del paper (§5.2)**: *"sandbox client-side de ejecución de código con Pyodide, diferido al piloto-2 por consideraciones de validación de seguridad (ADR-033, ADR-034)"*.
- **Estado código**: 🔵 deferido al piloto-2. ADR-033 establece el gate de validación de escape analysis.

### 6.5 [P3-5] Alertas predictivas con baseline individual

- **Estado código**: 🔵 ADR-032 diferida — requiere 200+ estudiantes + 10 episodios/estudiante + 30 intervenciones etiquetadas + AUC ≥ 0,75.
- **Estado**: el paper no la promete explícitamente — está fuera del scope académico del paper actual.

---

## 7. Mapa de impacto sobre la defensa doctoral

| Bloqueador | Capability afectada (audi2) | Hipótesis afectada (paper) | Severidad |
|---|---|---|---|
| **P0-1** 106 classifications hash legacy | §3.3 Etiquetado N1-N4 | H1, H2 | 🔴 CRÍTICA |
| **P0-2** Intercoder κ ≥ 0,70 pendiente | §3.9 Kappa, §4.1 features OFF | H3 | 🔴 CRÍTICA |
| **P0-3** Attestation Ed25519 sin consumer | §3.2 CTR | (no afecta H, sí afecta narrativa "evidencia criptográfica de calidad doctoral") | 🟡 MEDIA |
| **P1-1** "Perfil tipológico" no en UI | — | (riesgo de pregunta del comité sobre reificación individual) | 🟡 MEDIA |
| **P1-2** MI1/MI2/MI3 sin ADR | — | (riesgo de pregunta sobre dónde se documenta la distinción de tres órdenes) | 🟡 MEDIA |
| **P1-3** 7 principios sin ADR | — | (riesgo de pregunta sobre formalización del protocolo interpretativo) | 🟡 MEDIA |
| **P1-4** 5 riesgos sin documentar | — | (debilidad menor: paper más honesto que repo) | 🟢 BAJA |
| **P2-1** Pretest no operacionalizado | — | H1, H2 (sin pretest no se puede controlar nivel inicial) | 🔴 CRÍTICA |
| **P2-2** Cuestionario IA previa ausente | — | H2 (sin control de experiencia previa con IA, efecto confundido) | 🟡 MEDIA |
| **P2-3** Test transferencia no operacionalizado | — | H2 directamente (medida dependiente) | 🔴 CRÍTICA |
| **P2-4** Protocolo entrevistas no formalizado | — | Triangulación cualitativa de §6 y §7.3 | 🟡 MEDIA |
| **P3-1..5** Agenda declarada | — | — | 🟢 BAJA |

**Lectura**: los críticos para defender H1/H2 son **5 ítems** — P0-1, P0-2, P2-1, P2-3. Los demás son riesgos de calidad pero no bloqueadores estructurales.

---

## 8. Plan de ejecución sugerido

### 8.1 Sprint corto (1-2 semanas, bajo costo)

Estos cierran las brechas P1 enteras y permiten que el paper y el repo estén en plena coherencia documental:

1. **P1-1**: actualizar `docenteLabels.ts` con marcador anti-reificación (30-60 min).
2. **P1-2 + P1-3**: escribir **ADR-047 "Marcos interpretativos MI1-MI3 + Protocolo interpretativo de 7 principios"** (~3-4h).
3. **P1-4**: ampliar `docs/limitaciones-declaradas.md` con sección "Riesgos a priori" (~1h).
4. Cierre del fix de test `test_prompt_con_jailbreak_emite_evento_adverso` documentado en `audi2.md §5.1` (~15 min — fixture stale).

**Resultado**: paper↔código alineados al 100% en lo documental.

### 8.2 Sprint medio (3-6 semanas, costo medio)

5. **P0-1**: re-clasificar 106 históricos contra DB del piloto real (1h ejecución + coordinación DI UNSL).
6. **P0-3**: levantar `integrity-attestation-service` en VPS UNSL (coordinación DI UNSL + verificación).
7. **P2-2**: cuestionario inicial IA previa (8-12h).
8. **P2-4**: protocolo de entrevistas semi-estructuradas (12-16h).

**Resultado**: P0 técnicos cerrados, instrumentos cualitativos del diseño operacionalizados.

### 8.3 Sprint largo (2-4 meses, alto costo)

9. **P0-2**: validación intercoder Protocolo A + B con 2 docentes UNSL (~50-60h totales de docentes + coordinación).
10. **P2-1**: pretest estandarizado operacionalizado (~16-24h dev + revisión académica).
11. **P2-3**: pruebas comunes de transferencia (24-40h + decisión cómo recolectar grupo comparación).
12. **Recolección piloto real con n ≥ 64 por grupo** según análisis de potencia §6.2.

**Resultado**: estudio cuantitativo capaz de validar H1, H2, H3 con la potencia estadística que el paper exige.

### 8.4 Agenda futura (post-defensa)

13. P3-1 (Caliper/xAPI exporter) si hay interés en interoperabilidad.
14. P3-2, P3-3 (features bloqueadas por P0-2) — se activan apenas P0-2 cierre.
15. P3-4 (Pyodide piloto-2).
16. P3-5 (alertas predictivas baseline) — requiere n ≥ 200.

---

## 9. Conclusión

Lo bueno: el paper 2026-05-16 publicó una versión que el código respalda fielmente en su núcleo técnico. Las constantes, los hashes, las fórmulas, el sharding, el manifest, las reglas del labeler — todo verificado contra archivos y líneas específicas, sin un solo claim falso.

Lo perfectible: tres categorías de brechas distintas y resolubles con esfuerzo proporcional al impacto:

- **3 bloqueadores técnicos ya identificados** (P0-1 a P0-3) que `audi2.md` y `plan-accion.md` mapean bien — re-clasificación, intercoder, attestation.
- **4 brechas conceptuales nuevas de bajo costo** (P1) que cierran el alineamiento documental paper↔código antes de la defensa — "perfil tipológico", MI1-MI3, 7 principios, 5 riesgos. Estimado total: ~6-8h de escritura.
- **4 instrumentos del diseño cuasi-experimental** (P2) que existen como drafts o están ausentes y que son la deuda metodológica más sustantiva — pretest, cuestionario IA, transferencia, entrevistas. Esta es la categoría que **define si H1/H2 se pueden validar**.

La tesis es defendible hoy con disclaimers acotados (los mismos que `audi2.md` ya identificó). Cerrar P1 (sprint corto) eleva la calidad documental antes de la defensa con esfuerzo bajo. Cerrar P2 + P0-1 + P0-2 (sprints medio + largo) habilita la **validación empírica completa** que el paper formula como compromiso.

La recomendación operativa es ejecutar P1 ya (es trabajo de Cortez + dev local en el wrapper), coordinar P0-1 y P0-3 con DI UNSL para entrar al sprint medio cuanto antes, y planificar P0-2 + P2 para el cierre del semestre lectivo 2026 que es cuando se puede coordinar a las docentes etiquetadoras y al grupo de comparación.

---

**Trazabilidad**: este documento se construyó cruzando el texto íntegro del PDF (1241 líneas) con auditoría técnica de file_path:line_number en `AI-NativeV3-main/`, contrastando con los hallazgos previos de `ppconarev.md` (paper viejo vs código) y `audi2.md` (capabilities × 4 criterios). Cada claim del paper que se reporta acá tiene cita textual en el PDF (sección referenciada) y, donde aplica, file_path:line_number del código verificado.
