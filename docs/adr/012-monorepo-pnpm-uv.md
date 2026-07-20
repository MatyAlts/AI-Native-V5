# ADR-012 — Monorepo con pnpm workspaces + uv workspaces

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: stack, operación

## Contexto y problema

El proyecto consta de 12 servicios Python + 3 aplicaciones frontend + 5 packages compartidos. Necesitamos decidir cómo organizarlos: un repo por servicio (polyrepo) o uno solo con todos (monorepo).

## Opciones consideradas

### Opción A — Polyrepo (un repo por servicio/app)
Cada servicio/app con su propio repositorio, CI/CD, versionado, releases.

### Opción B — Monorepo con herramientas de workspaces
Un único repo con múltiples paquetes. pnpm + uv + turborepo orquestan.

## Decisión

**Opción B — Monorepo.**

Organización:

```
platform/
├── apps/         # 12 servicios Python + 3 frontends React
├── packages/     # 5 librerías compartidas
├── infrastructure/
├── docs/
└── scripts/
```

Herramientas:

- **pnpm workspaces** (definido en `pnpm-workspace.yaml`) para el lado Node/React.
- **uv workspaces** (definido en el `[tool.uv.workspace]` del `pyproject.toml` root) para Python.
- **Turborepo** para pipeline incremental del lado frontend.
- **Makefile** como interfaz unificada de comandos (`make dev`, `make test`, `make migrate`).

## Consecuencias

### Positivas
- Cambios atómicos cross-servicio en un solo PR (ej. cambiar contrato de evento + consumidor + emisor).
- Reutilización trivial de packages (`@platform/contracts`, `@platform/ui`).
- Una sola configuración de CI.
- Onboarding más rápido: un clone, un setup.
- Búsquedas cross-proyecto naturales (grep, IDE).

### Negativas
- CI requiere detección de afectados (turborepo lo resuelve para frontend; para Python usamos `uv run --project <app>`).
- Permisos fine-grained por carpeta son más difíciles que por repo.
- Git history se vuelve más denso; `git log` largo.

### Neutras
- Migración futura a polyrepo es posible con `git subtree split`.
- Herramientas modernas (pnpm, uv, turborepo) manejan monorepos grandes sin problema.

## Referencias

- `pnpm-workspace.yaml`
- `pyproject.toml` (root, sección `[tool.uv.workspace]`)
- `turbo.json`
- `Makefile`
