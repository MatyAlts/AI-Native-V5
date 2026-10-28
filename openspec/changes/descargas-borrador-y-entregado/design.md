## Context

Motivación en `proposal.md`. Estado verificado contra `origin/main` (`18bffe9`, 26/10) y la rama del PR #122 (`origin/feat/alumno-mis-trabajos-corregidos`) el 2026-10-28:

| Hecho | Dónde |
|---|---|
| Botón de la TP: visible sólo si el ejercicio está `completed`; rótulo `Descargar (.py\|.java)` | `apps/web-student/src/components/ExerciseListView.tsx:561-572` (main) |
| Fuente del botón de la TP: `getEpisodeState(episode_id).last_code_snapshot` del `episode_id` de `ejercicio_estados` | `ExerciseListView.tsx:234-270` |
| Lenguaje del botón de la TP: `ejercicio.language ?? tarea.language ?? DEFAULT_LANGUAGE` | `ExerciseListView.tsx:57-62` (`resolveDownloadLanguage`) |
| Devolver des-marca TODOS los ejercicios (`completado=false`) y deja el `episode_id` viejo | `apps/evaluation-service/src/evaluation_service/routes/entregas.py:821-846` |
| `GET /entregas/{id}/artefacto`: el alumno dueño lo lee; devuelve `artefactos[]` (uno por `orden`, con `codigo`, `language`, `episode_id`) y `legacy` | `routes/entregas.py:420-460` (main) |
| Artefacto sellado: se escribe en el submit con lo que manda el cliente; el submit siguiente **reemplaza** el conjunto | `models/entregas.py:109-150`; `_persistir_artefactos` |
| Cliente del endpoint (`getEntregaArtefacto`, `EntregaArtefacto`, `EntregaArtefactoError`) | `apps/web-student/src/lib/api.ts:1459-1488` — **sólo en la rama del #122** |
| Armado del archivo de lo entregado (`archivoDeDescarga`: código sellado + charla del episodio del artefacto) | `apps/web-student/src/utils/trabajoCorregido.ts` — **sólo en #122** |
| Vista de trabajo corregido: botón `Descargar (${ext})`, charla del `artefacto.episode_id` | `apps/web-student/src/components/TrabajoCorregidoView.tsx` (#122), botón en la sección "Lo que entregaste" |
| Armado común de archivo y extensión (`.py` / `.java`, comentario `#` / `//`) | `apps/web-student/src/utils/episodioDownload.ts:48-114` (main) |

## Goals / Non-Goals

**Goals:**
- Que el rótulo diga qué se baja, en las dos pantallas.
- Que en la pantalla de la TP el alumno pueda bajar lo entregado, sobre todo con la TP devuelta (hoy no tiene ningún botón ahí).
- No mostrar dos botones que bajan lo mismo.

**Non-Goals:**
- Cambiar qué es "el borrador": sigue siendo `last_code_snapshot` del episodio. No se suma el borrador local (`collectArtefactoDrafts`) a la descarga.
- Descargar intentos anteriores a la última entrega (no hay historia: el submit reemplaza el conjunto).
- Backend, endpoints o tipos nuevos en el servidor.
- Tocar Mis notas más allá del rótulo.

## Decisions

### D1 — Rótulos: "Descargar borrador" / "Descargar lo entregado"

| Opción | Veredicto |
|---|---|
| **"Descargar borrador (.py)" / "Descargar lo entregado (.py)"** | **Elegida.** Dicen el origen del código con palabras del alumno; la extensión se conserva porque ya avisa qué archivo baja |
| "Descargar código actual" / "Descargar versión corregida" | Descartada: "corregida" sugiere que el código fue modificado por el docente, y no lo fue |
| Un solo botón con menú | Descartada: más clicks, y el pedido es literalmente "dos botones" |

Los rótulos viven en una sola función pura (`utils/descargas.ts`, `rotuloDescarga(tipo, language)`) para que las dos pantallas no vuelvan a divergir.

### D2 — Cuándo aparece cada botón (función pura)

`botonesDeDescarga({ estado, legacy, submittedAt, completado }) -> { borrador: boolean, entregado: boolean }`:

| Situación | Borrador | Lo entregado |
|---|---|---|
| `draft`, ejercicio completado | sí | no (nunca se entregó) |
| `draft`, no completado | no | no |
| `submitted` / `graded` (no legacy) | no | sí |
| `returned`, ejercicio todavía no re-completado | no | sí |
| `returned`, ejercicio re-completado | sí | sí |
| `legacy` (cualquier estado), completado | sí | no (no hay artefacto sellado) |

Por qué el borrador desaparece en `submitted`/`graded`: la entrega no es editable, así que el borrador **es** lo entregado salvo por el desfasaje del editor (el `last_code_snapshot` es "lo último que el editor alcanzó a reportar", no necesariamente lo que el alumno mandó). Mostrar dos botones que casi siempre bajan lo mismo, y a veces no, es exactamente la confusión que se quiere sacar; y el que vale ahí es el sellado.

Cambio de comportamiento a declarar: en `graded` hoy el botón baja el episodio; después baja el artefacto sellado. Es lo correcto (es lo que corrigió el docente), y para `legacy` se conserva el comportamiento de hoy.

`submittedAt` presente es la condición de "se entregó alguna vez" (en `returned` el artefacto sellado es el de la entrega anterior hasta el próximo submit).

### D3 — "Lo entregado" en la pantalla de la TP: lectura perezosa, al click

Al apretar, se llama `getEntregaArtefacto(entrega.id)`, se busca el artefacto con ese `orden` y se arma el archivo con `archivoDeDescarga` (misma forma que Mis notas, charla del `artefacto.episode_id`, aviso si la charla falla).

Alternativa descartada: pedir el artefacto al montar la pantalla para mostrar el botón sólo si hay código. Suma un request por cada visita a la TP para un botón que se usa poco; la regla de D2 (no legacy + `submitted_at`) ya predice la existencia del artefacto, y el caso raro de que falte se resuelve con aviso (spec: "Ejercicio sin código sellado").

El spinner y el aviso de error van por `orden` y por tipo de botón, como hoy (`descargando`), para que apretar uno no ponga "Descargando…" en el otro.

### D4 — Extensión: no cambia

- Borrador: `resolveDownloadLanguage` (ejercicio > TP > default), como hoy.
- Lo entregado: `artefacto.language`, como en #122. Es el lenguaje con el que se selló, que es el dato correcto aunque la TP haya cambiado después.

El rótulo del botón de lo entregado en la TP se arma con `resolveDownloadLanguage` antes de leer el artefacto (no se conoce `artefacto.language` sin la lectura de D3); en la práctica coinciden. Si no coincidieran, el archivo usa el del artefacto. Riesgo aceptado y documentado.

### D5 — Dependencia del PR #122

El change necesita de #122: `getEntregaArtefacto` + tipos, `archivoDeDescarga` y la propia `TrabajoCorregidoView` (cuyo rótulo cambia).

| Opción | Veredicto |
|---|---|
| **Mergear #122 primero y abrir la rama de este change desde `main`** | **Recomendada.** #122 está listo para review; un PR chico encima de `main` es fácil de revisar y no arrastra el diff de otro |
| Basar la rama en `feat/alumno-mis-trabajos-corregidos` | Sólo si #122 se demora: el PR de este change apunta a esa rama y se retargetea a `main` cuando #122 entre. Riesgo: si #122 cambia en review, hay que rebasear |
| Duplicar `getEntregaArtefacto` en este change | Descartada: dos copias del mismo cliente, conflicto seguro al mergear |

Además, `ExerciseListView.tsx` lo toca también `publicar-nota-y-pedir-correccion` (lock, "Volver a abrir", badge "A corregir"). Este change se aplica **después** y se rebasea; los cambios están en zonas distintas del render (botones de la fila), el conflicto esperable es textual.

## Tesis: qué NO se toca

- **Cero cambios** en `apps/ctr-service`, `apps/classifier-service`, `packages/contracts`, `ai-native-prompts`, `apps/tutor-service`. Tampoco en backend alguno (`apps/evaluation-service` queda igual).
- Las dos descargas son **lecturas** (`GET /entregas/{id}/artefacto`, `GET /episodes/{id}`). No abren, cierran ni reanudan episodios; no emiten eventos al CTR; no usan `CodeEditor`.
- Verificación (tarea 5.1), debe salir **vacío**:

```bash
git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/evaluation-service
```

## Risks / Trade-offs

- [#122 no se mergea o cambia en review] → D5: plan B basando la rama en la de #122; el apply arranca verificando que `getEntregaArtefacto` exista.
- [El rótulo de la extensión en la TP no coincide con el artefacto] → D4: el archivo usa el lenguaje sellado; documentado.
- [Alumno en `graded` que quería "lo último que escribí" y no lo entregado] → por construcción coinciden; si el editor se desfasó, lo sellado es lo que vale (es lo que vio el docente).
- [Choque de archivo con `publicar-nota-y-pedir-correccion`] → aplicar después y rebasear.
- [Tests que asertan lo negativo se vacían solos (lección del repo)] → cada "no aparece el botón" se prueba rojo forzando la condición.

## Prueba local reproducible (para Neyén, sin escribir código)

1. **Levantar el stack** desde la raíz de `rama desarrollo/` en Git Bash:
   - `DEV_TRUST_HEADERS=true PROMPTS_REPO_PATH="$(cygpath -w "$(pwd)/ai-native-prompts")" bash scripts/dev-start-all.sh`
   - en otra terminal: `pnpm turbo dev`
   - web-student en http://localhost:5175, web-teacher en http://localhost:5174. Alumno de dev `e19354fb-c05a-4535-a0bf-a7d3ea09692d`, tenant `aaaa…`. Si el Postgres 18 de Windows está prendido, frenarlo (pisa el 5432).
2. En web-teacher, una TP de 2 ejercicios en Python publicada en la comisión del alumno.
3. **Borrador**: como alumno, ejercicio 1 → `print("v1")` → finalizar. En la pantalla de la TP el ejercicio 1 muestra **sólo** "Descargar borrador (.py)". Bajarlo: dice `print("v1")`.
4. Completar el 2 (`print("dos")`) y "Entregar TP". Ahora cada ejercicio muestra **sólo** "Descargar lo entregado (.py)". Bajarlo: `print("v1")`.
5. En web-teacher: calificar y devolver (o "Pedir corrección" si ya está aplicado ese change). En web-student, con la TP devuelta: cada ejercicio muestra "Descargar lo entregado" aunque esté sin completar.
6. Abrir el ejercicio 1, cambiar a `print("v2")`, finalizar **sin entregar**. El ejercicio 1 muestra **los dos** botones: "borrador" baja `print("v2")`, "lo entregado" baja `print("v1")`.
7. **Mis notas** → el trabajo corregido: los botones dicen "Descargar lo entregado (.py)" y bajan `print("v1")`.
8. **CTR sin cambios**: antes del paso 3 y después del 7, en `ctr_store`: `SELECT event_type, count(*) FROM events GROUP BY 1 ORDER BY 1;` → ningún `event_type` nuevo; las descargas solas (repetir 6–7 sin editar) no suben ningún conteo.
