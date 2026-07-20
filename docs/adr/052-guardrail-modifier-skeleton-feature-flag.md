# ADR-052 — Esqueleto del modificador de clasificación por señales de guardrail detrás de feature flag

- **Estado**: Aceptado
- **Fecha**: 2026-05-16
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: classifier, guardrails, informeSoc-R8, esqueleto-OFF, piloto-2, modificador-post-arbol
- **Cierra parcialmente**: R8 del `informeSoc.md` (componente técnico; conexión al pipeline + calibración empírica de constantes quedan bloqueadas por A1 + Protocolo B intercoder).

## Contexto y problema

Hoy los **guardrails** (`tutor-service`, ADR-019/043) y el **classifier** (`classifier-service`, ADR-010/018/020) son sistemas paralelos:

- Los guardrails detectan patrones léxicos en el prompt del estudiante (`jailbreak_*`, `direct_answer`, `persuasion_urgency`, `overuse`) y emiten eventos `intento_adverso_detectado` al CTR como **side-channel**.
- El classifier toma todos los eventos del episodio y produce una `appropriation` categórica vía `tree.py::classify`.

El evento `intento_adverso_detectado` cuenta como evento N4 en el `event_labeler` (ADR-019), pero **el árbol de decisión no lo trata distinto** de otros eventos N4. Un episodio con 5 intentos adversos severos puede clasificarse como `apropiacion_reflexiva` si las 5 coherencias dan los umbrales correctos.

El informeSoc.md §2.3 identificó esa desconexión como brecha pedagógica: "los guardrails capturan dependencia cognitiva léxica, pero un estudiante puede delegar pensamiento sin disparar guardrails, y un estudiante que dispara guardrails repetidamente puede aún así caer en la rama de apropiación reflexiva por las coherencias temporales/léxicas".

La recomendación R8 propuso integrar las señales de guardrail como **modificador post-árbol** sobre la clasificación final, **no como sexta entrada del árbol**. Razones:
- Mantiene el árbol existente intacto → no requiere re-validación intercoder Protocolo B nuevo.
- El modificador es explícito y trazable vía `Classification.features.appropriation_before_modifier`.
- Reversible: desactivar el flag recalcula sin re-etiquetar.

**Restricciones operacionales duras**:
- Conectar el modificador al pipeline bumpea `classifier_config_hash` → bloqueo análogo a ADR-051 (CEC). Requiere A1 cerrado.
- Las constantes de las 4 reglas (umbral severity_3_plus_count = 3, regla 1 vs 2, etc.) son **operacionalización inicial sin validación empírica**. Calibrar sobre las 106 históricas post-A1 antes de activar.
- El árbol base debe estar validado intercoder (Protocolo B, ADR-046) antes de modificarlo. Sin κ ≥ 0,70 sobre el árbol de 3 categorías, modificarlo es prematuro.

El presente ADR materializa la decisión de **implementar el modificador como funciones puras en `platform-ops` + feature flag en `classifier-service`**, ambos OFF por default y desconectados del pipeline, durante el período entre el cierre del piloto-1 y la disponibilidad de A1 + Protocolo B + calibración empírica.

## Decisión

Se implementa el modificador como **esqueleto técnico completo gateado por doble bloqueo (funciones desconectadas + feature flag OFF)**. Específicamente:

1. **Módulo `packages/platform-ops/src/platform_ops/guardrail_signals.py`** con dos funciones puras:
   - `extract_guardrail_signals(events: list[dict]) -> GuardrailSignals` — agrega los eventos `intento_adverso_detectado` en un resumen estructurado (total, severity_3_plus_count, categories_detected, overuse_confirmed).
   - `apply_guardrail_modifier(classification, signals) -> classification_modificada` — aplica las 4 reglas en orden fijo y devuelve una **copia** modificada vía `dataclasses.replace`. La classification original no se muta.

2. **Versión `GUARDRAIL_MODIFIER_VERSION = "1.0.0"`**. Sin sufijo `-draft` (a diferencia de ADR-050) porque las reglas son operacionales claras, no contenido textual. Lo provisional es **la calibración de constantes** (umbral 3 vs 2 vs 4, ventanas de overuse).

3. **Feature flag `guardrail_modifier_enabled: bool = False`** en `apps/classifier-service/src/classifier_service/config.py`. Comentario inline cita los 3 gates de activación (A1 + Protocolo B + validación empírica).

4. **NO conectado al pipeline real**:
   - `apps/classifier-service/src/classifier_service/services/pipeline.py` no importa este módulo en piloto-1.
   - `Classification.features` no contiene claves `guardrail_*` ni `modifier_applied` en piloto-1.
   - El `classifier_config_hash` no cambia por la existencia de este módulo.

5. **Las 4 reglas iniciales** (calibrar empíricamente post-A1):

   | Orden | Condición | Acción |
   |---|---|---|
   | 1 | `severity_3_plus_count ≥ 3` AND `overuse_confirmed` AND `appropriation == "apropiacion_reflexiva"` | bajar a `delegacion_pasiva` con `sub_branch="guardrail_triggered_combined"` |
   | 2 | `severity_3_plus_count ≥ 3` | bajar un nivel: reflexiva→superficial o superficial→delegacion_pasiva (con `sub_branch="guardrail_triggered"`); delegacion_pasiva queda igual (es el piso) |
   | 3 | `1 ≤ severity_3_plus_count ≤ 2` | NO modifica appropriation, marca `features.guardrail_warning_low_count = True` |
   | 4 | solo `overuse_confirmed` | NO modifica appropiation, marca `features.overuse_detected = True` |

   Primera regla matching gana. Las cuatro son mutuamente excluyentes por construcción del orden.

6. **Trazabilidad obligatoria**: cuando alguna regla aplique, persistir en `Classification.features`:
   - `guardrail_signals`: dict serializado de las señales.
   - `guardrail_modifier_version`: version del modificador.
   - `modifier_applied`: código de la regla (`rule_1_combined_severe`, `rule_2_three_plus_severity_3`, `rule_3_low_count_warning`, `rule_4_overuse_only`).
   - `appropriation_before_modifier`: el valor original (solo si appropriation cambió).

   Esto permite a la auditoría doctoral responder: "¿qué hubiera clasificado el árbol sin guardrail modifier?" → leer el valor original.

7. **Activación bloqueada hasta**:
   - **Gate A — A1 cerrado**: las 106 históricas re-clasificadas con `classifier_config_hash` post-LABELER 1.2.0.
   - **Gate B — Protocolo B intercoder κ ≥ 0,70 sobre el árbol de 3 categorías actual** (ADR-046). Modificar un árbol no validado es prematuro: cualquier falla del modificador puede deberse al modificador o al árbol base.
   - **Gate C — Calibración empírica de constantes**: computar el efecto del modificador sobre las 106 históricas; comparar con muestra anotada por dos docentes; ajustar umbral 3 si corresponde. Documentar en ADR-NNN nuevo.
   - **Gate D — Decisión académica de activación**: dirección + co-dirección + Ana Garis aprueban incluir el modificador en el pipeline. Si se aprueba, ADR-NNN nuevo que documente la activación; el pipeline bumpea `classifier_config_hash`.

## Drivers de la decisión

- **D1**: cerrar la brecha pedagógica identificada en informeSoc.md §2.3 (guardrails y classifier paralelos) sin romper invariantes del piloto-1.
- **D2**: respetar literalmente el ADR-019 (guardrails Fase A es **side-channel** que no bloquea el prompt al LLM). El modificador opera sobre la **clasificación post-cierre**, no sobre el flow del tutor. La Fase A sigue intacta.
- **D3**: preservar reversibilidad. El modificador es función pura sobre el output del árbol — desactivarlo y re-clasificar produce el output original. Esto es **arquitectónicamente distinto** de modificar el árbol (que sería irreversible sin re-etiquetar).
- **D4**: trazabilidad total. Cada modificación deja en `features` el valor previo + la regla aplicada. Una clasificación auditada puede explicarse en términos de qué hizo el árbol y qué hizo el modificador.
- **D5**: no modificar `delegacion_pasiva` (la regla 2 no la baja más porque ya es el piso). El árbol existente tiene `delegacion_pasiva` con dos sub_branches (`extreme`/`classic`); el modificador agrega un tercer sub_branch (`guardrail_triggered_combined` para regla 1, `guardrail_triggered` para regla 2) sin alterar la etiqueta principal.
- **D6**: fail-soft. El módulo no muta la classification de entrada (usa `dataclasses.replace`). Cualquier excepción en `extract_guardrail_signals` o `apply_guardrail_modifier` puede ser capturada por el caller sin contaminar la clasificación.
- **D7**: anticipar la calibración. Las 4 reglas iniciales son **operacionalización inicial conservadora**: la regla 1 requiere **combinación** de severidad alta + overuse para penalización máxima; la regla 3 marca warning a partir de 1 incidente. Cuando se ejecute Gate C, los umbrales pueden cambiar — el código permite bumpear `SEVERITY_3_PLUS_COUNT_THRESHOLD` y `GUARDRAIL_MODIFIER_VERSION` coordinadamente.

## Opciones consideradas

### Opción A — Esqueleto desconectado + flag OFF (elegida)

Ya descrita en la sección Decisión.

**Ventajas**:
- Cero riesgo para el piloto-1.
- Funciones puras inspeccionables y testeables sin tocar el classifier.
- Validación empírica (Gate C) se puede ejecutar sobre las 106 históricas post-A1 sin comprometer arquitectura.
- Reversible: desactivar el flag recalcula sin re-etiquetar (no es un bump irreversible de `classifier_config_hash` mientras el flag esté OFF).

**Desventajas**:
- Líneas de código sin uso productivo durante el bloqueo (~190 LOC del módulo + 14 tests + 1 flag).

### Opción B — Sexta entrada del árbol con flag OFF

Modificar la firma de `tree.py::classify` para recibir `guardrail_signals` como sexta entrada.

**Desventajas que la descartan**:
- Cambiar la firma del árbol bumpea `classifier_config_hash` aunque el flag esté OFF (porque la firma del archivo cambia y `test_pipeline_reproducibility.py` valida el hash del config). Riesgo no aceptable pre-A1.
- Requiere re-validación intercoder Protocolo B completo (el árbol cambió). Cuello de botella académico mayor.
- Pierde reversibilidad: no se puede "desactivar" la sexta entrada sin re-clasificar.

### Opción C — Eventos de guardrail con peso en CT/CCD/CII

Dar peso diferencial al `intento_adverso_detectado` dentro de las funciones de coherencia (ej. contar con peso 1.5 en `ccd_orphan_ratio`).

**Desventajas que la descartan**:
- Rompe interpretabilidad de las coherencias. Un CCD_mean alto post-modificación puede deberse a contenido o a peso de guardrail; no se distingue.
- Mezcla dos constructos teóricos distintos en una sola métrica. Académicamente cuestionable.

### Opción D — Modificador conectado al pipeline con flag OFF (patrón ADR-044)

Importar el módulo desde `pipeline.py` con `if settings.guardrail_modifier_enabled:` antes de invocarlo.

**Desventajas que la descartan**:
- Mismo problema que Opción B con la firma: importar el módulo desde el pipeline modifica el árbol de dependencias del classifier-service y puede afectar `test_pipeline_reproducibility.py`.
- Para una feature donde el bloqueo es **arquitectónico** (A1 + Protocolo B) más que **gradable** (calibración de constantes), el patrón "conectado con flag OFF" es menos seguro que "completamente desconectado".

## Criterios de éxito

1. El módulo `packages/platform-ops/src/platform_ops/guardrail_signals.py` existe y exporta `extract_guardrail_signals`, `apply_guardrail_modifier`, `GuardrailSignals`, `GUARDRAIL_MODIFIER_VERSION`, `SEVERITY_3_PLUS_COUNT_THRESHOLD`.
2. Los 14 tests en `tests/test_guardrail_signals.py` pasan en CI.
3. `apps/classifier-service/src/classifier_service/services/pipeline.py` NO importa este módulo en piloto-1 (verificable: `grep -r "guardrail_signals" apps/classifier-service/src/` devuelve 0 matches).
4. `apps/classifier-service/src/classifier_service/config.py` declara `guardrail_modifier_enabled: bool = False` con comentario que cita los gates A/B/C/D.
5. `Classification.features` no contiene claves `guardrail_signals`, `guardrail_modifier_version`, `modifier_applied`, ni `appropriation_before_modifier` en piloto-1 (verificable sobre la DB).
6. La función `apply_guardrail_modifier` no muta su input (verificable por el test `test_dos_llamadas_idempotentes` y por el assert `c.appropriation == 'apropiacion_reflexiva'` post-llamada en `test_regla_1_severidad_alta_mas_overuse_sobre_reflexiva_baja_a_delegacion`).

## Criterios de revisita (para activar)

- **Gate A — A1 cerrado**: las 106 históricas re-clasificadas. Referenciable.
- **Gate B — Protocolo B intercoder κ ≥ 0,70 sobre árbol de 3 categorías** (ADR-046). Reporte intercoder referenciable.
- **Gate C — Calibración empírica del modificador**:
   1. Computar `extract_guardrail_signals` sobre los 106 episodios históricos.
   2. Computar `apply_guardrail_modifier` sobre las 106 classifications.
   3. Comparar la distribución de modificaciones con criterio docente sobre una muestra de los episodios modificados.
   4. Si en >30% de los casos modificados los docentes discrepan, refinar reglas (típicamente bajar umbral severity_3_plus_count de 3 a 2, o subir a 4).
   5. Documentar en ADR-NNN nuevo.
- **Gate D — Decisión académica de activación**: dirección + co-dirección + Ana Garis aprueban incluir el modificador en el pipeline. El paper documenta el modificador en la sección de instrumentos. ADR-NNN nuevo que documente la activación, prendido del flag, bump del `classifier_config_hash`, y re-clasificación de las 106 una vez más (ahora con modificador activo).

Cuando los cuatro gates se cumplan, este ADR queda **superseded** por el ADR-NNN que documente la activación efectiva.

## Consecuencias

### Positivas

- Cero riesgo para el piloto-1.
- Funciones disponibles para análisis offline post-A1 (Gate C ejecutable sobre las 106).
- Trazabilidad total cuando se active: cada modificación deja huella explícita en `features`.
- Reversibilidad arquitectónica: desactivar el flag recalcula clasificaciones sin re-etiquetar eventos.
- Patrón "modificador post-árbol" establecido para futuras señales side-channel que requieran integración tardía.

### Negativas

- Líneas de código sin uso productivo durante el bloqueo (~190 LOC del módulo + 14 tests).
- Las 4 reglas iniciales pueden no sobrevivir Gate C — riesgo de re-trabajo si la calibración revela que el umbral 3 es muy estricto o muy laxo.
- Riesgo de doble penalización conceptual: un estudiante con direct_answer alto puede tener CCD bajo (por las coherencias) Y disparar regla 2 (por el modificador). Mitigación: la regla 2 baja **un nivel**, no dos. Documentado en el código y en este ADR.

### Neutras

- Contrato del CTR no cambia. `classifier_config_hash` no cambia. `LABELER_VERSION` no se bumpea.
- El módulo `guardrail_signals.py` es utilizable desde scripts ad-hoc sin levantar el classifier-service.
- El flag `guardrail_modifier_enabled` queda como settings disponible pero inerte hasta que algún caller (el pipeline u otro) lo lea.

## Referencias

- ADR-010 — CTR append-only. Restricción fundacional.
- ADR-019 — Guardrails Fase A side-channel. El modificador post-árbol respeta esa propiedad.
- ADR-027 — Diferir Fase B socratic_compliance. Patrón similar de "decisión académica humana bloquea activación técnica".
- ADR-043 — Overuse detection cross-prompt-window. Define la categoría `overuse` que el modificador usa.
- ADR-044 — Esqueleto Fase B socratic_compliance feature flag. Patrón "flag OFF a nivel de servicio" replicado en parte.
- ADR-045 — Esqueleto léxico anotación feature flag. Patrón análogo.
- ADR-046 — Intercoder κ ≥ 0,70 protocolo dual. Gate B de este ADR.
- ADR-051 — Esqueleto CEC bloqueado por A1. Patrón directo replicado de "esqueleto desconectado".
- `informeSoc.md` §2.3 — diagnóstico del hueco entre guardrails y classifier.
- `docs/research/design-integracion-guardrails-classifier.md` — design completo de R8 con análisis Opción A vs B vs C.
- `packages/platform-ops/src/platform_ops/guardrail_signals.py` — implementación.
- `packages/platform-ops/tests/test_guardrail_signals.py` — 14 tests determinísticos.
- `apps/classifier-service/src/classifier_service/config.py` — feature flag declarado.
- `apps/tutor-service/src/tutor_service/services/guardrails.py` — categorías y severidades vigentes que el modificador consume.
- `apps/classifier-service/src/classifier_service/services/tree.py` — árbol que NO se modifica en este ADR.
- `plan-accion.md` A1 — re-clasificación pendiente con DB real. Gate A de este ADR.
- `plan-accion.md` A2 — validación intercoder pendiente. Gate B de este ADR.
