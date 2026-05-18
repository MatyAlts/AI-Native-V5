# Descripción

<!-- Qué cambia este PR y por qué. Link al issue si corresponde. -->

## Tipo

- [ ] Feature nueva
- [ ] Bug fix
- [ ] Refactor
- [ ] Docs
- [ ] Chore / infra
- [ ] Cambio arquitectónico (requiere ADR nuevo)

## Checklist

- [ ] Tests unitarios agregados o actualizados
- [ ] Tests de integración agregados si aplica (DB, red, bus)
- [ ] Si toca una tabla nueva con `tenant_id`, verifica que pasa `make check-rls`
- [ ] Lint + typecheck limpio (`make lint && make typecheck`)
- [ ] Coverage no baja
- [ ] Documentación actualizada (README, onboarding, ADR)
- [ ] Conventional Commits en el título

## Cambios que rompen (breaking)

<!-- ¿Hay algo que requiera atención especial al desplegar? Migraciones
no compatibles hacia atrás, cambios de contrato de eventos, remoción
de endpoints. -->

## Screenshots / demos

<!-- Si aplica (cambios UI). -->
