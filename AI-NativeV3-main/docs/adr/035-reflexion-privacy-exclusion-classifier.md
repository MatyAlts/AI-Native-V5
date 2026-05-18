# ADR-035 — Reflexión metacognitiva: privacy + exclusión del classifier

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: privacy, classifier, ctr, pedagogia
- **Epic**: ai-native-completion-and-byok / Sec 10

## Contexto y problema

Capturar reflexion metacognitiva del alumno post-cierre de episodio cierra
el ciclo socratico (Seccion 8.6 de la tesis). El alumno responde 3
preguntas: que aprendio, que dificultad, que haria distinto. Hay tres
decisiones criticas:

1. **Modal bloqueante o opcional?**
2. **Persistir donde — tabla nueva o evento CTR?**
3. **El classifier consume reflexiones?**

## Drivers de la decisión

- **Calidad > completitud**: respuestas forzadas son basura. Mejor 60-70%
  de respuestas honestas que 100% de respuestas vacias.
- **Append-only del CTR**: el CTR ya soporta eventos post-cierre (la cadena
  criptografica continua). No tiene sentido inventar tabla paralela.
- **Reproducibilidad bit-a-bit del classifier_config_hash**: si el
  classifier consume reflexiones, dos episodios identicos en eventos
  pedagogicos pero uno con reflexion y otro sin producirian features
  distintas. Eso rompe la propiedad doctoral de auditabilidad.
- **PII en texto libre**: el alumno puede meter su nombre o info
  identificable en los 3 campos textuales. El export academico ya tiene
  flag `include_prompts` para texto libre — el patron se replica.

## Decisión

1. **Modal opcional**, no-bloqueante. Boton "Saltar" disponible. El
   `EpisodioCerrado` se appendea al CTR ANTES de mostrar el modal — son
   flujos independientes.
2. **Solo CTR**: el evento `reflexion_completada` se appendea con
   `seq = events_count` del episodio (mismo pattern que cualquier evento).
   Sin tabla `reflections` separada — las queries del docente pasan por
   analytics-service contra `ctr_store`.
3. **Classifier IGNORA `reflexion_completada`**: filtrado explicito en
   `apps/classifier-service/.../pipeline.py::_EXCLUDED_FROM_FEATURES`.
   Test anti-regresion en `test_pipeline_reproducibility.py` valida que
   dos episodios identicos (uno con reflexion, otro sin) producen el
   mismo `classifier_config_hash` y mismas features.

## Consecuencias

### Positivas

- Tasa de respuesta esperada 60-70% — calidad > completitud (la opcionalidad
  ES un dato analizable: "respondieron reflexion" vs "que N-level alcanzaron").
- Append-only preservado.
- Reproducibilidad bit-a-bit del classifier preservada (test concreto).

### Negativas / trade-offs

- 30-40% de episodios sin reflexion → analisis longitudinal mas escaso.
  Aceptado por el doctorando.
- Editar reflexion post-envio NO es posible (CTR append-only). Modelo:
  respondes una vez o nunca. Re-respuestas serian 2 eventos distintos —
  decision: el endpoint NO acepta una segunda respuesta para el mismo
  episodio (deduplicacion en backend, follow-up).

### Neutras

- Privacy: el contenido textual va al CTR como string libre. El export
  academico (`packages/platform-ops/.../academic_export.py`) redacta los
  3 campos a `[redacted]` por default. Investigador con consentimiento
  explicito usa `--include-reflections` que emite audit log structlog
  `reflections_exported_with_consent`.

## Bug genuino que cerro este ADR

Al escribir el test anti-regresion del classifier ANTES de asumir que la
reflexion era inocua, el test fallo: `ct_summary` cambiaba de `0.54` a
`0.56` cuando habia un evento `reflexion_completada` >5min post-cierre.
Causa: el classifier consumia TODOS los eventos del CTR sin filtrar, y la
reflexion creaba una nueva ventana de trabajo (pause >5min) que afectaba
la metrica de densidad.

Fix: `_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}` en
`pipeline.py::classify_episode_from_events`, filtrado ANTES del feature
extraction. Sin este fix, la reproducibilidad bit-a-bit estaba expuesta a
contaminacion silenciosa.

## Referencias

- Spec: `openspec/changes/ai-native-completion-and-byok/specs/reflection-post-close/spec.md`
- Test: `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py::test_reflexion_completada_no_afecta_clasificacion_ni_features`
- Endpoint: `apps/tutor-service/.../routes/episodes.py::emit_reflexion_completada`
- Modal: `apps/web-student/src/components/ReflectionModal.tsx`
- Prompt: `ai-native-prompts/prompts/reflection/v1.0.0/system.md`
