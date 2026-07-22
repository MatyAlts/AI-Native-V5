# Design doc — Devolución metacognitiva narrativa al cierre del episodio (R5 informeSoc.md)

**Versión**: 1.0.0 — propuesta de diseño, NO implementación
**Fecha**: 2026-05-16
**Autor**: derivado de informeSoc.md §4 y §5 + política de visibilidad §3.2 Nivel 1
**Estado**: design para revisión coautoral + implementación por sub-agent en sesión futura.

---

## 0. Por qué este documento existe

El piloto actual no entrega al estudiante ninguna devolución sobre su propio proceso al cierre del episodio (excepto el modal de reflexión que ahora le pide reflexionar pero no le devuelve nada). Esta es la asimetría principal que el `politica-visibilidad-estudiante.md` propone resolver vía un "Nivel 1" opt-in.

Este documento especifica **qué se devuelve, cómo se construye, dónde se muestra, bajo qué flag y con qué garantías de invariantes criptográficas**. Es el insumo para que un sub-agent implemente el cambio en una sesión futura sin tener que reinventar el diseño.

---

## 1. Propiedades invariantes que NO se tocan

Esta es la sección defensiva del diseño. Listada primero porque cualquier implementación que viole estas propiedades se rechaza sin revisión.

1. **El CTR sigue siendo append-only**: no se modifica ningún evento existente. Si la devolución persiste algo, es un evento nuevo (`devolucion_metacognitiva_mostrada`) que se agrega al final.
2. **`classifier_config_hash` no cambia**: la devolución es lectura, no afecta el cómputo del clasificador.
3. **`LABELER_VERSION` no se bumpea**: la devolución es UI, no clasificación.
4. **k-anonimidad N≥5 sigue activa**: la devolución NO compara al estudiante con su cohorte si la cohorte tiene N<5. Sin excepciones.
5. **Nunca aparece score numérico**: la devolución es narrativa, no cuantitativa.
6. **Nunca aparece nombre de categoría de apropiación**: `reflexiva`, `superficial`, `delegacion_pasiva` son palabras del lenguaje docente, no del estudiante.
7. **Nunca aparecen los nombres N1-N4**: el etiquetador es construcción analítica, no objeto pedagógico.

---

## 2. Qué se le devuelve al estudiante

### 2.1 Estructura de la devolución

Un párrafo narrativo de 60-120 palabras, generado **determinísticamente** a partir de la cadena de eventos del episodio. No usa LLM. El determinismo es necesario para reproducibilidad (dos episodios con la misma cadena de eventos producen la misma devolución).

El párrafo tiene 3 movimientos:

**Movimiento 1 — observación**: una afirmación de hecho sobre el episodio, en lenguaje no técnico.
> "Durante este episodio le hiciste cinco preguntas al tutor."

**Movimiento 2 — patrón situado**: una lectura del patrón, sin etiqueta.
> "Tres de esas conversaciones ocurrieron después de ejecutar tests y antes de modificar el código."

**Movimiento 3 — invitación reflexiva**: una pregunta o observación que el estudiante puede llevarse, sin imponer interpretación.
> "Es información sobre cómo estás trabajando. Si te resulta útil pensarla, podés anotarte en qué momentos del próximo TP querés repetir o cambiar este patrón."

### 2.2 Reglas de generación (función pura)

La función `generate_metacognitive_feedback(events: list[dict]) -> str` vive en un nuevo módulo `packages/platform-ops/src/platform_ops/metacognitive_feedback.py`.

**Inputs**: la cadena ordenada de eventos del episodio (post-cierre, con `episodio_cerrado` ya emitido).

**Lógica determinista** (pseudocódigo):

```
def generate_metacognitive_feedback(events):
    n_prompts = count(e for e in events if e.type == "prompt_enviado")
    n_ejec = count(e for e in events if e.type == "codigo_ejecutado")
    n_tests = count(e for e in events if e.type == "tests_ejecutados")
    duracion_total = events[-1].ts - events[0].ts

    # Patrón principal a destacar (selección por reglas determinísticas en orden)
    if n_prompts == 0:
        return PLANTILLA["sin_tutor"](n_ejec, duracion_total)
    if n_prompts >= 1 and n_ejec == 0:
        return PLANTILLA["solo_conversacion"](n_prompts, duracion_total)
    if prompts_post_tests_ratio(events) >= 0.5:
        return PLANTILLA["integrando_feedback"](n_prompts, ...)
    if prompts_first_3min_ratio(events) >= 0.5:
        return PLANTILLA["consulta_temprana"](n_prompts, ...)
    return PLANTILLA["mixto"](n_prompts, n_ejec, n_tests, duracion_total)
```

Cinco plantillas, una sola se selecciona por episodio. La selección es determinística (orden fijo de reglas, primer match gana). El texto generado es reproducible bit-a-bit dada la misma cadena de eventos.

### 2.3 Plantillas

Cada plantilla se define como string con placeholders. Ejemplo de la plantilla `integrando_feedback`:

```
"Durante este episodio le hiciste {n_prompts} preguntas al tutor. {n_post_tests}
de esas conversaciones ocurrieron después de ejecutar tests, antes de cambiar
el código. Eso suele indicar que estás integrando lo que el tutor te dice
con lo que el código te muestra. Es información sobre cómo estás trabajando.
Si te resulta útil pensarla, podés anotarte qué te ayudó de ese ida y vuelta."
```

Las cinco plantillas deben:
- Ser revisadas por dirección + co-dirección pedagógica (no por el implementador solo).
- Tener 60-120 palabras cada una.
- Estar en español rioplatense neutro sin emojis (consistente con el prompt del tutor).
- NO contener juicios valorativos ("hiciste bien", "te conviene").
- NO comparar con cohorte.
- NO sugerir lo que el estudiante "debería" haber hecho.

### 2.4 Casos límite

- **Episodio con menos de 5 eventos**: devolver mensaje neutro tipo *"El episodio fue muy corto para devolver un patrón. Volvé cuando sientas que es el momento."* (plantilla `episodio_corto`).
- **Episodio con `episodio_abandonado`**: NO mostrar devolución. El estudiante salió, no terminó. Mostrar la devolución sería intrusivo.
- **Episodio con `integrity_compromised=true`** (caso de tampering detectado): NO mostrar devolución (la cadena no es confiable). Mostrar mensaje administrativo neutro.

---

## 3. Dónde se muestra

### 3.1 Ubicación en UI

Componente nuevo `MetacognitiveFeedbackPanel.tsx` en `apps/web-student/src/components/`. Aparece:

1. **Después** del modal de reflexión (`ReflectionModal`), no antes —para no contaminar la reflexión del estudiante con la lectura del sistema.
2. **Solo si** el estudiante completó O salteó la reflexión (no se muestra si cerró la página).
3. **Solo si** `metacognitive_feedback_enabled = true` para ese estudiante (opt-in, default OFF en piloto-1).

### 3.2 Estructura del componente

```tsx
<MetacognitiveFeedbackPanel
  episodeId={episodeId}
  onClose={() => setShowFeedback(false)}
/>
```

El componente:
1. Llama `GET /api/v1/episodes/{id}/metacognitive-feedback`.
2. Muestra el párrafo recibido con estilo `prose` (Tailwind typography).
3. Tiene un botón "Cerrar" único.
4. NO tiene "me gustó / no me gustó" — eso introduciría sesgo y carga al estudiante.

### 3.3 Endpoint backend

`GET /api/v1/episodes/{id}/metacognitive-feedback` en `tutor-service` (o `analytics-service`, a decidir; ver §5):

- **Auth**: el estudiante debe ser dueño del episodio (`Episode.student_pseudonym == user.id`).
- **Permission gate**: si `user.preferencia_visibilidad.metacognitive_feedback_enabled = false`, devuelve 403 con `code: feature_disabled`.
- **Cache**: el resultado se puede cachear porque es determinístico. Cache key: `{episode_id}|{labeler_version}|{template_version_metacog_fb}`.
- **Response shape**:
  ```json
  {
    "episode_id": "...",
    "feedback_template": "integrando_feedback",  // qué plantilla se seleccionó
    "feedback_text": "Durante este episodio le hiciste...",
    "metacog_feedback_version": "1.0.0",  // bumpear cuando cambian plantillas
    "generated_at": "2026-05-16T14:33:12Z"
  }
  ```

### 3.4 Evento CTR

Mostrar la devolución dispara evento `devolucion_metacognitiva_mostrada` con n_level `meta`, excluido del classifier vía `_EXCLUDED_FROM_FEATURES`:

```python
_EXCLUDED_FROM_FEATURES = frozenset({
    "reflexion_completada",
    "tp_entregada",
    "tp_calificada",
    "devolucion_metacognitiva_mostrada",  # NUEVO
})
```

Payload:
```json
{
  "feedback_template": "integrando_feedback",
  "metacog_feedback_version": "1.0.0",
  "user_acknowledged_at": null  // o timestamp si el estudiante cierra el panel
}
```

---

## 4. Versionado de plantillas

`METACOG_FEEDBACK_VERSION = "1.0.0"` es la constante del módulo. Bumpear MINOR si:
- Se agrega/quita una plantilla.
- Se modifica sustantivamente el texto de una plantilla existente.

Bumpear MAJOR si:
- Cambian las reglas de selección.
- Se cambia el modelo (de determinístico a LLM, por ejemplo —desaconsejado).

Cada versión queda accesible vía el campo `metacog_feedback_version` del payload, permitiendo trazabilidad: "el estudiante X vio la devolución v1.0.0, el estudiante Y vio la v1.1.0".

---

## 5. Decisión pendiente — ¿en qué servicio vive?

Dos opciones:

**Opción A — `tutor-service`**: la generación vive cerca del tutor, que es quien interactúa con el estudiante. Pros: el frontend ya habla con tutor-service. Cons: tutor-service hoy es write-only al CTR (excepto `codigo_ejecutado`); agregar la generación implicaría lectura del CTR para construir el patrón → revisar ADR-010 sobre write-only.

**Opción B — `analytics-service`**: la generación vive donde ya están las funciones puras de análisis (`cii_longitudinal`, `cii_alerts`). Pros: respeta separación tutor-write / analytics-read. Cons: el frontend tiene que llamar a un servicio nuevo para esta función.

**Recomendación**: **Opción B**. Coherente con la arquitectura de dos planos (operacional vs analítico) declarada en `CLAUDE.md`. La devolución metacognitiva es análisis, no tutoría.

---

## 6. Trabajo de implementación estimado

| Tarea | Esfuerzo | Quién |
|---|---|---|
| Definir las 5 plantillas con dirección + co-dirección | 6-8 h | humanos |
| Implementar función pura `generate_metacognitive_feedback` + tests unit | 4-6 h | sub-agent |
| Endpoint `GET /metacognitive-feedback` en `analytics-service` + auth gate | 4-6 h | sub-agent |
| Componente UI `MetacognitiveFeedbackPanel.tsx` + integración en `EpisodePage` | 4-6 h | sub-agent |
| Migración de schema para `preferencia_visibilidad` por usuario | 2-3 h | sub-agent |
| Evento CTR `devolucion_metacognitiva_mostrada` + `_EXCLUDED_FROM_FEATURES` | 1-2 h | sub-agent |
| Tests smoke E2E del flujo completo | 3-4 h | sub-agent |
| ADR-051 documentando la decisión + invariantes | 2-3 h | sub-agent |
| **Total** | **26-38 h** | (16-24 h sub-agent + 10-14 h coordinación humana) |

El estimado del informeSoc.md original era 16-24 h. Refinado: 26-38 h totales incluyendo redacción de plantillas (que es el cuello de botella académico).

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Una plantilla puede leerse como juicio por algún estudiante. | Revisión coautoral de las 5 antes de soltar. Test usabilidad con 3-5 estudiantes piloto. |
| El estudiante ignora la devolución (cierra rápido) y queda como ruido visual. | Capturar `user_acknowledged_at` en el evento CTR para medir engagement. Si en piloto-2 el engagement es <40%, repensar la UX. |
| Determinismo se rompe si los timestamps son inconsistentes entre instancias. | Función pura sobre payload normalizado. Tests golden con cadenas de eventos conocidas. |
| Activar la feature flag bumpea sin querer el classifier_config_hash. | Imposible por diseño: `_EXCLUDED_FROM_FEATURES` excluye el nuevo evento del feature extraction. Test anti-regresión obligatorio. |

---

## 8. Referencias

- informeSoc.md §4 (asimetría visibilidad) y §5 (oportunidad reflexión).
- politica-visibilidad-estudiante.md §3.2 Nivel 1.
- ADR-010 — CTR append-only. Define los límites del nuevo evento.
- ADR-022 — alertas como pedagógicas no clínicas. Línea de razonamiento análogo.
- ADR-035 — `reflexion_completada` excluida del classifier. Antecedente para `devolucion_metacognitiva_mostrada`.
- Flavell (1979), Schraw (1998), Veenman (2006) — base teórica de la metacognición.
