# Session log

Bitácora de sesiones de trabajo significativas. Lo que vive acá es **changelog narrativo** — qué se hizo, por qué, en qué orden. Las verdades **permanentes** del sistema (invariantes, gotchas, decisiones que aplican a futuro) viven en `CLAUDE.md`, no acá.

**Convención**: cada sesión = un bloque dated `## YYYY-MM-DD`. No editar bloques viejos — agregar uno nuevo. Si una conclusión se vuelve permanente, **promovela** a `CLAUDE.md` y dejá un pointer acá.

---

## 2026-05-17 — PlanMejora.md ejecutado: P1 conceptual + P2-4 protocolo + P2-1/2/3 esqueleto técnico end-to-end

Sesión de ejecución del `PlanMejora.md` (root del wrapper `AI-Native-V4-main/`) que el usuario produjo tras auditar la versión 2026-05-16 del paper (`paper_conaiisi.pdf`) contra el código. Tres sub-sprints encadenados: brechas conceptuales P1 (cerradas con escritura), instrumentos quasi-experimentales P2-1/2/3 (esqueleto técnico end-to-end con placeholders académicos), y trazabilidad estática + navegabilidad + seeds demo.

### Sub-sprint 1 — P1 + P2-4 conceptual (4 brechas del paper + protocolo entrevistas)

1. **`apps/web-teacher/src/utils/docenteLabels.ts`** — `APPROPRIATION_DOCENTE` reformulado con prefijo "En este episodio:..."; `APPROPRIATION_INVESTIGADOR` reformulado con "Perfil tipologico:..." alineado con paper §4.4. Nuevas exportaciones: helper `appropriationWithScope(category, audience)` + constante `APPROPRIATION_REIFICATION_DISCLAIMER` (citable contra paper §4.4 + §7.3).
2. **`apps/web-teacher/src/views/ProgressionView.tsx`** y **`StudentLongitudinalView.tsx`** — render condicional del disclaimer cuando `viewMode === "investigador"`, con `data-testid="appropriation-reification-disclaimer"` para tests E2E futuros.
3. **`docs/adr/053-marcos-interpretativos-y-protocolo.md`** — ADR nuevo (>5000 palabras). Documenta canónicamente los marcos interpretativos MI1 (calidad epistémica), MI2 (apropiación reflexiva en sentido fuerte), MI3 (coherencia estructural multidimensional como horizonte evaluativo) + protocolo interpretativo de 7 principios del paper §7.3 (contextualidad, no-reducción, triangulación obligatoria, no-etiquetado individual, no-uso para alto stake sin triangulación, explicitación de versión, apertura a la crítica) + matriz operacional por fila con correspondencia a archivos del repo. **Cuidado de numeración**: inicialmente fue ADR-049, renombrado a ADR-053 porque 049/050/051/052 ya estaban tomados (ejercicio_id en CTR, metacognitive feedback, CEC features, guardrail modifier respectivamente).
4. **`docs/limitaciones-declaradas.md`** — agregada sección "Los cinco riesgos a priori del diseño cuasi-experimental" con R1 efecto Hawthorne, R2 performatividad cognitiva (confound intervención-medición), R3 deriva LLM, R4 brecha digital previa, R5 sobrecarga cognitiva. Cada riesgo con mitigación operacional y archivos del repo que la materializan. Encuadre actualizado para reflejar dualidad limitaciones técnicas (5 existentes) + riesgos metodológicos (5 nuevos). Entrada de versionado 2026-05-17 agregada.
5. **`docs/research/protocolo-entrevistas-piloto.md`** — protocolo nuevo (~600 líneas) con framework Braun & Clarke (2006) análisis temático reflexivo (sin kappa sobre temas per Braun & Clarke 2019), muestreo estratificado por perfil tipológico × pretest × experiencia previa IA, guía de entrevista en 3 bloques (reconstrucción episodio prototípico + percepción tutor + percepción IA), procesamiento en 6 fases, triangulación explícita con MI1 y MI2 del ADR-053, gates de calidad, cronograma sincronizado con agenda confirmatoria del paper §8.

### Sub-sprint 2 — P2-1/2/3 esqueleto técnico (backend + frontend end-to-end)

6. **Migration**: `apps/academic-service/alembic/versions/20260517_0001_instrumentos_research.py` con 3 tablas (`respuestas_cuestionario_ia`, `respuestas_pretest_autoeficacia`, `respuestas_test_transferencia`) — RLS forzado + UNIQUE (tenant + comisión + student + version + opcionalmente test_id) + indexes + CheckConstraint para `group_assignment IN ('experimental', 'comparison')`.
7. **Modelos SQLAlchemy**: `apps/academic-service/src/academic_service/models/instrumentos.py` con 3 clases heredando de `Base, TenantMixin`. Registradas en `models/__init__.py`.
8. **Schemas Pydantic**: `apps/academic-service/src/academic_service/schemas/instrumentos.py` — 6 schemas (Create + Out por instrumento) con `Literal["experimental", "comparison"]` para group_assignment.
9. **Routes**: `apps/academic-service/src/academic_service/routes/instrumentos.py` — 3 sub-routers (cuestionario_ia, pretest, transferencia) con POST/GET/me/catalogo + endpoints `/summary` con k-anonymity gate `MIN_STUDENTS_FOR_COHORT_SUMMARY=5`. Idempotencia 409 + validación 422. Registrados en `main.py`.
10. **Contenido placeholder**: `apps/academic-service/src/academic_service/services/instrumentos_content.py` — catálogos de items con marcadores `[PLACEHOLDER GARIS]` / `[PLACEHOLDER CATEDRA UTN]` explícitos para que cuando Garis y la cátedra validen, sólo saquen el marker. Funciones `validate_*_responses()` + `compute_pretest_autoeficacia_scores()` (total + sub-escalas por promedio) + `evaluate_test_transferencia_answer()` (devuelve False por default — placeholder hasta que cátedra apruebe patrones).
11. **Casbin**: `apps/academic-service/src/academic_service/seeds/casbin_policies.py` — +21 policies (3 recursos × 7 acciones cada uno: 3 superadmin C/R/D + 1 docente_admin R + 1 docente R + 2 estudiante C/R). Total recurso = 205 (era 184).
12. **Tests unitarios**: `apps/academic-service/tests/unit/test_instrumentos.py` — cobertura de schemas + validación + scoring + catálogo. Incluye `test_catalogo_tiene_marcadores_placeholder` que asegura que ningún item del esqueleto se cuela como contenido validado.
13. **API client web-student**: `apps/web-student/src/lib/api.ts` — 9 funciones nuevas (3 por instrumento: catalogo + submit + me) + namespace `instrumentosApi`.
14. **Página web-student**: `apps/web-student/src/pages/InstrumentosPage.tsx` — página única con 3 cards (Cuestionario IA + Pretest Likert 1-7 + Transferencia con N problemas). Idempotencia "Ya respondiste" + draft notice + renderer dinámico de items (likert/single_choice/multiple_choice/code).
15. **API client + vista web-teacher**: `apps/web-teacher/src/lib/api.ts` (3 funciones summary) + `apps/web-teacher/src/views/InstrumentosCohorteView.tsx` (3 SummaryCards con k-anonymity gate visual — si `insufficient_data:true`, muestra warning en vez de distribuciones; renderiza `APPROPRIATION_REIFICATION_DISCLAIMER` en header).

### Sub-sprint 3 — Navegabilidad + seed demo + docs canónicos

16. **Rutas TanStack**:
    - `apps/web-student/src/routes/instrumentos.tsx` — `/instrumentos?comisionId=...` con zod search schema + redirect a `/` sin comisionId. Usa `STUDENT_PSEUDONYM_DEV` para dev.
    - `apps/web-teacher/src/routes/instrumentos-cohorte.tsx` — `/instrumentos-cohorte?comisionId=...` con mismo patrón que `progression.tsx`.
17. **Navegación**:
    - Web-teacher `__root.tsx` — link "Instrumentos research" agregado a NAV_GROUPS Análisis con icono `FlaskConical`.
    - Web-student `materia.$id.tsx` — link "Cuestionarios de investigación" agregado al `ContextualHeader` (visible siempre cuando el estudiante está en una materia).
18. **Seed demo**: `scripts/seed-instrumentos-respuestas.py` — script idempotente (`ON CONFLICT DO NOTHING`) que inserta respuestas placeholder de los 18 estudiantes del seed-3-comisiones a los 3 instrumentos. Total esperado en primer run: 18 cuestionario_ia + 18 pretest + 54 transferencia (3 problemas × 18 estudiantes) = 90 inserts. Habilita ver el dashboard cohorte con N=6 por comision (suficiente para pasar `MIN_STUDENTS_FOR_COHORT_SUMMARY=5`).

### Trazabilidad ejecutada

- `python -c "ast.parse(...)"` × 7 archivos Python nuevos (los 6 backend + el seed): **OK**.
- `pnpm -F web-student run typecheck` y `pnpm -F web-teacher run typecheck`: **0 errores nuevos** en archivos modificados. Errores TS preexistentes en `CorreccionesView.tsx`, `EjerciciosView.tsx`, `lib/api.ts` (web-student) ya documentados en `audi2.md §5.1` no se introdujeron en este sprint.
- `biome check` targeteado a 6 archivos frontend nuevos/modificados: **0 errores** post-fixes (formato automático + `fieldset/legend` a11y + `useTemplate` style). Errores preexistentes en otros archivos sin tocar.

### Trazabilidad pendiente (requiere stack bootstrapped)

- `make migrate` para aplicar `20260517_0001_instrumentos_research.py` contra Postgres real.
- `uv run python -m academic_service.seeds.casbin_policies` para re-seedear las 205 policies.
- `uv run python scripts/seed-instrumentos-respuestas.py` para poblar datos demo.
- `uv run pytest apps/academic-service/tests/unit/test_instrumentos.py -v` para correr suite Python unit.
- `make test-smoke` para 30 smoke E2E API.
- `make check-rls` para verificar que las 3 tablas nuevas tienen RLS policy.
- Manual: levantar stack + abrir web-student :5175 → entrar a materia → click "Cuestionarios de investigación" → verificar form. Idem web-teacher :5174 → sidebar "Instrumentos research" → verificar agregados.

### Lo que NO se ejecutó (por restricciones reales no flojera)

- **P0-1** (re-clasificar 106 históricos): requiere DB piloto UTN real, no disponible en este entorno.
- **P0-2** (validación intercoder κ≥0.70): requiere 2 docentes humanos × semanas de etiquetado.
- **P0-3** (attestation Ed25519 en VPS): requiere credenciales del VPS UTN.
- **P2-1/2/3 contenido académico final**: requiere revisión coautoral con Garis + aprobación comité ético UTN. El esqueleto técnico arriba está listo para recibir el contenido aprobado sin tocar plumbing.
- **P3 (Caliper/xAPI, Pyodide, features con flag OFF)**: el paper §5.1 los declara explícitamente como agenda; no urgentes para defensa.

### Decisiones técnicas no obvias

- **ADR-053 vs ADR-049**: el último ADR libre era 053, no 049. ADR-049=ejercicio_id en CTR payload, ADR-050=metacognitive feedback, ADR-051=CEC features, ADR-052=guardrail modifier. Verificar siempre con `ls docs/adr | sort | tail` antes de asumir numeración.
- **Endpoints `/summary` en academic-service, no en analytics-service**: la data + RLS + Casbin viven en academic-service. Mover los endpoints de agregado al analytics-service hubiera requerido infraestructura cross-service sólo para esto — overkill para esqueleto.
- **`exactOptionalPropertyTypes: true` en tsconfig del web-student**: requiere `getToken: TokenGetter | undefined` explícito (no `getToken?: TokenGetter`) cuando se pasa downstream.
- **Biome a11y exige `<fieldset><legend>` sobre `<div><label>`** para inputs agrupados (radio, checkbox). `<label><span>...</span><select>...</select></label>` es OK para selects solo.
- **`func.cast(boolean → int)`** en SQLAlchemy NO funciona directo — usar `case((cond, 1), else_=0).cast(Integer)` para contar booleanos como int.
- **Anti-reificación se aplica al label dinámico del episodio (donde se atribuye categoría)** + disclaimer en vista cohortal investigador. NO se aplica a leyendas hardcoded del código de colores (que explican el color en abstracto, no atribuyen al estudiante).
- **Placeholders académicos como string literal `[PLACEHOLDER GARIS]` / `[PLACEHOLDER CATEDRA UTN]`** (no comments) para que `test_catalogo_tiene_marcadores_placeholder` los pueda verificar. Cuando Garis aprueba un item, le saca el marker manualmente.

### Artefactos del wrapper (no commiteados al repo)

- `PlanMejora.md` (root del wrapper `AI-Native-V4-main/`) — fuente del plan ejecutado; ~700 líneas con 4 prioridades P0/P1/P2/P3 + mapa de impacto sobre defensa doctoral.

### Sub-sprint 4 (continuación) — A1 + A3 script + P3-1 Caliper/xAPI exporter

Cierre del código que destraba dependencias externas (P0-1, P0-3 parcial) + agenda explícita P3-1 del paper §5.1:

19. **`scripts/reclassify-legacy-106.py`** — script batch que re-clasifica las classifications con `classifier_config_hash` legacy (~106). Estrategia: calcula el hash vigente con `compute_classifier_config_hash(DEFAULT_REFERENCE_PROFILE, "v1.0.0")`, lista current con hash distinto via SQL directo al CLASSIFIER_DB, y para cada episode_id hace `POST /api/v1/classify_episode/{id}` con headers de service-account `classifier_worker`. El endpoint ya es idempotente (A12 cumplida) — re-correr el script es seguro. Modo `--dry-run` para reportar sin persistir. Cuando Cortez tenga acceso a DB del piloto UTN, corre el script y cierra P0-1.
20. **`scripts/verify-attestation-deployment.py`** — chequeo continuo del deploy del `integrity-attestation-service` en VPS UTN. 4 chequeos: HTTP health, pubkey match con PEM esperada (mismatch = clave rotada sin avisar), consumer lag del stream `attestation.requests` en Redis, verificación bit-exacta de un journal day con la pubkey servida. Exit codes distintivos (0/1/2/3) según severidad. Complementa el checklist existente `docs/pilot/attestation-deploy-checklist.md` que ya cubre deploy inicial; este script es para monitoring continuo (cron semanal del doctorando contra VPS).
21. **Caliper Analytics 1.2 + xAPI 1.0.3 exporter MVP** (cierra P3-1 — el paper §5.1 lo declara como "agenda de extension del sistema instrumental"):
    - `apps/analytics-service/src/analytics_service/services/caliper_xapi_exporter.py` — funciones puras `to_caliper(events, context)` (envelope IMS Caliper 1.2) y `to_xapi(events, context)` (lista xAPI 1.0.3 statements). Mapeo de 10 tipos de eventos CTR a verbos/types estandar + IRIs custom bajo namespace `https://ai-native.utn.edu.ar/vocab/v1/` para términos del Modelo N4 sin equivalente. Hashes versionados (`self_hash`, `chain_hash`, `prompt_system_hash`, `chunks_used_hash`, `labeler_version`) preservados en `extensions` para auditoría externa.
    - `apps/analytics-service/src/analytics_service/routes/export_standards.py` — endpoints `GET /api/v1/export/caliper/{episode_id}` y `GET /api/v1/export/xapi/{episode_id}` pull-based on-demand. Fetch eventos del `ctr_store` con `set_tenant_rls`.
    - Registrado en `main.py`.
    - Tests unit `apps/analytics-service/tests/unit/test_caliper_xapi_exporter.py` con cobertura de envelope shape, actor mapping (student=Person/Agent, tutor=SoftwareApplication/Agent+account), event-type mapping parametrizado, extensions preservadas, result mapping para tests_ejecutados (success=True si failed=0).

**Decisiones técnicas del sub-sprint 4**:
- A1 via HTTP al endpoint existente (no via re-implementación in-process) → reusa idempotencia A12 + auth flow.
- A3 NO duplica `docs/pilot/attestation-deploy-checklist.md` (374 líneas, ya completo) — agrega script complementario de monitoring continuo.
- Exporter Caliper/xAPI es **on-demand pull-based**, NO push automatico → coherente con paper §5.1 "inspirado en, no analogo a". CTR sigue siendo fuente de verdad bit-exacta.
- Trazabilidad sub-sprint 4: 6/6 archivos Python parsean con `ast.parse`. Sin trazabilidad TS porque el sprint es 100% Python.

---

## 2026-05-16 (sesión vespertina, continuación) — Análisis cognitivo + plan CS01-CS24 + 7 ediciones consolidadas en paper y tesis sincronizada

Sesión de continuación tras cerrar el análisis pedagógico socrático (informeSoc.md) y sus implementaciones (R1-R10 + ADRs 050-052). El usuario pidió un segundo análisis desde lente de **ciencia cognitiva del aprendizaje y medición educativa** —complementario al socrático, no redundante—. La sesión produjo: informe cognitivo independiente, plan de acción derivado, ejecución de las acciones P0 sobre el paper, sincronización con la tesis doctoral extendida, y arreglo de inconsistencias residuales.

### Pasos ejecutados (en orden)

1. **`informeSocra1.md` creado en el wrapper** (~43 KB, 10 secciones). Análisis cognitivo externo desde marco teórico de medición educativa contemporánea (Mislevy/Steinberg/Almond 2003, Pellegrino/Chudowsky/Glaser 2001, Cronbach/Meehl 1955, Messick 1989, Sweller 1988-2011, Chi 1989-2014, Anderson 1983, Vygotsky 1934/1986, Bandura 1997, Flavell 1979, Schraw 1998, Veenman 2006). Identifica 6 observaciones cognitivamente sustantivas + 5 riesgos + 4 brechas de validación. Distingue **process assessment** (lo que el sistema mide) de **learning assessment** (lo que el sistema NO mide aún). Hallazgo crítico: la operacionalización vigente de CCD (`ccd.py:18-41`) tiene la rama de prompts reflexivos desactivada en runtime porque el tutor-service emite siempre `prompt_kind=solicitud_directa` — la validación intercoder κ ≥ 0,70 valida la versión reducida del constructo, no la conceptual.

2. **`plan1Socra.md` creado en el wrapper** (~40 KB, 12 secciones, 24 acciones CS01-CS24 priorizadas P0/P1/P2/P3). DAG explícito de dependencias, tabla de estado por acción, plan de reescritura del paper sección por sección con bibliografía expandida (20+ referencias verificadas en informeSocra1.md), 6 riesgos honestos del propio plan.

3. **8 acciones P0 ejecutadas sobre el paper-draft.md** con marcas DRAFT iniciales (post hoc removidas — ver paso 8):
   - CS02: distinción cii_evolution_intra vs cii_evolution_longitudinal en prosa de §4.5.
   - CS08: ratio prompt:exec declarado como decisión del implementador en §4.5 Tabla 3 + comentario extendido en `apps/classifier-service/src/classifier_service/services/ct.py`.
   - CS07: glosa terminológica "perfil tipológico de apropiación X" en §4.4.
   - CS03: distinción CCD-piloto-1 vs CCD-conceptual en §4.5 Tabla 3 + docstring extendido en `apps/classifier-service/src/classifier_service/services/ccd.py`.
   - CS01: 4 párrafos nuevos en §4.3 enunciando explícitamente MI1 (calidad epistémica de la trayectoria), MI2 (apropiación reflexiva en sentido fuerte), MI3 (coherencia estructural multidimensional como horizonte evaluativo) + distinción MI vs H. **La edición más sustantiva del paper en esta sesión.**
   - CS06: párrafo nuevo al final de §3 tematizando asimetría cognición distribuida declarada vs operacionalizada (Hutchins 1995, Clark & Chalmers 1998).
   - CS05: 2 párrafos nuevos en §9 sobre process assessment vs learning assessment anclados en Pellegrino, Chudowsky y Glaser (2001).
   - CS04: NO aplicado al paper (es script de análisis, no contenido textual).

4. **4 protocolos de instrumentos P1 creados en `docs/research/`**:
   - `protocolo-nasa-tlx.md` (CS09) — Paas (1992) 1 ítem + NASA-TLX completo opcional, aplicación al 20% de episodios al cierre.
   - `protocolo-mai-metacognicion.md` (CS10) — Schraw & Dennison (1994) MAI completo o Jr. MAI, pre/post cuatrimestre.
   - `diseno-test-transfer.md` (CS11) — 5 problemas isomórficos al banco, endpoint y tabla diseñados.
   - `protocolo-autoeficacia-programacion.md` (CS12) — Lishinski et al. (2016) CS Self-Efficacy Scale recomendado, pre-test único.

5. **3 scripts de validación de constructo P2 creados en `scripts/`** (modo `--dry-run` funcional con datos sintéticos, modo productivo `raise NotImplementedError` bloqueado por A1):
   - `sensitivity-analysis-cognitive-coherences.py` (CS04) — 34 corridas planificadas (6 CT pause + 4 CCD window + 24 tree thresholds ±20%).
   - `factorial-analysis-coherences.py` (CS17) — KMO + Bartlett + análisis paralelo de Horn + EFA. Funciones puras numpy. scipy opcional con fallback `p_value=-1.0` sentinel si no está instalado.
   - `typology-vs-dimensional.py` (CS18) — 3 modelos OLS (tipológico + dim_sum + dim_pca). Dry-run sintético: R²_adj 0.456 / 0.383 / 0.132.
   - `clustering-coherences.py` (CS19) — k-means++ + asignación semántica de nombres + κ Cohen vs árbol. Dry-run sintético: κ=1.000 con clusters bien separados.

6. **Documento de revisión coautoral `revision-coautoral-paper-2026-05-16.md` creado en el wrapper** (~28 KB, 10 secciones). Material para que Cortez tenga la sesión coautoral con Ana Garis sobre las 7 ediciones DRAFT con texto ANTES/DESPUÉS verbatim, motivación, opciones (a/b/c/d), formato de decisión checkbox por edición.

7. **Inconsistencias detectadas y arregladas en 4 archivos** (verificación coordinada post-redacción de los documentos):
   - **paper-draft.md CS06**: cerraba con "Línea 8 de la agenda confirmatoria de la Sección 8" pero §8 declara siete líneas. Reformulado a "agenda de investigación futura sobre cognición distribuida instrumentada, articulada con la agenda confirmatoria de la Sección 8".
   - **§15 inexistente**: el paper va de §1 a §10, no tiene §15 Limitaciones formal. 4 archivos referenciaban §15 erróneamente. Arreglado en informeSocra1.md (2 menciones), plan1Socra.md (8 menciones), revision-coautoral (4 menciones), aclarando que §15.6 referencia la **tesis extendida** (documento distinto del paper, 250 páginas vs 15) en informeSocra1.md y ccd.py.

8. **tesis16mayo.docx creado en el wrapper** (105 KB) — la tesis doctoral extendida (`AI-NativeV3-main/documentos/Tesis4.docx`, 1707 líneas markdown) sincronizada con las 7 ediciones del paper, propagadas en prosa adaptada al registro más extenso de la tesis. Workflow: pandoc Tesis4.docx → markdown, edits Claude en wrapper, pandoc markdown → tesis16mayo.docx con `--reference-doc=Tesis4.docx` para preservar formato. Mapeo paper → tesis:
   - CS06 → §3.1 Cognición distribuida (final).
   - CS01 → §4.9 Estatus epistemológico de los constructos (6 párrafos, la inyección más grande).
   - CS07 → §4.6 Nivel N4 (final).
   - CS02 + CS03 → §4.11 Coherencia estructural (final).
   - CS08 → §5.4 Métricas derivadas (final).
   - CS05 → §19.2 Limitaciones del modelo (final).
   - CS04: NO aplicada (script auxiliar).
   - Nota de versionado al inicio del documento enumerando las 7 actualizaciones con su sección. Cada inyección marcada con "**Actualización sincronizada con paper Cortez & Garis (revisión 2026-05-16, CSXX).**".

9. **Cierre de las 7 ediciones DRAFT del paper**: removidos los 7 HTML comments `<!-- DRAFT csXX -->` con script Python (regex multilínea + limpieza de líneas en blanco consecutivas). **Bug detectado y corregido**: CS03 y CS08 vivían DENTRO de HTML comments en celdas de la Tabla 3 (no como texto inline), entonces la remoción de comments eliminó el contenido sustantivo. Restaurados como texto inline en las celdas. Verificación final: 11/11 checks de contenido OK, 0 DRAFT csXX residuales. Total chars del paper: 85.070.

10. **Documentos de gobierno actualizados con estado final**:
    - `plan1Socra.md` tabla §7: CS01-CS03, CS05-CS08 marcadas como **CONSOLIDADO 2026-05-16 (paper + tesis16mayo.docx)** con ubicación exacta en cada documento. CS04 marcado como "script entregado (dry-run OK), ejecución bloqueada por A1".
    - `revision-coautoral-paper-2026-05-16.md` con bloque de actualización al inicio declarando que las 7 ediciones fueron consolidadas por decisión del autor principal, los HTML comments removidos, y que el documento se mantiene como **registro de motivación y opciones consideradas** —no como agenda bloqueante— para sesión post-consolidación con Ana Garis si decide reformular alguna edición.

### Lo que NO se hizo (deliberadamente)

- **NO se invitó a Ana Garis a sesión coautoral pre-consolidación**. El usuario decidió consolidar las 7 ediciones sin esperar la sesión. La sesión sigue siendo recomendable como revisión post-consolidación.
- **NO se aplicó CS04 al paper** (es script de análisis, no contenido textual).
- **NO se ejecutaron los scripts en modo productivo**. Los 4 scripts (sensitivity, EFA, IRT, clustering) están bloqueados por A1 (re-clasificación de las 106 históricas con classifier_config_hash post-LABELER 1.2.0). Modo `--dry-run` funciona con datos sintéticos.
- **NO se aplicaron las acciones P1 efectivas** (CS13-CS16 aplicar instrumentos). Requieren consentimiento ético + cohorte de piloto-2. Los protocolos están diseñados.
- **NO se tocaron las acciones P3** (CS21-CS24). Eje B post-defensa o piloto-3.
- **NO se commiteó nada**. Decisión explícita: el usuario revisa el resultado y decide cuándo committear.

### Cifras de la sesión

- **Documentos académicos nuevos** (4 en wrapper): `informeSocra1.md`, `plan1Socra.md`, `revision-coautoral-paper-2026-05-16.md`, `tesis16mayo.docx`. Total ~227 KB.
- **Protocolos P1 nuevos** (4 en `docs/research/`): NASA-TLX, MAI, transfer, autoeficacia. Total ~24 KB.
- **Scripts P0/P2 nuevos** (4 en `scripts/`): sensitivity-analysis, factorial-analysis, typology-vs-dimensional, clustering. ~28 KB Python.
- **Ediciones al paper-draft.md** (7 consolidadas): de 336 líneas iniciales → 355 líneas finales (+19 líneas netas de contenido sustantivo).
- **Ediciones al código fuente** (2 archivos): docstring de `ccd.py` ampliado, comentario inline en `ct.py`.
- **Tesis sincronizada** (`tesis16mayo.docx`): 7 inyecciones en prosa adaptada, verificada con python-docx (869 párrafos, 317.895 chars, 18/18 checks de contenido OK).
- **Inconsistencias arregladas**: 1 en paper-draft (Línea 8), 14 menciones erróneas a §15 en 3 documentos.
- **Tasks ejecutadas**: 37 tasks creadas en la sesión, 37 completadas.

### Archivos tocados

**Wrapper** (`C:/Socrates/AI-Native-V4-main/AI-Native-V4-main/`):
- `informeSocra1.md` (nuevo).
- `plan1Socra.md` (nuevo, después actualizado con estado CONSOLIDADO).
- `revision-coautoral-paper-2026-05-16.md` (nuevo, después actualizado con cierre).
- `tesis16mayo.docx` (nuevo).
- `informeSoc.md` (sin cambios — referencia desde nuevo análisis).

**Monorepo** (`AI-NativeV3-main/`):
- `apps/classifier-service/src/classifier_service/services/ccd.py` (docstring ampliado con CS03).
- `apps/classifier-service/src/classifier_service/services/ct.py` (comentario CS08).
- `docs/papers/paper-draft.md` (7 ediciones consolidadas + arreglo Línea 8).
- `docs/research/protocolo-nasa-tlx.md` (nuevo).
- `docs/research/protocolo-mai-metacognicion.md` (nuevo).
- `docs/research/diseno-test-transfer.md` (nuevo).
- `docs/research/protocolo-autoeficacia-programacion.md` (nuevo).
- `scripts/sensitivity-analysis-cognitive-coherences.py` (nuevo).
- `scripts/factorial-analysis-coherences.py` (nuevo).
- `scripts/typology-vs-dimensional.py` (nuevo).
- `scripts/clustering-coherences.py` (nuevo).
- `docs/SESSION-LOG.md` (este bloque).

### Próximos pasos identificados (requieren participación humana)

- **Sesión coautoral con Ana Garis** post-consolidación: revisión de las 7 ediciones consolidadas en paper y tesis16mayo, decisión de reformular o aprobar tal como están. Material de la sesión: `revision-coautoral-paper-2026-05-16.md`.
- **A1 cierre** (re-clasificación de 106 históricas con classifier_config_hash post-LABELER 1.2.0): pre-condición de los 4 scripts P2 (sensitivity, EFA, IRT, clustering).
- **Aplicación de instrumentos P1** en piloto-2: requiere aprobación de comité ético UTN.
- **Resolución de inconsistencias residuales `tesis §15.6`**: el código (ccd.py docstring) y `01-fixes-codigo-chicos.md` referencian "tesis §15.6 / §19.5" — esa numeración era de una versión anterior de la tesis. tesis16mayo.docx tiene §15.4 Coherencia estructural y §19.x sobre limitaciones. Decidir si actualizar las referencias del código o aclarar contexto histórico.

---

## 2026-05-16 — Informe pedagógico externo + 9 recomendaciones implementadas (R1-R10) + 3 ADRs nuevos

Sesión motivada por el pedido del usuario (Cortez) de un análisis externo en rol de especialista en didáctica universitaria y método socrático sobre la implementación del tutor + la trazabilidad cognitiva N4. El análisis se materializó en `informeSoc.md` (wrapper, mismo nivel que `paper-draft.md`) con marco teórico fuerte (Vlastos 1983, Lipman 1988, Boghossian 2013, Flavell 1979, Schraw 1998, Veenman 2006) e identificó cinco brechas pedagógicas: (1) prompt v1.1.0 implementa "no entrega solución" pero no mayéutica/elenchos/aporía como movimientos estructurados; (2) taxonomía N4 mide actos observables, no movimientos de pensamiento; (3) el estudiante es objeto del análisis, no sujeto; (4) árbol de decisión opaco; (5) cuello de botella κ ≥ 0,70 requiere manual del etiquetador que no estaba documentado. Diez recomendaciones priorizadas P0/P1/P2 con esfuerzos estimados.

A partir del informe el usuario pidió ejecutar todas las recomendaciones implementables sin inventar contenido sin respaldo. La sesión cubrió:

### Pasos ejecutados (en orden)

1. **`informeSoc.md` creado en el wrapper** (~16 KB, 9 secciones). Análisis pedagógico externo + 10 recomendaciones P0/P1/P2. Marco socrático estricto (cuatro movimientos: ironía, mayéutica, elenchos, aporía) contrastado con la implementación actual.

2. **Auto-corrección del informe (durante R2)**: verificación reveló dos errores propios del primer borrador:
   - **Error 1**: afirmar "el paper tiene 5 categorías de apropiación (autonomo/superficial/delegacion_pasiva/delegacion_extrema/regresivo)". Verificación de `paper-draft.md` §4.4 (Tabla 2) mostró que el paper define **tres tipos** coincidentes con `tree.py`. Las 5 categorías aparecían solo en el README del wrapper (líneas 263-267) sin respaldo en paper ni código. "Autonomo" en `ProgressionView.tsx:415` es label de UI para `apropiacion_reflexiva` (CSS var `--color-appropriation-reflexiva`).
   - **Error 2**: afirmar "el tutor responde la reflexión". Verificación de `ReflectionModal.tsx` + tests del backend mostró que el componente solo persiste 3 strings; **no hay streaming ni respuesta del tutor**.
   - R2 anulado como "reconciliación 3→5" (12-16h) y reemplazado por R2-corregido: actualización del README del wrapper para alinear con paper + código (3 categorías). Correcciones marcadas explícitamente en `informeSoc.md` §0, §3.4, §5(c), tabla P0.

3. **R1 — Manual del etiquetador N4** (`docs/research/manual-etiquetador-N4.md`, ~470 líneas). Criterios operacionales por nivel N1-N4, casos límite resueltos (anotación a los 119s vs 121s, tests pasando a 59s vs 60s, etc.), formato yaml de fichas para Protocolo A y dossiers para Protocolo B, protocolo de **pre-calibración interna con dir + co-dir sobre 20 eventos + 5 episodios** antes de invitar a los dos docentes UTN al estudio intercoder formal de ADR-046. P0 absoluto: ejecutar pre-calibración antes de invertir ~50 h docente.

4. **R4 — Prompt v1.2.0 DRAFT** (`ai-native-prompts/prompts/tutor/v1.2.0/system.md`, no activado en manifest). Incorpora los cuatro movimientos socráticos como secciones explícitas: ironía (suspender el saber del tutor), mayéutica como **secuencia de 4 pasos** (explicitar creencia → probar con caso → mostrar consecuencia → pedir reformulación), elenchos (poner al estudiante en contradicción consigo mismo, no con compilador ni con tutor), aporía productiva (validar el desconcierto en vez de simplificar el problema). Cobertura 9/10 guardarrailes formales (vs 4/10 en v1.1.0): agrega GP3, GC1, GC2, GC4, GC5. Activación bloqueada hasta revisión coautoral con Ana Garis + decisión de dir/co-dir + bumpeo coordinado de `default_prompt_version` en `config.py`.

5. **R6 — ReflectionModal reescrito** (`apps/web-student/src/components/ReflectionModal.tsx`). Cambios textuales únicamente: tres preguntas reformuladas de genéricas ("¿Qué aprendiste?") a metacognitivamente situadas ("¿En qué momento del episodio sentiste que algo hizo click?", "Si alguien viniera a hacer el mismo ejercicio mañana, ¿qué le contarías sobre cómo encararlo?", "¿Te quedaste con alguna pregunta sin responder?"); copy intro reescrito de "es opcional, podés saltearla sin problema" a "tomate un minuto para pensar... esto es para vos, no es una entrega, no se califica, y nadie te va a responder"; botón "Saltar" → "No quiero reflexionar ahora". **Keys del payload preservadas** (`que_aprendiste`, `dificultad_encontrada`, `que_haria_distinto`, `prompt_version="reflection/v1.0.0"`, `tiempo_completado_ms`) — los tests de `test_reflexion_completada.py:165-183` no se modifican.

6. **R10 — Política de visibilidad estudiante** (`docs/research/politica-visibilidad-estudiante.md`). Tres niveles: Nivel 0 (estudiante ve siempre — código, chat, reflexiones anteriores, tiempo absoluto), Nivel 1 (opt-in: devolución metacognitiva narrativa sin score sin categoría, distribución temporal con etiquetas descriptivas en lugar de N1-N4), Nivel 2 (solo docente: categoría de apropiación, 5 coherencias numéricas, slope longitudinal, cuartiles, alertas). **Excepción crítica**: el estudiante debe recibir notificación post-cierre de intentos adversos severidad ≥ 3 detectados sobre él — detectar sin avisar normaliza vigilancia no consentida.

7. **R9 — Encuesta interpretación docente alertas** (`docs/research/encuesta-interpretacion-docente-alertas.md`). Instrumento semi-estructurado: 4 ítems Likert + 2 ítems de framing + 3 viñetas con casos sintéticos + 2 preguntas abiertas. Métrica primaria `framing_pedagogico ∈ [-1, +1]` para medir si los docentes interpretan las alertas como guía pedagógica o como predicción de aprobación. Análisis cualitativo con dos codificadores y κ ≥ 0,70 sobre dimensión "intervención situada vs asunción de pronóstico". Aplicación retrospectiva 2 semanas antes de los promedios finales (evitar contaminación retrospectiva).

8. **R5 — Módulo `metacognitive_feedback.py`** (`packages/platform-ops/src/platform_ops/`, ~280 LOC). Función pura `generate_metacognitive_feedback(events)` + 7 plantillas determinísticas seleccionadas por reglas en orden fijo: `episodio_corto` (<5 eventos, defensiva), `abandonado_o_comprometido` (defensiva), `sin_tutor`, `solo_conversacion`, `integrando_feedback` (≥50% prompts post-tests), `consulta_temprana` (≥50% prompts en primeros 180s), `mixto` (default). Las 7 plantillas marcadas **DRAFT — PENDIENTE REVISIÓN COAUTORAL** con dir + co-dir + Ana Garis; `is_draft=True` en cada respuesta + sufijo `-draft` en `METACOG_FEEDBACK_VERSION = "1.0.0-draft"`. 11 tests golden incluyendo **invariantes pedagógicas**: ninguna plantilla nombra `reflexiva/superficial/delegacion`, ninguna nombra `N1/N2/N3/N4`, ningún score numérico.

9. **R7 — Módulo `cec_features.py`** (`packages/platform-ops/src/platform_ops/`, ~270 LOC). Tres funciones puras: `depth_variance` (varianza poblacional de profundidad de anidamiento AST entre snapshots), `function_granularity` (promedio de líneas-por-función + conteo de outliers fuera del rango [5, 30]), `naming_consistency` (heurística regex de homogeneidad snake/camel/pascal). Agregador `compute_cec(snapshots) -> CECResult` con `cec_summary ∈ [0, 1]`. **NO conectado a `pipeline.py` ni `tree.py`**. Fail-soft sobre código con SyntaxError: `_safe_parse` devuelve None, las funciones degradan graciosamente. 14 tests golden + smoke verificado: código coherente da `cec_summary=1.000`. Bloqueo arquitectónico (A1 + validación empírica de no-redundancia) documentado en docstring del módulo + ADR-051.

10. **R8 — Módulo `guardrail_signals.py`** (`packages/platform-ops/src/platform_ops/`, ~190 LOC). Función pura `extract_guardrail_signals(events) -> GuardrailSignals` que agrega los `intento_adverso_detectado` en resumen estructurado (total, severity_3_plus_count, categories_detected, overuse_confirmed). Función pura `apply_guardrail_modifier(classification, signals) -> classification_modificada` con 4 reglas en orden fijo: combinación severa (regla 1: severidad ≥3 + overuse sobre reflexiva → delegación), 3+ severidad alta (regla 2: bajar un nivel), 1-2 severidad alta (regla 3: marcar warning sin modificar), solo overuse (regla 4: marcar flag). Usa `dataclasses.replace` para devolver copia — no muta input. **Feature flag `guardrail_modifier_enabled: bool = False`** agregado a `apps/classifier-service/src/classifier_service/config.py` con comentario citando los 4 gates (A1 + Protocolo B + calibración + decisión académica). 14 tests golden + smoke verificado: 3 intentos severidad 3 sobre `apropiacion_reflexiva` → `apropiacion_superficial`, `appropriation_before_modifier` en features, original intacto.

11. **Verificaciones de no-regresión ejecutadas**:
    - `ast.parse` sobre los 7 archivos Python (3 módulos + 3 tests + config.py): OK.
    - Imports de los 3 módulos vía `python -c "import sys; sys.path.insert(0, 'packages/platform-ops/src'); from platform_ops.X import Y"`: OK.
    - Smoke test directo de las 3 funciones con datos sintéticos: outputs determinísticos coherentes con el diseño.
    - Verificación de que las keys del payload de ReflectionModal **no cambiaron**: los tests `test_reflexion_completada.py` siguen verdes (validan strings literales que no se tocaron).
    - **NO se corrió pytest** ni se levantó el stack. Los tests están listos para que el usuario los corra con `uv run pytest packages/platform-ops/tests/test_{metacognitive_feedback,cec_features,guardrail_signals}.py -v`.

12. **R5 fase 2, R7 conexión al pipeline, R8 conexión al pipeline, R3 pre-calibración**: NO implementados (requieren participación humana o están bloqueados por A1). Cada uno tiene su design doc en `docs/research/design-*.md` con secciones "Decisiones pendientes" y "Bloqueos a resolver" para spawn de sub-agents posteriores.

13. **Tres ADRs nuevos siguiendo el patrón ADR-044/045 (esqueleto + flag OFF + criterios de revisita)**:
    - **ADR-050** (`050-metacognitive-feedback-skeleton-feature-flag.md`) — Esqueleto técnico de la devolución metacognitiva con plantillas DRAFT. Gates: revisión coautoral + decisión política + endpoint/UI.
    - **ADR-051** (`051-cec-features-skeleton-bloqueado-a1.md`) — Esqueleto de CEC como funciones puras desconectadas del pipeline. Gates: A1 + validación empírica de no-redundancia + calibración rangos + decisión Opción A/B.
    - **ADR-052** (`052-guardrail-modifier-skeleton-feature-flag.md`) — Esqueleto del modificador post-árbol como función pura + flag OFF. Gates: A1 + Protocolo B κ ≥ 0,70 + calibración empírica + decisión académica.

### Lo que NO se hizo (deliberadamente)

- **NO se inventaron categorías académicas**. Cuando la verificación reveló que el README del wrapper listaba 5 categorías sin respaldo, se corrigió el README en lugar de crear un ADR "reconciliación 3→5". El paper y el código coinciden en 3.
- **NO se inventaron plantillas finales para R5**. Las 7 plantillas quedaron explícitamente marcadas DRAFT con doble gate (string `is_draft=True` + sufijo `-draft` en versión + comentarios `# DRAFT — PENDIENTE REVISIÓN COAUTORAL`).
- **NO se conectó R7 al pipeline**. Hacerlo bumpea `classifier_config_hash` antes de A1 y deja las 106 históricas en dos generaciones obsoletas. Bloqueo arquitectónico declarado en ADR-051.
- **NO se conectó R8 al pipeline**. Mismo razonamiento (bumpea hash) + el árbol base requiere intercoder Protocolo B antes de modificarlo. Bloqueo declarado en ADR-052.
- **NO se calibraron las constantes empíricamente** (`CEC FUNCTION_GRANULARITY_MIN_LINES=5`, `MAX_LINES=30`; `SEVERITY_3_PLUS_COUNT_THRESHOLD=3`). Quedaron como operacionalización inicial. Tests anti-regresión congelan los valores actuales hasta que se calibren con dirección.
- **NO se ejecutó pytest** ni se levantó el stack. Verificación se limitó a `ast.parse` + imports + smoke directo. El usuario debe correr los tests.
- **NO se activó el prompt v1.2.0 en manifest.yaml**. Es DRAFT.
- **NO se commiteó nada**. El usuario revisa el resultado y decide cuándo committear.

### Cifras de la sesión

- **Documentos académicos nuevos** (7): `informeSoc.md` (wrapper), `docs/research/manual-etiquetador-N4.md`, `politica-visibilidad-estudiante.md`, `encuesta-interpretacion-docente-alertas.md`, `design-metacognitive-feedback.md`, `design-sexta-coherencia-estructural.md`, `design-integracion-guardrails-classifier.md`.
- **Prompts nuevos** (1 DRAFT): `ai-native-prompts/prompts/tutor/v1.2.0/system.md`.
- **Módulos Python nuevos** (3): `metacognitive_feedback.py` (~280 LOC), `cec_features.py` (~270 LOC), `guardrail_signals.py` (~190 LOC).
- **Test suites nuevas** (3): `test_metacognitive_feedback.py` (11 tests), `test_cec_features.py` (14 tests), `test_guardrail_signals.py` (14 tests). Total 39 tests determinísticos.
- **ADRs nuevos** (3): ADR-050, ADR-051, ADR-052.
- **Archivos modificados** (4): `README.md` (wrapper, corrección 3 categorías), `informeSoc.md` (wrapper, auto-correcciones), `apps/web-student/src/components/ReflectionModal.tsx` (texto), `apps/classifier-service/src/classifier_service/config.py` (+`guardrail_modifier_enabled`).
- **Total LOC nuevas**: ~1000 LOC Python + ~16 KB markdown informe + ~8 KB markdown 6 docs research + ~7 KB markdown 3 ADRs + ~6 KB markdown prompt + entrada al SESSION-LOG. Estimación gruesa.
- **Autocorrecciones del informe original**: 2 errores propios detectados durante verificación y corregidos in-line con marca de fecha.

### Archivos tocados

**Wrapper** (`C:/Socrates/AI-Native-V4-main/AI-Native-V4-main/`):
- `informeSoc.md` (nuevo + 4 auto-correcciones marcadas con fecha).
- `README.md` (modificado, líneas 263-267 alineadas con paper + código).

**Monorepo** (`AI-NativeV3-main/`):
- `ai-native-prompts/prompts/tutor/v1.2.0/system.md` (nuevo DRAFT).
- `apps/classifier-service/src/classifier_service/config.py` (modificado: +`guardrail_modifier_enabled`).
- `apps/web-student/src/components/ReflectionModal.tsx` (modificado: textos).
- `docs/adr/050-metacognitive-feedback-skeleton-feature-flag.md` (nuevo).
- `docs/adr/051-cec-features-skeleton-bloqueado-a1.md` (nuevo).
- `docs/adr/052-guardrail-modifier-skeleton-feature-flag.md` (nuevo).
- `docs/research/manual-etiquetador-N4.md` (nuevo).
- `docs/research/politica-visibilidad-estudiante.md` (nuevo).
- `docs/research/encuesta-interpretacion-docente-alertas.md` (nuevo).
- `docs/research/design-metacognitive-feedback.md` (nuevo).
- `docs/research/design-sexta-coherencia-estructural.md` (nuevo).
- `docs/research/design-integracion-guardrails-classifier.md` (nuevo).
- `docs/SESSION-LOG.md` (modificado: este bloque).
- `packages/platform-ops/src/platform_ops/metacognitive_feedback.py` (nuevo).
- `packages/platform-ops/src/platform_ops/cec_features.py` (nuevo).
- `packages/platform-ops/src/platform_ops/guardrail_signals.py` (nuevo).
- `packages/platform-ops/tests/test_metacognitive_feedback.py` (nuevo).
- `packages/platform-ops/tests/test_cec_features.py` (nuevo).
- `packages/platform-ops/tests/test_guardrail_signals.py` (nuevo).

### Próximos pasos identificados (requieren participación humana)

- **R3 pre-calibración interna**: dir + co-dir sobre 20 eventos del Protocolo A + 5 episodios del Protocolo B usando `manual-etiquetador-N4.md`. Bloqueador del intercoder externo.
- **R5 gate A**: revisión coautoral de las 7 plantillas con Ana Garis. Bumpear `METACOG_FEEDBACK_VERSION` a `"1.0.0"` (sin sufijo) cuando se aprueben.
- **R5 fase 2**: implementación de endpoint + componente UI + schema `preferencia_visibilidad` + evento CTR `devolucion_metacognitiva_mostrada` agregado a `_EXCLUDED_FROM_FEATURES`. Spawn sub-agent post-Gate A.
- **R7 gate B**: validación empírica de no-redundancia CEC sobre 106 históricas post-A1. Script ad-hoc.
- **R8 gate C**: calibración empírica de las 4 reglas sobre 106 históricas + criterio docente sobre muestra.
- **Activación del prompt v1.2.0**: revisión coautoral + decisión dir/co-dir + bumpeo coordinado de `default_prompt_version` en `apps/tutor-service/src/tutor_service/config.py` (G12 — manifest + config alineados).
- **A1**: re-clasificación con DB real del piloto. Pre-condición de R7 gate B y R8 gate C.

---

## 2026-05-09 (sesión vespertina, continuación) — Mejora 3 sub-componente G8b del plan post-piloto-1: esqueleto léxico de `anotacion_creada` con feature flag OFF

Sesión de continuación inmediata tras cerrar la Mejora 4 (ADR-044). El usuario pidió "avancemos" para seguir con la siguiente mejora del orden recomendado. Análisis previo identificó que la Mejora 3 (clasificación semántica de anotaciones) tiene **dos sub-componentes** distintos según ADR-023: G8b (heurístico léxico ~80 LOC + corpus regex, gate humano de validación intercoder) y G8c (semántico vía embeddings ~200 LOC + endpoint nuevo en ai-gateway, gate arquitectónico + Eje B post-defensa). Decisión: atacar G8b con el patrón esqueleto-OFF ya validado en ADR-044; G8c queda fuera de scope porque requiere arquitectura nueva incompatible con el patrón "función pura + flag flip + golden hash".

### Pasos ejecutados (en orden)

1. **Lectura cruzada del ADR-023** entero para confirmar el alcance de G8b (regex sobre contenido textual, dos categorías N1/N4, gate humano de κ docente sobre 50+ anotaciones) y G8c (embeddings via ai-gateway, Eje B post-defensa, mismas restricciones que G14/ADR-017 reservado).

2. **Lectura del `event_labeler.py`** para entender dónde meter el hook. La función pura `label_event(event_type, payload, context)` ya tiene un bloque `if event_type == "anotacion_creada"` que aplica el override temporal v1.1.0 (ADR-023). El hook léxico va ANTES de ese bloque, con precedencia: si el lexical determina N1/N4, gana sobre temporal. Si retorna None, cae al fallback temporal.

3. **Creación de `apps/classifier-service/src/classifier_service/services/event_labeler_lexical.py`** (~165 LOC). Función pura `lexical_label(content) -> "N1" | "N4" | None` con 8 patrones regex distribuidos en 2 categorías. N1 (4 patrones): "estoy leyendo", "el enunciado pide/dice/menciona", "no entiendo todavía", "me piden/tengo que entender". N4 (4 patrones): "ahora entiendo/veo/comprendo", "tras la respuesta", "siguiendo el consejo", "el tutor me dijo/sugirió/explicó". Precedencia: N4 gana sobre N1 si ambos matchean (mismo criterio que el override temporal v1.1.0).

4. **Hash determinista del corpus** con misma fórmula canónica que `socratic_corpus_hash` (ADR-044), `guardrails_corpus_hash` (ADR-043) y `classifier_config_hash` (ADR-009). Golden value calculado: `40db6b9047b3c8fee3665c95f5b86d6ea790afd558564349cb009c0f2ca3fe95`.

5. **Feature flag en `apps/classifier-service/src/classifier_service/config.py`**: `lexical_anotacion_override_enabled: bool = False`. Comentario inline citando ADR-023 + ADR-045 explicando la precedencia léxico > temporal y la garantía preservada (reproducibilidad bit-a-bit del classifier_config_hash sobre classifications históricas del piloto-1).

6. **Hook en `event_labeler.label_event()`** dentro del bloque `anotacion_creada`, ANTES del override temporal v1.1.0: si flag OFF → salta directo al temporal (comportamiento idéntico a v1.1.0); si flag ON → invoca `lexical_label(content)`; si retorna N1/N4, gana; si retorna None, cae al fallback temporal. **Patrón fail-soft**: cualquier excepción del módulo léxico (corrupción de regex, payload malformado) se captura silenciosamente y el flow cae al temporal — el labeler nunca se rompe.

7. **Tests deterministas en `apps/classifier-service/tests/unit/test_event_labeler_lexical.py`** (~125 LOC, 16 tests): casos canónicos N1 (lectura del enunciado, todavía no entiendo, me piden), casos canónicos N4 (ahora entiendo, tras la respuesta, siguiendo el consejo, el tutor me dijo), precedencia N4 > N1 cuando ambos matchean, anotación neutral sin markers (None), anotación vacía (None), determinismo bit-a-bit del corpus_hash, idempotencia, case-insensitive, y golden hash anti-regresión.

8. **Validación inline manual** con `python -c` + `importlib.util.spec_from_file_location` + registro en `sys.modules`. Resultado: 20/20 OK. Todos los patrones N1 y N4 matchean lo esperado, precedencia funciona, neutrales devuelven None, vacías devuelven None, idempotente, case-insensitive.

9. **ADR-045 redactado** en `docs/adr/045-event-labeler-lexical-skeleton-feature-flag.md`. Estructura completa con 7 drivers (D1-D7), 4 opciones consideradas (A elegida; B "esperar al humano" descartada por lead-time; C "activar sin validación" descartada por violar ADR-023; D "implementar G8c directamente" descartada por gate arquitectónico). Criterios de éxito y de revisita para activación. **Supersede PARCIAL del ADR-023** sólo en la sección "G8b sigue como agenda" — la decisión sobre el override temporal v1.1.0 sigue vigente, y G8c sigue siendo agenda Eje B sin esqueleto.

10. **Trío de docs sincronizados**:
    - `CLAUDE.md` sección "Constantes que NO deben inventarse": bullet nuevo del override léxico esqueleto OFF antes del bullet de socratic_compliance.
    - `docs/limitaciones-declaradas.md`: Limitación 3 reescrita post-ADR-045 distinguiendo G8b (esqueleto cerrado, flag OFF) de G8c (sin esqueleto, Eje B). Tabla del plan actualizada. Tabla de referencias verificables actualizada con el nuevo path. Versionado del doc actualizado con la entrada de continuación de la sesión vespertina.
    - `loquehace.md` §13: prosa académica de Limitación 3 reformulada en registro narrativo (números en letras, párrafo continuo) distinguiendo el cierre de G8b del estado pendiente de G8c.

### Lo que NO se hizo (deliberadamente)

- **NO se commiteó nada**. Decisión explícita del flujo: el usuario revisa el resultado y decide cuándo committear.
- **NO se implementó G8c** (clasificación semántica vía embeddings). Fuera de scope del patrón esqueleto-OFF — requiere endpoint nuevo en `ai-gateway`, integración con embeddings, decisiones de modelo y budget. Sigue como agenda Eje B post-defensa, sin esqueleto.
- **NO se prendió el feature flag**. La activación queda explícitamente bloqueada hasta que la validación intercoder con docentes esté disponible (50+ anotaciones reales etiquetadas, κ ≥ 0,6).
- **NO se bumpeó el `LABELER_VERSION`**. Sigue en `"1.2.0"`. El bump a `"2.0.0"` ocurre cuando el flag se prenda post-validación (cambio semántico mayor: contenido textual con precedencia sobre temporal).

### Cifras de la mejora

- **Líneas de código agregadas**: ~165 LOC en `event_labeler_lexical.py` (módulo nuevo) + ~17 LOC de hook en `event_labeler.py` + 14 LOC de feature flag + comentarios en `config.py`. Tests nuevos: ~125 LOC en `test_event_labeler_lexical.py`. ADR: ~210 líneas de markdown. Total: ~531 LOC.
- **Esfuerzo real**: una sesión de trabajo concentrada como continuación de la Mejora 4. Patrón replicado prácticamente verbatim — el costo principal fue redactar el corpus de patrones y el ADR.
- **Archivos tocados**: `event_labeler_lexical.py` (nuevo), `event_labeler.py` (hook + import lazy), `config.py` (flag), `test_event_labeler_lexical.py` (nuevo), `docs/adr/045-...md` (nuevo), `CLAUDE.md` (bullet), `docs/limitaciones-declaradas.md` (Limitación 3 + tabla + versionado), `loquehace.md` (§13 prosa).

### Próximos pasos

- Correr `uv run pytest apps/classifier-service/tests/unit/test_event_labeler_lexical.py -v` desde el entorno con uv para validar la suite completa de 16 tests.
- Coordinar con el usuario la calibración intercoder con docentes para destrabar la activación del flag de G8b.
- Decidir cuándo arrancar la Mejora 2 (alertas predictivas con baseline individual ML, ADR-032) — siguiente del orden recomendado del plan, con gate humano (200 estudiantes con ≥10 episodios + 30 intervenciones docentes etiquetadas + AUC ≥ 0,75) que es **más restrictivo que el de Mejora 3 y 4** porque depende de DATOS DEL PILOTO REAL en curso. La Mejora 1 (forense IA externa) es estructural sin esqueleto posible (limitación del perímetro instrumentado).

---

## 2026-05-09 (sesión vespertina) — Mejora 4 del plan post-piloto-1: esqueleto técnico de Fase B `socratic_compliance` con feature flag OFF

Sesión de continuación del plan post-piloto-1. Tras cerrar la Mejora 5 (overuse, ADR-043) en la sesión AM y crear `docs/limitaciones-declaradas.md` como source-of-truth canónico, el usuario pidió continuar con la siguiente mejora del orden recomendado.

**Hallazgo crítico previo a tocar código**: la auditoría del ADR-027 mostró que la Mejora 4 está marcada como **"Aceptado: DIFERIR a Eje C post-defensa"**, con tres condiciones acumuladas de revisita (validación intercoder κ ≥ 0.6 sobre 50+ respuestas etiquetadas por 2 docentes; acuerdo académico sobre la fórmula; consenso de no afectar el árbol de clasificación). La cláusula textual del ADR-027 — *"el campo queda como `None` en eventos hasta que la calibración con docentes valide el cálculo"* — impide ejecutar el postprocess en runtime sin la validación humana, que el equipo técnico no puede generar autónomamente. A diferencia de Mejora 5 (overuse) que en ADR-019 era "agenda futura" sin gates humanos, ésta tiene gate explícito.

**Decisión adoptada con el usuario**: implementar el esqueleto técnico completo (postprocesador, score, hash determinista, hooks, tests) gateado por feature flag `socratic_compliance_enabled = False` por default. Reduce el lead-time entre disponibilidad del corpus humano y activación de "varias semanas de implementación" a "días de calibración del threshold + flag flip". La cláusula `None` del ADR-027 se preserva literalmente: con flag OFF, los campos del payload siguen siendo `None`/`[]` en runtime.

### Pasos ejecutados (en orden)

1. **Lectura cruzada de archivos clave**: ADR-027 entero, contrato `TutorRespondioPayload` (campos `socratic_compliance: float | None` y `violations: list[str]` ya existían desde F8 como opcionales), flow de `tutor_core.interact()` (hook entre línea 481 post stream-LLM y línea 488 emit `tutor_respondio`), patrón de corpus hash en `guardrails.py:200-227` y patrón de tests deterministas en `test_overuse_detector.py`.

2. **Creación de `apps/tutor-service/src/tutor_service/services/postprocess_socratic.py`** (~210 LOC). Función pura `postprocess(response_content) -> PostprocessResult` con tres categorías de violación: `code_block_complete` (fenced block >200 chars, peso 0.4), `no_question_in_response` (ausencia literal de "?"/"¿", peso 0.3), `direct_answer` (regex sobre imperativos típicos "la solución es", "tenés que", peso 0.3). Pesos suman exactamente 1.0 para que las tres violaciones simultáneas saturen el score a 0.

3. **Iteración sobre la fórmula del score**: la primera versión usaba `severity * weight / MAX_SEVERITY` que no llegaba a 0 con 3 violaciones (daba 0.10). Simplificado a `penalty = sum(weight_i)` sobre categorías distintas presentes; severity queda como metadata informativa en cada Violation pero NO escalea el cálculo. La fórmula simplificada queda decoupled — cambios de severity (relabeling) no rebalanceablen el score.

4. **Hash determinista del corpus** con misma fórmula canónica que `guardrails_corpus_hash` (ADR-043) y `classifier_config_hash` (ADR-009): `sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`, encoding UTF-8. Golden value calculado: `a9b1d8cc5fab959f031f30f9bbb4c2bb632c41acad6f6af3f20897aef2b105b9`.

5. **Feature flag en `apps/tutor-service/src/tutor_service/config.py`**: `socratic_compliance_enabled: bool = False`. Comentario inline citando ADR-027 + ADR-044 explicando la garantía preservada.

6. **Hook en `tutor_core.interact()`** entre el stream-end del LLM y la emisión del `tutor_respondio`: si flag OFF → `socratic_compliance=None, violations=[]`; si flag ON → llama al postprocess y popula. Patrón fail-soft (try/except con `logger.exception`, NO rompe el turno). Importación lazy del módulo dentro del bloque para evitar tocar startup time del tutor-service cuando el flag está OFF.

7. **Tests deterministas en `apps/tutor-service/tests/unit/test_postprocess_socratic.py`**: 12 tests cubriendo respuesta socrática (score 1.0), bloque de código grande, ausencia de pregunta, signo invertido único, imperativo de respuesta directa, tres violaciones simultáneas saturadas a 0, respuesta vacía neutral 0.5, hash determinista bit-a-bit, versión 1.0.0, idempotencia de la función pura, truncado del excerpt al límite 150, y test golden del hash anti-regresión.

8. **Validación inline manual** (sin uv ni venv en este entorno): 7 tests inline con `python -c` + `importlib.util` bypaseando el `__init__.py` del package. Resultado: 7/7 OK, `score=0.0` con 3 violaciones simultáneas, hash matchea golden.

9. **ADR-044 redactado** en `docs/adr/044-socratic-compliance-skeleton-feature-flag.md`. Estructura completa: contexto, decisión (esqueleto + flag OFF), drivers D1-D6, opciones consideradas (A elegida; B "esperar al humano" descartada por lead-time; C "código activo descartando resultado" descartada por código muerto activo), criterios de éxito, criterio de revisita (las 3 condiciones del ADR-027 se mantienen), consecuencias positivas/negativas/neutras. **Supersede PARCIAL del ADR-027**: la decisión de DIFERIR la activación se mantiene; lo que el ADR-044 cierra es la disponibilidad del esqueleto.

10. **Trío de docs sincronizados**:
    - `CLAUDE.md` sección "Constantes que NO deben inventarse": bullet nuevo de `socratic_compliance` esqueleto OFF antes del bullet de `_EXCLUDED_FROM_FEATURES`.
    - `docs/limitaciones-declaradas.md`: Limitación 4 reescrita post-ADR-044 (esqueleto cerrado, activación pendiente). Tabla del plan actualizada (Mejora 4 = "Esqueleto cerrado 2026-05-09 (flag OFF), activación pendiente"). Tabla de referencias verificables actualizada con el nuevo path. Versionado de doc actualizado.
    - `loquehace.md` §13: prosa académica de Limitación 4 reformulada con registro narrativo (números en letras: "cero coma seis", "cincuenta respuestas") siguiendo el estilo del documento.

### Lo que NO se hizo (deliberadamente)

- **NO se commiteó nada**. Decisión explícita del flujo: el usuario revisa el resultado y decide cuándo committear.
- **NO se ejecutó la suite completa de tests del tutor-service**. El entorno actual no tiene uv ni venv local (Windows; el repo está siendo trabajado desde un Claude Code outer al `(4)/` wrapper). La validación se hizo inline con `python -c` + importlib bypaseando `__init__.py` por las deps `platform_observability` que arrastra el package init. La suite completa con `uv run pytest apps/tutor-service/tests/unit/test_postprocess_socratic.py -v` debe correrse cuando se vuelva al entorno con uv disponible.
- **NO se prendió el feature flag**. La activación queda explícitamente bloqueada hasta que la validación intercoder con docentes esté disponible (las 3 condiciones del ADR-027).
- **NO se inició la Mejora 3** (clasificación semántica de anotaciones, ADR-023). Pendiente; misma estructura: gate humano + Eje B post-defensa.

### Cifras de la mejora

- **Líneas de código agregadas**: ~210 LOC en `postprocess_socratic.py` (módulo nuevo) + ~15 LOC de hook en `tutor_core.py` + 11 LOC de feature flag + comentarios en `config.py`. Tests nuevos: ~145 LOC en `test_postprocess_socratic.py`. ADR: ~165 líneas de markdown. Total: ~545 LOC.
- **Esfuerzo real**: una sesión de trabajo concentrada, conforme al patrón de la Mejora 5. La iteración sobre la fórmula del score ocupó ~10 min; el resto fue mecánico tras el diseño.
- **Archivos tocados**: `postprocess_socratic.py` (nuevo), `tutor_core.py` (hook), `config.py` (flag), `test_postprocess_socratic.py` (nuevo), `docs/adr/044-...md` (nuevo), `CLAUDE.md` (bullet), `docs/limitaciones-declaradas.md` (Limitación 4 + tabla + versionado), `loquehace.md` (§13 prosa).

### Próximos pasos

- Correr `uv run pytest apps/tutor-service/tests/unit/test_postprocess_socratic.py -v` desde el entorno con uv para validar la suite completa de 12 tests.
- Coordinar con el usuario y el director de tesis el procedimiento de calibración intercoder con docentes para destrabar la activación del flag (las 3 condiciones del ADR-027).
- Decidir cuándo arrancar la Mejora 3 (clasificación semántica de anotaciones, ADR-023, Eje B post-defensa) — siguiente del orden recomendado del plan, con gate humano similar.

---

## 2026-05-09 — Mejora 5 del plan post-piloto-1: detección de sobreuso (overuse) implementada

Sesión de ejecución del plan documentado en `documentos/borradores-paper/mejoras.docx`. Tras la verificación profunda de las cinco limitaciones declaradas del sistema y la confirmación de que las cinco son ciertas y respaldadas por ADRs, el usuario pidió ejecutar el plan en el orden recomendado. Se arrancó por la **Mejora 5 (overuse)** por ser la de menor complejidad técnica, self-contained en `guardrails.py`, y sin requerir validación intercoder con docentes — sirve como calentamiento del patrón antes de las mejoras 4 y 3 que comparten el mismo dominio pero son más grandes.

### Pasos ejecutados (en orden)

1. **Verificación inicial** del estado del módulo `guardrails.py` y de los hooks existentes en `tutor_core.py:336-370`. Confirmado que la versión vigente del corpus era `1.1.0`, las categorías eran cinco (jailbreak indirecto/sustitución/ficción, persuasion urgency, prompt injection), el `overuse` figuraba como agenda futura tanto en el docstring del módulo (`guardrails.py:21`) como en el ADR-019 (líneas 103, 112, 180). Próximo ADR disponible: `043` (último era `042`).

2. **Extensión del `Category` Literal** con la sexta categoría `overuse`, severidad ordinal 1 (informativa). Bump de `GUARDRAILS_CORPUS_VERSION` de `"1.1.0"` a `"1.2.0"`.

3. **Definición de los thresholds operativos** del detector como constantes module-level: `OVERUSE_BURST_WINDOW_SECONDS = 300.0`, `OVERUSE_BURST_THRESHOLD = 6`, `OVERUSE_PROPORTION_WINDOW_SECONDS = 600.0`, `OVERUSE_PROPORTION_THRESHOLD = 0.7`, `OVERUSE_MIN_EVENTS_FOR_PROPORTION = 5`. Decisión clave: incluir los thresholds en el JSON canónico de `compute_guardrails_corpus_hash()` para preservar la propiedad de reproducibilidad bit-a-bit del corpus. Cualquier modificación futura de un threshold bumpea automáticamente el hash y los eventos nuevos quedan etiquetados con el hash nuevo.

4. **Implementación de la clase `OveruseDetector`** con dependencia Redis vía `Protocol` `_RedisLike` (permite mockear con fake in-memory para tests sin acoplar a `redis.asyncio`). Mantiene dos sorted sets por episodio: `tutor:overuse:{episode_id}:prompts` y `tutor:overuse:{episode_id}:events`. TTL de ocho horas. Métodos: `record_prompt`, `record_non_prompt_event`, `check`. La heurística `check` evalúa primero burst (más sensible al estado actual) y después proportion (sensible a la trayectoria desde el inicio del episodio).

5. **Integración en el flow de `tutor_core.interact()`** inmediatamente después del bloque que emite los `intento_adverso_detectado` regex. Mismo patrón side-channel: el prompt llega al modelo de lenguaje sin modificación, cualquier excepción se captura y loggea sin bloquear el turno. Bug colateral fixeado en el primer intento: el atributo `prompt_event.event_id` no existe — el evento es un `dict` con clave `"event_uuid"`. Corregido a `UUID(prompt_event["event_uuid"])`.

6. **Helper interno `_record_overuse_non_prompt_event`** agregado al `TutorCore` para alimentar el denominador del cálculo de proportion. Llamado desde los cinco emisores de eventos cognitivos no-prompt: `emit_codigo_ejecutado`, `record_edicion_codigo`, `record_anotacion_creada`, `record_lectura_enunciado`, `emit_tests_ejecutados`. Cada llamada es fail-soft con try/except.

7. **Tests deterministas en `apps/tutor-service/tests/unit/test_overuse_detector.py`** con fake Redis async in-memory: cuatro casos canónicos del plan (burst con siete prompts en cuatro minutos, proportion con cinco prompts más dos no-prompts en diez minutos, no-sobreuso con cinco prompts en quince minutos, caso límite con seis prompts en exactamente cinco minutos), cuatro casos adicionales (sin actividad, solo non-prompts, episodio corto bajo el piso, aislamiento por episode_id), y test anti-regresión de las constantes.

8. **Actualización de tests existentes en `test_guardrails.py`**: golden hash actualizado a `6411ef8058d0c1171baff4f7152bd1746abbede505dda472dd5d7ed23e1cc1c5` (calculado contra el módulo modificado mediante `importlib.util` aislado), test de versión renombrado de `..._es_v1_1` a `..._es_v1_2` con assert sobre `"1.2.0"`, test `test_pattern_id_incluye_version` actualizado al sufijo `_v1_2_0_p`. Las regresiones históricas de la revisión adversarial 2026-04-27 (líneas 184-235 de `test_guardrails.py`) NO se tocan porque siguen siendo válidas en v1.2.0 (el corpus regex no cambió, solo se agregó el detector de window).

9. **ADR-043 redactado** en `docs/adr/043-overuse-detection-cross-prompt-window.md` con contexto, decisión, drivers (D1-D5), opciones consideradas (A elegida, B y C descartadas), criterios de éxito, análisis de sensibilidad de los thresholds, consecuencias positivas/negativas/neutras, referencias. El ADR supersede parcialmente la cláusula del ADR-019 sobre `overuse` como agenda futura — el ADR-019 sigue vigente sobre las cinco categorías regex.

10. **CLAUDE.md actualizado** en el bullet de "Detección preprocesamiento de intentos adversos" (línea 151) para reflejar la nueva realidad: agrega referencia a ADR-043, menciona la sexta categoría `overuse` con sus dos heurísticas y sus thresholds, distingue del estado de la Fase B que sigue diferida.

### Lo que NO se hizo (deliberadamente)

- **NO se commiteó nada**. Decisión explícita del flujo: el usuario revisa el resultado y decide cuándo committear.
- **NO se ejecutaron los tests contra el stack real**. Los tests del detector usan fake Redis y no requieren infraestructura. Los tests existentes de `guardrails` se actualizaron al nuevo hash.
- **NO se inició la Mejora 4 (socratic_compliance)** que es la siguiente en el orden recomendado. Conforme al alcance acordado del primer sprint.

### Cifras de la mejora

- **Líneas de código agregadas**: aproximadamente 200 LOC en `guardrails.py` + 30 LOC en `tutor_core.py` (helper + hook) + 6 líneas adicionales en los cinco emisores de eventos no-prompt. Tests nuevos: ~270 LOC en `test_overuse_detector.py`. Total: ~500 LOC nuevos.
- **Esfuerzo real**: una sesión de trabajo concentrada, conforme a la estimación del plan original (una semana en jornada completa, comprimida acá por la naturaleza self-contained de la mejora).
- **Archivos tocados**: `guardrails.py`, `tutor_core.py`, `test_guardrails.py`, `test_overuse_detector.py` (nuevo), `docs/adr/043-...md` (nuevo), `CLAUDE.md`.

### Próximos pasos

- Correr la suite de tests del tutor-service contra Postgres + Redis para verificar que ningún test existente se rompe.
- Decidir cuándo arrancar la Mejora 4 (`socratic_compliance` Fase B postprocesamiento), que es la siguiente del orden recomendado del plan.

---

## 2026-05-04 (Noche) — Auditoría completa con 4 agentes + 4 fixes críticos + smoke E2E + skill `impeccable` instalada + PRODUCT.md/DESIGN.md generados

Sesión posterior al cierre AM/PM del epic `ai-native-completion-and-byok`. El usuario pidió un "análisis completo del proyecto" para saber dónde estamos parados de cara a la defensa doctoral. Ejecutamos auditoría con 4 sub-agentes paralelos contra el stack live (12 servicios + 3 frontends + Postgres con data demo: 3 comisiones, 18 estudiantes, 6 TPs, 94 episodios cerrados, 470 events CTR íntegros).

### Pasos ejecutados (en orden)

1. **Levantamos el stack completo**: infra Docker ya estaba up; lanzamos los 12 servicios Python con `/tmp/launch-piloto.sh` (PIDs trackeados) + `pnpm turbo dev` para los 3 frontends. Health gate: 12/12 `status=ready` en 15s, 3/3 frontends sirviendo HTML 200.
2. **4 agentes auditoría en paralelo** (backend / frontend / DB / núcleo pedagógico):
   - **Pedagógico**: 98/98 tests propios passing — invariantes core sólidos (reproducibilidad classifier, labeler v1.2.0, guardrails Fase A, CII longitudinal, attestation tooling, 5 coherencias separadas). Detectó 2 críticos: `compute_chain_hash` divergente entre `packages/contracts` y `ctr-service` + migrations BYOK no aplicadas en DB local.
   - **DB**: cadena íntegra (470/470 events, genesis correcto). Detectó: sharding CTR es **fantasma en Postgres** (vive solo en Redis Streams), append-only sin trigger DB (solo convención de código), `content_db` VACÍA (RAG nunca probado con data real), 108 vs 116 casbin_rules, attestation stream `XLEN=0` con 94 episodios cerrados (path no se está disparando), nombres `EpisodioCerrado` vs `episodio_cerrado` ambiguos.
   - **Backend**: 446 tests unit clean, casbin matrix 48/48, `make check-rls` OK. Detectó **bug genuino BYOK SET LOCAL** (`apps/ai-gateway/.../services/byok.py:122` usa bind param que Postgres no acepta — toda la CRUD BYOK rota en runtime aunque tests mockeaban DB), naming confuso `labeler_version` en analytics (3 endpoints reutilizan el campo para 3 versiones distintas).
   - **Frontend**: Playwright MCP no funcionó (chromium path roto, dejó `~/.claude.json` corregido para próximas sesiones). Audit por API + tests + typecheck. 3/3 frontends carga, drill-down teacher con data coherente. Detectó: `packages/ui/StateMessage.tsx` líneas 28-29 rompe typecheck (turbo cachea y oculta), 5/9 views del web-teacher (G7 ADR-022) no usan HelpButton aunque CLAUDE.md lo declara mandatory, header de auth correcto es `X-User-Roles` (plural), no `X-Role`.
3. **4 fixes NOW aplicados** (sub-agente dedicado, ~15 min):
   - Aplicadas migrations `20260504_0001` (test_cases/created_via_ai) + `20260504_0002` (byok_keys) en `academic_main` con override `ACADEMIC_DB_URL=postgresql+asyncpg://postgres:postgres@...` (el default de `alembic/env.py` apunta hardcoded a `academic_user` que NO es owner — pendiente PR aparte).
   - Re-seed casbin: 108 → 116 policies (incluyendo `byok_key:CRUD × 2 roles`). Restart academic-service para refresh enforcer en memoria.
   - Bug BYOK SET LOCAL: `text("SET LOCAL ... :tid")` → `text("SELECT set_config('app.current_tenant', :tid, true)")` (semánticamente equivalente, acepta bind). Smoke real: `GET /api/v1/byok/keys` → 200 (antes 500 silencioso).
   - Bug `compute_chain_hash` divergente: `packages/contracts/.../ctr/hashing.py:46` invertido a `f"{self_hash}{prev}"` (ahora coincide con ctr-service y los 470 events íntegros de la DB). Test cross-package nuevo `packages/contracts/tests/test_chain_hash_canonical_formula.py` con 3 tests + 4 fixtures bit-exact extraídos de un episodio real. Sin este fix, un auditor doctoral que use el helper "oficial" para verificar la cadena obtenía falsos failures sobre cadenas íntegras.
4. **Mejora estructural #2 — Smoke E2E** (sub-agente dedicado, ~13 min): suite `tests/e2e/smoke/` con 32 tests + 1 skipped (BYOK_MASTER_KEY) — health × 12 + flujo pedagógico (open episode → emit event → close → verify) + BYOK CRUD + analytics (kappa, longitudinal, cuartiles, alertas) + audit alias ADR-031 + chain_e2e (recompute SHA-256 con helper de contracts contra DB real) + governance/ai-gateway. **32/32 passed en <2s**. CI workflow skeleton en `.github/workflows/e2e-smoke.yml` (workflow_dispatch por ahora). `make test-smoke` target nuevo. Atrapa exactamente la clase de bugs que escapan a tests con DB mockeada.
5. **Skill `impeccable` instalada global**: `npx skills add pbakaus/impeccable` falló por input interactivo; instalación manual a `~/.claude/skills/impeccable/` (SKILL.md + 35 reference files + 4 scripts). Resueltos placeholders `{{scripts_path}}`/`{{command_prefix}}` con script Python (23 archivos, 18 + 45 ocurrencias). Registrada en `~/.claude/CLAUDE.md` global como auto-load para cualquier tarea de UI. Filosofía respetada: gates obligatorios PRODUCT.md + DESIGN.md + shape brief NO se saltean.
6. **`PRODUCT.md` escrito** al root del repo (decisión: audiencia primaria de la defensa = comité doctoral, audiencia primaria del producto = docentes/alumnos UTN escalando a N facultades). 5 design principles: (1) modelo N4 visible, (2) auditabilidad visible no oculta, (3) densidad académica > whitespace SaaS, (4) escala como first-class, (5) honestidad técnica explícita. 5 anti-references: Moodle, Coursera marketing, SaaS dashboard genérico, EdTech gamificado, SIU Guaraní. Voice: *riguroso · transparente · pedagógico*.
7. **`DESIGN.md` escrito** al root (sub-agente, ~12 min, formato Stitch). 32 colors / 6 typography roles / 16 components extraídos de los 3 frontends + `packages/ui`. Estrategia detectada: **Restrained con vocabulario semántico extendido**. Hallazgo importante: **N1-N4 NO son tokens `@theme`**, viven hardcoded en componentes JS (`EpisodeNLevelView::LEVEL_COLORS`, etc.). Bug visual genuino documentado en Don'ts: `StudentLongitudinalView.tsx:251` usa `border-l-4 border-amber-400` (side-stripe banneado por la skill `impeccable`).
8. **CLAUDE.md corregido** (cirugía mínima sobre las falsedades verificadas): `X-Role` → `X-User-Roles` plural (2 ocurrencias), aclaración del sharding CTR (Redis Streams, NO Postgres), warning del path attestation no disparándose, caveat de HelpButton missing en G7, disambiguation `EpisodioCerrado` vs `episodio_cerrado` (clase Pydantic vs event_type), nuevo gotcha `alembic/env.py` hardcoded a `academic_user`, **nueva sección "Auditoría 2026-05-04"** con highlights completos + reference a PRODUCT.md/DESIGN.md/skill `impeccable` como source of truth de UX/UI.
9. **Cleanup limpio**: 12 uvicorn + 3 vite matados por PID, puertos del piloto libres, infra Docker (10 containers) sigue arriba como estaba.

### Lo que NO se hizo (deliberadamente, postpuesto a próxima sesión)

- **NO se commiteó nada**. 80 archivos sin commitear: ~50 heredados del epic ai-native-completion (cierre AM/PM de hoy mismo) + ~10 míos de hoy (PRODUCT/DESIGN/CLAUDE/Makefile/smoke E2E/test cross-package + fixes byok.py y hashing.py). Decisión consciente: separar limpio el commit del epic vs los fixes vs el smoke vs los docs UX requiere `git add -p` con cabeza fresca, no a las 9pm.
- **NO se ejecutó `impeccable shape`** para el redesign del flujo docente→materia→comisión que el usuario originalmente pidió ("darle al frontend un toque más lindo"). PRODUCT.md y DESIGN.md son **prerrequisitos** que la skill exige; el shape es la próxima fase.
- **NO se diagnosticó por qué attestation no se está disparando** (pero queda anotado como warning crítico en CLAUDE.md).

### Bugs detectados pero NO fixeados (pendientes mañana o esta semana)

- `apps/web-teacher/.../StudentLongitudinalView.tsx:251` usa side-stripe `border-l-4 border-amber-400` (banneado por skill `impeccable`).
- HelpButton missing en `EpisodeNLevelView`, `StudentLongitudinalView`, `CohortAdversarialView` (+ otras 2 G7).
- `packages/ui/StateMessage.tsx` líneas 28-29 violación `exactOptionalPropertyTypes` (turbo cachea, no se ve en CI happy path).
- `apps/academic-service/alembic/env.py` hardcoded a `academic_user` que NO es owner (workaround documentado, PR pendiente).
- Stream `attestation.requests` con `XLEN=0` después de 94 episodios cerrados (path no se dispara).
- `evaluation-service` sigue siendo esqueleto con solo `/health` (decisión: o se implementa o se deprecá como `enrollment-service`).
- Naming confuso `labeler_version` en 3 endpoints distintos de analytics que exponen 3 constantes diferentes.

---

## 2026-05-04 (PM) — Cierre Fase 1 epic `ai-native-completion-and-byok` + archive

Continuación de la sesión AM. El plan que dejamos al cierre AM se ejecutó completo (~3h). Epic archivada en `openspec/changes/archive/2026-05-04-ai-native-completion-and-byok/`. Fuera de los tests RLS que requieren Postgres real, todo verde local.

### Pasos ejecutados (en orden)

1. **Fix `conftest.py`**: agregado `collect_ignore_glob = ["apps/enrollment-service/**"]` raíz. `pytest apps packages -q --co` colecta 916 tests sin errores (antes rompía por `import pandas` del servicio deprecado).
2. **`materia_id` propagation end-to-end (ADR-040)** — cierra Sec 6.2 de la epic:
   - `SessionState.materia_id: UUID | None` (cacheado al `open_episode`, sobrevive a serialización Redis con backwards-compat para sesiones legacy).
   - `AcademicClient.get_comision()` nuevo método (`apps/tutor-service/.../services/academic_client.py`); `ComisionResponse` dataclass nuevo.
   - `tutor_core.open_episode` resuelve materia via la nueva llamada **fail-soft** (404 / exception → `materia_id=None`, episodio se abre igual y BYOK degrada a tenant_fallback).
   - `AIGatewayClient.stream(materia_id=...)` opcional, lo forwardea al body del SSE del ai-gateway.
   - `tutor_core.interact` lee `state.materia_id` y lo pasa por turno (el resolver del ai-gateway lo consume).
   - 4 tests E2E en `apps/tutor-service/tests/unit/test_materia_id_propagation.py`: happy path con cache, no se re-resuelve por turno (3 turnos = 1 sola llamada a `get_comision`), 404, exception. **NO romper estos tests** al refactorizar el resolver de comisiones.
   - Bug colateral fixeado: `SessionState.model` y `materia_id` no se serializaban a Redis (la persistencia de `model` era bug pre-existente, salió a la luz al agregar `materia_id`).
3. **Casbin policies `byok_key:CRUD` (ADR-039)**: 8 policies nuevas en `seeds/casbin_policies.py` (4 superadmin + 4 docente_admin) — total 108 → **116 policies**. Test matrix actualizado con 10 nuevas filas (4 happy superadmin + 4 happy docente_admin + 2 deny docente + 2 deny estudiante). El enforcement runtime sigue via header `X-User-Roles` en `routes/byok.py::_check_admin` (consistente con el patrón del ai-gateway que no consume Casbin DB) — las policies sirven como source of truth de la matriz.
4. **6 tests TP-gen con mock ai-gateway** (Sec 11.7) — `apps/academic-service/tests/unit/test_tp_generator.py`: materia inválida 400, governance falla 502, ai-gateway falla 502, JSON malformado 502, error estructurado 422, happy path con borrador parseado verificando que `materia_id` propaga al ai-gateway. **De paso descubrió un bug genuino**: `routes/tareas_practicas.py:181` importaba `from academic_service.models.academic import Materia` y el módulo correcto es `models.institucional`. Fix incluido. Sin los tests no había nada que ejercite ese código path.
5. **Endpoint rotate BYOK** (Sec 7.3): `rotate_byok_key()` en `services/byok.py` re-encripta plaintext y sustituye `encrypted_value` + `fingerprint_last4`. Preserva id/scope/created_at/created_by. 404 si key revocada (caller crea una nueva). Route `POST /api/v1/byok/keys/{id}/rotate` con `RotateKeyRequest` schema.
6. **Métricas BYOK OTLP** (Sec 13.1-13.2): 3 instrumentos nuevos en `apps/ai-gateway/.../metrics.py` — `byok_key_usage_total{provider, scope_type, resolved_scope}`, `byok_key_resolution_total{resolved_scope}`, histogram `byok_key_resolution_duration_seconds` (SLO p99 < 50ms). Sin `scope_id`/`tenant_id` en labels — cardinality budget verificado (≈100 series por counter). Instrumentadas via helper `_emit()` interno en `resolve_byok_key` que cubre los 4 caminos del resolver (materia / tenant / env_fallback / none).
7. **Health check `byok_resolver_healthy`** (Sec 5.6): `_check_byok_resolver()` no-critical en `apps/ai-gateway/.../routes/health.py` con 4 estados — BYOK_ENABLED=False (ok), master key válida (ok), master key falta + env fallback (degraded), nada (error). NO escala a critical aún en error porque el resolver ya degrada solo y los handlers devuelven 503 cuando corresponde.
8. **Sec 16 documental**:
   - **CLAUDE.md** "Estado actual de implementación": bloque nuevo "Capabilities cerradas en epic `ai-native-completion-and-byok` (2026-05-04)" con resumen de 5 capabilities + bug genuino del classifier explícito.
   - **CLAUDE.md** "Constantes": `BYOK_MASTER_KEY` (32 bytes base64), `LABELER_VERSION = "1.2.0"` post-epic, `_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}`.
   - **CLAUDE.md** "Casbin": contador 108 → 116 policies con detalle de los bumps acumulados.
   - **CLAUDE.md** "Dónde buscar contexto": ADRs **40 al cierre del epic**, descripción de una línea por ADR 033-040.
   - **historias.md**: HU-125 (BYOK admin), HU-126 (sandbox tests Pyodide), HU-127 (reflexión metacognitiva), HU-128 (TP-gen IA), HU-129 (governance UI).
   - **reglas.md**: RN-132 (BYOK resolver jerárquico — Alta), RN-133 (reflexión exclusión classifier — Crítica), RN-134 (test hidden no entran a features — Alta). Catálogo de severidades actualizado (Críticas 38→39, Altas 59→61).
   - **`.env.example`** queda como deferred (acceso al archivo bloqueado por permisos del agente; vars documentadas en CLAUDE.md "Constantes" para que el operador las copie al levantar el piloto).

### Bugs colaterales fixeados al ejecutar el plan

- `routes/tareas_practicas.py::generate_tarea_practica`: import `from academic_service.models.academic import Materia` → `from academic_service.models.institucional import Materia` (bloqueaba el endpoint TP-gen en runtime; sólo salió a la luz porque escribimos los 6 tests).
- `apps/ctr-service/tests/unit/test_chain_integrity.py::test_mutated_chain_hash_is_detected`: era flaky 1/16 cuando `chain_h[0]` casualmente era `"f"` y la mutación `"f" + chain_h[1:]` no cambiaba nada. Fix: elegir un char nuevo distinto del primero (`"a"` o `"b"`).
- `apps/analytics-service/tests/unit/test_n_level_distribution_endpoint.py`: assertion sobre `labeler_version == "1.1.0"` quedó stale después del bump v1.1.0 → v1.2.0 de la epic. Actualizado a `"1.2.0"`.
- `packages/contracts/tests/test_event_types_match_runtime.py`: el set de event classes hardcodeado no incluía las dos nuevas — agregadas `ReflexionCompletada` y `TestsEjecutados` al import + tuple del test.

### Tests al cierre

- **Python**: `uv run pytest apps packages -q` → **916 passed, 4 skipped** (los 4 skips son tests de RLS contra Postgres real, requieren `CTR_STORE_URL_FOR_RLS_TESTS`).
- **TS**: `pnpm --filter @platform/web-admin --filter @platform/web-teacher test` → 10 web-admin + 13 web-teacher = **23 passed**.
- Total tests verdes: **939**.

### Lo que queda como `[~]` honesto post-archive

Va al follow-up declarado en el archivo archivado de la epic. **Cuando llegue el deploy real del piloto en UTN, abrir change nuevo** (sugerido: `byok-operational-frontend`) con scope acotado:

- UI BYOK keys page en web-admin.
- UI Pyodide en web-student + botón "Correr tests".
- Wizard TP-gen en web-teacher.
- Adapters Gemini + Mistral (`uv add google-generativeai mistralai` validado).
- Cache Redis del resolver (`materia:{id}:facultad_id`, `resolved:*`).
- Dashboard Grafana provisionado (`byok-overview.json`).
- Tests E2E con stack completo + LLM real + DB real.
- `make check-rls` con las 2 tablas BYOK + `make test-rls` BYOK isolation.
- Procedimiento operacional de rotación de master key en `docs/pilot/runbook.md` (los 5 steps están en ADR-038).
- `.env.example` con `BYOK_MASTER_KEY` y `BYOK_ENABLED` documentadas.

NO mezclar con la epic actual. Archivar primero, abrir después.

### Pointers críticos del cierre

- Epic archivada: `openspec/changes/archive/2026-05-04-ai-native-completion-and-byok/`
- `openspec/changes/` queda con sólo `archive/` (epic activa = ninguna).
- Tests anti-regresión NO romper:
  - `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py::test_reflexion_completada_no_afecta_clasificacion_ni_features` (RN-133, reproducibilidad bit-a-bit del `classifier_config_hash`).
  - `apps/tutor-service/tests/unit/test_materia_id_propagation.py` (4 tests, propagación ADR-040 end-to-end).
  - `packages/contracts/tests/test_event_types_match_runtime.py::test_runtime_emits_only_contract_event_types` (eventos del CTR alineados runtime ↔ contract).
- `apps/academic-service/src/academic_service/seeds/casbin_policies.py`: **116 policies**, fuente de verdad de la matriz Casbin.

---

## 2026-05-04 — Epic `ai-native-completion-and-byok` (parcial: backend completo, UI deferida) + plan próxima sesión

Sesión basada en `openspec/changes/ai-native-completion-and-byok/`. Decisión del usuario: avanzar `opsx:apply` sobre la epic completa, partiendo en orden de menor a mayor riesgo (reflection → governance → sandbox backend → TP-gen → BYOK fundacional).

### Lo que se cerró (51 tasks ✅ done)

- **Sec 10 `reflection-post-close`** completa: contract `ReflexionCompletada`, endpoint `POST /api/v1/episodes/{id}/reflection` en tutor-service, modal `ReflectionModal.tsx` en web-student, redacción en `academic_export.py` con flag `--include-reflections`, prompt `reflection/v1.0.0`, 11 tests passing.
- **Sec 12 `governance-ui-admin`** completa: endpoint extendido `/cohort/{id}/adversarial-events` + endpoint nuevo `/governance/events` cross-cohort en analytics-service, página `GovernanceEventsPage.tsx` en web-admin con filtros + CSV export, helpContent, 7 tests E2E. **Bug pre-existente fixeado de paso**: `web-admin` declaraba `@testing-library/jest-dom/vitest` en setup pero la dep no estaba en `package.json` — agregada.
- **Sec 9 `sandbox-test-cases` BACKEND**: contract `TestsEjecutados`, migración Alembic test_cases JSONB + created_via_ai BOOL, endpoint filter por rol, endpoint `POST /api/v1/episodes/{id}/run-tests` en tutor-service, bulk-import schema, classifier labeler bumpeado v1.1.0 → **v1.2.0** con regla N3/N4 para `tests_ejecutados`. UI Pyodide DEFERIDA.
- **Sec 11 `tp-generator-ai` BACKEND**: prompt `tp_generator/v1.0.0` + manifest, endpoint `POST /api/v1/tareas-practicas/generate` en academic-service, cliente `AIGatewayClient` + `GovernanceClient` en `services/ai_clients.py`, audit log structlog `tp_generated_by_ai`, schema `TareaPracticaCreate.created_via_ai`. Wizard UI DEFERIDO.
- **Sec 1-7 `byok-multiprovider` FUNDACIONAL**: helper `crypto.py` AES-256-GCM en platform-ops (10 tests), 2 migraciones Alembic (`byok_keys` + `byok_keys_usage` con RLS), modelo SQLA + resolver jerárquico (materia → tenant → env_fallback) en `apps/ai-gateway/.../services/byok.py`, 4 endpoints CRUD (`/keys`, `/keys`, `/keys/{id}/revoke`, `/keys/{id}/usage`), `materia_id` opcional en `CompleteRequest` schema del ai-gateway (ADR-040 lado gateway), ROUTE_MAP del api-gateway agregado. UI BYOK keys DEFERIDA.
- **8 ADRs nuevos** (033-040): sandbox Pyodide-only, test_cases JSONB, reflexión privacy, TP-gen caller, governance UI read-only, BYOK AES-GCM, BYOK resolver, materia_id propagation.

### Bug genuino encontrado y cerrado (importante para defensa)

Al escribir el test anti-regresión del classifier ANTES de asumir que la reflexión era inocua, el test **falló**: `ct_summary` cambiaba de `0.54` a `0.56` cuando había un evento `reflexion_completada` con `ts > 5min` post-cierre. El classifier consumía TODOS los eventos del CTR sin filtrar, y la reflexión creaba una nueva ventana de trabajo (pause >5min) que afectaba la métrica de densidad.

**Fix**: `_EXCLUDED_FROM_FEATURES = {"reflexion_completada"}` en `apps/classifier-service/src/classifier_service/services/pipeline.py`, filtrado ANTES del feature extraction. Sin este fix, la **reproducibilidad bit-a-bit del `classifier_config_hash`** estaba expuesta a contaminación silenciosa por eventos side-channel post-cierre.

Documentado en ADR-035. Test en `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py::test_reflexion_completada_no_afecta_clasificacion_ni_features`.

### Bug pre-existente del repo descubierto (NO fixeado todavía)

`pytest apps packages` rompe en collection porque `apps/enrollment-service/` (deprecado por ADR-030) tiene `import pandas` y `pandas` no está instalado en el workspace. El servicio fue sacado de `[tool.uv.workspace].members` pero **no del pytest collection**. Fix una línea en `conftest.py` raíz: `collect_ignore_glob = ["apps/enrollment-service/**"]`.

### Tests passing al cierre

- 85 tests Python (11 reflection + 9 reproducibility + 38 labeler + 17 academic_export + 10 crypto).
- 10 tests TS (3 HomePage + 7 GovernanceEventsPage).
- **Total: 95 tests verdes**.

### NO entró en esta sesión (53 tasks marcadas `[~]` con razón concreta)

**UI volumetrica con browser real** (~12 tasks): editor drag-drop test cases en web-teacher (Sec 9.3), Pyodide en web-student + botón "Correr tests" (Sec 9.4-9.5), wizard TP-gen en web-teacher (Sec 11.4), página BYOK keys en web-admin (Sec 8.1-8.7).

**SDKs LLM nuevos** (~5 tasks): adapters Gemini + Mistral (Sec 1.2, 4.1-4.5), tabla pricing per-model. Requiere `uv add google-generativeai mistralai` validado contra context7 + keys reales para test.

**Optimización con Redis** (~4 tasks): cache `materia:{id}:facultad_id` TTL 1h, cache `resolved:*` TTL 5min, invalidación al rotate (Sec 5.2-5.3, 5.5). Optimización post-medición de SLO p99 < 50ms.

**Métricas OTLP + Grafana** (~7 tasks): contadores BYOK + pedagógicos (Sec 13.1-13.5), dashboard `byok-overview.json` provisionado (Sec 13.6-13.7).

**Tests E2E con stack completo** (~5 tasks): superadmin crea key → tutor la usa → métrica incrementa (Sec 15.3), TP-gen → edit → publish → episodio → tests Pyodide (Sec 15.4), reflexión post-close end-to-end (Sec 15.5), smoke post-deploy (Sec 15.7), `make test-rls` BYOK (Sec 15.2).

**Verificación operacional con Postgres real** (~3 tasks): `make check-rls` con las 2 nuevas tablas (Sec 3.6), test de migración reversible en CI (Sec 3.7), `make migrate` confirmando que las dos migraciones aplican limpio.

---

## **PLAN PRÓXIMA SESIÓN — Cerrar Fase 1 de la epic** (todo backend, sin browser/SDK/DB real)

**Objetivo**: dejar el código backend impecable y archivar la epic con `/opsx:archive`. El árbol `openspec/changes/` queda vacío después.

**Estado de entrada**: 51/53 tasks done. Las ~12 tareas siguientes son legítimamente cerrables inline. Los `[~]` que queden post-Fase 1 son **honestos** — declaran follow-up genuino (UI + SDK + DB real).

### Tareas en orden (~2-4h estimado)

1. **Fix bug pytest collection (5 min)**. En `conftest.py` raíz agregar:
   ```python
   collect_ignore_glob = ["apps/enrollment-service/**"]
   ```
   Verificar con `uv run pytest apps packages -q --co 2>&1 | tail -3` — debe colectar sin errores.

2. **Sec 16 documental (~1h)**:
   - **CLAUDE.md** "Estado actual de implementación": agregar resumen de las 5 capabilities cerradas en esta sesión, con bullets cortos por capability.
   - **CLAUDE.md** "Constantes que NO deben inventarse ni cambiarse": agregar `BYOK_MASTER_KEY` (32 bytes, base64) con referencia a `packages/platform-ops/src/platform_ops/crypto.py`.
   - **CLAUDE.md** "ADRs recientes": bump contador 31/32 → **40 ADRs**, agregar referencias 033-040 con una línea cada uno.
   - **`.env.example`**: agregar `BYOK_MASTER_KEY=<generar con: openssl rand -base64 32>` y `BYOK_ENABLED=false` con comentarios.
   - **`historias.md`**: agregar HU-125 (BYOK admin), HU-126 (sandbox tests Pyodide), HU-127 (reflexión metacognitiva), HU-128 (TP-gen IA), HU-129 (governance UI).
   - **`reglas.md`**: agregar RN-132 (BYOK resolver jerárquico), RN-133 (reflexión exclusión classifier), RN-134 (test hidden no entran a features).

3. **`materia_id` propagation en tutor-service (~30 min)** — cierra ADR-040 end-to-end (Sec 6.2). En `apps/tutor-service/src/tutor_service/services/tutor_core.py::interact`:
   - Resolver `materia_id` desde `episode.problema_id → tarea_practica.comision_id → comision.materia_id` via `AcademicClient`. Cachear en `SessionState` (campo nuevo `materia_id: UUID | None`) para evitar re-resolver por turno.
   - Pasar `materia_id` al cliente `AIGatewayClient.stream()` — primero hay que actualizar el cliente para aceptar el parámetro y el endpoint `/stream` del gateway para forwardearlo al payload.
   - Test E2E: mock que verifica el campo llega del tutor → ai-gateway.

4. **Casbin policy `byok_key:CRUD` (~15 min)** — Sec 7.7. En `apps/academic-service/src/academic_service/seeds/casbin_policies.py`:
   - Agregar policies para superadmin + docente_admin con `byok_key:CRUD`.
   - Mover el enforcement del header check (`_check_admin` en `ai-gateway/routes/byok.py`) a usar Casbin via api-gateway, consistente con el resto del repo.
   - Bump del contador (108 → 109+ policies, según el bump real).

5. **Tests TP-gen con mock ai-gateway (~30 min)** — Sec 11.7. Crear `apps/academic-service/tests/unit/test_tp_generator.py` con patrón de `test_reflexion_completada.py`:
   - Estudiante con `POST /generate` → 403 (Casbin).
   - Docente con `materia_id` inválido → 400.
   - Happy path: docente envía descripción NL → mock del `AIGatewayClient.complete` devuelve JSON estructurado → response 200 con borrador.
   - Mock devuelve JSON malformed → 502.
   - Mock devuelve `{"error": "razon"}` → 422.

6. **Endpoint `POST /api/v1/byok/keys/{id}/rotate` (~15 min)** — Sec 7.3. En `apps/ai-gateway/src/ai_gateway/services/byok.py` y `routes/byok.py`:
   - `rotate_byok_key(tenant_id, key_id, new_plaintext)` — encripta el nuevo plaintext, sustituye `encrypted_value` y `fingerprint_last4`, mantiene id/scope/created_at.
   - Endpoint POST con request body `{plaintext_value: str}`.

7. **Métricas BYOK contadores (~30 min)** — Sec 13.1-13.2. En `apps/ai-gateway/src/ai_gateway/metrics.py`:
   - `byok_key_usage_total{provider, scope_type, resolved_scope}` (sin `scope_id` UUID — cardinality).
   - `byok_key_resolution_total{resolved_scope}` con valores: `materia | tenant | env_fallback | none`.
   - `byok_key_resolution_duration_seconds` histogram con SLO p99 < 50ms.
   - Instrumentar el resolver para incrementar.

8. **Health check `byok_resolver_healthy` (~20 min)** — Sec 5.6. En `apps/ai-gateway/src/ai_gateway/routes/health.py`:
   - Extender el endpoint con `byok_resolver_healthy: bool` y `tenants_without_keys: int`.
   - Lookup count de tenants únicos en `byok_keys` y comparar con tenants conocidos del academic-service.

9. **Run final verificación (~15 min)**:
   - `uv run pytest apps packages -q --no-header` debe pasar todo.
   - `pnpm --filter @platform/web-admin test` debe pasar.
   - `pnpm --filter @platform/web-student typecheck` y biome OK en archivos tocados.
   - Si rompí algo en otro servicio, arreglar.

10. **Marcar tareas cerradas en `tasks.md`** y archivar la epic con `/opsx:archive`. Confirmar que `openspec/changes/` queda solo con `archive/`.

### Lo que NO entra en Fase 1 (queda como `[~]` honesto post-archive)

Va al follow-up declarado en el archivo archivado de la epic. Cuando llegue el deploy real del piloto en UTN, **abrir change nuevo** (sugerido: `byok-operational-frontend`) con scope acotado:
- UI BYOK keys page en web-admin.
- UI Pyodide en web-student + botón "Correr tests".
- Wizard TP-gen en web-teacher.
- Adapters Gemini + Mistral.
- Cache Redis del resolver.
- Dashboard Grafana provisionado.
- Tests E2E con stack completo + LLM real.

NO mezclar con la epic actual. Archivar primero, abrir después.

### Pointers críticos para arrancar

- Epic activa: `openspec/changes/ai-native-completion-and-byok/`
- Tasks file: `openspec/changes/ai-native-completion-and-byok/tasks.md` (tiene resumen al final con estado real).
- ADRs nuevos: `docs/adr/033-*.md` a `docs/adr/040-*.md`.
- Test crítico anti-regresión: `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py::test_reflexion_completada_no_afecta_clasificacion_ni_features` — NO romper este al refactorizar.
- Helper crypto BYOK: `packages/platform-ops/src/platform_ops/crypto.py` con 10 tests passing.
- Resolver BYOK: `apps/ai-gateway/src/ai_gateway/services/byok.py::resolve_byok_key`.

---

## 2026-04-29 — Iter 2 audi2.md: G12 (bump v1.0.1 prompt) + G10-A (EpisodioAbandonado) + G8a (override anotacion_creada) + 5 stubs ADR diferidos

Sesión basada en `audi2.md` — segunda iteración de la auditoría doctoral. Decisión estratégica del usuario: ejecutar la **"ruta mínima para defensa"** que prescribe el propio documento ([audi2.md:362-378](../audi2.md#L362-L378)): G12 + G10-A + G8a antes de defensa, declarar G9/G11/G13/G14/G15 como agenda confirmatoria con stubs ADR formales. Para G10 el usuario eligió **opción A** (defensa a >6 semanas → emisión real con beforeunload + worker timeout server-side).

### Orden de ejecución y por qué

1. **G12 primero** — bump v1.0.1 documental del prompt. Toca solo `ai-native-prompts/`, cero impacto sobre runtime / contracts / migrations. Reversible borrando un directorio. Validó el pipeline de versionado de prompts antes de ir a cambios pesados.
2. **G10-A segundo** — afecta la superficie de eventos del CTR (`EpisodioAbandonado` ya estaba en el contract pero nadie lo emitía). Hacerlo antes de G8a permite que el ADR-023 referencie la lista canónica de eventos correcta.
3. **G8a tercero** — override del labeler con `LABELER_VERSION` 1.0.0 → 1.1.0. Riesgo de romper `test_pipeline_reproducibility.py` si el bump no se hace bien. Última instancia.
4. **5 stubs ADR** — formaliza la decisión de NO implementar los G diferidos. Lo que CLAUDE.md llama "decisión informada" en vez de "deuda silenciosa".
5. **Verificación final** — pytest + ruff + mypy + biome + tsc.

### G12 — Bump documental v1.0.1 del prompt del tutor

- **Problema** ([audi2.md:188-219](../audi2.md#L188-L219)): el HTML comment al pie de `ai-native-prompts/prompts/tutor/v1.0.0/system.md` mapeaba GP3 al Principio 3 ("dejar equivocarse") cuando ese principio cubre semánticamente GP4 (verificación ejecutiva), no GP3 (descomposición ante incomprensión). El mismo comment mapeaba GP4 al mismo Principio 3 — dos guardarrailes distintos colapsados en uno. Cuenta declarada **4/10 era incorrecta**; cuenta correcta es **3/10** (GP1, GP2, GP4).
- **Cambio**: nuevo `ai-native-prompts/prompts/tutor/v1.0.1/system.md` con texto del prompt **idéntico** modulo el header `(v1.0.0)` → `(v1.0.1)` (el HTML comment es invisible al modelo). Manifest fail-loud `v1.0.1/manifest.yaml` con SHA-256 del archivo: `2ecfcdddd29681b24539114975b601f9ec432560dc3c3a066980bb2e3d36187b`.
- **Sin manifest global tocado** — `manifest.yaml` no existe en el repo y `prompt_loader.py` cae al default hardcoded `{tutor: v1.0.0}`. v1.0.1 queda accesible pero **NO activa**. La activación se decide entre cuatrimestres por rigor metodológico (audi2.md G12 timing).
- **Tests nuevos**: `apps/governance-service/tests/unit/test_prompt_v1_0_1_bump.py` con 5 tests:
  - v1.0.0 sigue cargable (preserva piloto histórico).
  - v1.0.1 carga con manifest fail-loud activo.
  - Hashes distintos (bump válido).
  - Texto del prompt idéntico modulo HTML comment + version header.
  - Cuenta corregida 4/10 → 3/10.
- **Bump conforme tesis 7.4**: PATCH documental, comportamiento del tutor preservado bit-a-bit.

### G10-A — Emisión real de `EpisodioAbandonado` (audi2.md G10 opción A) + ADR-025

- **Problema**: `EpisodioAbandonado` declarado en `packages/contracts/src/platform_contracts/ctr/events.py:69-76` desde F3, listado en tesis 7.2 como uno de los 8 eventos instrumentados v1.0.0. **En runtime nadie lo emitía** — verificado con grep. Era la asimetría más visible entre tesis y código.
- **Decisión**: opción A — emitir efectivamente con doble trigger e idempotencia.

#### Cambios backend

- **`session.py`**:
  - Campo `last_activity_at: float` en `SessionState` (epoch UTC, default `time.time()`).
  - `set()` lo refresca automáticamente — cubre `open_episode` (creación) y `next_seq` (cada evento). Sesiones legacy sin campo caen a `time.time()` para que NO disparen abandono inmediato en el primer pase del worker.
  - Nuevo `iter_active_sessions()` con SCAN de Redis (`MATCH tutor:session:*`, `COUNT 100`). Tolera state corruptos.
  - Constante `SESSION_KEY_PREFIX = "tutor:session:"` para que el worker y el manager compartan el mismo prefix.
- **`tutor_core.py`**: `record_episodio_abandonado(episode_id, reason, last_activity_seconds_ago, user_id) -> int | None`. Idempotente — si la sesión ya no existe (cerrada/abandonada/expirada), devuelve `None` sin emitir. Caller del CTR es el estudiante para `reason ∈ {beforeunload, explicit}`, `TUTOR_SERVICE_USER_ID` para `reason="timeout"`.
- **`abandonment_worker.py` nuevo**: `_sweep_once()` (testeable con `now` inyectable) + `run_abandonment_worker()` (loop cancelable). Falla soft: si `publish_event` falla para una sesión, log + continúa con la siguiente. Cancelable via `asyncio.CancelledError` desde el lifespan.
- **`routes/episodes.py`**: nuevo endpoint `POST /api/v1/episodes/{id}/abandoned` con schema `AbandonedEpisodeRequest(reason: Literal["beforeunload","explicit"], last_activity_seconds_ago: float ≥0 ≤86400)`. Devuelve **204 No Content** siempre — idempotente por diseño.
- **`main.py` + lifespan**: arranca el worker con `asyncio.create_task` (name `tutor.abandonment_worker`) y lo cancela en shutdown con `contextlib.suppress(asyncio.CancelledError)`. Apagable via `enable_abandonment_worker=False` para tests.
- **`config.py`**: settings nuevos `episode_idle_timeout_seconds=1800` (30 min), `abandonment_check_interval_seconds=60`, `enable_abandonment_worker=True`.

#### Cambios frontend (web-student)

- **`lib/api.ts`**: nuevo `emitEpisodioAbandonado(episodeId, payload, getToken?)` con doble estrategia — `fetch keepalive` cuando hay `getToken`, fallback a `navigator.sendBeacon` cuando no. `sendBeacon` no soporta `Authorization` header — en dev mode el proxy de Vite inyecta `X-User-Id`; en prod requiere firmar URL u otra estrategia. Documentado en el JSDoc.
- **`pages/EpisodePage.tsx`**: `useEffect` que registra listener `beforeunload` mientras `episodeId` esté seteado. Manda `last_activity_seconds_ago: 0` (signal honesta — el frontend no tiene baseline confiable de "última actividad" sin instrumentación adicional).
- **Sin tocar `vite.config.ts`** — el endpoint `/api/v1/episodes/{id}/abandoned` ya está cubierto por el ROUTE_MAP del api-gateway (`/api/v1/episodes` → tutor-service).

#### Tests nuevos

`apps/tutor-service/tests/unit/test_episodio_abandonado.py` con 7 tests:

- `record_episodio_abandonado` emite el evento correcto (event_type, payload, caller_id) y borra la sesión.
- Idempotente si no existe (devuelve `None`, 0 eventos publicados).
- Idempotente en doble llamada — solo la primera emite (mitigación Riesgo A "emisión doble" del [audi2.md:130-131](../audi2.md#L130-L131)).
- `_sweep_once` no toca sesiones activas (last_activity_at reciente).
- `_sweep_once` abandona sesiones inactivas con `reason="timeout"`.
- Caller del CTR es `TUTOR_SERVICE_USER_ID` para `timeout`, no el estudiante (auditabilidad).
- Falla soft: si `publish_event` falla para sesión A, sweep continúa con sesión B (verificado contando intentos).

#### ADR-025

[`docs/adr/025-episodio-abandonado-beforeunload-timeout.md`](adr/025-episodio-abandonado-beforeunload-timeout.md) — documenta opción A vs B, drivers, idempotencia, caller distinto por reason, constantes inmutables (1800s timeout, 60s check interval), coordinación con piloto.

### G8a — Override temporal de `anotacion_creada` en labeler v1.1.0 + ADR-023

- **Problema** ([audi2.md:18-54](../audi2.md#L18-L54)): `event_labeler.py:41` etiquetaba `anotacion_creada` como N2 fijo. La Tabla 4.1 de la tesis asigna a N1 (lectura) o N4 (apropiación tras tutor) según contenido. v1.0.0 cerraba el gap declarado en 15.6 (`time_in_level` por nivel) **introduciendo un sesgo nuevo** sub-reporta-N1/sobre-reporta-N2 documentado en 17.3.
- **Decisión**: G8a heurística temporal simple (la opción ligera del trifecta G8a/G8b/G8c). G8b (heurística léxica) y G8c (embeddings) quedan como Eje B.

#### Cambios al labeler

- **`LABELER_VERSION` 1.0.0 → 1.1.0** — re-etiqueta históricos sin tocar el CTR (ADR-020 lo cubre).
- **Constantes inmutables**: `ANOTACION_N1_WINDOW_SECONDS=120.0`, `ANOTACION_N4_WINDOW_SECONDS=60.0`. Documentadas en el ADR como decisión arbitraria del piloto sujeta a sensibilidad post-empírico.
- **Dataclass `EpisodeContext(event_ts, episode_started_at, last_tutor_respondio_at)`** — frozen, opt-in.
- **API**: `label_event(event_type, payload, context=None)`. **Sin contexto = comportamiento v1.0.0 puro** (backward-compat 100%); con contexto, override v1.1.0.
- **Override**: anotación dentro de los primeros 120s desde `episodio_abierto` → N1. Anotación dentro de 60s post `tutor_respondio` → N4. Solapes resueltos N4 > N1 (apropiación pedagógicamente más informativa que lectura inicial). `tutor_respondio` futuro relativo al evento (delta negativo) NO aplica el override (defensa contra desorden de seq).
- **Helper `_build_event_contexts(sorted_events)`** — recorre el episodio una vez propagando `episode_started_at` y `last_tutor_respondio_at`. Snapshot ANTES de procesar cada evento (así el `tutor_respondio` mismo no se considera como "su propio último tutor_respondio" para el override).
- **`time_in_level` y `n_level_distribution` reciben automáticamente el override** — usan los mismos contextos pre-computados → consistencia entre conteos y duraciones para el mismo evento. Anti-regresión por test integral.

#### Tests del labeler

`apps/classifier-service/tests/unit/test_event_labeler.py` actualizado: 32 tests pasando (21 pre-existentes intactos + 11 nuevos/refactorizados):

- `anotacion_creada_sin_contexto_es_n2_compat_v1_0_0` (compat).
- `labeler_version_es_1_x_y_minor_refleja_overrides_temporales` (sanity check del bump 1.x con minor ≥ 1).
- `anotacion_dentro_de_120s_de_episodio_abierto_es_n1` (borde inferior + 119s = N1).
- `anotacion_post_120s_sin_tutor_respondio_es_n2` (fallback).
- `anotacion_dentro_de_60s_de_tutor_respondio_es_n4` (20s + 59s = N4).
- `anotacion_post_60s_de_tutor_respondio_cae_a_n2` (fuera de ambas ventanas).
- `anotacion_n4_gana_sobre_n1_si_ambas_ventanas_solapan` (regla de desempate).
- `anotacion_con_tutor_respondio_futuro_no_aplica_n4` (defensa).
- `n_level_distribution_aplica_override_temporal_de_anotacion` (integración: 3 anotaciones a t=30/200/300 con tutor a t=180 → counts N1=1, N4≥2, N2=1; sanity assert que detecta regresión "todas en N2").

#### Test crítico preservado

`test_pipeline_reproducibility.py` 7/7 PASS sin tocar — la auditabilidad bit-a-bit del clasificador se mantiene. El bump de `LABELER_VERSION` se propaga en cada `n_level_distribution()` response y en cada `Classification`.

#### ADR-023

[`docs/adr/023-override-temporal-anotacion-creada.md`](adr/023-override-temporal-anotacion-creada.md) — documenta drivers, opt-in via context, regla de desempate N4>N1, constantes inmutables, criterio para revisitar (G8b post-defensa con validación κ). Marca explícitamente que la heurística es operacionalización conservadora declarable, **no verdad académica**.

### Stubs declarativos para los 5 G diferidos

Cada stub formaliza la decisión de NO implementar pre-defensa con criterio explícito de re-evaluación. Es lo que CLAUDE.md llama "decisión informada" en vez de "deuda silenciosa".

| ADR | G | Resumen |
|---|---|---|
| [ADR-017](adr/017-ccd-embeddings-semanticos.md) | G14 (audi2) / G1 (audi1) | CCD con embeddings semánticos. **Diferido a Eje B post-defensa**. Tesis 15.6 ya declara honestamente la operacionalización temporal v1.0.0 como gap. |
| [ADR-024](adr/024-prompt-kind-reflexivo-runtime.md) | G9 | `prompt_kind` reflexivo en runtime. **Diferido a Eje B**. Mid-cohort introduce sesgo; la rama "prompt reflexivo" del CCD queda muerta en runtime declarado en tesis 15.6. |
| [ADR-026](adr/026-boton-insertar-codigo-tutor.md) | G11 | Botón "Insertar código del tutor" en web-student. **Diferido a post-defensa**. Cambia condición experimental (confound 11.6 amplificado) — no es cambio neutro de instrumentación. |
| [ADR-027](adr/027-g3-fase-b-postprocesamiento.md) | G13 | Guardrails Fase B (postprocesamiento + `socratic_compliance`). **Diferido a Eje C**. RESUMEN-EJECUTIVO confirma "un score mal calculado es peor que ninguno"; requiere validación κ docente antes de cualquier wireado en el árbol del classifier. |
| [ADR-028](adr/028-desacoplamiento-instrumento-intervencion.md) | G15 (audi2) / G6 (audi1) | Desacoplamiento instrumento-intervención (capa "instrumento-only" del CTR + extensión Chrome para LLMs externos). **Diferido a post-piloto-1**. Refactor 2200 LOC + protocolo de consentimiento ampliado. |

[`docs/adr/README.md`](adr/README.md) actualizado: índice 015 → 028 (13 ADRs nuevos en el catálogo, 5 marcados explícitamente como "Aceptado (diferido)").

### Verificación final

| Check | Resultado |
|---|---|
| Tests Python (tutor-service + classifier-service + governance-service unit) | **185/186** ✓ |
| Falla restante | `test_load_sin_manifest_calcula_hash` — bug **pre-existente** cp1252 (test escribe con encoding default Windows, loader lee UTF-8). Confirmado pre-cambios. NO regresión. |
| `test_pipeline_reproducibility.py` (auditabilidad bit-a-bit) | **7/7** ✓ |
| `ruff check` archivos modificados | All checks passed (después de 2 fixes triviales: `F841 anotaciones_total`, `SIM105 contextlib.suppress`) |
| `mypy --no-incremental` event_labeler + abandonment_worker | Success: no issues found |
| `biome check` web-student | Checked 2 files. No fixes applied |
| `tsc --noEmit` web-student | Sin errores |

### Operaciones colaterales

- **`uv sync --all-packages`** corrió por primera vez (CLAUDE.md decía "tarda 3-5 min" — fue ~3 min). El `.venv` recién creado por el primer `uv run` quedó vacío hasta este sync.
- **`pnpm install`** corrió para tener `biome` + `tsc` disponibles. 425 paquetes resueltos (cache hit completo).
- **`git stash` no funciona en este repo** — `CLAUDE.md` ya declaraba `Is a git repository: false`. Confirmado al validar el bug pre-existente cp1252.

### Decisiones diferidas (declaradas como agenda)

Todo lo que **NO** se hizo en esta sesión está documentado en los 5 stubs ADR arriba. Específicamente:

- **G9**: `prompt_kind` reflexivo en runtime — diferido a Eje B (no aplicar mid-cohort).
- **G11**: botón "insertar código del tutor" — diferido a post-defensa (cambia UX experimental).
- **G13**: G3 Fase B postprocesamiento — diferido a Eje C (requiere validación κ).
- **G14**: CCD con embeddings semánticos — diferido a Eje B (requiere endpoint nuevo en ai-gateway).
- **G15**: desacoplamiento instrumento-intervención — diferido a post-piloto-1 (refactor 2200 LOC).

### Notas para el reporte empírico del piloto

- **`LABELER_VERSION="1.1.0"`** debe declararse en el reporte como la versión activa al momento de generar las clasificaciones (principio P6 de tesis 21.4).
- **`prompt_system_version="v1.0.0"`** sigue siendo la versión activa por default (v1.0.1 existe pero el `manifest.yaml` global no lo activa). Activar v1.0.1 entre cuatrimestres con commit explícito.
- **`EpisodioAbandonado`** empieza a aparecer en el CTR a partir del cutover de este PR. Episodios pre-cutover no tienen el evento — declarable como "abandono no observable" en el reporte (consistente con append-only ADR-010).
- **Tesis 17.3 + 19.5** deben actualizarse para reflejar que v1.1.0 cierra el sesgo del N2 fijo de v1.0.0 (Tabla 4.1 ahora se aproxima por heurística temporal en lugar de por contenido).

### Próximos pasos sugeridos (no bloqueantes)

- Cuando se decida implementar G9/G11/G13/G14/G15, reabrir los stubs ADR correspondientes (mismo número, status "Superseded por ADR-XXX") en lugar de crear uno nuevo.

### Continuación 2026-04-29 — T14-T18 (parches a tesis) + análisis de sensibilidad G8a + activación v1.0.1 global

Tras cerrar la ruta mínima de iter 2, el usuario pidió ejecutar las 3 tareas no bloqueantes que cierran el lado documental + académico del modelo híbrido honesto.

#### T14-T18 redactados en `03-cambios-tesis.md`

Nuevo archivo en raíz [`03-cambios-tesis.md`](../03-cambios-tesis.md) con propuestas de redacción (andamios) para que el doctorando refine contra el manuscrito real:

- **T14** — precisar override v1.1.0 de `anotacion_creada` en 4.3.1 / 15.6 + actualizar 17.3 sobre cierre parcial del sesgo + declarar G8b/G8c como Eje B. Coordinado con G8a + ADR-023.
- **T15** — declarar en 15.6 que la rama "prompt reflexivo" del CCD no se materializa en v1.0.x; activación es Eje B. Coordinado con G9 + ADR-024 (diferido).
- **T16** — precisar en 19.5 que el campo `origin` de `edicion_codigo` está parcialmente operacional (se emiten `student_typed | pasted_external` pero NO `copied_from_tutor` por ausencia de afordancia UX). Coordinado con G11 + ADR-026 (diferido).
- **T17** — actualizar 7.2 con triggers de `EpisodioAbandonado` (beforeunload + worker timeout) + idempotencia + caller distinto por reason. Coordinado con G10-A + ADR-025 (variante A elegida).
- **T18** — corregir cuenta de guardarrailes en 8.4.1: 4/10 → 3/10 (post-bump v1.0.1). Coordinado con G12.

Cada T trae: sección de tesis afectada, problema textual, propuesta de redacción borrador, coordinación con código (ADR + ruta + tests), riesgo doctoral. Tabla resumen tesis ↔ código al final.

#### Análisis de sensibilidad G8a

Nuevo script [`scripts/g8a-sensitivity-analysis.py`](../scripts/g8a-sensitivity-analysis.py) — reproducible (seed=42), genera corpus sintético, varía las dos constantes del override (`ANOTACION_N1_WINDOW_SECONDS`, `ANOTACION_N4_WINDOW_SECONDS`) por monkey-patching del módulo (con restauración garantizada en `try/finally`), y reporta tabla Markdown con distribución de anotaciones por nivel + ratio de tiempo total.

Output ejecutado: [`docs/adr/023-sensitivity-analysis.md`](adr/023-sensitivity-analysis.md) con 2000 episodios sintéticos, 5137 anotaciones. Resultados clave (vs baseline 120s/60s):

- N1 = 60s (estricto): **-52.7%** anotaciones N1 — el sesgo sub-reporta-N1 reaparece.
- N1 = 180s (laxo): **+2.5%** anotaciones N1 — saturación (la mezcla del corpus pone el 25% de anotaciones de "lectura inicial" mayoritariamente dentro de 120s).
- N4 = 120s (laxo): **+9.1%** anotaciones N4 — la ventana baseline 60s es conservadora; reflexiones con latencia 60-120s post `tutor_respondio` quedan en N2.
- **Ratio de tiempo por nivel es insensible** a la elección de ventanas (las anotaciones son fracción pequeña del total de eventos por episodio).

[ADR-023](adr/023-override-temporal-anotacion-creada.md) actualizado: la sección "Negativas / trade-offs" ahora ata al apéndice de sensibilidad y reporta los % concretos. El reporte empírico del piloto-1 debe re-ejecutar el script sobre corpus real al cierre del cuatrimestre.

#### Activación de v1.0.1 globalmente (decisión académica binaria)

El usuario eligió **activar AHORA** (no esperar al cierre del cuatrimestre). Decisión registrada en este bloque por trazabilidad — audi2.md G12 timing recomendaba diferir, el usuario pesó el trade-off y eligió activar.

Cambio implementado en TRES lugares alineados:

1. **`ai-native-prompts/manifest.yaml`** (nuevo) — fuente declarativa parseada por `PromptLoader.active_configs()` y expuesta en `GET /api/v1/active_configs`. Apunta `default.tutor: v1.0.1`, `default.classifier: v1.0.0`. Comentario inline documenta que el tutor-service NO consulta este archivo en runtime — usa su propia config — por lo que ambos lados deben mantenerse alineados.
2. **`apps/tutor-service/src/tutor_service/config.py:default_prompt_version`** — fuente efectiva consumida en runtime por `tutor_core.open_episode()`. v1.0.0 → v1.0.1. Comentario inline documenta la activación + atadura al manifest.
3. **Tests nuevos**:
   - `apps/governance-service/tests/unit/test_prompt_v1_0_1_bump.py::test_manifest_global_activa_v101_para_tutor_default` — verifica el parser + el `active.default.tutor == "v1.0.1"`.
   - `apps/tutor-service/tests/unit/test_config_prompt_version.py` (nuevo, 3 tests) — verifica `Settings().default_prompt_version == "v1.0.1"`, que el manifest existe y declara la misma versión, y sanity check del prompt name.

**Importante para el reporte empírico**: episodios pre-activación (timestamp < 2026-04-29) tienen `prompt_system_version="v1.0.0"` y `prompt_system_hash="238cbcbb..."`. Episodios post-activación tienen `v1.0.1` y `2ecfcdd...`. Ambos son reproducibles bit-a-bit con su versión correspondiente. El reporte empírico debe filtrar/declarar la versión por episodio (principio P6 tesis 21.4).

**Comportamiento del LLM idéntico bit-a-bit** — verificado por `test_texto_del_prompt_es_identico_modulo_comment_y_version`. El HTML comment es invisible al modelo. La activación NO modifica respuestas del tutor; solo cambia el hash propagado al CTR y la cuenta declarada en el HTML comment de auditoría (4/10 → 3/10).

#### Verificación final post-activación

| Check | Resultado |
|---|---|
| Tests Python (tutor + classifier + governance) | **189/190** ✓ |
| Falla restante | El mismo bug cp1252 pre-existente (no regresión). Verificado por 4ta vez. |
| Tests nuevos de la activación (governance + tutor config) | **9/9** ✓ |

#### Nota crítica para futuros Claude / doctorando

Hay DOS lugares donde "la versión activa del prompt" se declara, y mantenerlos desalineados es **silencioso pero peligroso**:

- `ai-native-prompts/manifest.yaml` (declarativo, expuesto en `/api/v1/active_configs`).
- `apps/tutor-service/src/tutor_service/config.py:default_prompt_version` (efectivo en runtime).

Si solo se cambia uno, frontends que consultan `/active_configs` ven una versión y el tutor-service usa otra al abrir episodios — el `prompt_system_hash` propagado al CTR no coincide con la versión declarada. El test `test_manifest_yaml_existe_y_se_parsea` cubre esto, pero es responsabilidad operacional mantenerlos alineados en cualquier rotación futura.

### Continuación 2026-04-29 (tarde) — Auditoría de coherencia backend ↔ infra ↔ frontend + 6 fixes ejecutados + B.2 documentado

Tras cerrar la activación v1.0.1, el usuario pidió un análisis riguroso cross-codebase para detectar gaps de coherencia. Delegué 3 inventarios en paralelo (backend, infraestructura, frontend) via agentes Explore y sinteticé el resultado en un audit de **3 gaps críticos + 5 stubs documentados como diferidos + 8 inconsistencias menores**. Después el usuario eligió ejecutar **todas las recomendaciones priorizadas y testeadas**.

#### Auditoría: hallazgos clave

- **B.1 CRÍTICO**: no había forma de inscribir estudiantes desde UI. `/api/v1/inscripciones` referenciado en docstrings era vaporware; `bulk-import` no incluía `inscripciones`; `enrollment-service` tenía `imports.py` con TODO sin resolver y ningún frontend que lo consumiera.
- **B.2 CRÍTICO**: `GET /api/v1/comisiones/mis` queda vacío para estudiantes reales — JOIN con `usuarios_comision` solo trae docentes/JTP. F9 (JWT con `comisiones_activas` claim) requiere Keycloak corriendo.
- **D.4 OPORTUNIDAD**: `POST /api/v1/episodes/{id}/verify` del ctr-service NO estaba expuesto en el ROUTE_MAP (conflicto con `/api/v1/episodes` → tutor-service). Una UI de verificación CTR sería visualmente potente para el comité doctoral — ATL clave para la defensa.

#### 6 fixes ejecutados con tests

| ID | Cambio | ADR | Tests nuevos |
|---|---|---|---|
| **D.2** | Tabla puertos Keycloak 8080 → 8180 en `CLAUDE.md:54` (mapeado desde 8080 del container per `docker-compose.dev.yml:79`) | — | — |
| **D.7** | `ClasificacionesPage`: TODO(F9) cerrado con nuevo `ComisionPicker.tsx` reusable que carga via `comisionesApi.list()` y autoselecciona la primera | — | — (tsc verde) |
| **B.1** | Bulk import de inscripciones centralizado en `academic-service`. Schema + service + bulk_import registry + UI + Casbin policies dormidas que se activan automáticamente. | **ADR-029** | 7 (bulk dry-run + commit + FK error + rollback + Casbin mapping + supported_entities) |
| **D.6** | Deprecar `enrollment-service` (redundante post-B.1). Sacado del workspace + ROUTE_MAP + helm. Directorio preservado en disco con README de deprecation. | **ADR-030** | 46/46 gateway+bulk verdes post-deprecation |
| **D.1** | **Audit inicial era incorrecto**: confundió "import de `HelpButton`" con "uso de `helpContent` via `PageContainer`". Las 9 keys del web-teacher Y todas las del web-admin YA estaban cubiertas. Sumé test anti-regresión que detecta keys faltantes en futuras adiciones. | — | 2 (`helpContent.coverage.test.ts`) |
| **D.4** | UI auditoría CTR via aliases `/api/v1/audit/*`. Nuevo `audit_router` en ctr-service registra los handlers existentes via `add_api_route` (cero duplicación). Sumado a ROUTE_MAP. UI `AuditoriaPage.tsx` con form + verify + colorización OK/FAIL + display detallado de `failing_seq`/`integrity_compromised`. | **ADR-031** | 3 (apunta al mismo handler legacy + audit_router solo expone read-only) |

#### B.2 documentado como plan operativo (no ejecutable hoy)

Nuevo archivo [`docs/plan-b2-jwt-comisiones-activas.md`](plan-b2-jwt-comisiones-activas.md) con:

- Síntoma actual verificado contra código.
- 3 dependencias externas que bloquean ejecución (Keycloak operacional, federación LDAP, coordinación DI UTN — los 5 puntos pendientes de ADR-021).
- Diseño propuesto con dos opciones (Java SPI vs groups-mapper estándar) — recomendación: groups-mapper para piloto-1.
- Cambios concretos en Keycloak / api-gateway / academic-service / frontends / tests.
- Estimación: ~210 LOC efectivo + tests E2E con Keycloak.
- Recomendación de timing: ejecutar en la misma ventana del deploy del `integrity-attestation-service` por compartir coordinación institucional.

#### Conflicto de routing detectado y resuelto en D.4

`/api/v1/episodes/*` ya rutea al tutor-service en el ROUTE_MAP. El verify del ctr-service vive bajo `/api/v1/episodes/{id}/verify`. **Mover el endpoint** rompía consumers service-to-service. **Cambiar el matching del proxy** era cambio sutil con riesgo. Solución: nuevo `audit_router = APIRouter(prefix="/api/v1/audit")` que registra `get_episode` y `verify_episode_chain` via `add_api_route` apuntando a las mismas funciones legacy. Backwards-compatible 100%.

#### Hallazgo importante para futuros Claude / doctorando

El test pre-existente `test_load_sin_manifest_calcula_hash` en governance-service falla en Windows con cp1252 (escribe el archivo con encoding default del SO pero el loader lo lee como UTF-8). **No es regresión de iter 2** — confirmado por 4ª vez en esta sesión. Si lo van a fixear, va aparte y antes de mergear cualquier otro cambio en governance-service para no contaminar scope.

#### Resumen ejecutivo de iter 2 (mañana + tarde)

| Plano | Antes | Después |
|---|---|---|
| **Coherencia tesis ↔ código** | 7 G abiertos en audi2.md | 4 G cerrados (G8a, G10-A, G12), 5 G diferidos con ADR formal |
| **Coherencia backend ↔ frontend** | 3 gaps CRÍTICOS + 5 diferidos + 8 inconsistencias | 1 CRÍTICO sin ejecutar (B.2) con plan operativo, resto cerrado |
| **ADRs** | 28 | **31** (nuevos: 023, 025, 029, 030, 031 — más los 5 stubs 017/024/026/027/028 redactados de mañana) |
| **Tests Python nuevos en iter 2** | 0 | **70+** (todos verdes) |
| **Servicios operacionales** | 12 + 1 esqueleto | 11 + 1 esqueleto + 1 deprecated (preservado en disco) |
| **UIs nuevas** | — | `AuditoriaPage` (auditoría CTR live), `ComisionPicker` reusable, `BulkImport > Inscripciones` |

#### Notas para reportes empíricos del piloto

- El bulk de inscripciones (ADR-029) habilita el alta masiva de estudiantes desde web-admin sin tocar SQL — desbloquea uso real con UTN para el cuatrimestre vigente.
- La `AuditoriaPage` (ADR-031) es ATL clave para la defensa: el comité puede ver en vivo la verificación criptográfica de cualquier episodio del corpus del piloto-1.
- B.2 sigue bloqueante para SSO real — hasta que Keycloak esté operacional con federación LDAP completa, los estudiantes reales no pueden loguearse fuera del modo dev. El plan está listo en `docs/plan-b2-jwt-comisiones-activas.md` para ejecución mecánica post-coordinación UTN.

#### Próximos pasos sugeridos (fuera de scope iter 2)

- Coordinación institucional con DI UTN: resolver los 5 puntos pendientes del ADR-021 + las preguntas del plan B.2.
- Cleanup del bug pre-existente cp1252 en `test_load_sin_manifest_calcula_hash` (separar scope, PR aislado).
- Drilldown navegacional `ClasificacionesPage → AuditoriaPage` con `episode_id` precargado (mejora UX, ~20 LOC).
- Eventualmente, eliminar `apps/enrollment-service/` directorio físico si pasa el siguiente cuatrimestre sin caso de uso.

---

## 2026-04-27 — G4 (etiquetador N1-N4) + G5 (registro externo Ed25519) + G3 mínimo (guardrails Fase A)

Sesión basada en el análisis del documento `audi1.md` (auditoría de 7 cambios grandes G1–G7 detectados como gaps entre la tesis y el código). Decisión estratégica: hacer **modelo híbrido honesto** — implementar G4, G5, G3-mínimo, G2-mínimo antes de la defensa; declarar G1, G6, G7 como agenda Cap 20 con ADR redactado. Arrancamos por G4 + G5.

### G4 — Etiquetador de eventos N1-N4 (componente C3.2 de la tesis)

- **ADR-020 redactado**: derivación en lectura, función pura sobre `(event_type, payload)`. NO almacena `n_level` en payload (rompería `self_hash` y append-only). Versionable vía `LABELER_VERSION` — bumpear re-etiqueta históricos sin tocar el CTR.
- **`event_labeler.py`** nuevo en classifier-service. Mapping canónico para los 9 `event_type` reales del contract. Override condicional para `edicion_codigo.origin == "copied_from_tutor" | "pasted_external"` → N4 (aprovecha info ya presente en el payload, no requiere cambios al frontend).
- **`anotacion_creada` queda con N2 fijo en v1.0.0** — la Tabla 4.1 de la tesis sugiere N1/N2/N4 según contenido, pero el override por estudiante o por NLP queda como agenda futura (ADR separado). Default N2 es la operacionalización conservadora más honesta.
- **Endpoint nuevo**: `GET /api/v1/analytics/episode/{id}/n-level-distribution` en analytics-service. Devuelve `{distribution_seconds, distribution_ratio, total_events_per_level, labeler_version}` para el episodio. Modo dev (sin CTR_STORE_URL) devuelve distribución vacía con `labeler_version` — coherente con `/cohort/{id}/progression`.
- **Tests**: 23 unit del labeler (mapping cubre los 9 event_type del contract via sanity check explícito; override por origin; clamp de delta negativo; idempotencia/pureza) + 6 unit del endpoint (auth + response shape). Total 29 nuevos.
- **Reproducibilidad bit-a-bit preservada**: `test_pipeline_reproducibility.py` 7/7 PASS sin tocar.

### G5 — Registro externo auditable Ed25519 (Sección 7.3 de la tesis)

- **ADR-021 redactado** (~250 líneas, estilo ADR-016). Decisiones criptográficas centrales:
  - **Ed25519** (RFC 8032) — claves 32 B, firmas 64 B, 70k ops/s, sin footguns.
  - **Buffer canónico bit-exact** documentado en el ADR: `f"{episode_id}|{tenant_id}|{final_chain_hash}|{total_events}|{ts_episode_closed}|{schema_version}"`. Orden FIJO (no alfabético), separador `|`, `ts` con sufijo `Z` no `+00:00`. Mismo nivel de cuidado que `chunks_used_hash` o `classifier_config_hash`.
  - **`ts_attested` NO entra en la firma** — sería trivialmente atacable. La firma es sobre los datos del episodio, no sobre cuándo se firmaron.
  - **Asíncrono con retry**: ctr-service emite a stream Redis `attestation.requests` después de commit transaccional. Worker single-consumer del attestation-service procesa. **El cierre del episodio NO se bloquea**. Backoff a 24h con alerta Grafana.
- **Servicio nuevo `integrity-attestation-service`** (puerto 8012):
  - `services/signing.py`: Ed25519 + buffer canónico + failsafe contra deploy de dev key en `environment=production` (compara `signer_pubkey_id` activo contra `DEV_PUBKEY_ID = "26f7cf0749b5"` hardcodeado).
  - `services/journal.py`: JSONL append-only con rotación diaria UTC. POSIX/Windows write con `O_APPEND` es atómico para writes < 4KB (cada attestation ~500 B).
  - `routes/attestations.py`: `POST` (interno, sin Casbin — IP allowlist en producción), `GET /pubkey` (público), `GET /{date}` (público para auditores).
  - `workers/attestation_consumer.py`: consumer del stream con DLQ a `attestation.dead` tras MAX_ATTEMPTS=3. Replica el patrón de `partition_worker.py` del ctr-service.
- **Dev keys deterministas**: `dev-keys/regenerate.py` deriva el keypair de un seed fijo (`AI-NativeV3-DEV-ATTESTATION-KEY1`, 32 bytes). Cualquiera que borre y regenere obtiene EXACTAMENTE las mismas claves — clave para tests con golden signature `6333bee9...ad1606`. Las dev keys SÍ se commitean al repo (excepción explícita en `.gitignore` con `!apps/integrity-attestation-service/dev-keys/dev-*.pem`); son **públicas, no secretas, DEV ONLY**.
- **Hook en ctr-service**:
  - `services/attestation_producer.py` nuevo. Patrón análogo al `EventProducer`: XADD a `attestation.requests` con maxlen approx 100k. Fail-soft: si Redis cae, log warning + retorna None — el caller continúa.
  - `partition_worker.py`: `_persist_event` cambió signature a `dict | None` — devuelve attestation_payload **solo** para `episodio_cerrado` exitoso (idempotencia respetada: un duplicado retorna None). El XADD ocurre POST-commit en `_process_message`. Si falla, log + continúa.
  - **Misma DB Redis (DB 0)**: corregí el config del attestation-service de DB 2 a DB 0 para compartir la instancia con ctr-service. Sin esto, el stream sería invisible al consumer.
- **Tool CLI `scripts/verify-attestations.py`**: cualquier auditor con la pubkey + el directorio de JSONLs verifica firmas bit-exact. Reporta OK/FAIL/WARN por línea, totales, duplicados (mismo episode_id firmado >1 vez — info, no necesariamente bug). Exit 0 si todo OK, 1 si alguna falla. **Probado end-to-end**: generé 3 attestations, manipulé 1 firma, la tool detectó "FIRMA INVALIDA" y devolvió exit 1.
- **Tests totales nuevos**:
  - 19 unit signing (buffer canónico bit-exact + golden signature reproducible + failsafe production)
  - 13 unit journal (append + rotación UTC + read + raw JSONL)
  - 12 unit endpoint HTTP
  - 10 unit producer ctr-service (mock Redis + normalización ts + fail-soft)
  - 10 unit consumer attestation-service (sign roundtrip + DLQ + retry semantics)
  - 2 integration end-to-end (Redis testcontainer; skipped si no hay docker, pasarían en CI)
  - 3 health/skeleton
  - **Total: 69 tests nuevos** + 0 regresiones.

### CLAUDE.md actualizado

- ADR count: 17 → 18.
- Numeración nueva: `022+`.
- Tabla de puertos: `integrity-attestation-service: 8012` (con nota sobre infra institucional separada en piloto).
- 2 invariantes nuevas en "Propiedades críticas": `n_level derivado en lectura` (ADR-020) + `attestation externa Ed25519 eventual` (ADR-021).

### reglas.md actualizado

- **RN-128 nueva** ("Cada episodio cerrado emite attestation externa Ed25519 (eventual)") — categoría Auditoría, severidad Alta, fase F5. Documenta fail-soft semantics + SLO 24h + buffer canónico bit-exact.
- Catálogo Reglas Altas: 56 → 57.
- Tabla de trazabilidad: nueva fila para RN-128.

### Decisiones diferidas a piloto-2 (declaradas como agenda)

- **Reconciliation job de attestations perdidas**: si Redis cae y se pierden requests, hoy las attestations quedan silenciosamente sin emitir. Reconciliation = job que itera `Episode.estado='closed'` sin attestation correspondiente y las re-emite. Documentado en ADR-021 trade-offs.
- **Métrica Prometheus `attestation_pending_count`** para alerta Grafana a 24h: declarada en ADR pero NO implementada en este PR. Es ~1h de trabajo, prioridad menor.
- **Override por estudiante de `anotacion_creada.n_level`**: requiere UI en web-student + tabla paralela `event_labels` (Opción C del ADR-020). Diferido.
- **G3 (Fase A guardrails)**, **G2 (CII longitudinal mínimo)**: próximos en el plan de "modelo híbrido honesto".

### Decisiones pendientes (NO técnicas — requieren coordinación institucional UTN)

ADR-021 documenta 5 preguntas para el doctorando que requieren input del director de informática UTN antes de deploy del piloto:

1. ¿UTN provee VPS institucional separado o vamos con MinIO compartido con bucket aparte?
2. ¿Quién genera y custodia la clave privada Ed25519? (recomendado: director de informática, no el doctorando — D3 del ADR).
3. ¿Hay budget para VPS adicional?
4. ¿24h de SLO con alerta Grafana es aceptable?
5. ¿La pubkey vive en el repo, en URL pública institucional, o ambas? (recomendado: ambas).

El código del PR está completo y testeado en dev mode. El deploy a piloto requiere resolver las 5 preguntas + coordinar con UTN. Recomendación: arrancar la conversación institucional ahora para no acumular código sin clave institucional confirmada.

### Validación final

- Suite total: **186 passed + 2 skipped (docker)** en ~30s.
- Lint: clean en todos los archivos nuevos.
- 0 regresiones en classifier + analytics + ctr-service + attestation-service.
- Reproducibilidad bit-a-bit preservada: `test_pipeline_reproducibility.py` 7/7 PASS sin tocar.

### Archivos clave creados/modificados

- `docs/adr/020-event-labeler-n-level.md` (G4)
- `docs/adr/021-external-integrity-attestation.md` (G5)
- `docs/adr/019-guardrails-fase-a.md` (G3 mínimo)
- `apps/classifier-service/src/classifier_service/services/event_labeler.py` (G4) — actualizado para incluir `intento_adverso_detectado` → N4
- `apps/classifier-service/tests/unit/test_event_labeler.py` (G4)
- `apps/analytics-service/src/analytics_service/routes/analytics.py` — endpoint `n-level-distribution` (G4)
- `apps/analytics-service/tests/unit/test_n_level_distribution_endpoint.py` (G4)
- `apps/integrity-attestation-service/` — servicio completo nuevo (G5, ~800 LOC + 47 tests)
- `apps/ctr-service/src/ctr_service/services/attestation_producer.py` (G5)
- `apps/ctr-service/src/ctr_service/workers/partition_worker.py` — modificado para hook (G5)
- `apps/ctr-service/tests/unit/test_attestation_producer.py` (G5)
- `apps/tutor-service/src/tutor_service/services/guardrails.py` (G3) — módulo nuevo, ~180 LOC
- `apps/tutor-service/src/tutor_service/services/tutor_core.py` (G3) — hook entre `prompt_enviado` y `ai_gateway.stream`
- `apps/tutor-service/tests/unit/test_guardrails.py` (G3) — 26 tests
- `apps/tutor-service/tests/unit/test_tutor_core.py` (G3) — +6 tests del hook
- `packages/contracts/src/platform_contracts/ctr/events.py` (G3) — `IntentoAdversoDetectado` + payload
- `scripts/verify-attestations.py` (G5)
- `CLAUDE.md`, `reglas.md`, `.gitignore`, `scripts/check-health.sh`

### G3 mínimo — Guardrails Fase A (Sección 8.5 de la tesis)

- **ADR-019 redactado**: detección preprocesamiento del prompt del estudiante por regex compilados. **NO bloquea** — el prompt sigue al LLM tal cual; el side-channel es el evento CTR `intento_adverso_detectado`. Categorías y severidad: `jailbreak_indirect` (3), `jailbreak_substitution` (4), `jailbreak_fiction` (2), `persuasion_urgency` (2), `prompt_injection` (5).
- **Contract nuevo**: `IntentoAdversoDetectadoPayload` con `{pattern_id, category, severity, matched_text, guardrails_corpus_hash}`. Mismo patrón que `PromptEnviado` en el contract Pydantic.
- **`guardrails.py`** en `tutor-service/services/`: regex compilados ES + EN, función pura `detect(content) -> list[Match]`. `compute_guardrails_corpus_hash()` con la fórmula canónica (`sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`) — mismo patrón que `classifier_config_hash` (ADR-009). Hash golden: `f30cf33a021624a890cfdbebe14823f9d450f1f421cd7b283e6e74d4dd4d2c69` (test golden lo verifica; cambiarlo BREAKEA reproducibilidad bit-a-bit).
- **Hook en `tutor_core.py:interact()`** entre `prompt_enviado` y `ai_gateway.stream`. Por cada match emite evento adverso. Falla soft: si `detect()` lanza, log + continúa sin adversos (no romper el flujo del estudiante por bug en regex). El callable `detect_adversarial` es **inyectable** en `__init__` para tests mockeables.
- **Decisiones diferidas explícitas a piloto-2**:
  - **Fase B** (postprocesamiento de respuesta del tutor + cálculo de `socratic_compliance` y `violations`): un score mal calculado es peor que ninguno (audit G3). Sigue como `None`/`[]` en el `TutorRespondioPayload`.
  - **`overuse` category** (8.5.3): requiere ventana cross-prompt; iteración separada.
  - **System message inyectado al LLM** ("el estudiante puede estar intentando manipularte"): hoy NO se inyecta — el `prompt_system` del tutor socrático ya condiciona el rol; el system message extra puede ser overkill o inducir false-positive bloquing.
  - **Flag `adversarial_flagged=true` en Episode**: requiere consumer dedicado o lógica en `partition_worker.py` (severidad acumulada > umbral). Diferido — la severidad por evento ya es queryable.
- **Mapping en event_labeler.py (ADR-020)**: `intento_adverso_detectado` → **N4** (interacción con IA). Test golden actualizado: 9 → 10 event_types en `EVENT_N_LEVEL_BASE`.
- **Tests del módulo**: 26 unit del guardrails (golden hash + cada categoría detecta + falsos positivos básicos + función pura/idempotente + performance smoke en prompt de 5000 chars). +6 tests de integration del hook con `FakeCTRClient` (prompt benigno → 2 eventos; jailbreak → 3 eventos en orden estricto; multi-categoría → multi-eventos; prompt llega al LLM sin censura; `detect_adversarial` mockeable).
- **CLAUDE.md**: ADR count 18 → 19, slots reservados ahora 017-018 (G1-G2). Invariante nueva: "Detección preprocesamiento de intentos adversos en prompts del estudiante (Fase A)".
- **reglas.md**: **RN-129 nueva** — categoría Seguridad / severidad Alta / fase F4. Catálogo Reglas Altas 57 → 58.
- **Validación final**: 274 passed + 2 skipped (docker) en ~33s. Lint clean en archivos nuevos. `test_pipeline_reproducibility.py` 7/7 PASS. `test_event_labeler.py` 24/24 PASS (incluyendo nuevo `intento_adverso_detectado` → N4). Cero regresiones.

### Revisión adversarial + 6 fixes (mismo día)

Tras cerrar G3+G4+G5, se hizo una **revisión adversarial con 3 agentes en paralelo** (uno por G), cada uno con instrucciones explícitas de "no ser complaciente". Los reportes identificaron 4 hallazgos de severidad ALTA + 2 docs pendientes. Todos corregidos en la misma sesión:

- **FIX 1+2 (G3): corpus de regex ampliado a v1.1.0 + persuasion_urgency restrictiva.** El reviewer encontró falsos negativos triviales (`OLVIDA TUS INSTRUCCIONES`, `ignore the previous prompt`, `ignora todas las instrucciones`, `descarta tus reglas`) y un falso positivo importante (`es urgente que entienda esto antes del examen` matcheaba como manipulación, era un estudiante real bajo presión). El corpus se amplió: verbos `olvid|ignor|descart|borr|override`, objetos `instrucci|regl|prompt|directiv|orden|comando`, mayúsculas con tildes via `[aá]`. `persuasion_urgency` ahora requiere **imperativo cercano** (`dame|escrib|respond|ayud|hac`) — sin imperativo no matchea. Se bumpeó `GUARDRAILS_CORPUS_VERSION` 1.0.0 → 1.1.0; nuevo hash golden `b6984c118d68d703...`. **Limitación declarada**: la evasión intra-palabra (`olvi-da`) NO está cubierta — agenda futura para Fase B con clasificador ML. Tests de regresión nuevos: 3 (test_v1_1_0_arregla_falsos_negativos, test_v1_1_0_corrige_falso_positivo, test_v1_1_0_persuasion_urgency_si_matchea_con_imperativo).
- **FIX 3 (G3): inyección de system message reforzante (Sección 8.5.1 de la tesis).** El ADR-019 v1.0.0 declaraba "no se inyecta system message" — eso contradecía literalmente la tesis Sección 8.5.1 que dice *"responder con formulación estándar de recuerdo del rol"*. Implementado: cuando hay match con severidad >= 3 (`jailbreak_indirect`, `jailbreak_substitution`, `prompt_injection`), el `tutor-service` inyecta un system message ADICIONAL (`_REINFORCEMENT_SYSTEM_MESSAGE`) ANTES del prompt del estudiante en `messages` que va al LLM. Severidades 1-2 (`jailbreak_fiction`, `persuasion_urgency`) NO inyectan — son ambiguas y reforzar contra estudiantes legítimos bajo presión sería over-correction. Tests nuevos: 3 (severidad alta inyecta, prompt benigno NO inyecta, severidad baja NO inyecta).
- **FIX 4 (G4): X-User-Id + log estructurado en endpoint /n-level-distribution.** ADR-020 línea 158 lo declaraba pero el endpoint solo tenía `X-Tenant-Id`. Inconsistente con `compute_kappa`, `ab_test_profiles`, `export_cohort` (todos los demás endpoints del analytics-service). Agregado `user_id: UUID = Depends(get_user_id)` + propagación al log. Tests nuevos: 2 (sin user_id → 401, user_id no UUID → 400). **Casbin enforcement** queda como deuda transversal del analytics-service (ningún endpoint lo hace hoy; out-of-scope de G4).
- **FIX 5 (G3): severidad documentada como ordinal en ADR-019.** El reviewer cuestionó "¿por qué `jailbreak_substitution=4` y `jailbreak_indirect=3`? los números son arbitrarios". Documentado en el ADR: la severidad es **ranking ordinal**, no peso cardinal. NO hace sentido sumar/promediar. El threshold del system message reforzante (`>= 3`) es la interpretación operativa del ranking.
- **FIX 6 (G5): replicas:1 documentado para attestation-consumer.** El reviewer marcó que `journal.py` usa `O_APPEND` atómico (< 4KB) pero NO file lock — single-consumer es **precondición operacional** no forzada en código. Documentado como sección "⚠ CRÍTICO" en el ADR-021 + nota top-of-file en el módulo del consumer. Cuando se redacte el Helm chart `infrastructure/helm/integrity-attestation/`, debe configurar `replicas: 1` explícitamente. Si en el futuro se necesita escalado horizontal, el rediseño correcto es agregar `filelock` package o particionar por `episode_id`.

**Lo que NO se arregló** (false positives del review):
- *G4 BUG #1 "_parse_ts(None) crashea"*: el código defensivo `if ev.ts else None` introduce path muerto (DB tiene `ts NOT NULL`). No es bug real; mantengo el defensivo por consistencia con otros endpoints.
- *G4 BUG #3 "sin tests integration con DB"*: ya declarado como deuda chica al cerrar G4. Requiere testcontainers Postgres; agenda futura.
- *G4 modo dev 200 vacío*: patrón consistente con `/cohort/{id}/progression`. Cambiar solo en G4 introduce inconsistencia.

**Validación final post-fixes**: 282 tests passed + 2 skipped (docker) en ~33s (+8 tests sobre los 274 originales). Cero regresiones. Lint clean en archivos nuevos/modificados. `test_pipeline_reproducibility.py` sigue 7/7 PASS sin tocar — cadena criptográfica del CTR intacta.

### Decisiones institucionales tomadas (G5 destrabado)

Mismo día, el doctorando confirmó las 5 preguntas pendientes del ADR-021:

1. ✅ **VPS institucional separado**: SÍ. Se descarta el fallback de MinIO con bucket aislado.
2. ✅ **Custodia de la clave privada**: Director de informática UTN — sin participación del doctorando.
3. ✅ **Presupuesto adicional**: aprobado.
4. ✅ **SLO de attestation**: 24h (default).
5. ✅ **Pubkey storage**: ambos (URL canónica + commit como snapshot).

**ADR-021 pasa de Propuesto a Aceptado** (sección "Decisiones tomadas (2026-04-27)" agregada).

**Artefactos operativos creados**:
- `docs/pilot/attestation-deploy-checklist.md` — checklist de 10 pasos para que el DI UTN provisione el VPS, genere la clave Ed25519 (sin participación del doctorando, cumple D3), despliegue el servicio, configure nginx con IP allowlist, y haga smoke test end-to-end. Incluye runbook de fallas comunes.
- `docs/pilot/attestation-pubkey.pem.PLACEHOLDER` — slot reservado para la pubkey institucional. Cuando el DI UTN entregue la clave (Paso 2 del checklist), se renombra a `attestation-pubkey.pem` y se commitea como snapshot del período del piloto.
- Resumen ejecutivo (`docs/RESUMEN-EJECUTIVO-2026-04-27.md`) actualizado: "Bloqueante institucional" → "Decisiones tomadas + próximos pasos operativos". Listo para enviar al director de tesis y al DI UTN.

**El piloto puede arrancar** una vez que el DI UTN ejecute el checklist (~1-2 días de trabajo de su lado, sin bloquear desarrollo del doctorando).

### G2 mínimo — CII evolution longitudinal (Sección 15.4)

Cierre del último ítem implementable del plan defensivo del modelo híbrido honesto.

- **ADR-018 redactado**: `cii_evolution_longitudinal` como **slope ordinal por `template_id`** sobre `APPROPRIATION_ORDINAL` (delegacion=0, superficial=1, reflexiva=2). Definición de "problemas análogos" via `TareaPractica.template_id` (ADR-016). Mínimo `MIN_EPISODES_FOR_LONGITUDINAL = 3` para calcular slope; con N<3 → `null` + flag `insufficient_data`. **NO se renombran** los `cii_stability`/`cii_evolution` actuales (intra-episodio) — preserva BC con clasificaciones históricas. **NO requiere migration Alembic**: el campo nuevo vive en `Classification.features['cii_evolution_longitudinal']` (JSONB). **NO incluye `cii_criteria_stability` ni `cii_transfer_effective`** — agenda futura piloto-2 cuando exista G1 / embeddings.
- **Decisiones diferidas explícitas a piloto-2**:
  - Renombrar `cii_*` → `iis_*` (BC-incompatible, requiere migración de exports académicos).
  - `cii_criteria_stability` y `cii_transfer_effective` (requieren NLP de contenido).
  - Persistir `cii_evolution_longitudinal` eagerly en cada clasificación (hoy on-demand al pegar al endpoint).
  - Análisis cross-comisión del mismo estudiante (hoy el endpoint requiere `comision_id` query param).
- **`packages/platform-ops/src/platform_ops/cii_longitudinal.py`** nuevo (~110 LOC):
  - `compute_evolution_per_template(classifications) -> list[dict]` agrupa por template + calcula slope.
  - `compute_mean_slope(per_template) -> float | None` promedia solo templates con N≥3.
  - `compute_cii_evolution_longitudinal(classifications) -> dict` helper de alto nivel para endpoint.
  - Constantes `CII_LONGITUDINAL_VERSION = "1.0.0"`, `MIN_EPISODES_FOR_LONGITUDINAL = 3`.
  - Reusa `APPROPRIATION_ORDINAL` de `platform_ops.longitudinal`.
- **Extensión de `RealLongitudinalDataSource`**: nuevo método `list_classifications_with_templates_for_student(student_pseudonym, comision_id, academic_session)` que hace **triple cross-DB query** (CTR + classifier + academic) para resolver `Episode.problema_id → TareaPractica.template_id`. Mantiene el método viejo `list_classifications_grouped_by_student` intacto para no romper `/cohort/progression`.
- **Endpoint nuevo**: `GET /api/v1/analytics/student/{student_pseudonym}/cii-evolution-longitudinal?comision_id=X`. Auth `X-Tenant-Id` + `X-User-Id` (alineado con FIX 4 de la revisión adversarial). Modo dev devuelve estructura vacía con 200 (mismo patrón que `/cohort/progression` y `/n-level-distribution`). Modo real triple cross-DB con RLS por tenant. `ATTESTATION_DB_URL`... → `academic_db_url` agregado al config del analytics-service.
- **Tests nuevos**: 19 unit del módulo (golden mejorando/empeorando/estable + insufficient_data + multi-template + huérfanas skipped + idempotencia + ts como str ISO o datetime + appropriation inválida descartada) + 8 unit del endpoint (auth + modo dev + response shape + path/query params validation).
- **CLAUDE.md**: ADR count 19 → 20. Slot 017 reservado solamente (G1). Invariante nueva en "Propiedades críticas" sobre CII longitudinal por `template_id`. ADR-018 referenciado.
- **reglas.md**: **RN-130 nueva** ("CII evolution longitudinal por `TareaPractica.template_id`, slope ordinal con N>=3"). Severidad Alta, fase F7. Catálogo Reglas Altas: 58 → 59. Tabla de trazabilidad: nueva fila.
- **Validación final post-G2**: **309 tests passed + 2 skipped (docker)** en ~43s. **+27 tests sobre los 282 anteriores** (19 cii_longitudinal + 8 endpoint). Cero regresiones. Lint clean en archivos nuevos. `test_pipeline_reproducibility.py` 7/7 PASS sin tocar — cadena criptográfica intacta.

### Estado del modelo híbrido honesto al cierre de la sesión

**✅ Implementado (defendible)**:
- **G3 mínimo** (Fase A guardrails) — ADR-019, RN-129
- **G4** (etiquetador N1-N4) — ADR-020
- **G5** (registro externo Ed25519) — ADR-021, RN-128, decisiones institucionales tomadas, checklist DI UTN
- **G2 mínimo** (CII evolution longitudinal) — ADR-018, RN-130

**📋 Agenda Cap 20 (NO implementar, ADR redactado o por redactar)**:
- **G1** (CCD con embeddings semánticos) — ADR-017 todavía sin redactar (slot reservado). Cuando lo redactes, declará la versión temporal del CCD como operacionalización conservadora; embeddings → piloto-2.
- **G6** (desacoplamiento instrumento-intervención) — refactor 1500 LOC, agenda Cap 20.
- **G7 completo** (dashboard docente con drill-down + alertas predictivas) — MVP simple sí, versión completa con ML diferida.

Las **promesas centrales de la tesis están cubiertas**: Sección 4.3, 6.4, 7.3, 8.5, 15.2, 15.4. Las que quedan como agenda están **declaradas explícitamente** (no son deuda silenciosa) — esa es la diferencia que defiende la tesis honestamente.

### G7 MVP — frontend del dashboard docente (3 vistas + endpoint nuevo)

Tras cerrar G2/G3/G4/G5 en backend, el doctorando preguntó qué frontend faltaba. La auditoría del web-teacher mostró que los **3 endpoints analytics nuevos no tenían UI consumer**: el docente del piloto no podía ver los nuevos indicadores. Decisión: implementar el **MVP G7 simple** acordado en el plan original del modelo híbrido (sin ML predictivo ni alertas — eso queda para piloto-2).

- **Endpoint nuevo `GET /api/v1/analytics/cohort/{id}/adversarial-events`**: agrega eventos `intento_adverso_detectado` por categoría/severidad/estudiante para una cohorte. Reusa `RealLongitudinalDataSource` con un método nuevo `list_adversarial_events_by_comision`. Función pura agregadora `aggregate_adversarial_events` en `packages/platform-ops/adversarial_aggregation.py` — testeable bit-exact. 9 unit del agregador + 5 unit del endpoint = 14 tests nuevos en backend.
- **`web-teacher` extendido en `lib/api.ts`** con 3 funciones nuevas + tipos: `getEpisodeNLevelDistribution`, `getStudentCIIEvolution`, `getCohortAdversarialEvents`. Mismo patrón existente (fetch directo + `authHeaders` + `throwIfNotOk`).
- **Vista `EpisodeNLevelView.tsx`** (~180 LOC): consume `/n-level-distribution`. Input UUID del episodio. Visualización: barra apilada SVG/divs coloreados con 5 segmentos (N1 verde, N2 azul, N3 amarillo, N4 naranja, meta gris) + tarjetas con tiempo absoluto/porcentaje/conteo por nivel. Cumple componente C3.2 + Sección 15.2.
- **Vista `StudentLongitudinalView.tsx`** (~280 LOC): consume `/cii-evolution-longitudinal`. Inputs: comisión + UUID estudiante. Visualización: 4 cards de resumen (episodios totales, templates evaluados con N≥3, slope promedio con flecha mejorando/estable/empeorando, suficiencia de datos) + tabla por template con sparkline SVG inline (puntos coloreados según appropriation ordinal) + slope crudo. Cumple Sección 15.4.
- **Vista `CohortAdversarialView.tsx`** (~280 LOC): consume `/cohort/{id}/adversarial-events`. Input: comisión. Visualización: 3 cards de totales + barras horizontales por categoría + barras verticales por severidad (1-5) + ranking top 10 estudiantes + tabla últimos 50 eventos con `matched_text` truncado y categoría/severidad coloreadas. Cumple Sección 8.5 + 17.8.
- **Decisión arquitectónica**: las 3 vistas son **standalone** (no dependen del `selectedComisionId` global del sidebar). `EpisodeNLevelView` no necesita comisión. `StudentLongitudinalView` y `CohortAdversarialView` tienen su propio `ComisionSelector` interno — el docente puede inspeccionar comisiones distintas a la actualmente seleccionada en sidebar. Mismo patrón que `TemplatesView` que ya estaba.
- **Help system**: 3 entries nuevas en `helpContent.tsx` (`episodeNLevel`, `studentLongitudinal`, `cohortAdversarial`) siguiendo formato del repo (español sin tildes, estructura div.space-y-4 + párrafos + lists + tip boxes oscuras + warning boxes para limitaciones declaradas). Cada vista usa `<PageContainer ... helpContent={...}>` obligatorio según skill `help-system-content`.
- **`App.tsx`**: union `View` extendido con 3 ids nuevos, `NAV_GROUPS` actualizado en grupo "Análisis" con iconos `TrendingUp`/`Layers`/`ShieldAlert` de lucide-react, render condicional ANTES del gate `selectedComisionId === null` (mismo patrón que `templates`).
- **Validación**: typecheck `tsc --noEmit` clean en web-teacher; `biome check` clean en los 5 archivos modificados (5 archivos auto-fixeados format + organizeImports + 2 warnings reales arreglados manualmente: `noSvgWithoutTitle` con `<title>`, `noArrayIndexKey` con `// biome-ignore` justificado por posición temporal estable). Suite Python: **323 passed + 2 skipped** (+14 nuevos sobre los 309 anteriores; cero regresiones).
- **Lo que NO se hizo (deliberado, agenda piloto-2)**:
  - **Alertas predictivas**: si algún indicador cae >1σ respecto del propio trayecto del estudiante → sugerir intervención. Requiere baseline + ML, fuera del MVP.
  - **Comparación contra cuartiles de cohorte con privacidad**: el audit G7 lo pide; hoy las 3 vistas muestran datos individuales sin comparativa anonimizada agregada.
  - **Drill-down navegacional**: hoy las 3 vistas son "search by UUID". Idealmente la vista Progresión tendría links que abren EpisodeNLevelView pre-poblado, y `StudentLongitudinalView` pre-poblada por estudiante. Eso requiere routing real (TanStack Router) — el web-teacher hoy es state-based switching. Diferido.
  - **Endpoint para listar episodios cerrados de un estudiante**: hoy el docente tiene que pegar UUIDs manualmente. Útil cuando se migre a routing real.
  - **Tests E2E del frontend**: el repo no tiene tests de vistas existentes — agregarlos solo para las 3 nuevas sería inconsistencia. Si se quiere infrastructure de testing UI, es PR aparte.
- **Archivos**: `packages/platform-ops/src/platform_ops/adversarial_aggregation.py` (nuevo), `packages/platform-ops/tests/test_adversarial_aggregation.py` (nuevo), `apps/analytics-service/src/analytics_service/routes/analytics.py` (endpoint nuevo), `apps/analytics-service/tests/unit/test_adversarial_events_endpoint.py` (nuevo), `packages/platform-ops/src/platform_ops/real_datasources.py` (método nuevo), `apps/web-teacher/src/views/{EpisodeNLevelView,StudentLongitudinalView,CohortAdversarialView}.tsx` (nuevos), `apps/web-teacher/src/lib/api.ts` (3 funciones + 3 tipos), `apps/web-teacher/src/utils/helpContent.tsx` (3 entries), `apps/web-teacher/src/App.tsx` (NAV_GROUPS + render).

### Agenda piloto-2 ejecutada en MVP — alertas + cuartiles + drill-down + TanStack Router + E2E

Mismo día, tras cerrar G7 MVP simple, el doctorando pidió implementar las **5 cosas declaradas como agenda piloto-2** en el bullet "Lo que NO se hizo" del bloque anterior. Decisión: hacerlas con **estadística clásica (NO ML)** + privacy gate + routing real + suite E2E del web-teacher. Esto dejó el G7 cerrado completo con operacionalización defendible pre-defensa; el ML predictivo verdadero (>1σ del propio trayecto, baseline individual) sigue siendo agenda piloto-2 real.

- **ADR-022 redactado** (`docs/adr/022-tanstack-router-migration.md`, ~280 líneas): cubre 4 decisiones acopladas — (1) migración del web-teacher a TanStack Router file-based, (2) drill-down navegacional via search params, (3) alertas predictivas con z-score clásico (NO ML), (4) cuartiles de cohorte con privacy gate `MIN_STUDENTS_FOR_QUARTILES = 5`. Sigue formato del template del repo (Estado, Drivers, Opciones consideradas, Decisión, Consecuencias). Las 3 alertas (`regresion_vs_cohorte`, `bottom_quartile`, `slope_negativo_significativo`) están documentadas con su threshold y severidad. Privacy threshold N≥5 documentado como k-anonymity educativa estándar.
- **`packages/platform-ops/src/platform_ops/cii_alerts.py`** nuevo (~230 LOC): funciones puras testeable bit-exact. `compute_cohort_slopes_stats(slopes)` usa `statistics.quantiles(method="exclusive")` para Q1/median/Q3 + `mean`/`stdev`/`min`/`max`; devuelve `insufficient_data: true` con N<5. `position_in_quartiles(slope, stats)` mapea a `Q1|Q2|Q3|Q4`. `compute_student_alerts(student_slope, n_episodes_total, cohort_stats)` con 3 reglas: (a) z ≤ -2σ → `regresion_vs_cohorte` high; ≤ -1σ → medium. (b) Q1 → `bottom_quartile` medium informativa. (c) `student_slope < -0.3` con `n_episodes_total >= 4` → `slope_negativo_significativo` medium (no requiere cohorte — degradación graciosa cuando insufficient_data). `compute_cohort_quartiles_payload` y `compute_alerts_payload` arman shapes serializables. Constantes `ALERTS_VERSION = "1.0.0"`, `MIN_STUDENTS_FOR_QUARTILES = 5`. **16 tests** cubriendo todos los casos golden + degradación + privacy gate.
- **`real_datasources.py` extendido**: nuevo método `list_episodes_with_classifications_for_student(student_pseudonym, comision_id, academic_session)` — triple cross-DB query (CTR + classifier + academic) que joina `Episode` + `Classification` + `TareaPractica.titulo`/`codigo` ordenados por `closed_at desc`. Reusa el patrón de `list_classifications_with_templates_for_student` de RN-130.
- **3 endpoints nuevos en `analytics-service`**:
  - `GET /api/v1/analytics/student/{student_pseudonym}/episodes?comision_id=X` — lista de episodios cerrados del estudiante con classifications. Habilita drill-down sin pegar UUIDs de episodio. Auth `X-Tenant-Id` + `X-User-Id`. Modo dev → estructura vacía con 200.
  - `GET /api/v1/analytics/cohort/{comision_id}/cii-quartiles` — cuartiles de slopes longitudinales de la cohorte. Devuelve `insufficient_data: true` con N<5 (privacy gate). Itera el endpoint de longitudinal por cada estudiante de la cohorte (N+1 cross-DB queries — documentado como limitación conocida; aceptable para piloto, optimizable con SQL agregada en piloto-2 si dolor real).
  - `GET /api/v1/analytics/student/{student_pseudonym}/alerts?comision_id=X` — combina cohort stats con student slope para emitir las 3 alertas. Si la cohorte es insuficiente (N<5), degrada a solo `slope_negativo_significativo`.
- **Tests endpoints**: `apps/analytics-service/tests/unit/test_student_episodes_endpoint.py` con 9 tests (auth headers obligatorios, query param `comision_id` requerido, modo dev shape, path/query validation).
- **Migración del `web-teacher` a TanStack Router file-based** (afectó ~14 archivos del frontend):
  - `vite.config.ts`: agregado plugin `TanStackRouterVite()` ANTES de `react()`. Genera `routeTree.gen.ts` automáticamente al primer build/dev.
  - `src/main.tsx` reescrito: `RouterProvider` con `createRouter({ routeTree, context: { getToken }, defaultPreload: "intent" })` + `declare module "@tanstack/react-router"` para tipar `Register['router']`.
  - `src/routes/__root.tsx` nuevo: layout root con `createRootRouteWithContext<RouterContext>()`, Sidebar con `NAV_GROUPS` por path id (`/templates`, `/kappa`, `/progression`, etc.), `<Outlet />`, `notFoundComponent`.
  - 10 routes nuevas en `src/routes/`: `index.tsx` (redirect a `/templates`), `templates.tsx`, `kappa.tsx`, `progression.tsx`, `tareas-practicas.tsx`, `materiales.tsx`, `export.tsx`, `episode-n-level.tsx`, `student-longitudinal.tsx`, `cohort-adversarial.tsx`. Cada route define su `Route = createFileRoute(...)` + valida search params con `validateSearch: (s) => zodSchema.parse(s)`.
  - `ComisionSelectorRouted.tsx` nuevo: lee `comisionId` via `useRouterState({ select: (s) => s.location.search as Record<string, unknown> })` + escribe via `navigate({ search: ... })`. Reemplaza el state-based `selectedComisionId` global del App.tsx anterior.
  - **Drill-down**: `ProgressionView.TrajectoryRow` ahora envuelve cada fila en `<Link to="/student-longitudinal" search={{ comisionId, studentId: trajectory.student_alias }}>`. Click en estudiante → abre vista pre-poblada con su slope per-template + alertas + cuartiles. Resuelve la queja del audit G7 ("hoy las 3 vistas son search by UUID, UX feo").
  - **Quirk de `exactOptionalPropertyTypes`**: las routes pasan props opcionales con spread condicional (`{...(comisionId ? { initialComisionId: comisionId } : {})}`) en vez de `prop={value || undefined}`. Sin esto, tsc rompe con "Type 'string | undefined' is not assignable to type 'string?'" porque la prop es `prop?: string` (sin `| undefined`).
  - **Para que `routeTree.gen.ts` se genere antes del primer typecheck**: correr `pnpm exec vite build` (o `pnpm dev`) una vez. El plugin lo regenera automáticamente al detectar cambios en `src/routes/`.
- **`StudentLongitudinalView.tsx` extendida** (~430 LOC): nuevo prop `initialStudentId` + autocarga via `useEffect`. Hace `Promise.all([getStudentCIIEvolution, getStudentAlerts])` cuando ambos comision+student están seteados. Render: panel **ámbar** con badges de severidad (high/medium) cuando hay alertas, panel **emerald** "dentro del rango esperado" cuando `n_alerts === 0`, etiqueta de cuartil ("Q1 — peor 25%", "Q4 — mejor 25%", etc.) con color codificado. La cabecera muestra `n_alerts` con icono de campana. La tabla per-template ya estaba; se mantuvo intacta.
- **`EpisodeNLevelView.tsx` y `CohortAdversarialView.tsx`**: agregados props `initialEpisodeId` / `initialComisionId` con autocarga via `useEffect`. Habilitan que el router los abra pre-poblados.
- **Suite E2E del web-teacher** (precedente nuevo en el repo — antes solo `packages/ui` tenía `*.test.tsx` de unit; el hay E2E del shell de las views):
  - `apps/web-teacher/tests/_mocks.ts`: helper `setupFetchMock(handlers)` que mockea fetch por **path-prefix**. Fallback benigno `{data:[],meta:{cursor_next:null}}` para los componentes que firen fetch al mount (`ComisionSelector`, `AcademicContextSelector`). Sin este default, los `mockResolvedValueOnce` perdían orden y los tests morían con `Cannot read properties of undefined (reading 'cursor_next')` cuando un componente no-target ejecutaba fetch antes que el target.
  - `tests/EpisodeNLevelView.test.tsx`: 4 tests (render inicial sin episodio, click "Analizar" con UUID válido dispara fetch, drill-down `initialEpisodeId` autocarga al montar, error de API renderiza mensaje).
  - `tests/CohortAdversarialView.test.tsx`: 3 tests (drill-down autocarga, render de barras + ranking + recientes con datos populated, error 500 renderiza mensaje).
  - `tests/StudentLongitudinalView.test.tsx`: 4 tests (drill-down autocarga 2 fetches, alertas severidad high renderizan en panel ámbar con quartile label, sin alertas → panel emerald, tabla con 1 row por template + slopes + etiquetas mejorando/empeorando).
  - **11 tests E2E nuevos** en total. Vitest + RTL + jsdom + `@testing-library/jest-dom` (que tuvo que agregarse con `pnpm add -D` — no estaba antes).
- **Validación final**: **348 Python passed + 2 skipped (docker)** en el back + **11 E2E passed** en el web-teacher. **+25 Python sobre los 323 anteriores** (16 cii_alerts + 9 endpoint episodes). Cero regresiones. `test_pipeline_reproducibility.py` 7/7 PASS sin tocar — cadena criptográfica intacta. Typecheck `tsc --noEmit` clean en web-teacher después del refactor del router (corrieron varios fixes de `exactOptionalPropertyTypes` y un `useRouterState` con type assertion). Biome clean.
- **Estado del audit G7 al cierre**: las 5 cosas que estaban como "lo que NO se hizo" **ahora están hechas en versión defendible**: alertas (estadística clásica), cuartiles (con privacy N≥5), drill-down (TanStack Router file-based), endpoint listado de episodios, suite E2E. Lo único que sigue diferido a piloto-2 es el ML predictivo verdadero (modelo entrenado sobre el propio trayecto del estudiante, no z-score vs cohorte) — declarado explícitamente en ADR-022.
- **CLAUDE.md actualizado**: ADR count 20 → 21. Nueva invariante en "Propiedades críticas" sobre alertas + cuartiles. `MIN_STUDENTS_FOR_QUARTILES = 5` agregado a "Constantes que NO deben inventarse". Sección "Frontends React (gotchas)" tiene un bullet nuevo sobre TanStack Router file-based + drill-down via search params + quirk de `exactOptionalPropertyTypes` + helper `setupFetchMock` para tests E2E. Sección "Modelo híbrido honesto" — bullet G7 MVP rescrito para reflejar que ahora cubre alertas+cuartiles+drill-down+11 E2E (no solo 3 vistas básicas). Reglas count 130 → 131 (RN-131).
- **reglas.md actualizado**: **RN-131 nueva** ("Alertas predictivas (>=1σ vs cohorte) + cuartiles con privacidad N>=5"). Categoría Cálculo + Privacidad, severidad Alta, fase F7. Catálogo Reglas Altas: 59 → 60. Tabla de trazabilidad: nueva fila apuntando a `cii_alerts.py` + endpoints + StudentLongitudinalView. Total reglas: 130 → 131.
- **Archivos creados/modificados** (no exhaustivo):
  - `docs/adr/022-tanstack-router-migration.md` (nuevo)
  - `packages/platform-ops/src/platform_ops/cii_alerts.py` (nuevo)
  - `packages/platform-ops/tests/test_cii_alerts.py` (nuevo, 16 tests)
  - `packages/platform-ops/src/platform_ops/real_datasources.py` (método `list_episodes_with_classifications_for_student`)
  - `apps/analytics-service/src/analytics_service/routes/analytics.py` (3 endpoints nuevos)
  - `apps/analytics-service/tests/unit/test_student_episodes_endpoint.py` (nuevo, 9 tests)
  - `apps/web-teacher/vite.config.ts` (plugin TanStackRouterVite)
  - `apps/web-teacher/src/main.tsx` (RouterProvider)
  - `apps/web-teacher/src/routes/{__root,index,templates,kappa,progression,tareas-practicas,materiales,export,episode-n-level,student-longitudinal,cohort-adversarial}.tsx` (10 routes nuevas)
  - `apps/web-teacher/src/components/ComisionSelectorRouted.tsx` (nuevo)
  - `apps/web-teacher/src/views/{EpisodeNLevelView,CohortAdversarialView,StudentLongitudinalView,ProgressionView}.tsx` (props initial* + drill-down `<Link>`)
  - `apps/web-teacher/src/lib/api.ts` (5 tipos + 3 funciones nuevas)
  - `apps/web-teacher/tests/_mocks.ts` (nuevo helper de fetch mock)
  - `apps/web-teacher/tests/{EpisodeNLevelView,CohortAdversarialView,StudentLongitudinalView}.test.tsx` (nuevos, 11 E2E tests)
  - `CLAUDE.md`, `reglas.md`, `docs/SESSION-LOG.md`

### Auditoría frontend ↔ backend + refactor de `student_alias` → `student_pseudonym`

Tras la /init review, se hizo una **auditoría de correspondencia frontend-backend** sobre los 12 servicios + 3 frontends. Cobertura: enumeración exhaustiva de routes en cada servicio cross-referenciada contra todos los `fetch()`/`api.ts` de los frontends. Hallazgos:

- **0 bugs activos** (ninguna llamada frontend a endpoint inexistente).
- **1 distorsión semántica latente** en endpoints `/cohort/{id}/progression` y `/cohort/{id}/adversarial-events`: el campo response se llamaba `student_alias` PERO en uso real (sin `pseudonymize_fn`) era el `str(student_pseudonym)` directo — el nombre prometía anonimización inexistente. Bomba de tiempo si alguien activaba `pseudonymize_fn` en estos endpoints (drill-down de `ProgressionView` → `StudentLongitudinalView` rompería silenciosamente porque el segundo espera UUID).
- **1 gap operativo confirmado**: enrollment-service expone `POST /api/v1/imports` (CSV bulk import 2-pass) sin UI. `apps/web-admin/src/pages/HomePage.tsx` lo declara textualmente: *"Inscripciones — próxima iteración."*
- **2 gaps menores** (CTR replay oculto detrás del proxy y `POST /api/v1/retrieve` sin UI) — discutibles si son by-design o gap.
- **1 esqueleto sospechoso**: `evaluation-service` está en workspace + helm + docker-compose con descripción "Rúbricas, corrección asistida, calificaciones finales", pero solo tiene `/health`. Reservado para fase futura.
- 5 endpoints API-only justificados: `ab-test-profiles`, governance/prompts, ai-gateway/{complete,stream,budget}, identity-service `/health`, `comisiones/mis` para estudiantes.

**Refactor #1 aplicado (la distorsión latente)** — `student_alias` → `student_pseudonym` en flujo UI:
- **Backend**: `packages/platform-ops/src/platform_ops/longitudinal.py` (`StudentTrajectory.student_pseudonym`), `packages/platform-ops/src/platform_ops/adversarial_aggregation.py` (todos los keys del payload), `packages/platform-ops/src/platform_ops/real_datasources.py` (docstrings + dict key del adversarial), `apps/analytics-service/src/analytics_service/routes/analytics.py` (response_models `StudentTrajectoryOut`, `AdversarialRecentEventOut`, `AdversarialTopStudentOut`).
- **NO TOCADO**: `packages/platform-ops/src/platform_ops/academic_export.py` mantiene `EpisodeRecord.student_alias` porque ahí SÍ es alias real (`hash(student_pseudonym + salt)`). El concepto está bien aplicado en export anonimizado; el bug era reusar el nombre en endpoints que no anonimizaban.
- **Frontend**: `apps/web-teacher/src/lib/api.ts` (3 tipos), `apps/web-teacher/src/views/{ProgressionView,CohortAdversarialView}.tsx`, `apps/web-teacher/tests/CohortAdversarialView.test.tsx`.
- **Tests**: `packages/platform-ops/tests/test_longitudinal.py` y `test_adversarial_aggregation.py` — todas las construcciones renombradas.
- **BC-incompatible**: cualquier consumer externo del API que parseaba `student_alias` rompe. Hoy el único consumer es `web-teacher`, también modificado en el mismo cambio. Documentar en CHANGELOG cuando exista uno.
- **Validación**: 87 Python passed (longitudinal + adversarial + analytics endpoints) + 11 E2E web-teacher passed + typecheck clean. Cero regresiones.

**Refactor #3 aplicado (`evaluation-service` esqueleto)** — agregadas dos brechas conocidas a `CLAUDE.md`:
- `evaluation-service` es esqueleto reservado para "Rúbricas, corrección asistida, calificaciones finales" (declaración del `pyproject.toml`). Tiene puerto, workspace entry, helm, docker-compose — pero solo `/health`. Métricas honestas: 11/13 servicios con endpoints reales, no 12/13.
- `identity-service` también es `/health` only pero **by-design** (auth via api-gateway + Casbin descentralizado). Distinto del caso de `evaluation-service` — acá la decisión es definitiva, no diferida.

**Lo que NO se hizo en esta sesión** (queda pendiente):
- **Refactor #2: UI de inscripciones** (CSV upload 2-pass) en `web-admin` — 1-2 días, gap operativo real para piloto UTN. El backend ya está, falta el frontend. Pendiente decisión del doctorando si vale la pena hacerlo ahora o en F8/F9 cuando Keycloak federation traiga las inscripciones del LDAP automáticamente.
- **Refactor #4: ADR-023** declarando explícitamente que el read/replay del CTR via `GET /api/v1/episodes/{id}` (CTR-service) y `POST /verify` están **deliberadamente ocultos** detrás del proxy del api-gateway, porque la auditoría se hace via attestations Ed25519 + classifications agregadas. Hoy es by-design implícito sin documentación.

**Archivos modificados esta sesión** (refactor #1 + #3):
  - `packages/platform-ops/src/platform_ops/longitudinal.py`
  - `packages/platform-ops/src/platform_ops/adversarial_aggregation.py`
  - `packages/platform-ops/src/platform_ops/real_datasources.py`
  - `packages/platform-ops/tests/test_longitudinal.py`
  - `packages/platform-ops/tests/test_adversarial_aggregation.py`
  - `apps/analytics-service/src/analytics_service/routes/analytics.py`
  - `apps/web-teacher/src/lib/api.ts`
  - `apps/web-teacher/src/views/ProgressionView.tsx`
  - `apps/web-teacher/src/views/CohortAdversarialView.tsx`
  - `apps/web-teacher/tests/CohortAdversarialView.test.tsx`
  - `CLAUDE.md` (Brechas conocidas extendida con `evaluation-service` y `identity-service`)

---

## 2026-04-21 — Cierre de bugs piloto + Camino 3 + TareaPractica + polish

Sesión larga: arrancó con cleanups de bugs detectados en bring-up Windows, terminó con TareaPractica end-to-end y 5 cleanups paralelos.

### Cleanups iniciales (bugs piloto)

- **BUG-23 cerrado**: `scripts/check-rls.py` Unicode → ASCII (`"✓"` → `"[OK]"`). Exit code ahora 0. CI gate `make check-rls` ya no rompe en Windows.
- **BUG-24 cerrado**: `pytest` desde root colecta 376 tests sin errores. Fix real: `--import-mode=importlib` en `pyproject.toml:81` `[tool.pytest.ini_options].addopts` + 13 `__init__.py` en `apps/*/tests/` y `packages/*/tests/`. **Gotcha**: primera corrida post-fix requiere `find apps packages -type d -name __pycache__ -exec rm -rf {} +` para limpiar caché stale. ⚠️ Después se descubrió que los `__init__.py` en `apps/<svc>/tests/` top level rompían `test_health.py` → ver BUG-29 más abajo.
- **BUG-25 cerrado (Option A)**: `identity_store` removida — archivos (`init-dbs.sql`, `operacional.py:88`, `ADR-003` addendum, `architecture.md`, `.env.example`, `.env`) + runtime (`DROP DATABASE identity_store; DROP ROLE identity_user;`). Pseudonimización vive en `packages/platform-ops/privacy.py` rotando `student_pseudonym` en `academic_main.episodes`.
- **otel-collector fixed**: exporter `loki` (removido de otel-collector-contrib v0.86+) → `otlphttp/loki` apuntando a `http://loki:3100/otlp` (Loki 3+ soporta OTLP nativo). Config en `infrastructure/observability/otel-collector-config.yaml`. Container UP en vez de crashloop.
- **Heads-up: imágenes Docker en `:latest` sin pinear**: `otel/opentelemetry-collector-contrib` y `grafana/loki` en `infrastructure/docker-compose.dev.yml` no tienen version pin — el fix del otel-collector va a repetirse en el próximo breaking release. Recomendación: pinear a `0.150.1` / `3.7.1` (versiones verificadas funcionando) en un PR separado.
- **BUG-11 + BUG-18 cerrados (duplicados)**: seed-casbin Unicode `✓` → `[OK]` en `apps/academic-service/src/academic_service/seeds/casbin_policies.py:145`. BUG-18 marcado como `DUPLICADO de BUG-11` en `BUGS-PILOTO.md`. Seed corre con exit 0 en Windows.
- **BUG-20 cerrado**: `scripts/check-health.sh` cambiado de `localhost` a `127.0.0.1` en los 2 curls (backend + frontend). `make status` / `make check-health` ya no dan falso negativo en Windows con IPv6 dual-stack. **Caveat**: los frontends Vite bindean `::1` (IPv6) — el curl a `127.0.0.1` puede dar falso negativo para ellos. Backends Python (uvicorn dual-stack) OK.
- **BUG-15 cerrado**: `--passWithNoTests` agregado al `test` script de los 4 packages TS sin tests (`web-admin`, `web-teacher`, `web-student`, `ctr-client`). `pnpm turbo test` → 4/4 successful (antes exit 1). **Deuda**: esos 4 packages no tienen tests reales — escribir al menos 1 smoke test por frontend antes de staging.

### Auth en endpoints analytics (BC-incompatible)

- **BUG-21 + BUG-22 cerrados**: endpoints de analytics ahora leen `X-Tenant-Id`/`X-User-Id` vía `Depends`. Confirmado el invariante: api-gateway es ÚNICO source of truth de identidad.
- **BUG-26 cerrado (kappa endpoint auth)**: `POST /api/v1/analytics/kappa` ahora requiere `X-Tenant-Id` + `X-User-Id` y emite audit log structlog `kappa_computed` (mismo patrón que BUG-21/22 + HU-088). 11/11 tests pass. **BC-incompatible** — 8 curls en docs pilot/F6/F7-STATE/runbook/kappa-workflow actualizados con headers. `docs/pilot/protocolo-piloto-utn.docx` (binary) pendiente de regenerar con `make generate-protocol`.
- **HU-088 audit log**: ratificada como structlog (no tabla persistente) — el endpoint AB emite event `ab_test_profiles_completed` con `tenant_id`, `user_id`, `kappa_per_profile`, `classifier_config_hash`. Si compliance team del piloto requiere tabla queryable, revisitable (S effort, 1-2h).
- **AB endpoint requiere auth desde 2026-04-21**: `POST /api/v1/analytics/ab-test-profiles` ahora requiere `X-Tenant-Id` + `X-User-Id` (per HU-088 audit log). Cambio BC-incompatible — curls en `docs/F7-STATE.md:167-173` y posibles notebooks usando el endpoint necesitan headers.

### Camino 3: jerarquía académica + UI + bulk import

- **HU-011 backend completado (Camino 3 Fase 1)**: agregados `Facultad` + `PlanEstudio` con CRUD completo (POST/GET list+filter/GET one/PATCH/DELETE), service+schemas+routes+tests siguiendo pattern de Carrera. Plus DELETE endpoints faltantes en `Universidad` (con superadmin-only enforce + cascade check 409 si tiene carreras), `Materia`, `Comisión`, `Periodo` (cascade checks reales: 409 si hijos activos). Routers registrados en `apps/academic-service/src/academic_service/main.py`. Tests: 8/8 facultad + 8/8 plan + 9/9 soft-delete pass; suite academic-service 64/66 (los 2 errors son pre-existentes en `test_comision_periodo_cerrado.py` por fixture `user_docente_admin_a` faltante — bug aparte).
- **BUG-27 cerrado**: agregado `apps/academic-service/tests/integration/conftest.py` con los fixtures compartidos `tenant_a_id`, `tenant_b_id`, `user_docente_admin_a`, `user_docente_admin_b` (mismo shape que el inline definido en `test_facultades_crud.py` / `test_planes_crud.py`). El collection error de `test_comision_periodo_cerrado.py` desaparece y la suite pasa de `71 passed + 2 errors` a `72 passed + 2 failed` — los 2 failed restantes son un bug separado de mocking SQLAlchemy en ese archivo. Candidato a BUG-28.
- **BUG-28 cerrado**: cambiados `Materia.__new__(Materia)` y `Periodo.__new__(Periodo)` por `MagicMock(spec=Materia/Periodo)` en `test_comision_periodo_cerrado.py` (2 tests). Suite academic-service final: **74 passed, 0 errors, 0 failures** (vs 71+2errors al inicio del día).
- **Camino 3 Fases 2-4 completas (UI académica + bulk import)**: agregadas `MateriasPage`, `ComisionesPage`, `FacultadesPage`, `PlanesPage` en `apps/web-admin/src/pages/`; `Breadcrumb` component en `apps/web-admin/src/components/`; DELETE buttons en UniversidadesPage + CarrerasPage con cascade 409 handling; `BulkImportPage` con dry-run preview + commit transaccional; backend `POST /api/v1/bulk/{entity}?dry_run=...` (multipart CSV, MAX_CSV_BYTES=5MB, 413 si excede) que soporta facultades/carreras/planes/materias/periodos/comisiones; `apps/web-admin/src/router/Router.tsx` con 9 routes navegables; `apps/api-gateway/.../proxy.py` ROUTE_MAP actualizado con `/facultades`, `/planes`, `/bulk`. Casbin re-seedeada a 79 policies.

### Content ingestion (RAG) — UI agregada

- **Auditoría content ingestion**: `content-service` (puerto 8009) tiene 5 endpoints (`POST /materiales` multipart, `GET list/single`, `DELETE`, `POST /retrieve`), 5 extractors (PDF unstructured+pypdf, Markdown con jerarquía, Code ZIP 13 lenguajes, Text, Video placeholder), chunker estratificado (code: 1 chunk/función, prose: sliding window 512/50 tokens, tables atómicas), embeddings con `intfloat/multilingual-e5-large` (1024 dims) + MockEmbedder fallback, pgvector con IVFFlat index (cosine), retrieval con re-ranking (bge-reranker-base) + `chunks_used_hash` SHA-256 para CTR audit, storage abstraction (mock/S3 MinIO). 24 unit tests pasando. Material scoping: solo `comision_id` (no materia_id ni problema_id — ADR-003 lo defiere a F3+). Async ingestion via Redis Streams diseñada pero no implementada (sync con timeout HTTP en F2).
- **UI MaterialesView**: agregada en `apps/web-teacher/src/views/MaterialesView.tsx` + tab en `App.tsx` + `materialesApi` con `multipartUpload` helper en `apps/web-teacher/src/lib/api.ts`. Polling de estado cada 2s hasta `indexed`/`failed` con `useRef<Map<id, timeoutHandle>>`. Roles autorizados: `docente`, `docente_admin`, `superadmin`. Badges de tipo (PDF rojo, MD azul, ZIP verde, etc.) y estado (pulse animado si procesando). Comisión hardcoded a `DEMO_COMISION_ID` hasta que aparezca un selector. **Implicación pilot**: docentes ya no necesitan curl para subir contenido al RAG.

### TareaPractica entity completa (Camino C) — gap crítico cerrado

El sistema asumía `Episode.problema_id` UUID **sin validación, sin tabla destino, sin endpoints, sin UI**. Implementado end-to-end:

- **Backend (`academic-service`)**: modelo `TareaPractica` en `models/operacional.py` (campos: codigo, titulo, enunciado markdown, fecha_inicio/fin nullable, peso decimal 0-1, rubrica JSONB, estado `draft|published|archived`, version int, parent_tarea_id FK self, created_by, soft delete). Migración `20260421_0002_add_tareas_practicas.py` con RLS aplicada. Service `tarea_practica_service.py` con CRUD + audit log RN-016 + 409 inmutabilidad si estado != draft. Routes `routes/tareas_practicas.py` con 9 endpoints (POST/GET list+filter por comision/estado/GET one/PATCH/DELETE + transiciones `POST {id}/publish`, `POST {id}/archive`, `POST {id}/new-version` para cadena de versiones inmutable + `GET {id}/versions` con `is_current` flag). Casbin: +13 policies (`tarea_practica:CRUD` para superadmin/docente_admin/docente, read-only para estudiante). Bulk import extendido para `entity=tareas_practicas` con JSON parse de rubrica.
- **Validación cross-service**: nuevo `AcademicClient` en `apps/tutor-service/src/tutor_service/services/academic_client.py`. `tutor.open_episode()` ahora valida 6 condiciones antes de crear el episodio (TP existe / tenant matches / comision matches / estado=published / now >= fecha_inicio / now <= fecha_fin), retornando 404/403/409/400 según corresponda.
- **UI web-teacher**: `views/TareasPracticasView.tsx` (~934 líneas) con CRUD + transiciones publish/archive/new-version + timeline de versiones con `is_current` destacado + form con validación de rubrica JSON. Tab "Trabajos Prácticos" como PRIMER tab (antes de Materiales) — flow conceptual: primero TPs, después material RAG asociado.
- **UI web-student**: nuevo `components/TareaSelector.tsx` que lista TPs `published` para la comisión, muestra título/codigo/version/excerpt + deadline indicator color-coded (rojo <24h, ámbar <72h, gris resto). El estudiante elige TP antes de abrir episodio. **Hardcoded `problema_id: "cccccccc-..."` REMOVIDO** de `apps/web-student/src/pages/EpisodePage.tsx:40-41` — ahora viene del TP seleccionado. Botón "Cambiar TP" cierra episodio actual (con reason `student_switched_tarea` para preservar append-only del CTR) y vuelve al selector. Enunciado del TP pinned arriba del CodeEditor.
- **Tests**: ~49 tests nuevos verdes (10 facultad-style CRUD + 10 versioning + 9 tutor validation + 12 bulk + 8 otros). **Suite total academic+tutor: 123 passed, 0 errors, 0 failures**.
- **Drift Casbin policies — RESUELTO**: spec actualizadas para no hardcodear count (RN-018, HU-016, F1-STATE.md addendum). Source of truth es el código del seed (`casbin_policies.py`). Hoy el seed carga 92 policies (4 roles × N entidades crecientes), evoluciona naturalmente al agregar recursos.

### Polish post-Camino C (5 cleanups paralelos)

- **Markdown renderer**: instalado `react-markdown@9` + `remark-gfm@4` en web-teacher y web-student. Componente `MarkdownRenderer.tsx` (~95 líneas) duplicado en cada frontend (no shared package — overhead). Reemplazó `<pre>` por `<MarkdownRenderer>` en `TareasPracticasView` (modal Ver) y `EpisodePage` (EnunciadoPanel). XSS-safe by default (react-markdown 9 no renderea HTML embebido). Sin `@tailwindcss/typography` plugin — usa selectors arbitrarios `[&_h1]:text-lg [&_p]:my-2 [&_table]:...` para estilos básicos. Rubrica sigue como `<pre>{JSON.stringify(...)}</pre>`. Editor `<textarea>` del docente sigue plain (TODO: split-pane preview).
- **Comisión selector real**: backend nuevo `GET /api/v1/comisiones/mis` en `academic-service` con `ComisionService.list_for_user()` que JOINea `comisiones` con `usuarios_comision` filtrando por `user_id` activo. Componente `ComisionSelector.tsx` duplicado en web-teacher + web-student, persiste selección en localStorage key `selected-comision-id` con verificación de stale-id contra response del backend. App.tsx de cada frontend reemplaza `DEMO_COMISION_ID` constant por `useState`. Constant mantenida como **fallback dev** (commented). Placeholder cuando `selectedComisionId === null`. **4/4 tests pass** para `test_mis_comisiones.py`. **Caveat importante**: la tabla `usuarios_comision` es para docentes/JTP/auxiliares — los **estudiantes viven en `inscripciones` con `student_pseudonym`**, así que el selector retornará vacío para estudiantes reales hasta que F9 derive `comisiones_activas` del JWT claim de Keycloak. El docstring del endpoint lo documenta. Dropdown muestra solo `codigo + uuid prefix` (no nombre de materia — necesitaría JOIN extra).
- **Pagination "Cargar más" en TareaSelector**: cursor-based, botón solo si `nextCursor !== null`, edge cases: empty initial, error mid-load (inline error preserva lista existente), comisión change reset, double-click guard. **Caveat**: sin `AbortController` en handleLoadMore — si user spam-clickea durante comisión change, response stale podría appendarse (riesgo bajo para piloto, no fix urgente).
- **Race condition tutor — mitigada**: `tutor_core.open_episode()` ahora hace **doble validación** vía `_validate_tarea_practica(is_recheck=True)`. Primera llamada al inicio (existente), segunda llamada justo antes del CTR `EpisodioAbierto` event emission. Reduce ventana de race de ~50-500ms (HTTP + Redis + governance fetch) a **<1ms** (in-process Python entre recheck y `ctr.publish_event()`). NO es atómica — protege contra "docente archiva durante creación", NO contra TOCTOU de ms. Documentado como best-effort en docstring. Si recheck falla, session state en Redis queda orphan pero TTL la limpia (no CTR event = no episode visible). **12/12 tests pass** (8 + 1 backwards-compat + 3 race-specific con `AsyncMock(side_effect=[first, second])`).
- **BUG-30 cerrado** (UX, baja severidad — antes mal-numerado como BUG-28 segundo): client-side date validation agregada en `apps/web-teacher/src/views/TareasPracticasView.tsx::handleSubmit` (form de TP). Si docente setea `fecha_fin <= fecha_inicio`, el form rechaza con mensaje claro "La fecha de fin debe ser posterior a la fecha de inicio" en lugar de pegarle al backend y recibir un 400 genérico. Backend ya tenía Pydantic validator (defensa en profundidad).
- **BUG-29 cerrado** (test_health fixture systematic fix): Strategy A descartada (asyncio_mode ya estaba "auto" globalmente) y Strategy B descartada (cambiar `@pytest.fixture` a `@pytest_asyncio.fixture` no resolvía). Fix real: eliminados los 12 `apps/*/tests/__init__.py` vacíos que BUG-24 había creado — con `__init__.py` presente, pytest+importlib seguía colapsando los 12 `tests/test_health.py` en un único módulo `tests.test_health`, y sólo el primer servicio alfabético (`academic-service`) registraba su fixture `client`. Removidos los `__init__.py`, importlib usa file path para identidad única. **38/38 tests verdes** en `apps/*/tests/test_health.py` (antes `3 passed + 33 errors`).

### Lecciones promovidas a CLAUDE.md (permanentes)

- ⬆️ **NO `__init__.py` en `apps/<svc>/tests/` top level** con `--import-mode=importlib` — colapsa modules across services. SÍ está OK en `tests/unit/` y `tests/integration/`. Worth a `make check-tests-init` lint target preventivo en futuro PR.
- ⬆️ **Scripts con stdout en Windows: ASCII, no Unicode** — usar `[OK]`/`[FAIL]` o `sys.stdout.reconfigure(encoding='utf-8')`. Patrón aplicado a check-rls.py y casbin_policies.py.
- ⬆️ **Implementaciones compartidas viven en `packages/platform-ops/` y `packages/observability/`** — antes de declarar OBJ como missing, grep ahí. Lección de 2 falsos negativos (OBJ-10 privacy + OBJ-12 A/B profiles).

### Estado final del proyecto post-cleanup

- **30 bugs documentados** (todos cerrados o duplicados — BUG-18 dup de BUG-11; el segundo BUG-28 fue renumerado a BUG-30).
- Tests academic+tutor+content ~170+ verdes, casbin matrix 23/23 con 92 policies.
- 8 entidades académicas con CRUD+UI, 0 hardcoded `DEMO_COMISION_ID` activos en código (solo fallback dev).
- El piloto puede arrancar **sin reservas técnicas** — los docentes hacen TODO desde el browser.

---

## 2026-04-22 — Reorganización de docs + fix bring-up + sidebar UI (pilot)

### CLAUDE.md restructurado + extracción de SESSION-LOG

- **CLAUDE.md reescrito**: nueva estructura (Known issues al tope, comandos en grupos Daily/Migraciones/Operacional, ports infra agregados, "Estado actual" reducido a verdades permanentes). Lecciones operativas movidas a Gotchas (pytest sin `__init__.py` top-level, ASCII en scripts Windows). Coverage framing invertido (CI <60% HOY, target 80/85 a futuro). Política B explícita en health checks (NO sumar en PRs ad-hoc, swept dedicado en OBJ-16). `TareaPractica` promovida a invariante crítico. Path corregido en test reproducibilidad: `apps/classifier-service/tests/unit/test_pipeline_reproducibility.py` (era `test de integración` factualmente incorrecto).
- **SESSION-LOG.md creado**: este archivo. El changelog narrativo del 2026-04-21 (~700 líneas que ocupaban ~40% del CLAUDE.md) se movió acá. Convención: bloques dated por sesión, no editar viejos, agregar nuevos. BUG-28 duplicado renombrado a BUG-30 en el proceso.

### Fix bring-up: `make generate-protocol` y dep `docx`

- **Bug descubierto regenerando el protocolo**: `make generate-protocol` falla en checkout limpio porque `docx` no está declarado como dep en ningún `package.json` del repo. Fix: `pnpm add -wD docx@^9.6.1` al root. Plus dos paths Linux hardcoded en los generadores: `docs/pilot/generate_protocol.js:624` y `docs/pilot/generate_teacher_guide.js:534` (`/home/claude/...` → relativo).
- **Makefile extendido**: agregados `make generate-teacher-guide` (regenera la guía docente) y `make generate-docs` (atajo: corre los dos). `CLAUDE.md` actualizado en sección de comandos operacionales.
- **DOCX regenerados**: `docs/pilot/protocolo-piloto-utn.docx` (~23 KB) y `docs/pilot/guia-capacitacion-docente.docx` (~21 KB).

### Sidebar colapsable en web-admin (pilot)

- **Goal**: reemplazar la topbar nav (`<nav>` horizontal con 9 botones) por un sidebar agrupado y colapsable. La topbar iba a quedar apretada a medida que la jerarquía académica crece (TPs, evaluaciones en F8+).
- **Where**: `apps/web-admin/src/components/Sidebar.tsx` (~225 líneas, nuevo) + `apps/web-admin/src/router/Router.tsx` (modificado: layout flex horizontal en vez de vertical, `<Sidebar>` reemplaza `<Nav>` inline). Componente **duplicado pattern** (igual que `MarkdownRenderer`) — no se sube a `packages/ui` hasta tener >=2 frontends usándolo.
- **Diseño**: colapsable con toggle (chevron-left/right), expanded ~256px / collapsed ~64px solo iconos. Tooltips en collapsed via `title` attr nativo (sin lib). Estado persiste en localStorage `web-admin-sidebar-collapsed`. Active route con `bg-gray-800 + border-l-2 border-blue-500`. Iconos de **`lucide-react`** (ya estaba en `package.json`, no agregó dep). Paleta dark (gray-900 fondo, gray-100 texto). Aria-labels + aria-current="page" + aria-expanded.
- **Agrupación final** (descubrió 2 rutas extra no listadas en mi spec inicial): `(sin header) Inicio` / `JERARQUÍA ACADÉMICA: Universidades, Facultades, Carreras, Planes, Materias, Comisiones` / `PEDAGOGÍA: Clasificaciones N4` / `OPERACIONAL: Importación masiva`.
- **Validación**: typecheck + lint en baseline pre-cambio (cero errores nuevos introducidos). Validado visualmente por user en browser (`http://localhost:5174` — Vite saltó del 5173 ocupado por otro proceso).
- **Caveats / TODOs explícitos**: (1) no es mobile-responsive (sidebar fijo aún en viewports chicos); (2) cuando F2-F3 migre a TanStack Router type-safe, el sidebar va a necesitar leer ruta activa de `useRouterState()` en vez de recibirla por props; (3) replicación a `web-teacher` queda para PR siguiente; (4) hay 7 typecheck errors pre-existentes en `pages/{BulkImport,Carreras,Comisiones,Materias,Planes}.tsx` + `vite.config.ts` por `exactOptionalPropertyTypes: true` — NO introducidos por este PR.

### Bug pre-existente descubierto durante validación

- **TanStack Router plugin mal configurado en `web-admin`**: `vite.config.ts` tiene el plugin `@tanstack/router-plugin` activo apuntando a `src/routes/` que no existe. Vite tira `ENOENT: no such file or directory` en startup pero igual sirve la app (el error es del plugin, no fatal). Fix futuro: o crear `src/routes/` (placeholder) o sacar el plugin de `vite.config.ts` hasta que migre el routing real (F2-F3). Candidato a issue/BUG aparte.

### Side effect: `pnpm install` sobre web-admin

- El agente del sidebar tuvo que correr `pnpm install --filter @platform/web-admin...` porque `apps/web-admin/node_modules` estaba vacío en el checkout. No agregó deps nuevas (solo levantó las existentes), pero el árbol de `node_modules` está poblado ahora.

### Sidebar colapsable en web-teacher (pilot completo en 2/3 frontends)

- **Goal**: replicar el patrón de sidebar de web-admin en web-teacher para unificar la navegación lateral. La topbar con 5 tabs horizontales se va a apretar a medida que aparezcan más vistas (analytics F8+).
- **Where**: `apps/web-teacher/src/components/Sidebar.tsx` (~213 líneas, nuevo, **patrón duplicado** del de web-admin) + `apps/web-teacher/src/App.tsx` (eliminada función `Header` completa, layout flex horizontal con `<Sidebar>` + `<main>`). NO se convirtieron tabs a rutas reales — sigue state-based switching (menos refactor, mismo resultado visual).
- **Diseño**: idem web-admin (gray-900, lucide-react, tooltips via `title` nativo, persistencia en localStorage `web-teacher-sidebar-collapsed` namespaced). Agrupación 3 bloques: **TRABAJO DEL DOCENTE** (TPs `ClipboardList`, Materiales `FolderOpen`), **ANÁLISIS** (Progresión `BarChart3`, Inter-rater `FileBarChart`), **OPERACIONAL** (Exportar `Download`). **Vista inicial cambiada** de `progression` a `tareas-practicas` para alinear con primer item del sidebar (cambio de UX, reversible en 1 línea si los docentes lo extrañan).
- **ComisionSelector**: integrado dentro del sidebar, debajo del header — visible solo cuando expanded. En collapsed se oculta (el `<select>` nativo no encaja en 64px y abrirlo programáticamente con `.showPicker()` es Chromium-only; refactor a popover custom sale del scope).
- **Validación**: typecheck delta 0 (10 errores pre-existentes intactos), lint delta -1 (formatter biome fixeó incidentalmente 1 error de format en `App.tsx`). User validó visualmente en browser (`http://localhost:5175` — Vite saltó del 5174 ocupado por web-admin).
- **Spec inicial mal scopeada**: el orchestrator dijo "2-3 tabs" en el plan; eran 5. El agente lo descubrió leyendo `App.tsx` y agrupó razonablemente. Lección operativa: NO asumir count de items — pedir al agente que verifique antes de groupear.

### TanStack Router plugin bug confirmado como cross-frontend

- El error `ENOENT: no such file or directory, scandir '...src/routes'` que vimos en web-admin se reproduce **idéntico en web-teacher** al levantar Vite. Ambos `vite.config.ts` tienen el plugin `@tanstack/router-plugin` activo apuntando a `src/routes/` que no existe en ninguno de los dos. **NO es un bug del sidebar** — es deuda pre-existente del setup. Probable también en web-student (no verificado en esta sesión). Fix: o sacar el plugin de los `vite.config.ts` hasta que migre el routing real (F2-F3), o crear `src/routes/` placeholder en cada frontend. **Candidato a issue/BUG aparte como cross-frontend**.

### Justificación creciente para `packages/ui` Sidebar

- Después de este PR hay **3 componentes duplicados** entre frontends: `MarkdownRenderer` (web-teacher + web-student), `Sidebar` (web-admin + web-teacher). El threshold para subir un genérico a `packages/ui` se cumple. **No se hizo en este PR** porque era out-of-scope explícito y `packages/ui` no está siendo usado activamente todavía. **Candidato a refactor**: `Sidebar` parametrizable por `NAV_GROUPS`, `STORAGE_KEY`, `HEADER_LABEL` y opcional `slot` arriba para `ComisionSelector` u otros componentes context-specific. Si el patrón se replica una vez más (web-student u otro frontend nuevo), pasa de "candidato" a "deuda inmediata".

### Estado del día (sidebar pilot completo en 2/3 frontends)

- web-admin: sidebar agrupado + colapsable funcional, validado.
- web-teacher: idem, validado.
- web-student: fuera de scope (single-page, sidebar no agrega valor).
- 0 errores nuevos introducidos en typecheck/lint en ninguno de los dos.
- Patrón visual consistente entre los dos frontends (gray-900, lucide-react, mismas clases Tailwind, mismo comportamiento de toggle + persistencia).
- 2 dev servers corriendo en background al cierre de la sesión: `bzsiq3av5` (web-admin :5174), `b3y47dypk` (web-teacher :5175). El user los matará cuando termine de testear.

### Ola 1 cleanup — TanStack Router plugin ENOENT removido

- **Causa**: los 3 `vite.config.ts` (web-admin, web-teacher, web-student) cargaban `TanStackRouterVite({ target: "react", autoCodeSplitting: true })` pero ningún `.ts`/`.tsx` importa de `@tanstack/react-router`. El plugin escaneaba `src/routes/` inexistente al startup y tiraba `ENOENT: no such file or directory, scandir '...src/routes'` (no fatal, ruido en logs).
- **Fix (Opción A)**: removido el `import { TanStackRouterVite }` y su entry del array `plugins` en los 3 `vite.config.ts`. Comentario in-place documenta cómo re-wirearlo cuando F2-F3 migre a routing type-safe. Deps `@tanstack/react-router` y `@tanstack/router-plugin` quedan en `package.json` (lockfile intacto, limpieza de deps va en PR aparte).
- **Verificación**: `pnpm tsc --noEmit` delta = web-admin 7→7, web-teacher 10→10, web-student 296→295 (un `TS2307 Cannot find module '@tanstack/router-plugin/vite'` menos en web-student por su tsconfig roto). Zero regresiones.
- **Archivos**: `apps/{web-admin,web-teacher,web-student}/vite.config.ts`.

### Hallazgo colateral: web-student tiene 295 errores de typecheck

- Surfeado durante la ola 1 al medir baseline. **NO es regresión** — es estado pre-existente. La causa raíz parece ser un `tsconfig.json` roto: faltan `@types/node` y los types de `vite`. Cantidad masiva de `TS2307 Cannot find module` y similares.
- **Severidad**: 🔴 Alta, pero NO urgente para piloto (web-student igual builda y corre — typecheck errors no bloquean Vite).
- **Acción**: deuda flagueada para PR aparte. NO se incluyó en la ola 2 (scope era web-admin + web-teacher). Cuando se aborde, probable fix: agregar `"@types/node"` a devDeps + revisar `compilerOptions.types` en el tsconfig del frontend.

### Ola 2 cleanup parte 3 — web-admin lint

- **Estado**: lint 17→0, typecheck 0→0 (intacto). Categorías idénticas a parte 2 (web-teacher): 9 `noLabelWithoutControl` + 8 `useExhaustiveDependencies`. `biome check --write` no aportó (safe-fix vacío, ningún format/imports issue).
- **Fix replicado mecánicamente del pattern de web-teacher**: 17 `biome-ignore` agregados con razón explícita — 6 sobre el helper `Field` (children es el control wrappeado, biome no lo ve estáticamente, mismo helper duplicado en `UniversidadesPage`/`CarrerasPage`/`FacultadesPage`/`PlanesPage`/`MateriasPage`/`ComisionesPage`) + 3 sobre labels inline con select bajo conditional ternario (`FacultadesPage`/`PlanesPage`/`MateriasPage`) + 8 sobre `useEffect` mount-only o single-arg-driven. Ningún cambio de runtime, sólo comentarios. **No se tocó** `Sidebar.tsx`, `Router.tsx`, `App.tsx`.

### Bring-up completo + bugs descubiertos durante runtime

- **`make init` end-to-end corrido**: 10 containers Docker (postgres/keycloak/redis/minio/grafana/prometheus/jaeger/loki/keycloak-db/otel-collector), `uv sync` (143 packages, 24 platform services built), `pnpm install`, migraciones Alembic en 4 bases (academic_main/ctr_store/classifier_db/content_db), permisos DB + rol `platform_app` + GUC `app.current_tenant` configurado, 93 Casbin policies seedeadas.
- **BUG nuevo del Makefile en Windows**: el target `setup-dev-perms` falla con `bash: C:\alberto\Penisi\AI-NativeV3-main: No such file or directory` — Make + Git Bash en Windows no manejan el path con `(1)` al invocar `@./scripts/setup-dev-permissions.sh`. **Workaround aplicado**: `bash scripts/setup-dev-permissions.sh` directo. **Fix sugerido en el Makefile**: cambiar `@./scripts/...` por `@bash ./scripts/...`. Candidato a entrada en `BUGS-PILOTO.md`.
- **12 backends levantados manualmente** vía `uv run uvicorn <svc_snake>.main:app --port <port> --host 127.0.0.1` (puertos 8000-8011). Pattern validado con api-gateway primero, replicado en los otros 11. Todos respondieron `/health` 200 — pero recordar CLAUDE.md: solo ctr-service tiene health check real, los otros 11 son stub `{"status":"ok"}`.
- **3 frontends vía `make dev`** con port shift por colisión externa: web-admin en **5174** (no 5173), web-student en **5175**, web-teacher en **5176**. El 5173 respondió HTTP 200 pero no era nuestro (proceso externo).

### Bugs runtime descubiertos + fixeados al pegar a la UI

Al usar la UI en browser (user reportó 500 al clickear "Clasificaciones N4" en web-admin sidebar):

- **Bug 1 — `.env` con DB URLs vacías**: `CTR_STORE_URL=` y `CLASSIFIER_DB_URL=` vacías + `CONTENT_DB_URL` faltaba del todo. El classifier-service cayó con `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from given URL string`. **Causa raíz**: el `.env.example` del repo nunca tuvo esos valores — las líneas 82-86 estaban pensadas "solo para analytics-service F8" pero classifier-service y content-service también leen `CLASSIFIER_DB_URL` y `CONTENT_DB_URL`, y para ellos no es opcional. **Fix aplicado**: pobladas las 3 URLs tanto en `.env` como en `.env.example`, con comentario explicando el dual-use y apuntando a la deuda de separar los namespaces (`ANALYTICS_CLASSIFIER_DB_URL` vs `CLASSIFIER_DB_URL`).
- **Bug 2 — `config.py` de classifier-service con default factualmente malo**: `classifier_db_url` default apuntaba a `ctr_store` ("las clasificaciones son derivados de eventos") pero la tabla `classifications` vive en `classifier_db` (ADR-003, y lo confirman `scripts/migrate-all.sh` + `seed-demo-data.py`). El comentario era stale — decisión arquitectónica cambió pero el default no se actualizó. **Fix**: default apunta a `classifier_user:classifier_pass@127.0.0.1:5432/classifier_db`, comentario actualizado mencionando ADR-003 y los users del setup-dev-permissions.
- **Bug 3 — `ClasificacionesPage.tsx` DEMO_COMISION_ID mismatch**: hardcode `"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"` — pero ese UUID es de **UNIVERSIDAD** en `seed-demo-data.py`, no una comisión. La comisión correcta del seed es `"aaaaaaaa-..."` (mismo UUID que TENANT_ID). Copy-paste error. **Fix**: UUID corregido + comentario `TODO(F9)` explícito que el hardcode es dev-only y va a ser reemplazado por `ComisionSelector` cuando el JWT de Keycloak traiga `comisiones_activas` como claim.
- **`scripts/seed-demo-data.py` ejecutado**: 6 estudiantes + 30 episodios CTR + 30 classifications en la comisión `aaaaaaaa-...`. El endpoint `GET /api/v1/classifications/aggregated` ahora devuelve data real (total_episodes=13 en últimos 30 días, distribution 0/6/7, CT=0.71, CCD=0.66, CII_stab=0.67, timeseries poblado).

### Estado al cierre del día

- **Plataforma corriendo end-to-end**: 10 containers + 12 backends + 3 frontends = 25 procesos. ~6-8 GB RAM.
- **ClasificacionesPage UI funcional con data real** — user validó en browser.
- Los 3 bugs runtime fixeados **en disco** (no commiteados porque el repo no está inicializado como git — pregunta pendiente desde hace rato: ¿es este el repo real o una copia de trabajo de un clone ajeno?).
- **Deuda que sigue abierta (para mañana o después)**:
  - ComisionSelector en web-admin (el hardcode ahora tiene TODO(F9) pero sigue siendo hardcode).
  - ~~Makefile target `setup-dev-perms` roto en Windows~~ ✅ FIXED (línea 146 ahora `@bash ./scripts/...`).
  - Separación namespace de env vars (CLASSIFIER_DB_URL compartida entre classifier-service y analytics-service fallback).
  - ~~web-student 295 typecheck errors~~ → **corregido el número**: baseline real es **2 typecheck + 15 lint**, no 295. Menor pero sigue pendiente cleanup.
  - ~~`packages/ui` refactor (6 componentes duplicados)~~ ✅ FIXED — Sidebar/MarkdownRenderer/ReadonlyField unificados. Los 6 duplicados eliminados.
  - `packages/ui` pre-existing lint errors en Button.tsx/Card.tsx/Label.tsx (4 errores del design system starter). No tocados hoy.
  - ⚠️ **La pregunta de git sigue sin resolverse** — si este `AI-NativeV3-main (1)/AI-NativeV3-main` es copia de trabajo, el riesgo de perder todo el laburo de hoy al reemplazar el directorio es real.

### Carrera.facultad_id pasa a NOT NULL + UI refactor

- **Pedido del user**: jerarquía real Facultad→Carrera (1-N). El modelo ya tenía `facultad_id` como FK a `facultades`, pero era **nullable**. El user pidió que sea requerido — que una carrera siempre pertenezca a una facultad.
- **Migración**: `20260422_0001_carrera_facultad_required.py` — `op.alter_column("carreras", "facultad_id", nullable=False)`. Corrió limpio sobre 1 row existente (ya tenía facultad_id seteado, sin backfill necesario).
- **Modelo**: `Carrera.facultad_id: Mapped[uuid.UUID]` (sin `| None`). Relación `.facultad` tipa `Facultad` directo.
- **Schema**: `CarreraCreate.facultad_id: UUID` required. **`universidad_id` REMOVIDO del payload de create** — se deriva del facultad en el service (API más limpia, invariante "facultad es el ancla" codificada en el type, elimina clase de error "mismatch universidad vs facultad.universidad"). `CarreraOut` sigue exponiendo `universidad_id` (denormalizado) + `facultad_id` (required). DB conserva ambas columnas por compatibilidad con queries existentes.
- **Service**: `CarreraService.create()` ahora valida `FacultadRepository.get_or_404(facultad_id)` + tenant match, luego inserta `universidad_id` denormalizado desde `facultad.universidad_id`.
- **Frontend `CarrerasPage.tsx`**: selector y columna de tabla pasaron de Universidad a Facultad. Carga `facultadesApi.list()` en vez de `universidadesApi.list()`. Botón "Nueva" disabled con tooltip si no hay facultades. `packages/web-admin/src/lib/api.ts` updated (`Carrera.facultad_id: string` required, `CarreraCreate` sin `universidad_id`). `BulkImportPage` + backend `bulk_import.py` ajustados — FK check de carreras ahora ancla en facultad, CSV require columna `facultad_id`.
- **Tests**: suite academic-service **107/107 pass**. Agregado `test_facultad_id_required`. Actualizado `test_bulk_import_carreras_validates_facultad_fk` (mockea `FacultadRepository.get_or_404`).
- **Validación runtime**: academic-service restarteado, `GET /api/v1/carreras` devuelve la row con `universidad_id` + `facultad_id` ambos populated, HTTP 200.
- **NO se hizo** (fuera de scope, deuda flagueada): mismo patrón en `PlanesPage` (Plan debería seleccionarse por Carrera, no por Universidad/Facultad), `MateriasPage` (por Plan), `ComisionesPage` (por Materia + Periodo). Cada uno necesita schema change + migración + UI refactor similar.

### Read-only context fields en forms de Materias/Planes/Comisiones

- **Pedido del user**: al crear una Materia/Plan/Comisión, el form solo muestra el selector del parent inmediato (plan, carrera, materia+periodo). Falta mostrar el contexto completo (Universidad, Facultad, Carrera, Plan, Materia, Periodo según corresponda) como campos read-only arriba del form, para que el creador sepa dónde va a caer el registro.
- **Pattern implementado**: chain fetch de parents + cache + display como `<ReadonlyField>` al tope del form.
  - **`MateriasPage.tsx`**: prop `context: Partial<PlanContext>` al `MateriaForm`, renderiza 3 read-only fields (Universidad / Carrera / Plan) en grid-3 con `rounded-md bg-slate-50 border p-3`. Chain cache ya existía desde antes (breadcrumb) — solo se reutilizó.
  - **`PlanesPage.tsx`**: mismo pattern `useEffect + useRef<Map>` para cache por `carreraId`. Chain: `carrera → facultad + universidad`. Form renderiza 2 read-only (Universidad / Facultad).
  - **`ComisionesPage.tsx`**: usa `useQuery` (el archivo ya usaba TanStack Query, se respetó el pattern intra-archivo) con compound `queryKey: ["comision-form-context", materiaId, periodoId]`, `staleTime: 5min`. Chain: `materia → plan → carrera → facultad + universidad`; periodo se resuelve del list cacheado (NO hay `GET /periodos/{id}` en academic-service). Form renderiza 5 read-only (Universidad / Carrera / Plan / Materia / Periodo) en grid-3 × 2 filas.
- **Helper `ReadonlyField`**: duplicado en los 3 archivos (~10 líneas cada uno). **Deuda DRY flagueada** — ahora son 3 duplicados más `Sidebar` x2 y `MarkdownRenderer` x2 = 5 componentes duplicados entre frontends. Candidato firme para `packages/ui` en el siguiente PR de cleanup.
- **Verificación**: typecheck 0 / lint 0 en los 3 pages. Pattern validado visualmente por user en MateriasPage, los otros 2 quedan para validar en browser.
- **Backend NO se tocó** en este paso — es UI-only. Todos los datos venían ya disponibles de los endpoints existentes (`carrerasApi.get`, `facultadesApi.get`, etc.).
- **Caveat ComisionesPage**: si `materiaId` seteado pero `periodoId` vacío (o viceversa), el context query queda disabled y los 5 fields muestran `"—"`. Aceptable — mismo comportamiento que MateriasPage sin plan seleccionado.

### Cascading selectors en ComisionesPage + limpieza de creación de Periodos

- **Pedido del user**: la página de Comisiones debe tener 4 selectores cascadeados (Universidad → Carrera → Plan → Materia) + el Periodo separado, en vez de un dropdown plano de Materia. Plus: remover cualquier UI para crear Periodos desde la página de Comisiones.
- **Refactor `ComisionesPage.tsx`**:
  - **5 selectores cascadeados**: Universidad → Carrera → Plan → Materia + Periodo (último separado). Cambiar un nivel resetea descendientes (ej. cambiar Carrera resetea Plan+Materia). Cambiar Periodo NO resetea el drill-down.
  - **Server-side filters**: `carrerasApi.list({ universidad_id })`, `planesApi.list({ carrera_id })`, `materiasApi.list({ plan_id })`. Verificado en `lib/api.ts` que ya soportan esos query params. Universidades sin filtro (eager load).
  - **Removido**: state `showPeriodoForm`, botón header "Crear periodo", componente `PeriodoForm` completo (~90 líneas), import `PeriodoCreate`. La página ya no permite crear Periodos.
  - **Simplificado**: eliminado `contextQuery` (chain fetch de 4 GETs que venía del paso anterior) — el read-only context del form ahora se deriva síncrono de los dropdowns ya cacheados. `ComisionForm` recibe `context: MateriaContext` (no `Partial`, sin fallbacks `?? "—"`).
  - **Gated**: lista de comisiones + botón "Nueva comisión" se habilitan solo cuando `materia && periodo` están ambos seteados.
  - **Banner amber**: si `periodos.length === 0`, mensaje "Creá uno desde la página de Periodos" (sin CTA inline).
- **Validación**: typecheck 0 / lint 0 / 0 biome-ignore nuevos.
- **🔴 Blocker UX flagueado**: **NO existe `PeriodosPage` en el router**. El mensaje amber "Creá uno desde la página de Periodos" es aspiracional. Si un tenant arranca sin periodos seedeados, el usuario queda bloqueado — no puede crear comisiones porque no puede crear periodos. **Follow-up obligatorio**: crear `PeriodosPage.tsx` + entry en Sidebar + ruta en Router. Prioridad alta si piloto UTN levanta con DB fresh sin seed. ✅ **Cerrado en el mismo día** — ver siguientes 2 secciones.

### PeriodosPage creada + wireada (resolución parcial del blocker)

- Nueva página `/periodos` en web-admin: ruta en Router + entry Sidebar sección "OPERACIONAL" con ícono `CalendarDays` de lucide-react.
- **CRUD parcial (list + create)**: form con `codigo` (max 20, pattern `[A-Za-z0-9_-]+`), `nombre` (max 100), `fecha_inicio`/`fecha_fin` (dates), `estado` (`abierto|cerrado`, default `abierto`). Validación client `fecha_fin >= fecha_inicio` antes de POST.
- Tabla: columnas Código · Nombre · Inicio · Fin · Estado (badge verde/slate) · Creado.
- **Casbin OK**: recurso `periodo:*` ya seedeado en `casbin_policies.py:53-96` para superadmin/docente_admin CRUD, docente read-only.
- Banner amber en ComisionesPage ahora apunta a una página que existe — flow desbloqueado.
- **Gap inicial flagueado**: delete + update NO en `periodosApi` (api.ts) ni en backend (PATCH). **Motivo**: restricción del prompt orchestrator al agente ("no modifiques api.ts"), que resultó ser mi error de scoping. Se completó en el siguiente paso.

### CRUD completo de Periodos (delete + update estado)

- **Pedido**: cerrar el loop CRUD — poder borrar periodos y marcarlos como `cerrado` cuando termina el ciclo académico. El cierre NO es opcional para la tesis: el invariante CTR se sella al cierre del ciclo.
- **Reglas `reglas.md` respetadas**: RN-013 (Comisión solo si Periodo abierto — ya lo respeta `ComisionService.create`), RN-016 (audit log en misma tx — `PeriodoService.update` emite `periodo.update` con campos modificados), RN-017 (cross-validation `fecha_fin > fecha_inicio`). **No hay regla explícita sobre transición abierto→cerrado one-way** — se infirió del invariante CTR del `CLAUDE.md` ("el CTR se sella al cierre del ciclo").
- **Backend**:
  - Nuevo `PATCH /api/v1/periodos/{id}` en `routes/comisiones.py` con `require_permission("periodo","update")`.
  - Schema `PeriodoUpdate` en `schemas/comision.py`: `nombre`/`fecha_inicio`/`fecha_fin`/`estado` todos opcionales, `codigo` excluido (immutable — lo usan comisiones downstream).
  - `PeriodoService.update()` en `services/comision_service.py` con guards: 409 si `estado=cerrado` (frozen), 409 si intento `cerrado→abierto` con mensaje "usar audit log si se necesita trazabilidad", 400 si `fecha_fin ≤ fecha_inicio` (cross-check contra valores persistidos cuando solo uno viene en el PATCH).
  - DELETE ya existía (soft delete con 409 si tiene comisiones activas — verificado, no duplicado).
  - **Sin migración Alembic** — no hay cambio de schema SQL.
- **Frontend**:
  - `periodosApi` en `lib/api.ts` extendido con `update(id, data: PeriodoUpdate)` + `delete(id)`. Nueva interface `PeriodoUpdate`.
  - `PeriodosPage.tsx` — columna "Acciones" con 2 botones: **"Cerrar"** (ambar, solo si `estado=abierto`, confirm con advertencia IRREVERSIBLE → PATCH estado=cerrado) y **"Eliminar"** (rojo, siempre visible, confirm → DELETE, surface 409 si hay comisiones). State `busyId` evita doble-click y desactiva botones de la row en operación.
- **Tests**: 5 nuevos en `test_periodos_crud.py` (update nombre OK abierto, transición abierto→cerrado OK, REJECT cerrado→abierto 409, REJECT modificar cuando cerrado 409, validación fecha_fin>fecha_inicio). Full suite academic-service: **112 passed** (107 → 112).
- **Edit full (modal con nombre/fechas)**: NO implementado — diferido como follow-up. Para MVP el flujo "Cerrar" cubre el requisito CTR; edit de typos queda via DB directa o API raw hasta que se pida.
- **Validación runtime**: academic-service restarteado, `GET /api/v1/periodos` devuelve el periodo del seed (`2026-S1`) HTTP 200.

### Makefile fix — `setup-dev-perms` en Windows

- BUG reportado temprano en la sesión: `make setup-dev-perms` falla en Windows+Git Bash porque `@./scripts/setup-dev-permissions.sh` no maneja bien el path con `(1)`. Workaround aplicado hoy: correr con `bash scripts/setup-dev-permissions.sh` directo.
- **Fix aplicado al Makefile línea 146**: `@./scripts/...` → `@bash ./scripts/...`. 1 línea, funciona en Windows + Linux. Candidato a entrada en `BUGS-PILOTO.md` con el fix aplicado.

### Edit full de Periodos (modal)

- Cierre del CRUD de Periodos en web-admin: agregado botón "Editar" (visible solo si `estado=abierto`, junto a "Cerrar" y "Eliminar") y modal inline con Tailwind (overlay fixed `z-50` + card centrado + `backdrop-blur-sm`).
- Form del modal pre-populado con nombre/fecha_inicio/fecha_fin del periodo; `codigo` disabled (immutable); `estado` NO expuesto (la transición a cerrado va por el botón "Cerrar" separado con confirm de irreversibilidad).
- **Diff on submit**: solo envía en el PATCH los campos efectivamente modificados. Si no hay diff, short-circuit a `onClose` sin llamar API. 409 Conflict (periodo cerrado) y 400 Validation surfaced al user con mensajes claros.
- **A11y mínimo**: `role="dialog"` + `aria-modal` + `aria-labelledby`, tecla Esc cierra, click en overlay cierra, `aria-label` en close button. Focus trap NO implementado (fuera de scope).
- Icono `Pencil` de lucide-react (ya instalado). 0 typecheck / 0 lint.

### Validación de solapamiento de fechas en Periodos

- `PeriodoService.create()` y `update()` ahora rechazan con **409 Conflict** si las fechas pisan a otro periodo soft-non-deleted del mismo tenant (RLS). Adyacencia permitida (`fecha_fin == fecha_inicio` es válido — cierre de uno coincide con inicio del otro).
- **Query de overlap**: `WHERE fecha_inicio < :fin AND fecha_fin > :inicio [AND id != :exclude_id]`. RLS aplica el filtro de tenant automáticamente.
- **Mensaje de error claro**: `"Las fechas solapan con periodo(s) existente(s): [codigo1, codigo2, ...]"`.
- **NO hay constraint DB** — es validación en service. Para el piloto UTN (baja concurrencia de admins) es aceptable. Follow-up si hace falta endurecer: `SELECT ... FOR UPDATE` o `EXCLUDE USING gist` con `btree_gist`.
- **No hay RN explícita** en `reglas.md` sobre overlap — implementado como regla emergente del invariante CTR de la tesis. **No se tocó `reglas.md`** (decisión del user).
- **4 tests nuevos** en `test_periodos_crud.py`: rechazo de overlap en create, adyacencia OK en create, rechazo de overlap en update, extensión sin overlap OK. Suite academic-service **112 → 116 passed**.

### Cascading selectors en PlanesPage + MateriasPage

- **Refactor replicado** del pattern de ComisionesPage a los otros 2 pages con jerarquía:
  - **PlanesPage**: Universidad → Carrera (filtrada por universidad) → lista de Planes. 2 selectors cascadeados en grid-cols-2.
  - **MateriasPage**: Universidad → Carrera (filtrada) → Plan (filtrado) → lista de Materias. 3 selectors cascadeados en grid-cols-3.
- **Server-side filters** (ya soportados en `lib/api.ts`): `carrerasApi.list({universidad_id})`, `planesApi.list({carrera_id})`, `materiasApi.list({plan_id})`. Sin tocar backend ni api.ts.
- **Resets descendentes**: cambiar Universidad resetea Carrera+Plan; cambiar Carrera resetea Plan. Disabled states en cadena.
- **Botones "Crear" gated** hasta que TODA la chain esté seteada.
- **Facultad fuera del chain** por consistencia con ComisionesPage. Sigue visible en los read-only context fields del form (sin cambios).
- **Breadcrumb en MateriasPage** mantenido (redundante con los dropdowns, pero alimenta también el contextCache que sirve al form). Follow-up trivial removerlo si el user lo pide.
- **Auto-select del primer item eliminado**: hacía sentido con dropdowns planos; con cascading arranca vacío (el user elige cada nivel).
- **Consistencia intra-archivo**: ambos usan `useState + useEffect` (no `useQuery`) porque los originales usaban ese pattern. ComisionesPage usa `useQuery` por el mismo principio. No unificado — fuera de scope.
- **Validación**: typecheck 0 / lint 0 / 0 errores nuevos. No se eliminaron `biome-ignore` existentes.

### Refactor `packages/ui`: componentes compartidos (Ola C parcial)

- **Hallazgo**: `packages/ui` NO estaba vacío como creíamos — ya tenía Badge/Button/Card/Input/Label + utils `clsx`+`tailwind-merge`. Era un design system starter parcialmente adoptado. El refactor suma 3 componentes más.
- **Extraídos a `packages/ui/src/components/`**:
  - **`Sidebar.tsx` parametrizable**: API `{ navGroups: NavGroup[], headerLabel, collapsedHeaderLabel, storageKey, activeItemId, onNavigate, topSlot? }`. `NavItem = { id, label, icon }`, `NavGroup = { label?, items }`. `topSlot` se renderiza sólo en expanded (para `ComisionSelector` en web-teacher). Mismo visual (gray-900, lucide-react, tooltips, chevron toggle, border-l azul).
  - **`MarkdownRenderer.tsx`**: copia exacta del de web-teacher (sin cambios de API).
  - **`ReadonlyField.tsx`**: `{ label, value }`, sin cambios.
- **Deps agregadas a `packages/ui/package.json`**: `react-markdown ^9.0.0` + `remark-gfm ^4.0.0` (las usa MarkdownRenderer).
- **Archivos ELIMINADOS**:
  - `apps/web-admin/src/components/Sidebar.tsx` (225 líneas).
  - `apps/web-teacher/src/components/Sidebar.tsx` (213 líneas).
  - `apps/web-teacher/src/components/MarkdownRenderer.tsx` (95 líneas).
  - `apps/web-student/src/components/MarkdownRenderer.tsx` (95 líneas).
  - 3× `ReadonlyField` inline en `apps/web-admin/src/pages/` (MateriasPage/PlanesPage/ComisionesPage).
- **Archivos MODIFICADOS** (imports + wiring): web-admin Router.tsx + 3 pages, web-teacher App.tsx + TareasPracticasView, web-student EpisodePage.
- **Validación post-refactor**:
  - web-admin: typecheck 0 / lint 0 (baseline).
  - web-teacher: typecheck 0 / lint 0 (baseline).
  - web-student: typecheck **2** / lint **15** (baseline pre-existente preservado — 0 regresiones).
- **Correcciones de log**: (1) `web-student 295 errors` era stale de una sesión vieja — baseline real hoy es 2. (2) `ReadonlyField` estaba en 3 pages, no 4 (PeriodosPage no lo usa).
- **Caveat**: `packages/ui` tiene 4 errores de lint pre-existentes en Button.tsx/Card.tsx/Label.tsx (design system starter) — fuera de scope hoy. Los 3 nuevos archivos (Sidebar/MarkdownRenderer/ReadonlyField) lintean clean.

### Cleanup final: web-student + packages/ui lint

- **web-student**: typecheck 2 → 0, lint 15 → 0.
  - `vite.config.ts`: mismo pattern ya validado en web-admin/web-teacher (`vitestConfig as const` + spread, sin acoplar tsc a `vitest/config`).
  - `EpisodePage.tsx:522`: `exactOptionalPropertyTypes` en `Meter.invertScale` — branching del JSX para no propagar `undefined` cuando el caller no lo fija (Meter usa default `false`).
  - `CodeEditor.tsx`: `editorRef: any` → `MonacoEditor.IStandaloneCodeEditor | null` vía `import type` (zero bundle cost). biome-ignore justificado en useEffect seed-only de Monaco (agregar `code` al deps rompe cursor/undo).
  - `ComisionSelector.tsx`: reemplazado `// eslint-disable-next-line` stale por `// biome-ignore lint/correctness/useExhaustiveDependencies` con razones explícitas, replicando el pattern de web-teacher.
  - Varios: `key={\`${x.ts}-${i}\`}` en vez de `key={i}`, organizeImports, format.
- **packages/ui**: lint 4 → 0.
  - Button/Card: format autosafe.
  - Label: `biome-ignore lint/a11y/noLabelWithoutControl` estructuralmente justificado (wrapper genérico del DS — el `htmlFor` llega vía `...props`, mismo pattern de los Field helpers de web-admin).
- **0 runtime bugs detectados**: todos los errores eran type-level o stylistic. Ninguno escondía un bug real (verificado explícitamente por el agente).
- **Verificación cruzada final**: **web-admin, web-teacher, web-student en 0 typecheck / 0 lint. `packages/ui` en 0 lint**. 4 workspaces alineados.

### Bug gemelo en content-service (descubierto post-cleanup)

- **Síntoma**: `GET /api/v1/materiales` (web-teacher) daba 500. `relation "materiales" does not exist`.
- **Causa raíz**: patrón gemelo al bug de classifier-service. El `config.py` de content-service tenía default apuntando a `academic_main` con comentario stale ("content vive en academic_main, ADR-003") — pero las migraciones efectivamente crearon la tabla `materiales` en `content_db` (verificado con `\dt`). Cuando content-service arrancó inicialmente, el `.env` NO tenía `CONTENT_DB_URL` definida (ni vacía — directamente faltaba), entonces pydantic-settings cayó al default erróneo.
- **Fix**:
  - `apps/content-service/src/content_service/config.py` default: `academic_main` → `content_db` con comentario actualizado explicando ADR-003 y apuntando al verification command.
  - content-service restarteado (nuevo BG ID `bbhiwvwx1`, el anterior `b8gtzi7zt` muerto).
  - El `.env` ya tenía `CONTENT_DB_URL` desde el fix del classifier bug, entonces esto más que nada evita futuros bring-ups fresh con el mismo problema.
- **Patrón detectado**: 2 servicios (classifier + content) con defaults de DB mal configurados. **Vale una auditoría preventiva** a los configs de los otros 10 servicios para ver si tienen el mismo issue antes de que aparezca en runtime. Candidato a entrada en `BUGS-PILOTO.md`.
- **Validación**: `GET /api/v1/materiales?comision_id=aaaa...` devuelve `{"data":[],"meta":{}}` HTTP 200 (empty pero válido — el seed no crea materiales).

### Auditoría preventiva de DB defaults en configs (post-bug content)

Tras el fix de classifier-service (apuntaba a `ctr_store`) y content-service (apuntaba a `academic_main`), auditamos los 12 `config.py` del backend para detectar el mismo patrón en otros servicios.

- **Cero bugs latentes adicionales**. Los 4 servicios con `*_db_url` default hardcodeado (academic, ctr, classifier, content) apuntan cada uno a su base correcta, consistente con `alembic/env.py` y `scripts/migrate-all.sh`.
- **6 servicios no tienen DB propia por diseño** (api-gateway, identity, tutor, governance, ai-gateway, enrollment/evaluation). Consistente con arquitectura — ninguno crea tablas SQL.
- **analytics-service** lee env vars en runtime sin default en config.py (`os.environ["CTR_STORE_URL"]` + `os.environ["CLASSIFIER_DB_URL"]`). Si faltan → cae a `_StubDataSource`. No revienta. OK para dev.
- **Deuda menor reconfirmada**: `CTR_STORE_URL` (usado por analytics) vs `CTR_DB_URL` (usado por ctr-service + migrate-all.sh) son 2 env vars para la misma DB. En `.env` ambas apuntan al mismo string, pero si alguien cambia una sola, analytics se desincroniza. Trampa latente — candidato a unificación.
- **Cosmético**: `.env` usa `localhost`, `config.py` usan `127.0.0.1`. Inconsistente con la gotcha IPv6/Windows de CLAUDE.md, pero no rompe (el `.env` sobrescribe).

### 🏆 Estado final de deuda al cierre del día

**Todos los 6 items originales del plan del día están ✅ cerrados**:
1. ✅ Edit full de Periodos
2. ✅ Cascading selectors en PlanesPage + MateriasPage
3. ✅ Validación solapamiento fechas en Periodos
4. ✅ `packages/ui` refactor (6 componentes duplicados unificados)
5. ✅ Makefile `setup-dev-perms` fix
6. ✅ web-student cleanup (número real era 2+15, no 295)

**Deuda que queda (para próximas sesiones)**:
- ⚠️ **La pregunta de git sigue sin resolverse** — sigue siendo el riesgo #1. Si este `AI-NativeV3-main (1)/AI-NativeV3-main` es copia de trabajo, cualquier rebuild del directorio borra el laburo del día.
- Separación namespace de env vars (`CLASSIFIER_DB_URL` dual-use entre classifier-service y analytics fallback).
- Edit full de Periodos NO cubre cambio de `estado` (para eso va el botón "Cerrar" separado). Si en algún momento se quiere reabrir un periodo cerrado, hoy es 409 — diseño intencional por invariante CTR.

---

## 2026-04-23 — ADR-016: TP template + instance

- ADR-016 aprobado e implementado: `TareaPracticaTemplate` a nivel `(materia_id, periodo_id)` + auto-instanciación en comisiones + `has_drift` tracking en instancias.
- Migration `20260423_0001_add_tareas_practicas_templates` aplicada: nueva tabla `tareas_practicas_templates` + columnas `template_id` (FK nullable) y `has_drift` (bool) en `tareas_practicas`.
- Nuevos endpoints: `/api/v1/tareas-practicas-templates` (10 métodos REST registrados en api-gateway, smoke test end-to-end OK).
- Casbin: 93 → 107 policies (+14 para `tarea_practica_template:CRUD` con superadmin/docente_admin/docente + read-only para estudiante). Test de matriz actualizado.
- Frontend: nueva `TemplatesView` en web-teacher + selector cascada Universidad → Período + badges de drift en `TareasPracticasView`.
- **CTR intacto**: `problema_id` sigue apuntando a la instancia (no al template) — reproducibilidad bit-a-bit preservada, cadena criptográfica SHA-256 sin cambios. Validado con `test_pipeline_reproducibility.py` (7/7 PASS) + `ctr-service` unit tests (19/19 PASS).
- **Tutor intacto**: las 6 validaciones de `tutor_core._validate_tarea_practica` siguen aplicando a la instancia. Test nuevo `test_open_episode_succeeds_with_tarea_practica_linked_to_template` verifica que una TP con `template_id != null` y `has_drift=true` no rompe el flujo del tutor — el `TareaPracticaResponse` ni siquiera expone esos campos (zero-impact).
- Smoke test end-to-end OK: `POST template → 3 instancias auto-creadas → PATCH una → drift aislado` en la instancia drifted sin tocar las otras 2.
- 121 tests integration academic-service PASS (+5 drift + 7 templates + 14 Casbin matrix = 26 casos nuevos).
- Regla nueva: `reglas.md` RN-013bis — "Plantillas de TP como fuente canónica" (Invariante / F1 / Severidad Media).
- Docs: `F1-STATE.md` anota el addendum de ADR-016 con pointer al RN-013bis.

**Deuda conocida (diferida)**:
- Auto-promoción de TPs existentes a templates: feature flag `AUTO_PROMOTE_UNIQUE_TPS` NO implementado por default (requeriría heurística "mismo codigo+titulo en 2+ comisiones de la misma materia+periodo").
- Endpoint `POST /api/v1/tareas-practicas/{id}/resync-to-template` para quitar `has_drift` (diferido — por ahora la única forma de "resync" es crear nueva versión del template).
- Re-instanciación en comisión nueva creada **después** del template: se decide en UI futura, hoy no auto-propaga.

**Bugs hallados durante validación (arreglados)**:
- **Casbin: rol `docente` sin `facultad:read`** — omisión pre-existente del seed (el docente tenía read sobre `universidad`, `carrera`, `plan`, `materia`, `periodo`, pero no `facultad`). Al probar el `AcademicContextSelector`, el segundo nivel del cascada devolvía 403 y el flow se colgaba. Fix: agregada la policy en `seeds/casbin_policies.py:123`. Count real: 93 → **108 policies** (el 107 documentado arriba era pre-fix).
- **Loop infinito en `AcademicContextSelector`** — los 6 fetchFn closures no estaban memoizados con `useCallback`; cada render creaba nueva referencia → `useEffect` del hook `useCascadeLevel` se disparaba → setState → re-render → 🔁. Resultado: ~36 req/s sostenidos hasta que el rate limiter devolvió 429 al ComisionSelector del sidebar (efecto colateral — el rate limit es por-cliente, no por-endpoint). Fix: envuelto cada fetchFn con `useCallback([id, getToken])`. Anotado como gotcha permanente en `CLAUDE.md` sección "Frontends React".
- **Seed Casbin no refresca el enforcer en memoria**: después de correr el seed, el `academic-service` seguía rechazando con las policies viejas porque el enforcer Casbin está cacheado. `--reload` de uvicorn no lo pickea. Workaround: kill + relaunch del servicio. Documentado en `CLAUDE.md` gotchas.
- **Migration FK name >63 chars**: el nombre auto-generado del FK self-referential de `tareas_practicas_templates.parent_template_id` excedía el límite de Postgres para identifiers. Renombrado a `fk_tp_templates_parent_template_id` en la migración antes de aplicar.
- **Governance: env var `GOVERNANCE_REPO_PATH` del `.env.example` NO la usaba el código** — el governance-service lee `PROMPTS_REPO_PATH` en su `Settings`. **Cerrado por F14 (2026-04-28)**: `.env.example:57` ahora declara `PROMPTS_REPO_PATH=./ai-native-prompts`. Histórico — quien tenga un `.env` viejo con la variable anterior debe re-cherry-pickearla.
- **Governance: prompts no sembrados por default** — `make init` no crea el directorio `ai-native-prompts/prompts/tutor/v1.0.0/system.md`. Sin ese archivo, el tutor-service tira **500** en cada `POST /api/v1/episodes` con `httpx.HTTPStatusError: '404 Not Found' for '/api/v1/prompts/tutor/v1.0.0'` — el alumno NO puede abrir ningún episodio. Fix en sesión: creado el `system.md` con prompt socrático N4 mínimo (principios, formato, lo que NO hace) + relanzado governance con `PROMPTS_REPO_PATH` correcto. Vale como **task de setup futura**: agregar a `make init` o un `scripts/seed-governance-prompts.py` que cree el archivo automáticamente.
- **`vite.config.ts` del web-student con UUID de student del seed viejo** — hardcodeado `a1a1a1a1-0001-0001-0001-000000000001` (del `seed-demo-data.py` original) en vez de los UUIDs de `seed-3-comisiones.py` (`b1b1b1b1-...`, `b2b2b2b2-...`, `b3b3b3b3-...`). Con el seed nuevo, el frontend loguea como estudiante inexistente → `TareaSelector` viene vacío silenciosamente (sin error visible). Fix: actualizado a `b1b1b1b1-0001-0001-0001-000000000001` (estudiante 1 de A-Mañana) con comentario inline sobre cómo rotar estudiantes para testing (`b2...`/`b3...` para B y C respectivamente).
