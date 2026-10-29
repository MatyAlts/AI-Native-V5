## Why

En la lista de Correcciones del docente (`apps/web-teacher/src/views/CorreccionesView.tsx:444-500`), una **re-entrega** (el alumno re-envió una TP que el docente le había devuelto) se ve igual que una entrega nueva: mismo badge "Entregada", misma tarjeta. Recién al abrirla aparece el aviso "Re-entrega — nota anterior: X" (PR #124, `CorreccionesView.tsx:1435-1444` y `:1987-1990`), que se calcula con un sondeo `GET /calificacion` **por entrega abierta**. El docente no puede priorizar ni seguir las re-entregas sin abrirlas una por una.

Pedido de la lista de mejoras (mejora 5): *"distinguir las reentregas en la lista de trabajos pendientes para facilitar su identificación y seguimiento"*.

El dato **ya existe** y es derivable sin migración: la calificación es única por entrega y sobrevive a la devolución (`models/entregas.py:153-160`, `UNIQUE(entrega_id)`; nada borra calificaciones), calificar exige `submitted` y la deja `graded`, devolver exige `graded`, y el submit sólo acepta `draft`/`returned` (`routes/entregas.py:293-322, :551-611, :751-815`). Por lo tanto: **una entrega `submitted` que ya tiene calificación es, necesariamente, una re-entrega.** Y el listado ya consulta `calificaciones` en lote para cada página (`_notas_metadata`, `routes/entregas.py:898-942`).

## What Changes

- **Backend (evaluation-service), sin migración**: `EntregaOut` suma `es_reentrega: bool`, derivado en el armado de la respuesta (`estado == "submitted"` y existe calificación no borrada), sin consultas nuevas. `GET /entregas` acepta un filtro opcional `reentrega=true|false`, resuelto en SQL para que la paginación por cursor no mienta.
- **web-teacher, lista de Correcciones**: badge **"Re-entrega"** junto al estado en la tarjeta, con la nota anterior ("Re-entrega · antes 6"). Un chip/toggle **"Sólo re-entregas"** en la barra de filtros, que se combina con el filtro de estado y la búsqueda; la cola de corrección por lote ("Corregir pendientes") hereda el filtro porque ya se deriva de la lista filtrada.
- **Compatibilidad con `publicar-nota-y-pedir-correccion`** (change concurrente): si la marca `reabierto_por_docente` llega viva a la re-entrega, la tarjeta suma "Corrección pedida: ej. 2 y 4" (o "todos"). Hoy ese change limpia la marca en el submit; ver design D5 y la pregunta abierta.
- **Fuera de alcance**: número de intento ("2.º intento"). No es derivable: no hay historia de devoluciones ni contador; contar desde ahora necesita una columna nueva con migración y daría números falsos para las re-entregas que ya existen. Ver design D3.

## Capabilities

### New Capabilities
- (ninguna)

### Modified Capabilities
- `correccion-grading`: el listado de entregas informa y filtra re-entregas; la vista docente las distingue en la lista de pendientes.

## Impact

- **Backend** (`apps/evaluation-service`): `schemas/entrega.py` (`EntregaOut.es_reentrega`), `routes/entregas.py` (`_entrega_out_con_tp`, `list_entregas` con `reentrega`). Sin Alembic. Campo aditivo: los clientes que no lo conocen lo ignoran.
- **web-teacher**: `lib/api.ts` (`EntregaDocente.es_reentrega`, `nota_final`, `listEntregas` con `reentrega`), `views/CorreccionesView.tsx` (badge + toggle), `utils/helpContent.tsx` (una línea). El aviso dentro de la entrega (#124) queda como está.
- **Choque de archivo** con `publicar-nota-y-pedir-correccion` (`CorreccionesView.tsx`, `routes/entregas.py`, `schemas/entrega.py`): zonas distintas; se aplica después y se rebasea.
- **Tesis**: nada. Los datos salen de `academic_main.entregas`/`calificaciones`; ningún evento CTR nuevo. Ver design "Tesis: qué NO se toca".
- **Gobernanza**: MEDIO (lógica de negocio de entregas, endpoint compartido). TDD estricto.
