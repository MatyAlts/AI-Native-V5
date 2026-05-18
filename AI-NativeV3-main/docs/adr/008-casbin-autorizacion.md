# ADR-008 — Casbin para autorización fine-grained

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: seguridad, autorización

## Contexto y problema

Keycloak (ADR-002) provee autenticación y roles base (`superadmin`, `docente_admin`, `docente`, `estudiante`), pero RBAC puro es insuficiente para nuestra matriz de permisos:

- Un usuario es "docente" pero solo en **ciertas comisiones**.
- Un `docente_admin` de UNSL no puede gestionar nada de UNCuyo aunque ambos tengan el mismo rol nominal (esto lo cubre RLS, pero necesitamos también impedirlo a nivel de API antes de llegar a la base).
- Algunos permisos son **condicionales**: "puede editar una rúbrica si le pertenece y el período está abierto".

Necesitamos un engine de autorización que combine RBAC (rol) con ABAC (atributos del recurso y contexto).

## Opciones consideradas

### Opción A — Casbin
Engine de autorización mature con modelo declarativo. Soporta RBAC, ABAC, RBAC con dominios (multi-tenant). Policies en archivo o DB.

### Opción B — Oso
Similar. DSL más moderno. Adopción menor.

### Opción C — Open Policy Agent (OPA)
Estándar industrial para políticas. Rego como lenguaje. Overkill para nuestra escala; requiere operar un servicio adicional o embeberlo.

### Opción D — Lógica inline en endpoints
Simple pero explota con la matriz completa (4 roles × 17 recursos × ~5 acciones × condiciones = cientos de if-else duplicados).

## Decisión

**Opción A — Casbin con modelo RBAC-con-dominios + ABAC.**

Modelo:

```conf
[request_definition]
r = sub, dom, obj, act

[policy_definition]
p = sub, dom, obj, act

[role_definition]
g = _, _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub, r.dom) && keyMatch(r.obj, p.obj) && r.act == p.act
```

Donde:
- `sub` = usuario
- `dom` = tenant (universidad)
- `obj` = recurso (`comision:*`, `rubrica:123`, etc.)
- `act` = acción (`read`, `create`, `update`, `delete`)

**Policies en PostgreSQL** (tabla `casbin_rules`) con cache en-memoria + invalidación por eventos. Esto permite modificar policies en runtime para casos puntuales (ej. `docente_admin` otorgando acceso excepcional por un semestre) sin redeploy.

**Enforcement** vía decorator en todos los endpoints:

```python
@router.post("/comisiones")
@require_permission("comision", "create")
async def create_comision(...): ...
```

## Consecuencias

### Positivas
- Matriz de permisos declarativa, testeable contra batería completa.
- Separación entre "qué roles existen" (Keycloak) y "qué pueden hacer" (Casbin).
- Policies como datos: modificables en caliente para casos excepcionales.
- Tests exhaustivos en CI: cada celda de la matriz (rol × recurso × acción) tiene un caso.

### Negativas
- Casbin tiene documentación mayormente en chino/inglés; recursos en español escasos.
- El modelo RBAC-con-dominios es menos común; requiere cuidado al diseñar policies.
- Performance: con >5000 policies puede degradarse. Mitigamos con cache + invalidación selectiva.

### Neutras
- ABAC con atributos del recurso (ej. `rubrica.periodo.estado == 'abierto'`) no se hace en Casbin sino en la capa de servicio; Casbin autoriza "puede editar rúbricas", el servicio verifica el estado específico.

## Referencias

- [Casbin docs](https://casbin.org/docs/overview)
- `apps/api-gateway/src/api_gateway/auth/` (implementación del decorator)
- Matriz completa en `docs/architecture.md` sección 6.2
