# Plan de acción derivado del informe cognitivo (informeSocra1.md)

**Versión**: 1.0.0 — propuesta inicial
**Fecha**: 2026-05-16
**Origen**: `informeSocra1.md` (análisis externo desde lente de ciencia cognitiva del aprendizaje y medición educativa).
**Complementa**: `informeSoc.md` y su plan implícito (R1-R10) sobre lente didáctica socrática.
**Destinatarios**: Alberto A. Cortez (autor), Daniela Carbonari (co-dir), Ana Garis (co-autora del paper), eventual sub-agentes que ejecuten las acciones.

---

## 0. Resumen ejecutivo

El informe cognitivo identificó **6 observaciones sustantivas + 5 riesgos + 4 brechas de validación** que el sistema AI-Native N4 tiene desde la lente de medición educativa moderna. Este plan convierte esas observaciones en **24 acciones priorizadas** (CS01-CS24), con DAG de dependencias, tabla de estado y plan paralelo de reescritura del paper.

**Distribución por prioridad**:
- **P0 — Antes de la defensa doctoral, sin requerir piloto adicional**: 8 acciones (CS01-CS08). Foco: enunciados explícitos en el paper + análisis de sensibilidad ya ejecutable + documentación de limitaciones expandida.
- **P1 — Antes de la submisión final del paper**: 4 acciones (CS09-CS12). Foco: diseño de instrumentos de validación convergente listos para piloto-2 (NASA-TLX, MAI, transfer, autoeficacia).
- **P2 — Agenda piloto-2 (validación de constructo)**: 8 acciones (CS13-CS20). Foco: implementación efectiva de los instrumentos, EFA, comparaciones tipológica vs dimensional, calibración empírica de umbrales.
- **P3 — Agenda piloto-3 / investigación futura**: 4 acciones (CS21-CS24). Foco: cognición distribuida operacionalizada, integración G9 (semántica), CCD completa.

**Distribución por tipo de cambio**:
- **Solo paper** (reescritura/anexos): 7 acciones.
- **Solo código** (análisis o módulos nuevos): 6 acciones.
- **Código + paper**: 11 acciones (la mayoría — el plan está diseñado para que cambios al código y al paper se sincronicen, no diverjan).

**Esfuerzo total estimado**: 180-240 horas de trabajo entre código, análisis, redacción y coordinación humana. Distribuido en 12-18 meses según la cadencia de los pilotos.

**Invariantes preservadas** (las mismas que en el plan previo de R1-R10):
- `classifier_config_hash` no cambia hasta A1 cerrado (re-clasificación con DB real del piloto).
- `LABELER_VERSION` no se bumpea por estas acciones (las propuestas que requerirían bump quedan condicionadas y marcadas).
- El contrato del CTR no se altera (append-only).
- Ningún flag de producción se prende sin gates explícitos.

---

## 1. Marco del plan — qué cubre y qué NO cubre

### 1.1 Cubre

- Las observaciones operacionalizables del informeSocra1.md (cada §3.1-3.4, §4, §5, §6, §7 y §9 generan al menos una acción concreta).
- Reescritura sincronizada del paper Cortez & Garis: sección por sección, qué se modifica, por qué, dependencia con qué acción CS.
- DAG explícito de dependencias entre acciones (gates humanos, gates externos como A1, secuencia obligatoria de validación).
- Estimaciones de esfuerzo realistas (rango bajo/alto, no número único).
- Distinción entre acciones ejecutables por sub-agentes vs acciones que requieren participación humana (dir, co-dir, Ana Garis, docentes UTN, estudiantes piloto).

### 1.2 NO cubre

- **Implementaciones de los R5/R7/R8 del informe didáctico**. Esas ya tienen su ADR (050, 051, 052) y design docs. Este plan es complementario, no sustituye.
- **A1, A2, A3, A5 externos del `plan-accion.md` original**. Son pre-condiciones, no acciones nuevas. Se referencian como gates.
- **La activación de los flags ya creados** (`socratic_compliance_enabled`, `lexical_anotacion_override_enabled`, `guardrail_modifier_enabled`, `metacognitive_feedback_enabled`). Esas activaciones tienen sus propios ADRs y gates.
- **G8c (clasificación semántica de anotaciones via embeddings)** — está marcado como Eje B post-defensa en ADR-045. Se referencia como pre-condición de algunas acciones.
- **G9 (clasificación semántica de prompts via embeddings)** — Eje B post-defensa. Pre-condición de CCD completa (CS21).

### 1.3 Cómo leer este plan

Cada acción tiene:
- **ID** (CS##): código único.
- **Observación de origen**: qué párrafo/§ de `informeSocra1.md` la genera.
- **Tipo**: código / paper / código+paper / análisis / instrumento.
- **Qué hace** (1-2 líneas).
- **Dónde** (archivos afectados o secciones del paper).
- **Esfuerzo** (rango horas).
- **Dependencias** (otras CS o gates externos).
- **Gate humano** (si requiere decisión de dir/co-dir/Ana Garis).

---

## 2. Acciones P0 — Antes de la defensa doctoral

Acciones ejecutables sin requerir piloto adicional, sin dependencia de A1, con impacto directo sobre la defensa.

### CS01 — Enunciar explícitamente MI1, MI2, MI3 en §4.3 del paper

- **Observación de origen**: `informeSocra1.md` §2 ("Riesgo a marcar: el marco interpretativo MI1, MI2, MI3 está declarado en el paper pero no enunciado explícitamente").
- **Tipo**: solo paper.
- **Qué hace**: agregar tres párrafos en §4.3 (o subsección §4.3.bis) enunciando qué afirma cada MI. La Fig. 2 los menciona pero el cuerpo no los enumera. Cada MI debe declarar (a) qué constructo sintético articula, (b) cómo se diferencia de las H_i, (c) qué juicio experto requiere para su validación indirecta.
- **Dónde**: `paper-draft.md` §4.3 (Tres órdenes epistemológicos de los constructos).
- **Esfuerzo**: 4-6 h (incluye discusión con co-autoría sobre redacción de cada MI).
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral con Ana Garis sobre la formulación final de cada MI.

### CS02 — Renombrar `cii_evolution` en prosa del paper para distinguirlo del longitudinal

- **Observación de origen**: `informeSocra1.md` §3.3 ("Dos constructos distintos con etiquetas casi iguales son trampa epistemológica") y §9 (C0.2).
- **Tipo**: solo paper.
- **Qué hace**: en todas las menciones del paper, escribir `cii_evolution_intra` (intra-episodio, pendiente léxica) y `cii_evolution_longitudinal` (inter-episodio, slope ordinal de apropiación) sin abreviar a `cii_evolution` a secas. Agregar nota a pie de página la primera vez explicando que los nombres del código no se renombran por compatibilidad histórica con classifications persistidas.
- **Dónde**: `paper-draft.md` §4.5 (Tabla 3), §6.1 (H2), Tabla 6, donde aparezca.
- **Esfuerzo**: 2-3 h.
- **Dependencias**: ninguna.
- **Gate humano**: ninguno (es cambio de prosa, no de constructo).

### CS03 — Documentar la versión reducida de CCD vigente en piloto-1 vs la conceptual

- **Observación de origen**: `informeSocra1.md` §3.2 ("Lo que el módulo declara que mide está parcialmente desactivado en runtime"), §7.4 (riesgo 4), §9 (C0.3).
- **Tipo**: código + paper.
- **Qué hace**:
  - **Código**: actualizar el docstring de `apps/classifier-service/src/classifier_service/services/ccd.py` (líneas 1-41) para distinguir explícitamente `CCD-piloto-1` (rama de prompts reflexivos OFF) de `CCD-conceptual` (con G9 activado). Comentario citando informeSocra1.md y este CS03.
  - **Paper**: agregar nota en §4.5 (Tabla 3) y/o sub-sección de limitaciones a discutir con coautoría (el paper actual va de §1 a §10 sin §15 dedicado; podría agregarse al final de §8 entre los riesgos a priori, o como nueva sub-sección §4.5.bis). Declarar que la validación intercoder κ ≥ 0,70 del piloto-1 valida la versión reducida de CCD, no la conceptual.
- **Dónde**: `apps/classifier-service/src/classifier_service/services/ccd.py` + `paper-draft.md` §4.5 (ubicación final pendiente decisión coautoral — ver `revision-coautoral-paper-2026-05-16.md` §4 opciones).
- **Esfuerzo**: 3-4 h.
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral con Ana Garis para la redacción en el paper (es nota crítica sobre validez del constructo).

### CS04 — Análisis de sensibilidad sobre constantes temporales y umbrales del árbol

- **Observación de origen**: `informeSocra1.md` §3.1 ("La pausa >5min como frontera de ventana es heurística"), §3.2 ("La ventana de 2 minutos es heurística"), §4.2 ("los umbrales del árbol son operacionalización del implementador sin validación empírica documentada"), §7.2 (riesgo 2), §9 (C0.4).
- **Tipo**: código + paper.
- **Qué hace**:
  - **Código**: crear script `scripts/sensitivity-analysis-cognitive-coherences.py` que recorre las 106 classifications históricas (post-A1) y reporta:
    - Sensibilidad de CT a la constante `PAUSE_THRESHOLD` (probar 3, 4, 5, 6, 8, 10 minutos).
    - Sensibilidad de CCD a la `CORRELATION_WINDOW` (probar 1, 2, 3, 5 minutos).
    - Sensibilidad de la categorización del árbol a los umbrales (variar `ccd_orphan_high`, `ct_high`, `ccd_mean_low`, `cii_stability_low` en ±20%).
    - Reportar qué fracción de las 106 cambian de categoría con cada variación.
  - **Paper**: agregar Anexo C "Análisis de sensibilidad" con la tabla de resultados.
- **Dónde**: `AI-NativeV3-main/scripts/sensitivity-analysis-cognitive-coherences.py` + `paper-draft.md` Anexo C.
- **Esfuerzo**: 12-16 h (script + ejecución post-A1 + redacción).
- **Dependencias**: **A1 cerrado** (re-clasificación de las 106 históricas con DB real).
- **Gate humano**: dirección revisa los rangos a probar antes de ejecutar.

### CS05 — Sección nueva en §9 (o crear §15 Limitaciones): "Proceso observable vs aprendizaje"

- **Observación de origen**: `informeSocra1.md` §0 (observación 1), §3.4 ("El sistema mide procesos observables de uso del asistente, no aprendizaje en sentido cognitivo estricto"), §10 (conclusiones).
- **Tipo**: solo paper.
- **Qué hace**: agregar dos párrafos (declaración explícita) en §9 al final, antes de "limitación del posicionamiento" actual, O —si la coautoría prefiere— crear sub-sección dedicada de limitaciones:
  - El sistema mide proceso observable, no aprendizaje en sentido cognitivo estricto.
  - Anclar en Pellegrino, Chudowsky & Glaser (2001): distinción process assessment vs learning assessment.
  - Reconocer que H1 es "diferenciabilidad observacional entre tipos de apropiación" y NO "diferenciabilidad entre niveles de aprendizaje".
  - Explicitar que las correlaciones con outcomes (transfer, calificaciones) son agenda piloto-2.
- **Dónde**: `paper-draft.md` §9 (en versión aplicada 2026-05-16). Ubicación final pendiente decisión coautoral — ver `revision-coautoral-paper-2026-05-16.md` §6 opciones.
- **Esfuerzo**: 3-4 h.
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral con Ana Garis (es declaración cuidadosa sobre alcance del aporte).

### CS06 — Párrafo nuevo en §3 (o crear sub-sección de limitaciones): "Cognición distribuida declarada vs operacionalizada"

- **Observación de origen**: `informeSocra1.md` §0 (observación 5), §3.4 ("El sistema implementa cognición distribuida pero no la mide"), §6.7 ("Cognición distribuida — la promesa que no se mide"), §7 (riesgo a tematizar).
- **Tipo**: solo paper.
- **Qué hace**: agregar párrafo en §3 (Marco teórico) — versión aplicada 2026-05-16 — declarando:
  - El paper declara cognición distribuida (Hutchins, 1995) y mente extendida (Clark & Chalmers, 1998) como anclajes.
  - Las cinco coherencias miden al estudiante, no al sistema cognitivo extendido (estudiante + tutor + IDE + tests + enunciado).
  - Reconocer esto como brecha entre marco teórico y operacionalización; declarar la operacionalización del sistema extendido como agenda futura (referencia a CS21-CS22 de este plan).
- **Dónde**: `paper-draft.md` §3 (aplicado). Ver `revision-coautoral-paper-2026-05-16.md` §5 con opciones de mover/duplicar a sub-sección de limitaciones.
- **Esfuerzo**: 4-5 h.
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral con Ana Garis.

### CS07 — Glosa terminológica: "perfil tipológico de apropiación X" vs "apropiación X"

- **Observación de origen**: `informeSocra1.md` §7.1 ("Riesgo de reificación"), §10 (conclusión sobre honrar la distinción de los tres órdenes).
- **Tipo**: solo paper.
- **Qué hace**:
  - Primera mención de cada categoría: usar "perfil tipológico de apropiación reflexiva" (o superficial, o delegación pasiva).
  - Menciones subsiguientes: abreviar a "perfil reflexivo", "perfil superficial", "perfil delegativo" — preservando la palabra "perfil" como ancla a la distinción "constructo de segundo orden" (Fig. 2).
  - Agregar nota terminológica en §4.4 (introducción de los tres tipos) explicando la convención.
- **Dónde**: `paper-draft.md` §4.4 + cualquier mención subsiguiente.
- **Esfuerzo**: 3-4 h (find-and-replace cuidadoso + nota terminológica).
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral (puede afectar tono del paper).

### CS08 — Documentar el ratio `prompt:exec=1:2` como decisión de diseño en `ct.py`

- **Observación de origen**: `informeSocra1.md` §3.1 ("El ratio prompt:exec=1:2 como 'saludable' es decisión del implementador, sin literatura cognitiva que justifique ese ratio específico").
- **Tipo**: código + paper.
- **Qué hace**:
  - **Código**: agregar comentario extenso en `apps/classifier-service/src/classifier_service/services/ct.py` (líneas 49-59 alrededor de `prompt_exec_ratio`) declarando que el rango "saludable" es operacionalización del implementador, no derivación de literatura cognitiva. Citar este CS08 y agendar calibración empírica para piloto-2 (CS20).
  - **Paper**: nota inline en §4.5 (Tabla 3) declarando la decisión (versión aplicada 2026-05-16).
- **Dónde**: `apps/classifier-service/src/classifier_service/services/ct.py` + `paper-draft.md` §4.5.
- **Esfuerzo**: 1-2 h.
- **Dependencias**: ninguna.
- **Gate humano**: ninguno.

---

## 3. Acciones P1 — Antes de la submisión final del paper

Diseño de los instrumentos de validación convergente. Listos para aplicar en piloto-2, pero el diseño puede y debe ser parte del paper.

### CS09 — Diseñar protocolo de aplicación de NASA-TLX

- **Observación de origen**: `informeSocra1.md` §6.2 (carga cognitiva ausente), §9 (C1.1: "Administrar NASA-TLX o Cognitive Load Scale al cierre de algunos episodios seleccionados").
- **Tipo**: instrumento + paper.
- **Qué hace**: crear `docs/research/protocolo-nasa-tlx.md` con:
  - Versión del NASA-TLX a usar (versión completa de 6 dimensiones o adaptación corta de Paas).
  - Cuándo administrar: al cierre del episodio, antes del modal de reflexión, en una fracción aleatoria (~20%) de los episodios para no contaminar el comportamiento sistemáticamente.
  - Quién la responde: estudiantes piloto post-consentimiento informado adicional.
  - Análisis previsto: correlacionar con CT (hipótesis: alta CT correlaciona con baja carga extrínseca y/o alta carga germana).
  - Citar Hart & Staveland (1988) + Paas (1992).
- **Dónde**: `AI-NativeV3-main/docs/research/protocolo-nasa-tlx.md` (nuevo). Agregar referencia en §6 (método) o §8 (agenda) del paper post-piloto-2.
- **Esfuerzo**: 6-8 h.
- **Dependencias**: ninguna (diseño autónomo).
- **Gate humano**: revisión coautoral + comité de ética UTN (instrumento adicional sobre estudiantes).

### CS10 — Diseñar protocolo de aplicación de MAI (Schraw & Dennison, 1994)

- **Observación de origen**: `informeSocra1.md` §6.3 (metacognición ausente), §9 (C1.2).
- **Tipo**: instrumento + paper.
- **Qué hace**: crear `docs/research/protocolo-mai-metacognicion.md` con:
  - Versión adaptada al castellano del MAI (52 ítems) o Jr. MAI (12 ítems, Sperling et al., 2002).
  - Cuándo administrar: al inicio del cuatrimestre (baseline) y al final.
  - Análisis previsto: correlacionar el cambio MAI(inicio→fin) con `cii_evolution_longitudinal` agregado del estudiante.
  - Hipótesis convergente: estudiantes con incremento alto de MAI tendrán mayor `cii_evolution_longitudinal`.
- **Dónde**: `AI-NativeV3-main/docs/research/protocolo-mai-metacognicion.md` (nuevo). Agregar referencia en §6 (método) o §8 (agenda) del paper post-piloto-2.
- **Esfuerzo**: 6-8 h (incluye buscar adaptación validada al castellano o documentar adaptación propia).
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral + comité ética + posiblemente traducción/adaptación si no hay versión castellana validada.

### CS11 — Diseñar test de transfer

- **Observación de origen**: `informeSocra1.md` §6.5 (transfer ausente), §9 (C1.3: "Sin instrumento de transfer, H2 es declarativa, no contrastable").
- **Tipo**: instrumento + paper + código (captura).
- **Qué hace**: crear `docs/research/diseno-test-transfer.md` con:
  - Set de 3-5 problemas isomórficos al banco de ejercicios del piloto pero **no idénticos** (cambio de dominio: del banco son listas en Python; del transfer son strings o tuplas).
  - Formato: 15-20 minutos al final del cuatrimestre, sin tutor, sin ejecución asistida.
  - Scoring: 0/1 por cada problema (resuelto correctamente / no), más rúbrica de explicación corta sobre el enfoque (capturada como texto libre).
  - Análisis previsto: correlacionar score de transfer con cada coherencia individualmente (validez criterial) y con la categoría de apropiación dominante del estudiante.
  - **Código**: endpoint `POST /api/v1/transfer-test/submit` en analytics-service para capturar respuestas. Tabla `transfer_test_responses` en `academic_main`.
- **Dónde**: `AI-NativeV3-main/docs/research/diseno-test-transfer.md` + nuevo endpoint. Referencia en §6 (H2) del paper + descripción detallada en sección de métodos.
- **Esfuerzo**: 16-24 h (diseño de ejercicios + endpoint + análisis previsto).
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral + docentes UTN revisan los ejercicios isomórficos (validez de contenido).

### CS12 — Diseñar escala de autoeficacia en programación

- **Observación de origen**: `informeSocra1.md` §6.6 (autoeficacia ausente), §9 (C1.4: "controlar por autoeficacia en los análisis de H1 y H2").
- **Tipo**: instrumento + paper.
- **Qué hace**: crear `docs/research/protocolo-autoeficacia-programacion.md` con:
  - Escala adaptada de Bandura (1997) calibrada para programación universitaria — buscar adaptaciones existentes (Lishinski et al., 2016 sobre CS self-efficacy) o documentar adaptación propia con piloteo previo.
  - Cuándo: inicio del cuatrimestre.
  - Análisis previsto: covariable de control en análisis de H1 y H2.
- **Dónde**: `AI-NativeV3-main/docs/research/protocolo-autoeficacia-programacion.md` (nuevo). Referencia en §6 del paper.
- **Esfuerzo**: 6-8 h.
- **Dependencias**: ninguna.
- **Gate humano**: revisión coautoral + comité ética.

---

## 4. Acciones P2 — Agenda piloto-2 (validación de constructo)

Implementación efectiva de los instrumentos diseñados en P1 + análisis cuantitativos que requieren datos del piloto-2.

### CS13 — Aplicar NASA-TLX en piloto-2 + análisis

- **Observación de origen**: `informeSocra1.md` §9 (C1.1).
- **Tipo**: análisis (con datos del piloto-2).
- **Qué hace**: aplicar el protocolo CS09 en piloto-2; computar correlaciones NASA-TLX ↔ CT, NASA-TLX ↔ CCD; reportar.
- **Esfuerzo**: 8-12 h (post-piloto-2).
- **Dependencias**: CS09 (protocolo diseñado), piloto-2 ejecutado, A1 cerrado.

### CS14 — Aplicar MAI en piloto-2 + análisis

- **Observación de origen**: `informeSocra1.md` §9 (C1.2).
- **Tipo**: análisis.
- **Qué hace**: aplicar CS10; computar correlación delta(MAI) ↔ `cii_evolution_longitudinal`; reportar.
- **Esfuerzo**: 8-12 h.
- **Dependencias**: CS10, piloto-2 ejecutado.

### CS15 — Aplicar test de transfer + análisis

- **Observación de origen**: `informeSocra1.md` §9 (C1.3).
- **Tipo**: análisis.
- **Qué hace**: aplicar CS11; analizar validez criterial (correlación coherencias ↔ transfer score).
- **Esfuerzo**: 12-16 h.
- **Dependencias**: CS11, piloto-2 ejecutado.

### CS16 — Aplicar escala de autoeficacia + análisis

- **Observación de origen**: `informeSocra1.md` §9 (C1.4).
- **Tipo**: análisis.
- **Qué hace**: aplicar CS12; usar como covariable de control en análisis de H1 y H2.
- **Esfuerzo**: 8-12 h.
- **Dependencias**: CS12, piloto-2 ejecutado.

### CS17 — Análisis Factorial Exploratorio (EFA) sobre las 5 coherencias

- **Observación de origen**: `informeSocra1.md` §9 (C2.1: "Análisis factorial exploratorio sobre las cinco coherencias del piloto-1 post-A1").
- **Tipo**: código + paper.
- **Qué hace**:
  - **Código**: script `scripts/factorial-analysis-coherences.py` que ejecuta:
    - KMO (Kaiser-Meyer-Olkin) para adecuación muestral.
    - Test de Bartlett de esfericidad.
    - Análisis paralelo de Horn para decidir número de factores.
    - EFA con rotación (oblimin o varimax según factores).
    - Reporta cargas factoriales + interpretación.
  - **Paper**: nueva subsección §8.X (Validez discriminante) con tabla de cargas factoriales.
- **Dónde**: `scripts/factorial-analysis-coherences.py` + `paper-draft.md` §8.
- **Esfuerzo**: 16-20 h (script + ejecución + interpretación + redacción).
- **Dependencias**: A1 cerrado (necesita 106 históricas re-clasificadas; n=106 es marginal para EFA, lo deseable es ≥150).
- **Gate humano**: si el KMO es <0.5 o Bartlett no significativo, el EFA es inviable con la muestra actual — documentar y posponer a piloto-2 con n acumulado.

### CS18 — Comparar capacidad predictiva: tipológica (3 categorías) vs dimensional (IRT)

- **Observación de origen**: `informeSocra1.md` §9 (C3.1).
- **Tipo**: código + paper.
- **Qué hace**:
  - **Código**: script `scripts/typology-vs-dimensional.py` que:
    - Computa modelo IRT (Rasch o 2PL) sobre las cinco coherencias tratadas como ítems continuos.
    - Compara capacidad predictiva (varianza explicada del score de transfer CS15) entre la tipología actual y la dimensión latente IRT.
  - **Paper**: subsección §8.Y con comparación.
- **Dónde**: `scripts/typology-vs-dimensional.py` + paper §8.
- **Esfuerzo**: 16-20 h.
- **Dependencias**: CS15 (test de transfer aplicado), A1 cerrado.

### CS19 — Clustering alternativo (k-means / LPA) sobre las 5 coherencias

- **Observación de origen**: `informeSocra1.md` §9 (C3.2: "Si los clusters emergentes coinciden con las tres categorías del árbol, hay validez convergente").
- **Tipo**: código + paper.
- **Qué hace**:
  - **Código**: script `scripts/clustering-coherences.py` que:
    - Aplica k-means y latent profile analysis sobre las 5 coherencias.
    - Compara clusters emergentes con la categorización del árbol.
    - Reporta tabla de contingencia + κ entre ambos approaches.
  - **Paper**: subsección §8.Z con resultados.
- **Esfuerzo**: 12-16 h.
- **Dependencias**: A1 cerrado.

### CS20 — Calibrar empíricamente las ventanas temporales (CT 5min, CCD 2min) y ratio prompt:exec

- **Observación de origen**: `informeSocra1.md` §3.1, §3.2, §9 (C1 implícita en calibrar parámetros operacionales).
- **Tipo**: código + paper.
- **Qué hace**: usando los datos del piloto-1 post-A1, ejecutar el script de CS04 con grid extendido; consultar a dirección + docentes UTN para decidir constantes definitivas; bumpear constantes si corresponde y bumpear `LABELER_VERSION` o `classifier_config_hash` coordinadamente (ADR nuevo si las constantes cambian).
- **Esfuerzo**: 10-14 h (post-CS04).
- **Dependencias**: CS04, dirección + docentes.

---

## 5. Acciones P3 — Agenda piloto-3 / investigación futura

Acciones más profundas que requieren cambios arquitectónicos o investigación adicional.

### CS21 — Activar la rama de prompts reflexivos en CCD (CCD completa)

- **Observación de origen**: `informeSocra1.md` §3.2 ("Una parte importante del constructo está fuera del cálculo del piloto-1"), §7.4 (riesgo 4), §9.
- **Tipo**: código + paper.
- **Qué hace**: implementar G9 (clasificación semántica de `prompt_kind`) que permita al `tutor-service` emitir `prompt_kind="reflexion"` cuando el contenido del prompt es reflexivo. Esto requiere endpoint en `ai-gateway` para clasificación semántica + ADR + bump LABELER + re-clasificación masiva.
- **Esfuerzo**: 40-60 h (arquitectura nueva + endpoint + validación + ADR + re-clasificación).
- **Dependencias**: A1 cerrado, decisión académica sobre Eje B post-defensa, presupuesto BYOK del piloto-3.
- **Gate humano**: revisión coautoral + decisión sobre activación post-defensa.

### CS22 — Operacionalizar el sistema cognitivo extendido (cognición distribuida instrumentada)

- **Observación de origen**: `informeSocra1.md` §6.7, §9 (C4.1, C4.2).
- **Tipo**: código + paper.
- **Qué hace**:
  - Diseñar e implementar un módulo `packages/platform-ops/src/platform_ops/extended_cognition.py` que capture:
    - Contribución del tutor por episodio (cantidad de información aportada, complejidad del andamiaje socrático medida por longitud + tipo de respuesta).
    - Contribución del IDE/Pyodide (autocompletes, errores capturados, feedback ejecutivo).
    - Latencias clave en el bucle.
  - Tests + ADR nuevo (~054).
  - Sección nueva del paper en agenda futura o piloto-3.
- **Esfuerzo**: 30-40 h.
- **Dependencias**: A1 cerrado, decisión académica sobre alcance.

### CS23 — Triangular validez de constructo con marco ICAP (Chi & Wylie, 2014)

- **Observación de origen**: `informeSocra1.md` §1 (marco), §4.1 (tipologías vs dimensiones — el árbol se parece a ICAP).
- **Tipo**: paper.
- **Qué hace**: agregar subsección en §3 (Marco teórico) o §9 (Discusión: posicionamiento) que mapee los tres tipos de apropiación del modelo N4 al framework ICAP (passive/active/constructive/interactive) de Chi & Wylie (2014):
  - `delegacion_pasiva` ≈ passive/active.
  - `apropiacion_superficial` ≈ active.
  - `apropiacion_reflexiva` ≈ constructive/interactive.
- Justificar la elección de tres categorías en lugar de cuatro (ICAP tiene cuatro). Discutir si el mapeo es defensable o si conviene migrar a ICAP en piloto-3.
- **Esfuerzo**: 6-10 h.
- **Dependencias**: ninguna formal; deseable post-CS19 (clustering) para tener evidencia empírica.

### CS24 — Reproducir el análisis con un grupo control

- **Observación de origen**: `informeSocra1.md` §6.5 ("Sin transfer, el sistema mide proceso intra-tarea, no aprendizaje generalizable"), aunque no explícita en C1-C4. Implícita en H2.
- **Tipo**: análisis + paper.
- **Qué hace**: diseño y ejecución de estudio comparado con grupo control (estudiantes sin tutor AI). Análisis comparativo del aprendizaje (medido por transfer + delta-MAI + autoeficacia post) entre grupo experimental (con tutor) y control (sin tutor o con tutor humano tradicional).
- **Esfuerzo**: 60-120 h (diseño + reclutamiento + ejecución + análisis + redacción).
- **Dependencias**: CS11, CS14, CS16, piloto-3, presupuesto institucional, aprobación ética ampliada.
- **Gate humano**: dirección + co-dirección + comité ética UTN.

---

## 6. DAG de dependencias

```
A1 (re-clasificación 106 históricas con DB real) — gate externo, plan-accion.md
│
├── CS04 (sensitivity analysis) ───────────────┐
│   └── CS20 (calibración empírica ventanas) ──┤
│                                              │
├── CS17 (EFA sobre 5 coherencias) ────────────┤
│                                              │
├── CS19 (clustering alternativo) ─────────────┤
│                                              │
└── CS18 (tipológica vs dimensional) ◄─────────┤
                                               │
              [todos requieren A1]             │
                                               ▼
                                    Resultados informan CS23

Sin dependencia de A1, ejecutables YA:
  CS01 (enunciar MI1-MI3)
  CS02 (renombrar cii_evolution_intra)
  CS03 (documentar CCD reducida)
  CS05 (proceso vs aprendizaje en §9)
  CS06 (cognición distribuida declarada vs operacionalizada)
  CS07 (glosa "perfil tipológico de")
  CS08 (documentar ratio prompt:exec)

Sin dependencia de A1, requieren participación humana coordinada:
  CS09 (NASA-TLX protocolo)
  CS10 (MAI protocolo)
  CS11 (transfer test)
  CS12 (autoeficacia)

Dependen de los protocolos + piloto-2:
  CS13 ◄── CS09 + piloto-2
  CS14 ◄── CS10 + piloto-2
  CS15 ◄── CS11 + piloto-2
  CS16 ◄── CS12 + piloto-2

Dependen de los análisis + decisiones académicas:
  CS18 ◄── CS15 + A1
  CS23 ◄── CS19 (deseable)
  CS24 ◄── CS11 + CS14 + CS16 + piloto-3

P3 / Investigación futura:
  CS21 (CCD completa via G9) — Eje B post-defensa
  CS22 (cognición distribuida instrumentada) — piloto-3
```

---

## 7. Tabla de estado

Estado inicial al cierre de la sesión 2026-05-16 (creación de este plan). Cada acción inicia en `pendiente`. Las acciones P0 son ejecutables sin gates externos; el resto tiene pre-condiciones explícitas.

| ID | Acción | Prioridad | Estado | Bloqueador |
|---|---|---|---|---|
| CS01 | Enunciar MI1, MI2, MI3 en §4.3 paper / §4.9 tesis | P0 | **CONSOLIDADO 2026-05-16** (paper §4.3 + tesis16mayo §4.9) | revisión coautoral diferida post-consolidación |
| CS02 | Distinguir cii_evolution_intra vs longitudinal en prosa | P0 | **CONSOLIDADO 2026-05-16** (paper §4.5 + tesis16mayo §4.11) | ninguno |
| CS03 | Documentar CCD-piloto-1 vs CCD-conceptual | P0 | **CONSOLIDADO 2026-05-16** (paper §4.5 Tabla 3 + tesis16mayo §4.11) | revisión coautoral diferida post-consolidación |
| CS04 | Análisis de sensibilidad constantes | P0 | script entregado (dry-run OK), ejecución bloqueada | **A1** |
| CS05 | §9 paper / §19.2 tesis: "Proceso vs aprendizaje" | P0 | **CONSOLIDADO 2026-05-16** (paper §9 + tesis16mayo §19.2) | revisión coautoral diferida post-consolidación |
| CS06 | §3: "Cognición distribuida declarada vs operacionalizada" | P0 | **CONSOLIDADO 2026-05-16** (paper §3 + tesis16mayo §3.1) | revisión coautoral diferida post-consolidación |
| CS07 | Glosa "perfil tipológico de" | P0 | **CONSOLIDADO 2026-05-16** (paper §4.4 + tesis16mayo §4.6) | revisión coautoral diferida post-consolidación |
| CS08 | Documentar ratio prompt:exec en código + paper | P0 | **CONSOLIDADO 2026-05-16** (paper §4.5 Tabla 3 + tesis16mayo §5.4 + ct.py) | ninguno |
| CS09 | Protocolo NASA-TLX | P1 | pendiente | revisión coautoral + ética |
| CS10 | Protocolo MAI | P1 | pendiente | revisión coautoral + ética |
| CS11 | Test de transfer (diseño) | P1 | pendiente | revisión coautoral + docentes (validez contenido) |
| CS12 | Escala autoeficacia | P1 | pendiente | revisión coautoral + ética |
| CS13 | Aplicar NASA-TLX + análisis | P2 | pendiente | CS09 + piloto-2 |
| CS14 | Aplicar MAI + análisis | P2 | pendiente | CS10 + piloto-2 |
| CS15 | Aplicar transfer + análisis | P2 | pendiente | CS11 + piloto-2 |
| CS16 | Aplicar autoeficacia + análisis | P2 | pendiente | CS12 + piloto-2 |
| CS17 | EFA sobre 5 coherencias | P2 | pendiente | **A1** |
| CS18 | Tipológica vs dimensional (IRT) | P2 | pendiente | CS15 + A1 |
| CS19 | Clustering alternativo | P2 | pendiente | **A1** |
| CS20 | Calibrar ventanas + ratio | P2 | pendiente | CS04 + dirección + docentes |
| CS21 | CCD completa (G9 activado) | P3 | pendiente | Eje B post-defensa + presupuesto |
| CS22 | Cognición distribuida instrumentada | P3 | pendiente | A1 + decisión académica |
| CS23 | Triangular con ICAP | P3 | pendiente | deseable post-CS19 |
| CS24 | Grupo control | P3 | pendiente | CS11 + CS14 + CS16 + piloto-3 |

---

## 8. Plan de reescritura del paper — sección por sección

Sincronización entre acciones del plan y modificaciones al `paper-draft.md`. Cada modificación al paper se hace **post-decisión de la acción correspondiente**, no antes.

### §1 Resumen / Palabras clave
- **Sin cambio** por este plan. (El informeSocra1.md no observa el resumen directamente.)

### §2 Antecedentes y posicionamiento
- **CS23** (P3): agregar mención breve del framework ICAP (Chi & Wylie, 2014) como antecedente complementario de las taxonomías SOLO/Biggs y Bloom/Anderson ya citadas. **No urgente**.

### §3 Marco teórico
- **CS06** (P0): agregar párrafo explicitando la asimetría entre marco teórico de cognición distribuida (Hutchins, 1995) y operacionalización efectiva (medición individual). Anunciar CS22 como agenda.
- **CS23** (P3): incorporar mapeo ICAP-Modelo N4 en discusión final del marco.

### §4.1-4.2 Los cuatro niveles + operacionalización en eventos
- **Sin cambio** por este plan. La Tabla 1 está validada por el informe cognitivo (es operacionalización clara de eventos).

### §4.3 Tres órdenes epistemológicos
- **CS01** (P0): expansión obligatoria — enunciar MI1, MI2, MI3 explícitamente. Esta es la modificación más importante del paper desde la lente cognitiva.

### §4.4 Tres tipos de apropiación
- **CS07** (P0): primera mención de cada categoría con "perfil tipológico de", luego abreviada a "perfil X". Nota terminológica explicativa.
- **CS19** (P2, posterior): si el clustering empírico converge con la tipología, agregar nota validatoria; si diverge, ampliar la sección con interpretación de la divergencia.

### §4.5 Coherencia estructural multidimensional
- **CS02** (P0): renombrar `cii_evolution` → `cii_evolution_intra` en Tabla 3.
- **CS03** (P0): nota declarando que `ccd_mean` y `ccd_orphan_ratio` en piloto-1 operan en versión reducida (sin rama de prompts reflexivos por `prompt_kind` ausente). Distinción CCD-piloto-1 vs CCD-conceptual.
- **CS08** (P0): nota a pie sobre el ratio prompt:exec=1:2 como decisión de diseño.

### §4.6 Ejemplo canónico
- **Sin cambio** directo. (Posible revisión menor de la prosa si CS07 cambia la convención de nombrado.)

### §6 Hipótesis y método
- **CS09-CS12** (P1): agregar al método los cuatro instrumentos diseñados (NASA-TLX, MAI, transfer test, autoeficacia) con referencia a los protocolos en `docs/research/protocolo-*.md`. Documentar como agenda piloto-2 si no se aplican en piloto-1.
- **CS11** (P1): redactar H2 con referencia explícita al test de transfer como instrumento operacionalizado, no declarativo.
- **CS24** (P3): si se ejecuta grupo control, agregar a la sección de método.

### §7 Plan analítico
- **CS17-CS19** (P2): agregar plan analítico para EFA, comparación tipológica vs dimensional y clustering alternativo. Documentar como análisis previsto.

### §8 Hallazgos preliminares
- **CS04** (P0): agregar Tabla 6.bis (o similar) con resultados de sensibilidad post-A1.
- **CS13-CS19** (P2): nueva subsección §8.X "Validación de constructo" con resultados de cada análisis. **Solo post-piloto-2**.

### Limitaciones (a discutir ubicación con coautoría)

El paper actual NO tiene §15 dedicado a Limitaciones. Las limitaciones del piloto están distribuidas: riesgos a priori al final de §8, limitación del posicionamiento al final de §9. La coautoría debe decidir si conviene **crear** una sub-sección dedicada (§9.X "Limitaciones explícitas" o §10.bis pre-conclusiones) o **integrar** cada CS en ubicaciones existentes:

- **CS05** (P0, aplicado DRAFT en §9): "Proceso observable vs aprendizaje". Anclar en Pellegrino, Chudowsky & Glaser (2001). Ubicación final por decisión coautoral (ver `revision-coautoral-paper-2026-05-16.md` §6).
- **CS06** (P0, aplicado DRAFT en §3): "Cognición distribuida declarada vs operacionalizada". Ubicación final por decisión coautoral (ver `revision-coautoral-paper-2026-05-16.md` §5).
- **CS21** (P3): si CCD completa no se activa antes de la defensa, agregar limitación temporal explícita donde finalmente vivan las limitaciones del paper.

### Anexos
- **CS04**: Anexo C "Análisis de sensibilidad" (post-A1).
- **CS17-CS19**: Anexo D "Análisis de validez de constructo" (post-piloto-2).

### Bibliografía
Agregar referencias citadas por las modificaciones (todas verificadas en el informeSocra1.md):
- Anderson, J. R. (1983, 1996) — ACT-R.
- Bandura, A. (1997) — Self-efficacy.
- Bjork & Bjork (2011) — Desirable difficulties.
- Bransford, Brown & Cocking (2000) — How People Learn.
- Carroll, J. B. (1963) — Time on task.
- Chi et al. (1989); Chi (2000); Chi & Wylie (2014) — Self-explanation + ICAP.
- Cronbach & Meehl (1955) — Construct validity.
- Deci & Ryan (1985) — Self-determination.
- Flavell (1979) — Metacognition.
- Hart & Staveland (1988) — NASA-TLX.
- Koedinger, Corbett & Perfetti (2012) — KLI framework.
- Lord (1980) — IRT.
- Marton & Säljö (1976) — Approaches to learning.
- Messick (1989) — Validity.
- Paas (1992) — Cognitive Load Scale.
- Pellegrino, Chudowsky & Glaser (2001) — Knowing what students know.
- Posner & Petersen (1990) — Attention.
- Rasch (1960) — IRT base.
- Roediger & Karpicke (2006) — Testing effect.
- Schraw (1998); Schraw & Dennison (1994) — Metacognition + MAI.
- Sperling et al. (2002) — Jr. MAI.
- Sweller (1988, 1994, 2011) — Cognitive load theory.
- Veenman et al. (2006) — Metacognition & learning.

---

## 9. Riesgos del plan mismo

Honestidad sobre los problemas que este plan puede tener.

### 9.1 Sobre-corrección del paper

Si todas las acciones P0 se ejecutan, el paper crecerá ~5-10 páginas (entre §3, §4.3, §4.4, §4.5, §9 y bibliografía; eventualmente una sub-sección de limitaciones dedicada si la coautoría decide crearla). Riesgo: el paper se vuelve más defensivo que afirmativo. Mitigación: la coautoría con Ana Garis debe decidir cuáles modificaciones se materializan en el cuerpo del paper y cuáles van a anexos.

### 9.2 La n del piloto-1 es marginal para EFA

CS17 (EFA) requiere idealmente n ≥ 150 observaciones. El piloto-1 tiene 106 classifications. Si el EFA es inviable con n=106, hay dos opciones: (a) posponer a piloto-2 con n acumulado; (b) reportar análisis exploratorio con caveat explícito sobre limitaciones de muestra. Decisión humana.

### 9.3 Los instrumentos adicionales (NASA-TLX, MAI, transfer, autoeficacia) suman carga sobre los estudiantes

Aplicarlos todos en piloto-2 puede ser invasivo y producir efecto de saturación. Mitigación: aplicación parcial (una fracción aleatoria de estudiantes para cada instrumento) o aplicación distribuida en el tiempo. Decisión coautoral.

### 9.4 G9 (CCD completa) es agenda Eje B sin presupuesto declarado

CS21 depende de implementar clasificación semántica de prompts via `ai-gateway` con costos BYOK reales. Sin presupuesto explícito para piloto-3, esta acción puede quedar en limbo años. Mitigación: declarar explícitamente en el paper que CCD vigente en piloto-1 (versión reducida) será la versión validada en la defensa; G9 queda como agenda Eje B post-defensa sin compromiso de timeline.

### 9.5 Grupo control (CS24) puede ser inviable por consideraciones éticas y de coordinación

Comparar estudiantes con/sin tutor AI en el mismo cuatrimestre es éticamente complejo (asignación aleatoria a "intervención que se presume mejor") y operacionalmente difícil (requiere dos cohortes paralelas). Mitigación: discutir con comité ético UTN antes de incluirlo en agenda. Alternativa: comparación pre/post con la misma cohorte (less rigoroso pero más viable).

### 9.6 Las acciones P0 dependen mucho de la disponibilidad de Ana Garis

Siete de las ocho acciones P0 requieren revisión coautoral. Si Ana Garis tiene baja disponibilidad, el bottleneck se traslada al plan. Mitigación: agrupar revisiones (dos o tres CS revisadas en una misma sesión) y/o autorizar al autor a tomar decisiones reversibles sobre redacción.

---

## 10. Próximos pasos concretos (a coordinar)

Lo inmediato (esta semana o la siguiente):

1. **Compartir este plan con Ana Garis** para revisión + priorización.
2. **Decidir cuáles P0 son non-negotiable pre-defensa**: la lectura del autor de este plan es que CS01, CS02, CS03, CS05 son non-negotiable; CS04 es non-negotiable si A1 cierra antes; CS06, CS07, CS08 son fuertemente recomendados.
3. **Iniciar CS02 y CS08** (no requieren revisión coautoral, sin riesgo): ejecutables por sub-agente esta misma semana.
4. **Agendar sesión coautoral** para CS01, CS03, CS05, CS06, CS07 (5 acciones interconectadas). Estimado de la sesión: 2-3 h.
5. **Para CS04**: confirmar timeline de A1 con dirección. Si A1 cierra antes de la defensa, ejecutar CS04 en cuanto cierre.
6. **Para CS09-CS12**: discutir con comité ético UTN la viabilidad de instrumentos adicionales en piloto-2.

Lo de mediano plazo (próximos 2-3 meses, post-A1):

7. **Ejecutar CS04, CS17, CS19** en cascada sobre las 106 históricas re-clasificadas.
8. **Decidir Eje B**: discutir con dirección + co-dirección si CS21 (CCD completa) entra en agenda piloto-3 con presupuesto o queda como Eje futuro sin compromiso.

---

## 11. Versionado de este plan

- **1.0.0** (2026-05-16) — versión inicial post-informeSocra1.md.
- *Pendiente 1.1.0* — incorporar feedback de Ana Garis sobre priorización y alcance.
- *Pendiente 1.2.0* — actualizar tras decisión de Eje B y timeline A1.

Cada versión se commitea aparte. Las acciones cerradas en una versión NO se reabren en versiones posteriores — si necesitan revisión, abren un CS nuevo con referencia explícita.

---

## 12. Referencias

- `informeSocra1.md` (2026-05-16) — análisis cognitivo de origen.
- `informeSoc.md` (2026-05-16) — análisis didáctico socrático complementario.
- `paper-draft.md` (`docs/papers/paper-draft.md` en AI-NativeV3-main) — objeto de las reescrituras.
- `AI-NativeV3-main/docs/research/` — destino de los protocolos de instrumentos.
- `plan-accion.md` (referencia histórica) — A1, A2, A3, A5 son gates externos.
- ADRs vigentes que este plan referencia: 010 (CTR append-only), 018 (CII longitudinal), 020 (event labeler), 022 (alertas), 027 (Fase B), 035 (reflexión excluida), 044, 045, 046 (intercoder κ ≥ 0.70), 050, 051, 052 (los 3 nuevos esqueletos).
- Marco teórico citado (lista completa en bibliografía del informeSocra1.md §10).
