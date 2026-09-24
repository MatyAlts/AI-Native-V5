# Tasks — alumno-descarga-episodio

Frontend-only (web-student). Helper puro con TDD; la descarga en sí se verifica
con test del helper + verificación manual del click.

## Lote 1 — armado del archivo (helper puro, TDD)
- [ ] ADE-01 · `buildEpisodioSourceFile({ code, messages, language, meta })` —
      función pura que devuelve `{ filename, content }`.
      - Extensión y estilo de comentario según `language` ("python" → `.py`, `#`;
        "java" → `.java`, `//`). Default python si falta.
      - `content` = encabezado comentado (ejercicio/tarea + fecha) + `code` tal
        cual + la charla `messages` (user/assistant) al pie, TODA comentada línea
        por línea (para que el archivo sea válido). Sin `code` → placeholder
        comentado, no revienta.
      - `filename` legible y seguro (slug del ejercicio + extensión).
      Test (rojo primero): python vs java (extensión + prefijo de comentario);
      charla multilinea comentada correctamente; sin código; sin mensajes.

## Lote 2 — affordance de descarga
- [ ] ADE-02 · Botón "Descargar (.py/.java)" en la UI del alumno para un ejercicio
      con episodio cerrado (candidato: `ExerciseListView.tsx`, que ya tiene el
      `episode_id` vía `entrega.ejercicio_estados`). Al click: `getEpisodeState`
      (código + messages), arma con ADE-01, y descarga con Blob + `<a download>`
      (patrón de `web-teacher/CorreccionesView.tsx`). Estados de carga/error.
      No romper la lista existente. Verificación manual del click + test del wiring
      donde sea testeable.

## Gates duros
- Solo web-student. NO backend, NO CTR/hashing, NO prompt del tutor,
  NO secrets/OpenRouter.
- NO exponer el system prompt: usar SOLO `messages` (alumno↔tutor) del endpoint.
- Reusar `getEpisodeState`/`EpisodeStateResponse` de `lib/api.ts`; no redefinir contratos.
- `tsc --noEmit` verde + suite web-student sin regresión.
