# ADR-055 — Reingreso a episodios: pausa por abandono + reanudación sin eventos nuevos

- **Estado**: Aceptado
- **Fecha**: 2026-06
- **Deciders**: Alberto Cortez, equipo plataforma
- **Tags**: ctr, tutor-service, append-only, ux-estudiante

## Contexto y problema

Fix de plataforma 2026-06-10 #2: cuando el alumno se va (cierra la pestaña o
queda inactivo 30 min), el episodio recibe `episodio_abandonado` (ADR-025) y la
sesión Redis del tutor se borra. Hasta este ADR, el episodio quedaba con
`estado="open"` para siempre en `ctr_store` y el alumno NO podía retomarlo:
sin sesión Redis, todo evento posterior rebota ("Episode no existe o expiró")
y la única salida era abrir un episodio nuevo para la misma TP, fragmentando
la trazabilidad del intento.

Lo pedido: que el episodio quede **en pausa** al abandonarse, que el alumno
pueda **reingresar** y continuar, y que el docente lo vea **marcado** en el
análisis para decidir qué hacer (esperarlo, conversarlo, ignorarlo).

## Drivers de la decisión

- **CTR append-only intocable** (ADR-010): nada de UPDATE/DELETE de eventos ni
  tipos de evento nuevos sin necesidad real.
- **Reproducibilidad**: el `event_labeler` y el feature-extraction no deben
  cambiar (cero impacto en `LABELER_VERSION` / `classifier_config_hash`).
- **Consistencia de `seq`**: el partition_worker exige `seq == events_count`;
  la reanudación no puede colisionar con eventos en vuelo.
- UX: el alumno retoma con su conversación y su código donde los dejó.

## Opciones consideradas

### Opción A — Evento nuevo `episodio_reanudado`
Explícito en la cadena, pero exige tipo de evento nuevo (contrato + labeler +
exclusión del feature extraction con ADR propio) para información que ya es
derivable: en la cadena, una reanudación es literalmente `episodio_abandonado`
seguido de más eventos.

### Opción B — Estado `paused` en Episode + reanudación que solo reconstruye la sesión
`estado` del Episode es metadata mutable (ya transiciona open→closed), NO es
parte de la cadena hasheada. El abandono pausa; la reanudación reconstruye la
sesión Redis desde la cadena persistida; el primer evento posterior repone
`open`. Cero tipos nuevos, cero impacto en hashes.

## Decisión

Opción elegida: **B**.

Mecánica completa:

1. **partition_worker** (`apps/ctr-service/.../workers/partition_worker.py`):
   al persistir `episodio_abandonado` setea `ep.estado = "paused"`. Cualquier
   evento posterior sobre un episodio `paused` lo repone a `"open"` (la
   reanudación es derivable de la cadena, no necesita evento propio).
2. **`POST /api/v1/episodes/{id}/resume`** (tutor-service): reconstruye la
   sesión Redis desde `GET episodes/{id}` del ctr-service —
   `seq = events_count`, historia user/assistant desde
   `prompt_enviado`/`tutor_respondio`, último código desde
   `edicion_codigo`/`codigo_ejecutado`, prompt del sistema con la MISMA
   `prompt_system_version` del episodio (los eventos nuevos conservan el
   `prompt_system_hash` original), contexto de ejercicio (ADR-048) y
   `materia_id` (ADR-040) re-resueltos best-effort. NO emite evento.
   Validaciones: dueño del episodio (`student_pseudonym == X-User-Id`),
   tenant, TP vigente (las mismas 5 condiciones de apertura — pasado el
   deadline el episodio queda pausado para el docente pero no se retoma).
   Idempotente si la sesión ya existe.
3. **Gate de consistencia de `seq`**: solo se reanuda con `estado="paused"`
   (garantiza que el `episodio_abandonado` ya fue drenado del stream: el
   estado lo setea el worker AL persistirlo, y sin sesión nadie pudo emitir
   nada después) o `estado="open"` sin sesión viva (heal de episodios
   huérfanos por TTL de Redis vencido sin abandono).
4. **Visibilidad docente**: `list_episodes_with_classifications_for_student`
   (platform-ops) incluye `estado IN ("closed", "paused")` y expone `estado`;
   el drill-down longitudinal del web-teacher muestra el badge "En pausa"
   (los pausados ordenan primero — `closed_at` NULL, nullsfirst).
5. **web-student**: la hidratación de `EpisodePage` reanuda automáticamente si
   `estado == "paused"` (caso F5 / reingreso directo); `materia.$id` retoma el
   episodio pausado de la misma TP **y mismo contexto de ejercicio** en vez de
   abrir uno nuevo (el contexto sale de `ejercicio_id` en el
   `EpisodeStateResponse`, derivado del payload de `episodio_abierto`).

## Consecuencias

### Positivas
- Cero cambios en contratos de eventos, hashing, labeler o classifier.
- El intento del alumno queda en UNA cadena, no fragmentado en N episodios.
- El docente ve los abandonos pendientes sin esperar al cierre.

### Negativas / trade-offs
- La reanudación no deja marca propia en la cadena (es derivable, no
  explícita): el análisis forense debe inferirla de
  `episodio_abandonado` + eventos posteriores.
- El classifier sigue clasificando SOLO episodios cerrados; un episodio
  pausado para siempre nunca se clasifica (igual que antes este ADR — el
  abandono ya no cerraba el episodio).
- Episodios `paused` cuya TP venció quedan pausados indefinidamente; limpieza
  (cierre administrativo batch) es agenda futura si molesta en los listados.

### Neutras
- `estado` del Episode pasa de binario open/closed a ternario
  open/paused/closed. Los consumidores que filtraban `== "closed"` no ven
  diferencia; los que filtraban `== "open"` ahora pueden ver menos episodios
  "colgados" (eso era un bug, no una feature).
