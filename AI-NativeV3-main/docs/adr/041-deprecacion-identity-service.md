# ADR-041 — Deprecacion de `identity-service`

- **Status**: Accepted
- **Fecha**: 2026-05-07
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: backend, infraestructura, deprecation, simplificacion
- **Cierra**: deuda silenciosa documentada en CLAUDE.md "Brechas conocidas" — `identity-service` en `/health`-only by-design pero todavia activo en workspace + helm.
- **Coordinado con**: [ADR-030](./030-deprecate-enrollment-service.md) (mismo patron de deprecation: `enrollment-service`).

## Contexto y problema

`identity-service` (puerto 8001) fue agregado en F0 con la responsabilidad declarada *"Wrapper de la Admin API de Keycloak + gestion de pseudonimizacion"*. La verificacion empirica al cierre de v1.0 confirmo que:

1. **Cero endpoints de negocio**. El servicio expone solo `/health`, `/ready`, `/live` ([apps/identity-service/src/identity_service/main.py:42](../../apps/identity-service/src/identity_service/main.py#L42) — un solo `app.include_router(health.router)`). El root `GET /` devuelve metadata estatica del servicio.
2. **Ningun consumer en repo**. `rg "from identity_service|import identity_service" apps/ packages/` devuelve solo el codigo del propio servicio (`main.py`, `config.py`, `observability.py`, `routes/health.py`, `tests/test_health.py`). NO esta importado por ningun otro app/package.
3. **Auth ya esta resuelta en otro lado**. El `api-gateway` es el unico source of truth de identidad (CLAUDE.md "Propiedades criticas"): emite JWT RS256 e inyecta `X-Tenant-Id`, `X-User-Id`, `X-User-Email`, `X-User-Roles` autoritativamente. Casbin descentralizado en cada servicio (cargado de `academic_main.casbin_rules`) hace authorization. Pseudonimizacion vive en `packages/platform-ops/src/platform_ops/privacy.py` rotando `student_pseudonym` en `academic_main.episodes`.
4. **Patron identico a `enrollment-service` (ADR-030)**: servicio del workspace con responsabilidad declarada que nunca aterrizo, sin frontend ni roadmap concreto. Mantenerlo activo es deuda silenciosa segun la regla operativa de CLAUDE.md *"la diferencia entre deuda silenciosa y decision informada es el ADR redactado."*

**Diferencia con `evaluation-service`** (que tambien es esqueleto): `evaluation-service` ya no es esqueleto — el epic `tp-entregas-correccion` aterrizo 8 endpoints REST (`/api/v1/entregas` CRUD + lifecycle + `/calificacion`). `identity-service` no tiene equivalente — su responsabilidad declarada (wrapper Keycloak Admin API) nunca emergio como necesidad real porque el flow JWT-via-gateway lo hace innecesario.

## Drivers de la decision

- **Coherencia arquitectonica**: la auth no necesita un servicio dedicado en este modelo (gateway-as-auth-source). Tener un puerto reservado para una responsabilidad ya cubierta es ruido en el catalogo.
- **Reducir superficie de deploy y dev loop**: 1 menos pod en helm staging/prod, 1 menos uvicorn que arrancar a mano en dev (per CLAUDE.md *"make dev no levanta los servicios Python"*), 1 menos entry en `make status` y `make check-health` que distrae sin agregar senial.
- **Honestidad del catalogo de servicios**: bajar de 12 a 11 servicios activos refleja la verdad operacional. CLAUDE.md ya marcaba *"el numerador honesto es 10/12 (12 activos menos `evaluation-service` esqueleto y `identity-service` que es by-design /health only)"* — con este ADR pasa a ser 11/11 sin asteriscos.
- **Reversibilidad preservada**: el codigo se preserva en disco con README de deprecation; si emerge un caso de uso real (ej. wrapper REST para Keycloak Admin API que el gateway no cubra, gestion de cuentas server-side, scim provisioning), el servicio se reactiva siguiendo los pasos del README.

## Opciones consideradas

### A — Deprecar y preservar codigo en disco (ELEGIDA)

Sacar `identity-service` del workspace, helm, tabla de puertos de CLAUDE.md. Preservar el codigo con README de deprecation para trazabilidad y revival rapido si emerge necesidad.

### B — Borrar el directorio entero del repo

Eliminar `apps/identity-service/` por completo.

**Descartada porque**:
- Pierde git history del esfuerzo F0 + el patron estructural (FastAPI + uvicorn + structlog + observability) que serviria como esqueleto si se decide revivir.
- Costo cero de mantenimiento mantenerlo dormido (no se levanta, no se sincroniza, no se testea fuera del workspace) vs. costo no-trivial de recrear si emerge un caso de uso real.
- CLAUDE.md prescribe principio de reversibilidad. Borrar es irreversible (modulo `git revert`); deprecar es reversible mecanicamente.

### C — Mantener el servicio activo "por si acaso"

Dejar `identity-service` en el workspace y helm como esta hoy.

**Descartada porque**:
- Es exactamente la deuda silenciosa que CLAUDE.md identifica. Si el caso de uso "por si acaso" no esta articulado en un ADR ni roadmap, el servicio no agrega senial — agrega ruido.
- Confunde a futuros desarrolladores ("¿que hace este servicio?") y a docentes leyendo el catalogo de servicios en defensa.
- Inflación del numerador de "X servicios activos" sin sustancia tecnica detras.

## Decision

**Opcion A**. `identity-service` queda deprecated. Codigo preservado en disco. Sacado de workspace + helm + CLAUDE.md.

### Cambios concretos

| Archivo | Cambio |
|---|---|
| [`pyproject.toml`](../../pyproject.toml) | `"apps/identity-service"` removido de `[tool.uv.workspace].members` con comentario explicativo apuntando a este ADR. NO se sincroniza con `uv sync`, NO aparece en `pytest apps/*/tests/`. |
| [`apps/identity-service/README.md`](../../apps/identity-service/README.md) | Reemplazado/creado con nota de deprecation completa, instrucciones de revival, y referencia a ADR-041. |
| [`infrastructure/helm/platform/values.yaml`](../../infrastructure/helm/platform/values.yaml) | Bloque `identity-service:` removido. **No se deploya** en staging/prod. |
| [`CLAUDE.md`](../../CLAUDE.md) | Tabla de puertos marca el puerto 8001 como deprecated (~~tachado~~). Mencion en plano academico-operacional removida. Caveat reemplazado por linea breve referenciando este ADR. Total de servicios activos pasa de "12" a "11". |

### Lo que NO se cambio

- `apps/identity-service/` directorio fisico — preservado completo per Opcion A.
- Tests del servicio en `apps/identity-service/tests/test_health.py` — preservados pero NO se ejecutan en CI (sacado del workspace).
- Routes del api-gateway — `identity-service` nunca estuvo en el `ROUTE_MAP` (CLAUDE.md ya lo declaraba *"NO esta en el ROUTE_MAP, sin endpoints"*), entonces no hay nada que remover de `apps/api-gateway/src/api_gateway/routes/proxy.py`.

## Consecuencias

### Positivas

- **1 menos servicio Python que mantener**: el monorepo pasa de 12 a 11 servicios activos. CLAUDE.md ya no necesita el caveat *"identity-service es /health only por by-design"*.
- **Menos confusion en defensa**: el comite doctoral ve un catalogo de servicios donde cada entrada tiene endpoints reales y responsabilidad activa.
- **Coherencia con ADR-030**: el patron es identico — servicio sin endpoints, codigo preservado en disco, sacado del workspace + helm. Reutilizar el mismo template baja el costo de comprension del ADR.
- **`make check-health` mas cuerdo**: ya no hay un servicio que respondiendo 200 sin nada utilizable detras.

### Negativas / trade-offs

- **Si UNSL pide flow institucional que requiera Keycloak Admin API server-side** (ej. scim provisioning, password reset administrativo, gestion de roles batch que el gateway no cubra), va a haber que revivir el servicio o agregar la funcionalidad al api-gateway. **Mitigacion**: el README documenta los 5 pasos exactos de revival, y el directorio sigue versionado.
- **Cosmetica residual**: si quedaran settings dormidas (`identity_service_url` o similar) en algun config, no afectan runtime — son inertes. (Verificacion `rg "identity[-_]service|identity_service_url" apps/api-gateway/` devolvio vacio post-cambios, confirmando que no hay este tipo de residuo.)

### Neutras

- El directorio `apps/identity-service/` sigue versionado pero "muerto". Linters/typecheckers fuera del workspace lo ignoran.
- El test `test_health.py` no se ejecuta en CI post-ADR-041. Si se restaura el servicio, los tests vuelven automaticamente al re-incluir el path en el workspace.

## Posible revival futuro (instrucciones operativas)

Si emerge un caso de uso real (ej. wrapper REST para Keycloak Admin API que el gateway no cubra, gestion de cuentas server-side), el revival es reversible siguiendo el README del servicio:

1. Re-incluir `"apps/identity-service"` en `pyproject.toml` `[tool.uv.workspace].members`.
2. Re-agregar el bloque `identity-service:` (port 8001) en `infrastructure/helm/platform/values.yaml`.
3. Implementar los endpoints en `apps/identity-service/src/identity_service/routes/`.
4. Agregar entrada al `ROUTE_MAP` del `api-gateway` (`apps/api-gateway/src/api_gateway/routes/proxy.py`) si los endpoints deben ser publicos para frontends.
5. Marcar este ADR como `Superseded por ADR-XXX` y redactar el ADR de revival explicando el caso de uso nuevo.

## Referencias

- [ADR-030](./030-deprecate-enrollment-service.md) — deprecacion de `enrollment-service` (mismo patron, antecedente directo).
- README del directorio: [`apps/identity-service/README.md`](../../apps/identity-service/README.md).
- CLAUDE.md "Propiedades criticas" — *"api-gateway es el UNICO source of truth de identidad"*.
- CLAUDE.md "Estado actual de implementacion" — caveat previo sobre identity-service `/health`-only by-design.
