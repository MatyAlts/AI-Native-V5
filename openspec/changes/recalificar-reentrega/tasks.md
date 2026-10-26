## 1. Re-entrega: PATCH y aviso (TDD, web-teacher)

- [x] 1.1 Test + implementación: entrega `submitted` con calificación previa califica con PATCH a `/calificacion` (no POST) y termina `graded`; verificar con `pnpm test` en CorreccionesView.test.tsx
- [x] 1.2 Test + implementación: entrega `submitted` sin calificación sigue usando POST `/calificar` (regresión)
- [x] 1.3 Test + implementación: si el POST responde 409, reintenta con PATCH y no muestra el error
- [x] 1.4 Test + implementación: la re-entrega muestra "Re-entrega — nota anterior: X" y el form arranca vacío; sin calificación previa no hay aviso

## 2. Verificación

- [x] 2.1 Refactor y suite web-teacher completa, typecheck y biome sin regresiones respecto del baseline
