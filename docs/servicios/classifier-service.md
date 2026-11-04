# classifier-service

## 1. Qué hace (una frase)

Clasifica episodios cerrados del CTR en categorías N4 (`delegacion_pasiva`, `apropiacion_superficial`, `apropiacion_reflexiva`) calculando tres coherencias independientes (CT, CCD, CII) y aplicando un árbol de decisión explicable parametrizado por un `reference_profile`, con persistencia append-only.

## 2. Rol en la arquitectura

Pertenece al **plano pedagógico-evaluativo**. Materializa el componente "Clasificador N4" descrito en el Capítulo 6 de la tesis (arquitectura C4 del sistema AI-Native), cuyas responsabilidades nominales son: traducir la secuencia de eventos de un episodio en una categoría pedagógica interpretable, producir las features intermedias (las 3 coherencias) que permiten explicar la decisión, y mantener el hash de configuración (`classifier_config_hash`) que hace la clasificación reproducible bit-a-bit.

## 3. Responsabilidades

- Exponer `POST /api/v1/classify_episode/{episode_id}` que trae los eventos del episodio desde [ctr-service](./ctr-service.md), corre el pipeline completo y persiste la clasificación.
- Implementar el pipeline de clasificación como función pura y determinista: `classify_episode_from_events(events, reference_profile)` produce el mismo `ClassificationResult` para el mismo input.
- Calcular las **3 coherencias agregadas en 5 métricas separadas**: `ct_summary` (temporal), `ccd_mean` + `ccd_orphan_ratio` (código-discurso), `cii_stability` + `cii_evolution` (inter-iteración). Nunca colapsarlas en un score único (invariante crítico — CLAUDE.md "Propiedades críticas").
- Aplicar el árbol de decisión (`services/tree.py`) con los umbrales del `reference_profile` activo. Árbol explicable — cada rama produce un `appropriation_reason` en texto que justifica la categoría asignada.
- **Etiquetar eventos con N1-N4 derivado en lectura** ([ADR-020](../adr/020-event-labeler-n-level.md)): `event_labeler.py::label_event(event_type, payload, context=None)` función pura. **`LABELER_VERSION = "1.2.0"`** ([ADR-034](../adr/034-test-cases-tp.md)): v1.0.0 → v1.1.0 (override temporal `anotacion_creada` por ventana posicional, [ADR-023](../adr/023-anotacion-temporal-override.md)) → v1.2.0 (regla N3/N4 sobre `tests_ejecutados`).
- **Excluir explícitamente eventos side-channel post-cierre del feature extraction** (RN-133): `_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}` en `pipeline.py`. Test anti-regresión `test_reflexion_completada_no_afecta_clasificacion_ni_features` en `tests/unit/test_pipeline_reproducibility.py`. **NO romper este test** al refactorizar classifier o agregar event types nuevos — si emerge un evento side-channel post-cierre, agregalo al set.
- Computar `classifier_config_hash` de forma determinista: `sha256(json.dumps({"tree_version": ..., "profile": ...}, sort_keys=True, ensure_ascii=False, separators=(",", ":")))`. Cualquier cambio en serialización rompe reproducibilidad (CLAUDE.md "Constantes que NO deben inventarse").
- Persistir append-only (ADR-010): si existe clasificación con el **mismo** `classifier_config_hash` para un episodio, es no-op (idempotencia). Si existe con **otro** hash, marca la anterior `is_current=false` e inserta la nueva con `is_current=true`.
- Exponer `GET /api/v1/classifications/{episode_id}` (la current del episodio) y `GET /api/v1/classifications/aggregated` (distribución + promedios + timeseries para dashboard docente).

## 4. Qué NO hace (anti-responsabilidades)

- **NO emite ni modifica eventos del CTR**: es consumidor read-only. Todas las escrituras al CTR pasan por [tutor-service](./tutor-service.md).
- **NO dispara automáticamente al cerrarse el episodio**: el pipeline está descripto como worker en el docstring de `services/pipeline.py`, pero el trigger corriente es manual (`POST /classify_episode/{id}`). El hook automático desde el stream `ctr.p*` está previsto en F3+ y hoy (F9) no hay worker en `apps/classifier-service/src/classifier_service/workers/` — **verificar estado actual**. El endpoint manual cubre el piloto.
- **NO retorna un score único**: devuelve 5 valores + una categoría + un texto-razón. Cualquier colapso a escalar único distorsiona la tesis.
- **NO es black-box**: el árbol en `tree.py` es un `if/elif/else` legible con umbrales en el `reference_profile`. No hay modelo entrenado, no hay pesos opacos.
- **NO valida autorización de negocio**: confía en headers `X-*` del api-gateway. Tiene `CLASSIFY_ROLES` y `READ_ROLES` sólo como check de rol-a-endpoint.

## 5. Endpoints HTTP

| Método | Path | Qué hace | Auth |
|---|---|---|---|
| `POST` | `/api/v1/classify_episode/{episode_id}` | Trae el episodio del CTR, corre el pipeline, persiste la clasificación. Idempotente por `classifier_config_hash`. | Rol en `CLASSIFY_ROLES`. |
| `GET` | `/api/v1/classifications/{episode_id}` | Clasificación `is_current=true` del episodio. 404 si no hay. | Rol en `READ_ROLES`. |
| `GET` | `/api/v1/classifications/aggregated?comision_id=...&period_days=30` | Distribución + promedios de coherencias + timeseries diaria para dashboard docente. | Rol en `READ_ROLES`. |
| `GET` | `/health`, `/health/ready` | Health real con `check_postgres` + `check_http(ctr)` (epic `real-health-checks`, 2026-05-04). | Ninguna. |

**Estudio de codificación ciega** ([ADR-063](../adr/063-estudio-codificacion-ciega.md), change `cibse-codificacion-ciega`). Prefijo `/api/v1/interrater/estudios`, ya ruteado por el gateway vía `/api/v1/interrater`. Todo pasa por `require_gateway_auth`. El acceso es por **membresía** del estudio (email asignado, atado al `X-User-Id` en el primer uso), no por rol: los roles `superadmin`/`docente_admin` solo crean estudios y gestionan membresías.

| Método | Path (relativo al prefijo) | Qué hace | Quién |
|---|---|---|---|
| `POST` | `` | Alta de estudio (`{clave, titulo}`); fija `traza_version` | `superadmin`/`docente_admin` |
| `GET` | `/mis-membresias` | Membresías activas del caller (cuenta como primer uso: ata el `user_id`) | cualquiera |
| `POST`/`GET` | `/{clave}/membresias` | Asignar (`{email, rol}`) / listar (email, alias, estado, fechas; nunca etiquetas) | investigador o admin |
| `DELETE` | `/{clave}/membresias/{membresia_id}` | Revocar (no borra; una re-asignación crea membresía nueva) | investigador o admin |
| `POST` | `/{clave}/codebook` | Versión nueva en borrador, vacía o `clonar_de` | investigador |
| `PUT` | `/{clave}/codebook/{etiqueta}` | Texto y esquema de un borrador (400 si el esquema no valida; 409 si está congelada) | investigador |
| `POST` | `/{clave}/codebook/{etiqueta}/congelar` | Congela con sha256 de texto, esquema y anclas | investigador |
| `PUT` | `/{clave}/codebook-vigente` | Fija la vigente (`{etiqueta}`); 409 si ya hay etiquetas | investigador |
| `GET` | `/{clave}/codebook/vigente` | Vigente (404 `sin_codebook` si no hay) | miembro |
| `GET` | `/{clave}/codebook/versiones` y `/versiones/{etiqueta}` | Versiones; anclas completas solo para el investigador | miembro |
| `GET`/`POST` | `/{clave}/codebook/{etiqueta}/anclas` | Listar / crear ancla (lee el CTR y fija evidencia) | investigador |
| `PUT`/`DELETE` | `/{clave}/codebook/{etiqueta}/anclas/{item_id}` | Editar / borrar ancla de un borrador | investigador |
| `POST` | `/{clave}/muestra[?sha256_esperado=]` | Muestra: cuerpo `text/csv` crudo; guarda solo `episode_id` + evidencia fija | investigador |
| `POST`/`GET` | `/{clave}/enunciados` | Cargar enunciados (`text/csv` crudo) / cobertura, alertas y estado | investigador |
| `POST` | `/{clave}/enunciados/{id}/revision` | Aprobar (`{"contenido_mostrado_md": null}`) o guardar versión editada | investigador |
| `GET` | `/{clave}/items` | Ítems del codificador en su orden: `{item_id, posicion, estado}` | codificador |
| `GET` | `/{clave}/items/{item_id}/traza` | Traza ciega (`traza_v1`) + enunciado; 409 `evidencia_alterada`/`traza_version_distinta`/`enunciado_pendiente`; 502 si el CTR no responde | miembro |
| `GET`/`PUT` | `/{clave}/items/{item_id}/mi-etiqueta` | Etiqueta propia (vacía si no hay) / guardado incremental; 409 `codebook_borrador`, `codificacion_cerrada`, `enunciados_pendientes` | codificador |
| `POST` | `/{clave}/mi-codificacion/cerrar` | Cierre (422 `{codigo: "incompleta", faltantes}`) | codificador |
| `GET` | `/{clave}/progreso` | Cantidades por codificador, sin valores | investigador |
| `GET` | `/{clave}/entrenamiento` | Codebook vigente, ejemplos con respuesta, prácticas a ciegas | miembro |
| `POST` | `/{clave}/entrenamiento/{item_id}/respuesta` | Respuesta de práctica (append-only) y devolución de esa ancla | miembro |
| `GET` | `/{clave}/exportacion?contenido=etiquetas\|entrenamiento\|historial&formato=csv\|json` | Exportación para análisis, sin emails ni contenido de episodios | investigador |

**Nota de ordenamiento de rutas**: `/classifications/aggregated` se registra **antes** que `/classifications/{episode_id}` para que FastAPI no matchee `"aggregated"` como UUID path param. Es un detalle de implementación en `routes/classify_ep.py:116`.

**Ejemplo de `POST /classify_episode/{id}` — response `ClassificationOut`**:

```json
{
  "episode_id": "7b3e7c8e-1a4f-4a6c-9b2e-3c0d5e6f7a1b",
  "comision_id": "a1a1a1a1-...",
  "classifier_config_hash": "e5f6a7b8c9d0...64hex",
  "appropriation": "apropiacion_reflexiva",
  "appropriation_reason": "Coherencia temporal alta (ct=0.78), alineación código-discurso (ccd_mean=0.72, orphans=0.18), estabilidad de enfoque (cii_stab=0.65): evidencia de trabajo sostenido con profundización.",
  "ct_summary": 0.78,
  "ccd_mean": 0.72,
  "ccd_orphan_ratio": 0.18,
  "cii_stability": 0.65,
  "cii_evolution": 0.58,
  "is_current": true
}
```

**Ejemplo de `GET /classifications/aggregated?comision_id=...&period_days=30`** — `AggregatedStatsOut`:

```json
{
  "comision_id": "a1a1a1a1-...",
  "period_days": 30,
  "total_episodes": 94,
  "distribution": {
    "delegacion_pasiva": 12,
    "apropiacion_superficial": 58,
    "apropiacion_reflexiva": 24
  },
  "avg_ct_summary": 0.52,
  "avg_ccd_mean": 0.48,
  "avg_ccd_orphan_ratio": 0.35,
  "avg_cii_stability": 0.41,
  "avg_cii_evolution": 0.47,
  "timeseries": [
    { "date": "2026-04-01", "counts": { "delegacion_pasiva": 1, "apropiacion_superficial": 3, "apropiacion_reflexiva": 0 } },
    { "date": "2026-04-02", "counts": { "delegacion_pasiva": 0, "apropiacion_superficial": 5, "apropiacion_reflexiva": 2 } }
  ]
}
```

Sólo cuenta filas con `is_current=true` — una reclasificación posterior con otro profile **no altera** el agregado histórico (hay que pedir explícitamente la nueva).

## 6. Dependencias

**Depende de (infraestructura):**
- PostgreSQL — base lógica `classifier_db` (ADR-003), usuario dedicado.
- [ctr-service](./ctr-service.md) — `GET /api/v1/episodes/{episode_id}` para traer los eventos del episodio a clasificar.
- [ctr-service](./ctr-service.md), estudio de codificación — mismo endpoint, con la cuenta de servicio propia `ESTUDIO_LECTOR_SERVICE_USER_ID` (`00000000-0000-0000-0000-000000000c0d`, rol `classifier_worker`, firma HMAC si hay `GATEWAY_SHARED_SECRET`, timeout 15 s; `services/ctr_lectura.py`). Solo se usa con `episode_id` resueltos desde la muestra o las anclas del estudio, nunca desde un pedido.

**Depende de (otros servicios):** sólo ctr-service.

**Dependen de él:**
- [analytics-service](./analytics-service.md) — lee `classifier_db` directamente (read-only con RLS) para κ, A/B de profiles, progresión longitudinal, export académico.
- [web-teacher](./web-teacher.md) — consume `/classifications/aggregated` para dashboards.

## 7. Modelo de datos

Base lógica: **`classifier_db`** (ADR-003). Migraciones en `apps/classifier-service/alembic/versions/`.

**Tabla única principal** (`apps/classifier-service/src/classifier_service/models/__init__.py`):

- **`classifications`**
  - PK: `id` BigInteger autoincrement.
  - `tenant_id` con RLS policy (migración `20260902_0002`).
  - `episode_id` (UUID) + `comision_id` (UUID) — indexados.
  - `classifier_config_hash` (CHAR(64)) — el hash determinista del árbol+profile usados.
  - `appropriation` — una de `{delegacion_pasiva, apropiacion_superficial, apropiacion_reflexiva}`.
  - `appropriation_reason` — texto explicativo generado por la rama del árbol.
  - `ct_summary`, `ccd_mean`, `ccd_orphan_ratio`, `cii_stability`, `cii_evolution` — los 5 floats separados.
  - `features` JSONB — features intermedios (ventanas de CT, pairs de CCD, etc.) para debugging.
  - `classified_at`, `is_current` (bool).
  - Constraints: `UniqueConstraint(episode_id, classifier_config_hash)` — garantiza idempotencia por par episodio+config.
  - Index: `ix_classifications_episode_current` sobre `(episode_id, is_current)` para el lookup típico "cuál es la current de este episodio".

**Tablas del estudio de codificación ciega** (migración `20261104_0007`, `models/estudio.py`, [ADR-063](../adr/063-estudio-codificacion-ciega.md)). Todas con `tenant_id` y RLS forzado. Solo las leen endpoints del estudio: ni el agregado κ del piloto ni `pedagogia.py` las tocan.

| Tabla | Contenido | Inmutabilidad (trigger) |
|---|---|---|
| `estudio_codificacion` | `clave` (única por tenant), título, `codebook_vigente_id`, `muestra_sha256`, `muestra_cargada_at`, `traza_version` | — |
| `estudio_membresia` | email (minúsculas), `rol` (`investigador`/`codificador`), `alias`, `semilla`, `user_id` (atado en el primer uso), `cerrada_at`, `revocada_at`; una activa por `(estudio, lower(email))` | — |
| `estudio_muestra` | `item_id` opaco, `episode_id`, evidencia fija (`seq_tope`, `chain_hash_tope`, `events_count_carga`, `last_chain_hash_carga`, `estado_carga`), `problema_id`, `ejercicio_id`; único `(estudio, episode_id)` | sin UPDATE de evidencia ni ids |
| `estudio_enunciado` | `fuente` (`tp`/`ejercicio`), `fuente_id`, `archivo_sha256`, original y su sha, mostrado y su sha, `alertas`, revisión | sin UPDATE ni DELETE una vez revisado |
| `codebook_version` | `etiqueta`, `estado` (`borrador`/`congelada`), `contenido_md`, `esquema_formulario` (JSONB), `contenido_sha256`, `congelada_at/por` | congelada: sin UPDATE ni DELETE |
| `estudio_ancla` | `item_id` opaco, versión, `episode_id`, evidencia fija, `uso`, `orden`, `respuesta_esperada`, `explicacion_md`, `consensuado_por` | de versión congelada: sin INSERT, UPDATE ni DELETE; evidencia sin UPDATE |
| `estudio_etiqueta` | por `(membresía, ítem)`: `respuestas` (JSONB), `regimen`, `regimen_regla`, `regimen_propuesto`, `es_frontera`, `confianza`, `notas`, versión del codebook y de la traza | — (upsert) |
| `estudio_etiqueta_historial` | snapshot de cada guardado | append-only |
| `entrenamiento_respuesta` | respuesta a una práctica, con versión vigente y traza | append-only |

**Append-only con `is_current`** (ADR-010): reclasificar NO borra la fila vieja — la marca `is_current=false` e inserta la nueva con `is_current=true`. El historial queda preservado para auditorías de cambios de profile. Las estadísticas agregadas sólo cuentan filas `is_current=true`.

## 8. Archivos clave para entender el servicio

- `apps/classifier-service/src/classifier_service/services/pipeline.py` — orquestador. `compute_classifier_config_hash()` es la función del hash determinista (ver cita en Sección 9). `classify_episode_from_events()` es la función pura que otros tests pueden llamar directamente. `persist_classification()` implementa el append-only. **`_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}`** (RN-133) — set crítico que protege el `classifier_config_hash` reproducible bit-a-bit.
- `apps/classifier-service/src/classifier_service/services/event_labeler.py` — `label_event()` función pura + `LABELER_VERSION = "1.2.0"` ([ADR-034](../adr/034-test-cases-tp.md)). v1.1.0 metió override temporal de `anotacion_creada` por ventana posicional ([ADR-023](../adr/023-anotacion-temporal-override.md)) — constantes `ANOTACION_N1_WINDOW_SECONDS = 120.0` y `ANOTACION_N4_WINDOW_SECONDS = 60.0`. v1.2.0 metió regla N3/N4 sobre `tests_ejecutados` (`tests_passed/tests_total` ≥ umbral → N4; ≥ otro umbral → N3). `time_in_level()` y `n_level_distribution()` construyen contextos automáticamente con `_build_event_contexts()`. **Bumpear MINOR re-etiqueta históricos** (RN-020) sin tocar el CTR.
- `apps/classifier-service/src/classifier_service/services/tree.py` — el árbol N4. `DEFAULT_REFERENCE_PROFILE` (umbrales por default). `classify()` — lógica explícita con 3 ramas principales (`delegacion_pasiva`, `apropiacion_reflexiva`, `apropiacion_superficial` como fallback). Cada rama construye un `reason` con los valores concretos que la gatillaron.
- `apps/classifier-service/src/classifier_service/services/ct.py` — coherencia temporal. Ventanas de trabajo separadas por `PAUSE_THRESHOLD = 5min`. Preserva las ventanas individuales en `features` para explainability.
- `apps/classifier-service/src/classifier_service/services/ccd.py` — coherencia código-discurso. `CORRELATION_WINDOW = 2min` para decidir si una acción tiene un "giro verbal" correlacionado.
- `apps/classifier-service/src/classifier_service/services/cii.py` — coherencia inter-iteración. Proxy de estabilidad: overlap de tokens entre prompts consecutivos. Proxy de evolución: longitud media a lo largo del episodio.
- `apps/classifier-service/src/classifier_service/services/aggregation.py` — agregación para `/classifications/aggregated`. Distribución, promedios y timeseries diaria.
- `apps/classifier-service/src/classifier_service/routes/classify_ep.py` — los 3 endpoints. Atención al orden de registro (aggregated antes que `{episode_id}`).
- `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py` — test clave que bloquea regresiones en el hash determinista.

**Fórmula del hash determinista — ¡no cambiar!**

```python
# apps/classifier-service/src/classifier_service/services/pipeline.py:34
def compute_classifier_config_hash(
    reference_profile: dict[str, Any], tree_version: str = "v1.0.0"
) -> str:
    canonical = json.dumps(
        {"tree_version": tree_version, "profile": reference_profile},
        sort_keys=True,
        ensure_ascii=False,         # ← CON ensure_ascii=False
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
```

**Comparación con el `self_hash` del CTR** (ver [ctr-service](./ctr-service.md) Sección 8): ambos usan `sort_keys=True` y `separators=(",", ":")`, pero:
- `classifier_config_hash`: `ensure_ascii=False`.
- `self_hash` del CTR: también `ensure_ascii=False` (después del `model_dump_json`).
- `self_hash` excluye campos del evento (`self_hash`, `chain_hash`, `prev_chain_hash`, `persisted_at`, `id`); `classifier_config_hash` canoniza todo el dict `{tree_version, profile}` sin exclusiones.

Las dos fórmulas viajan juntas en cada evento del CTR — son independientes pero igualmente sensibles. Ver CLAUDE.md "Serialización canónica NO es uniforme entre hashes".

**El árbol de decisión — completo**:

```python
# apps/classifier-service/src/classifier_service/services/tree.py:56
def classify(ct, ccd, cii, reference_profile=None) -> ClassificationResult:
    profile = reference_profile or DEFAULT_REFERENCE_PROFILE
    th = profile["thresholds"]
    ct_summary  = float(ct.get("ct_summary", 0.5))
    ccd_mean    = float(ccd.get("ccd_mean", 0.5))
    ccd_orphan  = float(ccd.get("ccd_orphan_ratio", 0.0))
    cii_stab    = float(cii.get("cii_stability", 0.5))
    cii_evo     = float(cii.get("cii_evolution", 0.5))

    # ── Rama 1: DELEGACIÓN PASIVA ─────────────────────────────────────
    # (a) orphan extremo (>=0.8) — copy-paste del tutor, cualquier ritmo
    # (b) orphan alto + coherencia temporal baja — errático sin reflexión
    EXTREME_ORPHAN_THRESHOLD = 0.8
    is_extreme_delegation = ccd_orphan >= EXTREME_ORPHAN_THRESHOLD
    is_classic_delegation = (ccd_orphan >= th["ccd_orphan_high"]
                             and ct_summary < th["ct_low"])
    if is_extreme_delegation or is_classic_delegation:
        return ClassificationResult(
            appropriation="delegacion_pasiva",
            reason=f"Delegación {...}: ccd_orphan_ratio={ccd_orphan:.2f}, ct_summary={ct_summary:.2f}. Evidencia de trabajo sin verbalización de comprensión.",
            ...
        )

    # ── Rama 2: APROPIACIÓN REFLEXIVA ─────────────────────────────────
    # Condiciones FUERTES en las 3 dimensiones simultáneamente
    if (ct_summary >= th["ct_high"]
        and ccd_mean >= 1 - th["ccd_mean_low"]   # alto = bueno
        and ccd_orphan < th["ccd_orphan_high"]
        and cii_stab > th["cii_stability_low"]):
        return ClassificationResult(
            appropriation="apropiacion_reflexiva",
            reason=f"Coherencia temporal alta (ct={ct_summary:.2f}), alineación código-discurso, estabilidad de enfoque: trabajo sostenido con profundización.",
            ...
        )

    # ── Rama 3 (fallback): APROPIACIÓN SUPERFICIAL ────────────────────
    return ClassificationResult(
        appropriation="apropiacion_superficial",
        reason=f"Coherencias intermedias (ct={ct_summary:.2f}, ccd_mean={ccd_mean:.2f}, ...): engagement presente pero sin evidencia suficiente de profundización.",
        ...
    )
```

**Umbrales por default** (`DEFAULT_REFERENCE_PROFILE`):

```python
{
    "name": "default",
    "version": "v1.0.0",
    "thresholds": {
        "ct_low": 0.35,              # <0.35 → temporal incoherente
        "ct_high": 0.65,              # >0.65 → temporal sostenida
        "ccd_orphan_high": 0.5,       # >=0.5 → muchos eventos sin reflexión
        "ccd_mean_low": 0.35,         # usado como (1 - x) para "alto"
        "cii_stability_low": 0.2,
        "cii_evolution_low": 0.3,
    },
}
```

Umbrales por cátedra ("cs1_easy", "cs1_hard", etc.) se definen como profiles alternativos con los mismos keys pero valores distintos — cada profile produce un `classifier_config_hash` diferente.

**Las 3 coherencias — definiciones operacionales**:

- **CT (`ct_summary`)** (`apps/classifier-service/src/classifier_service/services/ct.py`):
  - Divide el episodio en **ventanas de trabajo** separadas por pausas `>PAUSE_THRESHOLD = 5min`.
  - Para cada ventana calcula densidad de eventos, ratio prompt/ejecución, pausas reflexivas.
  - `ct_summary` = promedio ponderado normalizado ∈ [0, 1].
  - Con `<MIN_EVENTS_FOR_SCORE = 3` eventos, devuelve 0.5 (neutro, insufficient data).

- **CCD** (`apps/classifier-service/src/classifier_service/services/ccd.py`):
  - `ccd_mean` — promedio de alineación entre acciones (código/prompt) y giros verbales (reflexión explícita).
  - `ccd_orphan_ratio` — fracción de acciones **sin** giro verbal dentro de `CORRELATION_WINDOW = 2min`.
  - Los "giros verbales" son: `anotacion_creada` o `prompt_enviado` con `prompt_kind="reflexion"`/`"epistemologica"`.
  - Sin notas explícitas, todos los `codigo_ejecutado` y `prompt_enviado(solicitud_directa)` caen como "huérfanos" — por eso la UX del web-student empuja al estudiante a usar el `NotesPanel`.

- **CII** (`apps/classifier-service/src/classifier_service/services/cii.py`):
  - `cii_stability` — overlap de tokens entre prompts consecutivos. Alta si el estudiante profundiza en el mismo tema; baja si salta.
  - `cii_evolution` — longitud media de prompts a lo largo del episodio. Tendencia creciente → desarrollo de pensamiento; decreciente → frustración/delegación.
  - Con `<2 prompts`, devuelve 0.5 / 0.5 con flag `insufficient_data=True`.

Todas las métricas preservan sus features intermedios (ventanas, pairs, insufficient_data flags) en la columna `classifications.features` JSONB — permite explainability post-hoc sin recomputar.

## 9. Configuración y gotchas

**Env vars críticas**:

- `CLASSIFIER_DB_URL` — default `postgresql+asyncpg://classifier_user:classifier_pass@127.0.0.1:5432/classifier_db`.
- `CTR_SERVICE_URL` — URL base del ctr-service para el fetch de episodios.

**Puerto de desarrollo**: `8008`.

**Gotchas específicos**:

- **Las 3 coherencias permanecen separadas en sus 5 métricas operacionales**: agrupar `ccd_mean` y `ccd_orphan_ratio` en un solo número, o colapsar CII en "cii_overall", rompe el análisis multidimensional de la tesis. Cualquier PR que mueva en esa dirección debe refutarse citando CLAUDE.md.
- **Hash determinista sensible a `sort_keys`, `separators`, `ensure_ascii`**: los tres parámetros viajan juntos; cambiar cualquiera invalida toda clasificación previa porque el hash cambia y el append-only detecta "config nueva" → inserta reclasificación. El test `test_pipeline_reproducibility.py` es el gate.
- **`appropiacion_superficial` es el fallback**: el árbol primero chequea `delegacion_pasiva` (rama estricta con doble condición), después `apropiacion_reflexiva` (condiciones fuertes en las 3 dims), y si ninguna gatilla cae a `apropiacion_superficial` con una `reason` que describe "intento moderado, señales mixtas". Cambiar el orden cambia resultados.
- **`DEFAULT_REFERENCE_PROFILE` es el único profile en el código hoy**: el A/B de profiles (HU-118) arma el JSON en el request de analytics-service y re-clasifica in-memory contra el gold standard. No hay tabla `profiles` en la DB — los profiles son valores transitorios del experimento.
- **Reclasificación con mismo hash NO es estrictamente idempotente en el wire**: `persist_classification()` siempre ejecuta `UPDATE classifications SET is_current=false WHERE episode_id=X AND is_current=true`; si la clasificación actual ya tiene el mismo hash, ese UPDATE la marca `is_current=false` y después el INSERT viola el `UniqueConstraint(episode_id, classifier_config_hash)` → `IntegrityError`. El endpoint devuelve 500. **Workaround correcto**: el handler debería hacer `SELECT ... WHERE episode_id=X AND classifier_config_hash=Y` primero y devolver existente si hay match. Queda como bug reportado — ver Sección 11.
- **Sin auto-trigger en `episodio_cerrado`**: el docstring del pipeline lo sugiere, pero no hay worker corriendo. La clasificación es un POST manual — el web-student o un operador lo dispara. Para el piloto funciona; para prod con 100+ comisiones activas, es pieza faltante.
- **CII con ≥3 prompts**: es el umbral donde empieza a producir señal útil. Episodios con 1-2 prompts devuelven 0.5/0.5. El árbol los clasifica casi siempre como `apropiacion_superficial` (no cumple condiciones fuertes de ninguna rama).

**Traceback — POST /classify_episode con episodio inexistente en CTR**:

```
INFO: "POST /api/v1/classify_episode/7b3e7c8e-... HTTP/1.1" 404 Not Found
{ "detail": "Episode 7b3e7c8e-... no encontrado en CTR" }
```

**Traceback — POST /classify_episode idempotente (bug reportado)**:

```
INFO: "POST /api/v1/classify_episode/... HTTP/1.1" 500 Internal Server Error
sqlalchemy.exc.IntegrityError: (asyncpg.exceptions.UniqueViolationError)
  duplicate key value violates unique constraint "uq_classifications_episode_config"
  DETAIL: Key (episode_id, classifier_config_hash)=(7b3e7c8e-..., e5f6a7b8...) already exists.
```

## 10. Relación con la tesis doctoral

El classifier-service es la **operacionalización de los tres criterios de coherencia N4** descritos en el Capítulo 5 de la tesis. Cada coherencia responde a una pregunta del marco:

- **CT (temporal)**: ¿el estudiante trabajó con ritmo sostenido o fragmentado? Proxy: densidad de eventos dentro de ventanas separadas por pausas ≥5min.
- **CCD (código-discurso)**: ¿las acciones del estudiante están acompañadas de verbalización reflexiva, o son "huérfanas"? Proxy: ventanas de correlación ±2min entre `codigo_ejecutado`/`prompt_enviado` y `anotacion_creada`/`prompt_enviado(prompt_kind=reflexion)`.
- **CII (inter-iteración)**: ¿el estudiante profundiza en un tema o salta? ¿su pensamiento se elabora o se degrada? Proxy: overlap de tokens entre prompts consecutivos (stability) + longitud media a lo largo del episodio (evolution).

**Discrepancias declaradas con la tesis (operacionalización v1.0.0)**:

- **CCD vs Sección 15.3 de la tesis**: la tesis define CCD como "similitud semántica entre explicaciones en chat y contenido del código (mediante técnicas de embeddings)". El classifier-service v1.0.0 implementa **proximidad temporal** entre acciones y verbalizaciones (ventana ±2min). Es una operacionalización de primera generación más liviana y reproducible bit-a-bit. La migración a embeddings es agenda confirmatoria.

- **CII vs Sección 15.4 de la tesis**: la tesis define CII como "estabilidad de patrones a través de problemas análogos" — observación **longitudinal inter-episodio**. El classifier-service v1.0.0 implementa `cii_stability` y `cii_evolution` como métricas **intra-episodio** (entre prompts consecutivos del mismo episodio, vía overlap léxico de tokens). El nombre técnico interno se podría refinar a `iis_*` (Iteration-Internal-Stability) para evitar ambigüedad. La CII longitudinal real es agenda confirmatoria.

El `classifier_config_hash` es exactamente el mecanismo que permite, cuando las versiones semántica/longitudinal estén implementadas, distinguir clasificaciones v1.0.0 de las nuevas sin romper las viejas.

El árbol N4 del Capítulo 6 de la tesis define las 3 categorías (`delegacion_pasiva`, `apropiacion_superficial`, `apropiacion_reflexiva`). El `tree.py` las implementa con lógica explicita y umbrales parametrizados — el experimento de A/B de profiles (HU-118) busca calibrar esos umbrales contra un gold standard etiquetado por docentes (κ ≥ 0.70, meta de la tesis — ADR-046).

**¿Por qué 3 categorías y no un espectro?** La tesis argumenta (Capítulo 4) que las categorías discretas son más comunicables al docente que valores continuos — "este estudiante está en delegación pasiva" es accionable; "este estudiante tiene un score de apropiación de 0.42" requiere interpretación. Las 3 coherencias agregadas (operacionalizadas en 5 métricas crudas) quedan disponibles en `ct_summary`, `ccd_mean`, etc., para quien quiera el detalle; la categoría es la síntesis interpretable.

**Por qué append-only con `is_current`** (ADR-010): si se recalibra el árbol (ej. se publica `v1.1.0` con umbrales distintos, o se corre un profile nuevo contra episodios viejos), la clasificación anterior **no se pierde**. Un auditor puede preguntar "con los umbrales de v1.0.0, ¿este estudiante era delegación pasiva o superficial?" y la respuesta está persistida. Esto es necesario para la validez metodológica: si la tesis reporta resultados con los umbrales de `v1.0.0`, esos resultados deben seguir siendo reproducibles aunque después se actualicen los umbrales.

**Por qué el árbol y no un clasificador entrenado**: el capítulo de validación de la tesis incluye **interpretabilidad** como criterio. Un modelo entrenado (regresión logística, random forest, LLM-as-classifier) puede tener mejor κ pero sacrifica la lectura pedagógica — no se puede responder "¿por qué este estudiante fue clasificado así?" con una feature importance. El árbol `if/elif/else` produce un `appropriation_reason` textual con los valores específicos que gatillaron la rama, auditable a simple vista por el docente.

## 11. Estado de madurez

**Tests** (6 archivos unit):
- `tests/unit/test_tree.py` — las 3 ramas del árbol con casos borderline.
- `tests/unit/test_ct.py` — ventanas, pausas, score temporal.
- `tests/unit/test_ccd.py` — correlation window, orphan ratio, edge cases (0 eventos, todos huérfanos).
- `tests/unit/test_cii.py` — stability con <2 prompts, evolution con prompts de longitud creciente/decreciente.
- `tests/unit/test_aggregation.py` — distribution, timeseries diaria.
- `tests/unit/test_pipeline_reproducibility.py` — **clave**: verifica que el hash sea estable ante re-ejecución y que cambios en `reference_profile` produzcan hash distinto.

**Known gaps**:
- Sin test de integración end-to-end (`POST /classify_episode/{id}` contra ctr-service real + DB).
- Worker automático para clasificar al cerrar episodio **no implementado**; trigger es manual.
- CII_stability con overlap léxico es operacionalización v1 — embeddings quedan como futuro ([ADR-017](../adr/017-ccd-embeddings-deferred.md), G14 diferido).
- **Bug de idempotencia**: reclasificación con mismo `classifier_config_hash` falla con `IntegrityError` en lugar de devolver existente. Fix propuesto: hacer `SELECT FIRST` antes del `UPDATE + INSERT`. Deuda QA 2026-05-07 explícita.
- **106 classifications con hash legacy `9dd96894...`** (pre-bump labeler v1.2.0): re-classify masivo nunca corrió. Los hashes nuevos son deterministas; deuda operacional declarada en CLAUDE.md.

**Fase de consolidación**:
- F3 — implementación del árbol + 3 coherencias (`docs/F3-STATE.md`).
- F4 — hardening, idempotencia append-only validada.
- F7 — A/B de profiles (HU-118) operable vía analytics-service.
- F9 — migraciones RLS (`20260902_0002_enable_rls_on_classifier_tables.py`).
- 2026-04-26 ([ADR-020](../adr/020-event-labeler-n-level.md)) — `event_labeler.py` con N1-N4 derivado en lectura.
- 2026-04-29 ([ADR-023](../adr/023-anotacion-temporal-override.md)) — `LABELER_VERSION = "1.1.0"` con override temporal de `anotacion_creada`.
- 2026-05-04 (epic `ai-native-completion-and-byok`) — `LABELER_VERSION = "1.2.0"` ([ADR-034](../adr/034-test-cases-tp.md)) con regla N3/N4 sobre `tests_ejecutados`. **`_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}`** (RN-133) — bug genuino cerrado.
- 2026-05-04 (epic `real-health-checks`) — `/health/ready` real con `check_postgres + check_http(ctr)`.

## 12. Runbook: estudio de codificación ciega

Procedimiento del investigador para el estudio de [ADR-063](../adr/063-estudio-codificacion-ciega.md). Todo va por la API: los IDs de la muestra nunca entran al repo, ni a este documento, ni a un issue. Los archivos de trabajo (`estudio/`) quedan fuera del repo.

**Orden**: estudio y membresías → codebook en borrador → anclas → muestra → enunciados y su revisión → congelar y fijar la vigente → (codificación) → progreso → exportación. Los enunciados se cargan **después** de la muestra y de las anclas, porque la cobertura se calcula contra los `problema_id`/`ejercicio_id` que esas cargas fijan.

### 12.0 Variables

Local (dev): se le pega directo al classifier (`:8008`) con los headers que en producción inyecta el gateway. Los valores son de ejemplo; el investigador local no necesita ningún rol especial.

Los comandos se corren desde el directorio de trabajo que contiene `estudio/` (fuera del repo); `REPO` apunta a la copia local del repo.

```bash
export REPO=$HOME/Proyectos/AI-Native/codigo
export BASE=http://127.0.0.1:8008/api/v1/interrater/estudios
export TENANT=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
ADMIN=(-H "X-Tenant-Id: $TENANT" -H "X-User-Id: 11111111-1111-1111-1111-111111111111" -H "X-User-Email: admin@utn.test" -H "X-User-Roles: superadmin")
INV=(-H "X-Tenant-Id: $TENANT" -H "X-User-Id: 22222222-2222-2222-2222-222222222222" -H "X-User-Email: investigador@utn.test" -H "X-User-Roles: estudiante,docente")
```

Producción: `BASE=https://<gateway>/api/v1/interrater/estudios`, y en lugar de los headers `X-*`, `-H "Authorization: Bearer $TOKEN"` con el token de Clerk de la cuenta correspondiente (el gateway inyecta la identidad). El alta del estudio exige una cuenta en `CLERK_ADMIN_EMAILS`.

### 12.1 Estudio y membresías

```bash
curl -sS -X POST "$BASE" "${ADMIN[@]}" -H 'Content-Type: application/json' \
  -d '{"clave": "cibse-2027", "titulo": "CIbSE 2027: referencia humana"}'
curl -sS -X POST "$BASE/cibse-2027/membresias" "${ADMIN[@]}" -H 'Content-Type: application/json' \
  -d '{"email": "investigador@utn.test", "rol": "investigador"}'
# Desde acá, el investigador. Codificadores (solo después de responder la pregunta 1 del proposal si son externos):
curl -sS -X POST "$BASE/cibse-2027/membresias" "${INV[@]}" -H 'Content-Type: application/json' \
  -d '{"email": "codificador1@utn.test", "rol": "codificador"}'
curl -sS -X POST "$BASE/cibse-2027/membresias" "${INV[@]}" -H 'Content-Type: application/json' \
  -d '{"email": "codificador2@utn.test", "rol": "codificador"}'
curl -sS "$BASE/cibse-2027/membresias" "${INV[@]}" | jq '.[] | {alias, rol, estado, atada}'
```

Revocar (por id, el email no viaja en la URL): `curl -sS -X DELETE "$BASE/cibse-2027/membresias/<membresia_id>" "${INV[@]}"`. Una re-asignación del mismo email crea una membresía nueva, sin etiquetas.

### 12.2 Codebook: validar el esquema, cargar el borrador

El esquema sigue el meta-esquema cerrado de `services/estudio_esquema.py::validar_esquema`. Su forma exacta está en «Forma exacta del meta-esquema», más abajo: **ese es el único lugar canónico** (ADR-063 D9 apunta acá). Validarlo antes de subir:

```bash
uv run --project "$REPO" python -c "import json; from classifier_service.services.estudio_esquema import validar_esquema; print(validar_esquema(json.load(open('estudio/esquema_v0.json'))) or 'esquema valido')"
curl -sS -X POST "$BASE/cibse-2027/codebook" "${INV[@]}" -H 'Content-Type: application/json' -d '{"etiqueta": "v0"}'
jq -n --rawfile md estudio/codebook_v0.md --slurpfile esq estudio/esquema_v0.json '{contenido_md: $md, esquema: $esq[0]}' \
  | curl -sS -X PUT "$BASE/cibse-2027/codebook/v0" "${INV[@]}" -H 'Content-Type: application/json' --data-binary @-
```

Si el esquema no valida, el `PUT` responde 400 con `detail.errores` y no cambia nada. Una versión nueva que parte de otra: `-d '{"etiqueta": "v1", "clonar_de": "v0"}'`.

Si el borrador ya tiene anclas, el `PUT` guarda el esquema igual y devuelve `anclas_invalidas`: cada ancla cuya respuesta esperada dejó de valer contra el esquema nuevo (`item_id`, `uso`, `orden`, `motivos`). No rechaza, porque al renombrar una dimensión el ancla tampoco vale contra el esquema viejo y no habría forma de corregirla; congelar sí rechaza (12.6).

#### Forma exacta del meta-esquema

Objeto cerrado: una clave desconocida, en cualquier nivel, es un error (400). Este ejemplo es completo y válido (`validar_esquema` devuelve `[]`):

```json
{
  "dimensiones": [
    {"clave": "d1", "nombre": "Verbaliza", "valores": ["presente", "ausente"], "cita_requerida_si": ["presente"]},
    {"clave": "d2", "nombre": "Verifica", "valores": ["presente", "ausente"], "cita_requerida_si": ["presente"]},
    {"clave": "d3", "nombre": "Justifica", "valores": ["presente", "ausente"], "cita_requerida_si": ["presente"]},
    {"clave": "d4", "nombre": "Autonomía", "valores": ["interlocutor", "oraculo", "transferencia"], "cita_requerida_si": ["transferencia"]}
  ],
  "regimenes": [
    {"clave": "reflexiva", "nombre": "Reflexiva"},
    {"clave": "superficial", "nombre": "Superficial"},
    {"clave": "pasiva", "nombre": "Pasiva"},
    {"clave": "evidencia_insuficiente", "nombre": "Evidencia insuficiente"}
  ],
  "regimen_evidencia_insuficiente": "evidencia_insuficiente",
  "regimenes_exentos": ["evidencia_insuficiente"],
  "dimensiones_opcionales_si_regimen": ["evidencia_insuficiente"],
  "notas_obligatorias_si_regimen": ["evidencia_insuficiente"],
  "marca_frontera": true,
  "notas_obligatorias_si_frontera": true,
  "confianza": {"valores": ["alta", "media", "baja"], "obligatoria": false},
  "reglas_regimen": [
    {"regimen": "reflexiva", "condicion": [
      [{"dimension": "d1", "en": ["presente"]}],
      [{"dimension": "d2", "en": ["presente"]}, {"dimension": "d3", "en": ["presente"]}],
      [{"dimension": "d4", "en": ["interlocutor"]}]
    ]},
    {"regimen": "pasiva", "condicion": [
      [{"dimension": "d4", "en": ["transferencia"], "con_cita": true}],
      [{"dimension": "d1", "en": ["ausente"]}],
      [{"dimension": "d2", "en": ["ausente"]}],
      [{"dimension": "d3", "en": ["ausente"]}]
    ]}
  ],
  "regimen_por_defecto": "superficial"
}
```

| Clave | Obligatoria | Forma |
|---|---|---|
| `dimensiones` | sí | lista de 1 a 8 objetos con exactamente `clave` (`^[a-z][a-z0-9_]{0,39}$`, única), `nombre` (texto no vacío), `valores` (2 a 6 textos distintos) y `cita_requerida_si` (subconjunto de `valores`; `[]` si ninguno) |
| `regimenes` | sí | lista de 2 a 6 objetos con exactamente `clave` (misma regla, única) y `nombre` (texto no vacío) |
| `regimen_evidencia_insuficiente` | sí | una clave de `regimenes` |
| `regimenes_exentos` | no | claves de `regimenes`; default `[regimen_evidencia_insuficiente]`, y tiene que incluirlo. El codificador los elige explícitamente; la regla no los deriva |
| `dimensiones_opcionales_si_regimen`, `notas_obligatorias_si_regimen` | no | listas de claves de `regimenes`; default `[]` |
| `marca_frontera` | no | booleano; default `false` |
| `notas_obligatorias_si_frontera` | no | booleano; default `false`; `true` exige `marca_frontera: true` |
| `confianza` | no | `null` (default) u objeto con exactamente `valores` (1 o más textos distintos) y `obligatoria` (booleano) |
| `reglas_regimen` | no | lista ORDENADA, default `[]` (sin reglas, el codificador elige el régimen). Cada regla tiene exactamente `regimen` (declarado y no exento) y `condicion`: lista no vacía de cláusulas (conjunción); cada cláusula es una lista no vacía de átomos (disyunción); cada átomo tiene `dimension` (declarada), `en` (lista no vacía de valores distintos de esa dimensión) y, opcional, `con_cita` (booleano) |
| `regimen_por_defecto` | si hay reglas | clave de `regimenes`, no exenta; obligatoria con reglas y **prohibida** sin reglas |

Toda clave de régimen o de dimensión tiene que ser texto: una lista u objeto en su lugar es error de validación (400), no un 500.

Semántica:
- Un átomo se cumple si el valor de la dimensión está en `en`; con `con_cita: true` además exige una cita no vacía (sin contar espacios).
- Régimen de la regla: `null` si alguna dimensión referenciada por CUALQUIER regla no tiene valor; si no, el de la primera regla cuya condición se cumple, o `regimen_por_defecto`.
- El régimen guardado es siempre el de la regla, salvo un exento elegido explícitamente; `regimen_regla` se calcula igual. Un régimen no exento distinto del de la regla, o con dimensiones incompletas, es 422; el desacuerdo va en `regimen_propuesto`, con nota obligatoria.
- Cierre: exige régimen; las dimensiones, salvo si el régimen está en `dimensiones_opcionales_si_regimen`; cita cuando el valor está en `cita_requerida_si`; notas si el régimen está en `notas_obligatorias_si_regimen`, si hay frontera con `notas_obligatorias_si_frontera` o si hay `regimen_propuesto`; confianza si es obligatoria.
- La respuesta esperada de un ancla sigue las mismas reglas que una etiqueta, contra el esquema vigente del borrador, y para congelar tiene que estar completa con la misma regla que el cierre de una codificación.

### 12.3 Anclas (en el borrador)

Cada ancla es un JSON `{episode_id, uso: "ejemplo"|"practica", orden, respuesta_esperada, explicacion_md, consensuado_por}`. La respuesta esperada tiene el formato de una etiqueta (`{"respuestas": {"<dim>": {"valor", "cita"}}, "regimen", ...}`) y se valida contra el esquema de la versión. En el borrador se admite incompleta: el alta y la edición devuelven `faltantes` (mismos códigos que el cierre) y congelar la rechaza hasta completarla. El episodio tiene que estar terminado y fuera de la muestra.

```bash
curl -sS -X POST "$BASE/cibse-2027/codebook/v0/anclas" "${INV[@]}" -H 'Content-Type: application/json' \
  --data-binary @estudio/ancla_01.json
curl -sS "$BASE/cibse-2027/codebook/v0/anclas" "${INV[@]}" | jq '.[] | {item_id, uso, orden, enunciados_listos}'
```

### 12.4 Muestra fija

El CSV original (`estrato,origen,tp,episode_id`) se sube **crudo**: el servidor calcula el sha256 de los bytes, guarda solo `episode_id` y descarta el resto. Usar `--data-binary` y no `-d` (`-d` quita los saltos de línea y el sha no coincide).

```bash
SHA=$(sha256sum estudio/muestra.csv | cut -c1-64)
curl -sS -X POST "$BASE/cibse-2027/muestra?sha256_esperado=$SHA" "${INV[@]}" -H 'Content-Type: text/csv' \
  --data-binary @estudio/muestra.csv
```

Respuesta: `{"items": N, "sha256": "..."}`. Errores:
- 422 `sha256_distinto`;
- 422 `csv_invalido`, con la fila;
- 422 `episodios_invalidos`, con la fila y el motivo: inexistente, `open`, `paused` sin abandono o integridad comprometida;
- 409 `episodio_es_ancla`;
- 409 `muestra_con_etiquetas`: con etiquetas ya no se reemplaza.

La carga es todo o nada.

### 12.5 Enunciados: carga y revisión obligatoria

CSV `tipo,tp_id,ejercicio_id,enunciado`. Una fila `tp` lleva `tp_id`; una fila `ejercicio` lleva `ejercicio_id`. El texto va entre comillas si tiene comas, comillas o saltos de línea. Las filas que no corresponden a ningún ítem ni ancla se ignoran y se informan.

```bash
curl -sS -X POST "$BASE/cibse-2027/enunciados" "${INV[@]}" -H 'Content-Type: text/csv' \
  --data-binary @estudio/enunciados.csv | jq '.cobertura, .ignoradas'
curl -sS "$BASE/cibse-2027/enunciados" "${INV[@]}" | jq '.enunciados[] | {id, tipo, alertas, revisado}'
```

Revisar CADA enunciado. Mirar las `alertas` (fecha, email, docente, comision, horario, rubrica, tests, pista, solucion), pero leer igual el texto completo: las alertas no reemplazan la lectura. Aprobar tal cual o guardar una versión editada (el original y su sha256 se conservan):

```bash
ID=$(curl -sS "$BASE/cibse-2027/enunciados" "${INV[@]}" | jq -r '[.enunciados[] | select(.revisado | not)][0].id')
curl -sS -X POST "$BASE/cibse-2027/enunciados/$ID/revision" "${INV[@]}" -H 'Content-Type: application/json' \
  -d '{"contenido_mostrado_md": null}'
```

Mientras falte o no esté revisado algún enunciado de la muestra, nadie puede guardar etiquetas (409 `enunciados_pendientes`). Un enunciado revisado no cambia más (409 `enunciado_revisado` si se sube otro texto).

### 12.6 Congelar y fijar la vigente

```bash
curl -sS -X POST "$BASE/cibse-2027/codebook/v0/congelar" "${INV[@]}" | jq '{etiqueta, estado, contenido_sha256}'
curl -sS -X PUT "$BASE/cibse-2027/codebook-vigente" "${INV[@]}" -H 'Content-Type: application/json' -d '{"etiqueta": "v0"}'
curl -sS "$BASE/cibse-2027/codebook/versiones" "${INV[@]}"
```

Congelar revalida cada ancla contra el esquema de la versión: si alguna no vale (dimensión o valor que el esquema ya no tiene, o un régimen esperado que la regla no da; los exentos explícitos valen) o está incompleta (lo que exigiría el cierre de una codificación: régimen, dimensiones, citas, notas, confianza; motivos `incompleta: <código>`), responde 422 `anclas_invalidas` con `detail.anclas` (`item_id`, `uso`, `orden`, `motivos`) y `detail.errores`, y la versión sigue en borrador. Se corrige editando la respuesta esperada del ancla (o borrándola) y se vuelve a congelar.

Anotar el `contenido_sha256`: es el que se cita en el método. Con etiquetas del estudio, la vigente ya no cambia (409). El entrenamiento funciona con la vigente en borrador; la codificación exige que esté congelada.

### 12.7 Seguimiento y exportación

```bash
curl -sS "$BASE/cibse-2027/progreso" "${INV[@]}"
curl -sS "$BASE/cibse-2027/exportacion?contenido=etiquetas&formato=csv" "${INV[@]}" -o estudio/etiquetas.csv
curl -sS "$BASE/cibse-2027/exportacion?contenido=entrenamiento&formato=json" "${INV[@]}" -o estudio/entrenamiento.json
curl -sS "$BASE/cibse-2027/exportacion?contenido=historial&formato=csv" "${INV[@]}" -o estudio/historial.csv
```

La exportación trae `episode_id`, semilla y posición; con la semilla, el orden de cada codificador se recomputa con `printf '%s' "<semilla>:<item_id>" | sha256sum` ordenando el hex en forma ascendente (ADR-063 D7).

### 12.8 Notas para el investigador y para el método

- **`tests_ejecutados` trae solo conteos**: la mayoría de las corridas de pruebas del CTR registran totales, pasados y fallidos, sin la salida. Aunque el codebook §2 hable de "lo que imprimió y el error", eso solo está en las ejecuciones (`codigo_ejecutado`: `stdout`/`stderr`), no en las corridas de pruebas.
- **Diferencia de evidencia humano/juez**: el codificador ve más que el juez (salidas, estados intermedios, copias, pegados, lecturas, fin cerrado o abandonado). Declararlo en el método (ADR-063 D4).
- **Enunciados cargados a mano**: el sistema no verifica que el texto sea el de academic-service, y `Ejercicio.enunciado_md` se edita en el lugar. Declarar en el método que se cargaron desde una exportación del investigador, con `archivo_sha256` registrado.
- **Evidencia fija**: lo que se ve de cada ítem es lo que había al cargarlo. Si el CTR cambia la cadena hasta el tope, la traza responde 409 `evidencia_alterada`.
