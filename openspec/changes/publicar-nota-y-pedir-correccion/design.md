## Context

Motivación en `proposal.md`. Estado verificado contra `origin/main` (`18bffe9`) el 2026-10-27:

| Hecho | Dónde |
|---|---|
| Estados de la entrega: `draft → submitted → graded → returned`, CHECK en la tabla | `apps/evaluation-service/src/evaluation_service/models/entregas.py:46, 103` |
| Calificar: `submitted → graded` | `routes/entregas.py:551-611` |
| Re-calificar (PR #124): PATCH in-place; deja `graded` salvo que esté `returned` | `routes/entregas.py:614-722` (`:704`) |
| Devolver: `graded → returned` + `_reabrir_ejercicios` (TODOS a `completado=false`, `episode_id` intacto) | `routes/entregas.py:751-815`, `:821-846` |
| Submit acepta `draft`/`returned`; exige `completado` en todos y código de todos los `orden` esperados | `routes/entregas.py:293-417` (`:319, :333, :345-368`) |
| `_persistir_artefactos` **borra** los artefactos previos y sella los nuevos + hash del conjunto | `routes/entregas.py:1127-1180` |
| PATCH de ejercicio acepta `draft`/`returned`, cualquier `orden` | `routes/entregas.py:463-548` (`:487`) |
| `GET /calificacion`: el alumno dueño la lee **en cualquier estado** | `routes/entregas.py:725-748`, `_assert_can_read :1270` |
| web-student muestra nota en `graded` | `GradeDetailView.tsx:34`, `ExerciseListView.tsx:445-452`, `TareaSelector.tsx:124, :637`, `MisNotasPage.tsx` (`agruparEntregas`) |
| Lock secuencial: N bloqueado si N-1 no completado | `apps/web-student/src/components/ExerciseListView.tsx:349-353` |
| "Volver a abrir" (alumno): visible si completado y entrega editable | `ExerciseListView.tsx:486`, PATCH `completado:false` (`:212`) |
| Re-entrega: borradores locales + fallback `last_code_snapshot` del `episode_id` del estado | `ExerciseListView.tsx:102-145` (`recuperarArtefactos`), `:312-320` |
| Docente: "Devolver al estudiante" sólo en `graded`, fuera de la cola | `apps/web-teacher/src/views/CorreccionesView.tsx:1572-1583, :2161-2172`; `lib/api.ts:1962` |
| Textos que prometen liberación diferida | `tour/vistas.tsx:329-335`, `utils/helpContent.tsx:654-662`, `onboarding/docenteOnboarding.tsx:131-133` |
| Otros lectores de `returned`: sólo cuentan "corregidas" o permiten corrección IA; ninguno depende de que estén todos reabiertos | `services/correccion_ia.py:85`, `web-teacher/onboarding/estadoDocente.ts:110`, `views/ProgressionView.tsx:118` |
| Moodle / Active-IA: **ningún código del repo lee `returned`** ni llama `/return` (grep sobre `apps/` y `packages/`) | — |

## Goals / Non-Goals

**Goals:**
- El docente puede publicar la nota sin reabrir nada, y pedir corrección de un subconjunto de ejercicios.
- Los ejercicios no reabiertos conservan `completado`, `episode_id` y el código sellado, también tras la re-entrega.
- El lock secuencial no obliga a pasar por ejercicios no reabiertos.
- Las entregas `returned` existentes en producción se comportan exactamente igual que hoy.
- Los textos de ayuda dicen la verdad.

**Non-Goals:**
- Ocultar la nota al alumno hasta "publicar" (ver D1, alternativa B; pregunta abierta).
- Feedback por ejercicio en la devolución (el feedback sigue siendo el de la calificación).
- Que el editor muestre el código entregado al reabrir y que cerrar sin cambios complete: es el change `editor-muestra-codigo-entregado-al-reabrir`.
- Reabrir episodios cerrados (prohibido: ver "Tesis").

## Decisions

### D1 — No hay estado nuevo: "Publicar nota" = calificar

Hoy `graded` **ya es** "nota publicada": el alumno la ve apenas el docente guarda (tabla de arriba). La promesa de "cerrar las notas de toda la comisión y liberarlas después" nunca se cumplió.

| Opción | Qué implica | Veredicto |
|---|---|---|
| **A) `graded` = publicada** (renombrar "Calificar" → "Publicar nota"; "Guardar y siguiente" → "Publicar y siguiente"; corregir los 3 textos) | Cero cambio de modelo, cero migración, cero cambio de lo que ve el alumno hoy | **Elegida.** Alinea los rótulos con lo que el sistema ya hace |
| B) Nota oculta hasta publicar (flag `publicada_at` en `calificaciones` o estado nuevo) | Migración Alembic + backfill de **todas** las `graded`/`returned` existentes a publicadas (si no, a los alumnos se les esconden notas que hoy ven) + gatear 5 lugares (`GET /calificacion`, `_notas_metadata`, `GradeDetailView`, `ExerciseListView`, `TareaSelector`/`MisNotasPage`) + un tercer botón | Descartada para este change. Si Neyén quiere la liberación diferida de verdad, es un change propio (pregunta abierta 1) |

### D2 — "Pedir corrección" = `POST /return` con `ordenes` opcional (backward compatible)

- Body nuevo opcional `ReturnEntregaBody { ordenes: list[int] | None }`.
- **Sin body o `ordenes=None`**: hoy. Se reabren todos. Lo usan clientes viejos y la TP monolítica.
- **Con `ordenes`**: 422 si la lista está vacía, tiene duplicados o algún `orden` no está en `ejercicio_estados`. Para cada `orden` pedido: `completado=False`, `completed_at=None`, `reabierto_por_docente=True`. El resto **no se toca** (deepcopy, mismo cuidado que `_reabrir_ejercicios`).
- En la devolución total (sin body) también se marca `reabierto_por_docente=True` en todos, para que el estado diga lo que pasó.
- Se mantiene el nombre de ruta `/return`. Un endpoint nuevo `/pedir-correccion` duplicaría validaciones de estado y de comisión sin ganar nada, y un `/publish` no hace falta (D1).
- Log de auditoría `tp_correccion_pedida` por **structlog** (como `tp_calificada`, ADR-010: **no** va al CTR), con `ordenes` y `parcial: bool`.

Alternativa descartada: que el frontend llame N veces al PATCH de ejercicio. El docstring de `return_entrega` ya explica por qué devolver tiene que ser atómico.

### D3 — La marca vive en `ejercicio_estados` (JSONB), sin migración

`EjercicioEstadoSchema` suma `reabierto_por_docente: bool = False`. La columna es JSONB, la clave nueva no requiere Alembic; las filas viejas no la tienen y deserializan con `False`.

Una sola función pura define el alcance, usada por submit, PATCH y (espejada) el frontend:

```
ordenes_a_corregir(estado_entrega, estados) ->
  si alguna fila tiene reabierto_por_docente=True  -> esas
  si no                                             -> todas (legacy / devolución total)
```

**Entregas `returned` ya existentes en prod**: no tienen la marca → "todas" → mismo comportamiento que hoy. No se tocan.

### D4 — Re-entrega parcial: el backend conserva lo no reabierto

En `submit_entrega`, cuando la entrega viene de `returned` y la devolución es parcial:

- Los `orden` **no** reabiertos que tienen artefacto sellado se **copian** del artefacto previo (mismo `codigo`, `episode_id`, `ejercicio_id`, `language`; el `sha256` se recalcula y da igual). Si el cliente manda código para esos `orden`, **se ignora** (se loguea). Así sigue andando el cliente actual, que manda todo lo que encuentra.
- Los `faltantes` se calculan sólo sobre los reabiertos (más los no reabiertos sin artefacto previo, caso legacy: ahí se exige al cliente como hoy).
- El chequeo de `incompletos` no cambia: los no reabiertos siguen `completado=True`.
- **La marca `reabierto_por_docente` NO se borra en el submit** (decisión de Neyén, 28/10: la lista del docente tiene que poder mostrar "Corrección pedida: ej. 2 y 4" sobre la re-entrega; ver `reentregas-marcadas-en-pendientes` D5-A). En cambio, `POST /return` la **reescribe en todas las filas**: `true` en las pedidas, `false` en el resto (devolución total: `true` en todas). Así la marca de una devolución anterior no sobrevive a la siguiente. `ordenes_a_corregir` y el 409 de D5 sólo se consultan en `returned`; en el web-student la marca se ignora salvo con `estado === "returned"` (`devolucionParcialVigente`), para que "A corregir" no aparezca sobre una entrega ya re-entregada o calificada.
- `_persistir_artefactos` sigue reemplazando el conjunto entero y re-sellando el hash: el conjunto nuevo = copiados + nuevos.

Por qué en el backend y no en el frontend (`getEntregaArtefacto` + `recuperarArtefactos`): el servidor ya tiene el código sellado; el cliente no tiene que poder alterar lo que el docente no reabrió; y no depende del PR #122. El fallback de `recuperarArtefactos` por `last_code_snapshot` podía mandar algo distinto de lo sellado (es "lo último que el editor alcanzó a reportar").

### D5 — El alumno no toca lo no reabierto

- Backend: en `returned` con devolución parcial, `PATCH /ejercicio/{orden}` sobre un `orden` fuera de `ordenes_a_corregir` → **409** "Tu docente no pidió corregir este ejercicio". Cubre los dos sentidos: des-marcar (perdería el estado) y marcar (pisaría el `episode_id` del intento corregido).
- Frontend: `canReopen` (`ExerciseListView.tsx:486`) suma la condición; badge "A corregir" en los reabiertos por el docente.
- En `draft` nada cambia ("Volver a abrir" sigue como hoy).

### D6 — Lock secuencial: sólo entre pendientes

Función pura nueva `estaBloqueado(orden, estados)` (en `apps/web-student/src/lib/`): un ejercicio **completado** nunca está bloqueado; uno **no completado** está bloqueado si **algún** ejercicio de `orden` menor no está completado.

- Devolución parcial "2 y 4" de 5: el 2 se habilita; el 4 espera al 2; 1/3/5 completados.
- Devolución total (legacy): idéntico a hoy (todos pendientes → sólo el 1).
- `draft` normal (avance secuencial): idéntico a hoy.
- **Único cambio de comportamiento fuera de la devolución**: en `draft`, si el alumno usa "Volver a abrir" sobre el 1 teniendo el 2 completo y el 3 nunca empezado, hoy el 3 queda habilitado (su anterior, el 2, está completo); con la regla nueva espera al 1. Es más consistente con "secuencial" y se testea explícitamente.

### D7 — Interacción con la re-calificación (PR #124)

Re-entrega → `submitted` con la calificación vieja adherida → el docente corrige con el PATCH (`handleCalificar` cae a PATCH ante 409, `CorreccionesView.tsx:1543-1552`) → `graded` → puede volver a "Pedir corrección" con otra lista. El PATCH sobre `returned` sigue sin tocar el estado (`entregas.py:704`). Nada de esto cambia; se agrega un test del ciclo completo (pedir corrección parcial → re-entrega → re-calificar → pedir corrección de nuevo).

### D8 — UI docente

- `CorreccionesView`: el botón "Devolver al estudiante" pasa a **"Pedir corrección"**, abre un modal (`Modal` de `@platform/ui`) con un checkbox por ejercicio (ninguno tildado por defecto; "Confirmar" deshabilitado con cero) y llama `devolverEntrega(id, ordenes, getToken)`.
- En una entrega `returned` se muestra qué ejercicios se pidieron corregir (leyendo la marca; si no hay marca: "todos").
- Rótulos de D1. Textos de ayuda: los tres sitios dejan de decir que la nota se libera al devolver; explican "Publicar nota" (el alumno la ve al guardar) y "Pedir corrección" (opcional, elegís ejercicios).

### Orden de apply

Este change primero: reduce el problema (menos ejercicios reabiertos) y no depende de nada. Después `editor-muestra-codigo-entregado-al-reabrir`, que cubre lo que queda: el ejercicio reabierto que el alumno cierra sin cambios.

## Tesis: qué NO se toca

Restricción del dueño: *"que no modifique en nada a la tesis"*.

- **Cero cambios** en `apps/ctr-service`, `apps/classifier-service`, `packages/contracts`, `ai-native-prompts`, `apps/tutor-service` (prompts, pins, emisión), `LABELER_VERSION`, `classifier_config_hash`.
- **No se reabre ningún episodio cerrado.** Sólo cambia el flag de progreso `completado` en `academic_main.entregas`, como hoy.
- Ni el backend ni el frontend de este change emiten eventos CTR. El log nuevo `tp_correccion_pedida` es structlog (ADR-010).
- Verificación (tarea 7.1), debe salir **vacío**:

```bash
git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service
```

**Matiz de comportamiento (informar a Cortez)**: el instrumento queda igual, pero cambia la población de intentos. Con devolución parcial, los ejercicios no objetados no se rehacen → menos episodios de "segundo intento" por TP devuelta, y el `episode_id` de esos ejercicios en la re-entrega sigue apuntando al primer intento. Cualquier análisis que cuente re-intentos post-devolución tiene que leer el corte temporal de este deploy.

## Risks / Trade-offs

- [El docente quería la liberación diferida que prometía el texto] → D1 la descarta explícitamente y deja la pregunta abierta. Mientras tanto, el texto deja de mentir.
- [Cliente viejo del web-teacher cacheado] → sigue llamando `/return` sin body → devolución total, como hoy. Compatible.
- [Cliente viejo del web-student] → no conoce la marca: muestra "Volver a abrir" en no reabiertos, pero el backend responde 409 (D5). El lock viejo sigue la regla N-1, que con "2 y 4" habilita el 4 antes que el 2: inofensivo, el submit lo exige igual.
- [Devolución parcial de una entrega legacy sin artefactos] → los no reabiertos no tienen código sellado: se le exigen al cliente como hoy (D4). Documentado y testeado.
- [Tests negativos que se vacían solos (lección del repo)] → cada 409/422 nuevo se prueba rojo quitando su guard.

## Prueba local reproducible (para Neyén, sin escribir código)

1. **Levantar el stack** desde la raíz de `rama desarrollo/` en Git Bash:
   - `DEV_TRUST_HEADERS=true PROMPTS_REPO_PATH="$(cygpath -w "$(pwd)/ai-native-prompts")" bash scripts/dev-start-all.sh`
   - en otra terminal: `pnpm turbo dev`
   - web-student en http://localhost:5175, web-teacher en http://localhost:5174. Alumno de dev: `e19354fb-c05a-4535-a0bf-a7d3ea09692d` (`apps/web-student/src/auth.ts`), tenant `aaaa…`.
   - Si el Postgres 18 nativo de Windows está prendido, frenarlo (pisa el 5432). Si al abrir un episodio da 403, es el `tenant_id` de la universidad `bbbb…` que dejan los smoke (memoria "403 local al abrir episodios").
2. **TP de 3 ejercicios** en web-teacher, publicada en la comisión del alumno de dev.
3. **Entregarla como alumno**: en cada ejercicio escribir algo distinto (`print(1)`, `print(2)`, `print(3)`), finalizar, "Entregar TP".
4. **Publicar nota**: web-teacher → Correcciones → la entrega → nota + feedback → "Publicar nota". En web-student: "Calificada", "Ver calificación" muestra la nota, **ningún ejercicio reabierto**, sin botón de entregar.
5. **Pedir corrección del 2**: web-teacher → la entrega → "Pedir corrección" → tildar sólo el ejercicio 2 → confirmar. Estado "Devuelta".
6. **En web-student**: ejercicio 1 y 3 "Completado" sin "Volver a abrir"; ejercicio 2 con badge "A corregir" y habilitado.
7. Abrir el 2, cambiar a `print(22)`, finalizar, "Entregar TP". Tiene que pasar.
8. **En web-teacher**, ver el código de la nueva entrega: ej. 1 `print(1)`, ej. 2 `print(22)`, ej. 3 `print(3)`.
9. **Compatibilidad**: en la base `academic_main`, `SELECT estado, ejercicio_estados FROM entregas WHERE estado='returned';` → las devoluciones viejas no tienen `reabierto_por_docente` y siguen con todos `completado=false`.
10. **CTR**: antes del paso 4 y después del 8, en `ctr_store`: `SELECT event_type, count(*) FROM events GROUP BY 1 ORDER BY 1;` → no aparece ningún `event_type` nuevo (los conteos suben por abrir/cerrar episodios, es esperado).
