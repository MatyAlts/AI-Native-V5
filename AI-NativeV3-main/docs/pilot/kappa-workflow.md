# Procedimiento intercoder para Cohen's kappa (OBJ-13)

Workflow operativo para que dos docentes etiqueten independientemente un set de episodios y se calcule κ contra el clasificador automático N4. Es la evidencia empírica de **OBJ-13 (intercoder reliability)** del piloto UNSL.

> Referencias canónicas: **RN-095** (interpretación Landis & Koch + objetivo κ ≥ 0.6), **RN-096** (3 categorías estrictas), **RN-111** (gold standard humano obligatorio para A/B). Endpoint: `POST /api/v1/analytics/kappa` (`apps/analytics-service/src/analytics_service/routes/analytics.py`). Implementación: `packages/platform-ops/src/platform_ops/kappa_analysis.py::compute_cohen_kappa`.

## 1. Objetivo

La tesis sostiene que el clasificador N4 mide apropiación cognitiva de manera consistente con el juicio docente. Sin κ ≥ 0.6 ese sostén se cae: cualquier afirmación posterior sobre trayectorias o A/B de profiles queda sin base. Por eso el etiquetado intercoder debe ejecutarse **antes** de abrir el piloto a los estudiantes, y repetirse en cada iteración del `reference_profile`.

## 2. Pre-requisitos

- Cohorte enrolada en `enrollment-service` con al menos una `tarea_practica` cerrada.
- ≥ 50 episodios en estado `closed` (con eventos de `prompt_enviado`, `tutor_respondio`, `codigo_ejecutado` y `validacion_*`) en el `tenant_id` del piloto.
- 2 docentes designados por el equipo de investigación (uno debe ser el responsable pedagógico de la cátedra; el otro, externo a la implementación). El nombramiento debe quedar registrado en el acta del comité del piloto.
- Acceso de los 2 docentes al `web-teacher` con rol `docente` y `X-Tenant-Id` correcto.
- `TOKEN` con permisos para `POST /api/v1/analytics/kappa` (rol `docente_admin` o `investigador`).

## 3. Selección de la muestra

- **Tamaño**: 50 episodios (mínimo del protocolo §4.3; subir a 60–80 si hay desbalance fuerte de clases).
- **Estrategia**: muestreo aleatorio **estratificado por la clasificación automática** del `classifier-service`, para asegurar representación de las 3 categorías N4 (`delegacion_pasiva`, `apropiacion_superficial`, `apropiacion_reflexiva`). Si el clasificador todavía no corrió, estratificar por `tarea_practica_id`.
- **Criterio fijado por el investigador responsable** (Alberto Cortez para el piloto UNSL); el script de muestreo y la `seed` aleatoria se commitean en `docs/pilot/kappa-tuning/sample-YYYY-MM-DD.md` para reproducibilidad.
- **Excluir** episodios con `integrity_compromised=true` (RN-039/RN-040) — no son evidencia válida.

## 4. Proceso de tagging

1. El investigador genera la plantilla `gold-standard-template.json` (ver §6) con los 50 `episode_id` y `human_label: null`.
2. Cada docente recibe **una copia separada** de la plantilla y revisa cada episodio en `web-teacher → /episodes/<id>` viendo: enunciado de la `tarea_practica`, secuencia completa de eventos del CTR, código final, resultado de validación.
3. Cada docente asigna `human_label` ∈ `{delegacion_pasiva, apropiacion_superficial, apropiacion_reflexiva}` (RN-096 — exactamente esos tres valores; cualquier otro string rompe el endpoint).
4. **Sin colusión**: nada de notas compartidas, ni chat, ni revisar la etiqueta del clasificador automático antes de tagear (sesgaría hacia acuerdo artificial).
5. **Presupuesto de tiempo**: 5–10 min por episodio. 50 episodios ≈ 5–8 hs por docente; partir en 2 sesiones.
6. Cada docente devuelve su JSON completo al investigador, que arma el body del `POST /analytics/kappa` mapeando `rater_a` = docente 1, `rater_b` = docente 2.

## 5. Submission al endpoint

```bash
TOKEN="<jwt-investigador>"
TENANT="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER="11111111-1111-1111-1111-111111111111"

curl -X POST http://127.0.0.1:8000/api/v1/analytics/kappa \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-Id: $TENANT" \
  -H "X-User-Id: $USER" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON' | jq .
{
  "ratings": [
    {"episode_id": "11111111-1111-1111-1111-111111111001", "rater_a": "apropiacion_reflexiva", "rater_b": "apropiacion_reflexiva"},
    {"episode_id": "11111111-1111-1111-1111-111111111002", "rater_a": "apropiacion_superficial", "rater_b": "apropiacion_reflexiva"},
    {"episode_id": "11111111-1111-1111-1111-111111111003", "rater_a": "delegacion_pasiva", "rater_b": "delegacion_pasiva"}
  ]
}
JSON
```

Response esperado (forma `KappaResponse`):

```json
{
  "kappa": 0.6842,
  "n_episodes": 50,
  "observed_agreement": 0.84,
  "expected_agreement": 0.49,
  "interpretation": "sustancial",
  "per_class_agreement": {
    "delegacion_pasiva": 0.81,
    "apropiacion_superficial": 0.62,
    "apropiacion_reflexiva": 0.88
  },
  "confusion_matrix": { "...": "..." }
}
```

## 6. Plantillas

- **Vacía**: `docs/pilot/kappa-tuning/gold-standard-template.json` — copiar y completar `cohort_id`, `sample_date`, `selected_episodes`.
- **Ejemplo tagueado**: `docs/pilot/kappa-tuning/gold-standard-example.json` — referencia de cómo queda un JSON completo de un docente (con `human_label` rellenado).

## 7. Interpretación del resultado

Escala Landis & Koch 1977 (RN-095, idéntica a `KappaResult.interpretation`):

| κ | Interpretación |
|---|---|
| < 0.20 | pobre |
| 0.21 – 0.40 | justo |
| 0.41 – 0.60 | moderado |
| 0.61 – 0.80 | sustancial |
| 0.81 – 1.00 | casi perfecto |

**Objetivo de la tesis: κ ≥ 0.6** (acuerdo sustancial).

Leer también `per_class_agreement`: si una clase queda < 0.5 mientras κ global está OK, hay un problema localizado en esa categoría que toca refinar.

## 8. Acción según resultado

| Caso | Acción |
|---|---|
| κ ≥ 0.6 | Declarar reliability. Documentar en `docs/pilot/kappa-tuning/kappa-baseline-YYYY-MM-DD.md`: `kappa`, `n_episodes`, matriz de confusión, IDs de docentes, fecha. Adjuntar el response JSON. Habilita el piloto. |
| 0.4 ≤ κ < 0.6 | Reunión de calibración: revisar los desacuerdos episodio por episodio, refinar criterios escritos de las 3 categorías, **muestrear 50 episodios distintos** y volver a tagear. No reusar la misma muestra (sesgo de ajuste). |
| κ < 0.4 | Disparar **I04** del runbook: revisar el `reference_profile` del clasificador, no sólo los criterios docentes. El gap puede estar en los thresholds, no en la subjetividad humana. |

## 9. Pitfalls comunes

- **No compartir notas durante el tagging** — invalida la independencia. Si los docentes hablan sobre episodios, ese batch se descarta.
- **No mirar la etiqueta del clasificador automático antes de tagear** — sesga hacia acuerdo artificial; κ saldría inflado.
- **No reusar la misma muestra** después de un κ insuficiente — el segundo cómputo mediría ajuste a la muestra, no acuerdo intercoder.
- **No mezclar etiquetas de docentes distintos** entre runs — `rater_a` siempre el mismo docente, `rater_b` el otro, en TODOS los episodios del batch.
- **Excluir episodios con `integrity_compromised=true`** del muestreo (RN-039/RN-040) — su cadena CTR no es confiable.
- **Validar antes de mandar**: si un `human_label` quedó `null` o con typo, Pydantic `Literal` (RN-096) rechaza el batch entero con HTTP 422.

## 10. Referencias cruzadas

- **Runbook I04** (`docs/pilot/runbook.md`): qué hacer si κ baja **durante** el piloto (ya con datos productivos). Este workflow cubre la fase **previa** al piloto.
- **RN-111** (`reglas.md`): A/B de profiles requiere gold standard humano — el JSON tagueado de §6 sirve también como input de `POST /api/v1/analytics/ab-test-profiles`.
- **`scripts/eval-retrieval.py`**: gate análogo para `content-service`. Mismo espíritu (evaluación humana antes de cambios de contrato), distinto subsistema.
