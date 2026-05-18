# ADR-037 — Governance UI: solo lectura, sin tabla nueva

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez
- **Tags**: ui, gobernanza, read-only
- **Epic**: ai-native-completion-and-byok / Sec 12

## Contexto y problema

El admin institucional necesita **visibilidad cross-cohort** de los
intentos adversos detectados (ADR-019, RN-129). Hoy hay un endpoint por
cohorte (`/cohort/{id}/adversarial-events`) — falta agregacion a nivel
facultad/materia/periodo.

Hay que decidir:
1. Tabla nueva `governance_events` (con `is_reviewed`, `reviewed_by_user_id`,
   workflow de marcado) o reusar el CTR via analytics?
2. Workflow de "marcar como revisado" o solo lectura?

## Drivers de la decisión

- **CTR es source of truth**: los eventos `intento_adverso_detectado` ya
  estan en el CTR. Crear una tabla espejo agrega cardinalidad sin valor.
- **Pre-defensa, simplicidad > completitud**: un workflow de revision
  agrega complejidad operativa (UI, permisos, queries de "pending"). El
  admin del piloto puede listar eventos sin marcarlos como "revisados".
- **Cross-cohort scaling**: a nivel facultad pueden ser miles de eventos
  por periodo. Pagination cursor-based es necesaria.

## Decisión

1. **Sin tabla nueva**. La pagina consume:
   - `GET /api/v1/analytics/cohort/{id}/adversarial-events` extendido con
     query params opcionales `facultad_id`, `materia_id`, `periodo_id`
     (no breaking — todos opcionales).
   - `GET /api/v1/analytics/governance/events` (endpoint nuevo de
     agregacion cross-cohort con paginacion cursor-based).
2. **Solo lectura**. Sin workflow "marcar revisado" — deferido a piloto-2
   con tabla `governance_event_reviews` separada del CTR.

## Consecuencias

### Positivas

- Cero impacto en el invariante "CTR append-only" (ADR-010).
- Pagina simple de implementar (filtros + tabla + CSV export).
- Casbin ya tiene roles `superadmin`/`docente_admin` — sin policies nuevas.

### Negativas / trade-offs

- Sin estado de "revisado" persistido. El admin re-visita los mismos
  eventos. Aceptable pre-defensa — la cantidad real de eventos del piloto
  es manejable.
- Cross-cohort aggregation requiere JOIN en el data-source layer:
  `Event.episode_id → Episode.comision_id → Comision.materia_id →
  Materia.facultad_id`. Hoy solo `comision_id` esta resuelto; los joins
  facultad/materia/periodo son **TODO en `RealLongitudinalDataSource`** —
  la implementacion piloto-1 acepta el filtro pero no aplica JOINs aun
  (degrada a "todos los eventos del tenant").

## Frontend

Pagina `apps/web-admin/src/pages/GovernanceEventsPage.tsx`:
- Filtros cascade facultad → materia → período (cada uno UUID input por
  ahora; piloto-2 puede agregar dropdowns con fetch).
- Pagination cursor-based (`cursor_next` del response).
- Export CSV con headers ASCII (cp1252-safe en Windows).
- HelpButton + PageContainer obligatorio.

## Referencias

- Spec: `openspec/changes/ai-native-completion-and-byok/specs/governance-ui-admin/spec.md`
- Endpoint: `apps/analytics-service/.../routes/analytics.py::get_governance_events`
- Pagina: `apps/web-admin/src/pages/GovernanceEventsPage.tsx`
- ADR-019 — Guardrails Fase A (origen de los eventos `intento_adverso_detectado`).
