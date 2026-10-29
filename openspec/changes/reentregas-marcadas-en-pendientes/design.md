## Context

Motivación en `proposal.md`. Estado verificado contra `origin/main` (`18bffe9`, 26/10) el 2026-10-28:

| Hecho | Dónde |
|---|---|
| Una entrega por `(tenant, TP, alumno)`; la re-entrega reusa la misma fila | `apps/evaluation-service/src/evaluation_service/models/entregas.py:42-107` |
| `Calificacion` con `UNIQUE(entrega_id)`; `graded_at` = primera, `updated_at` = última re-calificación; nada escribe `deleted_at` | `models/entregas.py:153-190`; `routes/entregas.py:924-935` |
| Calificar: sólo `submitted` → `graded`, 409 si ya hay calificación | `routes/entregas.py:551-611` |
| Re-calificar (PR #124): PATCH in-place, deja `graded` salvo `returned` | `routes/entregas.py:614-722` |
| Devolver: sólo `graded` → `returned` | `routes/entregas.py:751-815` |
| Submit: sólo `draft`/`returned` → `submitted` | `routes/entregas.py:293-322` |
| Listado: filtros `comision_id`, `estado`, `tarea_practica_id`; aislamiento por comisión del docente; cursor por `id` | `routes/entregas.py:149-276` |
| El listado ya trae `nota_final` y `graded_at` por lote (`_notas_metadata`, una consulta `IN` por página) | `routes/entregas.py:898-942`, `_entrega_out_con_tp :945-977` |
| `EntregaOut` ya expone `nota_final`/`graded_at` | `schemas/entrega.py` (`EntregaOut`) |
| Lista docente: chips de estado (server-side), búsqueda por alumno y conteos (client-side sobre lo cargado), "Cargar más"; cola de lote = `filteredEntregas` en `submitted` | `apps/web-teacher/src/views/CorreccionesView.tsx:163-300, :444-500` |
| Aviso de re-entrega **dentro** de la entrega, con un `GET /calificacion` por entrega abierta | `CorreccionesView.tsx:1435-1444, :1987-1990` |
| Tipo `EntregaDocente` del web-teacher sin `nota_final` | `apps/web-teacher/src/lib/api.ts:1808-1830` |
| Change concurrente: marca `reabierto_por_docente` en `ejercicio_estados`; **se limpia en el submit** (su D4) | `openspec/changes/publicar-nota-y-pedir-correccion/design.md` (D2–D4, D8) |

## Goals / Non-Goals

**Goals:**
- Ver en la lista, sin abrir, qué pendientes son re-entregas y con qué nota venían.
- Filtrarlas, y que la corrección por lote pueda hacerse sólo sobre ellas.
- Una sola definición de "re-entrega", en el backend, testeada.

**Non-Goals:**
- Número de intento (D3).
- Marcar re-entregas en `graded`/`returned` ("ya fue re-entregada alguna vez"): no es lo que se pidió (pendientes) y no es derivable sin historia.
- Reordenar la lista (el orden por `id` sostiene el cursor).
- Cambiar el aviso de #124 dentro de la entrega.

## Decisions

### D1 — Re-entrega = `submitted` + calificación vigente, derivado al leer

Las cuatro transiciones (tabla de arriba) hacen que `submitted` con calificación sólo se alcance por `graded → returned → submitted`. No hace falta guardar nada.

| Opción | Veredicto |
|---|---|
| **Derivar al leer** (`estado == "submitted"` y la entrega está en el resultado de `_notas_metadata`) | **Elegida.** Cero migración, cero consultas extra (el lote de calificaciones ya se trae), vale para las re-entregas que ya existen en prod |
| Columna `es_reentrega` / `intentos` con migración | Descartada: duplica un dato derivable y arranca mal para lo existente (D3) |
| Derivar sólo en el frontend (`estado === "submitted" && nota_final != null`) | Descartada como fuente única: la regla quedaría en el cliente, sin test de backend, y el filtro igual necesita SQL (D2). El frontend **lee** `es_reentrega` |

`submitted_at > graded_at` sería una segunda señal, pero es redundante con la máquina de estados y frágil ante relojes; no se usa.

### D2 — Filtro `reentrega` en SQL, no en el cliente

La lista pagina de a 50 con "Cargar más". Un filtro sólo en el cliente mostraría "no hay re-entregas" cuando están en la página 2. Por eso `reentrega=true` agrega a las condiciones `Entrega.estado == "submitted"` y `EXISTS (SELECT 1 FROM calificaciones c WHERE c.entrega_id = entregas.id AND c.deleted_at IS NULL)`; `false`, la negación de esa conjunción. Va **después** del aislamiento por comisión, sin tocarlo. Si viene junto con `estado` distinto de `submitted` y `reentrega=true`, el resultado es vacío (coherente, no error).

En el web-teacher, el toggle "Sólo re-entregas" entra en la `queryKey` (como `estadoFilter`) y reinicia la paginación. Los conteos de los chips siguen siendo sobre lo cargado (como hoy); el toggle muestra su propio conteo de lo cargado.

### D3 — Sin número de intento

No hay de dónde sacarlo: la calificación se edita in-place, `updated_at` sólo dice la última re-calificación, la devolución no deja rastro persistente (los logs `tp_calificada`/`tp_correccion_pedida` son structlog, no tabla consultable). Un contador nuevo (`entregas.intentos`, Alembic en `apps/evaluation-service/alembic/`) sólo contaría desde el deploy: una TP devuelta dos veces antes del deploy diría "2.º intento" siendo el 3.º. Mostrar un número falso es peor que no mostrarlo. Si se quiere, es un change propio.

### D4 — UI: badge al lado del estado, con la nota anterior

En la tarjeta (`CorreccionesView.tsx:479-486`), junto al `Badge` de estado, un segundo `Badge` (`@platform/ui`, variante de aviso) "Re-entrega · antes {nota}". La nota viene en `nota_final` del propio listado (ya está en el JSON; se agrega al tipo `EntregaDocente`). Accesible: el texto es el dato, no sólo color. El toggle va en la barra de filtros, al lado de los chips de estado, con `aria-pressed`. Una línea en `helpContent.correcciones` (sin tildes).

### D5 — Compatibilidad con `publicar-nota-y-pedir-correccion`

Ese change agrega la marca `reabierto_por_docente` por ejercicio y, en su D4, **la limpia al re-entregar**. Con eso, al momento en que la re-entrega aparece en la lista de pendientes, la marca ya no está y este change no puede decir "Corrección pedida: ej. 2 y 4".

| Opción | Veredicto |
|---|---|
| **A) Mover la limpieza al momento de devolver**: `POST /return` reescribe la marca en **todas** las filas (`true` en las pedidas, `false` en el resto) y el submit ya no la limpia. `ordenes_a_corregir` sólo se consulta en `returned`, así que la marca vieja en `submitted`/`graded` no cambia nada del flujo; el badge "A corregir" del alumno se condiciona a `estado === "returned"` | **Recomendada.** Ajuste chico al otro change (dos líneas de su D4 y un test), y el dato llega a la lista |
| B) No tocar el otro change | La tarjeta muestra sólo "Re-entrega" (el requisito "Ejercicios pedidos" se cumple por su escenario "sin marca"). Cero coordinación, menos información |
| C) Guardar las órdenes pedidas en otro lado (columna/tabla) | Descartada: migración para un dato que ya está en el JSONB |

Este change implementa la lectura de la marca de forma **tolerante**: si está, la muestra; si no, no inventa. Funciona igual con A o con B, y con o sin el otro change aplicado. **Decisión (Neyén, 28/10): A.** `publicar-nota-y-pedir-correccion` (PR #126, commit `448cc21`) ya no limpia la marca en el submit y la reescribe en cada devolución; este change sólo la lee.

Orden de apply: después de `publicar-nota-y-pedir-correccion` (comparte `CorreccionesView.tsx`, `routes/entregas.py` y `schemas/entrega.py`). No depende del PR #122 ni de `descargas-borrador-y-entregado`.

## Tesis: qué NO se toca

- **Cero cambios** en `apps/ctr-service`, `apps/classifier-service`, `packages/contracts`, `ai-native-prompts`, `apps/tutor-service`. No se emiten eventos al CTR; no se agregan logs nuevos.
- El cambio de backend es de **lectura** sobre `academic_main.entregas`/`calificaciones`: no escribe, no migra, no toca la máquina de estados.
- Verificación (tarea 5.1), debe salir **vacío**:

```bash
git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/evaluation-service/alembic
```

## Risks / Trade-offs

- [Algún día se borran calificaciones (soft-delete)] → la definición ya filtra `deleted_at IS NULL`, igual que `_notas_metadata`; una entrega con calificación borrada deja de contar como re-entrega, que es lo coherente.
- [Un estado nuevo en la máquina de entregas rompe la equivalencia de D1] → test que fija las transiciones: si alguien habilita `submitted` con calificación por otro camino, el test de "entrega nueva" lo detecta.
- [Clientes que no conocen el campo] → aditivo, se ignora.
- [Tests negativos que se vacían solos (lección del repo)] → cada `false`/"sin badge"/"no recibe" se prueba rojo forzando la condición.
- [La marca de D5 depende de otro change] → lectura tolerante; documentado.

## Prueba local reproducible (para Neyén, sin escribir código)

1. **Levantar el stack** desde la raíz de `rama desarrollo/` en Git Bash:
   - `DEV_TRUST_HEADERS=true PROMPTS_REPO_PATH="$(cygpath -w "$(pwd)/ai-native-prompts")" bash scripts/dev-start-all.sh`
   - en otra terminal: `pnpm turbo dev`
   - web-student en http://localhost:5175, web-teacher en http://localhost:5174. Alumno de dev `e19354fb-c05a-4535-a0bf-a7d3ea09692d`, tenant `aaaa…`. Si el Postgres 18 de Windows está prendido, frenarlo; si al abrir un episodio da 403, es el tenant `bbbb…` que dejan los smoke.
2. En web-teacher, **dos** TPs de 1 ejercicio publicadas en la comisión del alumno (TP-A y TP-B).
3. Como alumno, entregar las dos.
4. En web-teacher → Correcciones: las dos dicen "Entregada", **ninguna** dice "Re-entrega".
5. Calificar TP-A con 6 y devolverla ("Pedir corrección" si ese change ya está aplicado). Como alumno, re-entregar TP-A.
6. En Correcciones (recargar): TP-A dice "Entregada" **y** "Re-entrega · antes 6", sin abrirla; TP-B sólo "Entregada".
7. Activar "Sólo re-entregas": queda sólo TP-A. "Corregir pendientes" arranca con una sola entrega.
8. Re-calificar TP-A: pasa a "Calificada" y el badge "Re-entrega" desaparece.
9. (Si D5-A quedó aplicado, con una TP de 3 ejercicios) Pedir corrección del 2 → re-entregar → la tarjeta dice "Corrección pedida: ej. 2".
10. **CTR sin cambios**: antes del paso 3 y después del 8, en `ctr_store`: `SELECT event_type, count(*) FROM events GROUP BY 1 ORDER BY 1;` → ningún `event_type` nuevo (los conteos suben por abrir/cerrar episodios, es esperado).
