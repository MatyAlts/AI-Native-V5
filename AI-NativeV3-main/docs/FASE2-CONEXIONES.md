# Fase 2 — Auditoría de las conexiones (los bordes del grafo)

> **Artefacto Fase 2** del [`PLAN-AUDITORIA-RESILIENCIA.md`](PLAN-AUDITORIA-RESILIENCIA.md).
> Auditoría 2026-06-04. "Acá vivieron los 4 bugs del incidente." Foco: auth servicio-a-
> servicio + qué pasa en cada borde cuando el destino falla.

---

## 🚨 HALLAZGO #1 (CRÍTICO) — Bypass de autenticación en prod

**`DEV_TRUST_HEADERS=true` en el env de `api-gateway` (prod).**

Lógica confirmada en `middleware/jwt_auth.py:99-113`: si una request **no trae token JWT**
pero trae los headers `X-User-Id` / `X-Tenant-Id` / `X-User-Roles`, el gateway **los confía
sin validar nada** y los reenvía a los backends como identidad autoritativa.

**Impacto:** cualquiera, sin loguearse, puede impersonar a cualquier usuario y rol (incl.
`superadmin`) y cualquier tenant, solo seteando 3 headers. Lectura/escritura de datos de
cualquier alumno/comisión. Para una tesis basada en integridad y auditabilidad, es el peor
agujero posible.

**Por qué NO se apaga con un flag:** los frontends hoy NO mandan el Bearer real de Clerk (su
nginx inyecta los X-* en su lugar). `DEV_TRUST_HEADERS=false` sin antes cablear el Bearer
end-to-end rompe el login de todos. El validador de Clerk YA está configurado
(`JWT_ISSUER`, `JWKS_URI`) — falta usarlo y dejar de inyectar headers.

**Estado:** anotado, NO arreglado (requiere wiring de auth real + decisión).

### ✅ CONFIRMADO con probe (2026-06-04, read-only)

`GET https://ai-native-tutor-socratico-academic-service.3xzl86.easypanel.host/api/v1/comisiones/mis`
con headers **forjados** (`X-User-Roles: superadmin`, user/tenant inventados, **sin token**)
→ **200** `{"data":[],"meta":{...}}`. El backend, **expuesto en su dominio público**, aceptó
una identidad inventada y procesó la request como superadmin. Vacío solo porque el tenant era
falso; con un tenant real devuelve datos reales.

**Conclusión:** el alcance es mayor que el flag del gateway. Los backends están en internet y
confían en X-* sin auth → **se puede saltar el gateway por completo**. Severidad: CRÍTICA.
Mitigación real: (a) no exponer los backends públicamente (solo el gateway), (b) auth real
JWT end-to-end, (c) que los servicios internos no confíen en X-* sin verificar origen.

---

## Modelo de auth servicio-a-servicio

- **Borde externo:** frontend → `api-gateway`. *Debería* exigir JWT de Clerk; hoy confía en
  headers (ver Hallazgo #1).
- **Bordes internos:** cada servicio llama al siguiente **directo** (red Docker, sin pasar
  por el gateway) y manda `X-User-Id` + `X-Tenant-Id` + `X-User-Roles`. El destino **confía
  en esos headers sin re-verificar** (modelo declarado: api-gateway es el único source of
  identidad). Ej: `tutor → academic` manda `X-User-Roles: tutor_service` (service account).
- **Riesgo compuesto:** si los backends están expuestos por dominio público (lo están, cada
  uno tiene su `*.easypanel.host`), y confían en X-* sin auth, se puede saltar el gateway
  entero. *(A verificar con un probe.)*

---

## Matriz de bordes: qué pasa cuando el destino falla

| Origen → Destino | Tipo | Auth | Si destino 4xx/5xx | Si destino down/timeout |
|---|---|---|---|---|
| frontend → api-gateway | HTTP | ⚠️ X-* (sin JWT) | propaga status | — (es el SPOF) |
| api-gateway → cualquier backend | HTTP proxy | reenvía X-* | **propaga transparente** | **500 opaco** (sin 502/retry) 🚩 |
| tutor → academic (validar tarea) | HTTP | `tutor_service` | **propaga** (no abre episodio) | propaga |
| tutor → academic (ejercicio/comisión) | HTTP | `tutor_service` | **fail-soft** (degrada) | fail-soft |
| tutor → governance (prompt) | HTTP | service | **propaga** (no abre episodio) 🚩 | propaga |
| tutor → ai-gateway (LLM) | HTTP | service | propaga (corta el turno) | propaga |
| tutor → ctr (evento primario) | HTTP/Redis | service | **propaga** (integridad > disp.) | propaga |
| tutor → ctr (adverso/overuse) | HTTP/Redis | service | **fail-soft** | fail-soft |
| tutor → redis (sesión) | TCP | password | — | **gaierror → 500** (bug del incidente) |
| classifier → ctr | HTTP | service | *a verificar* | *a verificar* |
| content → ai-gateway | HTTP | service | *a verificar* | *a verificar* |
| ctr-workers → redis stream | XREADGROUP | — | — | **lee pero no persiste** (incidente) |
| ctr-workers → postgres | asyncpg | — | **no ACK → pending** (81 huérfanos) | — |

---

## "Explota cuando debería degradar"

1. **api-gateway → backend caído = 500 opaco.** No distingue "el backend respondió 500" de
   "el backend no existe". Sin 502/503 claro, sin retry, sin circuit breaker. El frontend ve
   un error genérico.
2. **tutor → governance caído = no se abre ningún episodio.** Es hard-dep. Mitigante:
   governance es nodo hoja (raro que caiga), pero no degrada con mensaje claro.

---

## Los 4 bugs del incidente (2026-06-04), mapeados a bordes

1. **tutor → academic:** faltaba permiso Casbin `tutor_service:tarea_practica:read` + el gate
   de comisión no eximía al service account → **403**. → ✅ corregido (exención `SERVICE_ROLES`).
2. **tutor → redis:** `gaierror` (DNS tras restart) → **500**. → reconexión frágil (Fase 3).
3. **ctr-workers → redis stream:** leía pero no persistía. → Fase 3/4.
4. **ctr-workers → postgres:** sin ACK → **81 eventos pending huérfanos**. → Fase 4 (XAUTOCLAIM).

> Patrón: **3 de 4 vivieron en un borde, no dentro de un servicio.** Confirma la tesis del
> plan: el problema está en las conexiones.

---

## Pendiente para cerrar Fase 2

- Probe: ¿los backends responden a X-* forjados desde su dominio público? (confirma el alcance del bypass).
- Verificar failure handling de `classifier → ctr` y `content → ai-gateway`.
- Confirmar si el SSE del chat se buffea en el proxy (heredado de Fase 1).
