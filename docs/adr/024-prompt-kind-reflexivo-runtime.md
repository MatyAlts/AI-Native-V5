# ADR-024 — Activar `prompt_kind` reflexivo en runtime (DIFERIDO a Eje B post-defensa)

- **Estado**: Aceptado (decisión: **DIFERIR**, no implementar pre-defensa)
- **Fecha**: 2026-04-29
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: classifier, ccd, contracts, eje-b
- **Cierra**: G9 del audi2.md.

## Contexto y problema

`apps/classifier-service/src/classifier_service/services/ccd.py:52,62` busca `prompt_kind == "reflexion"` para identificar verbalización reflexiva por prompt. Pero:

1. El contract Pydantic de `PromptEnviadoPayload` admite **cinco** valores de `PromptKind` (`solicitud_directa`, `comparativa`, `epistemologica`, `validacion`, `aclaracion_enunciado`) — **ninguno es `reflexion`**.
2. El tutor-service hardcodea `prompt_kind="solicitud_directa"` en [`tutor_core.py:200`](../../apps/tutor-service/src/tutor_service/services/tutor_core.py#L200).

En consecuencia, en runtime CCD **nunca activa la rama de prompts reflexivos**. La única fuente activa de verbalización es `anotacion_creada`. La 15.6 de la tesis menciona "prompt con intencionalidad reflexiva" como una de las dos fuentes de verbalización contempladas — la incoherencia entre tesis y código es la más visible que queda.

## Decisión

**DIFERIR** la implementación. La tesis ya declara honestamente el gap (15.6); el modelo híbrido funciona.

### Por qué

- **Mid-cohort introduce sesgo** ([audi2.md:82](../../audi2.md#L82)): episodios anteriores quedan con todos los prompts marcados como `solicitud_directa`. Aplicar al cierre del cuatrimestre o reclasificar todo el corpus con `classifier_config_hash` nuevo (ADR-010 cubre el patrón pero es coordinación pesada).
- **Heurísticas regex requieren validación κ contra juicio docente** (mismo protocolo que el clasificador N4, Capítulo 14). Sin validación es decisión arbitraria con apariencia de rigor.
- **audi2.md G9 timing**: *"Agenda confirmatoria. No aplicar antes de defensa. La tesis ya lo declara honestamente como gap."*

## Criterio para revisitar (Eje B post-defensa)

Implementar G9 cuando se cumpla:

1. Hay corpus de prompts del piloto etiquetado a mano para validación κ.
2. Se acepta una pausa entre cuatrimestres para reclasificar el corpus con `classifier_config_hash` actualizado.
3. T15 de `03-cambios-tesis.md` se acepta — la 15.6 declara explícitamente que en v1.0.0 la rama "prompt reflexivo" no se materializa y la activación es scope Eje B.

### Implementación propuesta (referencia)

Tres pasos detallados en audi2.md G9:

1. **Alinear contract**: agregar `"reflexion"` como sexto valor de `PromptKind`. Definir subconjuntos `REFLEXION_KINDS = {epistemologica, validacion, reflexion}` y `ACCION_KINDS = {solicitud_directa, comparativa, aclaracion_enunciado}`.
2. **Clasificar `prompt_kind` en emisión** desde tutor-service vía reglas heurísticas livianas (~80 LOC). Patrones tipo "no entendí…" / "creo que…" → `reflexion`; "dame la solución…" → `solicitud_directa`; "vs" / "diferencia entre…" → `comparativa`.
3. **Adaptar CCD**: `prompt_kind != "reflexion"` → `prompt_kind in ACCION_KINDS`; `prompt_kind == "reflexion"` → `prompt_kind in REFLEXION_KINDS`.

LOC estimado: ~150 (50 reglas + 30 contracts Pydantic + 30 contracts TS + 40 tests).

## Consecuencias de DIFERIR

### Positivas

- Coherencia en la cohorte activa del piloto-1 — todos los prompts comparten el mismo etiquetado heurístico nulo.
- `classifier_config_hash` permanece estable.
- Cero impacto en consumidores TS con `match` exhaustivo sobre los 5 valores actuales.

### Negativas

- La rama "prompt reflexivo" del CCD queda muerta en runtime — declarado en tesis 15.6 pero igualmente representa sub-cobertura observable.
- Cuando se implemente, requiere bumpear `classifier_config_hash` y reclasificar episodios históricos (ADR-010 lo cubre vía `is_current=false`).

## Referencias

- audi2.md G9 — propuesta detallada.
- ADR-010 — append-only del CTR (reclasificación con `is_current=false`).
- Tesis 15.6 — gap declarado.
- 03-cambios-tesis.md T15 — acción paralela en tesis.
