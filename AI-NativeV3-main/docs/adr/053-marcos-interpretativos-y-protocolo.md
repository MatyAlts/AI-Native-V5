# ADR-053 — Marcos interpretativos MI1-MI3 + Protocolo interpretativo de 7 principios

- **Estado**: Aceptado
- **Fecha**: 2026-05-17
- **Deciders**: Alberto Cortez (director tesis)
- **Tags**: paper-alignment, marcos-interpretativos, protocolo-interpretativo, anti-reificacion, pre-defensa
- **Motivado por**: auditoría `PlanMejora.md` (2026-05-17) que detectó 4 brechas conceptuales del paper Cortez & Garis (`paper_conaiisi.pdf`, versión 2026-05-16) sin reflejo en el repositorio: marcos interpretativos MI1-MI3 (paper §4.3), siete principios interpretativos (paper §7.3), marcador anti-reificación "perfil tipológico de apropiación" (paper §4.4) y cinco riesgos a priori (paper §8). Este ADR cierra la primera, segunda y tercera; la cuarta queda documentada en `docs/limitaciones-declaradas.md` (entrada 2026-05-17).

## Contexto y problema

La tercera ronda de consolidación del paper (2026-05-16) introdujo tres elementos epistemológicos que el repositorio no documenta de manera canónica:

1. **Tres marcos interpretativos de tercer orden (MI1, MI2, MI3)** distinguidos explícitamente de las hipótesis contrastables H1-H3. Los marcos operan como horizontes interpretativos sobre los constructos sintéticos (calidad epistémica, apropiación reflexiva en sentido fuerte, coherencia estructural multidimensional como horizonte evaluativo) y NO se validan empíricamente sino por triangulación con juicio docente y auto-reconstrucción estudiantil.

2. **Siete principios rectores del protocolo interpretativo** que orientan la lectura pedagógica de los resultados del clasificador, separan al instrumento del uso de alto stake, y declaran la apertura a la crítica externa.

3. **Marcador anti-reificación "perfil tipológico de apropiación X"** que enfatiza que las categorías del clasificador describen episodios, no estudiantes — alineado con el principio "no-etiquetado individual" (principio 4 del protocolo interpretativo).

La auditoría `PlanMejora.md` verificó que ninguno de los tres está documentado en código, comments, ADRs ni `docs/`. Si el tribunal doctoral cruza paper con repositorio durante la defensa, va a encontrar tres conceptos centrales del paper sin trazabilidad operacional en el sistema. Esa discrepancia, aunque sea cosmética desde la perspectiva del clasificador, debilita la defensa de la coherencia paper↔implementación que el proyecto sostiene.

## Drivers de la decisión

- **D1**: Defendibilidad académica ante tribunal doctoral UNSL. El paper es el ancla pública; el repositorio debe poder mostrar formalización canónica de los conceptos que el paper introduce.
- **D2**: Trazabilidad bidireccional paper ↔ ADR ↔ código ↔ UI. La práctica del proyecto (verificable en ADR-046, ADR-035, ADR-027, entre otros) es que cada decisión académica del paper queda anclada a un ADR del repositorio.
- **D3**: Discriminación entre las tres órdenes epistemológicas del paper §4.3 (eventos observables, indicadores derivados, constructos sintéticos). Sin marcos interpretativos documentados, la distinción se diluye en la lectura.
- **D4**: Prevención de reificación individual de las categorías de apropiación. Sin marcador anti-reificación en UI + sin principio "no-etiquetado individual" documentado, el docente puede usar las categorías como atributos permanentes del estudiante — uso que el paper §4.4 y §7.3 explícitamente prohíben.

## Decisión

Adoptamos tres componentes complementarios que conjuntamente cierran las brechas P1-1, P1-2 y P1-3 del `PlanMejora.md`:

### 1. Documentación canónica de los tres marcos interpretativos MI1, MI2, MI3 (paper §4.3)

| Marco | Constructo sintético de tercer orden | Indicadores operacionales relacionados (segundo orden) | Validación | Archivos del repo donde el marco aplica como horizonte de lectura |
|---|---|---|---|---|
| **MI1** | Calidad epistémica de la trayectoria | Perfiles tipológicos de apropiación del Clasificador N4 (`tree.py::classify_episode`), patrones temporales por nivel del CTR (`pipeline.py::extract_features`), eventos N4 con reformulación productiva (`event_labeler.py::label_event`) | Indirecta: triangulación con juicio docente experto sobre las trayectorias + auto-reconstrucción del estudiante en entrevista (`docs/research/protocolo-entrevistas-piloto.md`, este sprint) | `apps/classifier-service/src/classifier_service/services/tree.py`, `pipeline.py`, `event_labeler.py` |
| **MI2** | Apropiación reflexiva en sentido fuerte | Proxies observacionales: verificación crítica (override `tests_ejecutados` N4 cuando `failed=0` con ventana ≥ 60s desde `tutor_respondio`), reformulación productiva (anotaciones post-respuesta N4 con ventana 60s, `event_labeler.py:81 ANOTACION_N4_WINDOW_SECONDS`), integración con capacidad de explicación posterior (`reflexion_completada` registrado pero **excluido del feature extraction** por `pipeline.py:63-69 _EXCLUDED_FROM_FEATURES`) | Indirecta: el sistema captura proxies, no el constructo entero. La apropiación en sentido fuerte requiere que el estudiante pueda explicar a posteriori el porqué de cada decisión interactuada con el asistente; la verificación de esa explicabilidad es objeto de la entrevista cualitativa post-piloto, no del clasificador automático | `apps/classifier-service/src/classifier_service/services/event_labeler.py`, `pipeline.py` (exclusión `reflexion_completada`); `docs/research/protocolo-entrevistas-piloto.md` para validación cualitativa |
| **MI3** | Coherencia estructural multidimensional como horizonte evaluativo | Las cinco coherencias agregadas (CT, CCD prom, CCD orphan ratio, CII estab, CII evol) del JSONB `Classification.coherencies`, calculadas separadamente por episodio y deliberadamente NO colapsadas en un score único (ver ADR-018 + paper §4.5) | Indirecta: triangulación con el juicio docente sobre los perfiles completos + inspección del lenguaje narrativo del clasificador (textual explanation que acompaña cada Classification) que el docente contrasta con su propio juicio profesional | `packages/platform-ops/src/platform_ops/cii_alerts.py`, `cii_longitudinal.py`, `apps/classifier-service/src/classifier_service/services/ccd.py` (incluye distinción CCD-piloto-1 vs CCD-conceptual), `aggregation.py` |

**Decisión clave sobre MI1-MI3**: NO son hipótesis contrastables. Las hipótesis contrastables son H1-H3 (paper §6.1) que se formulan sobre indicadores de segundo orden. Confundir MI con H comprometería la integridad metodológica del trabajo — el paper §4.3 lo enuncia explícitamente y este ADR lo registra.

**Aplicación operacional**: cualquier ADR futuro que modifique indicadores de segundo orden (las cinco coherencias, el árbol de decisión, los overrides del labeler) debe declarar a qué MI orienta la lectura del cambio. Cualquier reporte académico del piloto que reporte resultados de las cinco coherencias debe nombrar explícitamente bajo qué MI se interpretan.

### 2. Protocolo interpretativo de 7 principios (paper §7.3)

Los siete principios rectores del protocolo interpretativo se enumeran a continuación con (a) afirmación del principio, (b) operacionalización en código si aplica, (c) responsabilidad pedagógica del docente, (d) implicación en UI/comunicación al estudiante:

| # | Principio | Operacionalización en código | Disciplina pedagógica | Implicación UI/estudiante |
|---|---|---|---|---|
| 1 | **Contextualidad**: toda lectura considera el contexto institucional | Multi-tenancy RLS (ADR-001) garantiza separación institucional de los datos; no hay análisis cross-tenant. `analytics-service` `/cohort/{id}/progression` opera siempre dentro de un `tenant_id` | El docente debe leer los resultados a la luz de la cohorte, la materia, el momento del ciclo lectivo y las particularidades del curso | UI muestra contexto institucional en headers (`ComisionSelector`, breadcrumbs con materia/período) |
| 2 | **No-reducción**: los constructos sintéticos no se reducen a indicadores | Las cinco coherencias se persisten como JSONB separado (`Classification.coherencies`) y nunca se colapsan en un score único (ADR-018, paper §4.5) | El docente debe leer las cinco coherencias por separado, NO calcular promedios | UI `StudentLongitudinalView` muestra las 5 coherencias separadas; **prohibido** agregar columna de "score N4 promedio" en futuras vistas |
| 3 | **Triangulación obligatoria**: toda inferencia involucra ≥2 fuentes independientes | El protocolo dual del ADR-046 valida etiquetador (Protocolo A) y clasificador (Protocolo B) por separado, con ≥2 anotadores humanos | El docente que use el clasificador para diagnóstico individual debe complementar con su propio juicio profesional sobre las trayectorias y, cuando aplique, entrevista al estudiante | Disclaimer canónico `APPROPRIATION_REIFICATION_DISCLAIMER` en `docenteLabels.ts` cita "triangulación con juicio docente y auto-reconstrucción del estudiante" |
| 4 | **No-etiquetado individual**: las categorías describen episodios, no estudiantes | Marcador "perfil tipológico de" en `APPROPRIATION_INVESTIGADOR` de `docenteLabels.ts` (este sprint, P1-1) | El docente NO debe usar las categorías como atributos permanentes del estudiante; las categorías describen el comportamiento de UN episodio, y un mismo estudiante puede exhibir distintos perfiles en distintos momentos del curso | Helper `appropriationWithScope(...)` que agrega sufijo "(este episodio)"; disclaimer visible en vistas cohortales `ProgressionView` y `StudentLongitudinalView` cuando se opera en modo investigador |
| 5 | **No-uso para alto stake sin triangulación**: el modelo no es instrumento de selección o acreditación | El sistema NO produce notas, NO produce certificados, NO ranking de estudiantes. La vista del docente es diagnóstica para orientación pedagógica | El docente NO debe usar las categorías del clasificador como input directo de calificaciones, ni reportarlas a terceros como evaluación final | UI no expone categorías de apropiación en vistas de calificación (`evaluation-service`); las dos áreas (clasificación N4 vs calificación) están desacopladas por diseño |
| 6 | **Explicitación de versión**: todo reporte incluye `classifier_config_hash` | Cada `Classification` persiste su `classifier_config_hash` con UNIQUE constraint `(episode_id, classifier_config_hash)` (migration `20260901_0001_classifier_schema.py:50`); cada evento del CTR persiste `LABELER_VERSION`, `GUARDRAILS_CORPUS_VERSION`, `prompt_system_hash` aplicables | Todo reporte académico/operativo que cite resultados de clasificación debe citar el `classifier_config_hash` activo al momento de la clasificación | Vista de auditoría CTR (`apps/web-admin/src/pages/ClasificacionesPage.tsx`) muestra los hashes |
| 7 | **Apertura a la crítica**: los datos están disponibles para reanálisis externo | Endpoint `analytics-service /export-academic` produce dataset anonimizado con `student_alias` (hash, no UUID) y `include_prompts=False` por default (RN-090); el árbol de decisión es código abierto y auditable contra el repositorio | El equipo de tesis se compromete a publicar el dataset anonimizado del piloto con su `classifier_config_hash` para reanálisis por la comunidad académica | UI no muestra herramientas de export al docente común; el export es responsabilidad del equipo investigador |

**Aplicación operacional**: ADRs futuros que afecten el clasificador deben referenciar qué principios respeta el cambio. Code reviews de PRs sobre `tree.py`, `pipeline.py`, `event_labeler.py` deben verificar que los principios 2 (no-reducción) y 6 (explicitación de versión) no se rompan.

### 3. Marcador anti-reificación en UI (cierra P1-1 del `PlanMejora.md`)

Ya implementado en este sprint en `apps/web-teacher/src/utils/docenteLabels.ts`:

- `APPROPRIATION_DOCENTE` reformulado con prefijo "En este episodio:..." que hace explícito el scope episódico para el docente común.
- `APPROPRIATION_INVESTIGADOR` reformulado con prefijo "Perfil tipologico:..." alineado con la formulación literal del paper §4.4.
- Helper `appropriationWithScope(category, audience)` para uso en vistas cohortales que requieren scope explícito.
- Constante `APPROPRIATION_REIFICATION_DISCLAIMER` con texto canónico citable contra paper §4.4 + §7.3.
- Disclaimer renderizado en `ProgressionView` (header) y `StudentLongitudinalView` (footer) cuando el `viewMode === "investigador"`.

## Opciones consideradas

### Opción A — ADR-053 unificado (elegida)

Documentar marcos MI1-MI3 + 7 principios + marcador anti-reificación en un único ADR-053 con la matriz operacional de correspondencia código↔ADR.

**Ventajas**:
- Trazabilidad concentrada: un solo lugar para que el tribunal valide la coherencia paper↔repositorio.
- Permite cross-referencias internas entre los tres componentes (ej.: principio 4 referencia marcador anti-reificación de §4.4).
- Costo bajo: un solo ADR vs tres con overhead duplicado de contexto.

**Desventajas**:
- ADR largo (más difícil de leer rápidamente).
- Riesgo de "ADR-saco-de-papas" si se modifica un componente sin tocar los otros — mitigado por la matriz operacional que permite editar filas independientes.

### Opción B — Tres ADRs separados (uno por componente)

Separar cada componente en su propio ADR (un ADR para marcos MI1-MI3, otro para los 7 principios, otro para el marcador anti-reificación). Habría requerido tres números de ADR libres consecutivos.

**Desventajas que la descartan**:
- Sobrecarga documental sin valor: los tres componentes están conceptualmente acoplados (el marcador anti-reificación es operacionalización del principio 4; los principios son protocolo de lectura de los marcos).
- Riesgo de cross-references rotas si uno se edita y los otros no.

### Opción C — Solo agregar comments en código sin ADR

Agregar comments en `tree.py`, `pipeline.py`, `ccd.py` mencionando MI1-MI3 y los principios sin crear ADR.

**Desventajas que la descartan**:
- El tribunal lee ADRs, no comments del código.
- Pierde el formato canónico de decisiones académicas del proyecto (ADR-018, ADR-027, ADR-046 establecen el patrón).

## Criterios de éxito

1. ADR-053 (este archivo) creado y referenciado desde `paper-draft.md` y desde `docs/CAPABILITIES.md` cuando aplique.
2. `apps/web-teacher/src/utils/docenteLabels.ts` exporta `APPROPRIATION_REIFICATION_DISCLAIMER` y helper `appropriationWithScope`.
3. Vistas cohortales `ProgressionView` y `StudentLongitudinalView` renderizan el disclaimer en modo investigador, verificable por `data-testid="appropriation-reification-disclaimer"`.
4. `docs/limitaciones-declaradas.md` agrega entrada de versionado 2026-05-17 que referencia este ADR (cierre del P1-4 del `PlanMejora.md`).
5. Verificable por grep: `grep -r "MI1\|MI2\|MI3" docs/adr/` debe devolver al menos este ADR; `grep -r "perfil tipologico" apps/web-teacher/` debe devolver al menos `docenteLabels.ts` y las dos vistas con el disclaimer.

## Criterio de revisita

- Si el paper en versiones futuras introduce nuevos marcos interpretativos (MI4+) o modifica los siete principios, este ADR debe actualizarse (no crearse uno nuevo) y la fila correspondiente de la matriz operacional debe ser editada con el cambio.
- Si la auditoría intercoder (A2 del plan-acción + ADR-046) detecta que algún principio se viola sistemáticamente en la operación, este ADR debe agregar criterio de mitigación o ser superseded por un ADR específico que reformule el principio.
- Si la entrevista cualitativa (P2-4 del `PlanMejora.md`, documentada en `docs/research/protocolo-entrevistas-piloto.md`) muestra que la triangulación de MI1 con auto-reconstrucción del estudiante no funciona como se espera, este ADR debe actualizarse con hallazgos y mitigaciones.

## Consecuencias

### Positivas

- Trazabilidad bidireccional paper ↔ ADR ↔ código ↔ UI sobre los tres componentes epistemológicos centrales del paper §4.3, §4.4, §7.3.
- Defensa doctoral con material formal de respuesta ante preguntas del tribunal sobre "cómo se distingue en el código una hipótesis contrastable de un constructo sintético", "cómo se previene el uso del clasificador como atributo permanente del estudiante", "qué garantiza que el sistema no se use para alto stake sin triangulación".
- El marcador anti-reificación en UI protege al docente de un sesgo cognitivo plausible (atribuir la categoría del último episodio como característica del estudiante).
- Habilita criterio para code reviews de PRs sobre el clasificador: cualquier cambio debe declarar qué MI afecta y qué principios respeta.

### Negativas / trade-offs

- ADR largo (>5000 palabras). Requiere lectura calmada — mitigado por la matriz operacional que permite consulta puntual.
- El disclaimer en UI agrega ruido visual mínimo en vistas investigador. Decidido aceptar el costo porque el comité doctoral es el lector primario de esa vista.
- Los principios 1, 3, 5, 7 son **actitudinales más que técnicos** — su cumplimiento depende de la disciplina pedagógica del docente y de la disciplina académica del equipo de tesis, NO de enforcement automático por el código. Este ADR los documenta pero no puede garantizar su cumplimiento operativo.

### Neutras

- Los ADRs históricos (027, 044, 045, 046) NO se modifican. Sus referencias al `classifier_config_hash` y a las cinco coherencias siguen vigentes; este ADR-053 agrega un horizonte interpretativo sin alterar la lógica del clasificador.
- El `classifier_config_hash` NO cambia por este ADR. Las classifications históricas del piloto-1 NO se recomputan.
- El `LABELER_VERSION` NO se bumpea.

## Archivos modificados con este ADR (2026-05-17)

- `docs/adr/049-marcos-interpretativos-y-protocolo.md` — este archivo (nuevo).
- `apps/web-teacher/src/utils/docenteLabels.ts` — agregados marcador anti-reificación en labels, helper `appropriationWithScope`, constante `APPROPRIATION_REIFICATION_DISCLAIMER`.
- `apps/web-teacher/src/views/ProgressionView.tsx` — renderiza disclaimer en header cuando `!isDocente`.
- `apps/web-teacher/src/views/StudentLongitudinalView.tsx` — renderiza disclaimer en footer cuando `!isDocente`.
- `docs/limitaciones-declaradas.md` — entrada de versionado 2026-05-17 (cierra P1-4 del `PlanMejora.md`).

## Referencias

- ADR-001 — Multi-tenancy RLS (operacionaliza principio 1 "contextualidad").
- ADR-018 — CII evolution longitudinal (operacionaliza MI3 + principio 2 "no-reducción").
- ADR-027 — Diferir Fase B `socratic_compliance` (relación con MI2 vía proxies de apropiación reflexiva).
- ADR-035 — Reflexión privacy exclusion del classifier (operacionaliza MI2 vía exclusión deliberada de `reflexion_completada` del feature extraction).
- ADR-044 / ADR-045 — Esqueletos OFF (gates de validación intercoder que operacionalizan principio 3 "triangulación").
- ADR-046 — Umbral kappa 0,70 + protocolo dual (operacionaliza principio 3 "triangulación obligatoria" vía Protocolo A + Protocolo B).
- Paper Cortez & Garis (`paper_conaiisi.pdf`, versión 2026-05-16) — Resumen, §4.3 (tres órdenes epistemológicos), §4.4 (perfiles tipológicos de apropiación), §7.3 (consideraciones de equidad + siete principios interpretativos).
- `PlanMejora.md` (root del wrapper `AI-Native-V4-main/`) — P1-1, P1-2, P1-3.
- `docs/research/protocolo-entrevistas-piloto.md` — entrevistas semi-estructuradas para triangulación cualitativa de MI1, MI2 (P2-4 del `PlanMejora.md`).
- Mislevy, R. J., Steinberg, L. S., & Almond, R. G. (2003). Focus article: On the structure of educational assessments. Measurement: Interdisciplinary Research and Perspectives, 1(1), 3-62.
- Pellegrino, J. W., Chudowsky, N., & Glaser, R. (2001). Knowing What Students Know: The Science and Design of Educational Assessment. National Academy Press.
- Messick, S. (1989). Validity. En R. L. Linn (Ed.), Educational measurement (3rd ed.). American Council on Education / Macmillan.
