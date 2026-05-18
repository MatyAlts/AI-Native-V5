# Formato del CSV de importación de inscripciones

El endpoint `POST /api/v1/imports` acepta CSV con las siguientes columnas
obligatorias:

| Columna | Tipo | Descripción |
|---|---|---|
| `student_pseudonym` | UUID | Pseudónimo del estudiante (resuelto previamente contra identity-service) |
| `comision_codigo` | string | Código de la comisión destino (ej. `Algebra-II-A`) |
| `rol` | enum | `regular`, `oyente` o `reinscripcion` |
| `fecha_inscripcion` | ISO 8601 date | `YYYY-MM-DD` |

## Ejemplo

```csv
student_pseudonym,comision_codigo,rol,fecha_inscripcion
00000000-0000-0000-0000-000000000001,Algebra-II-A,regular,2026-03-01
00000000-0000-0000-0000-000000000002,Algebra-II-A,regular,2026-03-01
00000000-0000-0000-0000-000000000003,Programacion-II-B,reinscripcion,2026-03-03
```

## Reglas

- El encoding debe ser UTF-8.
- El separador es coma (`,`). TSV con tabs también se acepta.
- Los IDs de UUIDs deben tener formato estándar 8-4-4-4-12 hexa.
- `comision_codigo` debe existir en el tenant (se valida en commit).
- `student_pseudonym` debe existir en `academic_main.inscripciones` (se valida en commit). Nota: la identidad real vive en Keycloak; ver `packages/platform-ops/privacy.py` para des-identificación.
- El CSV máximo es de 10 MB. Para archivos más grandes, dividir.

## Flujo

1. **Upload** `POST /api/v1/imports` con `file=@inscriptos.csv`.
   - Valida formato + columnas + tipos por fila.
   - Devuelve `{import_id, status: "validated" | "failed", errors: [...], preview: [...]}`.
2. **Preview** — el operador ve errores por fila en el frontend.
3. **Commit** `POST /api/v1/imports/{import_id}/commit`.
   - Aplica todas las inscripciones en una transacción.
   - Si cualquier fila falla en commit, toda la importación se revierte.

## Errores comunes

- **`Faltan columnas`** — header incompleto. Revisar que estén las 4 columnas.
- **`no es UUID válido`** — revisar el pseudónimo; a veces el SIS de origen entrega legajos en vez de pseudónimos y hay que resolverlos primero.
- **`formato inválido`** — la fecha no es ISO. Excel a veces exporta `DD/MM/YYYY`, hay que convertirlo.
