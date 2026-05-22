# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estructura del directorio

Este directorio (wrapper `AI-Native-V5-main/`) **NO contiene código** — el monorepo real vive en `AI-NativeV3-main/`. Ojo con el nombre: el wrapper es V5 (snapshot 2026-05-20), el subdirectorio es V3 (heredado, sin renombrar). El versionado del wrapper avanza con cada snapshot importante (V4 → V5); el subdirectorio interno no se toca para no romper paths cacheados ni docs internas. Layout actual:

```
.
├── AI-NativeV3-main/                          ← Proyecto real (monorepo). Acá vive todo el código.
├── CLAUDE.md                                  ← Este archivo (puntero al proyecto real).
├── README.md                                  ← Onboarding técnico narrativo del wrapper (~420 líneas, TL;DR + arquitectura + bootstrap).
├── ONBOARDING.md                              ← Guía de onboarding alternativa (~20KB) — leer si README.md no alcanza.
│
├── docs/
│   ├── research/                              ← Auditorías y plan de acción (gobierno del proyecto)
│   │   ├── audita1.md                          ← Auditoría inicial — inventario, brechas, riesgos. Sección "⚠️ Errata" con falsos positivos.
│   │   ├── plan-accion.md                      ← 26 acciones priorizadas + DAG + tabla de estado. Leer la tabla al inicio antes de ejecutar.
│   │   ├── audi2.md                            ← Auditoría de completitud profunda (20 capabilities × 4 criterios). Fuente más reciente sobre estado del código.
│   │   ├── ppconarev.md                        ← Revisión paper vs implementación (umbral kappa, protocolo muestral, AI-Native framing, Caliper/xAPI, 3→5 coherencias).
│   │   └── loquehace.md                        ← Narrativo descriptivo para comité doctoral.
│   ├── papers/                                ← Drafts del paper y versiones intermedias
│   │   ├── paper-draft.md                      ← Draft consolidado — 10/10 decisiones académicas resueltas (Camino 1 + protocolo dual). Fuente vigente junto con ADR-046.
│   │   ├── paper-final.md                      ← Versión final para submisión CONAIISI.
│   │   ├── papermod.md                         ← Versión con modificaciones intermedias.
│   │   ├── paper-original.txt                  ← Texto crudo original.
│   │   └── gaby.docx                           ← Insumo coautoral (binario).
│   ├── BRANCH-PROTECTION.md                   ← Reglas de branch protection para A8.
│   ├── INFORME-PRE-PROD.md                    ← Informe de readiness pre-producción.
│   └── paper16mayo.docx                       ← Snapshot del paper al 2026-05-16 (binario).
│
├── _templates/                                ← Plantillas CONAIISI 2025 (formato A4 oficial)
│   ├── conaiisi2025-investigadores.doc
│   └── conaiisi2025-investigadores-converted.docx
│
├── PlanMejora.md                              ← Plan de mejora paper PDF vs código (2026-05-17, ~30KB) — 16 ítems P0-P3, posterior a audi2.md. Confirma match exacto de las 12 constantes del Apéndice A. Sección 0 (resumen ejecutivo) y tablas P1/P2 son lectura obligatoria si se toca paper o se prepara defensa.
├── informeSoc.md                              ← Análisis externo — lente didáctica socrática (~33KB).
├── informeSocra1.md                           ← Análisis externo — lente cognitiva (Mislevy/Cronbach/Messick, ~43KB). Complementa informeSoc.md.
├── revision-coautoral-paper-2026-05-16.md     ← Revisión coautoral del paper-draft (~30KB) — comentarios línea a línea. **Header dice "consolidadas en paper y propagadas a tesis sin esperar sesión coautoral"**: las 7 CS viven en paper-draft.md (tesis), NO se forzaron en paper-final.md (versión congreso comprimida).
├── revision-coautoral-instrumentos-2026-05-20.md ← Paquete coautoral para Garis sobre los 3 instrumentos quasi-experimentales del paper §6.2 (~19KB, 8 secciones). 23 items + 5 análogos de transfer con decisiones checkbox por item. Espera sesión con Garis para validar contenido y sacar markers `[PLACEHOLDER GARIS]` / `[PLACEHOLDER CATEDRA UTN]`.
├── paquete-coordinacion-intercoder-2026-05-20.md ← Paquete operativo para destrabar A2 del plan-accion (validación intercoder κ ≥ 0,70). ~22KB, 10 secciones. Incluye especificación del script `select-intercoder-corpus.py`, carta de invitación + acuerdo confidencialidad templates editables, cronograma 8-10 semanas, template reporte intercoder. NO reemplaza `manual-etiquetador-N4.md` del subdir — lo complementa con lo operativo.
├── plan1Socra.md                              ← Plan derivado de informeSoc/informeSocra1.
├── comparacion.md                             ← Comparativas (~20KB) — versión a versión del paper / decisiones.
├── paper_conaiisi.txt                         ← Texto plano del PDF (~118KB extraídas con pdftotext). Útil para grep/búsqueda del paper desde Claude; el .pdf es binario y no se puede leer directamente.
│
├── AI-Native-V5-backup-pre-UTN-20260520-231416.tar.gz ← Backup tarball defensivo (7.4MB) tomado **antes** del cambio masivo `UNSL → UTN` del 2026-05-20. Restaurar con `tar xzf AI-Native-V5-backup-pre-UTN-*.tar.gz` si hay que revertir. **NO borrar** mientras los binarios `.docx`/`.pdf` mantengan inconsistencia con el cambio (ver bloque "Cambio institucional UNSL → UTN").
│
└── Artifacts binarios (no editables por Claude — referencia para humanos):
    ├── paper_conaiisi.pdf                      ← PDF final del paper para submisión CONAIISI 2025. Para inspeccionar contenido textual, usar `paper_conaiisi.txt`. **NOTA**: este PDF sigue diciendo "UNSL" — el cambio masivo del 2026-05-20 NO tocó binarios. Re-generar desde `paper-final.md` actualizado antes de submitir.
    ├── paper16mayo.docx                        ← Snapshot DOCX del paper. Dice "UNSL" — re-exportar desde `paper-draft.md` si la versión académica formal exige consistencia.
    ├── tesis16mayo.docx                        ← Snapshot DOCX de la tesis doctoral completa. Idem — dice "UNSL", re-exportar desde `Tesis4.docx` markdown del subdir actualizado.
    ├── trayectoria.docx                        ← Trayectoria académica/profesional del autor (insumo para defensa/comité).
    ├── comoHacer.docx                          ← Notas operativas/metodológicas (insumo personal del autor).
    ├── gaby.docx                               ← Insumo coautoral.
    └── Pautas_para_autores_CONAIISI_A4_2025.doc ← Pautas oficiales del congreso.
```

**Relación entre docs** (tres cadenas paralelas que se cruzan):

1. **Cadena código**: `docs/research/audita1.md` (qué hay) → `docs/research/plan-accion.md` (cómo arreglarlo) → ejecución → `docs/research/audi2.md` (qué quedó terminado al 100%). Si hay conflicto sobre estado del código, **`audi2.md` es la fuente más reciente**.
2. **Cadena paper**: `docs/research/ppconarev.md` (paper viejo `ppcona.docx` vs código) → `docs/papers/paper-draft.md` (decisiones resueltas) → `docs/papers/paper-final.md` (submisión) → `paper_conaiisi.pdf` (entregable). Si hay conflicto sobre decisiones académicas, **`paper-draft.md` + ADR-046 son las fuentes vigentes**.
3. **Puente paper↔código (la pieza más fresca)**: `PlanMejora.md` (2026-05-17) cruza el PDF entregable contra el código real y devuelve 16 ítems organizados P0/P1/P2/P3. **Es el sucesor natural de `audi2.md` y `ppconarev.md`** — leer antes de tocar el paper o de planificar la defensa. Confirma que las 12 constantes del Apéndice A.4 hacen match exacto con el código (no hay falsos positivos en la integridad técnica).
4. **Cadena análisis externo** (no del autor, lente cognitiva/didáctica): `informeSoc.md` (didáctica socrática) + `informeSocra1.md` (ciencia cognitiva del aprendizaje) → `revision-coautoral-paper-2026-05-16.md` (comentarios sobre el paper-draft) → `plan1Socra.md`. Útil para defensa doctoral y respuestas a comité.

**Antes de cualquier comando** (build, test, dev, migrate, lint), entrá al subdirectorio:

```bash
cd "AI-NativeV3-main"
```

Sin ese `cd`, todos los `make`, `pnpm`, `uv`, `pytest` van a fallar — no hay `Makefile`, `package.json` ni `pyproject.toml` en este nivel.

## Source of truth

El CLAUDE.md operativo (invariantes, constantes hash, versiones pinned, gotchas Windows/IPv6/Vite, ports, decisiones non-obvious) vive en **`AI-NativeV3-main/CLAUDE.md`** (~247 líneas). Leelo antes de modificar cualquier cosa que toque:

- Reproducibilidad bit-a-bit (`classifier_config_hash`, `LABELER_VERSION=1.2.0`).
- CTR append-only (`GENESIS_HASH`, `chain_hash`, `self_hash`).
- BYOK encryption (`BYOK_MASTER_KEY`).
- k-anonymity (`MIN_STUDENTS_FOR_QUARTILES=5`, `MIN_EPISODES_FOR_LONGITUDINAL=3`).
- RLS multi-tenant + headers `X-Tenant-Id` / `X-User-Id` / `X-User-Roles`.

## Contexto del proyecto

Monorepo de la plataforma **AI-Native N4** — tesis doctoral UTN (Cortez): "Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación en Programación Universitaria". **No es producto comercial**: piloto académico cuya aceptabilidad doctoral depende de invariantes criptográficas (append-only, reproducibilidad, k-anonymity).

Stack: **11 servicios Python activos** (FastAPI 0.100+ / SQLAlchemy 2.0 async / Alembic / structlog / OTel) + 3 frontends React 19 (web-admin, web-student, web-teacher con Vite 6 + TanStack Router/Query) + 7 packages compartidos. Workspace híbrido `uv` (Python) + `pnpm` + `turbo` (TS).

`identity-service` y `enrollment-service` **fueron borrados** del workspace (A25 del plan-accion) — eran deprecated por ADR-041 y ADR-030 respectivamente. Auth movido al api-gateway, bulk-import movido a academic-service.

## Arquitectura en un vistazo

Dos planos desacoplados por bus Redis Streams particionado (8 shards):

- **Plano académico-operacional**: `academic-service` (CRUDs + bulk-import de inscripciones), `evaluation-service` (entregas + calificaciones, ADR del epic `tp-entregas-correccion`), `analytics-service` (kappa, progresión cohorte, alertas predictivas, export académico anonimizado).
- **Plano pedagógico-evaluativo (núcleo de la tesis)**: `tutor-service` (SSE socrático con guardrails ADR-019/043), `ctr-service` + 8 workers (cadena criptográfica SHA-256 append-only, una partición por worker), `classifier-service` (N4 + 3 coherencias agregadas en 5 métricas + LABELER_VERSION=1.2.0), `content-service` (RAG pgvector), `governance-service` (prompts versionados internos, NO expuesto en ROUTE_MAP).
- **Transversales**: `api-gateway` (único punto de auth — emite JWT RS256 e inyecta `X-Tenant-Id`/`X-User-Id`/`X-User-Roles` a servicios internos; cualquier endpoint público requiere entrada en `ROUTE_MAP`), `ai-gateway` (LLM proxy con BYOK por tenant — todo LLM/embedding pasa por acá), `integrity-attestation-service` (Ed25519 post-cierre, vive en VPS UTN, 503 by design en dev local).

**4 bases lógicas separadas** sin joins cross-base: `academic_main`, `ctr_store`, `classifier_db`, `content_db`. Los servicios se comunican por eventos Redis Streams o HTTP via api-gateway, nunca por queries cross-base.

**Multi-tenancy** = Row-Level Security forzado en Postgres (ADR-001). Toda tabla con `tenant_id` tiene policy RLS y el driver entra con `SET LOCAL app.current_tenant = ...` por request (helper `set_tenant_rls`). `make check-rls` lo verifica en CI.

Diagrama visual ASCII + flujo pedagógico docente↔alumno + descripción del rol de cada servicio: `README.md` secciones 2 ("Arquitectura en un vistazo") y 7 ("Flujo pedagógico"). Detalle profundo de invariantes, constantes hash y gotchas operacionales: `AI-NativeV3-main/CLAUDE.md`.

## Invariantes críticas (resumen)

Estas NO son sugerencias — están verificadas por tests y fundamentan la aceptabilidad doctoral del piloto. Detalles, fórmulas canónicas, constantes hash y casos de borde están en `AI-NativeV3-main/CLAUDE.md` sección "Propiedades críticas":

| Invariante | Qué significa | ADR |
|---|---|---|
| **CTR append-only** | Nunca `UPDATE`/`DELETE` de eventos. Reclasificar = `is_current=false` viejo + INSERT nuevo. | ADR-010 |
| **`classifier_config_hash` determinista** | Reproducibilidad bit-a-bit. Tocar sort_keys/separators/ensure_ascii/exclusiones rompe la tesis. | ADR-020 |
| **3 coherencias agregadas en 5 métricas SEPARADAS** | 3 coherencias conceptuales (Temporal, Código-Discurso, Inter-Iteración) operacionalizadas en 5 columnas independientes: `CT`, `CCD_mean`, `CCD_orphan_ratio`, `CII_stability`, `CII_evolution`. Nunca colapsar en score único. | ADR-018 |
| **k-anonymity** | `MIN_STUDENTS_FOR_QUARTILES=5` (cuartiles cohorte) y `MIN_EPISODES_FOR_LONGITUDINAL=3` (slope longitudinal por template). | ADR-022/RN-131 |
| **Multi-tenant RLS forzado** | Toda tabla con `tenant_id` tiene policy RLS. `make check-rls` en CI. | ADR-001 |
| **api-gateway único source de identidad** | Servicios internos confían en headers `X-Tenant-Id`/`X-User-Id`/`X-User-Roles` (plural). No re-verificar JWT aguas abajo. | — |
| **Write-only al CTR desde tutor-service** | Excepto `codigo_ejecutado` (usa `user_id` del estudiante) y `intento_adverso_detectado` side-channel. | ADR-010 |
| **`n_level` derivado en lectura, NUNCA en payload** | El etiquetador es función pura sobre `(event_type, payload)`. Agregarlo al payload rompe `self_hash`. | ADR-020 |
| **CTR apunta a la instancia, NUNCA al template** | `Episode.problema_id = TareaPractica.id` (instancia). Si el template muta, la instancia marca `has_drift=true` y el CTR queda intacto. | ADR-016 |
| **Eventos excluidos del feature extraction** | `reflexion_completada`, `tp_entregada`, `tp_calificada` no entran al classifier. Cada exclusión nueva requiere ADR. | ADR-027/044 |
| **Attestation Ed25519 post-cierre eventual** | XADD a stream Redis `attestation.requests`. Ausencia NO bloquea cierre (SLO 24h). | ADR-021/RN-128 |
| **Export académico anonimizado** | `salt ≥ 16 chars`, `include_prompts=False` default. `student_alias` (hash) en export; `student_pseudonym` (UUID) en endpoints UI. | RN-090 |

**Romper cualquiera invalida la tesis.** Constantes críticas (`GENESIS_HASH = "0"*64`, `TUTOR_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000010")`, `NUM_PARTITIONS=8`, `BYOK_MASTER_KEY`, `LABELER_VERSION=1.2.0`, ventanas N1/N4 del override `anotacion_creada`, timeout abandono = 1800s) están enumeradas en el CLAUDE.md interno bajo "Constantes que NO deben inventarse ni cambiarse" — incluyen la fórmula exacta de cada hash (`self_hash` con `ensure_ascii=False`, `chain_hash` con orden `self+prev`, `classifier_config_hash` JSON canónico).

## Estado actual (resumen — ver `audi2.md`, `plan-accion.md` y `paper-draft.md` para detalle vigente)

Las cifras que siguen son un snapshot estable, no la verdad de hoy — para el conteo actual leer los archivos referenciados directamente.

**Completitud del sistema (de `audi2.md`)**: 11/20 capabilities funcionales activas al 100% en los 4 criterios estrictos (código+tests+docs / invariantes / producción piloto / aprobación académica). Las otras 9 son parciales con bloqueador específico identificable. 6 capabilities en skeleton OFF / DEFERRED (agenda piloto-2 o gates externos).

**Núcleo defendible al 100%**: gestión multi-tenant, bulk-import, TP templates con auto-instanciación, dashboard cohorte, alertas k-anonymity, clasificación N4, reflexión post-cierre, longitudinal CII, auditoría criptográfica CTR, generación TP por IA, BYOK multi-provider (esta última reclasificada de parcial a 100% post-A14, sentinel pattern UUID v5 cerrando gap `byok_keys_usage` en env_fallback).

**Plan ejecutado (`plan-accion.md`)**: 23/26 acciones cerradas (header del doc; su propia tabla literal lista 18 ✅ + 4 externas marcadas + 4 pendientes — la diferencia es por cómo el doc cuenta externas con pre-cond cumplida) + 5 mejoras bonus discontiguas (F1-F4 + F6, ver `audi2.md` §8) + alineamiento paper/código por ADR-046. Quedan A15/A16/A18/A20 (riesgosos o de cierre) + 4 externos (A1 DB real, A2 intercoder, A3 Keycloak DI UTN, A5 defensa). **Consultar la tabla de estado al inicio del archivo** antes de retomar — sub-agents pueden haber cerrado más acciones desde este snapshot.

**Sprint posterior `plan-mejora-instrumentos-research` (2026-05-17, ver `AI-NativeV3-main/docs/CAPABILITIES.md`)**: cierra P1 + P2-1/2/3 + P2-4 del `PlanMejora.md`. Materializa 3 instrumentos del diseño cuasi-experimental del paper §6.2 (cuestionario IA previa, pretest autoeficacia adaptado de Lishinski 2016, test transferencia) — todos con **esqueleto técnico cerrado pero contenido marcado `[PLACEHOLDER GARIS]` / `[PLACEHOLDER CATEDRA UTN]`** hasta validación coautoral. También: ADR-053 (marcos interpretativos MI1-MI3 + 7 principios del paper §7.3 + marcador anti-reificación en UI), `docs/limitaciones-declaradas.md` 2026-05-17 (5 riesgos a priori R1-R5 con mitigación), protocolo de entrevistas semi-estructuradas (Braun & Clarke 2006), +21 Casbin policies (184 → **205 actuales**, no las 170 que aún figuran en audi2.md y en el paper publicado). Esto NO bumpea el "11/20 capabilities" porque los esqueletos no pasan C3 (producción con datos reales) ni C4 (aprobación coautoral).

**Paper consolidado (`paper-draft.md`)**: 10/10 decisiones académicas resueltas en dos pasadas — Camino 1 + protocolo dual para κ ≥ 0,70 (formalizado en ADR-046) y 4 decisiones temáticas (presentación canónica como 3 coherencias agregadas con 5 métricas internas alineada a UI, mención única "AI-Native N4" como proyecto, párrafo único con extensiones operativas referenciando ADRs, suavización "inspirado en" para Caliper/xAPI).

**Stack operacional (última verificación end-to-end)**: 11 servicios HTTP healthy en :8000-:8011 (excepto :8012 integrity-attestation que es 503 by design en dev local — vive en VPS UTN), 8 ctr-workers consumiendo streams Redis, 3 frontends Vite en :5173/5174/5175. End-to-end verificado: api-gateway → analytics-service → DB devuelve clasificaciones reales del seed (3 comisiones, 18 estudiantes, 106 classifications). Bugfix Windows aplicado a `asyncio.add_signal_handler` no implementado en `ProactorEventLoop` — workers ahora arrancan limpios en Windows. **Para verificar el estado vigente del stack levantado**: `cd AI-NativeV3-main && bash scripts/check-health.sh`.

**2 riesgos académicos críticos vigentes**:
1. **106 classifications con hash legacy** pre-LABELER_VERSION 1.2.0 — pre-cond A12 ya cumplida (idempotencia `persist_classification`); falta A1 (worker batch sobre DB real del piloto).
2. **Validación intercoder κ ≥ 0,70** (post-ADR-046) sobre protocolo dual: 200 eventos estratificados 50 por nivel N1-N4 (Protocolo A) + 50 episodios cerrados en 3 categorías de apropiación (Protocolo B). Bloquea socratic_compliance (ADR-044) y lexical_anotacion (ADR-045) que siguen en feature-flag OFF. **Cuello de botella académico más grande** — requiere coordinación con 2 docentes UTN (~25-30h por docente).

**Acciones humanas pendientes** (no son código): marcar `Smoke E2E API` como Required check en branch protection (A8); coordinar Keycloak claim `comisiones_activas` con DI UTN (A3); coordinar etiquetadores UTN para κ ≥ 0,70 con protocolo dual (A2); ejecutar re-clasificación con DB real (A1); revisión coautoral del paper-draft.md con Ana Garis previa a submisión; consolidar agradecimientos (Daniela Carbonari co-directora del PID, Bruno Roberti, Carlos Martínez, Claudia Naveda, Juan Sarmiento, Juan Robledo).

## Cambio institucional UNSL → UTN (2026-05-20)

La institución que aloja el piloto se movió **realmente** de UNSL (Universidad Nacional de San Luis) a UTN (Universidad Tecnológica Nacional). Reemplazo masivo aplicado en 196 archivos editables, 947 ocurrencias, +2 archivos renombrados (`unsl_onboarding.py` → `utn_onboarding.py`, `unsl-pilot.json` → `utn-pilot.json`). Verificación: cero matches editables residuales. `UTN-FRM` (afiliación de Garis) preservado intacto.

**Lo que NO se tocó y mantiene inconsistencia conocida**:
- Archivos binarios `.docx`/`.pdf`/`.doc` (Claude no los puede editar): `paper_conaiisi.pdf`, `paper16mayo.docx`, `tesis16mayo.docx`, `ppcona.docx`, `Tesis4.docx`, `protocolo-piloto-unsl*.docx`, etc. Todos siguen diciendo UNSL. **Si la versión académica formal exige consistencia**: re-exportar desde los `.md` actualizados (pandoc / Word / LaTeX según corresponda). Los 2 `protocolo-piloto-unsl*.docx` mantienen "unsl" en el nombre del archivo — considerar renombrar también.
- Memorias engram con menciones a UNSL (contexto histórico de decisiones previas al cambio). No se rebuscan-y-reemplazan automáticamente. Si una próxima sesión carga contexto que dice "UNSL", entender que es referencia histórica al estado pre-2026-05-20.

**Backup defensivo disponible**: `AI-Native-V5-backup-pre-UTN-20260520-231416.tar.gz` en el root. Conserva el estado completo pre-cambio. Restaurar con `tar xzf` si hay que revertir.

**Implicación académica en agradecimientos del paper**: ahora `paper-draft.md` y `paper-final.md` dicen *"Cortez & Garis, UTN-FRM + UTN"* (antes UTN-FRM + UNSL). La formulación puede sonar redundante porque UTN-FRM es facultad de UTN. Si Cortez y Garis están ambos en UTN-FRM, consolidar a una sola afiliación; si son sedes distintas dentro de UTN, mantener separadas con aclaración explícita.

## Trabajar en este directorio vs. en el subdirectorio

- Editar / leer / referenciar cualquier `.md` bajo `docs/research/`, `docs/papers/`, o los análisis externos del root (`informeSoc.md`, `informeSocra1.md`, `revision-coautoral-paper-*.md`, `plan1Socra.md`, `comparacion.md`) → desde acá está bien. Son docs de gobierno + análisis académico, no código.
- Cualquier cambio de código, infra, tests, docs internas, ADRs (incluido el ADR-046 sobre kappa), SESSION-LOG → siempre **desde `AI-NativeV3-main/`** (`cd "AI-NativeV3-main"` primero).
- Si vas a hacer trabajo sustancial de código, abrí Claude Code directamente en `AI-NativeV3-main/` y usá su CLAUDE.md (~252 líneas, denso con invariantes, gotchas Windows/IPv6/Vite, constantes hash y comandos operativos) como guía principal.
- Si vas a ejecutar acciones de `docs/research/plan-accion.md`, primero leé la tabla de estado al inicio del archivo para confirmar qué ya está cerrado (evitar duplicar trabajo). Sub-agents que ejecutaron acciones pueden haber descubierto deuda no documentada — chequear engram con `topic_key: plan/action-2026-05/*`.
- Si vas a tocar el paper o discutir decisiones académicas, leé primero **`PlanMejora.md`** (auditoría más fresca paper PDF vs código, 2026-05-17), luego `docs/research/ppconarev.md` (divergencias contra el paper viejo) y finalmente `docs/papers/paper-draft.md` (decisiones resueltas). Para feedback de revisores externos, sumá `informeSoc.md` + `informeSocra1.md` + `revision-coautoral-paper-2026-05-16.md`. El paper original `AI-NativeV3-main/ppcona.docx` queda intacto como insumo. Decisiones académicas formales viven en ADRs del repositorio (especialmente ADR-046 para kappa).
- Si necesitás grep o búsqueda dentro del texto del paper publicado, usá `paper_conaiisi.txt` (extraído con `pdftotext`) — el `.pdf` es binario y Claude no lo lee bien.
- Los `.docx`, `.pdf` y `.doc` del root son **artifacts binarios** — Claude no los puede editar y los lee con dificultad. Tratarlos como referencia para humanos, no como fuente operativa.

## Comandos comunes

**Todos asumen `cd AI-NativeV3-main` previo.** No hay `Makefile` ni `pyproject.toml` en este nivel — todo target falla sin el `cd`.

### Bootstrap (primera vez, ~5-10 min)

```bash
cd AI-NativeV3-main
cp .env.example .env                                   # editar BYOK_MASTER_KEY (openssl rand -base64 32)
docker compose -f infrastructure/docker-compose.dev.yml up -d
uv sync --all-packages
pnpm install
ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/academic_main \
CTR_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store \
CTR_STORE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ctr_store \
CLASSIFIER_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/classifier_db \
CONTENT_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/content_db \
bash scripts/migrate-all.sh
uv run python -m academic_service.seeds.casbin_policies
uv run python scripts/seed-3-comisiones.py
```

Alternativa más corta si tenés todo instalado: `make init` (orquesta `dev-bootstrap` + `install` + `migrate` + `setup-dev-perms` + `setup-rls-user` + `seed-casbin`).

### Día a día

```bash
bash scripts/dev-start-all.sh    # 11 servicios HTTP + 8 ctr-workers en background
make dev                          # 3 frontends Vite (:5173 admin, :5174 teacher, :5175 student)
bash scripts/dev-stop-all.sh     # apagar servicios (Ctrl+C aparte para `make dev`)
make status                       # estado infra + health de servicios
bash scripts/check-health.sh      # solo health (espera 10/11 OK; :8012 es 503 by design en dev local)
```

### Tests

```bash
make test                                        # suite completa Python + TS (no usar en iteración rápida)
make test-fast                                   # solo Python unit + casbin matrix, con -x (corte al primer fallo)
make test-rls                                    # 4 tests de RLS contra Postgres con user non-superuser
make test-smoke                                  # 30 smoke E2E API contra stack levantado (<2s)
make test-smoke-local                            # mismo, pero re-seedea y skipea :8012 (para piloto local)
make test-e2e                                    # Playwright contra frontends (asume seed activo)

# Test individual Python
uv run pytest apps/<svc>/tests/unit/test_X.py::test_Y -v

# Test individual TS (desde la app)
cd apps/web-teacher && pnpm test -- src/components/Foo.test.tsx
```

`make test-rls` y `make test-smoke` son las redes de seguridad principales del piloto. **Antes de declarar cerrado un epic, agregale smoke tests** — atrapan la clase de bugs que escapan a tests unit con DB mockeada (RN: BYOK `SET LOCAL` con bind param que Postgres no acepta, que pasó tests porque mockeaban DB y falló en runtime).

### Calidad

```bash
make lint                  # ruff check + ruff format --check + turbo lint
make lint-fix              # autofix
make typecheck             # mypy + turbo typecheck
make check-rls             # verifica que toda tabla con tenant_id tenga RLS policy
make check-claude-md       # detecta drift numérico entre claims del CLAUDE.md interno y el código real
```

`make check-claude-md` es el detector de mentiras del CLAUDE.md operativo — corrérlo después de tocar invariantes, constantes hash o conteos.

### Migraciones

```bash
make migrate                                              # aplica pendientes en las 4 bases
make migrate-new SERVICE=academic-service NAME=add_foo    # nueva migration autogenerate
```

**Gotcha**: `alembic/env.py` de `academic-service` apunta hardcoded a `academic_user` que NO es owner en dev. Si `make migrate` falla con permission denied, usar el override explícito del bootstrap (las env vars `*_DB_URL` apuntando a `postgres:postgres`).

### Reset y limpieza

```bash
bash scripts/reset-to-seed.sh    # vuelve al estado "recién seedeado" (preserva comisiones/docentes/alumnos/25 ejercicios canónicos/Casbin/BYOK)
make clean                        # limpia caches Python/TS
make clean-all                    # destruye infra Docker (volúmenes incluidos) — DESTRUCTIVO
```

### URLs útiles con el stack arriba

| URL | Servicio |
|---|---|
| http://localhost:5173 | web-admin |
| http://localhost:5174 | web-teacher |
| http://localhost:5175 | web-student |
| http://localhost:8000 | api-gateway |
| http://localhost:3000 | Grafana |
| http://localhost:16686 | Jaeger |
| http://localhost:8180 | Keycloak admin |
| http://localhost:9090 | Prometheus |
