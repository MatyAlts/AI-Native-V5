# ADR-043 — Detección de sobreuso del tutor mediante ventana temporal cross-prompt

- **Estado**: Aceptado
- **Fecha**: 2026-05-09
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: tutor, guardrails, ctr, mejora-5-plan-post-piloto-1, eje-a-cierre
- **Supersede**: la cláusula del ADR-019 que declaraba `overuse` como agenda futura. La supersesión es PARCIAL: el ADR-019 sigue siendo la decisión vigente sobre las cinco categorías regex de la Fase A; este ADR agrega la sexta categoría con un mecanismo de detección distinto.
- **Cierra**: Mejora 5 del plan documentado en `mejoras.docx`.

## Contexto y problema

El ADR-019 cerró la Fase A de los guardrails con cinco categorías de detección regex aplicadas como función pura sobre cada prompt individual: `jailbreak_indirect`, `jailbreak_substitution`, `jailbreak_fiction`, `persuasion_urgency` y `prompt_injection`. La Sección 8.5.3 de la tesis describe una sexta categoría de comportamiento adverso, denominada **sobreuso intencional** (`overuse`), que el ADR-019 declaró explícitamente fuera del alcance de la versión v1.0.0 con la justificación textual de que "requiere ventana temporal cross-prompt sobre múltiples prompts del mismo episodio (no es una decisión por-prompt)" (ADR-019 línea 112). El docstring del módulo `apps/tutor-service/src/tutor_service/services/guardrails.py:21` documenta la misma limitación.

El plan de mejoras post-piloto-1 (`mejoras.docx`) propuso convertir esta limitación en mejora sustancial mediante un detector que mantiene estado por episodio y razona sobre múltiples prompts. El presente ADR materializa la decisión de implementación, los umbrales elegidos, el mecanismo de persistencia del estado y las garantías de no regresión sobre el sistema vigente.

## Decisión

Se implementa un detector de sobreuso con dos heurísticas complementarias que operan sobre un **sliding window por episodio en Redis**, integrado al flow side-channel del tutor con el mismo patrón fail-soft que el detector regex de la Fase A. La sexta categoría `overuse` se agrega al tipo `Category` del módulo `guardrails.py` con severidad ordinal igual a 1 (informativo, conforme a la tabla de severidades del ADR-019). El `GUARDRAILS_CORPUS_VERSION` se bumpea de `"1.1.0"` a `"1.2.0"` y el `compute_guardrails_corpus_hash()` se extiende para incluir los thresholds del detector en el JSON canónico, preservando la propiedad de reproducibilidad bit-a-bit del corpus.

### Heurísticas

**Patrón Burst**: cuando la cantidad de eventos `prompt_enviado` dentro de los últimos `OVERUSE_BURST_WINDOW_SECONDS = 300.0` (cinco minutos) sobre el mismo episodio iguala o supera `OVERUSE_BURST_THRESHOLD = 6`, el detector emite un Match con `pattern_id = "overuse_v1_2_0_burst"`. La heurística captura ráfagas compulsivas de prompts típicamente asociadas con patrones de "spam" del tutor: "dame esto, dame el otro, dame...".

**Patrón Proportion**: cuando la fracción `prompts / total_eventos_cognitivos` dentro de los últimos `OVERUSE_PROPORTION_WINDOW_SECONDS = 600.0` (diez minutos) iguala o supera `OVERUSE_PROPORTION_THRESHOLD = 0.7`, el detector emite un Match con `pattern_id = "overuse_v1_2_0_proportion"`. La heurística captura inicios de episodio donde el estudiante prompea sin leer ni pensar (alta proporción de prompts respecto del trabajo cognitivo no-prompt). Aplica un piso anti-falso-positivo de `OVERUSE_MIN_EVENTS_FOR_PROPORTION = 5` eventos totales para evitar disparos espurios en episodios cortos.

### Mecanismo de persistencia del estado

El detector mantiene dos sorted sets en Redis por episodio. La key `tutor:overuse:{episode_id}:prompts` registra los timestamps de los `prompt_enviado` con score igual al epoch UTC y member igual al UUID del evento. La key `tutor:overuse:{episode_id}:events` registra los timestamps de los eventos cognitivos no-prompt (`edicion_codigo`, `codigo_ejecutado`, `lectura_enunciado`, `anotacion_creada`, `tests_ejecutados`) con la misma estructura. Eventos de tipo `meta` (apertura, cierre, abandono) NO entran al ledger porque no son cognitivos. El TTL de las keys es de ocho horas, mayor que la duración típica de la sesión del tutor (seis horas) para tolerar desfases entre cierre del episodio y limpieza de Redis.

### Integración con el flow del tutor

El hook se ubica en `apps/tutor-service/src/tutor_service/services/tutor_core.py::interact()` inmediatamente después del bloque que emite los eventos `intento_adverso_detectado` de la Fase A regex y antes del bloque que arma los messages para el LLM. La secuencia es: registrar el prompt actual en el ledger mediante `record_prompt`, ejecutar `check` para evaluar las dos heurísticas, y si el resultado es un Match emitir un evento adicional `intento_adverso_detectado` con la categoría `overuse`. El flow se mantiene side-channel: el prompt llega al modelo de lenguaje sin modificación, y cualquier excepción en el detector es capturada y loggeada sin bloquear el turno del estudiante.

Adicionalmente, los cinco emisores de eventos cognitivos no-prompt del `tutor_core.py` (`emit_codigo_ejecutado`, `record_edicion_codigo`, `record_anotacion_creada`, `record_lectura_enunciado`, `emit_tests_ejecutados`) reciben una llamada al helper interno `_record_overuse_non_prompt_event(event)` después del `publish_event` correspondiente, helper que delega al detector con el mismo patrón fail-soft. Esto alimenta el denominador del cálculo de Proportion sin alterar la firma pública de los métodos.

## Drivers de la decisión

- **D1**: cumplir la promesa textual de la Sección 8.5.3 de la tesis sobre detección de sobreuso, sin la cual la Sección 17.8 del análisis empírico del piloto pierde una dimensión declarada.
- **D2**: NO modificar el contrato del payload `IntentoAdversoDetectadoPayload` ni el `event_type` correspondiente. La nueva categoría se distingue exclusivamente por el campo `category="overuse"` y por el valor de `pattern_id`. Esto preserva la cadena criptográfica del CTR sin migración del esquema.
- **D3**: preservar la propiedad de reproducibilidad bit-a-bit del corpus de guardrails. Cualquier cambio futuro en los thresholds bumpea `guardrails_corpus_hash` y los eventos nuevos quedan etiquetados con el hash nuevo, mientras los históricos preservan el suyo. Mismo patrón canónico que `classifier_config_hash` en ADR-009.
- **D4**: aprovechar la infraestructura Redis ya disponible en el sistema (la sesión del tutor vive en Redis, el `abandonment_worker` la consume, los streams del CTR usan Redis Streams). No introducir nueva dependencia.
- **D5**: mantener el principio fail-soft. Una caída de Redis no debe bloquear el flow del tutor.

## Opciones consideradas

### Opción A — Sliding window en Redis con sorted sets (elegida)

Ya descrita en la sección Decisión.

**Ventajas**:
- Latencia esperada por chequeo: dos operaciones `zadd`/`zremrangebyscore`/`zrangebyscore` cada una de complejidad `O(log N)` sobre N pequeño (decenas de eventos por episodio). Negligible respecto del round-trip al modelo de lenguaje.
- Aislamiento por episodio garantizado por la inclusión del UUID en la key.
- Limpieza natural por TTL.
- Estado serializable: cualquier worker del consumer-group del CTR puede inspeccionarlo sin coordinación adicional.

**Desventajas**:
- Acopla el detector a Redis. Mitigación: `OveruseDetector` usa un `Protocol` `_RedisLike` que permite mockear con un fake in-memory para tests.
- Lógica de window-trimming distribuida entre `record_prompt` y `check`. Mitigación: el patrón es estándar y el `check` es la única vía de evaluación.

### Opción B — Estado en SessionState

Persistir el sliding window dentro del `SessionState` que ya vive en Redis. La sesión incluiría una nueva lista de timestamps de prompts.

**Desventajas que la descartan**:
- Bloat del SessionState que afecta a todos los lectores (no solo al detector).
- Requeriría migración del schema del `SessionState` (campo nuevo) con backwards-compat para sesiones legacy en flight.
- La concurrencia del SessionState es coordinada via `next_seq` (operación de lectura-modificación-escritura) y el detector tendría que reusarla, complejizando la separación de responsabilidades.

### Opción C — Cálculo en lectura sobre el CTR persistido

No mantener estado dedicado: cada vez que se necesita evaluar overuse, querear los eventos del episodio en Postgres y computar la heurística sobre ellos.

**Desventajas que la descartan**:
- Latencia de query a Postgres en el path crítico del turno del tutor. Inaceptable.
- Acopla el detector con el `ctr-service` cross-plano (el tutor vive en el plano pedagógico, el CTR persistido vive en su propio servicio). Viola la separación arquitectónica de los dos planos.

## Criterios de éxito

1. Los cuatro casos canónicos del plan se cubren con tests unitarios deterministas: burst (siete prompts en cuatro minutos), proportion (cinco prompts y dos no-prompts en diez minutos), no-sobreuso (cinco prompts en quince minutos), caso límite (seis prompts en exactamente cinco minutos). Los cuatro tests viven en `apps/tutor-service/tests/unit/test_overuse_detector.py`.
2. Las cinco categorías regex de la Fase A siguen detectándose correctamente. El test `test_guardrails_corpus_hash_es_golden` se actualiza al nuevo hash `6411ef8058d0c1171baff4f7152bd1746abbede505dda472dd5d7ed23e1cc1c5` que refleja el bump del corpus.
3. El campo `event_type` del CTR se mantiene como `intento_adverso_detectado` para todos los tipos de detección (regex y overuse). El consumidor del CTR distingue por `payload.category`.
4. Cualquier auditor del repositorio público puede verificar que los thresholds documentados en este ADR coinciden con las constantes en `guardrails.py`.

## Análisis de sensibilidad

Las constantes elegidas (`OVERUSE_BURST_THRESHOLD = 6`, `OVERUSE_BURST_WINDOW_SECONDS = 300.0`, `OVERUSE_PROPORTION_THRESHOLD = 0.7`, `OVERUSE_PROPORTION_WINDOW_SECONDS = 600.0`, `OVERUSE_MIN_EVENTS_FOR_PROPORTION = 5`) son operacionalización conservadora y declarable, no resultado de validación empírica ex-ante. La fundamentación de cada elección sigue.

El umbral burst de seis prompts en cinco minutos se deriva de la observación pedagógica de que un estudiante reflexivo formula prompts a un ritmo del orden de uno cada uno a dos minutos cuando trabaja activamente con el tutor. Seis prompts en cinco minutos representa más del doble de ese ritmo (uno cada cincuenta segundos) sostenido durante toda la ventana, lo cual es indicador robusto de patrón compulsivo no reflexivo.

El umbral proportion de setenta por ciento en ventana de diez minutos se deriva de la asimetría esperada del trabajo cognitivo: en un episodio sano, el estudiante invierte la mayor parte del tiempo leyendo el enunciado, escribiendo código y ejecutando tests, con prompts al tutor como complemento minoritario. Una proporción superior a setenta por ciento de prompts respecto del total de eventos cognitivos durante diez minutos consecutivos sugiere que el estudiante ha externalizado la fase reflexiva al tutor.

El piso anti-falso-positivo de cinco eventos totales en la ventana evita que episodios cortos disparen alertas espurias por proporción mientras el estudiante todavía está construyendo el contexto del trabajo. El número se elige conservador para reducir falsos positivos en episodios de baja densidad.

Un análisis empírico ex-post sobre los datos del piloto-1 puede refinar estos umbrales a partir de la distribución observada de inter-arrival times de prompts y proporciones reales. Si tal análisis sugiere modificaciones, el procedimiento es bumpear las constantes, recomputar `guardrails_corpus_hash`, actualizar el golden test y bumpear `GUARDRAILS_CORPUS_VERSION` semánticamente. La práctica operativa es la misma que el ADR-009 declara para `classifier_config_hash`.

## Consecuencias

### Positivas

- La promesa textual de la Sección 8.5.3 de la tesis queda cumplida con implementación reproducible y auditable.
- El campo `event_type = "intento_adverso_detectado"` se preserva uniforme; los consumidores del CTR no requieren modificaciones del schema.
- El detector convive con la Fase A regex sin interferencia: el mismo prompt puede disparar cero, una o múltiples categorías regex y adicionalmente disparar overuse.
- La reproducibilidad bit-a-bit del corpus se preserva mediante el bump de versión y la actualización del golden hash.
- El esfuerzo total de implementación se mantuvo dentro de la estimación de una semana del plan original.

### Negativas

- El detector introduce dependencia operativa de Redis para el flow de detección de overuse. Mitigación: el patrón fail-soft hace que una caída de Redis no bloquee el turno del estudiante; los eventos de overuse simplemente no se emiten durante la ventana de caída.
- El campo `event_type` no diferencia categorías de detección en el schema. Una posible iteración futura podría separar `intento_adverso_detectado_regex` y `intento_adverso_detectado_window` como tipos distintos para facilitar análisis SQL directo. Decisión actual: NO separar para preservar la cadena criptográfica vigente.

### Neutras

- No afecta el árbol de decisión del clasificador ni el `classifier_config_hash`.
- No afecta los hashes deterministas de los eventos del CTR.
- No requiere migración de Postgres ni de Casbin.

## Referencias

- ADR-019 — Fase A de guardrails (preprocesamiento regex de prompts), cuya cláusula sobre `overuse` como agenda futura este ADR supersede parcialmente.
- ADR-009 — Patrón canónico de hash determinista (`classifier_config_hash`) que `guardrails_corpus_hash` replica.
- `apps/tutor-service/src/tutor_service/services/guardrails.py` — implementación del detector.
- `apps/tutor-service/src/tutor_service/services/tutor_core.py` — integración del hook.
- `apps/tutor-service/tests/unit/test_overuse_detector.py` — tests del detector.
- `apps/tutor-service/tests/unit/test_guardrails.py` — golden hash actualizado y test de versión.
- `mejoras.docx` — plan de mejoras post-piloto-1, sección 5 (Mejora 5).
- Tesis Sección 8.5.3 — descripción del comportamiento adverso de sobreuso.
- Tesis Sección 17.8 — análisis empírico de eventos adversos del piloto.
