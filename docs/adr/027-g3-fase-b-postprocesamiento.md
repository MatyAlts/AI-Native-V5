# ADR-027 — G3 Fase B: postprocesamiento de respuesta del tutor + `socratic_compliance` (DIFERIDO a Eje C post-defensa)

- **Estado**: Aceptado (decisión: **DIFERIR**, no implementar pre-defensa)
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: tutor, guardrails, classifier, eje-c, agenda-confirmatoria
- **Extiende**: ADR-019 (G3 Fase A — preprocesamiento de prompts adversos).
- **Cierra**: G13 del audi2.md.

## Contexto y problema

ADR-019 cerró la Fase A de los guardrails: detección heurística regex de patrones adversos en el **prompt del estudiante**, antes del envío al LLM, con emisión de `intento_adverso_detectado`. Esa Fase A está documentada como **"Fase A SOLO"** y declara que la Fase B queda fuera de scope de v1.x.

La Fase B propuesta:

1. **Postprocesamiento de la respuesta del tutor** (no del prompt).
2. **Cálculo de `socratic_compliance: float | None`**: score [0,1] que mide qué tan socrática fue la respuesta del tutor según el rol declarado en el prompt v1.0.x.
3. **Persistencia en `TutorRespondioPayload`**: el campo ya está en el contract (F8 lo agregó como opcional). En runtime hoy queda **permanentemente `None`** — señal explícita de gap.

La tesis 8.5.1 describe el postprocesamiento como parte del diseño del tutor; la 19.5 lo declara como gap. No hay incoherencia en la tesis (el modelo híbrido funciona), pero el campo `None` permanente es señal observable.

## Decisión

**DIFERIR**. El RESUMEN-EJECUTIVO confirma esta decisión: *"Un score mal calculado es peor que ninguno. El campo queda como `None` en eventos hasta que la calibración con docentes valide el cálculo."*

### Por qué

- **El score requiere validación κ contra juicio docente** (mismo protocolo que el clasificador N4, Capítulo 14). Sin esa validación es decisión arbitraria con apariencia de rigor.
- **Falsos positivos pedagógicos**: una respuesta legítima del tutor penalizada como "no socrática" ensucia los reportes empíricos del piloto-1. La Fase B exige más rigor que la Fase A porque cambia interpretación, no solo registra señal.
- **Riesgo de reclasificación**: si el classifier empieza a leer `socratic_compliance` para ajustar el árbol de decisión (sin estarlo hoy), bumpea `classifier_config_hash` y obliga a recomputar todas las `Classification`s del piloto.

## Criterio para revisitar (Eje C post-defensa)

Implementar G13 cuando se cumpla **todo** lo siguiente:

1. **Validación κ con docentes**: subset etiquetado a mano de respuestas del tutor con score "socrático compliant" vs "no compliant" según juicio docente (mínimo 50 respuestas, 2 etiquetadores independientes, target κ ≥ 0.6 igual que el clasificador N4).
2. **Acuerdo académico sobre el cálculo**: el ADR de la implementación documenta la fórmula de `socratic_compliance` con la misma rigurosidad que `classifier_config_hash` y `guardrails_corpus_hash` (reproducibilidad bit-a-bit).
3. **Consenso de no afectar el árbol de clasificación pre-validación**: incluso después de implementarlo, `socratic_compliance` se persiste pero **no entra al árbol** hasta validación κ explícita.

### Implementación propuesta (referencia)

audi2.md G13 detalla `apps/tutor-service/src/tutor_service/services/postprocess.py` con tres módulos:

1. **Detector de patrones en la respuesta del tutor**: regex análoga a `guardrails.py` pero sobre el output. Detecta:
   - Bloque de código completo en respuesta a un prompt tipo "dame la solución" → penaliza compliance.
   - Respuesta sin pregunta al final → penaliza si el prompt era reflexivo.
   - Off-topic → la respuesta no menciona conceptos del prompt.
2. **Cálculo de `socratic_compliance`**: score [0,1] derivado de las penalizaciones. Documentar fórmula reproducible bit-a-bit.
3. **Inclusión en `tutor_respondio`**: llenar `socratic_compliance: float`, `violations: list[str]`. Los campos ya están en el contract.

LOC estimado: ~250 (detector + score + tests + corpus regex).

## Consecuencias de DIFERIR

### Positivas

- El campo `socratic_compliance: float | None` permanece `None` en runtime — señal explícita y honesta de gap.
- Cero coordinación con calibración docente durante el piloto-1.
- `prompt_system_hash` y `classifier_config_hash` permanecen estables.

### Negativas

- La promesa textual de "postprocesamiento" en la 8.5.1 queda como agenda observable.
- El reporte empírico del piloto-1 NO incluye análisis de `socratic_compliance` por episodio (sólo análisis de `intento_adverso_detectado` de la Fase A).

## Referencias

- audi2.md G13 — propuesta detallada.
- ADR-019 — Fase A (preprocesamiento), cerrada en iter 1.
- Tesis Sección 8.5.1 — diseño del tutor con postprocesamiento.
- Tesis Sección 19.5 — gap declarado.
- `docs/RESUMEN-EJECUTIVO-2026-04-27.md` — confirmación explícita de DIFERIR.
- Capítulo 14 — protocolo de validación κ docente (referencia para el criterio).
