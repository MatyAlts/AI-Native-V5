## Context

Ver proposal.md. El backend ya soporta el caso: `PATCH /api/v1/entregas/{id}/calificacion` (`recalificar_entrega`) actualiza la misma fila, normaliza el estado a `graded` (salvo `returned`) y registra `tp_recalificada`. En el front, `GradingFormView` calcula `yaCalificada` sólo por estado (`graded`/`returned`) y la carga de la calificación (`getCalificacion`) sólo corre si `yaCalificada`. `recalificarEntrega` (PATCH inline) y `handleRecalificar` ya existen.

## Goals / Non-Goals

**Goals:** que una re-entrega sea calificable sin 409; que el tutor sepa que es re-entrega y vea la nota anterior.
**Non-Goals:** tocar backend/DB/CTR/app del estudiante; marcar re-entregas en la lista; mover `recalificarEntrega` a `api.ts`.

## Decisions

1. **Detección por sondeo, no por estado.** El tipo `Entrega` no trae la calificación, así que para entregas `submitted` se hace un `getCalificacion` best-effort (404 -> `null`; error -> se ignora). `esReentrega = submitted && calificacionPrevia`. Se valida `nota_final` numérico por si llega otro shape. Alternativa descartada: agregar un flag al listado del backend (toca backend y contrato por algo que se resuelve con un GET).
2. **Form vacío, nota anterior como referencia (no prefill).** Se está corrigiendo una versión NUEVA del código; prellenar nota/feedback viejos invita a guardarlos sin releer y mezcla lo viejo con lo nuevo. Se muestra un aviso con la nota anterior y el feedback anterior en texto de referencia.
3. **Un solo botón "Calificar".** `handleCalificar` elige el camino: re-entrega -> PATCH; si no, POST. Si el POST devuelve 409 (carrera/dato viejo: el sondeo aún no volvió o falló) se reintenta con PATCH. La validación y la salida (refetch + `onUpdated`) se comparten.
4. **Frontend-only.** El PATCH ya cubre el caso (documentado en su docstring); no hay hueco real en el backend.

## Risks / Trade-offs

- [Sondeo falla y no hay aviso de re-entrega] -> el fallback 409 -> PATCH sigue evitando el error; sólo se pierde el aviso.
- [El PATCH pisa `graded_by`/nota] -> es lo buscado en una recalificación; queda log `tp_recalificada` con la nota anterior.
- [Un GET extra por cada entrega `submitted` abierta] -> aceptable; 404 liviano.

## Hallazgo (no se corrige acá)

La lista y la cola en lote (`pendientesQueue`) cuentan toda `submitted` como pendiente, re-entregas incluidas: sensato, ya que hay que corregirlas. No se distinguen visualmente de las primeras entregas; el aviso aparece recién al abrirlas. En modo cola, el aviso también se muestra. Marcar re-entregas en la lista requeriría un dato del backend: queda como mejora.
