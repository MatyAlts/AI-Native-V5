# ADR-034 — test_cases como JSONB en `tareas_practicas`

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez
- **Tags**: datos, jsonb, schema
- **Epic**: ai-native-completion-and-byok / Sec 9

## Contexto y problema

Cada TareaPractica puede tener N test cases (pythonicos, con tipo
`stdin_stdout` o `pytest_assert`, peso, flag publico/hidden). Hay dos
patrones razonables para almacenarlos:

1. **JSONB** en una columna nueva de `tareas_practicas` (y de
   `tareas_practicas_templates` para que el versionado los clone).
2. **Tabla separada** `tarea_practica_test_cases` con FK a la TP.

## Drivers de la decisión

- **Volumen esperado**: <20 tests por TP es lo tipico (probablemente <10 en
  promedio). No hay queries cross-TP por test.
- **Versionado de TP**: ADR-016 declara que una nueva version clona la
  metadata de la padre. JSONB hace esto trivial (`SELECT test_cases FROM ...`).
  Tabla separada requiere INSERT batch al clonar y FK chains.
- **Templates**: `TareaPracticaTemplate` auto-instancia TPs en cada comision
  con sus test_cases. Si fuera tabla separada, el auto-instance produciria
  N filas por test * M comisiones — multiplicando inserts.
- **Queryability cross-TP**: el unico use case es "listar todos los tests
  de una TP" — JSONB lo cubre con `SELECT test_cases`.

## Decisión

**Columna JSONB** `test_cases` en `tareas_practicas` y
`tareas_practicas_templates` con default `'[]'::jsonb` y `NOT NULL`.

## Consecuencias

### Positivas

- Versionado de TP clona los tests trivialmente.
- Templates auto-instancian sin INSERT batch.
- Schema simple: el bulk-import acepta `test_cases` como JSON stringified
  en una columna del CSV.

### Negativas / trade-offs

- Si una TP empieza a tener >50 tests o si el frontend necesita queries
  cross-TP por test_id (ej. "que TPs usan este patron de test"), conviene
  migrar a tabla separada — **threshold para revisar**.
- El JSONB no tiene CHECK constraint sobre la shape de cada elemento. La
  validacion vive en el schema Pydantic (`TareaPracticaCreate.test_cases:
  list[dict[str, Any]]`) y en el endpoint de bulk-import.

## Shape de cada elemento

```json
{
  "id": "uuid",
  "name": "string",
  "type": "stdin_stdout" | "pytest_assert",
  "code": "string",
  "expected": "string",
  "is_public": true | false,
  "weight": 1
}
```

`is_public=true` => visible al alumno. `is_public=false` => filtrado por el
endpoint `GET /tareas-practicas/{id}/test-cases?include_hidden=false`.

## Referencias

- Migracion: `apps/academic-service/alembic/versions/20260504_0001_add_test_cases_and_created_via_ai.py`
- ADR-033 — Sandbox Pyodide-only (consumidor de tests publicos).
- ADR-016 — TareaPracticaTemplate (versionado de TPs).
