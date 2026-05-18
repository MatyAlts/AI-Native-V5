# ADR-044 — Esqueleto técnico de Fase B (`socratic_compliance`) detrás de feature flag

- **Estado**: Aceptado
- **Fecha**: 2026-05-09
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: tutor, guardrails, fase-b, mejora-4-plan-post-piloto-1, eje-c-preparacion
- **Supersede PARCIAL**: ADR-027. La decisión de DIFERIR la activación se mantiene; lo que este ADR cierra es la disponibilidad del esqueleto técnico listo para activación post-validación intercoder.
- **Cierra parcialmente**: Mejora 4 del plan documentado en `mejoras.docx` (componente técnico; el componente humano sigue abierto).

## Contexto y problema

ADR-027 documentó la decisión doctoral explícita de **DIFERIR** la Fase B de los guardrails (postprocesamiento de respuestas del tutor + cálculo de `socratic_compliance` y `violations` en el `TutorRespondioPayload`) a Eje C post-defensa, con tres condiciones acumuladas para la revisita: validación intercoder κ ≥ 0,6 sobre 50+ respuestas etiquetadas por dos docentes independientes, acuerdo académico sobre la fórmula del score, y consenso de no afectar el árbol de clasificación pre-validación.

La justificación operativa central del ADR-027 es: *"Un score mal calculado es peor que ninguno. El campo queda como `None` en eventos hasta que la calibración con docentes valide el cálculo."* Esta cláusula impide activar la Fase B en runtime hasta que la validación humana exista — y la validación humana no es accionable por el equipo técnico solo.

El plan de mejoras post-piloto-1 (`mejoras.docx`) propuso atacar esta limitación como Mejora 4 del orden recomendado. Sin la calibración intercoder, no se puede prender el postprocess en producción. Pero el código técnico — detector regex sobre la respuesta, fórmula provisoria del score, integración en el flow del tutor, hash determinista del corpus, batería de tests — sí es accionable autónomamente y, una vez listo, reduce el lead-time de activación cuando la validación esté disponible (de "varias semanas de implementación + tests" a "días de calibración del threshold final + flag flip").

El presente ADR materializa la decisión de **implementar el esqueleto técnico de la Fase B con activación bloqueada por feature flag** durante el período entre el cierre de v1.0.0 del piloto y la disponibilidad del corpus de validación intercoder con docentes.

## Decisión

Se implementa la Fase B del régimen de guardrails como **esqueleto técnico completo gateado por feature flag OFF en config**. Específicamente:

1. **Módulo `apps/tutor-service/src/tutor_service/services/postprocess_socratic.py`** con función pura `postprocess(response_content: str) -> PostprocessResult`. Devuelve `socratic_compliance: float` en `[0, 1]` y `violations: list[Violation]`. Función pura, idempotente, sin side-effects, determinista bit-a-bit. Patrón canónico del corpus hash idéntico a `guardrails_corpus_hash` (ADR-043) y `classifier_config_hash` (ADR-009).

2. **Feature flag `socratic_compliance_enabled: bool = False`** en `apps/tutor-service/src/tutor_service/config.py`. Por default OFF. Mientras esté OFF:
   - El `postprocess` NO se invoca desde `tutor_core.interact()`.
   - El campo `TutorRespondioPayload.socratic_compliance` persiste como `None`.
   - El campo `TutorRespondioPayload.violations` persiste como lista vacía `[]`.
   - **Garantía preservada**: la cláusula del ADR-027 ("el campo queda `None` hasta que la calibración con docentes valide el cálculo") se respeta literalmente en runtime.

3. **Hook en `apps/tutor-service/src/tutor_service/services/tutor_core.py::interact()`** ubicado entre la finalización del stream del LLM (línea 481, post `state.messages.append`) y la emisión del evento `tutor_respondio` (línea 488). El hook lee `settings.socratic_compliance_enabled`; si OFF, salta al emit con `socratic_compliance=None, violations=[]`. Si ON, llama al `postprocess` sobre la respuesta acumulada y popula los campos del payload con el resultado. **Patrón fail-soft**: cualquier excepción del postprocess es capturada y loggeada sin bloquear el turno (mismo patrón que el detector regex de Fase A en ADR-019 y el `OveruseDetector` de ADR-043).

4. **Corpus determinista**: `SOCRATIC_CORPUS_VERSION = "1.0.0"`, `SOCRATIC_CORPUS_HASH` calculado con la misma fórmula canónica que el resto del sistema. Bumpear cualquier patrón regex, peso o severidad cambia el hash; eventos `tutor_respondio` futuros (cuando el flag se prenda) quedarán etiquetados con el hash que el corpus tenía al computarlos. Eventos persistidos durante el período de flag OFF NO llevan corpus_hash en su payload (porque el postprocess no se invoca).

### Heurísticas provisorias del corpus v1.0.0

Tres categorías de violación, todas sujetas a validación intercoder κ pre-activación:

- **`code_block_complete`** (severidad informativa 3, peso 0,4): bloque fenced (` ``` ... ``` `) con cuerpo de más de 200 caracteres. Captura el patrón "el tutor dio la solución completa en un bloque". Una ilustración corta de 1-3 líneas NO matchea — threshold deliberadamente conservador.
- **`no_question_in_response`** (severidad informativa 2, peso 0,3): ausencia literal de "?" o "¿" en cualquier parte de la respuesta. Captura el patrón "el tutor afirmó sin preguntar". Heurística simple por diseño — distinguir preguntas implícitas requiere análisis semántico (Eje C).
- **`direct_answer`** (severidad informativa 3, peso 0,3): regex sobre imperativos típicos de respuesta directa ("la solución es", "el código es", "tenés que", "debés hacer", "simplemente hacé/escribí/usá"). Captura el patrón "el tutor instruyó en lugar de guiar".

### Fórmula del score

```
penalty = sum(_WEIGHTS[c] for c in categorías_distintas_presentes)
socratic_compliance = max(0.0, min(1.0, 1.0 - penalty))
```

Pesos suman exactamente `1.0` (`0.4 + 0.3 + 0.3`) para que las tres violaciones simultáneas saturen el score a `0`. La severity NO escalea el cálculo del score — se reporta como metadata en cada `Violation` para observabilidad pedagógica pero queda desacoplada de la fórmula. Una respuesta vacía devuelve `socratic_compliance=0.5` (neutral) sin violations.

## Drivers de la decisión

- **D1**: respetar literalmente la cláusula `None` del ADR-027 mientras se prepara el terreno para activación. La feature flag OFF garantiza que el contrato observable del CTR no cambia hasta que la validación humana exista.
- **D2**: reducir lead-time entre disponibilidad del corpus humano y activación. La calibración intercoder no requiere implementar nada nuevo — solo tomar el corpus etiquetado, computar κ, ajustar thresholds/pesos, bumpear `SOCRATIC_CORPUS_VERSION`, y prender el flag.
- **D3**: preservar la propiedad de reproducibilidad bit-a-bit del corpus. Mismo patrón canónico que `guardrails_corpus_hash` y `classifier_config_hash`. Permite auditar exactamente qué fórmula se usó para cada respuesta del tutor cuando el flag esté ON.
- **D4**: NO modificar el contrato del `TutorRespondioPayload`. Los campos `socratic_compliance: float | None` y `violations: list[str]` ya existen desde F8 — populamos lo que ya está en el contract.
- **D5**: mantener el principio fail-soft. Una excepción del postprocess no debe bloquear el turno del estudiante, igual que la Fase A.
- **D6**: NO afectar el árbol de clasificación. El `socratic_compliance` se persiste pero NO entra al `Classification.features` (ya está en `_EXCLUDED_FROM_FEATURES`-equivalent por el hecho de que el classifier opera sobre eventos pre-cierre y `tutor_respondio` no está excluido pero su payload nuevo no se lee por el classifier hoy). Documentado para que cualquier cambio futuro al árbol que quiera leer este campo requiera ADR explícito.

## Opciones consideradas

### Opción A — Esqueleto técnico con feature flag OFF (elegida)

Ya descrita en la sección Decisión.

**Ventajas**:
- Cumple ADR-027 literalmente: el campo persiste `None` mientras el flag esté OFF.
- Reduce drásticamente el lead-time de activación post-validación humana.
- Permite tests deterministas autónomos sobre la fórmula provisoria — el equipo técnico itera en confianza sin esperar al corpus humano.
- Patrón fail-soft + flag-gating es estándar y auditable.

**Desventajas**:
- El módulo `postprocess_socratic.py` queda en el codebase como código no ejecutado en runtime — un lector casual podría asumir que está activo. Mitigación: docstring del módulo + bullet en CLAUDE.md + descripción en `docs/limitaciones-declaradas.md` que dejan claro el estado.
- La fórmula provisoria puede cambiar tras validación intercoder — si los pesos/thresholds finales son muy distintos, el "esqueleto" es 50% reescritura. Mitigación: el costo de mantener el flag OFF + tests deterministas durante el ínterin es bajo; rebalanceo de pesos cambia el hash y bumpea la versión del corpus, comportamiento ya soportado.

### Opción B — Esperar a la validación humana antes de implementar nada

Mantener el estado del ADR-027 sin cambios: no escribir código de Fase B hasta que la calibración intercoder esté disponible.

**Desventajas que la descartan**:
- Lead-time entre disponibilidad del corpus humano y rollout de Fase B en producción se vuelve "varias semanas" (implementación + tests + ADR + revisión) en lugar de "días" (calibración del threshold + flip del flag).
- El equipo técnico no puede iterar sobre la fórmula sin el código existente. La validación intercoder docente requiere comparar respuestas etiquetadas humanas vs respuestas etiquetadas por el postprocess — sin postprocess implementado no hay nada que comparar.

### Opción C — Implementar Fase B sin feature flag, dejando `None` hardcodeado

Implementar el módulo y dejar el hook en `tutor_core` siempre invocando, pero forzar `socratic_compliance=None, violations=[]` con un `# TODO` antes del emit.

**Desventajas que la descartan**:
- El código en producción que se ejecuta pero descarta su resultado es señal mala — código muerto activo, costoso de razonar, difícil de auditar.
- No hay forma limpia de prender la Fase B sin un PR que cambie lógica de runtime — un flag flip es operacional, no arquitectónico.

## Criterios de éxito

1. La feature flag `socratic_compliance_enabled: bool = False` está documentada en `config.py` con justificación inline al ADR-027 + ADR-044.
2. El módulo `postprocess_socratic.py` exporta `postprocess`, `compute_socratic_corpus_hash`, `SOCRATIC_CORPUS_HASH`, `SOCRATIC_CORPUS_VERSION = "1.0.0"`, y los dataclasses `Violation` + `PostprocessResult`.
3. La función `postprocess` es pura, idempotente, determinista bit-a-bit. Verificado por test golden hash en `apps/tutor-service/tests/unit/test_postprocess_socratic.py::test_corpus_hash_golden`.
4. El hook en `tutor_core.interact()` respeta el flag: con OFF, los campos del payload son `None` y `[]`; con ON, los campos se populan con el resultado del postprocess.
5. Patrón fail-soft validado: una excepción del postprocess no rompe el turno del estudiante.
6. Trío de docs sincronizados: `CLAUDE.md` con bullet en "Constantes que NO deben inventarse" + invariante; `docs/limitaciones-declaradas.md` Limitación 4 con estado actualizado al esqueleto-OFF; `loquehace.md` §13 con la corrección de prosa.
7. SESSION-LOG entry del 2026-05-09 con los pasos ejecutados.

## Criterio de revisita (para activación)

Las tres condiciones del ADR-027 siguen aplicando para flippear el flag a ON:

1. Validación κ con docentes: subset etiquetado a mano de respuestas del tutor, mínimo 50 respuestas, 2 etiquetadores independientes, target κ ≥ 0,6.
2. Acuerdo académico sobre la fórmula final del score (puede mantener la v1.0.0 o requerir bump a 1.1.0+ con rebalanceo de pesos/thresholds).
3. Consenso de no afectar el árbol de clasificación pre-validación.

Cuando las tres se cumplan, el procedimiento de activación es:
- Bumpear `SOCRATIC_CORPUS_VERSION` si la fórmula cambió, recalcular `SOCRATIC_CORPUS_HASH` golden y actualizar test.
- Flip del flag a `True` en producción.
- Coordinar con el equipo de analytics para que los reportes empíricos del piloto-2 incluyan análisis del nuevo campo (HU futura).

## Consecuencias

### Positivas

- ADR-027 se respeta literalmente — `None` y `[]` en runtime mientras flag OFF.
- Lead-time de activación post-validación reducido a días.
- Tests deterministas autónomos sobre la fórmula provisoria.
- Hash determinista del corpus permite auditar reproducibilidad bit-a-bit cuando flag se prenda.
- Patrón consistente con ADR-043 (overuse) — flag-gated, fail-soft, hash-determinista.

### Negativas

- Código no ejecutado en runtime durante el período del piloto. Mitigado por docstring + CLAUDE.md + `limitaciones-declaradas.md`.
- Fórmula provisoria puede invalidarse parcialmente con la calibración real. Mitigado por el versionado del corpus.

### Neutras

- El contrato del `TutorRespondioPayload` no cambia (los campos ya existían como opcionales desde F8).
- El `classifier_config_hash` no cambia.
- El árbol de clasificación N4 no se ve afectado.

## Referencias

- ADR-027 — DIFERIR la Fase B (decisión doctoral explícita preservada por este ADR).
- ADR-019 — Fase A de guardrails (preprocesamiento de prompts).
- ADR-043 — `OveruseDetector` (mismo patrón flag-gated + fail-soft + corpus hash).
- ADR-009 — `prompt_system_hash` y patrón canónico de corpus hashes.
- Tesis Sección 8.5.1 — diseño del tutor con postprocesamiento.
- Tesis Sección 19.5 — gap declarado.
- `mejoras.docx` — plan post-piloto-1 con orden de mejoras.
- `docs/limitaciones-declaradas.md` — Limitación 4 actualizada al estado post-ADR-044.
- `apps/tutor-service/src/tutor_service/services/postprocess_socratic.py` — implementación.
- `apps/tutor-service/tests/unit/test_postprocess_socratic.py` — tests deterministas.
