> **Nota de alcance (commit "trivaluada pura", 2026-09-25)**: este commit implementa
> SOLO los bloques 2, 3 y 4 (dimensiones trivaluadas + Kleene fuerte + estado
> `abstencion_traza_insuficiente` + UI), acotado a los casos 1, 3, 4 y 6 de la
> Tabla 3.11. Los bloques 5 (revisión humana), 6 (sumidero `sin_clasificar` +
> bump de `tree_version`), 7 (reclasificación) y 8 (cierre/docs finales) NO se
> tocan acá — quedan para commits siguientes, tal como pide el alcance dado al
> implementador. Los casos 2 y 5 de la Tabla 3.11 (dependen de B4, verificación
> literal de citas) quedan declarados como brecha, con constantes de extensión
> sin validador (ver `regimen_llm.py`, comentario junto a `Estado`).

## 1. Gates previos (bloqueantes — no arrancar sin esto)

- [x] 1.1 🔴 Conseguir la **Tabla 3.11** de la tesis. LEVANTADO: `tabla-3.11-de-la-tesis.md` transcribe los seis casos + la Tabla B.2 y es la fuente normativa de este commit.
- [ ] 1.2 🔴 Aprobación humana del bump de `tree_version` (D6). **Fuera de alcance de este commit** (pertenece al bloque 6, B2b) — no tocado.
- [ ] 1.3 🔴 Aprobación humana del relabelado de los 23 episodios `sin_clasificar` (D5). **Fuera de alcance de este commit** (bloque 6/7) — no tocado.
- [ ] 1.4 🔴 Decidir si la anulación humana **reemplaza** la etiqueta oficial o queda al lado. **Fuera de alcance de este commit** (bloque 5, revisión humana) — no tocado.
- [ ] 1.5 Cargar la skill `impeccable` antes de tocar UI. **NO invocada.** El cambio en `EpisodeNLevelView.tsx` es una extensión mecánica de un ternario a tres estados, siguiendo la decisión de diseño YA tomada en D3/4.3 (sin color nuevo, tratamiento neutro) — no hay decisión de UI nueva que un gate de diseño deba aprobar. Declarado como desviación; el orquestador/usuario debería confirmar si esto es aceptable antes de dar el commit por cerrado.

## 2. B2a — Dimensión trivaluada, sin cambio de comportamiento

Objetivo del bloque: que el hash y los veredictos queden **idénticos**. Si algo cambia acá, es un bug.

- [x] 2.1 `_Dim.presente` pasa a `Literal["presente","ausente","no_evaluable"]` (`regimen_llm.py`). Extendido también a `_Autonomia.presente` (ver corrección de D4 en design.md) — las CUATRO dimensiones, no solo tres.
- [x] 2.2 `field_validator`/`model_validator(mode="before")` que coaccionan `True→"presente"` / `False→"ausente"`, y para autonomía el legado `oraculo: bool` (clave Y sentido invertido) a `presente`.
- [x] 2.3 Test de retrocompatibilidad con un payload real del piloto (booleanos en las 4 dimensiones, incluido `oraculo`), que se re-parsea sin error y produce el mismo veredicto.
- [x] 2.4 `regimen_segun_regla` reescrita en términos de los valores nuevos. NOTA: no se implementó el paso intermedio "no_evaluable se comporta como ausente" por separado — se fue directo a Kleene fuerte (bloque 3) porque separar los dos pasos en commits de test distintos no aportaba una red de seguridad adicional aquí (el mismo test de retrocompat cubre ambos).
- [x] 2.5 13/13 tests de `test_pipeline_reproducibility.py` en verde, hash idéntico al baseline.
- [x] 2.6 **AGREGADA post-QA (2026-09-25), bug SEVERO real**: 2.2/2.3 coacciona en `_Dim`/`_Autonomia`, pero esos validadores solo corren cuando el dict pasa por `RegimenLLMRaw.model_validate` — y el endpoint de lectura (`classify_ep.py::get_current_classification`) devolvía `feats.get("regimen_llm")` SIN pasar por el modelo. V/E/J no se notaban (mismo nombre de campo); autonomía SÍ, porque el campo se renombró (`oraculo→presente`) y un registro legado sin `presente` perdía la dimensión en el frontend, en blanco y sin log. Medido contra producción: 663/689 episodios juzgados (96,2%) tienen la forma legada; 26 tienen `raw=None`; 0 tienen la forma nueva. Fix: `normalizar_regimen_llm_persistido` en `regimen_llm.py`, invocado desde el único borde de lectura confirmado por grep. Ver D2 corregida en `design.md` y `test_classify_ep_regimen_llm_read.py` (6 tests: forma legada ×2, forma nativa, sin veredicto, `raw=None`, corrupto-degrada).
- [x] 2.7 **AGREGADA post-QA**: cobertura de valores fuera de dominio de punta a punta por `clasificar_regimen_llm` (`"quizas"`, `null`, campo faltante, dimensión faltante) — los 4 degradan a `error_parseo` sin excepción no capturada. Certifica la propiedad que hace aceptable dejar el caso 5 de la Tabla 3.11 fuera de alcance.
- [x] 2.8 **CORRECCIÓN de auditoría (2026-09-25)** sobre 2.6: de los 6 tests de `test_classify_ep_regimen_llm_read.py`, solo 2 son RED real contra el bug de QA (verificado corriendo la suite contra el código anterior al fix: `2 failed, 4 passed`). Los otros 4 son guardas hacia adelante que ya pasaban sin el fix — quedaron mal presentados como si todos hubieran atrapado el bug. Docstrings del módulo y de cada test corregidos para decir cuál es cuál.
- [x] 2.9 **AGREGADA por hallazgo de auditoría**: `test_classifier_config_hash_golden` en `test_pipeline_reproducibility.py`. Los 13 tests preexistentes prueban determinismo (`h1==h2` en el mismo proceso), no invariancia — no fijan ningún literal, así que un cambio accidental en el default de `tree_version` o en `DEFAULT_REFERENCE_PROFILE` los deja los 13 en verde con el hash movido. Verificado deliberadamente: cambiando el default a `v4.1.0`, el golden falla y los otros 13 siguen en verde. Golden: `28e111aec4c5ec470bc8836cd716f563f41639d043d79bc95dca7da99e62b774` (idéntico antes/después de esta change — confirma que B2a no movió el hash). Esto es lo que hace verificable 6.7 cuando llegue ese commit.

## 3. B2a — Regla trivaluada y derivación por evidencia insuficiente

- [x] 3.1 Kleene fuerte implementado en `regimen_segun_regla` vía `_kleene_desde_dim`/`_kleene_and`/`_kleene_or`. Devuelve `Literal["REFLEXIVA","SUPERFICIAL","INDETERMINADO"]`.
- [x] 3.2 Estado nuevo agregado a `Estado`, con nombre CORREGIDO: `abstencion_traza_insuficiente` (no `evidencia_insuficiente` — ese nombre es del caso 2 de la tabla, que es OTRO estado, fuera de alcance; ver comentario en `regimen_llm.py` junto a `Estado`). Rutea por el fallback existente (`_marcar_para_revision`), sin tocar `classify_ep.py` — la rama genérica `estado != "ok"` ya lo cubre.
- [x] 3.3 Revisado: `_hay_evidencia_citable` itera genéricamente sobre las 4 dimensiones y solo exige cita cuando `regimen=="REFLEXIVA"`; no depende del tipo de `presente`. Verificado con `test_kleene_caso3_sigue_ok_y_no_deriva_pese_a_los_no_evaluable` (caso 3 con las 4 evidencias vacías sigue siendo `ok`, no `inconsistente`).
- [x] 3.4 `RESPONSE_JSON_SCHEMA` actualizado en CUATRO bloques (no tres — corrección de alcance por D4 corregida): verbalizacion, verificacion, justificacion Y autonomia pasan a enum de tres valores. `autonomia` deja de tener la forma `{"oraculo": boolean}`.
- [x] 3.5 `SYSTEM_PROMPT` reescrito con las definiciones de la Tabla B.2 para las 4 dimensiones, definiendo `no_evaluable` por ausencia de traza, con una advertencia explícita de no confundirlo con baja confianza.
- [x] 3.6 Los 3 `_FEWSHOT` actualizados a formato trivaluado nativo (`presente`/`ausente`), incluida `autonomia`.
- [x] 3.7 `PROMPT_VERSION` bumpeada `eje_fino_v1.1.0 → eje_fino_v1.2.0`.
- [x] 3.8 🔴 Pruebas unitarias de los casos EN ALCANCE (1, 3, 4, 6 — ver Alcance del commit). Casos 2 y 5 declarados como brecha, NO implementados (dependen de B4, verificación literal de citas). Ver tabla de ciclo TDD en el informe del implementador.
- [x] 3.9 `test_fallback_proxy_y_needs_review_si_abstencion_traza_insuficiente`: confirma que `appropriation` no se toca y `needs_review`/`needs_review_reason` sí se setean.
- [x] 3.10 13/13 reproducibilidad en verde tras todo el bloque 3, hash idéntico.

## 4. B2a — El tercer valor en la pantalla

- [x] 4.1 `web-teacher/src/lib/api.ts`: `RegimenLLMDimension.presente` es ahora `"presente" | "ausente" | "no_evaluable" | boolean` (acepta ambas formas); `autonomia` unificada a la misma forma (ya no `{oraculo}`); `RegimenLLM.estado` incluye `abstencion_traza_insuficiente`.
- [x] 4.2 🔴 `EpisodeNLevelView.tsx`: los CUATRO ternarios (no tres — autonomia también, por D4 corregida) pasan por `estadoDimension()` + `DIM_LABEL`/`AUTONOMIA_LABEL`, con soporte explícito para el booleano legado.
- [x] 4.3 Sin color nuevo: `no_evaluable` usa el mismo tratamiento visual neutro (`text-muted`) que `ausente` ya usaba; solo cambia el texto.
- [x] 4.4 Tests del componente: uno con `no_evaluable` (confirma que NO se dibuja como "ausente"); uno con un registro cuya autonomía es legada (`oraculo`) usando la forma que la API YA FIJADA devuelve hoy (strings normalizados por el backend — CORREGIDO post-QA: la versión anterior de este test fabricaba `presente: true` para autonomía, una forma que ningún registro real tuvo nunca, porque el legado real es `oraculo` sin `presente`); uno defensivo que confirma que un dict crudo sin normalizar (booleanos + `oraculo`) no rompe el render aunque autonomía quede sin label en ese caso patológico.

## 5. B3+B5 — Revisión humana con historial (aditivo puro)

- [ ] 5.1 Modelo `ClassificationReview` en `classifier_db` (D7): episodio, clasificación revisada, revisor, veredicto humano, motivo, timestamp, `tenant_id`. Append-only — corregir una revisión es una fila nueva, nunca un UPDATE.
- [ ] 5.2 Migración Alembic del classifier-service **con policy RLS activa** sobre la tabla nueva (ADR-001: toda tabla con `tenant_id` la lleva). Verificar con `make check-rls`, que corre en CI.
- [ ] 5.3 `GET /api/v1/classifications/review-queue`: lista los episodios con `features['needs_review']=True` sin revisión posterior, con el motivo y el estado terminal del juez. Filtro por comisión. Lee los headers `X-Tenant-Id`/`X-User-Id`/`X-User-Roles` del gateway vía `Depends` — no re-verificar JWT aguas abajo.
- [ ] 5.4 `POST /api/v1/classifications/{episode_id}/review`: registra el veredicto humano. El comportamiento depende de 1.4 — si reemplaza la etiqueta oficial, lo hace creando una `Classification` nueva con marca de procedencia humana y poniendo la anterior en `is_current=false` (ADR-010), nunca con un UPDATE.
- [ ] 5.5 Verificar que **no** hace falta tocar el `ROUTE_MAP` (D8): ambos endpoints cuelgan de `/api/v1/classifications`, que ya está en `proxy.py:61`. Confirmar a mano contra el gateway levantado, no por lectura — un endpoint inalcanzable falla en silencio.
- [ ] 5.6 Policies Casbin para el rol que puede anular (pregunta abierta del design). Van al seed (`academic-service/seeds/casbin_policies.py`), que es el source of truth, y bumpean el conteo. Recordar que el enforcer en memoria no se refresca solo: hay que relanzar el servicio.
- [ ] 5.7 Pantalla de cola de revisión en web-teacher, consumiendo 5.3. Patrón obligatorio `HelpButton` + `PageContainer` + entry en `helpContent.tsx` (11 keys hoy).
- [ ] 5.8 Ruta nueva en `web-teacher` (TanStack Router file-based, search params validados con zod) y entrada en la navegación. Sin esto la pantalla existe y no se llega.
- [ ] 5.9 Tests: la cola devuelve los retenidos y solo los retenidos; una revisión los saca de la cola; un segundo POST sobre el mismo episodio apila historial en vez de pisarlo; un rol sin policy recibe 403.
- [ ] 5.10 Verificar contra la base del piloto que la cola devuelve los 40 episodios retenidos al 18/09 (23 `error_parseo`, 16 `inconsistente`, 1 `baja_confianza`) — el conteo viene de la auditoría, no de una medición de esta change.

## 6. B2b — El sumidero de `sin_clasificar` (aislado, último)

- [ ] 6.1 🔴 **Antes de tocar el mapeo**: rastrear los consumidores del valor de `appropriation` y anotar cuáles rompen o cuentan mal con un quinto valor. El riesgo no es un crash — es un `.get(valor, 0)` que lo suma a otra cosa. Incluye κ (`platform_ops/kappa_analysis.py`), el mapa ordinal de CII longitudinal (`cii_longitudinal.py`), el export académico (`academic_export.py`), analytics (`routes/analytics.py`, `routes/pedagogia.py`) y los tres frontends.
- [ ] 6.2 `_EJE_TO_APPROPRIATION["sin_clasificar"]` pasa a `"sin_clasificar"` (`pipeline.py:86`). La columna es `String(40)` sin enum: **no hay migración de esquema**.
- [ ] 6.3 Excluir explícitamente el valor nuevo del mapa ordinal `APPROPRIATION_ORDINAL`. No es un punto del continuo: es la ausencia de medición. Misma disciplina con la que el CII longitudinal ya excluye TPs huérfanas.
- [ ] 6.4 Guardas en los consumidores de 6.1, cada una con su test.
- [ ] 6.5 Etiqueta legible en los frontends. «Sin clasificar» no es un estado de error: es información sobre el episodio.
- [ ] 6.6 🔴 Bump de `tree_version` `v4.0.0 → v4.1.0` en los **dos** sitios: `pipeline.py:41` (default de `compute_classifier_config_hash`) y `routes/health.py:59` (`_TREE_VERSION`). Más el test que afirma el valor (`tests/test_health.py:104`).
- [ ] 6.7 Verificar que el hash **cambió** y que el valor nuevo es estable entre corridas. Los 13 tests de reproducibilidad tienen que seguir pasando con el hash nuevo.
- [ ] 6.8 Este bloque va en su propio commit. Es el único que mueve el hash, y el diff que lo mueve tiene que ser legible de un vistazo dentro de seis meses.

## 7. NO se ejecuta en esta change (operativo, gate aparte)

- [ ] 7.1 ⛔ Reclasificar los 23 episodios `sin_clasificar` ya persistidos. Corre contra la base real del piloto, con `persist_classification` idempotente como precondición (ya verificada). **Fuera de alcance.**
- [ ] 7.2 ⛔ Reclasificar las 106 clasificaciones con hash legacy `9dd96894...`, más las que esta change deja legacy. Es el backlog A1 del plan de acción, ya abierto. **Fuera de alcance.**
- [ ] 7.3 ⛔ El segundo sumidero: 21 de 105 episodios (20%) donde los dos codificadores humanos coincidieron en superficial-o-reflexiva y el árbol mandó al eje `autonomo`; `autonomo` es la categoría con más discrepancia humana (38% sobre 182 episodios doblemente codificados, contra 0% de delegación pasiva). Registrado como contexto, **no como alcance**.

## 8. Cierre

- [ ] 8.1 Smoke test del flujo: episodio que deriva por evidencia insuficiente → aparece en la cola → un docente lo revisa → sale de la cola con historial. Va en `tests/e2e/smoke/` **antes** de declarar la change cerrada.
- [ ] 8.2 `make test-fast` en verde, más `pnpm test` de web-teacher. Registrar el conteo y el SHA sobre el que corrió.
- [ ] 8.3 Verificar que `LABELER_VERSION` **no** se movió: esta change no toca el etiquetador N4.
- [ ] 8.4 Verificar que `git diff` sobre `packages/contracts/.../ctr/` está vacío: el hashing de eventos no se toca.
- [ ] 8.5 Actualizar `CLAUDE.md`: `_TREE_VERSION` y los valores de `appropriation` en «Constantes que NO deben inventarse» (REWRITE); el porqué de la regla trivaluada en gotchas (APPEND); conteo de smoke tests si cambió.
- [ ] 8.6 ADR nuevo por la regla trivaluada versionada y por el bump de `tree_version`. El ADR-057 describe el contrato v4.0.0 que esta change modifica — referenciarlo, no reescribirlo.
- [ ] 8.7 Actualizar `obsidian.md` en el lugar: frontmatter (`estado`, `ultimo`), `Estado actual` y `Próximos pasos` se **reescriben**; `Gotchas y aprendizajes` se **apila**. Si solo apilaste, no la actualizaste.
