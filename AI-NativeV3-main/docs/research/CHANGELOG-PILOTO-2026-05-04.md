# Changelog del piloto Juani2so — corte 2026-05-04

**Tesis**: Alberto Alejandro Cortez — *"Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación en Programación Universitaria"* (UNSL).

Documento de cierre tras una serie de epics OpenSpec aplicadas al monorepo entre el 2026-05-01 y el 2026-05-04. Lista qué se agregó, qué quedó verificado, y el único frente pendiente.

---

## Estado al cierre

- **6 epics archivadas** en `openspec/changes/archive/`.
- **1 epic activa pero bloqueada en exploración** (`ai-native-completion-and-byok`) — requiere 4 decisiones arquitectónicas del doctorando antes de avanzar.
- **862 tests passing** (`uv run pytest apps packages --ignore=apps/enrollment-service`), 4 skipped por env vars no seteadas (RLS contra Postgres real), 0 failed.
- **Cobertura plano pedagógico**: `tutor-service` 85% (cumple target), `ctr-service` 73% (a 2pts del target Fase A, gap a Fase B documentado en `BUGS-PILOTO.md` GAP-9), `classifier-service` 85% (cumple target).
- **12 microservicios FastAPI** (puertos 8000-8012) con `/health/ready` real chequeando dependencias críticas + 3 frontends React 19 (web-admin, web-teacher, web-student).
- **7 pilares de la tesis** implementados con evidencia testeable: CTR append-only SHA-256, 5 coherencias del classifier, tutor socrático con guardrails Fase A, attestation Ed25519 externa, N4 labeler v1.1.0, CII evolution longitudinal, alertas predictivas con privacy gate k≥5.

---

## Histórico de epics aplicadas (orden cronológico)

### 1. `2026-05-01-seed-template-id-and-manifest-reconcile`

**Qué hace**: cierra inconsistencias entre los seeds del piloto y la realidad del modelo de datos. Agregó `template_id` a `Episode.problema_id` (vincula la instancia con el template académico, ADR-016), reconcilió el manifest declarativo `ai-native-prompts/manifest.yaml` con el `default_prompt_version` que el tutor-service usa en runtime, y normalizó los nombres de comisiones para que sean humanos (no UUIDs raw).

**Por qué importa**: sin esto, los eventos del CTR apuntaban a un `problema_id=99999999-...` hardcoded que no existía como TP real — rompía reproducibilidad bit-a-bit ante una auditoría externa. El reconcile del manifest cierra el gap entre lo que frontends ven (via `/active_configs`) y lo que el tutor efectivamente usa al abrir episodios.

### 2. `2026-05-01-playwright-e2e-suite`

**Qué hace**: introdujo una suite Playwright top-level en `tests/e2e/` con 5 user journeys cross-frontend (web-admin, web-teacher, web-student). globalSetup, helpers compartidos, 3 targets `make` (`make e2e`, `make e2e-headed`, `make e2e-debug`) y README operativo.

**Por qué importa**: el monorepo tenía cero E2E coverage antes — solo vitest + RTL para componentes (con fetch mockeado) y pytest para backend. Ningún test conducía un browser real. Esta suite es la red de seguridad mínima para detectar regresiones cuando se mergea código que toca el ROUTE_MAP del api-gateway, los proxies de Vite o la auth dev-trust-headers.

### 3. `2026-05-03-closing-adrs-and-frontend-polish`

**Qué hace**: cierre de 1 ADR redactado nuevo (ADR-032 — alertas predictivas ML diferidas a piloto-2 con criterio cuantificable de revisita: ≥200 estudiantes, ≥30 intervenciones κ docente ≥0.6, AUC ≥0.75) + 4 fixes de polish frontend:
- KPI cards en web-admin home (count de comisiones/materias/estudiantes).
- Subtítulos sin UUIDs raw (mostrar nombres humanos).
- Microcopy con tildes corregidas (cp1252 / Windows-friendly).
- Sidebar topslot con separador visual.

**Por qué importa**: ADR-032 cierra honestamente la pregunta del comité doctoral "¿van a tener ML predictivo verdadero?" — la respuesta es "no en piloto-1, sí cuando el dataset alcance el umbral". Los fixes frontend bajan friction percibido para los docentes/admins UNSL en la primera demo.

### 4. `2026-05-04-grafana-dashboards-provisioned`

**Qué hace**: 5 dashboards provisionados en Grafana (Plataforma / CTR / AI Gateway / Tutor / Classifier) + instrumentación OTel mínima emitiendo métricas via OTLP push al Collector. `setup_observability()` ahora inicializa MeterProvider + OTLPMetricExporter por default — los 12 servicios consumen el wrapper.

**Por qué importa**: el comité quería ver dashboards en vivo, no screenshots. Cada dashboard es uno con paneles de p95 latency, error rate, throughput por servicio, integridad CTR (counter `ctr_episodes_integrity_compromised_total`), y cobertura de instrumentación OTel.

### 5. `2026-05-04-real-health-checks`

**Qué hace**: los 11 servicios FastAPI que devolvían `/health/ready` hardcoded ahora consumen un helper compartido en `packages/observability/src/platform_observability/health.py` (`check_postgres`, `check_redis`, `check_http`, `assemble_readiness`). `HealthResponse.checks` pasó de `dict[str, str]` vacío a `dict[str, CheckResult]` con `{ok, latency_ms, error}` por dependencia. Status semantics: `ready`/`degraded`/`error` → 200/200/503.

Smokes operativos validados: stop Postgres → 5 servicios marcan `error` + 503 en <10s; stop Redis → 3 servicios marcan `error`; stop ai-gateway (non-critical de tutor) → tutor marca `degraded` con HTTP 200; stop Keycloak → api-gateway + identity-service marcan `error`. Recovery <5s tras `docker start`.

**Por qué importa**: en Kubernetes los pods nunca se marcaban NotReady aunque la DB cayera — todas las fallas de infra se convertían en 500s opacos. Ahora los probes hacen su trabajo. `ctr-service` mantiene su patrón estable propio (no fue tocado para no agrandar blast radius).

### 6. `2026-05-04-pre-defense-hardening`

**Qué hace**: blindaje pre-defensa. **Cero features nuevas, cero cambios de contrato.** Solo:
- Tests focales en `tutor-service` cubriendo los 3 hot-spots auditados (`content_client.py` 0%→100%, `governance_client.py` 0%→100%, `clients.py` 41%→100%) + tests de routes. **Cobertura: 60% → 85%** (cumple target Fase A y Fase B).
- Tests focales en `ctr-service`: `test_chain_integrity.py` con 3 escenarios mínimos del invariante central (chain íntegra, self_hash mutado, chain_hash mutado, payload mutado, break en first event, cadena vacía); + tests del partition_worker construcción + events route validation. **Cobertura: 63% → 73%** (a 2pts del target Fase A, gap a Fase B documentado).
- 3 ADRs deferred ahora con comment-flags grep-ables `# Deferred: ADR-XXX / <milestone> — <razón>` en el call site (ADR-017 CCD embeddings en `ccd.py`, ADR-024 prompt reflexivo runtime en `governance_client.py`, ADR-026 botón insertar código tutor en `EpisodePage.tsx`).
- Smoke regresión global verde (862 tests passing).
- Fix de 2 regresiones legacy: test viejo de `api-gateway/tests/test_health.py` actualizado para mockear el helper (rota cuando se hace pegar real sin stack); test viejo de analytics-service esperaba `labeler_version="1.0.0"` cuando el actual es "1.1.0" (ADR-023 G8a).

**Por qué importa**: blinda la respuesta cuantitativa del comité. Antes de esta epic, el plano pedagógico tenía 60-63% coverage — el comité podía objetar trivialmente "¿el núcleo de la tesis está testeado?". Ahora la respuesta es "tutor 85% / classifier 85% / ctr 73% con plan documentado a 85% en piloto-2". El test directo de chain integrity cubre la propiedad central declarada en Sección 7.3 con 6 escenarios de mutation testing manual.

---

## Lo que está sólido (evidencia para defensa)

1. **Reproducibilidad bit-a-bit del classifier** — `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py`. El test que más vale ante el comité: emite mismo payload N veces, assertea byte-exact same hash. Cubre que la operacionalización semántica sea determinista y reversible.

2. **Chain integrity tampering detection** — `apps/ctr-service/tests/unit/test_chain_integrity.py` (nuevo en epic 6). 6 escenarios: chain íntegra, self_hash mutado, chain_hash mutado, payload mutado sin recomputar, break en first event, cadena vacía. Cubre RN-039/RN-040 + Sección 7.3.

3. **CTR sharding 8 partitions + integrity_checker reverse-verification** — `apps/ctr-service/src/ctr_service/workers/integrity_checker.py` (252 LOC defensivos), `producer.py` (single-writer per partition), `partition_worker.py` (consumer pattern). Append-only verificable post-hoc.

4. **Academic-service CRUD + RLS multi-tenant** — 66 endpoints reales para 11 entidades. `test_rls_isolation.py` valida aislamiento; `make check-rls` lo verifica en CI. Patrón repetible para nuevos servicios académicos.

5. **API gateway como único source of truth de identidad** — JWT RS256, headers autoritativos `X-Tenant-Id`/`X-User-Id`/`X-Role`, zero bypass via ROUTE_MAP. Endpoints no registrados en ROUTE_MAP quedan inaccesibles desde frontend (audit posture).

6. **Versioning hermético del plano pedagógico** — `LABELER_VERSION="1.1.0"` (ADR-023), `GUARDRAILS_CORPUS_VERSION` (ADR-019), `classifier_config_hash` SHA-256 determinista (ADR-009). Eventos viejos auditables con la versión que los procesó.

7. **Attestation externa Ed25519** — `integrity-attestation-service` firma append-only JSONL `attestations-YYYY-MM-DD.jsonl` con clave institucional UNSL. Independiente del ctr-service, eventually consistent (SLO 24h, RN-128). Verificable por auditor externo con `scripts/verify-attestations.py`.

8. **Health checks reales en los 12 servicios** — JSON granular con `{ok, latency_ms, error}` por dependencia, mapeo correcto a HTTP status codes para que kubelet saque pods de rotación cuando una critical dep cae.

9. **Sistema de ayuda in-app uniforme** — patrón `HelpButton` + `PageContainer` + `helpContent.tsx` consistente en los 3 frontends. Documentado en `.claude/skills/help-system-content/SKILL.md`.

10. **5 dashboards Grafana provisionados** — Plataforma / CTR / AI Gateway / Tutor / Classifier. Demo en vivo durante la defensa sin screenshots.

---

## Próximo avance: epic activa pendiente

### `ai-native-completion-and-byok`

**Estado actual**: solo `exploration.md` (32K LOC de exploración). Bloqueada en 4 decisiones arquitectónicas del doctorando que están marcadas con `(*)` en el archivo de exploración. Sin esas decisiones, el agente las tomaría solo y entrarían a la tesis sin review.

**Qué cubre la epic** (5 sub-cambios que cierran el loop AI-Native sin tocar invariantes doctorales):

1. **Sandbox + test cases automáticos en `web-student`** — el alumno valida su código contra assertions definidas por el docente. *Decisión bloqueante (\*)*: Pyodide client-side (latencia 0ms, test cases visibles al estudiante = no hay "hidden tests") VS subprocess server-side (200-500ms, hidden tests posibles, requiere worker pool + cgroups).

2. **Reflexión post-entrega en `web-student`** — cuestionario metacognitivo opcional al cierre del episodio, emite evento side-channel `reflexion_completada` (NO muta payload de `EpisodioCerrado`). *Decisión bloqueante (\*)*: ¿obligatorio o opcional? Obligatorio sesga la duración del episodio; opcional sesga la representatividad de la muestra reflexiva.

3. **Generación asistida de TPs con IA en `web-teacher`** — docente describe en NL → AI propone borrador de `TareaPracticaTemplate` → docente edita y publica. Bloqueado por el #5 (necesita BYOK para que el docente use su propia API key institucional, no la del piloto).

4. **Governance events con UI institucional en `web-admin`** — auditoría cross-comisión de intentos adversos (RN-129) y eventos de gobernanza. Reusa el endpoint `/api/v1/analytics/cohort/{id}/adversarial-events` que ya existe; agrega filtros institucionales (facultad/materia/período).

5. **BYOK multi-provider con scope facultad/materia** — admin configura keys de Gemini/Anthropic/Mistral con resolución jerárquica `materia → plan → carrera → facultad → tenant → default`. Reemplaza el `get_provider()` hardcoded del `ai-gateway`. Extiende el `tenant_secrets.py` resolver existente. *Decisión bloqueante (\*)*: encriptación at-rest — ¿AES-GCM/Fernet en DB (requiere `cryptography` lib + helper compartido) o seguir con K8s SealedSecrets (UX de admin más complicada)? *Decisión bloqueante (\*)*: ¿propagar `materia_id` cross-servicio (cambio en payload del ai-gateway que toca tutor-service + classifier-service) o resolver en el ai-gateway via cache Redis `materia:{id}:facultad_id`?

**Por qué está bloqueada**: las 4 decisiones afectan invariantes doctorales (privacidad, reproducibilidad, condición experimental). Si el agente las decide solo, el doctorando se entera al hacer review y puede haber re-trabajo grande.

**Effort estimado**: 5-7 días de implementación tras destrabar las 4 decisiones. Cada sub-cambio termina siendo su propia epic OpenSpec con propose + apply + archive.

**Recomendación operativa**: tratar esta epic como **post-defensa** o **piloto-2**. La defensa de tesis se sostiene con lo que YA está. BYOK + sandbox + reflexión + governance UI son features que mejoran ergonomía institucional y abren la puerta al uso real en aula, no son requisito de la tesis doctoral.

---

## Cómo usar este documento

- **Antes de tocar el repo**: leer la sección "Estado al cierre" + "Lo que está sólido" para entender la línea de base.
- **Para regenerar dashboards**: epic 4 archivada en `openspec/changes/archive/2026-05-04-grafana-dashboards-provisioned/` con tasks operativas.
- **Para retomar `ai-native-completion-and-byok`**: leer `openspec/changes/ai-native-completion-and-byok/exploration.md` (las 4 decisiones bloqueantes están marcadas con `(*)`), responder con criterio del doctorando, después invocar `/opsx:propose ai-native-completion-and-byok` para destrabarla.
- **Para defensa**: el material listo para mostrar al comité está en este documento + los ADRs en `docs/adr/` + los 5 dashboards en Grafana.
