## 1. Tests tutor-service (target +15 pts → ~75%)

- [x] 1.1 Crear `apps/tutor-service/tests/unit/test_content_client.py` mockeando httpx para cubrir success path + error 404/500 + timeout. Verificar shape de chunks devueltos + `chunks_used_hash` propagation (RN-026).
- [x] 1.2 Crear `apps/tutor-service/tests/unit/test_governance_client.py` mockeando fetch del prompt activo via httpx. Cubrir success + 404 (prompt missing) + caching si aplica.
- [x] 1.3 Crear `apps/tutor-service/tests/unit/test_clients.py` para `academic_client` + `ai_gateway_client`: success + retries + timeout + auth header inyectado.
- [x] 1.4 Crear `apps/tutor-service/tests/unit/test_episodes_route.py` mockeando `tutor_core.interact` para validar shape SSE + endpoint `POST /api/v1/episodes/{id}/abandoned` con `reason="explicit"` y `reason="timeout"`.
- [x] 1.5 Correr `uv run pytest apps/tutor-service --cov=tutor_service --cov-report=term-missing` y verificar coverage ≥ 75%. Si < 75%, agregar 1-2 tests al hot-spot secundario (`features.py` o `services/abandonment_worker.py`).

## 2. Tests ctr-service (target +12 pts → ~75%)

- [x] 2.1 Crear `apps/ctr-service/tests/unit/test_partition_worker.py` mockeando Redis stream client. Cubrir consumer loop (XREADGROUP), single-writer assertion via `lock_acquired` mock, manejo de excepciones del payload deserialization.
- [x] 2.2 Crear `apps/ctr-service/tests/unit/test_events_route.py` mockeando DB session para los endpoints `POST /api/v1/events` (write) + `GET /api/v1/episodes/{id}/verify` (read+verify alias del audit, ADR-031). Cubrir 200 + 404 + tamper detection en verify.
- [x] 2.3 Crear `apps/ctr-service/tests/unit/test_chain_integrity.py` con 3 scenarios mínimos del spec: chain íntegra, self_hash mutado, chain_hash mutado. Construir N=5 eventos en memoria con `compute_self_hash` + `compute_chain_hash` reales (importados de `packages/contracts`). Si no existe helper público `verify_chain(events)`, refactorizar `integrity_checker.py` para exponerlo (D2 + spec optional refactor).
- [x] 2.4 Correr `uv run pytest apps/ctr-service --cov=ctr_service --cov-report=term-missing` y verificar coverage ≥ 75%. Si < 75%, agregar test al hot-spot `attestation_producer.py` o `producer.py` (shard_of edge cases).

## 3. ADR comment-flags

- [x] 3.1 Identificar el call site exacto de cada ADR deferred:
  - ADR-017 → `apps/classifier-service/src/classifier_service/services/ccd.py` (función que computa CCD por ventana 2 min).
  - ADR-024 → `apps/tutor-service/src/tutor_service/services/governance_client.py` o `tutor_core.py` (cerca del fetch del prompt activo).
  - ADR-026 → `apps/web-student/src/pages/EpisodePage.tsx` (cerca del editor Monaco / chat panel).
- [x] 3.2 Agregar comment-flag formato D3 en cada call site:
  ```python
  # Deferred: ADR-XXX / piloto-2 — <una línea de razón concreta>
  ```
  Para TSX usar `// Deferred: ADR-026 / post-defensa — ...`.
- [x] 3.3 Verificar grep: `rg "^# Deferred: ADR-(017|024)" apps/ packages/` retorna 2 hits Python; `rg "// Deferred: ADR-026" apps/web-student/` retorna 1 hit TSX.

## 4. BUGS-PILOTO.md update

- [x] 4.1 Leer `BUGS-PILOTO.md` actual y localizar GAP-9 (coverage ratchet).
- [x] 4.2 Actualizar con:
  - Coverage post-epic medido (tutor-service: X%, ctr-service: Y%, fecha de medición).
  - Nota: "Fase A cerrada por epic `pre-defense-hardening` 2026-05-04. Fase B (target 85%) requiere effort estimado 6-8h adicionales — agendable post-defensa o piloto-2".
  - Pointer al archive del epic.

## 5. Smoke regression global

- [x] 5.1 Correr `uv run pytest apps packages --ignore=apps/enrollment-service -x 2>&1 | tail -30` y verificar exit 0 + total tests passed.
- [x] 5.2 Correr `uv run ruff check apps/ packages/` (sin --fix) y verificar 0 violations en archivos tocados por la epic.
- [x] 5.3 Documentar el conteo final de tests (X passed) en una nota al pie de GAP-9 o en una nueva entrada `BUGS-PILOTO.md` "Auditoría de regresión post pre-defense-hardening".
