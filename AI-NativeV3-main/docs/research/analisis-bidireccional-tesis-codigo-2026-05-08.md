# Análisis bidireccional Tesis v3.4 ↔ Código v1.0.0

**Autor del análisis**: pase automatizado con 4 sub-agentes paralelos sobre el repo + parseo de la tesis docx.
**Fecha**: 2026-05-08.
**Tesis**: `tesis_v3_4_ronda2_aceptada.docx`.
**Código**: `/home/juanisarmiento/ProyectosFacultad/Juani2so` (branch `main`, último commit `45a99e0`).
**Convención de marcadores**: ✓ confirmado · ✗ DIFIERE · ⚠ parcial / matizado.

> **NOTA PARA EL LECTOR (próximo dev / director de tesis)**
>
> Este documento tiene **dos partes**:
> 1. **Secciones 1-10**: análisis bidireccional verificado contra el código (fotografía 2026-05-08).
> 2. **Sección 11**: recomendaciones priorizadas, **reorganizadas** en (11.A) cambios YA APLICADOS en esta sesión y (11.B) cambios PENDIENTES con instrucciones operativas.
> 3. **Sección 12**: plan operativo de cierre — pasos accionables para dejar tesis y código impecables antes de defensa.
>
> Si vas a tomar el trabajo desde acá: leé la sección 12 primero. Es la "checklist de cierre" para próximo dev.

---

## 1. Mapa del repositorio

### Servicios encontrados (`apps/`)
13 directorios; **11 activos** + 2 deprecados-en-disco (preservados con README de deprecation):
| Servicio | Puerto | Stack | Tesis lo cita | Notas |
|---|---|---|---|---|
| `api-gateway` | 8000 | FastAPI | implícito | Único puerto de entrada; auth + ROUTE_MAP |
| `academic-service` | 8002 | FastAPI + SQLA 2.0 | implícito | Comisiones, usuarios, TPs, Templates, bulk-import |
| `evaluation-service` | 8004 | FastAPI | no | Entregas + calificaciones (epic tp-entregas-correccion) |
| `analytics-service` | 8005 | FastAPI | no | κ + progression + alertas + cuartiles + AB profiles |
| `tutor-service` | 8006 | FastAPI + SSE | **sí (C2.2)** | Mediador LLM, prompt socrático, guardrails |
| `ctr-service` | 8007 | FastAPI + producer Redis | **sí (C2.3+C2.4)** | Append-only, hashing, attestation emitter |
| `classifier-service` | 8008 | FastAPI | **sí (C2.5)** | Etiquetador + analizadores CT/CCD/CII |
| `content-service` | 8009 | FastAPI + pgvector | implícito (RAG) | Materiales + retrieval + chunks |
| `governance-service` | 8010 | FastAPI | **sí (C2.7)** | Versionado de prompts + active_configs |
| `ai-gateway` | 8011 | FastAPI | implícito | Proxy LLM + BYOK + budget per-tenant |
| `integrity-attestation-service` | 8012 | FastAPI | **sí (Anexo F + ADR-021)** | Ed25519 + JSONL append-only |
| ~~`identity-service`~~ | ~~8001~~ | — | sí (deprecado) | DEPRECATED por ADR-041 |
| ~~`enrollment-service`~~ | ~~8003~~ | — | no | DEPRECATED por ADR-030 |

### Frontends (`apps/web-*`)
3 SPA React 19 + Vite 6 + TanStack Router:
- `web-admin` (5173): bulk-import, usuarios, casbin, governance UI, auditoria CTR.
- `web-teacher` (5174): dashboards, episodios drill-down N1-N4, alertas, cuartiles.
- `web-student` (5175): editor + chat tutor + tests + sandbox Pyodide.

### Packages (`packages/`)
- `contracts` (Python+TS dual): contratos Pydantic CTR + tipos zod.
- `platform-ops` (Python): privacy, hashing helpers, CII longitudinal, alertas, crypto.
- `observability` (Python): structlog + OTel + health helpers compartidos.
- `test-utils`, `auth-client`, `ctr-client`, `ui` (TS).

### ADRs (`docs/adr/`)
**42 ADRs** (001-042) + 1 sensitivity analysis. Todos los citados explícitamente por la tesis (017-021) **existen**. ADR-018, 019, 020 están **"Propuesto"** (no Aceptado) pese a estar implementados — riesgo formal documentado abajo.

### Coincidencia con afirmación de tesis sobre arquitectura
La tesis (Cap 6.3) declara **7 contenedores C4** (C2.1-C2.7). El código tiene **11 servicios activos + 3 frontends + integrity-attestation-service** (separado en infra institucional según ADR-021). El mapeo no es 1:1 — el código está más fragmentado que la tesis, con servicios transversales (api-gateway, ai-gateway) y plano académico-operacional (academic-service, evaluation-service, analytics-service) que la tesis no menciona explícitamente. **Recomendación**: Sec 6.3 quedó simplificada; o se refleja la fragmentación real en un Anexo E ampliado, o se declara explícitamente que algunos contenedores agrupan múltiples servicios físicos.

---

## 2. Verificación servicio por servicio

### 2.1. tutor-service (C2.2 según tesis)
- **Existe**: `apps/tutor-service/src/tutor_service/` ✓
- **Aplica prompt socrático v1.0.0**: ✓ pero con drift documentado — `apps/tutor-service/src/tutor_service/config.py:37` declara `default_prompt_version: str = "v1.0.1"` mientras los eventos CTR registran `prompt_system_version: "v1.1.0"`. El env override (no leíble por permisos) setea v1.1.0. **El manifest declara v1.1.0 activo, el `system.md` desplegado dice v1.0.0**. Tres versiones declaradas en distintos lados, sin coincidencia.
- **Detecta intentos adversos en preprocesamiento (ADR-019)**: ✓ `apps/tutor-service/src/tutor_service/services/guardrails.py:196` (`def detect`).
- **Code mort detectado**: `tutor_core.py` chequea `prompt_kind == "reflexion"` en CCD pero ese valor no existe en el contrato Pydantic (sólo 5 valores: `solicitud_directa`, `comparativa`, `epistemologica`, `validacion`, `aclaracion_enunciado`). Rama muerta documentada en docstring del módulo.

### 2.2. ctr-service (C2.3 + C2.4)
- **Existe**: `apps/ctr-service/src/ctr_service/` ✓
- **Encadenamiento SHA-256**: ✓ con divergencias críticas detalladas en sec 4.
- **AttestationProducer**: ✓ pero **opcional** — `apps/ctr-service/src/ctr_service/services/partition_worker.py:68` declara `attestation_producer: AttestationProducer | None = None`. Si no se inyecta, no se emite. Causa el gap 29/117 documentado abajo.
- **Sharding Redis Streams** (8 particiones, single-writer por partición): ✓ aunque a nivel bus, NO a nivel Postgres (la tabla `events` es única, no particionada físicamente). La tesis no afirma particionamiento físico — ok.

### 2.3. classifier-service (C2.5)
- **Existe**: `apps/classifier-service/src/classifier_service/` ✓
- **Etiquetador en `services/event_labeler.py`** (ADR-020): ✓ exactamente en la ruta que cita la tesis.
- **Analizadores CT/CCD/CII**: ✓ en `services/{ct,ccd,cii}.py`.
- **CII longitudinal**: ✓ función pura en `packages/platform-ops/src/platform_ops/cii_longitudinal.py`.
- **`LABELER_VERSION = "1.2.0"`** — discrepancia crítica con tesis abajo.

### 2.4. integrity-attestation-service (Anexo F + ADR-021)
- **Existe**: `apps/integrity-attestation-service/` ✓ — estructura completa: `routes/{attestations,health}.py`, `services/{signing,journal}.py`, `workers/attestation_consumer.py`, dev-keys, tests unit + integration.
- **Firma Ed25519 con failsafe**: ✓ `signing.py:120-144` rechaza arrancar en `environment=production` con dev key.
- **Clave institucional UNSL**: ⚠ NO desplegada todavía. `docs/pilot/attestation-pubkey.pem.PLACEHOLDER` sigue en placeholder. Hoy sólo opera la dev key. La D3 ("custodia DI UNSL sin participación del doctorando") **no está cumplida en el deploy actual**, sólo declarada.
- **Journal JSONL append-only rotado diariamente**: ✓ `journal.py:53-74`.
- **CLI `verify-attestations.py`**: ✓ `scripts/verify-attestations.py:1-43` reusa el módulo del servicio (bit-exact garantizado).
- **Buffer canónico bit-exact en ADR-021**: ✓ documentado L123-143; implementación en `signing.py:49-73` matchea.

### 2.5. Frontend (apps/web-student)
- **Editor + chat + panel tests**: ✓ `EpisodePage.tsx`, `CodeEditor.tsx` (Monaco), `ChatPanel.tsx`.
- **`lectura_enunciado` con IntersectionObserver**: ✓ `apps/web-student/src/pages/EpisodePage.tsx:695-704`. Heurística: `intersectionRatio >= 0.25` AND `document.visibilityState === "visible"`. Acumula y flushea con `emitLecturaEnunciado(...)` cada `flushMs`.
- **Pyodide sandbox client-side** (ADR-033): ✓ Pyodide en `web-student`, sin worker Docker.
- **Excepción de patrón help-system**: `EpisodePage.tsx` NO usa `PageContainer` (justificado: layout full-screen).

---

## 3. Verificación de eventos del CTR (Tabla 7.1)

| # | Evento | Tesis | Contrato Pydantic | Emisión real | Estado |
|---|---|---|---|---|---|
| 1 | `episodio_abierto` | Instr. | `EpisodioAbierto` ([events.py:64](packages/contracts/src/platform_contracts/ctr/events.py)) | `tutor_core.py:267` | ✓ |
| 2 | `episodio_cerrado` | Instr. | `EpisodioCerrado` (events.py:75) | `tutor_core.py` close_episode | ✓ |
| 3 | `lectura_enunciado` | Instr. (IO+heur) | `LecturaEnunciado` (events.py:162) | `tutor_core.py:680` | ✓ |
| 4 | `anotacion_creada` | Instr. | `AnotacionCreada` (events.py:175) | `tutor_core.py:633` | ✓ |
| 5 | `edicion_codigo` | Instr. con `origin` | `EdicionCodigo` (events.py:202) — 3 valores declarados | `tutor_core.py:571` | ⚠ `copied_from_tutor` declarado pero NO emitido (UI pendiente, ADR-026 diferido) |
| 6 | `codigo_ejecutado` | Instr. | `CodigoEjecutado` (events.py:224) | `tutor_core.py:533` | ✓ |
| 7 | `prompt_enviado` | Instr. | `PromptEnviado` (events.py:105) | `tutor_core.py:322` | ✓ pero `prompt_kind` único `solicitud_directa` (esperado) |
| 8 | `tutor_respondio` | Instr. | `TutorRespondio` (events.py:122) | `tutor_core.py:432` | ✓ |
| 9 | `intento_adverso_detectado` | Instr. (preproc) | `IntentoAdversoDetectado` (events.py:150) | `tutor_core.py:341-370` | ✓ |
| 10 | `pseudocodigo_escrito` | NO instr. (Eje A) | Ausente | Ausente | ✓ confirma tesis |
| 11 | `debugger_usado` | NO instr. (Eje A) | Ausente | Ausente | ✓ confirma tesis |
| 12 | `codigo_aceptado` | NO instr. (Eje A) | Ausente | Ausente | ✓ confirma tesis |
| 13 | `excepcion` | NO instr. (Eje A) | Ausente | Ausente | ✓ confirma tesis |
| extra | `episodio_abandonado` | Doble trigger | `EpisodioAbandonado` (events.py:85) | `tutor_core.py:477` + `abandonment_worker.py:64` | ✓ doble trigger funciona, idempotente |

### Eventos en código que la Tabla 7.1 NO lista
Estos son extensiones post-tabla, debe declararlas la tesis:
| Evento | Origen | Justificación |
|---|---|---|
| `ReflexionCompletada` | events.py:260, ADR-035 | Reflexión metacognitiva post-cierre, **excluida del classifier** (RN-133) |
| `TestsEjecutados` | events.py:295, ADR-034 | Sandbox client-side Pyodide, conteos sin código |
| `TpEntregada` | events.py:315 | Workflow entrega/calificación (evaluation-service) |
| `TpCalificada` | events.py:328 | Misma trazabilidad académica |

**Recomendación**: actualizar Tabla 7.1 con sección "Extensiones v1.1+" o **declarar explícitamente** que estos cuatro existen pero no son del scope evaluativo del modelo N4. Si no, el comité va a marcar discrepancia entre tesis y código.

---

## 4. Verificación del encadenamiento criptográfico

### Afirmación 1 — Fórmula en dos etapas
**self_hash primero, prev_chain_hash después**:
- `apps/ctr-service/src/ctr_service/services/hashing.py:90` → `combined = f"{self_hash}{prev}".encode()` ✓
- `packages/contracts/src/platform_contracts/ctr/hashing.py:52` → `concatenated = f"{self_hash}{prev}"` ✓ (post-fix 2026-05-04 que invirtió el orden — antes estaba al revés y rompía verificación cross-package)
- ✓ **Confirmado**.

### Afirmación 2 — Canonicalize JSON con `ensure_ascii=False`
**✗ DIVERGENCIA CRÍTICA — silenciosa, no testeada.**

- **Runtime (ctr-service)**: `hashing.py:24-32` → `json.dumps(..., ensure_ascii=False, separators=(",",":"))` sobre dict Python.
- **Helper "auditor oficial" (packages/contracts)**: `hashing.py:28-36` → `event.model_dump_json()` → `json.loads` → `json.dumps(parsed, sort_keys=True, separators=(",",":"))` **SIN `ensure_ascii=False`** → default Python `ensure_ascii=True` → escapa no-ASCII como `\uXXXX`.

**Impacto bit-exact**: si un evento tiene tilde/ñ (cualquier `prompt_enviado` en español, cualquier `anotacion_creada`), el helper que va a usar el comité doctoral para verificar la cadena va a **calcular `self_hash` distinto al que el sistema persistió**. Falsos failures sobre cadenas íntegras.

**Tesis Sec 7.3 dice**: "campos ordenados lexicográficamente, codificación UTF-8, separadores compactos, sin escape de caracteres no-ASCII" — el package contracts NO cumple esa promesa.

**Test cross-package en `packages/contracts/tests/test_chain_hash_canonical_formula.py`** sólo cubre `compute_chain_hash`, NO `compute_self_hash`. Un test adversarial con un evento que contenga "ñ" o tilde en `payload.content` revelaría el bug en segundos.

### Afirmación 3 — Genesis canónico = SHA-256("")
**✗ DIFIERE — el comentario en código miente factualmente.**

- `apps/ctr-service/src/ctr_service/models/base.py:27`:
  ```python
  GENESIS_HASH = "0" * 64  # SHA-256 de cero bytes; alias criptográfico de "cadena vacía"
  ```
- `SHA-256("") = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (lo que dice la tesis).
- `"0" * 64 = "0000...0000"` (lo que está en el código).

Funcionalmente da igual (ambos son constantes arbitrarias de 64 hex chars), pero **el comentario es falso** y la tesis afirma que es el hash de la cadena vacía. Cualquier miembro del comité con conocimiento básico de SHA-256 (`echo -n "" | sha256sum`) lo va a marcar.

**Replicado** en `packages/contracts/.../ctr/hashing.py:19`.

### Afirmación 4 — `prompt_system_hash` y `classifier_config_hash` en cada evento
- ✓ `packages/contracts/.../ctr/events.py:38,40` los declara obligatorios en `CTRBaseEvent` con regex `^[a-f0-9]{64}$`. Heredados por todas las subclases.

---

## 5. Verificación del Clasificador

### CT (Coherencia Temporal)
| # | Afirmación | Estado | Evidencia |
|---|---|---|---|
| CT-1 | Ventanas por pausas >5 min | ✓ | `apps/classifier-service/src/classifier_service/services/ct.py:22` `PAUSE_THRESHOLD = timedelta(minutes=5)` |
| CT-2 | Densidad ev/min + razón prompts/ejecuciones | ⚠ | `prompt_exec_ratio` mide **proporción** `p/(p+e)`, no razón `p/e`. Discrepancia leve de redacción |
| CT-3 | `ct_summary ∈ [0,1]` + features explainability | ✓ | `compute_ct_summary` (L87-117) + `ct_features` (L120-132) |
| CT-4 | Proporción tiempo por nivel N1-N4 | ✓ | `event_labeler.py::time_in_level` (L216-246), endpoint `/api/v1/analytics/episode/{id}/n-level-distribution` |

### CCD (Coherencia Código-Discurso)
| # | Afirmación | Estado | Evidencia |
|---|---|---|---|
| CCD-1 | Ventana 2 min posteriores | ✓ | `ccd.py:50` `CORRELATION_WINDOW = timedelta(minutes=2)`, búsqueda `a_ts < r_ts <= a_ts + WINDOW` (estrictamente posterior) |
| CCD-2 | `prompt_kind = "solicitud_directa"` único | ✓ | `tutor_core.py:330` hardcoded |
| CCD-3 | `ccd_mean` + `ccd_orphan_ratio` | ✓ | `compute_ccd` (L62-155) |
| CCD-4 | Única fuente de verbalización = `anotacion_creada` | ✓ de facto | `ccd.py:88-94` chequea también `prompt_enviado.prompt_kind == "reflexion"` pero ese valor **no existe en el contrato**. Rama muerta |

### CII intra-episodio
| # | Afirmación | Estado | Evidencia |
|---|---|---|---|
| CII-1 | Jaccard tokens consecutivos | ✓ | `cii.py:74-84` `_jaccard_tokens` |
| CII-2 | Slope longitud prompts | ✓ | `cii.py:50-63` regresión lineal sobre `lengths = [len(c.split())]` |
| CII-3 | `cii_stability` + `cii_evolution` (legacy) | ✓ | `cii.py:65-71` |

### CII longitudinal (ADR-018)
| # | Afirmación | Estado | Evidencia |
|---|---|---|---|
| LONG-1 | Slope ordinal por `template_id` | ✓ | `cii_longitudinal.py:64-121` |
| LONG-2 | `MIN_EPISODES_FOR_LONGITUDINAL = 3` | ✓ | L38 |
| LONG-3 | TPs huérfanas excluidas | ✓ | L92-94 `if template_id is None: continue` |
| LONG-4 | Endpoint on-demand | ✓ | `analytics.py:568-660` |
| LONG-5 | Función pura en platform-ops | ✓ | Ubicación correcta |

**Bonus no documentado en tesis**: `compute_evolution_per_unidad` (L124-197) agrupa por `unidad_id` además del `template_id`. Es un **superset** del modelo aspiracional. El docstring lo declara: "habilita trazabilidad longitudinal para pilotos donde `template_id=NULL`". → **gap B (código tiene más que la tesis)**.

### Etiquetador (ADR-020)
- ✓ Ubicación, función pura, `LABELER_VERSION` versionable.
- ✗ **`LABELER_VERSION = "1.2.0"`** (no v1.0.0 como sugiere la tesis).
- ✗ **`anotacion_creada` ya NO es N2 fijo** — discrepancia que afecta la tesis (ver Sec 5).

### Override por `origin` de `edicion_codigo`
- ✓ Conjunto N4 = `{"copied_from_tutor", "pasted_external"}` (`event_labeler.py:111`).
- ✓ Frontend instrumenta sólo `student_typed` y `pasted_external` (`CodeEditor.tsx:55,146-148`).
- ✓ `copied_from_tutor` declarado en contrato pero NO emitido — afordancia UI pendiente (ADR-026 diferido). **Coincide con tesis**.

### ⚠ Discrepancia que afecta la TESIS — `anotacion_creada` ya NO es N2 fijo
La tesis (Sec 4.3.1, 15.6, 17.3, 19.5) afirma N2 fijo como sesgo declarado del piloto y como agenda del Eje B.

**El código corre `LABELER_VERSION = "1.2.0"` con override v1.1.0 ya activo** (ADR-023, Accepted 2026-04-27):
- `event_labeler.py:97` mapea `anotacion_creada → N2` como base, pero `label_event` (L155-164) aplica override condicional cuando `context is not None`:
  - Δ post-`tutor_respondio` ∈ [0, 60s) → **N4** (apropiación).
  - Δ post-`episodio_abierto` ∈ [0, 120s) → **N1** (lectura).
  - Solapes → N4 gana.
- Constantes: `ANOTACION_N1_WINDOW_SECONDS = 120.0`, `ANOTACION_N4_WINDOW_SECONDS = 60.0`.
- El piloto SÍ usa el override — `time_in_level` y `n_level_distribution` (L216-282) construyen contextos vía `_build_event_contexts`.

**Implicación**: **buena noticia para defensa**. La tesis declara como deuda algo que ya está cerrado en código con operacionalización conservadora. El sesgo está mitigado, no abierto. **Hay que actualizar la tesis** para reflejarlo (Sec 4.3.1, 15.6, 17.3, 19.5, agenda Eje B). El reporte empírico debe usar v1.2.0/override v1.1.0, no v1.0.0 puro.

---

## 6. Verificación de detección de intentos adversos

| # | Afirmación | Estado | Evidencia |
|---|---|---|---|
| GR-1 | Detector regex en `services/guardrails.py` | ✓ | `apps/tutor-service/src/tutor_service/services/guardrails.py:196` (`def detect`) |
| GR-2 | 5 categorías exactas | ✓ | `guardrails.py:30-36` (`Literal[...]`) y `events.py:138-144` |
| GR-3 | Severidad 1-5 entera | ✓ | `_SEVERITY` dict + `Field(ge=1, le=5)` |
| GR-4 | Corpus versionado + hash determinista | ✓ | `GUARDRAILS_CORPUS_VERSION = "1.1.0"` + `compute_guardrails_corpus_hash` con `sort_keys=True, ensure_ascii=False, separators=(",",":")`, utf-8 |
| GR-5 | Side-channel, NO bloquea | ✓ | `tutor_core.py:341-370` doble try/except |
| GR-6 | Severidad ≥3 inyecta `_REINFORCEMENT_SYSTEM_MESSAGE` | ✓ | `tutor_core.py:57` umbral, L399-409 inyección como mensaje system independiente, L411 user_message original sin tocar |
| GR-7 | Payload con pattern_id, category, severity, matched_text, guardrails_corpus_hash, timestamp | ⚠ | 5/6 en payload; `timestamp` vive en `event_ts` del `CTRBaseEvent` (campo común), no en payload específico. Defendible arquitectónicamente, pero la tesis afirma que está EN el payload |
| GR-8 | Falla soft | ✓ | doble try/except |

**Nota**: el corpus está en **v1.1.0** (no v1.0.0). El bump preserva auditabilidad — eventos viejos quedan etiquetados con qué corpus los detectó. Coincide con el patrón del versionado.

---

## 7. Verificación del prompt v1.0.0

| # | Afirmación | Estado | Evidencia |
|---|---|---|---|
| P-1 | Ruta `ai-native-prompts/prompts/tutor/v1.0.0/system.md` | ✓ | Existe |
| P-2 | ~280 palabras | ⚠ | `wc -w = 483` total. Cuerpo del prompt (sin HTML comment) ronda ~280 — la afirmación es razonable sólo si se refiere al texto visible al modelo |
| P-3 | Estructura: identidad + 5 principios + lo que NO hace + formato/contexto | ✓ | Headers correctos |
| P-4 | HTML comment al pie con mapping GP/GC | ✓ | Presente |
| P-5 | HTML comment marca asignación obsoleta de GP3 que se corregirá a v1.0.1 | **✗** | El HTML comment dice literalmente que GP3 está cubierto por Principio 3 — **no menciona** que esa asignación esté obsoleta |
| P-6 | Hash SHA-256 calculado | — | **`238cbcbb95810e261afc8baf2ca92196395eea97ebf23d28396fe980e5fadd93`** (calculado sobre el archivo literal) |
| P-7 | Cobertura literal: GP1, GP2, GP4 (3/10) según tesis | **✗** | El HTML comment del archivo declara cobertura de GP1+GP2+GP3+GP4 = **4/10**. Tesis dice 3/10. **Discrepancia directa** |
| P-8 | Español rioplatense neutro, sin emojis | ✓ | "Sos", "Pedile", "Hacés", 0 emojis |

### Drift de versiones del prompt — múltiples fuentes inconsistentes
- `ai-native-prompts/manifest.yaml` → declara `tutor: v1.1.0` activo.
- `apps/tutor-service/src/tutor_service/config.py:37` → `default_prompt_version: str = "v1.0.1"`.
- Eventos CTR en piloto → `prompt_system_version: "v1.1.0"`.
- Archivo desplegado físicamente → `system.md` vigente declara v1.0.0.

**4 versiones distintas declaradas en 4 lugares**. El test `apps/tutor-service/tests/unit/test_config_prompt_version.py` cubre la consistencia manifest↔config, pero el override por env (que setea v1.1.0) lo bypassa.

**Recomendación**: o se redacta v1.0.1 (corrige 4/10 → 3/10) y se promueve a activo en manifest + config, o se actualiza el HTML comment de v1.0.0 con la nota de obsolescencia que la tesis afirma que tiene. Ambas alternativas son trabajo de minutos.

---

## 8. Verificación del Integrity Attestation Service (CRÍTICO)

La tesis Sec 7.3 + 20.5.1 afirma **el Eje D está CERRADO**. Verifiqué punto por punto.

| # | Afirmación | Estado | Evidencia |
|---|---|---|---|
| AT-1 | Servicio existe | ✓ | `apps/integrity-attestation-service/` con estructura completa: `routes/`, `services/`, `workers/`, `dev-keys/`, tests unit + integration |
| AT-2 | Firma Ed25519 funcional | ✓ | `signing.py:120-144` con failsafe (rechaza prod con dev key) |
| AT-3 | Clave institucional UNSL desplegada (D3) | ⚠ **NO** | `docs/pilot/attestation-pubkey.pem.PLACEHOLDER` sigue en placeholder. Sólo opera dev key (seed `AI-NativeV3-DEV-ATTESTATION-KEY1`). El procedimiento de generación sin participación del doctorando está documentado en `docs/pilot/attestation-deploy-checklist.md` pero **no ejecutado** |
| AT-4 | Journal JSONL append-only rotado diariamente | ✓ | `journal.py:53-74` con `O_APPEND`, rotación `attestations-YYYY-MM-DD.jsonl` |
| AT-5 | CLI `scripts/verify-attestations.py` | ✓ | Existe, reusa módulo del servicio (bit-exact garantizado) |
| AT-6 | Buffer canónico bit-exact en ADR-021 | ✓ | `docs/adr/021-external-integrity-attestation.md:123-143` documenta exhaustivamente |
| AT-7 | Stream Redis `attestation.requests` desde ctr-service | ⚠ parcial | Existe en código (`AttestationProducer` + `partition_worker.py:74-76`) pero es **opcional** — si el deploy no instancia el producer, los cierres pasan sin emitir |
| AT-8 | Smoke real (¿se está disparando?) | ⚠ | XLEN `attestation.requests = 29`. Episodios cerrados en DB = 117. **Sólo 25%** de los cierres dispararon attestation. Gap operacional: 88 episodios cerrados nunca generaron XADD. La diferencia es entre cierres por seeds (no instancian producer) y cierres por API real (sí lo instancian). El consumer institucional (puerto 8012) no está corriendo en local — vive en VPS UNSL en piloto real, así que los 29 mensajes están acumulados sin atestar |

### Conclusión sobre Eje D
**La tesis afirma "cerrado" pero la realidad es "cerrado a nivel diseño + dev, NO cerrado en deploy de pilotaje"**. Concretamente:

1. ✓ Toda la infra técnica existe y es correcta (firma, journal, CLI, buffer).
2. ✗ Clave institucional UNSL NO desplegada (Paso 2 del checklist no ejecutado).
3. ⚠ Producer es opcional → 75% de cierres pasan sin emitir.
4. ⚠ Service consumidor (8012) no está running en local; los XADDs se acumulan pendientes.

**Para defensa**: o se actualiza la afirmación de Sec 20.5.1 a "Eje D cerrado en diseño + dev key; deploy con clave institucional pendiente" (mover a agenda confirmatoria con criterio operacional cuantificable: 100% de `episodio_cerrado` con XADD correspondiente + clave institucional desplegada), **o se completa el deploy ANTES de defensa**. La afirmación actual es vulnerable a auditoría.

---

## 9. ADRs

42 ADRs encontrados en `docs/adr/` (001-042) + 1 anexo (`023-sensitivity-analysis.md`).

### ADRs que la tesis cita explícitamente
| ADR | Estado declarado | Cita en tesis | Coincidencia |
|---|---|---|---|
| **017** CCD embeddings semánticos | Propuesto (DIFERIDO) | Eje B agenda | ✓ tesis y ADR coinciden |
| **018** CII evolution longitudinal | **Propuesto** | Sec 15.6 + Eje B parcialmente cerrado | ⚠ ADR debería ser Aceptado — implementación está mergeada, función pura tiene tests, endpoint operacional |
| **019** Guardrails Fase A | **Propuesto** | Sec 8.5.1 + Eje C cerrada Fase A | ⚠ misma observación |
| **020** Etiquetador N1-N4 | **Propuesto** | C3.2 (Cap 6.4) | ⚠ misma observación |
| **021** Attestation externa | Aceptado (decisión) | Sec 7.3 + Anexo F + Eje D | ✓ |

**Riesgo formal**: la tesis cita ADR-018, 019, 020 como decisiones tomadas pero el frontmatter de los archivos dice "Propuesto". Si el comité abre los ADRs, va a leer "Status: Proposed" mientras la tesis los presenta como cerrados. **Recomendación**: promover a "Accepted" con fecha. Trabajo de 5 minutos.

### Lista completa de ADRs
| ADR | Título | Estado |
|---|---|---|
| 001 | Multi-tenancy RLS | Aceptado |
| 002 | Keycloak IAM federado | Aceptado |
| 003 | Separación bases lógicas | Aceptado |
| 004 | AI Gateway propio | Aceptado |
| 005 | Redis Streams bus | Aceptado |
| 006 | FastAPI + SQLAlchemy 2.0 | Aceptado |
| 007 | React + TanStack | Aceptado |
| 008 | Casbin autorización | Aceptado |
| 009 | Git fuente prompt | Aceptado |
| 010 | Append-only clasificaciones | Aceptado |
| 011 | pgvector RAG | Aceptado |
| 012 | Monorepo pnpm + uv | Aceptado |
| 013 | OpenTelemetry | Aceptado |
| 014 | Docker + K8s | Aceptado |
| 015 | Blue-green + rolling | Aceptado |
| 016 | TP template + instancia | Aceptado |
| **017** | **CCD embeddings semánticos** | **Propuesto (DIFERIDO Eje B)** |
| **018** | **CII evolution longitudinal** | **Propuesto** ⚠ |
| **019** | **Guardarraíles Fase A** | **Propuesto** ⚠ |
| **020** | **Etiquetador N1-N4** | **Propuesto** ⚠ |
| **021** | **Attestation externa Ed25519** | **Aceptado** |
| 022 | TanStack Router migration | Propuesto |
| 023 | Override anotacion_creada | Aceptado (2026-04-27) |
| 024 | prompt_kind reflexivo runtime | DIFERIDO Eje B |
| 025 | episodio_abandonado doble trigger | Aceptado |
| 026 | Botón Insertar código tutor | DIFERIDO post-defensa |
| 027 | G3 Fase B postprocesamiento | DIFERIDO Eje C |
| 028 | Desacoplamiento instrumento-intervención | DIFERIDO post-piloto-1 |
| 029 | Bulk-import inscripciones | Aceptado |
| 030 | Deprecate enrollment-service | Aceptado |
| 031 | Audit aliases CTR | Aceptado |
| 032 | G7 ML alertas predictivas | DIFERIDO piloto-2 |
| 033 | Sandbox Pyodide-only | Aceptado |
| 034 | test_cases JSONB | Aceptado |
| 035 | Reflexión privacy | Aceptado |
| 036 | TP-gen caller academic | Aceptado |
| 037 | Governance UI read-only | Aceptado |
| 038 | BYOK AES-GCM master key | Aceptado |
| 039 | BYOK resolver jerárquico | Aceptado |
| 040 | materia_id propagation | Aceptado |
| 041 | Deprecación identity-service | Aceptado |
| 042 | TareaPracticaTemplate piloto-1 | Aceptado |

---

## 10. Inventario de gaps tesis ↔ código

### A. La tesis afirma X pero el código NO lo tiene (o difiere)

#### A.1 — `GENESIS_HASH ≠ SHA-256("")` ⚠ CRÍTICO documental
**Tesis Sec 7.3**: "El primer evento de un episodio usa como `chain_hash_0` un valor genesis canónico (el hash de la cadena vacía)."
**Código** (`apps/ctr-service/src/ctr_service/models/base.py:27`): `GENESIS_HASH = "0" * 64` con comentario factualmente falso ("SHA-256 de cero bytes").
**SHA-256("")** real = `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
**Riesgo**: cualquier miembro del comité con conocimiento mínimo de SHA-256 lo va a marcar.
**Decisión**: actualizar tesis (decir que es constante arbitraria de 64 hex chars) o actualizar código + comentario para que efectivamente use SHA-256(""). Preferir lo primero — cambiar el código rompe TODA la cadena histórica del piloto.

#### A.2 — `ensure_ascii=False` no se cumple en helper "auditor oficial" ⚠ CRÍTICO técnico
**Tesis Sec 7.3**: "campos ordenados lexicográficamente, codificación UTF-8, separadores compactos, **sin escape de caracteres no-ASCII**."
**Código `packages/contracts/.../ctr/hashing.py:28-36`**: NO usa `ensure_ascii=False` → escapa no-ASCII como `\uXXXX`.
**Impacto**: si auditor doctoral usa el helper "oficial" para verificar cadenas con tildes/ñ, ve falsos failures.
**Decisión**: arreglar `packages/contracts/.../ctr/hashing.py` agregando `ensure_ascii=False` + agregar test `compute_self_hash` con evento que tenga "ñ"/tilde.

#### A.3 — Eje D no está cerrado en deploy ⚠ CRÍTICO operacional
**Tesis Sec 20.5.1**: "Eje D. Auditabilidad externa efectiva. Estado en v1.0.0: cerrado mediante el integrity-attestation-service con firma Ed25519, journal JSONL append-only rotado diariamente, custodia de clave por la dirección de informática de UNSL".
**Código + ops**: clave institucional NO desplegada (placeholder), producer opcional (25% emisión real), consumer no running.
**Decisión**: mover Eje D de "cerrado" a "agenda confirmatoria con criterio cuantificable" (100% de cierres con XADD + pubkey institucional desplegada), o ejecutar checklist operativo antes de defensa.

#### A.4 — HTML comment del prompt v1.0.0 NO marca obsolescencia de GP3 ⚠ ALTO
**Tesis Sec 8.4.1 (nota)**: "el HTML comment del archivo del prompt v1.0.0 vigente registra una asignación obsoleta de GP3 al Principio 3; la corrección documental sin cambio sustantivo se proyecta como bump v1.0.1".
**Código (`ai-native-prompts/prompts/tutor/v1.0.0/system.md`)**: HTML comment dice cobertura de GP1+GP2+**GP3**+GP4 = 4/10, sin nota de obsolescencia.
**Decisión**: o redactar v1.0.1 con 3/10 corregido + activarlo en manifest + config, o agregar nota explícita de obsolescencia al HTML comment de v1.0.0. Trabajo de 5-15 min.

#### A.5 — Drift de versión del prompt entre 4 fuentes ⚠ ALTO
- Manifest: v1.1.0 activo.
- Config: v1.0.1.
- Eventos CTR: v1.1.0 (por env override).
- Archivo `system.md`: v1.0.0 declarada en cabecera.
**Decisión**: alinear las 4 fuentes a una sola declaración. Si v1.1.0 está activo en piloto, el archivo `v1.1.0/system.md` debería existir y ser el fuente — el `v1.0.0/system.md` queda como histórico.

#### A.6 — `prompt_kind == "reflexion"` rama muerta ⚠ MEDIO
**Tesis Sec 15.6**: "la activación efectiva de la clasificación de intencionalidad del prompt … constituye parte del Eje B de la agenda confirmatoria."
**Código `ccd.py:81,92`**: chequea `prompt_kind == "reflexion"` pero ese valor no existe en el contrato Pydantic (`PromptEnviadoPayload` admite 5 valores, ninguno es "reflexion"). Rama imposible de activar con datos reales.
**Decisión**: ya documentado en docstring del módulo como deuda Eje B/G9. Aceptable para defensa siempre que se mencione explícitamente.

### B. El código tiene Y pero la tesis NO lo documenta

#### B.1 — `LABELER_VERSION = "1.2.0"` con override v1.1.0 activo ⚠ ALTO
**Código `event_labeler.py:76`**: `LABELER_VERSION = "1.2.0"` (incluye override temporal de `anotacion_creada` por ventana 120s/60s + regla N3/N4 para `tests_ejecutados`).
**Tesis Sec 4.3.1, 15.6, 17.3, 19.5**: declara `anotacion_creada → N2 fijo` como sesgo del piloto inicial, parte del Eje B no resuelto.
**Esto es buena noticia para defensa**: la tesis declara como deuda algo que ya está cerrado en código con operacionalización conservadora. Hay que actualizar tesis para reflejarlo (ADR-023 ya tiene análisis de sensibilidad).

#### B.2 — `compute_evolution_per_unidad` (CII por unidad) ⚠ MEDIO
**Código `cii_longitudinal.py:124-197`**: agrupa por `unidad_id` además del `template_id`. Habilita trazabilidad longitudinal cuando `template_id=NULL`.
**Tesis ADR-018 / Sec 15.6**: sólo describe `compute_evolution_per_template`. La extensión por unidad no está en el manuscrito.
**Decisión**: incorporar como mejora del Eje B parcialmente cerrado en el manuscrito, o redactar ADR-equivalente referenciado en tesis.

#### B.3 — Eventos extra en código no listados en Tabla 7.1 ⚠ ALTO
4 eventos implementados pero **no listados en la Tabla 7.1**:
- `ReflexionCompletada` (ADR-035) — reflexión metacognitiva post-cierre.
- `TestsEjecutados` (ADR-034) — sandbox client-side.
- `TpEntregada` y `TpCalificada` (evaluation-service) — workflow académico.
**Decisión**: o agregar sección "Extensiones de la ontología post-Tabla 7.1" al manuscrito explicando cada una con su scope (especial atención a `ReflexionCompletada` que está **excluida** del classifier por privacy — RN-133), o referenciar como deuda futura.

#### B.4 — `unidades-trazabilidad` (entidad `Unidad` por comisión)
**Código `apps/web-teacher/src/routes/`**: hay rutas y componentes para CRUD de `Unidad` + analítica longitudinal por unidad.
**Tesis**: no menciona el constructo `Unidad`. Es un decorador docente añadido para destrabar trazabilidad cuando los TPs no están templated (ADR-018 case AD-4).
**Decisión**: incorporar al manuscrito como elemento operacional del piloto que completa la cobertura del Eje B parcial.

#### B.5 — BYOK multi-provider (epic ai-native-completion)
**Código** (ADRs 038-040): infraestructura completa de BYOK con AES-256-GCM, resolver jerárquico materia → tenant → env_fallback, integración Mistral SDK.
**Tesis**: no menciona BYOK. La tesis dice "agnóstico al proveedor LLM" — el código va más allá: permite que cada materia use su propia API key.
**Decisión**: BYOK es una decisión de gobernanza institucional con implicaciones éticas (¿quién paga el costo del LLM?). Vale incorporarlo a Cap 16.3 (gobernanza) o a un anexo dedicado, especialmente pensando en escala multisite.

#### B.6 — Fragmentación arquitectónica (10 servicios activos vs 7 contenedores C4)
**Tesis Sec 6.3**: 7 contenedores C2.1-C2.7.
**Código**: 11 servicios activos (api-gateway, ai-gateway, academic-service, evaluation-service, analytics-service como adicionales).
**Decisión**: o se incorpora la fragmentación real al manuscrito, o se agrupa explícitamente: api-gateway+ai-gateway como "infraestructura transversal", academic+evaluation+analytics como "plano académico-operacional".

---

## 11. Recomendaciones priorizadas — Estado al 2026-05-08

> Esta sección se reorganizó en dos sub-secciones: lo YA aplicado en esta sesión (11.A) y lo que QUEDA pendiente (11.B). Cada item incluye instrucciones operativas para el próximo dev.

### 11.A. CAMBIOS APLICADOS EN ESTA SESIÓN (2026-05-08)

#### ✓ A1 — Comentario falso de `GENESIS_HASH` corregido en 2 archivos
**Antes**: `GENESIS_HASH = "0" * 64  # SHA-256 de cero bytes; alias criptográfico de "cadena vacía"`.
**Después**: comentario que aclara que es **constante arbitraria** de 64 hex chars, NO `SHA-256("")` (cuyo valor real `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` se incluye en la nota).
**Archivos**:
- `apps/ctr-service/src/ctr_service/models/base.py:27-33`
- `packages/contracts/src/platform_contracts/ctr/hashing.py:1-13`

**Tests verificados**: `test_hashing.py::test_genesis_hash_format` — sigue verde porque solo cambió el comentario, no el valor.

**Implicación para tesis**: Sec 7.3 puede mantener "valor genesis canónico" pero **debe omitir** la frase "el hash de la cadena vacía". Sustituir por: *"un valor genesis canónico (constante de 64 ceros hexadecimales)"*.

#### ✓ A2 — `ensure_ascii=False` agregado al helper auditor + test cross-package adversarial
**Antes**: `packages/contracts/.../hashing.py::compute_self_hash` reparseaba con `json.dumps(..., sort_keys=True, separators=...)` — sin `ensure_ascii=False`. Default Python = `ensure_ascii=True` → escape `\uXXXX` de caracteres no-ASCII. **El runtime del ctr-service SÍ usa `ensure_ascii=False`**. Divergencia silenciosa: cualquier evento con tilde o "ñ" producía hashes distintos en runtime vs auditor.
**Después**: helper alineado bit-a-bit con runtime.
**Archivos**:
- `packages/contracts/src/platform_contracts/ctr/hashing.py:34-50` (nuevo flag + docstring que cita Sec 7.3)
- `packages/contracts/tests/test_self_hash_non_ascii_parity.py` (3 tests nuevos)

**Tests adversariales agregados** (todos verdes — 3/3):
1. `test_self_hash_evento_con_tildes_es_bit_exact_con_runtime` — evento con `"El año pasado vi qué difícil es entender..."` → package y runtime producen idéntico hash.
2. `test_self_hash_evento_con_enie_en_prompt` — `prompt_enviado` con `"¿Cómo enseño punteros..."` → bit-exact match.
3. `test_self_hash_no_escapa_caracteres_no_ascii` — antiregresión que verifica que el JSON canonicalizado contiene "ñ" literal, no `ñ`.

**Implicación para tesis**: la Sec 7.3 ya está cumplida bit-a-bit. **No hace falta editar la tesis** — el código quedó alineado con la afirmación.

#### ✓ A3 — ADR-018, ADR-019, ADR-020 promovidos a `Accepted`
**Antes**: frontmatter decía `Estado: Propuesto` pese a estar implementados, mergeados y operando en piloto.
**Después**: `Estado: Accepted` con anotación `(2026-05-08, promovido a Accepted tras verificación bidireccional tesis-código)`.
**Archivos**:
- `docs/adr/018-cii-evolution-longitudinal.md:3-4`
- `docs/adr/019-guardrails-fase-a.md:3-4`
- `docs/adr/020-event-labeler-n-level.md:3-4`

**Implicación para tesis**: ninguna — la tesis ya los citaba como decisiones tomadas. **Riesgo formal cerrado**: si el comité abre los ADRs, ahora va a leer "Accepted".

---

### 11.B. CAMBIOS PENDIENTES (requieren decisión / coordinación / redacción de tesis)

#### CRÍTICO

##### ⚠ B1 — Decidir narrativa del Eje D (auditabilidad externa)
**Estado real**: clave institucional UNSL **NO desplegada** (placeholder vigente en `docs/pilot/attestation-pubkey.pem.PLACEHOLDER`); `AttestationProducer` opcional → solo 25% de los cierres dispararon attestation (29 XADDs vs 117 episodios cerrados); consumer no running en local.
**Tesis afirma**: "Eje D cerrado" en Sec 20.5.1.
**Discrepancia**: la tesis se adelanta al estado real del deploy.
**Dos opciones**:
- **Opción A — Atemperar tesis** (30 min de redacción):
  - Editar Sec 7.3, 20.5.1 Eje D para decir: *"diseño y dev key cerrados; deploy con clave institucional UNSL pendiente como condición operacional, criterio cuantificable: 100% de `episodio_cerrado` con XADD correspondiente y pubkey institucional desplegada antes del cierre del piloto"*.
  - Beneficio: defensa segura sin dependencia externa.
- **Opción B — Cerrar deploy real** (1-2 días con DI UNSL):
  - Ejecutar `docs/pilot/attestation-deploy-checklist.md` (10 pasos).
  - Generar y desplegar pubkey institucional. Renombrar `attestation-pubkey.pem.PLACEHOLDER` → `attestation-pubkey.pem`. Commit.
  - Hacer obligatoria la inyección de `AttestationProducer` en producción (ver B6).
  - Validar 100% emission rate con un script `scripts/audit-attestation-coverage.py`.
- **Recomendación**: empezar por Opción A para defensa, ejecutar Opción B en paralelo si DI UNSL responde a tiempo.

##### ⚠ B2 — Drift de versiones del prompt (4 fuentes inconsistentes)
**Fuentes hoy**:
- `ai-native-prompts/manifest.yaml` → `tutor: v1.1.0` activo.
- `apps/tutor-service/src/tutor_service/config.py:37` → `default_prompt_version: str = "v1.0.1"`.
- Eventos CTR del piloto → `prompt_system_version: "v1.1.0"` (por env override).
- Archivo desplegado físicamente → `system.md` v1.0.0 (con HTML comment 4/10 GP3 mal asignado).

**Fix completo (1 hora)**:
1. Crear `ai-native-prompts/prompts/tutor/v1.0.1/system.md` con el HTML comment corregido a 3/10 (sin GP3 explícito).
2. **Importante**: si el cuerpo del prompt cambia, el SHA-256 cambia, lo cual rompería verificación de eventos pasados que registran el hash de v1.0.0. Por eso conviene crear `v1.0.1` como NUEVO archivo en lugar de editar v1.0.0.
3. Actualizar `manifest.yaml` para que `tutor` apunte a la versión que efectivamente está activa en producción.
4. Alinear `config.py:37` con el manifest.
5. Documentar la migración en `docs/SESSION-LOG.md`.

**NO se aplicó en esta sesión** porque modificar el archivo del prompt v1.0.0 cambia su hash y rompería la verificación de los 470+ eventos del CTR vigente. La acción correcta es crear v1.0.1 como nuevo archivo, lo cual requiere coordinación que excede un fix puntual.

#### ALTO

##### ⚠ B3 — Actualizar tesis: `anotacion_creada` ya NO es N2 fijo
**Código real**: `LABELER_VERSION = "1.2.0"` con override v1.1.0 activo (ADR-023). Heurística temporal 120s/60s.
**Tesis afirma** (Sec 4.3.1, 15.6, 17.3, 19.5): N2 fijo como sesgo declarado del piloto, parte de Eje B no resuelto.
**Acción** (30-60 min de redacción):
- Editar Sec 4.3.1: "anotacion_creada se etiqueta con override temporal según ventana al `tutor_respondio` previo (60s → N4) o al `episodio_abierto` (120s → N1), fallback N2. Operacionalización conservadora declarada en ADR-023".
- Editar Sec 15.6: agregar al final "El sesgo de N2 fijo declarado en versiones anteriores está cerrado en LABELER_VERSION=1.2.0 con override v1.1.0".
- Editar Sec 17.3: el reporte empírico debe usar v1.2.0/override v1.1.0, no v1.0.0 puro. Citar el análisis de sensibilidad de `docs/adr/023-sensitivity-analysis.md`.
- Editar Sec 19.5: mover este sesgo de la lista de limitaciones abiertas a "limitaciones cerradas con operacionalización conservadora".
- Editar Sec 20.5.1 Eje B: "G8a cerrado vía override temporal en LABELER v1.1.0 (ADR-023)".

##### ⚠ B4 — Drift del HTML comment del prompt v1.0.0 (GP3 cobertura 4/10 vs 3/10)
**Tesis Sec 8.4.1**: el HTML comment "registra una asignación obsoleta de GP3 al Principio 3, corrección como v1.0.1".
**Código**: el HTML comment dice "GP1+GP2+GP3+GP4 = 4/10 cubiertos" sin mención de obsolescencia.
**Fix**: ver B2 (crear v1.0.1 con corrección). Atado.

##### ⚠ B5 — Incorporar 4 eventos extra a la ontología (Tabla 7.1)
Eventos en código no listados en la tabla:
- `ReflexionCompletada` (ADR-035) — reflexión metacognitiva post-cierre. **Excluido del classifier por RN-133** (privacy).
- `TestsEjecutados` (ADR-034) — sandbox client-side Pyodide.
- `TpEntregada` y `TpCalificada` — workflow académico (evaluation-service).
**Acción** (30 min): agregar al final de Sec 7.2 una tabla "Extensiones post-Tabla 7.1" con cada uno + scope + privacy considerations + ADR de referencia.

##### ⚠ B6 — Hacer `AttestationProducer` obligatorio en arranque prod
**Riesgo actual**: `attestation_producer: AttestationProducer | None = None` en `partition_worker.py`. Si el deploy lo olvida inyectar, el sistema se silencia. Causa el gap 25% de cobertura.
**Fix sugerido** (45 min):
1. Cambiar default de `None` a parámetro obligatorio.
2. En el bootstrap del ctr-service, validar que esté instanciado si `environment == "production"`. Sino, abortar arranque.
3. Tests de integración: verificar que **toda** persistencia de `episodio_cerrado` produce un XADD.
4. Métrica OTLP: `ctr_attestation_emission_total{result="emitted|skipped|error"}` para observar cobertura en producción.

##### ⚠ B7 — Documentar fragmentación arquitectónica vs C4 ideal
**Tesis Sec 6.3**: 7 contenedores C4.
**Código**: 11 servicios + 3 frontends + integrity-attestation.
**Acción** (1 hora): actualizar Sec 6.3 con los 11 servicios agrupándolos bajo los 7 contenedores conceptuales. Mencionar planos: académico-operacional (academic, evaluation, analytics), pedagógico-evaluativo (tutor, ctr, classifier, content, governance), transversales (api-gateway, ai-gateway), externo (integrity-attestation).

#### MEDIO

##### ⚠ B8 — Documentar `Unidad` y `compute_evolution_per_unidad`
**Código**: `apps/web-teacher/` tiene CRUD de `Unidad` por comisión, y `cii_longitudinal.py:124-197` calcula CII longitudinal por `unidad_id`. Es **superset** del modelo aspiracional de la tesis.
**Acción** (30-60 min): agregar a Sec 15.4 / 15.6 el constructo `Unidad` como decorador docente que destraba la trazabilidad longitudinal cuando `template_id=NULL`. Actualizar ADR-018 con la extensión.

##### ⚠ B9 — Documentar BYOK en gobernanza
**Código** (ADRs 038-040): infraestructura completa de BYOK con AES-256-GCM, resolver jerárquico materia → tenant → env_fallback, integración Mistral.
**Tesis**: no menciona BYOK. La tesis dice "agnóstico al proveedor LLM" — el código va más allá.
**Acción** (1 hora): agregar a Cap 16.3 (Métricas de gobernanza) o como Anexo dedicado las implicaciones de BYOK (cada materia con su key) para escala multisite y costos.

##### ⚠ B10 — `prompt_kind == "reflexion"` rama dormida en CCD
**Estado**: **NO se borró** en esta sesión. La rama está cubierta por `test_ccd.py:75-83` (`test_prompt_reflexion_cuenta_como_verbalizacion`) que valida el comportamiento futuro cuando el contract admita "reflexion" (Eje B / ADR-024).
**Decisión defensible**: dejarla dormida con docstring que ya está en `ccd.py:18-42`. Es código condicional al cambio del contract, no código abandonado.
**Si en el futuro se decide activar el Eje B**: hay que (1) agregar "reflexion" al `Literal` de `PromptEnviadoPayload.prompt_kind`, (2) modificar el tutor-service para emitir `prompt_kind="reflexion"` en prompts reflexivos detectados por heurística o LLM, (3) actualizar `test_ccd_documenta_gap_reflexion.py` con la nueva realidad.

##### ⚠ B11 — Aclarar `prompt_exec_ratio` (semántica proporción vs razón)
**Código**: mide `p/(p+e)` (proporción ∈ [0,1]).
**Tesis Sec 15.6**: dice "razón prompts/ejecuciones".
**Acción** (5 min): editar Sec 15.6: *"proporción de prompts respecto del total de eventos prompts+ejecuciones, normalizada a [0,1]"*.

#### BAJO

##### ⚠ B12 — Conteo de palabras del prompt (~280)
**Realidad**: archivo total = 483 palabras; cuerpo visible al modelo ≈ 280; HTML comment ≈ 200.
**Acción** (2 min): editar Anexo A.2 para aclarar "**~280 palabras del cuerpo visible al modelo** (el HTML comment al pie es metadata de auditoría humana, no se envía al LLM)".

##### ⚠ B13 — Insertar hash SHA-256 del prompt en Anexo A.4
**Reemplazar** `[A COMPLETAR: valor del hash SHA-256]` por:
- Si se mantiene v1.0.0 vigente: `238cbcbb95810e261afc8baf2ca92196395eea97ebf23d28396fe980e5fadd93`
- Si se promueve v1.0.1 (ver B2): recalcular después de crear el archivo.

---

---

## 12. Plan operativo de cierre — checklist para próximo dev

> Esta sección es **accionable**. Cualquier persona con acceso al repo + tesis puede usar este orden para cerrar el trabajo. Tiempos asumidos: 1 dev senior trabajando enfocado, sin interrupciones.

### Fase 1 — Cambios al código (3-4 horas)

**Pre-requisito**: rama nueva tipo `chore/cierre-tesis-2026-05-08` desde `main`.

| Paso | Acción | Esfuerzo | Verificación |
|---|---|---|---|
| 1.1 | Crear `ai-native-prompts/prompts/tutor/v1.0.1/system.md` con cuerpo idéntico al v1.0.0 + HTML comment corregido (3/10 sin GP3 explícito + nota de obsolescencia) | 20 min | Calcular nuevo SHA-256 con `sha256sum` |
| 1.2 | Actualizar `ai-native-prompts/manifest.yaml` para apuntar `tutor: v1.0.1` (o la versión efectivamente activa) | 5 min | Test `test_config_prompt_version.py` debe seguir pasando |
| 1.3 | Alinear `apps/tutor-service/src/tutor_service/config.py:37` con el manifest | 5 min | Mismo test |
| 1.4 | Hacer obligatoria la inyección de `AttestationProducer` en producción (ver B6) | 45 min | Test integración: `test_episodio_cerrado_emite_xadd_attestation.py` |
| 1.5 | Agregar métrica `ctr_attestation_emission_total{result}` para observar cobertura | 15 min | Smoke contra Prometheus |
| 1.6 | Crear `scripts/audit-attestation-coverage.py` que reporte cobertura `XLEN attestation.requests / count(episodios cerrados)` | 30 min | Output JSON con ratio |
| 1.7 | Correr suite completa: `make test` | 5 min | 0 failures |
| 1.8 | Commit: `chore(prompt): bump v1.0.0 → v1.0.1 cierre tesis (3/10 GP)` y `feat(ctr): attestation producer obligatorio en prod` | 10 min | — |

**Total Fase 1**: ~2.5 horas + buffer.

### Fase 2 — Cambios a la tesis (4-6 horas de redacción)

> Editar el `.docx` directamente. Los cambios son los items B3, B5, B7, B8, B9, B11, B12, B13.

| Paso | Sección de tesis | Cambio concreto | Esfuerzo |
|---|---|---|---|
| 2.1 | **Sec 4.3.1** | Reescribir párrafo de `anotacion_creada` para reflejar override v1.1.0 (heurística temporal 120s/60s). Citar ADR-023 | 20 min |
| 2.2 | **Sec 6.3** | Mapear los 11 servicios reales bajo los 7 contenedores C4. Mencionar planos: académico-operacional, pedagógico-evaluativo, transversales, externo | 1 hora |
| 2.3 | **Sec 7.2** | Agregar tabla "Extensiones post-Tabla 7.1" con `ReflexionCompletada` (privacy gate RN-133), `TestsEjecutados`, `TpEntregada`, `TpCalificada` | 30 min |
| 2.4 | **Sec 7.3** | Eliminar la frase "el hash de la cadena vacía". Sustituir por "una constante canónica de 64 ceros hexadecimales". (El cambio en código de A1 está alineado — la tesis solo necesita corregir la afirmación) | 5 min |
| 2.5 | **Sec 8.4.1** | Si se activó v1.0.1: actualizar para decir "cobertura literal v1.0.1: GP1, GP2, GP4 = 3/10". Eliminar la frase "asignación obsoleta de GP3" porque ya no hay obsoleta | 15 min |
| 2.6 | **Sec 15.4 / 15.6** | Agregar mención de `Unidad` como complemento de `template_id` para destrabar trazabilidad longitudinal cuando templates falten | 30 min |
| 2.7 | **Sec 15.6** | Aclarar `prompt_exec_ratio` como proporción no razón. Agregar al final párrafo sobre cierre del sesgo de N2 fijo en `LABELER_VERSION=1.2.0` | 20 min |
| 2.8 | **Sec 16.3** | Agregar bullet sobre BYOK como dimensión de gobernanza (resolver jerárquico, AES-256-GCM, audit trail) | 30 min |
| 2.9 | **Sec 17.3** | Reportar usando v1.2.0/override v1.1.0, no v1.0.0 puro. Citar `docs/adr/023-sensitivity-analysis.md` | 30 min |
| 2.10 | **Sec 19.5** | Mover `anotacion_creada → N2 fijo` de "limitación abierta" a "limitación cerrada con operacionalización conservadora" | 15 min |
| 2.11 | **Sec 20.5.1 Eje B** | Marcar G8a (override `anotacion_creada`) como cerrado. Mantener G9 (clasificación semántica de `prompt_kind`), G14 (CCD embeddings) como abiertos | 15 min |
| 2.12 | **Sec 20.5.1 Eje D** | Decidir narrativa según resultado de B1: <br>• Si se ejecutó deploy: mantener "cerrado" + agregar nota sobre cobertura 100% verificada. <br>• Si NO: bajar a "diseño y dev key cerrados; deploy con clave institucional como condición operacional pendiente, criterio cuantificable: 100% emission rate" | 30 min |
| 2.13 | **Anexo A.2** | Aclarar que ~280 palabras se refiere al cuerpo visible al modelo, no al archivo total | 5 min |
| 2.14 | **Anexo A.4** | Reemplazar `[A COMPLETAR]` por el SHA-256 del archivo vigente (calculado en Paso 1.1 si se hizo v1.0.1, o `238cbcbb95810e261afc8baf2ca92196395eea97ebf23d28396fe980e5fadd93` si se mantiene v1.0.0) | 5 min |

**Total Fase 2**: ~5.5 horas.

### Fase 3 — Cierre del Eje D (opcional, 1-2 días con DI UNSL)

Si se eligió Opción B del item B1:

1. Coordinar con DI UNSL para ejecutar `docs/pilot/attestation-deploy-checklist.md` (10 pasos).
2. Generar par de claves Ed25519 institucional sin participación del doctorando (Paso 2 del checklist — D3 del ADR-021).
3. Renombrar `docs/pilot/attestation-pubkey.pem.PLACEHOLDER` → `docs/pilot/attestation-pubkey.pem` con la pubkey real.
4. Configurar nginx con IP allowlist + systemd unit con `replicas: 1`.
5. Smoke test end-to-end: cerrar un episodio dummy → verificar que el JSONL append-only registra la attestation con firma válida.
6. Correr `scripts/audit-attestation-coverage.py` y validar 100% rate.
7. Commit + tag `v1.0.0-pilot-ready`.

### Fase 4 — Validación final (30 min)

Antes de declarar "tesis impecable":

1. Re-ejecutar este informe (mismos 4 sub-agentes paralelos) para validar que las afirmaciones de la tesis ahora coinciden con el código.
2. Generar `docs/SESSION-LOG.md` entry con resumen del cierre.
3. Generar el DOCX del protocolo UNSL con `make generate-protocol` (toma los nuevos hashes y configs).
4. Imprimir un PDF de la tesis actualizada y verificar visualmente.

---

## Resumen ejecutivo (actualizado 2026-05-08)

### Lo que se hizo en esta sesión

**3 fixes de código aplicados + 1 test cross-package adversarial nuevo**:
1. ✓ Comentario falso de `GENESIS_HASH` corregido en `ctr-service` y `packages/contracts`.
2. ✓ `ensure_ascii=False` agregado al helper auditor → bit-exact match runtime/auditor para eventos con tildes/ñ.
3. ✓ ADR-018, ADR-019, ADR-020 promovidos a `Accepted`.
4. ✓ Suite completa de tests: **152 passed** (incluyendo 3 nuevos del adversarial parity).

### Estado al cierre de esta sesión

**Riesgo formal cerrado** ✓ — los ADRs ya no dicen "Proposed" mientras la tesis los presenta como decisiones tomadas.

**Riesgo técnico de auditoría cerrado** ✓ — el comentario de GENESIS_HASH ya no miente, y el helper auditor del package es bit-exact con el runtime para todos los caracteres del piloto (incluyendo el español).

**Pendientes de cierre** (organizados en Fase 1-4 de la Sec 12):
- 1 cambio operacional grande: deploy de attestation institucional (Eje D) — coordinación con DI UNSL.
- 1 cambio de código de tamaño medio: `AttestationProducer` obligatorio en prod.
- 1 cambio de versionado del prompt: crear v1.0.1 con HTML comment corregido + alinear las 4 fuentes (manifest, config, env, archivo).
- ~10 cambios de redacción de tesis: documentar lo que el código tiene de más (override v1.1.0, eventos extra, Unidad, BYOK, fragmentación arquitectónica) + atemperar 2-3 afirmaciones que el deploy no respalda todavía.

### Tiempo restante para tesis impecable

- **Mínimo (defensa segura sin deploy de attestation)**: 1 día completo de trabajo concentrado:
  - Fase 1 código (sin Eje D): 2.5 horas.
  - Fase 2 redacción tesis: 5.5 horas.
  - Fase 4 validación: 30 min.
- **Ideal (con cierre operacional del Eje D)**: 2-3 días:
  - Lo anterior + Fase 3 con DI UNSL: 1-2 días extra.

### Lectura para próximo dev / director

Si llegaste a este documento sin haber leído el código:
- **Lo bueno**: el código es **muy sólido**. 42 ADRs, contratos en package compartido, tests bit-exact, RLS multi-tenant, attestation con failsafe. La tesis subestima en varios puntos qué tan terminado está el código.
- **Lo a corregir**: drift documental. La tesis quedó atrás del código en muchas cosas buenas (override v1.1.0, eventos extra, Unidad, BYOK) y al frente en pocas operacionales (Eje D, drift de versiones del prompt).
- **Estrategia**: la mayoría del trabajo restante es **redacción**, no código. La Sec 12 te da el orden exacto. Si seguís la checklist, en un día de trabajo enfocado tenés tesis y código alineados.
