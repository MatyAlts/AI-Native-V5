# Cómo contribuir

## Proceso

1. Leer [`CLAUDE.md`](./CLAUDE.md) (verdades operativas + invariantes) y los STATE de fases en [`docs/phases/`](./docs/phases/) para entender en qué fase estamos y qué tipo de cambios son apropiados.
2. Mirar los [ADRs](./docs/adr/) antes de hacer cambios arquitectónicos significativos. La doc por servicio vive en [`docs/servicios/`](./docs/servicios/).
3. Crear branch desde `main` con prefijo `feat/`, `fix/`, `docs/`, `refactor/` o `chore/`.
4. Abrir PR hacia `main` con descripción clara del cambio.
5. Esperar a que CI pase y pedir review.

## Convenciones de código

### Python

- Python 3.12
- `uv` para gestión de dependencias
- `ruff` para lint y format
- `mypy --strict` para tipos
- `pytest` con `pytest-asyncio`
- Nombres en inglés para APIs públicas, español aceptable en UI o docs
- Docstrings en español breves

### TypeScript

- TypeScript estricto con `noUncheckedIndexedAccess`
- `biome` para lint y format
- React 19 con hooks
- Naming: `PascalCase` para componentes, `camelCase` para funciones y variables

### Commits

Convención [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(academic): agregar endpoint de búsqueda de comisiones
fix(ctr): reparar race condition en worker partition 3
docs(adr): añadir ADR-016 sobre migración a Kafka
test(contracts): cobertura completa de hashing
```

## Cambios arquitectónicos

Cualquier cambio que afecte decisiones existentes requiere un nuevo ADR:

1. Copiar `docs/adr/_template.md` a `docs/adr/NNN-titulo-descriptivo.md`.
2. Completar. Si reemplaza un ADR existente, marcar el anterior como
   "Superseded by ADR-NNN".
3. Abrir PR con el cambio de código + el nuevo ADR juntos.

## Tests obligatorios

PRs deben incluir:

- **Feature nueva**: tests unitarios + integration si toca red/DB.
- **Bug fix**: test que reproduce el bug antes del fix.
- **Nueva tabla con `tenant_id`**: test que verifica la policy RLS
  (se corre automáticamente en CI con `make check-rls`).
- **Cambio de contrato de evento**: actualización en `packages/contracts`
  Python + TypeScript, tests de serialización.

## Coverage

- Global ≥70% hasta F3, ≥80% desde F3.
- Servicios del plano pedagógico (tutor, ctr, classifier): ≥85% desde F3.

## Preguntas / dudas

Abrir un issue con label `question` antes de empezar un cambio grande.
Mejor preguntar que reescribir.
