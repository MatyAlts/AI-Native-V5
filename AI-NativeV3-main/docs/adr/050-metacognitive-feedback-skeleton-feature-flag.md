# ADR-050 — Esqueleto técnico de la devolución metacognitiva narrativa al cierre del episodio detrás de feature flag

- **Estado**: Aceptado
- **Fecha**: 2026-05-16
- **Deciders**: Alberto Cortez, director de tesis (pendiente revisión coautoral Ana Garis sobre plantillas)
- **Tags**: web-student, metacognicion, devolucion-cierre, informeSoc-R5, esqueleto-OFF, piloto-2
- **Cierra parcialmente**: R5 del `informeSoc.md` (componente técnico — las 7 plantillas siguen marcadas DRAFT pendiente revisión coautoral).

## Contexto y problema

El piloto AI-Native N4 implementa una asimetría deliberada en visibilidad de datos: el estudiante produce eventos, el docente los interpreta. El estudiante no ve su etiqueta N1-N4, su categoría de apropiación, sus cinco coherencias, su slope longitudinal ni las alertas predictivas sobre él. `politica-visibilidad-estudiante.md` documenta esa decisión y propone, para piloto-2, un **Nivel 1 opt-in** que devuelve al estudiante información sobre su propio proceso en lenguaje no técnico, sin score, sin nombrar categorías de apropiación.

El informe pedagógico `informeSoc.md` §4 identificó esa asimetría como costo formativo: "la metacognición se entrena haciendo visible al estudiante el patrón de su propio pensamiento. Esconder los datos al productor de esos datos es renunciar a la mitad del potencial formativo" (Flavell 1979, Schraw 1998, Veenman 2006). La recomendación R5 propuso implementar una devolución metacognitiva narrativa al cierre del episodio.

Análoga a la situación de la Fase B (ADR-027/044) y del override léxico (ADR-023/045), la activación productiva de R5 requiere **decisión académica humana** sobre las plantillas textuales (revisión coautoral con dir + co-dir + Ana Garis) y **decisión política sobre default** (OFF en piloto-1, posiblemente ON en piloto-2). El equipo técnico solo no puede activarla.

El presente ADR materializa la decisión de **implementar el esqueleto técnico de la devolución metacognitiva con activación bloqueada por feature flag y plantillas explícitamente DRAFT** durante el período entre el cierre del piloto-1 y la disponibilidad de revisión coautoral + decisión de visibilidad.

## Decisión

Se implementa la devolución metacognitiva como **esqueleto técnico completo gateado por feature flag a nivel de usuario y plantillas marcadas DRAFT en código**. Específicamente:

1. **Módulo `packages/platform-ops/src/platform_ops/metacognitive_feedback.py`** con función pura `generate_metacognitive_feedback(events: list[dict]) -> dict`. Devuelve dict con `feedback_template`, `feedback_text`, `metacog_feedback_version` y `is_draft`. Función pura, determinista, sin side-effects, bit-a-bit reproducible para misma cadena de eventos.

2. **Versión `METACOG_FEEDBACK_VERSION = "1.0.0-draft"`**. El sufijo `-draft` es explícito en el string de versión — cualquier observación del CTR que registre este valor identifica unívocamente que las plantillas eran provisionales. Cuando dir + co-dir + Ana Garis aprueben las plantillas, bumpear a `"1.0.0"` (sin sufijo) y actualizar el flag `is_draft` a `False`.

3. **Siete plantillas seleccionadas por reglas determinísticas en orden fijo**:
   - `episodio_corto` (< 5 eventos) — defensiva.
   - `abandonado_o_comprometido` — defensiva (no se devuelve patrón sobre cadena incompleta o tampered).
   - `sin_tutor` (0 prompts del estudiante).
   - `solo_conversacion` (≥1 prompt y 0 ejecuciones/tests).
   - `integrando_feedback` (≥50% prompts post-tests/exec).
   - `consulta_temprana` (≥50% prompts en primeros 180s).
   - `mixto` (default sin señal dominante).
   
   Las siete plantillas tienen comentario explícito `# DRAFT — PENDIENTE REVISIÓN COAUTORAL` en el código. **NO usar en piloto real sin la revisión**.

4. **Feature flag a nivel de usuario** (no de servicio): `preferencia_visibilidad.metacognitive_feedback_enabled = False` por default. Esto difiere del patrón de ADR-044/045 (flag a nivel de servicio) porque la devolución es opt-in del estudiante, no decisión operacional. El esquema de almacenamiento de esa preferencia (tabla nueva, columna JSONB en `usuarios`, o registro en `byok_keys`-like) **queda pendiente del design** — se decide cuando se implemente el endpoint que materializa R5 fase 2.

5. **Mientras el esqueleto no esté conectado al pipeline**:
   - El módulo `metacognitive_feedback.py` existe y sus tests pasan.
   - NO se invoca desde ningún endpoint productivo.
   - NO se emite ningún evento `devolucion_metacognitiva_mostrada` al CTR.
   - El contrato observable del piloto-1 no cambia.

6. **Activación bloqueada hasta**:
   - **Gate A**: revisión coautoral de las 7 plantillas con dir + co-dir + Ana Garis. Cada plantilla debe ser aprobada literalmente o re-redactada.
   - **Gate B**: decisión política sobre default (OFF universal vs OFF con opt-in vs ON con opt-out).
   - **Gate C**: implementación del endpoint `GET /api/v1/episodes/{id}/metacognitive-feedback` en `analytics-service` (recomendación del design doc), del schema de `preferencia_visibilidad`, y del componente UI `MetacognitiveFeedbackPanel.tsx`.

### Reglas de selección de plantillas (orden fijo)

Primera regla matching gana:

| Orden | Condición | Plantilla |
|---|---|---|
| 1 | `len(events) < 5` | `episodio_corto` |
| 2 | `has_abandonado` OR `integrity_compromised` | `abandonado_o_comprometido` |
| 3 | `n_prompts == 0` | `sin_tutor` |
| 4 | `n_prompts ≥ 1` AND `n_exec == 0` AND `n_tests == 0` | `solo_conversacion` |
| 5 | `n_post_tests / n_prompts ≥ 0.5` | `integrando_feedback` |
| 6 | `n_temprana / n_prompts ≥ 0.5` (ventana 180s) | `consulta_temprana` |
| 7 | default | `mixto` |

Los umbrales (0.5, 180s, 5 eventos mínimos) son operacionalización inicial — calibrar empíricamente con docentes UTN cuando se ejecute el gate A.

## Drivers de la decisión

- **D1**: respetar literalmente la asimetría visibilidad del piloto-1. La feature flag a nivel de usuario garantiza que el comportamiento observable del estudiante en el piloto-1 no cambia hasta que la decisión política se tome.
- **D2**: reducir lead-time entre revisión coautoral y activación productiva. Las plantillas son lo único que requiere participación humana — el resto del stack (función pura, reglas determinísticas, casos límite, tests) ya está cubierto. Cuando el gate A se levante, queda: actualizar 7 strings + bump version + flag flip + endpoint + UI.
- **D3**: preservar reproducibilidad bit-a-bit. Función pura sobre cadena de eventos → output determinista. Dos episodios con la misma cadena producen el mismo `feedback_text` para la misma versión de plantillas.
- **D4**: marcar explícitamente la condición DRAFT en runtime. El campo `is_draft: True` en cada respuesta y el sufijo `-draft` en `metacog_feedback_version` impiden que un consumidor downstream (UI, exports, dashboards) trate erróneamente el contenido como definitivo.
- **D5**: NO contaminar el `classifier_config_hash`. El evento `devolucion_metacognitiva_mostrada` (cuando exista) debe agregarse a `_EXCLUDED_FROM_FEATURES` del pipeline (ADR-035 patrón canónico). Documentado acá para que la implementación del gate C no lo olvide.
- **D6**: fail-soft. Cualquier excepción en la generación del feedback NO debe romper el cierre del episodio. La devolución es decorativa pedagógicamente, no crítica.
- **D7**: respetar invariantes pedagógicas del informeSoc.md §3.1 (R5 design doc §1) — los tests verifican explícitamente que ninguna plantilla nombre categorías de apropiación ni niveles N1-N4 ni score numérico.

## Opciones consideradas

### Opción A — Esqueleto OFF con plantillas DRAFT (elegida)

Ya descrita en la sección Decisión.

**Ventajas**:
- Reduce lead-time entre disponibilidad de gate A y producción.
- Mantiene el patrón ya validado en ADR-044 y ADR-045 (esqueleto + flag OFF).
- Tests pasan (33 tests entre los 3 módulos R5/R7/R8, 11 propios), CI puede correr.
- Las 7 plantillas son provisorias pero **funcionalmente coherentes** — el flujo se puede demostrar a dir + co-dir + Ana Garis antes de aprobar los textos.

**Desventajas**:
- Riesgo de que las plantillas DRAFT se prendan accidentalmente. Mitigación: doble gate (flag de servicio + flag de usuario). Ambos en OFF por default.
- Riesgo de que la implementación se considere "lista" sin revisión coautoral. Mitigación: marca `is_draft=True` en cada respuesta + comentarios explícitos en código + este ADR.

### Opción B — Esperar a la revisión coautoral antes de implementar nada

Postergar la implementación hasta que dir + co-dir + Ana Garis aprueben las plantillas finales.

**Desventajas que la descartan**:
- Lead-time alto. La revisión coautoral toma semanas de coordinación; el código toma horas.
- Discusión sobre plantillas sin código corriendo es estéril. Tener el módulo funcionando permite demostrar el output sobre cadenas de eventos reales del piloto-1, lo cual informa la revisión.

### Opción C — Implementar y activar con plantillas inventadas

Implementar el módulo Y prender los flags en piloto-1 con las plantillas DRAFT como definitivas.

**Desventajas que la descartan**:
- Viola "no inventes nada" — las plantillas son decisiones pedagógicas que requieren participación de la co-autoría del paper.
- Contamina los datos del piloto-1 con un contrato no validado. Sería irreversible operacionalmente: los estudiantes ya verían las devoluciones.
- Riesgo doctoral: defender una tesis con devolución metacognitiva activa pero sin revisión coautoral expone al tribunal a interpretarlo como descuido.

### Opción D — Implementar con un LLM en lugar de plantillas

Generar el feedback con el `ai-gateway` en lugar de plantillas determinísticas.

**Desventajas que la descartan**:
- Rompe reproducibilidad bit-a-bit. Dos episodios con la misma cadena producirían feedback distinto.
- Costo BYOK por estudiante por episodio — escala mal y depende de la calidad del provider.
- Pierde auditabilidad: no se puede explicar a un comité doctoral por qué un feedback dado se generó tal como se generó.
- LLM puede generar texto que viole las invariantes pedagógicas (mencionar categoría, score, etc.) y los tests determinísticos no aplican.

## Criterios de éxito

1. El módulo `packages/platform-ops/src/platform_ops/metacognitive_feedback.py` existe y exporta `generate_metacognitive_feedback`.
2. Los 11 tests en `tests/test_metacognitive_feedback.py` pasan en CI.
3. Ningún test del piloto-1 cambia su comportamiento por la introducción de este módulo (verificable: el módulo no se importa desde ningún servicio actual).
4. Las 7 plantillas tienen comentario `# DRAFT — PENDIENTE REVISIÓN COAUTORAL` literal.
5. El campo `is_draft` de la respuesta es `True` mientras `METACOG_FEEDBACK_VERSION` contenga el sufijo `-draft`.

## Criterios de revisita (para activar)

- **Gate A cumplido**: 7 plantillas aprobadas literalmente (o re-redactadas) por dir + co-dir + Ana Garis. Plantillas finales se commitean reemplazando los strings DRAFT. Bumpear `METACOG_FEEDBACK_VERSION` a `"1.0.0"` (sin sufijo).
- **Gate B cumplido**: decisión política sobre default registrada en `politica-visibilidad-estudiante.md` (recomendación: OFF en piloto-1, ON con opt-out en piloto-2).
- **Gate C cumplido**: endpoint `GET /api/v1/episodes/{id}/metacognitive-feedback` en `analytics-service`, schema `preferencia_visibilidad`, componente `MetacognitiveFeedbackPanel.tsx`, evento CTR `devolucion_metacognitiva_mostrada` agregado a `_EXCLUDED_FROM_FEATURES`. Ver R5 fase 2 en `docs/research/design-metacognitive-feedback.md`.

Cuando los tres gates se cumplan, este ADR queda **superseded** por un ADR-NNN nuevo que documente la activación efectiva.

## Consecuencias

### Positivas

- Lead-time entre revisión coautoral y activación reducido a horas.
- Patrón ya validado replicado (ADR-044, ADR-045).
- Las plantillas son inspeccionables, criticables y reemplazables sin tocar el resto del stack.
- La inclusión de plantillas defensivas (`episodio_corto`, `abandonado_o_comprometido`) cubre casos límite que el design doc original no detallaba.

### Negativas

- Líneas de código sin uso productivo durante el período pre-gate. ~280 LOC del módulo + 11 tests.
- Riesgo de drift entre el módulo y las decisiones académicas si la revisión se demora mucho.

### Neutras

- El contrato del CTR no cambia. `classifier_config_hash` no cambia. `LABELER_VERSION` no se bumpea.
- Las plantillas finales pueden requerir ajustes a las reglas de selección si el gate A las modifica sustancialmente (ej. si se agrega una 8va categoría). Las reglas son configurables, no cementadas.

## Referencias

- ADR-027 — Diferir Fase B socratic_compliance. Patrón análogo de "decisión académica humana bloquea activación técnica".
- ADR-044 — Esqueleto técnico Fase B con feature flag. Patrón directo replicado.
- ADR-045 — Esqueleto léxico anotación con feature flag. Patrón directo replicado.
- ADR-035 — Exclusión de eventos side-channel del classifier. Patrón canónico para `devolucion_metacognitiva_mostrada`.
- `informeSoc.md` §4 (asimetría visibilidad) y §5 (oportunidad reflexión).
- `docs/research/politica-visibilidad-estudiante.md` — propuesta de 3 niveles + Nivel 1 opt-in.
- `docs/research/design-metacognitive-feedback.md` — design completo de R5 con fases.
- `packages/platform-ops/src/platform_ops/metacognitive_feedback.py` — implementación.
- `packages/platform-ops/tests/test_metacognitive_feedback.py` — 11 tests determinísticos.
- Flavell, J. H. (1979). Metacognition and cognitive monitoring. *American Psychologist*, 34(10), 906-911.
- Schraw, G. (1998). Promoting general metacognitive awareness. *Instructional Science*, 26(1), 113-125.
- Veenman, M. V. J., Van Hout-Wolters, B. H. A. M., & Afflerbach, P. (2006). Metacognition and learning. *Metacognition and Learning*, 1(1), 3-14.
