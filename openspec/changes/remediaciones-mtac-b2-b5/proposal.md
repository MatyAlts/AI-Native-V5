## Why

Auditoría del código contra el documento «Pendientes de la propuesta MTAC» (tesis doctoral UTN, A. A. Cortez). Tres pendientes técnicos dependen del repo, y los tres fallan por el mismo mecanismo: **una ausencia de información se persiste como si fuera información**.

**B2a — El juez no tiene tercer valor.** `_Dim.presente` es `bool` (`regimen_llm.py:67`). Una dimensión que el juez no pudo evaluar se colapsa a `False`, y `regimen_segun_regla` (`:177-178`) la lee como «ausente». El hecho de que faltaba evidencia se pierde antes de llegar a la base. El pendiente pide textual «valores presente/ausente/no evaluable, evaluación trivaluada, derivación por evidencia insuficiente».

**B2b — El sumidero de `sin_clasificar`.** `_EJE_TO_APPROPRIATION["sin_clasificar"] = "apropiacion_superficial"` (`pipeline.py:86`, único uso en `:117`). Los episodios que el árbol no puede clasificar **no quedan sin clasificar: quedan etiquetados como apropiación superficial**. Son 23 en el corpus, indistinguibles en la base de una apropiación superficial genuina. La degradación además **tiene dirección**: cae en la categoría del medio, que es donde se concentran las 27 discrepancias entre codificadores humanos (0 discrepancias en delegación pasiva).

**B3+B5 — La marca de revisión no la lee nadie.** `features["needs_review"]` se escribe (`classify_ep.py:134-135`) y está cubierta por 6 aserciones de test, pero `rg 'needs_review'` sobre `apps/`, `packages/` y `scripts/` devuelve **solo el sitio de escritura, su config y los tests**: cero endpoints, cero frontends, cero consultas. El sistema marca episodios para revisión humana y esa marca no llega a ningún humano — 40 episodios retenidos al 18/09 (23 `error_parseo`, 16 `inconsistente`, 1 `baja_confianza`).

## What Changes

- **Dimensión trivaluada en el juez**: `presente` pasa de booleano a `presente | ausente | no_evaluable`, en el modelo Pydantic, en el JSON Schema del contrato y en el prompt del juez (el del classifier SÍ es tocable; el del tutor NO).
- **Regla determinista trivaluada y versionada**: `regimen_segun_regla` deja de emitir veredicto cuando el valor desconocido cambia el resultado, y deriva por evidencia insuficiente a revisión humana en vez de colapsar a SUPERFICIAL.
- **Retrocompatibilidad de lectura**: las clasificaciones ya persistidas con `presente: true/false` se siguen parseando. Es requisito, no deseable.
- **El tercer valor llega a la UI**: `EpisodeNLevelView.tsx:418-431` hoy rotula con un ternario booleano `presente|ausente`. Sin tocarlo, «no evaluable» se muestra como «ausente» y el colapso se reintroduce en la pantalla.
- **`sin_clasificar` deja de rollear a superficial** y se persiste como su propio valor de `appropriation`, con bump de `tree_version` (que **sí** mueve `classifier_config_hash`, a propósito).
- **Cola de revisión humana con historial**: tabla append-only nueva en `classifier_db`, endpoint de lectura de la cola y endpoint de registro de anulación humana, más la pantalla del docente que la consume.

## Capabilities

### New Capabilities

- `regimen-trivaluado`: el juez del eje superficial↔reflexiva distingue «no evaluable» de «ausente», la regla determinista es trivaluada y versionada, y un episodio sin evidencia suficiente se deriva a revisión en vez de recibir una etiqueta inferida. Incluye la retrocompatibilidad de los veredictos ya persistidos y la presentación del tercer valor al docente.
- `episodio-sin-clasificar`: un episodio que el árbol no puede clasificar se persiste como no clasificado y no como apropiación superficial, y los consumidores aguas abajo (κ, ordinales, exports, frontends) lo tratan explícitamente en vez de contarlo como una categoría del continuo.
- `revision-humana-clasificacion`: los episodios marcados para revisión son alcanzables por un docente, que puede anular la etiqueta del sistema dejando registro auditable con historial, para todas las rutas que producen etiqueta (juez, árbol, delegación pasiva).

### Modified Capabilities

Ninguna de las 26 de `openspec/specs/` cubre el clasificador N4. Las más cercanas (`pilot-hardening`, `metrics-instrumentation-otlp`) no declaran requisitos sobre la etiqueta ni sobre la revisión humana.

## Impact

| Área | Impacto | Detalle |
|---|---|---|
| `classifier-service/services/regimen_llm.py` | Modificado | `_Dim`, `RESPONSE_JSON_SCHEMA`, `regimen_segun_regla`, `_hay_evidencia_citable`, `SYSTEM_PROMPT`, `PROMPT_VERSION` |
| `classifier-service/services/pipeline.py` | Modificado | `_EJE_TO_APPROPRIATION["sin_clasificar"]` + `tree_version` en `compute_classifier_config_hash` (`:41`) |
| `classifier-service/routes/classify_ep.py` | Modificado | nuevo estado terminal en el fallback a `_marcar_para_revision`; endpoints nuevos bajo `/api/v1/classifications` |
| `classifier-service/models/__init__.py` + `alembic/` | Nuevo | tabla de revisiones append-only con `tenant_id` y policy RLS (ADR-001) |
| `classifier-service/routes/health.py:59` | Modificado | `_TREE_VERSION` (hoy `v4.0.0`), y el test que lo afirma (`tests/test_health.py:104`) |
| `web-teacher` | Modificado | tercer estado en `EpisodeNLevelView.tsx:418-431`; tipo en `lib/api.ts:1324`; pantalla nueva de cola de revisión |
| `api-gateway/routes/proxy.py` | **Sin cambios** | `/api/v1/classifications` ya está en el `ROUTE_MAP` (`:61`) y el proxy resuelve por prefijo — montar los endpoints nuevos bajo ese prefijo los deja alcanzables sin tocar el gateway |
| `packages/platform-ops` (κ, ordinales, export) | Modificado | tratamiento explícito del valor nuevo de `appropriation`; el mapa ordinal de CII longitudinal no tiene posición para él |
| CTR / hashing de eventos | **Sin cambios** | append-only intacto |
| Prompts del tutor | **Sin cambios** | coautoría académica, intocables byte a byte |

## Lo que esta change NO hace

- **No reclasifica los históricos.** Los 23 episodios de `sin_clasificar` ya persistidos y las 106 clasificaciones con hash legacy siguen como están. Es trabajo operativo contra la base del piloto, con su propio gate.
- **No toca el segundo sumidero.** Medido y registrado acá como contexto de la decisión, no como alcance: de 105 episodios donde los dos codificadores humanos coincidieron en superficial-o-reflexiva, el árbol mandó **21 (20%)** al eje `autonomo`; y sobre 182 episodios doblemente codificados, `autonomo` es la categoría con **más discrepancia humana (38%**, contra 0% de delegación pasiva).
- **No toca F15** (corrección asistida por IA, otro negocio) ni los prompts del tutor.
- ~~**No trivalúa `autonomia.oraculo`** (fundamentado en el design: los episodios sin diálogo no llegan al juez).~~

  > **Corrección (auditoría, 2026-09-25): este Non-Goal es FALSO y quedó implementado
  > al revés.** El razonamiento que cita («los episodios sin diálogo no llegan al
  > juez») era la justificación original de D4 en `design.md`, y esa D4 se corrigió
  > durante la implementación: la Tabla B.2 de la tesis (`tabla-3.11-de-la-tesis.md`)
  > define explícitamente un valor `no evaluable` para Autonomía («no hay propuestas
  > del asistente sobre las que observar la conducta»), que es distinto de «no hay
  > diálogo del alumno» — el gate de subgrupos prueba lo segundo, no lo primero.
  > **Esta change SÍ trivalúa `autonomia`** (ya no se llama `oraculo`, ver D4
  > corregida en `design.md`), como las otras tres dimensiones. Este Non-Goal no se
  > borra para dejar rastro de que la premisa original era la contraria a lo que el
  > código terminó haciendo — no la vuelvas a citar como alcance vigente.

## Decisiones que requieren aprobación humana antes de implementar

1. **Bumpear `tree_version`** mueve `classifier_config_hash` y deja a TODAS las clasificaciones del piloto con hash legacy, sumándose al backlog ya abierto de 106. Es gobernanza ALTA: toca datos que la tesis cita.
2. **Relabelar 23 episodios** que la tesis cita como apropiación superficial. El cambio de código es una línea; el costo es académico.
3. **Si la anulación humana reemplaza la etiqueta oficial** o solo queda registrada al lado. Decide qué etiqueta lee el corpus de la tesis.

## Knowledge Base Impact

- `CLAUDE.md` (raíz del repo) — **REWRITE** de la sección «Constantes que NO deben inventarse»: `_TREE_VERSION` y el conteo de valores de `appropriation`. **APPEND** en gotchas: por qué la regla del juez es trivaluada y qué versiona.
- `docs/servicios/classifier-service.md` — **REWRITE** del contrato de salida del juez y de la tabla de valores de `appropriation`.
- `docs/adr/` — **APPEND**: ADR nuevo por la regla trivaluada versionada y por el bump de `tree_version` (el 057 describe el contrato v4.0.0 que esta change modifica).
- `docs/SESSION-LOG.md` — **APPEND** datado, con lo que costó.
- `obsidian.md` (nota viva) — **REWRITE** de frontmatter (`estado`, `ultimo`), `Estado actual` y `Próximos pasos`; **APPEND** en `Gotchas y aprendizajes`.

## Open Questions

**La Tabla 3.11 no la tenemos a la vista.** El pendiente B2 pide «pruebas unitarias sobre los seis casos de la tabla», pero esa tabla vive en el documento de la tesis y no está en el repo. **No se inventan los seis casos.** Es entrada bloqueante para la fase de specs: o se aporta la tabla, o los seis casos se derivan de la regla trivaluada y se validan contra la tesis después — y esa derivación queda declarada como supuesto, no como cumplimiento del pendiente.

**El conteo de 23 episodios `sin_clasificar` y los 40 retenidos al 18/09** vienen de la auditoría contra las bases de producción, no de una medición hecha en esta change.
