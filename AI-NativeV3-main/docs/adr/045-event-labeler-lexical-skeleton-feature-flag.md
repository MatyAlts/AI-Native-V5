# ADR-045 — Esqueleto técnico del override léxico de `anotacion_creada` (G8b) detrás de feature flag

- **Estado**: Aceptado
- **Fecha**: 2026-05-09
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: classifier, instrumentación, labeler, mejora-3-plan-post-piloto-1, eje-b-preparacion
- **Supersede PARCIAL**: ADR-023. La sección "G8b sigue como agenda" del ADR-023 se cierra técnicamente; G8c (semántico vía embeddings) sigue siendo agenda Eje B post-defensa, fuera de scope.
- **Cierra parcialmente**: Mejora 3 del plan documentado en `mejoras.docx` (sub-componente G8b léxico; sub-componente G8c semántico queda fuera de scope).

## Contexto y problema

ADR-023 cerró el sesgo sistemático del labeler v1.0.0 sobre `anotacion_creada` mediante un override por **posición temporal** del evento dentro del episodio (heurística G8a, `LABELER_VERSION` 1.0.0 → 1.1.0). El propio ADR-023 documentó tres opciones del trifecta G8a/G8b/G8c, eligió G8a por ser la única implementable autónomamente sin gates humanos, y dejó G8b (heurístico léxico sobre el contenido textual de la anotación) y G8c (clasificación semántica vía embeddings) como agenda explícita.

La sub-mejora **G8b** descrita en ADR-023 sección "G8b — heurístico léxico" propone reglas regex sobre el contenido de la anotación: patrones tipo "estoy leyendo" / "el enunciado pide" → N1; patrones tipo "ahora entiendo" / "tras la respuesta" → N4. ADR-023 la descartó para pre-defensa con la justificación textual: *"requiere validación κ contra juicio docente sobre subset etiquetado a mano (mismo protocolo que el clasificador N4, Capítulo 14). Sin esa validación el corpus regex es decisión arbitraria con apariencia de rigor — peor que declararlo como heurística temporal honesta."*

El plan de mejoras post-piloto-1 (`mejoras.docx`) ataca esta limitación como Mejora 3 del orden recomendado. G8b tiene un gate humano explícito (validación intercoder κ ≥ 0,6 sobre 50+ anotaciones etiquetadas por 2 docentes independientes); G8c tiene **además** un gate arquitectónico (endpoint nuevo en `ai-gateway`, integración con embeddings, decisiones de modelo). Ambos sub-componentes no son ejecutables completamente sin coordinación humana.

El presente ADR materializa la decisión de **implementar el esqueleto técnico de G8b con activación bloqueada por feature flag OFF**, replicando exactamente el patrón ya validado por ADR-044 (Fase B socratic_compliance, Mejora 4 del mismo plan). La activación real depende del corpus humano de calibración, idéntica restricción que ADR-027/ADR-044. **G8c queda fuera de scope** del presente ADR — el esqueleto-OFF aplica a soluciones cuya activación es flag-flip, no a soluciones que requieren arquitectura nueva.

## Decisión

Se implementa el override léxico de `anotacion_creada` (G8b) como **esqueleto técnico completo gateado por feature flag OFF en config**. Específicamente:

1. **Módulo `apps/classifier-service/src/classifier_service/services/event_labeler_lexical.py`** con función pura `lexical_label(content: str) -> LexicalLabel | None`. Devuelve `"N1"`, `"N4"`, o `None` cuando el contenido no matchea el corpus. Función pura, idempotente, sin side-effects, determinista bit-a-bit. Patrón canónico del corpus hash idéntico a `socratic_corpus_hash` (ADR-044), `guardrails_corpus_hash` (ADR-043) y `classifier_config_hash` (ADR-009).

2. **Feature flag `lexical_anotacion_override_enabled: bool = False`** en `apps/classifier-service/src/classifier_service/config.py`. Por default OFF. Mientras esté OFF:
   - El módulo `event_labeler_lexical` NO se invoca desde `event_labeler.label_event()`.
   - El override temporal v1.1.0 (ADR-023) sigue siendo el único que actúa sobre `anotacion_creada`.
   - **Garantía preservada**: las classifications históricas del piloto-1 mantienen el `classifier_config_hash` y `LABELER_VERSION="1.2.0"` con los que fueron computadas. Reproducibilidad bit-a-bit intacta.

3. **Hook en `apps/classifier-service/src/classifier_service/services/event_labeler.py::label_event()`** dentro del bloque `if event_type == "anotacion_creada"`, ANTES del override temporal v1.1.0. El hook lee `settings.lexical_anotacion_override_enabled`; si OFF, salta directo al override temporal (comportamiento idéntico a v1.1.0). Si ON, invoca `lexical_label(content)` sobre el contenido textual de la anotación; si retorna `"N1"` o `"N4"`, esa es la etiqueta final (gana sobre el override temporal). Si retorna `None`, cae al override temporal v1.1.0 como fallback. **Patrón fail-soft**: cualquier excepción del módulo léxico es capturada silenciosamente y el flow cae al fallback temporal — el labeler nunca se rompe.

4. **Corpus determinista**: `LEXICAL_CORPUS_VERSION = "1.0.0"`, `LEXICAL_CORPUS_HASH` calculado con la misma fórmula canónica que el resto del sistema. Bumpear cualquier patrón regex cambia el hash. Eventos `anotacion_creada` etiquetados durante el período de flag OFF NO llevan `lexical_corpus_hash` en su contexto (el módulo no se invoca); cuando el flag se prenda, las classifications recomputadas con el labeler v2.0.0 llevarán el corpus_hash en su payload extendido (esquema a definir post-validación intercoder).

### Heurísticas provisorias del corpus v1.0.0

Dos categorías léxicas, ambas sujetas a validación intercoder κ pre-activación:

**N1 — comprensión / lectura inicial** (4 patrones provisorios):
- `n1_estoy_leyendo_v1_0_0`: matchea "estoy leyendo" (case-insensitive).
- `n1_enunciado_pide_v1_0_0`: matchea "el enunciado/la consigna" + verbo de mandato ("pide", "dice", "menciona", "exige", "requiere").
- `n1_no_entiendo_todavia_v1_0_0`: matchea "no entiendo todavía" / "todavía no entiendo" / "todavía no me queda claro".
- `n1_me_piden_v1_0_0`: matchea "me piden (que)" / "tengo que (entender|leer|comprender|interpretar)".

**N4 — apropiación post-tutor** (4 patrones provisorios):
- `n4_ahora_entiendo_v1_0_0`: matchea "ahora (entiendo|veo|me doy cuenta|comprendo|capto)".
- `n4_tras_la_respuesta_v1_0_0`: matchea "tras/después de/con la respuesta".
- `n4_siguiendo_consejo_v1_0_0`: matchea "siguiendo (el consejo|la pista|la sugerencia|lo que)".
- `n4_el_tutor_v1_0_0`: matchea "el tutor (me dijo|sugirió|propuso|explicó|me ayudó)".

### Precedencia

Cuando el contenido matchea ambos N4 y N1, gana **N4**. Mismo criterio pedagógico que el override temporal v1.1.0 cuando ambas ventanas matchean: la señal de apropiación post-tutor es más informativa que la señal de lectura inicial.

### Precedencia entre overrides (cuando flag se prenda)

El hook está ubicado de manera que el léxico tiene **precedencia sobre el temporal**. Una anotación que el corpus léxico clasifica como N1 o N4 mantiene esa etiqueta aunque su posición temporal contradiga (por ejemplo, una anotación con texto "ahora entiendo lo que dice el enunciado" en los primeros 120s del episodio se etiqueta N4 por contenido, no N1 por posición). Cuando el corpus léxico devuelve `None`, el override temporal v1.1.0 actúa como fallback. Esta precedencia es la que justifica el bump a `LABELER_VERSION = "2.0.0"` cuando el flag se prenda — cambio semántico mayor en la regla de etiquetado.

## Drivers de la decisión

- **D1**: cumplir la promesa textual del ADR-023 sobre G8b sin violar la cláusula de validación humana. La feature flag OFF garantiza que el comportamiento del labeler no cambia hasta que la validación humana exista.
- **D2**: reducir el lead-time entre disponibilidad del corpus humano y activación. Mismo argumento que ADR-044 — la calibración intercoder no requiere implementar nada nuevo, solo κ + ajuste de patrones + bump de versión + flag flip.
- **D3**: preservar la propiedad de reproducibilidad bit-a-bit del classifier_config_hash sobre todas las classifications históricas del piloto-1. Mientras el flag esté OFF, el labeler v1.1.0 permanece autoritativo; las classifications no se recomputan.
- **D4**: NO modificar la API pública de `label_event()`. Los callers existentes (`time_in_level`, `n_level_distribution`, pipeline) no necesitan cambios — el flag se lee internamente al `label_event` desde `settings`.
- **D5**: mantener el principio fail-soft. Una excepción del módulo léxico (corrupción de regex, payload malformado, etc.) NO debe romper el labeler — el override temporal v1.1.0 actúa como fallback automático.
- **D6**: NO modificar el contrato del CTR. El labeler es derivado en lectura (ADR-020). Cambios al labeler no tocan eventos persistidos. Lo único que cambia post-activación es el `LABELER_VERSION` que se propaga en `n_level_distribution` y `Classification.classifier_config_hash`.
- **D7**: tratar G8c (semántico) como agenda separada. Su gate arquitectónico (endpoint nuevo en `ai-gateway`) lo hace incompatible con el patrón esqueleto-OFF que asume "función pura + flag flip + golden hash". G8c sigue siendo Eje B post-defensa, sin esqueleto.

## Opciones consideradas

### Opción A — Esqueleto técnico de G8b con feature flag OFF (elegida)

Ya descrita en la sección Decisión.

**Ventajas**:
- Cumple ADR-023 literalmente: el comportamiento del labeler durante el piloto-1 no cambia.
- Reduce drásticamente el lead-time post-validación humana.
- Tests deterministas autónomos sobre el corpus provisorio.
- Patrón consistente con ADR-043 (overuse) y ADR-044 (socratic_compliance).
- Permite iteración sobre los patrones sin esperar al corpus humano (los patrones podrán refinarse contra ese corpus cuando esté disponible).

**Desventajas**:
- Módulo `event_labeler_lexical.py` queda en el codebase como código no ejecutado en runtime mientras flag OFF. Mitigación: docstring del módulo + bullet en `CLAUDE.md` + descripción en `docs/limitaciones-declaradas.md` que dejan claro el estado.
- La precedencia léxico > temporal puede invalidarse parcialmente con la calibración real (los docentes pueden preferir temporal > léxico, o requerir combinación más compleja). Mitigación: el bump a `LABELER_VERSION = "2.0.0"` post-activación incluye la posibilidad de cambiar la precedencia y el corpus.

### Opción B — Esperar a la validación humana antes de implementar nada

Mantener el estado del ADR-023 sin cambios. No escribir código de G8b hasta que la calibración intercoder esté disponible.

**Desventajas que la descartan**:
- Lead-time entre disponibilidad del corpus humano y rollout en producción se vuelve "varias semanas" en lugar de "días". Mismo argumento que descartó la Opción B en ADR-044.
- La validación intercoder docente requiere comparar etiquetas del módulo léxico vs etiquetas humanas. Sin módulo implementado no hay nada que comparar.

### Opción C — Activar G8b en producción sin validación intercoder

Implementar G8b y prenderlo directamente, asumiendo que los patrones provisorios son razonables.

**Desventajas que la descartan**:
- Viola explícitamente la cláusula textual del ADR-023: *"sin esa validación el corpus regex es decisión arbitraria con apariencia de rigor"*.
- Cambia el `LABELER_VERSION` a 2.0.0 sobre datos del piloto-1 sin justificación cuantitativa, contaminando los reportes empíricos con una operacionalización no validada.

### Opción D — Implementar G8c (semántico) directamente

Saltarse G8b e implementar el sub-componente más sustantivo de Mejora 3.

**Desventajas que la descartan**:
- Requiere endpoint nuevo en `ai-gateway`, integración con embeddings, decisiones de arquitectura — fuera del patrón esqueleto-OFF.
- ADR-023 explícitamente declara G8c como agenda Eje B post-defensa.
- El gate humano sigue presente: incluso con la arquitectura semántica lista, la validación intercoder seguiría siendo necesaria.

## Criterios de éxito

1. La feature flag `lexical_anotacion_override_enabled: bool = False` está documentada en `config.py` con justificación inline a ADR-023 + ADR-045.
2. El módulo `event_labeler_lexical.py` exporta `lexical_label`, `compute_lexical_corpus_hash`, `LEXICAL_CORPUS_HASH`, `LEXICAL_CORPUS_VERSION = "1.0.0"`.
3. La función `lexical_label` es pura, idempotente, determinista bit-a-bit. Verificado por test golden hash en `apps/classifier-service/tests/unit/test_event_labeler_lexical.py::test_corpus_hash_golden`.
4. El hook en `event_labeler.label_event()` respeta el flag: con OFF, comportamiento idéntico al v1.1.0; con ON, léxico tiene precedencia sobre temporal.
5. Patrón fail-soft validado: una excepción del módulo léxico NO rompe el labeler.
6. Trío de docs sincronizados: `CLAUDE.md` con bullet en "Constantes que NO deben inventarse"; `docs/limitaciones-declaradas.md` Limitación 3 reescrita al estado esqueleto-OFF; `loquehace.md` §13 con la corrección de prosa.
7. SESSION-LOG entry del 2026-05-09 con los pasos ejecutados.

## Criterio de revisita (para activación)

Las condiciones aplicables del ADR-023 se mantienen para flippear el flag a ON:

1. **Validación κ con docentes**: subset etiquetado a mano de anotaciones reales del piloto, mínimo 50 anotaciones, 2 etiquetadores independientes, target κ ≥ 0,6 sobre las dos categorías N1 y N4 (el clasificador léxico no etiqueta N2 explícitamente — N2 sigue siendo el fallback de `label_event` cuando ni el léxico ni el temporal asignan algo).
2. **Acuerdo académico sobre el corpus final** (puede mantener el v1.0.0 o requerir bump a 1.1.0+ con rebalanceo de patrones tras la calibración).
3. **Decisión sobre la precedencia** léxico vs temporal post-validación. La precedencia provisoria del esqueleto v1.0.0 es léxico > temporal; la calibración puede confirmar o invertir.
4. **Bump del `LABELER_VERSION`** a `"2.0.0"` con re-clasificación de classifications históricas del piloto post-activación. La reproducibilidad bit-a-bit del v1.1.0 sigue accesible recomputando con la versión anterior.

Cuando estas condiciones se cumplan, el procedimiento de activación es:
- Bumpear `LEXICAL_CORPUS_VERSION` si los patrones cambiaron, recalcular `LEXICAL_CORPUS_HASH` golden y actualizar test.
- Bumpear `LABELER_VERSION` a `"2.0.0"` con entrada en el historial del docstring del labeler.
- Flip del flag a `True` en producción.
- Re-clasificar las classifications históricas del piloto (cómputo derivado del CTR, no afecta eventos persistidos).
- Coordinar con analytics-service para que los reportes empíricos del piloto-2 incluyan las nuevas distribuciones N1/N4 sobre anotaciones.
- Actualizar la Sección 17.3 / 19.5 de la tesis sobre qué sesgo cierra la nueva versión.

## Consecuencias

### Positivas

- ADR-023 se respeta literalmente — comportamiento del labeler v1.1.0 invariante mientras flag OFF.
- Lead-time de activación post-validación reducido a días.
- Tests deterministas autónomos sobre el corpus provisorio.
- Hash determinista del corpus permite auditar reproducibilidad bit-a-bit cuando flag se prenda.
- Patrón consistente con ADR-043 (overuse) y ADR-044 (socratic_compliance) — flag-gated, fail-soft, hash-determinista.
- Reproducibilidad bit-a-bit del classifier_config_hash sobre classifications del piloto-1 intacta.

### Negativas

- Código no ejecutado en runtime durante el período del piloto. Mitigado por docstring + CLAUDE.md + `limitaciones-declaradas.md`.
- Patrones provisorios pueden invalidarse parcialmente con la calibración real. Mitigado por el versionado del corpus.
- G8c (semántico) sigue siendo Eje B post-defensa — el presente ADR cubre solo la sub-mejora léxica.

### Neutras

- El `LABELER_VERSION` no cambia mientras flag OFF.
- El contrato del CTR no cambia (labeler es derivado en lectura, ADR-020).
- El `classifier_config_hash` no cambia mientras flag OFF.
- El árbol de clasificación N4 no se ve afectado.

## Referencias

- ADR-023 — override temporal v1.1.0 (decisión vigente, supersede parcial por este ADR sólo en la sección "G8b sigue como agenda").
- ADR-020 — `n_level` derivado en lectura, patrón de bump de `LABELER_VERSION`.
- ADR-027 / ADR-044 — Fase B socratic_compliance esqueleto-OFF (patrón replicado por este ADR).
- ADR-043 — `OveruseDetector` (mismo patrón flag-gated + fail-soft + corpus hash).
- ADR-009 — patrón canónico de corpus hashes.
- Tesis Tabla 4.1 — asignación pedagógica de las anotaciones a N1/N4 según contexto.
- Tesis Sección 19.5 — gap pendiente del override por contenido (reflejado por este ADR como sub-componente cerrado en G8b técnico).
- `mejoras.docx` — plan post-piloto-1 con orden de mejoras.
- `docs/limitaciones-declaradas.md` — Limitación 3 actualizada al estado post-ADR-045.
- `apps/classifier-service/src/classifier_service/services/event_labeler_lexical.py` — implementación.
- `apps/classifier-service/tests/unit/test_event_labeler_lexical.py` — tests deterministas.
