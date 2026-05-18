## Why

La auditoría 2026-05-04 dejó el piloto en estado **PARCIAL-ROBUSTO**: los 7 pilares de la tesis están implementados, pero el plano pedagógico tiene **gap de cobertura crítico** (`tutor-service` 60%, `ctr-service` 63% vs target 85%). El comité doctoral puede objetar cuantitativamente la robustez del núcleo de la tesis. Además, hay **3 ADRs declarados como deferred** (ADR-017 CCD embeddings, ADR-024 prompt reflexivo runtime, ADR-026 botón insertar código tutor) cuya marca en el código es solo el doc del ADR — no hay un comment-flag explícito en el sitio del código que diga "esto es deuda intencional con criterio de revisita en piloto-2", lo que dificulta la trazabilidad ante el comité. Y NO hay test directo de **chain integrity tampering detection** del CTR (la propiedad central de la tesis); existe el `integrity_checker` worker, pero la evidencia de que detecta corrupción de la cadena es implícita.

Esta epic NO agrega features nuevos — blinda lo existente con tests focalizados, evidencia explícita en código, y verificación de regresión global. Es la inversión mínima (~4-6h) que cierra las objeciones cuantificables del comité y permite ir a defensa con narrativa "todo lo que está, está testeado y trazable".

## What Changes

- **Tests de cobertura focalizados en `tutor-service`** (target +15 pts, de ~60% a ~75%):
  - `apps/tutor-service/tests/unit/test_content_client.py` — mock httpx + assertions sobre payload + error handling.
  - `apps/tutor-service/tests/unit/test_governance_client.py` — mock + verificación de fetch del prompt activo.
  - `apps/tutor-service/tests/unit/test_clients.py` — academic_client + ai_gateway_client retries + timeouts.
  - `apps/tutor-service/tests/unit/test_episodes_route.py` — mocks de tutor_core para validar SSE shape sin pegar a LLM real.
- **Tests de cobertura focalizados en `ctr-service`** (target +12 pts, de ~63% a ~75%):
  - `apps/ctr-service/tests/unit/test_partition_worker.py` — mock Redis stream + verificación de single-writer per partition.
  - `apps/ctr-service/tests/unit/test_events_route.py` — write event + verify chain endpoints con mocks de DB.
  - `apps/ctr-service/tests/unit/test_chain_integrity.py` — **test directo del invariante central**: emite N eventos con `producer.publish()`, corre `integrity_checker.verify_episode_chain()`, mutea un byte del `self_hash` o `chain_hash` de un evento intermedio, assertea que el checker marca `integrity_compromised=true`. Cubre RN-039/RN-040.
- **Marcar los 3 ADRs deferred con comments explícitos en código** (sin tocar lógica):
  - ADR-017 (CCD embeddings semánticos) → comment-flag en `apps/classifier-service/src/classifier_service/services/ccd.py` indicando "implementación temporal por ventana 2 min, deferred a embeddings semánticos en ADR-017 / piloto-2".
  - ADR-024 (prompt reflexivo runtime) → comment-flag en `apps/tutor-service/src/tutor_service/services/tutor_core.py` o `governance_client.py` cerca del fetch del prompt indicando "prompt_kind reflexivo en runtime deferred a ADR-024 / piloto-2".
  - ADR-026 (botón insertar código del tutor en web-student) → comment-flag en `apps/web-student/src/pages/EpisodePage.tsx` cerca del bloque del editor Monaco indicando "feature deferred a ADR-026 / post-defensa".
- **Smoke regression global**: correr `uv run pytest apps packages -x` (excluyendo `enrollment-service` por dep faltante pre-existente, ya documentado) y verificar 100% verde. Documentar el conteo final en `BUGS-PILOTO.md`.
- **Coverage targets verificables**: agregar invocación local `uv run pytest apps/tutor-service apps/ctr-service --cov=tutor_service --cov=ctr_service --cov-report=term-missing` para que cualquier futuro contribuidor pueda re-medir.
- **NO incluido (out-of-scope explícito)**:
  - Tests de frontends (vitest + RTL) — effort grande, no parte de blindaje.
  - Endpoint público `cii-evolution-longitudinal` en analytics-service — feature nueva, va a `ai-native-completion-and-byok`.
  - Health check refactor del `ctr-service` para que use el helper compartido — separate change.
  - Ratchet de coverage gate global (60% → 80%) — Fase A documentada en `BUGS-PILOTO.md` GAP-9, fuera de scope acá.

## Capabilities

### New Capabilities
(ninguna)

### Modified Capabilities
(ninguna — esta epic agrega tests + comments, no cambia contratos públicos.)

## Impact

- **Código tocado**: ~7 archivos de test nuevos (~600-800 LOC total) + 3 archivos de código fuente con un comment-flag de 2-3 líneas cada uno. **Cero cambios de lógica** en código de producción.
- **Sin migraciones**, sin cambios de contrato externo, sin cambios en helm chart, sin cambios en ROUTE_MAP del api-gateway.
- **CI**: los nuevos tests corren como parte de `make test`. Si CI tiene gate de coverage, el delta esperado es +12-15 pts en tutor + ctr.
- **Riesgo 1 — tests escritos pero subiendo cobertura menos de target**: hot-spots identificados (clients HTTP, partition_worker, routes/events) son los de mayor leverage. Si el delta real es <10 pts, escribir 1-2 tests adicionales en hot-spot secundario.
- **Riesgo 2 — `test_chain_integrity.py` requiere infra real (Redis + Postgres) o mocks complejos**: optar por mocks (consistente con el resto de tests unit del proyecto) y verificar el invariante con seq de eventos in-memory + manual mutation del campo. Si el mock se vuelve frágil, mover a `tests/integration/` y aceptar que solo corre con `make test-rls` o stack levantada.
- **Acceptance criteria** (validado en specs/tasks):
  - `uv run pytest apps/tutor-service` y `apps/ctr-service` reportan coverage ≥ 75% en sus respectivos paquetes (verificado con `--cov-report=term-missing`).
  - `test_chain_integrity.py` cubre 3 escenarios: chain íntegra (no flag), self_hash mutado (flag), chain_hash mutado (flag).
  - Los 3 ADRs deferred tienen comment-flag in-place con formato uniforme (`# Deferred: ADR-XXX / piloto-2 — <breve razón>`).
  - `BUGS-PILOTO.md` GAP-9 actualizado con coverage actual post-epic.
- **Out-of-scope explícito** ya enumerado en What Changes.
