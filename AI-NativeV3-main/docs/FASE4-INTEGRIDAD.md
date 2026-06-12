# Fase 4 — Integridad de datos (tesis-crítico)

> **Artefacto Fase 4** del [`PLAN-AUDITORIA-RESILIENCIA.md`](PLAN-AUDITORIA-RESILIENCIA.md).
> Auditoría 2026-06-04, sobre la DB de prod (`ctr_store`), read-only.

## Resultado: la cadena CTR está ÍNTEGRA ✅

Verificación **independiente del servicio** (SQL puro sobre la tabla `events`, sin confiar en
el endpoint `/verify`): chequeo de encadenamiento `prev_chain_hash[n] == chain_hash[n-1]` por
episodio + genesis en `seq=0`.

| Chequeo | Resultado |
|---|---|
| Episodios | 42 (39 closed, 3 open) |
| Eventos totales (tabla `events`) | 567 |
| `seq=0` arranca del GENESIS (`'0'×64`) | **42 / 42 ✅** |
| Eslabones (`seq>0`) bien encadenados | **525 / 525 ✅** |
| **Eslabones rotos** | **0** 🎯 |
| `integrity_compromised = true` | **0** |
| Huérfanos en la DB (`events_count` vs tabla) | **0** (567 == 567) |

**Interpretación:** la propiedad append-only se sostiene en prod. Cero eslabones rotos
implica además **cero eventos perdidos en el medio**: un evento faltante rompería el
encadenamiento (el `prev_chain_hash` del siguiente no matchearía), y no hay ninguno.

## Sobre los "81 huérfanos" del incidente

Eran entradas **pending en los streams de Redis** (`ctr.p0..p7`) que no llegaron a Postgres,
NO filas perdidas en la DB. Al momento de esta auditoría, en la DB todo cuadra (567 eventos,
counts consistentes, `dead_letters = 0`). Conclusión: o se reprocesaron, o el estado
transitorio se resolvió. **No hay pérdida de datos visible en la base hoy.**

## Lo que NO se verificó acá (honestidad)

- **Recomputo de `self_hash` desde el payload** (detecta tampering de contenido, no solo de
  estructura). El sistema lo cubre con su propio `integrity_compromised` (= 0) y el endpoint
  `/api/v1/audit/episodes/{id}/verify`; acá verifiqué estructura + encadenamiento.
- **Aislamiento RLS multi-tenant** independiente. Las policies RLS existen (CLAUDE.md, ADR-001)
  y `make check-rls` corre en CI, pero no se re-testeó contra la DB de prod en esta pasada.
  *Nota:* el probe del bypass (Fase 2) con un tenant falso devolvió vacío — consistente con
  RLS filtrando, pero es evidencia débil.
- **Orphans pending en Redis** (los streams `ctr.p0..p7`): Redis no está expuesto, no se midió
  el `XPENDING` actual. Recomendado para Fase 3 (con acceso interno).

## Veredicto Fase 4

🟢 **Sólido.** El núcleo criptográfico que sostiene la tesis (cadena append-only) está intacto
en prod: 42 cadenas, 0 rotas, 0 comprometidas, 0 pérdidas. Esto es lo que el comité necesita
ver, y hoy se cumple.
