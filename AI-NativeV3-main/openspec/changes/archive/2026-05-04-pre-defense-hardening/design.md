## Context

Auditoría 2026-05-04 identificó 3 gaps cuantitativos:

1. **`tutor-service` cobertura ~60%** vs target 85%. Hot-spots: `clients.py` 41%, `content_client.py` 0%, `governance_client.py` 0%, `routes/episodes.py` 48%.
2. **`ctr-service` cobertura ~63%** vs target 85%. Hot-spots: `partition_worker.py` 23%, `routes/events.py` 35%, `db/session.py` 53%.
3. **No hay test directo del invariante de chain integrity** (la propiedad central de la tesis). Existen tests de hashing y de reproducibilidad del classifier, pero ninguno emite N eventos, mutea uno, y verifica detección.

Adicionalmente, 3 ADRs declarados como `Status: deferred` (017, 024, 026) no tienen comment-flag en el sitio del código — solo el doc del ADR. Para defensa doctoral, la trazabilidad "deuda intencional con criterio de revisita" tiene que ser visible al auditor que lee el código, no solo al que lee el catálogo de ADRs.

**Stakeholders**: doctorando (defensa cerca), comité doctoral (puede objetar coverage o trazabilidad), auditor externo del CTR (tiene que ver evidencia testeable de tampering detection).

**Constraints**:
- NO agregar features nuevos. NO cambiar contratos. NO tocar lógica de producción excepto comments.
- Los tests deben ser unit (sin requerir Postgres/Redis reales) — consistente con el resto del proyecto.
- Coverage targets son piso, no techo: si llegamos más arriba, mejor.
- `make test` debe seguir verde post-epic, sin regresiones.

## Goals / Non-Goals

**Goals:**
- `tutor-service` coverage ≥ 75% (delta ~+15 pts).
- `ctr-service` coverage ≥ 75% (delta ~+12 pts).
- Test directo de chain integrity tampering detection (3 escenarios mínimos).
- Comment-flags uniformes para ADRs 017/024/026 deferred en el sitio del código.
- `BUGS-PILOTO.md` GAP-9 actualizado con números post-epic.
- `make test` verde end-to-end.

**Non-Goals:**
- Cobertura ≥ 85% (target documentado en CLAUDE.md). Cierra el gap pero no llega al target final — Fase B en GAP-9.
- Tests de frontends (web-admin/teacher/student).
- Endpoints nuevos (CII evolution longitudinal, etc.).
- Refactor del `ctr-service` para usar helper compartido de health checks.
- Ratchet del coverage gate global (60% → 80%) en CI.
- Cobertura de servicios secundarios (governance, analytics, content).

## Decisions

### D1 — Tests unit con mocks, NO integration

**Decisión**: todos los tests nuevos son unit con mocks. Para `test_chain_integrity.py`, mockear el SQLAlchemy session y construir `Event` Pydantic en memoria.

**Rationale**: consistente con el resto del proyecto (`test_pipeline_reproducibility.py`, `test_event_labeler.py`, etc. son todos unit con mocks). Mantener la suite rápida (<30s total) y sin dep de Docker. Integration tests existen separados (`tests/integration/test_*.py`) y se corren con `make test-rls` cuando hace falta DB real.

**Alternativas descartadas**:
- Integration con testcontainers: ya existe `test_ctr_end_to_end.py` con Postgres real, no agrego más allá. El invariante de chain integrity es lógica pura sobre los hashes, no requiere DB.
- Hybrid: complica sin necesidad.

### D2 — Mutation testing manual en `test_chain_integrity`

**Decisión**: el test construye una secuencia de N=5 eventos en memoria, calcula sus hashes con `compute_self_hash` + `compute_chain_hash` reales (no mockeados — son funciones puras de `packages/contracts/.../ctr/hashing.py`), y luego mutea manualmente un byte del `self_hash` o `chain_hash` de un evento intermedio. Verifica que `verify_episode_chain()` (helper público existente o equivalente) marca el episodio como compromised.

**Rationale**: la propiedad que se está afirmando es "si cualquier byte de un hash está mutado, la cadena se detecta rota". Mutation testing manual es la forma correcta — frameworks como mutmut son overkill para 1 propiedad.

**Alternativas descartadas**:
- Property-based con hypothesis: agrega dep, complicación. La propiedad se cubre con 3 casos explícitos.
- Solo testear `compute_self_hash` byte-exact: ya está cubierto en `packages/contracts/tests/test_hashing.py`. Lo que falta es el end-to-end del invariante.

### D3 — Format uniforme para comment-flags de ADRs deferred

**Decisión**: comment de 2-3 líneas en formato:
```python
# Deferred: ADR-017 / piloto-2 — CCD opera por ventana temporal 2 min;
# embeddings semánticos quedan como agenda Cap 20 (operacionalización
# conservadora declarada).
```

**Rationale**: 
- `Deferred:` prefijo grep-able (`rg "^# Deferred"` lista toda la deuda intencional).
- ADR-XXX + nombre del milestone (piloto-2 / post-defensa / Cap 20) — auditor sabe el criterio de revisita.
- 1 línea breve de razón — contexto sin sobre-documentar.

**Alternativas descartadas**:
- TODO genérico: sin trazabilidad al ADR.
- Decorator/marker en código: cambia lógica, scope creep.

### D4 — Hot-spots prioritizados por leverage

**Decisión**: priorizar archivos con baja cobertura Y alta superficie:

| Archivo | Cov actual | Esperado post-epic | Razón |
|---|---|---|---|
| `tutor-service/.../content_client.py` | 0% | ~80% | Hot-spot mayor, código RAG glue. |
| `tutor-service/.../governance_client.py` | 0% | ~80% | Sin tests, fetch del prompt — crítico para abrir episodios. |
| `tutor-service/.../clients.py` | 41% | ~75% | academic + ai-gateway clients, error handling. |
| `tutor-service/.../routes/episodes.py` | 48% | ~70% | Endpoints SSE + abandoned. |
| `ctr-service/.../partition_worker.py` | 23% | ~70% | 8 partitions sharding, complejidad alta. |
| `ctr-service/.../routes/events.py` | 35% | ~70% | Write + verify endpoints. |

NO se prioriza `db/session.py` 53% porque la lógica es trivial (engine factory + session context), test value bajo.

**Rationale**: ROI máximo. Tocar todos los archivos al 90% sería effort 3× con marginal value bajo.

## Risks / Trade-offs

**[Riesgo 1] — Mocks de httpx + redis se vuelven frágiles** cuando los clients evolucionan.
→ Mitigación: usar `AsyncMock` con `side_effect`, no asserts sobre internals. Solo verificar shape de input/output del client, no la mecánica de httpx.

**[Riesgo 2] — `test_chain_integrity` depende del helper `verify_episode_chain()` y ese helper puede no existir como API pública del worker**.
→ Mitigación: si el worker tiene la lógica inline, extraer a una función pura `verify_chain(events: list[Event]) -> ChainStatus` reutilizable, y llamarla desde el test Y desde el worker. Refactor mínimo (~10 LOC). Si emerge complejidad, fallback: testear el worker entero con mock del DB session.

**[Riesgo 3] — Coverage delta menor a target +12-15 pts**.
→ Mitigación: medir tras cada PR de tests. Si tras los archivos prioritarios estamos en +8 pts, agregar tests del 2do hot-spot (db/session, schemas).

**[Riesgo 4] — Comment-flags en código rompen typecheck o lint** (no debería, son comentarios) o se borran sin querer en futuros refactors.
→ Mitigación: prefijo `# Deferred:` grep-able permite verificación periódica (`rg "^# Deferred:" apps/ packages/ | wc -l` debería dar exactamente 3 post-epic).

**[Trade-off] — Coverage no alcanza el target final 85%**: el blindaje es 75%, no 85%.
→ Aceptado: 75% cierra la objeción cuantitativa primaria. Llegar a 85% requiere ~3-4× el effort por ROI marginal. Documentado en GAP-9 como Fase B.

## Migration Plan

**Fase 1 — Tests tutor-service** (1 PR, ~2h):
1. Escribir `test_content_client.py`, `test_governance_client.py`, `test_clients.py`, `test_episodes_route.py` con mocks.
2. Correr `uv run pytest apps/tutor-service --cov=tutor_service --cov-report=term-missing` y verificar ≥ 75%.
3. Commit + verify CI.

**Fase 2 — Tests ctr-service** (1 PR, ~2h):
1. Escribir `test_partition_worker.py`, `test_events_route.py`, `test_chain_integrity.py` con mocks.
2. Correr `uv run pytest apps/ctr-service --cov=ctr_service --cov-report=term-missing` y verificar ≥ 75%.
3. Commit + verify CI.

**Fase 3 — ADR comment-flags + BUGS-PILOTO update** (1 PR, ~30min):
1. Agregar 3 comment-flags formato D3.
2. Actualizar `BUGS-PILOTO.md` GAP-9 con coverage post-epic.
3. Verificar `rg "^# Deferred: ADR-(017|024|026)" -- apps/ packages/` retorna ≥ 3 hits.

**Fase 4 — Smoke global** (~30min):
1. `uv run pytest apps packages --ignore=apps/enrollment-service -x` → todo verde.
2. Documentar conteo final en `BUGS-PILOTO.md`.

**Rollback**: cada PR independiente. Tests fallidos → revert del PR específico, sin impacto en lógica de producción (los tests no tocan código de prod salvo los 3 comments de Fase 3).

## Open Questions

- **¿Extraer `verify_chain()` a función pura del worker?** Depende de cómo está estructurado `integrity_checker.py` hoy. Decisión tomada al implementar Fase 2 — si el helper ya existe internamente, exponerlo; si no, refactor mínimo.
- **¿Subir a 80% en lugar de 75%?** Si Fase 1+2 llegan naturalmente a 78-80% sin esfuerzo extra, dejarlo. No bajar del piso 75%.
