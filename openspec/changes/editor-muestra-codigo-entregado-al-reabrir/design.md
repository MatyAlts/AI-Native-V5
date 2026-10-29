## Context

Motivación y diagnóstico en `proposal.md`. Estado verificado contra `origin/main` (`18bffe9`) el 2026-10-27. Recoge lo útil del change descartado `tp-devuelta-ejercicio-no-se-completa`.

**Qué pasa hoy con una TP de 2 ejercicios devuelta (devolución total):**

| Paso | Qué hace el sistema | Dónde |
|---|---|---|
| Entrega | Manda borradores locales, sella `entrega_artefactos` (un `codigo` por `orden`) y **borra los borradores** | `ExerciseListView.tsx:312-320`; `entregas.py:1127` |
| Devolución | `returned`, `completado=false` en todos, `episode_id` del intento 1 intacto | `entregas.py:811-812, 821` |
| Abrir ej. 1 | El episodio viejo está `closed` → se abre uno **nuevo** | `routes/materia.$id.tsx` (`openEpisodeAndNavigate`) |
| Estado del episodio | Sin código propio y `open` → REAPERTURA siembra `last_code_snapshot` con el último código del episodio cerrado más reciente (mismo alumno/TP/ejercicio). Sólo lectura | `tutor-service/routes/episodes.py:498-526`; `ctr-service/routes/events.py:159-205` |
| Siembra | `borradorLocal` (sólo del mismo `episode_id`) → `snapshot` → scaffold TP → scaffold ejercicio → placeholder | `EpisodePage.tsx:589-608`; `lib/cascadaCodigo.ts:94-103` |
| Editor | Arranca con `initialCode`; `lastFiredSnapshotRef = initialCode` → **cargar no emite `edicion_codigo`** (`resolverEdicionPendiente` devuelve `null` si no cambió) | `CodeEditor.tsx:429`; `lib/edicionPendiente.ts:73` |
| Cerrar sin tipear | flush sin pendiente → sin borrador → `hayCodigo=false` → `return` **sin PATCH ni aviso** | `EpisodePage.tsx:826-875` |
| Lista | Ej. 1 sigue "Continuar", ej. 2 bloqueado | `ExerciseListView.tsx:349-353` |

**Cadena cortada**: si en el paso "Cerrar sin tipear" el episodio nuevo se cierra, la próxima reapertura encuentra ESE episodio como el cerrado más reciente; no tiene eventos de código → REAPERTURA no siembra → scaffold. Y el código entregado no aparece en ningún candidato.

## Goals / Non-Goals

**Goals:**
- Un ejercicio reabierto cuyo editor muestra código del alumno, cerrado sin editar, queda completado por cualquiera de los tres caminos de cierre, y la re-entrega manda ese código.
- El editor de un ejercicio reabierto nunca cae al scaffold si existe código entregado para ese mismo ejercicio.
- BUG-1 intacto: sin código propio no se marca.
- Cero cambio en la emisión CTR.

**Non-Goals:**
- Tocar REAPERTURA (`tutor-service`) o `closed-match` (`ctr-service`). Este último está en la lista de "no tocar" por la tesis.
- Aviso en pantalla cuando un ejercicio no se marca (change aparte si hace falta).
- Cubrir "cerré en la máquina A, re-entrego desde la B" (ver Riesgos).
- Reabrir episodios cerrados.

## Decisions

### D1 — Candidato nuevo `codigoEntregado`, entre `snapshot` y los scaffolds

```
borradorLocal (mismo episodio) > snapshot (propio o REAPERTURA) > codigoEntregado > scaffoldTp > scaffoldEjercicio > placeholder
```

- **Por qué debajo de `snapshot`**: `snapshot` puede ser código del propio episodio (pausa y vuelta) — pisarlo es borrar trabajo. El frontend no distingue si el snapshot es propio o heredado por REAPERTURA (`EpisodeStateResponse` no lo dice), así que el entregado no puede ganarle sin tocar el tutor-service. En el caso normal los dos son el mismo código; donde difieren, los dos son código del alumno para ese mismo ejercicio.
- **Por qué arriba de los scaffolds**: el ejercicio ya tiene una entrega del alumno; volver a mostrarle la consigna vacía es lo que lo lleva a cerrar sin tocar ("mi código desapareció").
- **No es ED-4.** ED-4 (eliminado el 2026-09-28, `openspec/changes/eliminar-ed4-siembra-codigo-previo/`) arrastraba código de **otro** ejercicio y pisaba la decisión del docente. Esto es código del **mismo** ejercicio, de la **misma** entrega, que el alumno ya entregó — el mismo alcance que REAPERTURA, que ese change declaró legítimo (caso 3). El match es por `orden` **y** `ejercicio_id` cuando los dos existen; un artefacto de otro ejercicio nunca se usa (test dedicado).
- **Cuándo se pide**: sólo con `ejercicioContext` (TP multi-ejercicio) **y** `borradorLocal` y `snapshot` vacíos. Un GET chico; en el camino normal (episodio con código propio) no se pide. Si falla (red, 404, `legacy`, sin fila para el `orden`, `codigo` vacío) → no hay candidato y la cascada sigue como hoy.
- `resolverCascadaDeCodigo` sigue siendo pura; `EpisodePage` resuelve el candidato y se lo pasa. Origen nuevo: `"codigo-entregado"`.

### D2 — Cerrar sin editar: el código mostrado pasa a ser el borrador

Se guarda en un `siembraRef` el resultado de la cascada (`codigo`, `origen`). Se agrega `huboEdicionRef` (lo pone en `true` `onEditDebounced`, que también corre en el flush).

Forma final del guard en `markEjercicioCompletedOnce` (orden de evaluación):

1. `flushEditorRef` (igual que hoy).
2. Borrador local con código → marca (igual que hoy).
3. Sin borrador, `huboEdicionRef=false` y `siembraRef.origen ∈ {"snapshot","codigo-entregado"}` con `codigo.trim()` no vacío → `saveArtefactoDraft(entregaId, {orden, ejercicio_id, episode_id: <episodio actual>, codigo: siembra.codigo, language})` y marca.
4. Cualquier otro caso (scaffold, placeholder, editó y dejó vacío) → no marca (igual que hoy, BUG-1).

**Sin red en el cierre**: el código ya se resolvió al hidratar. Mejor que el plan viejo (GET en el cierre, con su carrera y su latencia).

**`episode_id` del borrador = episodio actual**: coincide con el que el PATCH escribe en `ejercicio_estados` y con el que el alumno vio y aceptó. Ninguna lectura aguas abajo usa el `episode_id` del artefacto (grep en `correccion_ia.py`, `olvido.py`, analytics, classifier: sin usos). El change viejo proponía el `episode_id` del artefacto; con origen `snapshot` (REAPERTURA) ese dato no está disponible, y una regla única es más simple de testear.

**D2b — "editó y dejó vacío"** (heredado del change viejo, D5): si hubo edición, no se usa la siembra aunque el buffer quede vacío. Contradiría lo que el alumno hizo en pantalla.

### D3 — Re-entrega

Con el borrador del paso 3, `recuperarArtefactos` lo encuentra primero (`collectArtefactoDrafts`) y no necesita el fallback por snapshot. Con `publicar-nota-y-pedir-correccion` aplicado, los ejercicios **no** reabiertos ni siquiera llegan acá: el backend conserva su artefacto sellado.

### D4 — `getEntregaArtefacto` y el PR #122

El PR #122 (abierto, `feat/alumno-mis-trabajos-corregidos`) agrega a `apps/web-student/src/lib/api.ts` `getEntregaArtefacto` + `ArtefactoEntregado`/`EntregaArtefacto`/`EntregaArtefactoError` (+ `tests/getEntregaArtefacto.test.ts`).

- **Si #122 está en `main` al empezar el apply**: rebasar y reusar.
- **Si no**: copiar el bloque **idéntico** (`git show origin/feat/alumno-mis-trabajos-corregidos:apps/web-student/src/lib/api.ts`). No se copia su test (es de #122); se testea a través del flujo. Al mergear el segundo, el conflicto es texto igual contra texto igual.
- El endpoint backend ya existe en `main` (`entregas.py:420-460`) y el dueño lo puede leer (`is_owner`).

### D5 — Por qué no arreglar la cadena cortada en el backend

La alternativa limpia sería que `closed-match` saltee episodios cerrados sin código, o que REAPERTURA recorra más de uno. Lo primero toca `ctr-service` (prohibido por la restricción de tesis); lo segundo agrega N lecturas de cadenas CTR por hidratación. El candidato `codigoEntregado` resuelve el caso que importa (TP devuelta) sin tocar ninguno de los dos.

## Tesis: qué NO se toca

- **Cero cambios** en `apps/ctr-service`, `apps/classifier-service`, `packages/contracts`, `ai-native-prompts`, `apps/tutor-service` (REAPERTURA incluida), `LABELER_VERSION`, `classifier_config_hash`, ni en `CodeEditor.tsx`/`edicionPendiente.ts` (donde vive la emisión de `edicion_codigo`).
- **Sembrar no emite**: el editor arranca con `initialCode` y el baseline de emisión es ese mismo valor (`CodeEditor.tsx:429`, `edicionPendiente.ts:73`). Se agrega un test que monta el editor con origen `codigo-entregado` y verifica **0** `edicion_codigo` sin tecleo.
- **Cerrar sin editar no emite nada nuevo**: escribe `localStorage` y hace el mismo PATCH de siempre (`evaluation-service`, no CTR). El cierre emite los mismos eventos que hoy.
- **No se reabre ningún episodio cerrado.** Se lee el artefacto sellado; el episodio viejo queda cerrado y atestado.
- Verificación (tarea 6.1), debe salir **vacío**:

```bash
git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/web-student/src/components/CodeEditor.tsx apps/web-student/src/lib/edicionPendiente.ts
```

**Matiz de comportamiento (informar a Cortez)**: el contenido del primer `edicion_codigo` de un episodio reabierto depende de con qué arrancó el buffer. Hoy, vía REAPERTURA, ya arranca con el código previo en el caso común; este change extiende eso a la cadena cortada (antes: scaffold). En esos episodios, `snapshot` incluye el código entregado y `diff_chars` mide sólo lo que el alumno cambió. Además, ejercicios cerrados sin cambios pasan a contar como completados (episodios cortos sin `edicion_codigo`), que antes quedaban pendientes. El instrumento (tipos de evento, payloads, emisión, labeler) no cambia.

## Risks / Trade-offs

- [Cierra sin editar en la máquina A, re-entrega desde la B] → B no tiene el borrador; `recuperarArtefactos` busca el snapshot del episodio nuevo (vacío) → 422 nombrando el ejercicio. Mitigación: "Volver a abrir" + cerrar en B repite el fallback. Con `publicar-nota-y-pedir-correccion`, sólo afecta a ejercicios reabiertos. Documentado.
- [El docente pidió corregir ese ejercicio y el alumno lo cierra sin cambios] → se re-entrega el mismo código. Es lo que el alumno hizo; el docente lo ve en la corrección y en el episodio (sin ediciones).
- [El snapshot heredado difiere del sellado] → gana el snapshot (D1). Ambos son del alumno, mismo ejercicio. Alternativa (que gane el sellado) requiere que tutor-service marque el snapshot como heredado: pregunta abierta, no bloquea.
- [Tests negativos que se vacían solos] → cada negativo se prueba rojo quitando su condición.

## Prueba local reproducible (para Neyén, sin escribir código)

Reusa la receta del change viejo. Hace falta una entrega devuelta nueva (la TP `SMK-P4D2B` está archivada).

1. **Levantar el stack** desde la raíz de `rama desarrollo/` en Git Bash:
   - `DEV_TRUST_HEADERS=true PROMPTS_REPO_PATH="$(cygpath -w "$(pwd)/ai-native-prompts")" bash scripts/dev-start-all.sh`
   - en otra terminal: `pnpm turbo dev`
   - web-student http://localhost:5175, web-teacher http://localhost:5174. Alumno de dev `e19354fb-c05a-4535-a0bf-a7d3ea09692d`, tenant `aaaa…`.
   - Postgres 18 nativo de Windows apagado (pisa el 5432). 403 al abrir episodio = universidad con tenant `bbbb…` de los smoke.
2. **TP de 2 ejercicios** publicada en la comisión del alumno de dev.
3. **Entregar**: ej. 1 `print(1)`, finalizar; ej. 2 `print(2)`, finalizar; "Entregar TP".
4. **Devolver**: web-teacher → Correcciones → nota → guardar → "Devolver al estudiante" (o "Pedir corrección" de los dos, si ya está el otro change).
5. **Foto CTR antes** (`ctr_store`): `SELECT event_type, count(*) FROM events GROUP BY 1 ORDER BY 1;`
6. **Escenario del alumno**: ej. 1 → "Continuar". **Anotar qué muestra el editor** (esperado: `print(1)`). No escribir nada. "Finalizar episodio", saltear reflexión, "Siguiente ejercicio →".
   - Antes del fix: ej. 1 sigue "Continuar", ej. 2 bloqueado.
   - Con el fix: ej. 1 "Completado", ej. 2 habilitado.
7. **Cadena cortada** (sólo con el fix, o para ver el bug antes): en el ej. 1 completado, "Volver a abrir" → "Continuar" → el editor muestra `print(1)` (antes del fix: scaffold/placeholder). Cerrar sin escribir → queda completado.
8. **F12 > Network** en el paso 6/7: a lo sumo un `GET …/entregas/<id>/artefacto` al abrir y el `PATCH …/ejercicio/1` al cerrar. Ningún request nuevo a `/events` ni a `edicion_codigo` sin tipear.
9. **Re-entregar**: ej. 2 → `print(22)` → finalizar → "Entregar TP". Pasa sin "Falta el código…". En web-teacher, ej. 1 = `print(1)`, ej. 2 = `print(22)`.
10. **BUG-1**: otra TP de 2 ejercicios **nunca entregada**, abrir ej. 1, no escribir, finalizar → **no** se marca, ej. 2 sigue bloqueado.
11. **Foto CTR después**: misma consulta del paso 5 → ningún `event_type` que no estuviera antes (los conteos suben por abrir/cerrar, es esperado).
