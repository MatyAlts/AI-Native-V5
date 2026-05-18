# Fixes chicos al código — segunda iteración

Cambios de bajo riesgo, mayormente cosméticos o de consistencia, que alinean el código con la tesis vigente (v3.4) sin tocar la semántica del sistema, sin migrar datos persistidos y sin coordinar con el piloto en curso. Cada fix es ≤100 LOC.

Esta iteración continúa la numeración de la primera ronda. Asumo aplicados F1–F10 y F13; F11 y F12 quedaron pendientes y se retoman acá. La numeración nueva empieza en F14.

Línea editorial: **modelo híbrido**. La tesis preserva sus definiciones aspiracionales (4.3, 7.2, 8.3–8.4, 15.2–15.4) y declara honestamente la cobertura v1.0.0 (4.3.1, 8.4.1, 15.6, 19.5, 20.5.1). Estos fixes cierran inconsistencias menores entre lo declarado y lo efectivamente implementado, varias de las cuales fueron introducidas por la implementación de G3-mínimo, G4 y G5 documentada en `docs/RESUMEN-EJECUTIVO-2026-04-27.md`.

---

## F14 — Reparar el typo `GOVERNANCE_REPO_PATH` → `PROMPTS_REPO_PATH` en `.env.example`

**Estado en iter 1:** identificado pero no aplicado. El typo sigue en `.env.example:57` y se documenta como gotcha permanente en cuatro archivos: `README.md:171`, `CLAUDE.md` (sección Dev mode), `docs/SESSION-LOG.md` y `docs/servicios/governance-service.md`.

**Por qué retomarlo ahora:** el gap es de 1 LOC y la documentación del workaround creció en lugar de cerrarse. Mantener un workaround documentado en cuatro lugares cuando el fix es trivial es deuda técnica que se compone.

**Problema:** `.env.example:57` declara `GOVERNANCE_REPO_PATH=./ai-native-prompts` pero el código (`apps/governance-service/src/governance_service/config.py:23`) lee `prompts_repo_path: str = "/var/lib/platform/prompts"` desde la env var `PROMPTS_REPO_PATH`. Consecuencia: `make init` limpio en cualquier OS deja el governance-service apuntando al default que no existe en dev; tutor-service no puede abrir episodios; web-student falla con un 500 silencioso.

**Fix:**

```diff
  # Repo Git con prompt versionado (ADR-009)
- GOVERNANCE_REPO_PATH=./ai-native-prompts
+ PROMPTS_REPO_PATH=./ai-native-prompts
  GOVERNANCE_REPO_URL=git@github.com:your-org/ai-native-prompts.git
```

Acompañar con la limpieza documental: quitar el bloque "Gotcha conocido" de `README.md`, el bullet correspondiente en `CLAUDE.md` y `docs/SESSION-LOG.md`, y mover la nota del MD `docs/servicios/governance-service.md` a una sección "Histórico" análoga a la que aplicó iter 1 con la deuda PascalCase.

**Tamaño:** 1 LOC en `.env.example` + ~15 LOC borradas en docs.

**Riesgo:** Nulo. El default del código sigue siendo `/var/lib/platform/prompts`, que no se usa en dev. Quien tenía un `.env` con la var vieja debe re-cherry-pickearla; lo declara el changelog del fix.

**Test:** `apps/governance-service/tests/test_config.py::test_env_example_var_matches_settings_field` — parsea `.env.example` y assertea que existe `PROMPTS_REPO_PATH=` y que `Settings()` lo lee correctamente sin caer al default. ~15 LOC.

---

## F15 — Completar el pinning de imágenes Docker en `infrastructure/docker-compose.dev.yml`

**Estado en iter 1:** F12 quedó parcial. Verificación con `grep -E "image:" infrastructure/docker-compose.dev.yml`:

- Pineadas: `pgvector/pgvector:pg16`, `postgres:16-alpine`, `quay.io/keycloak/keycloak:25.0`, `redis:7-alpine`, `otel/opentelemetry-collector-contrib:0.150.1`, `grafana/loki:3.7.1`.
- Flotantes (siguen en `:latest`): `minio/minio:latest`, `jaegertracing/all-in-one:latest`, `prom/prometheus:latest`, `grafana/grafana:latest`.

**Problema:** un breaking change upstream en cualquiera de las cuatro imágenes flotantes rompe `make dev-bootstrap`. El piloto depende de Grafana (dashboards), Prometheus (métricas técnicas de tesis 16.1), Jaeger (traces) y MinIO (objetos). El riesgo es bajo en el día a día pero no nulo a través de meses de pilotaje.

**Fix:**

```diff
-     image: minio/minio:latest
+     image: minio/minio:RELEASE.2025-09-07T16-13-09Z
-     image: jaegertracing/all-in-one:latest
+     image: jaegertracing/all-in-one:1.62
-     image: prom/prometheus:latest
+     image: prom/prometheus:v2.55.0
-     image: grafana/grafana:latest
+     image: grafana/grafana:11.3.0
```

Las versiones específicas son las **vigentes en la fecha de bootstrapping del piloto**; verificar antes de mergear que coinciden con lo que tienen los tags actuales del entorno UNSL. El criterio es congelar las que ya están corriendo, no actualizar.

**Tamaño:** 4 LOC.

**Riesgo:** Nulo. Pinning a la versión que efectivamente está desplegada no cambia comportamiento.

**Test:** ninguno necesario; el smoke `scripts/check-health.sh` ya cubre el up del stack.

---

## F16 — Exportar `IntentoAdversoDetectado` desde `__init__.py` de contracts y agregarlo al test parity

**Origen:** **nuevo**. Hallazgo derivado de la implementación de G3 fase A.

**Problema:** la primera iteración cerró G3 mínimo agregando la clase `IntentoAdversoDetectado` en `packages/contracts/src/platform_contracts/ctr/events.py:115-141` y emitiéndola desde `apps/tutor-service/src/tutor_service/services/tutor_core.py:209-245`. Sin embargo, dejó dos puntas sueltas:

1. **No se exporta desde `packages/contracts/src/platform_contracts/ctr/__init__.py`** (verificado: la lista `__all__` no la incluye y los `from … import` tampoco). Cualquier consumidor que haga `from platform_contracts.ctr import …` no la ve y debe importarla por path completo (`from platform_contracts.ctr.events import IntentoAdversoDetectado`), que es asimétrico respecto a las otras 9 clases.

2. **El test parity `packages/contracts/tests/test_event_types_match_runtime.py` está desincronizado.** El set `_contract_event_types()` se construye sobre las 9 clases listadas explícitamente (sin `IntentoAdversoDetectado`); el set `_runtime_event_types()` lee `tutor_core.py` con regex y ahora encuentra `intento_adverso_detectado`. El assert `extras = runtime - contract` produce el set `{"intento_adverso_detectado"}` y el test debería estar fallando en cada corrida.

   El RESUMEN-EJECUTIVO afirma "274 tests automatizados pasan" y "cero regresiones"; o bien este test no se está ejecutando en CI (verificar `Makefile` y `pyproject.toml`), o bien el test pasa por algún path no obvio. Sea como fuere, el test es semánticamente incorrecto post-G3.

**Fix:**

1. En `packages/contracts/src/platform_contracts/ctr/__init__.py`, agregar la clase a los imports y a `__all__`:

```diff
  from platform_contracts.ctr.events import (
      AnotacionCreada,
      CodigoEjecutado,
      CTRBaseEvent,
      EdicionCodigo,
      EpisodioAbandonado,
      EpisodioAbierto,
      EpisodioCerrado,
+     IntentoAdversoDetectado,
      LecturaEnunciado,
      PromptEnviado,
      TutorRespondio,
  )
  ...
  __all__ = [
      "CTRBaseEvent",
      "EpisodioAbierto",
      "EpisodioCerrado",
      "EpisodioAbandonado",
+     "IntentoAdversoDetectado",
      "PromptEnviado",
      ...
  ]
```

2. En `packages/contracts/tests/test_event_types_match_runtime.py`, agregar la clase al import y al tuple del helper `_contract_event_types`, y extender el subset esperado en el test parametrizado para que `intento_adverso_detectado` sí cuente como evento del subset emitido por el tutor-service:

```diff
  from platform_contracts.ctr.events import (
      AnotacionCreada,
      CodigoEjecutado,
      EdicionCodigo,
      EpisodioAbandonado,
      EpisodioAbierto,
      EpisodioCerrado,
+     IntentoAdversoDetectado,
      LecturaEnunciado,
      PromptEnviado,
      TutorRespondio,
  )
  ...
  def _contract_event_types() -> set[str]:
      classes = (
          EpisodioAbierto,
          EpisodioCerrado,
          EpisodioAbandonado,
          PromptEnviado,
          TutorRespondio,
          LecturaEnunciado,
          AnotacionCreada,
          EdicionCodigo,
          CodigoEjecutado,
+         IntentoAdversoDetectado,
      )
      return {cls.model_fields["event_type"].default for cls in classes}
  ...
  # En el subset emitido por tutor_core directamente:
  (
      "tutor_core_emitted",
      {
          "episodio_abierto",
          "prompt_enviado",
          "tutor_respondio",
          "episodio_cerrado",
          "codigo_ejecutado",
          "edicion_codigo",
          "anotacion_creada",
+         "intento_adverso_detectado",
      },
  ),
```

`lectura_enunciado` se mantiene fuera del subset emitido directamente por tutor_core (el comment del test ya lo aclara: se emite desde el frontend vía endpoint dedicado).

**Tamaño:** ~12 LOC sumadas entre los dos archivos.

**Riesgo:** Nulo (export) / Bajo (el test). El cambio del test cierra un gap; si por alguna razón el test ya estaba pasando, ahora valida lo que declara querer validar.

**Acción paralela:** ver F17 (agregar también el TS).

---

## F17 — Agregar `IntentoAdversoDetectado` y `EpisodioAbandonado` al contract TS

**Origen:** **nuevo** para `IntentoAdversoDetectado`; **residual de iter 1** para `EpisodioAbandonado` (declarado en Pydantic pero el TS nunca lo tuvo).

**Problema:** la unión `CTREvent` en `packages/contracts/src/ctr/index.ts:142-150` incluye 8 eventos: `EpisodioAbierto`, `EpisodioCerrado`, `PromptEnviado`, `TutorRespondio`, `EdicionCodigo`, `CodigoEjecutado`, `LecturaEnunciado`, `AnotacionCreada`. El Pydantic declara 11 (los 8 + `EpisodioAbandonado` desde iter 1 + `IntentoAdversoDetectado` desde G3 fase A). Cualquier consumer TS que valide eventos contra `CTREvent.parse(event)` rompería ante un evento real `intento_adverso_detectado` o `episodio_abandonado`.

Hoy esto no rompe nada porque ningún frontend hace validación end-to-end del payload contra `CTREvent`. Pero el contract TS es el punto donde se va a apoyar la primera vista que necesite enumerar eventos del CTR (la `CohortAdversarialView` actual usa un type local en `lib/api.ts` que duplica la información) y la asimetría se va a notar entonces.

**Fix:**

```ts
// packages/contracts/src/ctr/index.ts

// Después de EpisodioCerrado, agregar:
export const EpisodioAbandonado = CTRBase.extend({
  event_type: z.literal("episodio_abandonado"),
  payload: z.object({
    reason: z.string(),  // "timeout" | "beforeunload" | "explicit" en runtime
    last_activity_seconds_ago: z.number().nonnegative(),
  }),
})
export type EpisodioAbandonado = z.infer<typeof EpisodioAbandonado>

// Después de TutorRespondio, agregar:
export const IntentoAdversoCategory = z.enum([
  "jailbreak_indirect",
  "jailbreak_substitution",
  "jailbreak_fiction",
  "persuasion_urgency",
  "prompt_injection",
])
export type IntentoAdversoCategory = z.infer<typeof IntentoAdversoCategory>

export const IntentoAdversoDetectado = CTRBase.extend({
  event_type: z.literal("intento_adverso_detectado"),
  payload: z.object({
    pattern_id: z.string(),
    category: IntentoAdversoCategory,
    severity: z.number().int().min(1).max(5),
    matched_text: z.string(),
    guardrails_corpus_hash: z.string().regex(/^[a-f0-9]{64}$/),
  }),
})
export type IntentoAdversoDetectado = z.infer<typeof IntentoAdversoDetectado>

// Y agregar a la union:
export const CTREvent = z.discriminatedUnion("event_type", [
  EpisodioAbierto,
  EpisodioCerrado,
  EpisodioAbandonado,           // ← nuevo (residual iter 1)
  PromptEnviado,
  TutorRespondio,
  IntentoAdversoDetectado,      // ← nuevo (G3 fase A)
  EdicionCodigo,
  CodigoEjecutado,
  LecturaEnunciado,
  AnotacionCreada,
])
```

**Tamaño:** ~30 LOC.

**Riesgo:** Bajo. Schema nuevo; los consumers que importen schemas individuales no se ven afectados. Para los que importen `CTREvent.parse(event)`, la unión sigue aceptando los 8 anteriores y ahora también acepta los dos nuevos cuando aparezcan.

**Test:** agregar `packages/contracts/tests/test_ts_python_parity.py` que importa el `index.ts` (vía `tsx` o equivalente) y compara los `event_type` literales del Pydantic con los de la unión Zod TS. Si la diferencia es no vacía, falla el test. ~30 LOC.

**Acción paralela en tesis:** ver `03-cambios-tesis.md` → T13 (mencionar `intento_adverso_detectado` como evento adicional del v1.0.0 en 7.2 + 4.3.1).

---

## F18 — Aclarar en `event_labeler.py` el override de `anotacion_creada` y la divergencia con la Tabla 4.1

**Origen:** **nuevo**, derivado de la implementación de G4.

**Problema:** `apps/classifier-service/src/classifier_service/services/event_labeler.py:41` hardcodea `"anotacion_creada": "N2"` en el dict `EVENT_N_LEVEL_BASE`. La docstring del módulo (líneas 21-23) ya reconoce el gap:

> `anotacion_creada` se etiqueta N2 fijo en v1.0.0. La Tabla 4.1 de la tesis sugiere que puede ser N1/N2/N4 según contenido; el override (manual del estudiante o por NLP) queda como agenda futura para no introducir embeddings antes de tiempo.

Sin embargo, la Tabla 4.1 de la tesis vigente lista "Anotación creada" bajo **N1** ("notas tomadas; reformulación verbal en el asistente") y bajo N4 ("apropiación de argumento: reproducción razonada de una explicación del asistente en producción posterior propia") según el contenido. La asignación N2 fija no aparece en la Tabla 4.1 — es una decisión del implementador, no de la tesis.

Esto significa dos cosas:

1. **Toda métrica que dependa de `time_in_level` está corriendo con un sesgo sistemático**: las anotaciones del estudiante, que en el modelo conceptual son evidencia de N1 (lectura/reformulación) o N4 (apropiación), están alimentando N2 (estrategia). El sesgo sub-reporta N1 y N4 y sobre-reporta N2.

2. **La 15.6 de la tesis dice explícitamente que la operacionalización de CT v1.0.0 "no implementa en esta versión la proporción de tiempo por nivel N1–N4… por dependencia de la instrumentación completa de eventos"**. El `event_labeler` cierra esa dependencia, así que ahora la "proporción de tiempo por nivel" sí está calculada. Pero la asignación que se está usando contradice la Tabla 4.1.

**Fix de bajo riesgo (esta iteración):** dos cambios documentales que explicitan el sesgo sin moverlo:

1. En `event_labeler.py:21-23`, ampliar el docstring para citar la Tabla 4.1 con su asignación textual y declarar la elección N2 como decisión de implementación:

```python
"""...

Override condicional para `edicion_codigo`: ...

`anotacion_creada` se etiqueta N2 fijo en v1.0.0. La Tabla 4.1 de la tesis
asigna las anotaciones a N1 ("notas tomadas; reformulación verbal en el
asistente") cuando ocurren durante la lectura del enunciado y a N4
("apropiación de argumento: reproducción razonada de una explicación del
asistente en producción posterior propia") cuando ocurren tras una respuesta
del tutor. La asignación N2 fija de v1.0.0 NO surge de la Tabla 4.1 sino que
es una decisión de implementación del labeler para no requerir clasificación
semántica del contenido en esta versión. El sesgo sistemático que esto introduce
(sub-reporta N1 y N4, sobre-reporta N2) está documentado en el reporte
empírico (Sección 17.3) y la migración a override por contenido es agenda
del Eje B (clasificación semántica) post-defensa.
"""
```

2. Agregar test de regresión que documenta la elección y bloquea cambios accidentales:

```python
# apps/classifier-service/tests/unit/test_event_labeler.py

def test_anotacion_creada_etiquetada_n2_en_v1_0_0() -> None:
    """Decisión de implementación documentada: la Tabla 4.1 de la tesis
    asigna las anotaciones a N1 o N4 según contenido. v1.0.0 las fija
    a N2 para no requerir clasificación semántica.

    Si esto cambia, hay que bumpear LABELER_VERSION (ADR-020) y actualizar
    19.5 de la tesis sobre el sesgo sistemático que se cierra.
    """
    assert label_event("anotacion_creada", payload={"content": "no entiendo"}) == "N2"
    assert label_event("anotacion_creada", payload={"content": "ya vi por qué falla"}) == "N2"
```

**Tamaño:** ~25 LOC docstring + ~15 LOC test.

**Riesgo:** Nulo. No cambia comportamiento del labeler.

**Acción paralela en tesis:** ver `03-cambios-tesis.md` → T14 (precisar en 4.3.1 / 15.6 que la operacionalización de "tiempo por nivel" v1.0.0 usa una asignación simplificada de `anotacion_creada` a N2).

**Acción paralela como cambio grande:** ver `02-cambios-codigo-grandes.md` → G8 (clasificador semántico de anotaciones para override por contenido).

---

## F19 — Documentar gap `prompt_kind="reflexion"` en CCD

**Estado en iter 1:** identificado; no resuelto.

**Problema (mismo que en la auditoría del repo anterior, persistente):** `apps/classifier-service/src/classifier_service/services/ccd.py:52,62` busca `prompt_kind == "reflexion"` para identificar verbalización reflexiva por prompt. Pero:

- El contract Pydantic (`packages/contracts/src/platform_contracts/ctr/events.py`, clase `PromptEnviadoPayload`) admite solo cinco valores: `solicitud_directa | comparativa | epistemologica | validacion | aclaracion_enunciado`. **`"reflexion"` no es admitido.**
- El runtime (`apps/tutor-service/src/tutor_service/services/tutor_core.py:176`) emite siempre `"prompt_kind": "solicitud_directa"`.
- Resultado: la rama "verbalización reflexiva por prompt" en CCD nunca se activa con datos reales del piloto. La única fuente activa de verbalización en runtime es `anotacion_creada`.

La 15.6 de la tesis menciona "prompt con intencionalidad reflexiva" como una de las dos fuentes de verbalización contempladas por CCD v1.0.0. Sin esta precisión, un lector que coteje 15.6 con el código encontrará una discrepancia no declarada.

**Fix de bajo riesgo (esta iteración):** dos cambios documentales:

1. En `apps/classifier-service/src/classifier_service/services/ccd.py:1-14`, ampliar el docstring de cabecera para documentar el gap explícitamente:

```python
"""Coherencia Código-Discurso (CCD).

...

NOTA DE IMPLEMENTACIÓN v1.0.0
-----------------------------
Este módulo trata como verbalización reflexiva a:
  (a) `anotacion_creada` (siempre), y
  (b) `prompt_enviado` con `payload.prompt_kind == "reflexion"`.

Sin embargo, "reflexion" NO es uno de los valores admitidos por
`PromptKind` en los contracts vigentes (ver
`packages/contracts/src/platform_contracts/ctr/events.py` clase
PromptEnviadoPayload). El tutor-service emite siempre
`prompt_kind="solicitud_directa"` en v1.0.0. Por tanto la rama (b)
nunca se activa con datos reales y CCD subestima la reflexividad de
prompts cuyo contenido es reflexivo pero quedan etiquetados como
"solicitud_directa".

Esta es una limitación conocida del v1.0.0, alineada con la Sección 15.6
de la tesis ("operacionalización temporal liviana, determinista, reproducible
bit-a-bit; captura una señal importante pero no su contenido"). El fix
completo —clasificación automática de prompt_kind— es scope del Eje B y se
aborda en G9.
"""
```

2. Agregar `apps/classifier-service/tests/unit/test_ccd_documenta_gap_reflexion.py` con un test que toma un prompt de contenido reflexivo emitido con `prompt_kind="solicitud_directa"` (que es lo que pasa en runtime) y verifica que CCD lo cuenta como acción huérfana, no como reflexión. Bloquea regresiones del tipo "alguien cierra el gap parcialmente sin migrar el contract".

**Tamaño:** ~25 LOC docstring + ~30 LOC test.

**Riesgo:** Nulo.

**Acción paralela en tesis:** ver `03-cambios-tesis.md` → T15 (precisar en 15.6 que la rama "prompt con intencionalidad reflexiva" no se materializa en v1.0.0).

**Acción paralela como cambio grande:** ver `02-cambios-codigo-grandes.md` → G9 (clasificador heurístico/ML de `prompt_kind`).

---

## F20 — Sincronizar `docs/servicios/ctr-service.md` con la realidad post-G3

**Origen:** **nuevo**.

**Problema:** verificación con `grep -nE "event_type|intento_adverso|episodio_abandonado" docs/servicios/ctr-service.md`. Si el MD del servicio sigue listando los 8 event_type "pre-G3" sin mencionar `intento_adverso_detectado`, está desincronizado del runtime que ahora emite 9 (descontando `episodio_abandonado` que sigue declarado pero no emitido).

**Fix:** ajustar la sección que enumera los event_types en runtime para incluir `intento_adverso_detectado` (con nota a pie hacia ADR-019) y aclarar el estado de `episodio_abandonado` (declarado en contracts, no emitido en runtime, pendiente de G10):

```diff
- `event_type` en snake_case en runtime: `episodio_abierto`, `prompt_enviado`, `codigo_ejecutado`, `tutor_respondio`, `anotacion_creada`, `edicion_codigo`, `episodio_cerrado`, `lectura_enunciado`, `episodio_abandonado`. El catálogo completo de payloads tipados vive en `packages/contracts/src/platform_contracts/ctr/events.py`.
+ `event_type` en snake_case en runtime (9 tipos efectivamente emitidos en v1.0.0): `episodio_abierto`, `prompt_enviado`, `codigo_ejecutado`, `tutor_respondio`, `anotacion_creada`, `edicion_codigo`, `episodio_cerrado`, `lectura_enunciado` (instrumentado desde el frontend), `intento_adverso_detectado` (ADR-019, side-channel del tutor-service para análisis empírico Sección 17.8). `EpisodioAbandonado` está declarado en los contratos Pydantic pero ningún servicio lo emite todavía — la decisión de cerrarlo es scope de G10. El catálogo completo de payloads tipados vive en `packages/contracts/src/platform_contracts/ctr/events.py`.
```

**Tamaño:** ~3 LOC.

**Riesgo:** Nulo, solo documentación.

---

## F21 — Sincronizar `docs/servicios/tutor-service.md` con `prompt_kind` realmente emitido

**Origen:** **nuevo**.

**Problema:** el MD `docs/servicios/tutor-service.md` afirma que el tutor enriquece los prompts con su `prompt_kind` (uno de los cinco valores), sugiriendo clasificación de intencionalidad por el lado del emisor. La realidad: tutor_core.py:176 emite siempre `"solicitud_directa"`. El MD está desalineado del runtime real.

**Fix:** una nota corta en el bullet correspondiente al evento `prompt_enviado`:

```diff
- - **CCD_mean** y **CCD_orphan_ratio** (código-discurso): correlación entre acciones (`codigo_ejecutado`, `prompt_enviado`) y verbalizaciones (`anotacion_creada`, `prompt_enviado` con `prompt_kind="epistemologica"` u otra reflexión).
+ - **CCD_mean** y **CCD_orphan_ratio** (código-discurso): correlación entre acciones (`codigo_ejecutado`, `prompt_enviado`) y verbalizaciones (`anotacion_creada`, `prompt_enviado` con `prompt_kind` reflexivo). Nota v1.0.0: el tutor-service emite siempre `prompt_kind="solicitud_directa"`; la clasificación automática de intencionalidad del prompt es agenda confirmatoria (Eje B, G9). Hoy la única fuente activa de verbalización reflexiva es `anotacion_creada`.
```

**Tamaño:** 2 LOC.

**Riesgo:** Nulo.

---

## F22 — Documentar en `EdicionCodigoPayload` que `copied_from_tutor` solo se emite parcialmente

**Origen:** **nuevo**, residual ampliable de iter 1.

**Problema:** F6 (iter 1) agregó al payload de `edicion_codigo` el campo `origin: Literal["student_typed", "copied_from_tutor", "pasted_external"]`. El backend lo recibe correctamente. El frontend (`apps/web-student/src/components/CodeEditor.tsx`) emite `student_typed | pasted_external` pero **no `copied_from_tutor`**: ese valor requiere un botón "Insertar código del tutor" que no está en la UI. Verificación: `grep -rn "copied_from_tutor" apps/web-student` → solo aparece en el type literal de TypeScript, no como string emitido.

Esta es la pieza que el `event_labeler` (G4) lee para hacer el override `edicion_codigo → N4` cuando origin ∈ {`copied_from_tutor`, `pasted_external`}. Hoy el override se activa solo por `pasted_external`; el caso `copied_from_tutor` está latente esperando UI.

**Fix:** ampliar el `description` del campo `origin` en el contract Pydantic y en el TS:

```python
# packages/contracts/src/platform_contracts/ctr/events.py:175
origin: Literal["student_typed", "copied_from_tutor", "pasted_external"] | None = (
    Field(
        default=None,
        description=(
            "Procedencia del cambio en el editor. None = legacy/desconocido. "
            "v1.0.0 emite student_typed y pasted_external desde web-student; "
            "copied_from_tutor está declarado en el contract pero requiere "
            "una afordancia de UI (botón 'Insertar código del tutor') "
            "aún no incorporada al editor del estudiante. El event_labeler "
            "(ADR-020) reconoce los tres valores y aplica override a N4 "
            "para los dos no-typed."
        ),
    )
)
```

Mismo en TS, como JSDoc.

**Tamaño:** ~12 LOC entre los dos archivos.

**Riesgo:** Nulo.

**Acción paralela como cambio grande:** ver `02-cambios-codigo-grandes.md` → G11 (botón "Insertar código del tutor" en web-student).

**Acción paralela en tesis:** ver `03-cambios-tesis.md` → T16 (precisar en 19.5 que `copied_from_tutor` está parcialmente operacional).

---

## F23 — Corregir HTML comment del prompt: GP3 sin cobertura literal

**Origen:** **nuevo** (residual de iter 1 no detectado en F9).

**Problema:** el HTML comment al pie de `ai-native-prompts/prompts/tutor/v1.0.0/system.md` (agregado por F9 iter 1) mapea:

```
GP3 (descomponer ante incomprension)  <- Principio 3 (dejar equivocarse)
GP4 (estimular verificacion ejecutiva) <- Principio 3 (descubrir el bug solo)
```

El Principio 3 textual del prompt ("Dejar que se equivoque. Si propone algo con un bug, NO lo corregís de inmediato — guialo a que descubra el bug por sí mismo") cubre semánticamente GP4 (estimulación de la verificación ejecutiva), no GP3 (descomponer ante incomprensión manifestada). El comment asigna el mismo Principio 3 a dos guardarraíles distintos, inflando la cuenta a 4/10. La cuenta correcta es **3/10** (GP1, GP2, GP4).

**Riesgo: ALTO — este fix NO es chico.** Verificación: `apps/governance-service/src/governance_service/services/prompt_loader.py:38-40` calcula `compute_content_hash` con `hashlib.sha256(content.encode("utf-8")).hexdigest()` sobre el contenido **completo del archivo**, incluyendo el HTML comment. Cualquier edición del comment cambia el `prompt_system_hash` y rompe la verificación contra `manifest.yaml`.

**Reagendado:** este fix se reclasifica a `02-cambios-codigo-grandes.md` como **G12**. La forma correcta es: bump `v1.0.0` → `v1.0.1` (PATCH según tesis 7.4: "corrección de redacción, refinamiento de instrucciones sin cambio sustantivo"); generar nuevo `manifest.yaml` con el hash recomputado; firmar el commit con GPG (ADR-009); no aplicar mid-cohort. F23 queda **anulado** en este documento — ver G12.

---

## Tabla resumen + orden sugerido

| ID | Título corto | LOC | Riesgo | Origen | Acopla con |
|----|--------------|-----|--------|--------|------------|
| F14 | Typo `GOVERNANCE_REPO_PATH` → `PROMPTS_REPO_PATH` | 1 + ~15 doc | Nulo | residual iter 1 | — |
| F15 | Pinear las 4 imágenes Docker flotantes | 4 | Nulo | residual iter 1 (F12 parcial) | — |
| F16 | Exportar `IntentoAdversoDetectado` + arreglar test parity | ~12 | Nulo / Bajo | nuevo | F17 |
| F17 | Agregar `IntentoAdversoDetectado` y `EpisodioAbandonado` al TS | ~30 + ~30 test | Bajo | nuevo + residual | F16 |
| F18 | Aclarar override de `anotacion_creada` en `event_labeler.py` | ~40 | Nulo | nuevo | G8 |
| F19 | Documentar gap `prompt_kind="reflexion"` en CCD | ~55 | Nulo | residual iter 1 | G9 |
| F20 | Sincronizar `docs/servicios/ctr-service.md` con runtime post-G3 | 3 | Nulo | nuevo | — |
| F21 | Sincronizar `docs/servicios/tutor-service.md` con `prompt_kind` real | 2 | Nulo | nuevo | — |
| F22 | Documentar que `copied_from_tutor` no se emite | ~12 | Nulo | nuevo | G11 |
| ~~F23~~ | ~~Corregir HTML comment del prompt~~ | — | — | reclasificado | Movido a G12 (cambia el hash) |

**Orden sugerido de ejecución (un commit por bloque):**

1. **Bloque A — typos bloqueantes y ops (riesgo cero, sin acoplamiento):** F14 + F15. Commit "fix(env,docker): cerrar typo PROMPTS_REPO_PATH y pinear las 4 imágenes flotantes (cierra deuda iter 1)".

2. **Bloque B — contract parity post-G3:** F16 + F17 en el mismo commit. Commit "feat(contracts): exportar IntentoAdversoDetectado, agregar EpisodioAbandonado al TS, arreglar test parity runtime↔contracts (post G3 fase A)".

3. **Bloque C — alineación documental (sin riesgo):** F18 + F19 + F20 + F21 + F22 en un commit. Commit "docs: explicitar limitaciones v1.0.0 en event_labeler, CCD, MDs de servicios y origin (alinea con tesis §15.6 / §19.5)".

Aplicación total: ~210 LOC, 3 commits ortogonales. Ningún bloque rompe la suite del piloto. F23 se reagenda como G12 por su impacto sobre el hash del prompt.
