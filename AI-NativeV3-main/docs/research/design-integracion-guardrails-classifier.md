# Design doc — Integración guardrails ↔ classifier (R8 informeSoc.md)

**Versión**: 1.0.0 — propuesta de diseño, NO implementación
**Fecha**: 2026-05-16
**Autor**: derivado de informeSoc.md §2.3 (guardrails detectan léxico pero no dependencia cognitiva benigna)
**Estado**: design para revisión coautoral + implementación por sub-agent en sesión futura. Bloqueado por intercoder κ ≥ 0,70 (Protocolo B sobre tree).

---

## 0. Por qué este diseño existe

Hoy los guardrails (`tutor-service`, ADR-019/043) y el classifier (`classifier-service`, ADR-010/018/020) son sistemas paralelos:

- Los guardrails detectan patrones léxicos en el prompt del estudiante (`jailbreak_*`, `direct_answer`, `persuasion_urgency`, `overuse`) y emiten eventos CTR `intento_adverso_detectado`.
- El classifier toma todos los eventos del episodio y produce una categoría de apropiación.

El `intento_adverso_detectado` cuenta como evento N4 en el etiquetador (`event_labeler.py`), pero **el árbol de decisión (`tree.py`) no lo trata distinto** de otros eventos N4. Un episodio con 5 intentos adversos detectados puede clasificarse como `apropiacion_reflexiva` si las 5 coherencias dan los umbrales correctos.

Mi observación pedagógica en informeSoc.md §2.3 fue: "los guardrails capturan dependencia cognitiva léxica, pero un estudiante puede delegar pensamiento sin disparar guardrails". La integración propuesta busca cerrar ese hueco: **las señales de guardrail deberían modular la clasificación final, no quedar como evento decorativo**.

---

## 1. Propiedades invariantes que NO se tocan

1. **Append-only del CTR**: los eventos `intento_adverso_detectado` se siguen emitiendo como hoy.
2. **Guardrails Fase A sigue siendo side-channel**: NO bloquea el prompt al LLM. Esa propiedad es central a ADR-019.
3. **`classifier_config_hash` cambia con la integración**: bumpear coordinadamente con A1 (re-clasificación histórica) o esperar a A1 cerrado.
4. **5 coherencias permanecen separadas**: la integración NO colapsa señales de guardrail en CT/CCD/CII. Las trata como **modificador exógeno** del árbol.
5. **`guardrails_corpus_hash` y `socratic_compliance` siguen sus reglas de versionado existentes (ADR-019/027/044)**.

---

## 2. Tres aproximaciones consideradas

### 2.1 Opción A — Modificador post-árbol (recomendada)

El árbol corre como hoy, produce una categoría. Luego una función `apply_guardrail_modifier(classification, guardrail_signals)` la modifica condicionalmente:

```python
def apply_guardrail_modifier(
    classification: ClassificationResult,
    guardrail_signals: GuardrailSignals,
) -> ClassificationResult:
    # Si hay intentos adversos severos repetidos, la apropiacion_reflexiva
    # baja a apropiacion_superficial. La superficial baja a delegacion.
    if guardrail_signals.severity_3_plus_count >= 3:
        if classification.appropriation == "apropiacion_reflexiva":
            classification.appropriation = "apropiacion_superficial"
            classification.reason += (
                " Modificador: 3+ intentos adversos severos."
            )
        elif classification.appropriation == "apropiacion_superficial":
            classification.appropriation = "delegacion_pasiva"
            classification.features["sub_branch"] = "guardrail_triggered"
            classification.reason += (
                " Modificador: 3+ intentos adversos severos sobre superficial."
            )

    # Si overuse confirmado, no cambia la apropiacion pero deja flag.
    if guardrail_signals.overuse_confirmed:
        classification.features["overuse_detected"] = True

    return classification
```

**Ventajas**: trazable (el `reason` documenta el modificador), reversible (se puede desactivar el modificador y recalcular sin re-etiquetar), no toca el árbol existente, no requiere re-validación intercoder del Protocolo B (el árbol no cambió).

**Desventajas**: introduce un paso adicional que rompe la pureza del pipeline. La función `classify_episode_from_events` deja de ser una función pura sobre eventos: depende también de las señales de guardrail extraídas externamente.

### 2.2 Opción B — Sexta entrada del árbol

Las señales de guardrail entran al `tree.py::classify` como sexta dimensión:

```python
def classify(
    ct, ccd, cii, guardrail_signals, reference_profile=None,
) -> ClassificationResult:
    ...
```

**Ventajas**: pureza del pipeline preservada, el árbol expresa toda la lógica en un solo lugar.

**Desventajas**: cambia la firma del árbol → requiere re-validación intercoder Protocolo B sobre el árbol modificado. Coordinación cara con ADR-046 que estipula 50 episodios.

### 2.3 Opción C — Eventos de guardrail con peso en CT/CCD/CII

Las funciones `ct.compute_ct`, `ccd.compute_ccd`, `cii.compute_cii` ya consumen `intento_adverso_detectado` como cualquier evento N4. La opción C es darles peso diferencial al verlo: por ejemplo, contar `intento_adverso` con peso 1.5 en CCD_orphan_ratio.

**Ventajas**: cambio mínimo, fluye por el pipeline existente.

**Desventajas**: rompe la interpretabilidad de las coherencias (un CCD_mean alto puede deberse a contenido o a peso de guardrail, no se distingue). **Académicamente cuestionable**.

### 2.4 Recomendación

**Opción A** para piloto-2. Razón: el árbol queda intacto (no requiere Protocolo B nuevo), el modificador es explícito y trazable, y se puede activar bajo feature flag sin afectar las 106 históricas.

---

## 3. Diseño detallado de Opción A

### 3.1 Extracción de señales de guardrail por episodio

Nueva función pura en `packages/platform-ops/src/platform_ops/guardrail_signals.py`:

```python
@dataclass(frozen=True)
class GuardrailSignals:
    total_attempts: int  # cantidad de intento_adverso_detectado
    severity_3_plus_count: int  # cantidad de severidad >= 3
    categories_detected: frozenset[str]  # jailbreak_substitution, etc.
    overuse_confirmed: bool  # cualquier intento_adverso con category=overuse
    extraction_version: str = "guardrail_signals/v1.0.0"

def extract_guardrail_signals(events: list[dict]) -> GuardrailSignals:
    """Funcion pura. Toma eventos del episodio, devuelve resumen de senales."""
    ...
```

### 3.2 Integración en el pipeline

`pipeline.py::classify_episode_from_events` queda:

```python
def classify_episode_from_events(events, reference_profile=None):
    # Etapa 1: filtrar excluidos (como hoy)
    classifier_events = [e for e in events if e.type not in _EXCLUDED_FROM_FEATURES]

    # Etapa 2: features (como hoy)
    ct = compute_ct(classifier_events)
    ccd = compute_ccd(classifier_events)
    cii = compute_cii(classifier_events)

    # Etapa 3: clasificacion base (como hoy)
    classification = classify(ct, ccd, cii, reference_profile=profile)

    # Etapa 4 (NUEVO): modificador de guardrails
    if settings.guardrail_modifier_enabled:
        signals = extract_guardrail_signals(events)
        classification = apply_guardrail_modifier(classification, signals)
        classification.features["guardrail_signals"] = signals.to_dict()
        classification.features["guardrail_modifier_version"] = "v1.0.0"

    return classification
```

Etapa 4 está bajo feature flag. Default OFF en piloto-1.

### 3.3 Reglas del modificador (versión inicial — calibrar empíricamente)

**Regla 1**: 3+ intentos adversos severidad ≥ 3 → bajar un nivel de apropiación.
- Justificación: tres intentos serios de saltar el contrato socrático son indicio de **disposición a delegar** independiente del patrón temporal/léxico capturado por las coherencias.

**Regla 2**: 1-2 intentos severidad ≥ 3 → no modificar apropiación pero marcar flag `guardrail_warning_low_count`.
- Justificación: un intento puede ser experimentación legítima ("a ver qué pasa si pruebo esto"). Tres es patrón.

**Regla 3**: `overuse_confirmed` → no modificar apropiación pero marcar flag `overuse_detected`.
- Justificación: overuse mide ritmo, no contenido. Ya está parcialmente capturado por CCD; agregarlo como flag explícito es trazabilidad académica, no penalización.

**Regla 4**: combinación `severity_3_plus_count >= 3` Y `overuse_confirmed` Y `apropiacion_reflexiva` → bajar a `delegacion_pasiva` con sub_branch `guardrail_triggered`.
- Justificación: combinación de delegación léxica + ritmo de over-consumo es señal robusta de dependencia cognitiva que el árbol no captura.

**Calibración**: las reglas anteriores son operacionalización inicial. La validación empírica sobre las 106 históricas (post-A1) debe medir si el modificador cambia clasificaciones de manera consistente con criterio docente. Si en >30% de los casos modificados los docentes discrepan, refinar reglas.

### 3.4 Trazabilidad

Cada modificación queda registrada en `Classification.features`:

```json
{
  "guardrail_signals": {
    "total_attempts": 4,
    "severity_3_plus_count": 3,
    "categories_detected": ["jailbreak_substitution", "direct_answer"],
    "overuse_confirmed": false
  },
  "guardrail_modifier_version": "v1.0.0",
  "modifier_applied": "rule_1_three_severity_3_plus",
  "appropriation_before_modifier": "apropiacion_superficial"
}
```

Esto permite responder en auditoría: "¿qué hubiera clasificado el árbol sin guardrail modifier?" → leer `appropriation_before_modifier`.

---

## 4. Riesgos pedagógicos del modificador

### 4.1 Riesgo de doble penalización

Un estudiante que delega léxicamente (categoría `direct_answer`) ya tiende a tener CCD bajo y orphan alto, lo cual lo lleva a `apropiacion_superficial` o `delegacion_pasiva` por las coherencias. Si además se le aplica el modificador, baja dos niveles. **Mitigación**: la Regla 1 baja UN nivel, no dos. Documentar explícitamente en el ADR.

### 4.2 Falsos positivos de severidad 3

La severidad 3 hoy se asigna a `jailbreak_indirect`, `direct_answer`, `persuasion_urgency` (ver `guardrails.py`). Un estudiante puede usar lenguaje urgente legítimamente ("tengo el parcial el lunes, ¿podés explicarme bien las listas?") y ser detectado como `persuasion_urgency`. **Mitigación**: la Regla 1 requiere **3 detecciones**, no 1. El piso reduce la sensibilidad a falsos positivos individuales. Documentar el trade-off.

### 4.3 Reactividad al estudiante consciente del sistema

Si un estudiante sabe del modificador, evita los patrones léxicos durante el episodio pero igual delega. **Mitigación**: el modificador no se anuncia al estudiante. La política de visibilidad (`politica-visibilidad-estudiante.md`) clasifica las detecciones como Nivel 2 (solo docente), con la excepción crítica §3.4 (notificación post-cierre de intentos adversos sin nombrar categorías técnicas).

---

## 5. Trabajo de implementación estimado

| Tarea | Esfuerzo |
|---|---|
| Implementar `extract_guardrail_signals` + tests unit | 4-5 h |
| Implementar `apply_guardrail_modifier` con las 4 reglas iniciales + tests | 4-5 h |
| Integrar en `pipeline.py` bajo feature flag + tests anti-regresión | 2-3 h |
| Validación empírica sobre 106 históricas (post-A1) — medir cuántas cambian, comparar con criterio docente sobre muestra | 8-12 h |
| Calibración de constantes (umbral 3, etc.) según validación | 4-6 h |
| ADR-052 documentando la decisión + invariantes | 2-3 h |
| **Total** | **24-34 h** |

Estimado del informeSoc.md original era 8-12 h. Refinado: 24-34 h cuando se incluye la validación empírica obligatoria (el informe original subestimó).

---

## 6. Bloqueos a resolver antes de implementar

1. **A1 cerrado**: re-clasificación de las 106 históricas con `classifier_config_hash` actual. Sin esto, no hay corpus consistente sobre el cual medir el efecto del modificador.
2. **Validación intercoder Protocolo B cerrada** (ADR-046): si el árbol base no alcanza κ ≥ 0,70, primero arreglar el árbol, después modificar.
3. **Aprobación de las 4 reglas iniciales** por dirección + co-dirección + Ana Garis. Las reglas son decisiones académicas, no técnicas.

---

## 7. Decisiones pendientes (requieren participación humana)

1. **Opción A vs B vs C**: confirmar Opción A.
2. **Calibración de la Regla 1 (umbral 3 vs 2 vs 4)** con análisis empírico.
3. **Inclusión del modificador en el paper**: si va, en qué sección. La integridad académica exige explicitarlo si se activa.

---

## 8. Referencias

- informeSoc.md §2.3 — diagnóstico del hueco entre guardrails y classifier.
- ADR-010 — append-only del CTR. Restricción inmutable.
- ADR-019 — Guardrails Fase A side-channel.
- ADR-027/044 — Fase B (socratic_compliance) — diferida.
- ADR-043 — Overuse detection cross-prompt-window.
- ADR-046 — Intercoder κ ≥ 0,70 protocolo dual.
- `apps/tutor-service/src/tutor_service/services/guardrails.py` — categorías y severidades vigentes.
- `apps/classifier-service/src/classifier_service/services/tree.py` — árbol a no modificar (Opción A) o modificar (Opción B).
- `apps/classifier-service/src/classifier_service/services/pipeline.py` — pipeline donde se inserta la Etapa 4.
- politica-visibilidad-estudiante.md — relación con la excepción crítica §3.4.
