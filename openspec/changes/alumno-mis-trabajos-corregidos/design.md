# Design — alumno-mis-trabajos-corregidos

## Context

Todo lo que la vista necesita **ya existe del lado del servidor** y el alumno ya
tiene permiso para leerlo. Lo que falta es la pantalla que lo junte.

| Dato | De dónde sale | Ya lo usa |
|---|---|---|
| Lista de entregas con nota (TPs archivadas incluidas) | `GET /api/v1/entregas?comision_id=…` — `listMisEntregas` (`web-student/src/lib/api.ts:1362`) | "Mis notas" (#107) |
| Nota, devolución general, criterios | `GET /api/v1/entregas/{id}/calificacion` (`evaluation-service/routes/entregas.py:725-748`) — `getCalificacion` (`api.ts:1301`) | `GradeDetailView` |
| **Código entregado, por ejercicio** | `GET /api/v1/entregas/{id}/artefacto` (`entregas.py:420-459`): dueño o docente, si no 404. Devuelve `artefactos[]` con `orden, ejercicio_id, episode_id, codigo, language, sha256` (`schemas/entrega.py:82-105`) | web-teacher (descarga del docente). **El web-student no tiene cliente todavía.** |
| Charla alumno–tutor del ejercicio | `GET /api/v1/episodes/{id}` (`tutor-service/routes/episodes.py:436-530`): dueño-o-nada, sirve episodios cerrados | Descarga de #95 (`ExerciseListView.tsx:234-270`) |
| Título del ejercicio | `GET /api/v1/tareas-practicas/{id}/ejercicios` (`academic-service/routes/tareas_practicas.py:626-660`) — **404 al alumno si la TP no está `published`** (`:648`) | `ExerciseListView` |

Dos hechos del código que cambian el diseño respecto de las notas del 16/10:

1. **El código correcto es el artefacto, no el snapshot del episodio.** El
   artefacto se sella con hash en el submit (`_persistir_artefactos`,
   `entregas.py:1127-1180`) y guarda **su propio `episode_id`**. En cambio
   `ejercicio_estados[].episode_id` se pisa cuando el alumno abre el episodio
   nuevo de una reapertura (`entregas.py:837-840`), así que puede apuntar a un
   intento que el docente no corrigió. El artefacto sólo se reemplaza en un
   **re-submit** (`entregas.py:1136`) — exactamente cuando la entrega deja de
   estar corregida.
2. **`ExerciseListView` no se puede montar acá**: al montarse llama
   `createOrGetEntrega`, un `POST /api/v1/entregas` (`api.ts:1246-1261`).

La nota y los criterios son **por entrega (TP)**, no por ejercicio
(`models/entregas.py:162-177`). La vista lo refleja: nota arriba, código abajo.

## Goals / Non-Goals

**Goals:**
- Una vista de sólo lectura del trabajo corregido: nota + devolución por
  criterio (por TP) y código entregado + descarga (por ejercicio).
- Reusar sin modificar: `buildEpisodioSourceFile`, el render de la calificación,
  `listMisEntregas`, `getEpisodeState`.
- Cero escrituras y cero eventos CTR, demostrado por test.
- Sin cambios de backend.

**Non-Goals:**
- Intentos previos a una reapertura (trabajo futuro, ver proposal).
- Enunciado del TP archivado.
- Títulos de ejercicio en TPs archivadas vía backend (D2-b, change aparte).
- Descargar el TP entero en un zip.
- Tocar `ExerciseListView` o su botón de descarga existente.

## Decisions

### 1. El código sale del artefacto; la charla, del episodio que nombra el artefacto

`getEntregaArtefacto(entregaId)` en `api.ts`, tipado contra `EntregaArtefactoOut`.
Para la descarga: `codigo` y `language` del artefacto; `messages` de
`getEpisodeState(artefacto.episode_id)`. Se descarta usar
`last_code_snapshot` del episodio: es "lo último que el editor alcanzó a
reportar", no lo entregado (el propio `ExerciseListView.tsx:90-101` lo admite).

**Si la charla falla, el código igual se descarga** — el código es lo que el
alumno necesita conservar; la charla es contexto. Se avisa con palabras.

**El episodio se pide al apretar "Descargar", no al montar la vista.** Montar
la vista hace 2 requests (calificación + artefacto) y no N episodios.

### 2. Un componente nuevo, independiente de dónde se monte

`TrabajoCorregidoView({ entrega, onBack })` en `web-student/src/components/`.
Recibe la `Entrega` ya cargada (la trae la lista), así que **no pide la entrega**.
Adentro:
- Bloque de calificación: se extrae el cuerpo de `GradeDetailView` a un
  componente presentacional (`CalificacionDetalle`) que ambos usan, **sin cambiar
  lo que `GradeDetailView` renderiza** (sus tests existentes son la red). Si la
  extracción resulta invasiva, alternativa aceptable: montar `GradeDetailView`
  tal cual arriba y el bloque de código abajo.
- Bloque por ejercicio: `orden`, título (o "Ejercicio N"), `<pre>` de sólo lectura
  con el código, botón "Descargar (.py/.java)" con estado por botón (mismo
  patrón `descargando: number | null` que `ExerciseListView.tsx:159-162`).

No se usa Monaco: un `<pre>` es sólo lectura por construcción y no arrastra el
`CodeEditor`, que es justamente el que emite `edicion_codigo` y los eventos de
portapapeles.

**Montaje (depende de D1):** con D1-(b), `MisNotasPage.tsx:278-280` monta
`TrabajoCorregidoView` cuando `selected.estado` es `graded`/`returned`, y sigue
montando `GradeDetailView` para `submitted`. Con D1-(a) se suma
`routes/mis-trabajos-corregidos.tsx` que reusa `agruparEntregas().conNota`.

### 3. Lógica pura separada y testeada directo

`utils/trabajoCorregido.ts` con funciones puras:
- `ejerciciosDelTrabajo(artefactos, titulos?)` → lista ordenada por `orden`, con
  `titulo ?? "Ejercicio N"`.
- `esTrabajoCorregido(entrega)` → `graded` | `returned`.
- `archivoDeDescarga(artefacto, messages | null, meta)` → envuelve
  `buildEpisodioSourceFile` sin cambiar su contrato (con `messages=[]` si la
  charla falló).

Los títulos se piden con `listEjerciciosTp(tarea_practica_id)` y **cualquier error
se trata como "sin títulos"** (D2-a). Es un GET y su fallo no bloquea nada.

### 4. Inventario de llamadas — por qué ninguna escribe ni emite al CTR

Toda llamada que la vista puede hacer, con su handler:

| Llamada | Método | Handler | ¿Escribe? ¿Emite CTR? |
|---|---|---|---|
| `listMisMaterias` (ya la hace "Mis notas") | GET `/api/v1/materias/mias` | academic-service | No. Lectura. |
| `listMisEntregas` (ya la hace "Mis notas") | GET `/api/v1/entregas` | `entregas.py:149` | No. Lectura + batch de metadata. |
| `getCalificacion` | GET `/api/v1/entregas/{id}/calificacion` | `entregas.py:725-748` | No: `select(Calificacion)` y return. |
| `getEntregaArtefacto` (nuevo cliente) | GET `/api/v1/entregas/{id}/artefacto` | `entregas.py:420-459` | No: `select(EntregaArtefacto)` y return. |
| `listEjerciciosTp` | GET `/api/v1/tareas-practicas/{id}/ejercicios` | `tareas_practicas.py:626-660` | No. Lectura. |
| `getEpisodeState` (al descargar) | GET `/api/v1/episodes/{id}` | `episodes.py:436-530` → `ctr.get_episode` (`tutor-service/services/clients.py:369-395`) → ctr-service `routes/events.py:210-245` | No: dos `select` (episodio + eventos) y return. El único desvío del handler (`episodes.py:498-528`, siembra de reapertura) **sólo corre si el episodio está `open`** y también es lectura ("No emite ningún evento CTR nuevo"). El episodio de un artefacto está cerrado. |

Lo que la vista **NO** llama, y el test lo afirma: `openEpisode`,
`closeEpisode`, `resumeEpisode`, `emitEpisodioAbandonado`, cualquier
`emit*` (`api.ts:350-670`, todos `POST /api/v1/episodes/{id}/events/*`),
`sendMessage`, `classifyEpisode`, `createOrGetEntrega`, `submitEntrega`,
`markEjercicioCompleted`, `reabrirEjercicio`.

Los listeners que emiten `pestana_perdida`/`pestana_recuperada`/
`episodio_abandonado` viven en `EpisodePage.tsx` y `routes/materia.$id.tsx`;
"Mis notas" (`MisNotasPage.tsx`) y `GradeDetailView` no registran ninguno. La
vista nueva tampoco.

**Cómo se prueba (no se afirma de palabra):** un test de integración del
componente mockea `fetch`, recorre la vista y descarga todos los ejercicios, y
afirma que (a) todas las requests fueron `GET` y (b) ninguna URL matchea
`/events/|/close|/abandoned|/resume|/message|/reflection|classify`.

Con eso: no hay evento nuevo en `ctr_store`, no cambia `events_count` ni
`last_chain_hash` de ningún episodio, no se dispara clasificación, y el
`classifier_config_hash` ni se toca. **Nada de lo que el paper consume cambia.**

### 5. Estados con palabras (principio 5 de `PRODUCT.md`)

| Estado | Qué dice |
|---|---|
| Cargando | Skeleton, no spinner en el medio. |
| Sin artefactos (`legacy`) | "Esta entrega es anterior a que la plataforma guardara el código entregado." (D3-a) |
| Falla el artefacto | "No pudimos traer tu código. Probá de nuevo." — distinto del caso legacy. |
| Artefacto 404 | Se trata como no disponible (es lo que el backend devuelve a un ajeno). |
| Falla la charla al descargar | Se descarga el código y se avisa: "La charla con el tutor no se pudo incluir." |
| `returned` | Cartel: el docente la devolvió para revisar. |

### 6. Test runner

vitest de `apps/web-student` (`pnpm test` = `vitest run`). Tests nuevos en
`apps/web-student/tests/`, junto a `GradeDetailView.test.tsx`,
`MisNotasPage.test.tsx` y `episodioDownload.test.ts`, que son la red de
seguridad. **El CI no corre vitest** — la verificación es local. **Bajo Node 26,
los rojos de `localStorage` son falsos** (ambientales): se anotan en el baseline
y no se confunden con regresiones.

## Risks / Trade-offs

- **[Endpoint del artefacto pensado para el docente]** `ArtefactoOut` dice "para
  la descarga del docente", pero el handler ya admite al dueño
  (`is_owner`, `entregas.py:433`). → No se cambia nada del backend; un test del
  cliente fija el shape que consume la vista. Si alguien restringe ese endpoint a
  docentes, el test de la vista no lo ve: se anota en el `STATUS.md`.
- **[`api-gateway`]** `/api/v1/entregas` ya está en el `ROUTE_MAP`
  (`api-gateway/routes/proxy.py:87`) y rutea por prefijo, así que `/artefacto`
  llega. Se confirma en la prueba local, no se asume.
- **["Ejercicio N" en TPs archivadas]** Es feo pero honesto. → D2.
- **[La vista muestra el código; el docente puede haber corregido otra cosa]**
  En entregas `legacy` el docente pudo haber corregido sobre el snapshot del
  episodio. → D3: no se muestra nada que no esté sellado.
- **[Re-entrega sin recalificar]** Desaparece de la vista hasta que el docente
  vuelva a corregir. → Declarado como non-goal; el alumno sigue viendo la
  entrega en "sin corregir todavía".
- **[`returned` reabierto en curso]** El alumno puede tener un episodio nuevo
  abierto mientras mira lo corregido. La vista no lo toca: usa el `episode_id`
  del artefacto (cerrado), nunca el de `ejercicio_estados`.

## Open Questions

Las tres están en el proposal (D1, D2, D3) con opciones y recomendación. **D1 es
la única que cambia qué se construye** (una ruta nueva o no); las tareas asumen
las recomendadas (D1-b, D2-a, D3-a) y marcan dónde cambia si se elige otra.
