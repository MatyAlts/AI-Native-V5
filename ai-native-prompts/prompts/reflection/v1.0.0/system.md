# Cuestionario de reflexion metacognitiva post-episodio (v1.0.0)

Cuestionario opcional que el estudiante responde inmediatamente despues de
cerrar un episodio practico. NO es un prompt al LLM — es la fuente declarativa
de las preguntas que el frontend (web-student) renderiza en el modal.

El governance-service lo expone para que dashboards puedan mostrar la version
activa, pero el tutor-service NO lo consume en runtime (la modal vive en el
cliente). El prompt_version queda como metadata trazable en el evento CTR
`reflexion_completada`.

## Proposito

Capturar la metacognicion del estudiante sobre la sesion que acaba de
terminar: que aprendio, que le costo, que cambiaria. Es feedback longitudinal
para la tesis (Seccion 8.6, reflexion guiada como cierre del ciclo socratico)
y NO entra al classifier — la presencia/ausencia de reflexion no afecta
features ni `classifier_config_hash` (ADR-035).

## Reglas duras

1. **Opcional.** El estudiante puede saltear el modal con un boton "Saltar".
   En ese caso NO se emite el evento `reflexion_completada` y el episodio
   sigue cerrado igual (el `EpisodioCerrado` ya se appendeo al CTR).
2. **No bloqueante.** El cierre del episodio NO espera la respuesta. Son
   flujos independientes — el modal aparece DESPUES del POST de close.
3. **Privacy.** El contenido textual viaja al CTR como string libre. El
   estudiante puede meter info identificable; por eso el export academico
   redacta los 3 campos por default. Investigador con consentimiento usa
   `--include-reflections` (audit log structlog).
4. **Cap de longitud.** Cada campo `<= 500 chars`. El frontend valida y el
   endpoint del tutor-service rechaza con 422 si se excede.

## Preguntas (frontend renderiza textareas con estos labels)

1. **Que aprendiste?**
   `que_aprendiste` — texto libre, max 500 chars.
   Hint UI: "En una o dos lineas, que cosa nueva entendiste o reforzaste".

2. **Que dificultad encontraste?**
   `dificultad_encontrada` — texto libre, max 500 chars.
   Hint UI: "Donde te quedaste trabado, que parte costo mas".

3. **Que harias distinto la proxima?**
   `que_haria_distinto` — texto libre, max 500 chars.
   Hint UI: "Si volvieras a empezar este ejercicio, que cambiarias en tu
   forma de encararlo".

## Payload del evento CTR

El frontend pega `POST /api/v1/episodes/{id}/reflection` con:

```json
{
  "que_aprendiste": "string <= 500 chars",
  "dificultad_encontrada": "string <= 500 chars",
  "que_haria_distinto": "string <= 500 chars",
  "tiempo_completado_ms": 0,
  "prompt_version": "reflection/v1.0.0"
}
```

El tutor-service emite un evento `reflexion_completada` al CTR con ese
payload + metadata estandar (event_uuid, episode_id, tenant_id, seq, ts,
prompt_system_hash, prompt_system_version, classifier_config_hash).

## Versionado

Bump MINOR (`v1.1.0`) si se agregan/quitan preguntas o se reescribe el
copy. Bump MAJOR (`v2.0.0`) si cambia la estructura del payload (rompe
contratos historicos). El campo `prompt_version` del evento permite
distinguir reflexiones capturadas con cuestionarios diferentes en analisis
longitudinal.
