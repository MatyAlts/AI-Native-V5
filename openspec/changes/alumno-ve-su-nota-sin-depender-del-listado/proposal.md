# El alumno ve su nota sin depender del listado de TPs

## El problema

Un docente preguntó:

> *"en el socrático, si se archiva un TP, ¿se deja de ver? ¿Y los TP entregados se
> pueden corregir igual? Porque si se archiva el alumno deja de ver el TP, en
> consiguiente deja de ver la nota y corrección."*

Tenía razón en las tres cosas, y se verificó cada una contra el código:

| Pregunta | Hoy | ¿Está bien? |
|---|---|---|
| ¿El alumno deja de ver el TP archivado? | **Sí** | Sí — el TP cerró |
| ¿El docente puede corregir lo entregado? | **Sí** | Sí |
| ¿El alumno pierde la nota y la corrección? | **Sí, en la práctica** | **No.** Es su registro académico |

El tercero es un defecto, no una decisión. Y **archivar no se puede deshacer**:
`publish()` sólo acepta TPs en `draft`, así que `archived → published` no existe en
la API.

## Lo que NO es el problema

**No es de permisos.** El endpoint que sirve la calificación **no mira el estado
de la TP**: `GET /api/v1/entregas/{id}/calificacion` sólo chequea dueño de la
entrega y visibilidad de comisión. `list_entregas` tampoco filtra por estado de
TP — una entrega de una TP archivada **sí aparece** ahí. El gate que sí mira el
estado (`_assert_tp_viva`) es de escritura y no se aplica a los GET.

El problema es que **no hay cómo llegar**. La nota se alcanza sólo desde
`TareaSelector`, cuyas zonas iteran sobre `AvailableTarea[]`, que viene de
`listAvailableTareas` con `estado: "published"` fijo. Una TP archivada nunca
entra a ninguna zona, ni siquiera si tiene una entrega calificada.

**El dato está, el permiso está, la puerta no.**

## Lo que descubrió la verificación, y por eso esto no es sólo frontend

La idea original era una pantalla nueva y nada más. No alcanza:

`listMisEntregas` devuelve `Entrega[]` con `id, tarea_practica_id, estado,
submitted_at, …` — **sin título ni código de la TP**. Para resolver el título
habría que pedir `GET /api/v1/tareas-practicas/{id}`, y ese endpoint
**devuelve 404 a un alumno cuando la TP no está `published`**
(`academic-service/routes/tareas_practicas.py:119-120`).

Una lista de notas sobre UUIDs no sirve de nada. Así que hace falta un cambio de
backend, y se eligió el más chico de los tres que había.

## La decisión: desnormalizar, no relajar permisos

Se evaluaron tres caminos y se eligió el primero:

**(A) Mandar `tarea_codigo` y `tarea_titulo` en la respuesta de entregas.**
Elegido. Cero cambios de control de acceso, y para un registro histórico es más
correcto: muestra el título **con el que el alumno entregó**, no el actual.

**(B) Dejar que el alumno lea la TP de la que entregó** — relajar el chequeo de
`academic-service` con una excepción por propiedad ("tengo una entrega acá").
Conceptualmente más correcto y le devolvería también el enunciado, pero es un
cambio en el control de acceso: bajo la gobernanza del proyecto eso se analiza y
no se escribe sin aprobación humana explícita. Descartado para esta change, no
para siempre.

**(C) Un endpoint nuevo** tipo "mis TPs con entrega, incluyendo archivadas". Más
superficie para el mismo resultado.

**Lo que (A) no resuelve, y queda dicho:** el alumno recupera la **nota y la
corrección**, no el **enunciado** del TP archivado. Si eso hace falta, es (B) y
es otra change con su propio gate.

## Qué se construye

**Backend** — `EntregaOut` (`evaluation-service/schemas/entrega.py:108`) suma dos
campos opcionales con el código y el título de su TP. Opcionales, no obligatorios:
las entregas de una TP borrada no tienen de dónde sacarlos, y un campo obligatorio
convertiría ese caso en un 500.

**Frontend** — ruta nueva `apps/web-student/src/routes/mis-notas.tsx`, al lado de
`progreso.tsx` y `reflexiones.tsx` que ya existen. Lista las entregas del alumno
en la comisión y linkea a `GradeDetailView`, que **se reusa sin tocarlo**: sólo
necesita `{id, estado}` de la entrega, y los dos ya vienen.

## El shape, confirmado antes de escribir código

```
  Mis notas                              Prog 1 — A-Mañana

  CON NOTA
  ─────────────────────────────────────────────────────────
  TP2   Agenda de turnos                            8.50
        entregado 12/09 · corregido 19/09              →
  TP1   Primeros programas                           7.00
        entregado 28/08 · corregido 03/09              →

  SIN CORREGIR TODAVIA
  ─────────────────────────────────────────────────────────
  TP3   Listas y diccionarios                           —
        entregado 26/09 · el docente no lo corrigio aun
```

Cuatro decisiones con su porqué, contra las anti-referencias de `PRODUCT.md`:

1. **Lista, no grilla de cards.** La anti-referencia 3 banea las grillas de cards
   idénticas. Para un registro histórico una lista se lee como un acta.
2. **Dos grupos, no tabs ni filtros.** Tabs para dos estados es navegación tipo
   Moodle, que es la anti-referencia 1.
3. **La nota alineada a la derecha, tabular — NO el template de número grande con
   label chico**, que está baneado explícitamente.
4. **Los estados se dicen con palabras**: *"el docente no lo corrigió aún"*, no un
   spinner ni un "pendiente". Principio 5 de `PRODUCT.md`.

**Densidad:** más liviana que las vistas del docente. El principio 3 pide densidad
académica pero está escrito para docentes; esta pantalla la usa un alumno de
primer año que quiere ver una nota. Una línea por entrega más una de metadata.
Decisión tomada a propósito y confirmada.

## Dos limitaciones que la pantalla tiene que admitir, no tapar

**Es por comisión, no global.** `listMisEntregas` toma `comision_id`. Si el alumno
cursa dos materias son dos pantallas, y por eso el encabezado nombra la comisión.

**El endpoint trae 50 como máximo**, hardcodeado en `api.ts`. Para un cuatrimestre
alcanza holgado, pero al llegar a 50 la pantalla estaría mintiendo por omisión.
Tiene que avisarlo en vez de truncar en silencio — principio 5 otra vez.

## Lo que NO entra

**El aviso al archivar.** Que `archive()` cuente las entregas sin calificar y avise
antes de confirmar. Es barato y vale, pero toca otro servicio y otro frontend
(web-teacher), y el daño que esta change arregla es el del alumno que ya perdió el
acceso. Change aparte.

**Que archivar se pueda deshacer.** Hoy es terminal. Es una pregunta de producto
—¿debería poder deshacerse?— y no una técnica.

**El enunciado del TP archivado.** Ver el camino (B) arriba.

## Cómo se sabe que funcionó

- Un alumno con una entrega calificada de una TP **archivada** la ve en "Mis
  notas", con su código y título, y puede abrir la corrección.
- Una entrega `submitted` sin calificar aparece en el segundo grupo, y dice con
  palabras que el docente no la corrigió.
- Un alumno **sin ninguna entrega** ve un estado vacío que le dice qué hacer, no
  "no hay nada".
- La pantalla se ve bien con 3 entregas y con 40, y avisa al tocar el límite de 50.
- Los dos campos nuevos son opcionales: una entrega cuya TP no se puede resolver
  **no rompe el endpoint**.
- Todo control de la pantalla es operable por teclado con foco visible.
