# Tareas

## 0. Red de seguridad

- [x] Correr y anotar el baseline exacto, con el **exit code real** (no un pipe —
      `pytest | tail` devuelve el código de `tail` y un rojo pasa como verde):
      `uv run pytest apps/evaluation-service -q` y, en `apps/web-student`,
      `pnpm vitest run`.
- [x] Si algo falla ya, **no lo arregles**: anotalo como pre-existente.

## 1. Backend — dos campos nuevos en `EntregaOut`

`apps/evaluation-service/src/evaluation_service/schemas/entrega.py:108`.

- [x] RED primero: un test que pida una entrega y afirme que la respuesta trae el
      código y el título de su TP. Tiene que fallar antes de tocar el schema.
- [x] `tarea_codigo: str | None` y `tarea_titulo: str | None`. **Opcionales, no
      obligatorios**: una entrega cuya TP no se pueda resolver no puede tumbar el
      endpoint con un 500. Un campo obligatorio convierte un dato faltante en una
      caída.
- [x] Poblarlos en los endpoints que devuelven entregas al alumno — como mínimo
      `list_entregas` y `GET /{entrega_id}`.
- [x] **CUIDADO CON EL N+1.** `list_entregas` devuelve hasta 50 filas. Si cada una
      dispara su propia consulta por la TP, son 51 queries. Resolvelo con **una**
      consulta para todas las TPs del lote (un `IN`), o con un join. Y dejá dicho
      en el código cuál elegiste y por qué.
- [x] **Las tablas viven en `academic_main`, los modelos en `evaluation-service`**
      (ver `CLAUDE.md`, "Ownership cruzado entregas/calificaciones"). `entregas` y
      `tareas_practicas` están en la MISMA base, así que un join es posible. Pero
      **verificá** que el modelo de `TareaPractica` sea alcanzable desde
      evaluation-service antes de asumirlo; si no lo es, resolvelo con una consulta
      aparte y el `IN`, no inventando un import cruzado.
- [x] **No toques RLS ni el filtro por rol.** `list_entregas` ya restringe
      `student_pseudonym == user.id` para no-docentes. Esta change **no cambia
      quién ve qué**: agrega dos campos a filas que el alumno ya podía leer.
- [x] TRIANGULA: una entrega cuya TP existe (trae los dos campos) y una cuya TP no
      se puede resolver (los dos en `None`, y el endpoint responde 200).

## 2. Frontend — la ruta nueva

`apps/web-student/src/routes/mis-notas.tsx`. File-based routing de TanStack: el
plugin regenera `routeTree.gen.ts` solo, **no lo edites a mano**.

- [x] Lista las entregas de la comisión con `listMisEntregas`.
- [x] **Dos grupos**: las que tienen nota (`graded`/`returned`) y las que no.
      Nada de tabs ni filtros — la anti-referencia 1 de `PRODUCT.md` es Moodle.
- [x] **Lista, no grilla de cards.** La anti-referencia 3 banea las grillas de
      cards idénticas.
- [x] La nota **alineada a la derecha, tabular**. **NO** el template de número
      grande con label chico: está baneado explícitamente.
- [x] Al hacer click, montar `GradeDetailView` con la entrega. **No lo
      modifiques**: sólo necesita `{id, estado}` y los dos ya vienen.
- [x] Ordenadas por fecha, lo más reciente arriba.

## 3. Los estados, que es donde esto se gana o se pierde

El principio 5 de `PRODUCT.md` es explícito: *"NO 'coming soon', NO spinners
eternos, NO mensajes vagos. La honestidad ES un asset académico."*

- [x] **Entrega sin calificar**: dice con palabras que el docente no la corrigió
      todavía. No un "pendiente" pelado, no un spinner.
- [x] **Vacío**: el alumno no entregó nada nunca. El estado vacío **enseña la
      interfaz** (adónde ir a entregar), no dice "no hay nada". La referencia del
      register `product` lo pide así.
- [x] **Cargando**: skeleton, no un spinner en el medio del contenido. También de
      la referencia del register.
- [x] **Error** de red o del endpoint: se dice. No una lista vacía, que es
      indistinguible de "no entregaste nada" — ese es el modo de falla a evitar.
- [x] **El límite de 50**: `listMisEntregas` pide `limit=50` hardcodeado. Al llegar
      a 50, **avisar** que puede haber más en vez de truncar en silencio. Una
      pantalla que miente por omisión es peor que una que admite su límite.

## 4. Accesibilidad — es piso, no extra

`PRODUCT.md` fija **WCAG 2.1 AA** como mínimo (ley 26.653) y navegación por
teclado completa en flujos críticos.

- [x] Cada fila es operable por teclado, con **foco visible**.
- [x] La nota no se comunica **sólo** por color.
- [x] Verificalo con un test, no de ojo.

## 5. Responsive

- [x] Funciona a **320px** sin scroll horizontal. En una fila con código, título,
      fecha y nota, eso obliga a decidir qué se apila y qué se corta — decidilo, no
      lo dejes al wrap del navegador.
- [x] Varios alumnos reportaron que la plataforma se usa en **netbooks**. No es
      una pantalla ancha.

## 6. Lo que NO se toca

- [x] `GradeDetailView` — se reusa tal cual.
- [x] `TareaSelector` y sus zonas. **Esta change no cambia el listado de TPs**: lo
      que hace es dejar de depender de él.
- [x] El filtro `estado: "published"` de `listAvailableTareas`, ni el chequeo de
      `academic-service` que devuelve 404 por TP no publicada. Relajar eso era el
      camino (B) del proposal y se descartó a propósito.
- [x] `archive()` y el aviso de entregas sin corregir. Change aparte.
- [x] Nada del tutor ni de sus prompts.

## 7. Verificación antes de declarar terminado

Esto se chequea en este orden, y **con el exit code real**:

- [x] `uv run ruff format --check` y `uv run ruff check` sobre
      `apps/evaluation-service`.
- [x] En `apps/web-student`: `pnpm run lint` (es biome) y
      `pnpm exec tsc --noEmit -p .`.
- [x] Las dos suites.

**Por qué este orden y por qué está escrito**: en los dos PRs anteriores de esta
sesión se entregó con el linter sin correr —biome en uno, `ruff format` en el
otro— con los tests y el typecheck en verde. CI tiene jobs de lint **separados**
(`Lint Python`, `Lint frontend`) que rebotan el PR igual.

## Modo TDD estricto

Está activo. Para cada tarea: RED (un test que viste fallar) → GREEN (lo mínimo)
→ TRIANGULATE (segundo caso con otros datos) → REFACTOR (verde después de cada
paso).

**Y verificá cada test nuevo por mutación.** Un test que pasa no prueba que
discrimine. En la change anterior aparecieron **cuatro** aserciones que pasaban
sin medir nada, todas con la misma forma: una subcadena corta buscada en un
documento largo casi siempre está, y por otra razón.

## Informe final

Categorías tipadas, sin promover nada por comodidad: **EVIDENCIA** (comando +
salida + timestamp), **JUICIO** (quién, contra qué, confianza), **SUPUESTO** (lo
que diste por sentado y qué hiciste en lugar de verificarlo).

Para cada mutación: qué rompiste, qué test se puso rojo, y la salida.

Si algo no pudiste hacer, decilo y decí por qué. **No lo dejes invisible** — es el
único estado que el formato no permite.
