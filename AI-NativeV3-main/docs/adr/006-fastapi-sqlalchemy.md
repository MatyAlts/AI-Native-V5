# ADR-006 — FastAPI + SQLAlchemy 2.0 en backend

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: stack, python, backend

## Contexto y problema

Definir el stack canónico de backend Python del monorepo. La elección debe cubrir:

- API REST performante con OpenAPI auto-generado.
- ORM con tipado correcto y soporte de async.
- Ecosistema grande y documentación en español (para onboarding de colaboradores).
- Validación de schemas de entrada/salida robusta.

## Opciones consideradas

### Opción A — FastAPI + SQLAlchemy 2.0
Combinación más popular del ecosistema Python async. Pydantic v2 integrado.

### Opción B — Litestar + SQLAlchemy 2.0
Técnicamente superior en varios aspectos (DX mejor, async-first nativo, mejor rendimiento en benchmarks), pero ecosistema más chico.

### Opción C — FastAPI + Tortoise ORM
Tortoise más ergonómico para CRUDs simples, pero penaliza cuando la complejidad crece (queries analíticas, raw SQL, joins complejos).

### Opción D — Django Ninja + Django ORM
Django es maduro y tiene admin panel free. Pero el modelo sync de Django (aún con ASGI) no encaja con workers del CTR que necesitan concurrency alta, y el ORM es menos expresivo para queries complejas.

## Decisión

**Opción A — FastAPI + SQLAlchemy 2.0.**

Stack específico:
- **FastAPI** >= 0.115 para HTTP + OpenAPI.
- **SQLAlchemy 2.0** con async engine (asyncpg driver) y `Mapped[]` typing.
- **Pydantic v2** para schemas de request/response.
- **Alembic** para migraciones.
- **uv** como package manager + workspace manager.
- **Ruff** para lint/format. **mypy strict** para typing.
- **pytest + pytest-asyncio + hypothesis + testcontainers** para tests.

## Consecuencias

### Positivas
- Ecosistema enorme: docs en español, cursos, Stack Overflow.
- FastAPI + Pydantic + SQLAlchemy 2.0 se integran naturalmente.
- Candidatos de contratación lo conocen.
- OpenAPI gratuito; web-admin puede auto-generar cliente.

### Negativas
- Litestar sería técnicamente mejor (mejor DX en algunos puntos, async puro). Costo de oportunidad aceptado.
- Django admin no existe; si hace falta, se implementa custom.

### Neutras
- Decisión reversible con esfuerzo medio: las capas de servicio y repo son relativamente portables.

## Referencias

- [FastAPI docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- `pyproject.toml` (root + por servicio)
