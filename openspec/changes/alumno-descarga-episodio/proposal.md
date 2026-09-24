# El alumno descarga su episodio cerrado como archivo de código + charla

## Qué y por qué
Después de entregar/cerrar un episodio, el alumno puede **descargar un archivo de
código fuente** (`.py` o `.java` según el ejercicio) con **su código final** más
**su conversación con el tutor** incluida como comentarios. Le sirve para tener un
registro de lo que hizo y cómo llegó — su propio material de estudio.

## Alcance
- **Frontend-only** (web-student). NO se toca backend, CTR/hashing, ni el prompt del tutor.
- Se **compone** desde un endpoint ya existente: `GET /api/v1/episodes/{id}`
  (`getEpisodeState` en `web-student/src/lib/api.ts`) devuelve en una llamada
  `last_code_snapshot` (código final) + `messages` (transcript user/assistant),
  incluso para episodios cerrados. Sin endpoint nuevo.
- Descarga en cliente: Blob de texto + `<a download>` (patrón ya usado en
  web-teacher `CorreccionesView.tsx`).

## Formato del archivo
- Extensión según `ejercicio.language` (`.py` para Python, `.java` para Java) —
  NO asumir Python. Para Programación 1 sale `.py`.
- Contenido: encabezado (ejercicio, fecha) + código final del alumno + la charla
  alumno↔tutor como comentarios (`#` en Python, `//` en Java) al pie. El archivo
  debe ser sintácticamente válido (la charla va SIEMPRE comentada).

## Gobierno de privacidad
- El alumno descarga SU PROPIO episodio. El endpoint es dueño-o-nada
  (`student_pseudonym == user.id`, sin bypass por rol) — sin riesgo cross-student.
- El transcript sólo trae contenido alumno↔tutor; el **system prompt (Ana Garis)
  NO se expone** (no es evento CTR, nunca entra en `messages`). No reproducir ni
  inferir el system prompt en el archivo.
- La regla `include_prompts=False` es del export académico del docente — NO aplica
  acá (el alumno viendo su propia charla ya ocurre en la UI en vivo).

## No incluye
- Backend nuevo. Export masivo. Nada del lado docente.

## Knowledge Base Impact
none — feature de presentación/descarga en frontend; no cambia modelo, reglas ni arquitectura.
