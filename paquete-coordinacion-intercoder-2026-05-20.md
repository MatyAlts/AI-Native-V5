# Paquete de coordinación — Validación intercoder κ ≥ 0,70 (Protocolos A + B)

**Fecha de preparación**: 2026-05-20
**Para**: Alberto A. Cortez (director tesis), Ana Garis (co-directora paper)
**Audiencia operacional**: 2 docentes UTN a designar como etiquetadores externos + DI UTN para coordinación logística
**Objetivo**: destrabar la ejecución de A2 del `plan-accion.md` — la validación intercoder es el **cuello de botella académico más grande del proyecto** (bloquea H3 del paper + features OFF `socratic_compliance` ADR-044 y `lexical_anotacion` ADR-045).

> **Nota operativa**: este paquete consolida los pasos operativos pendientes para ejecutar el protocolo dual formalizado en ADR-046. **NO reemplaza** al `manual-etiquetador-N4.md` (294 líneas, fuente operacional para los 2 docentes) ni al ADR-046 (decisión académica formal). **Los complementa** con lo que falta para que la coordinación arranque: script de selección de corpus, paquete de reclutamiento, cronograma y reporte esperado.

---

## 0. Resumen ejecutivo

ADR-046 (2026-05-10) formaliza la validación intercoder dual: 200 eventos estratificados (Protocolo A) + 50 episodios cerrados (Protocolo B) etiquetados por 2 docentes UTN independientes. Umbral κ ≥ 0,70 en al menos 2 de 3 pares (Clasificador vs A1, Clasificador vs A2, A1 vs A2).

**Lo que ya existe operacionalmente**:
- ✅ ADR-046 — decisión formal del umbral + protocolo dual
- ✅ `manual-etiquetador-N4.md` (1.0.0) — criterios operacionales por nivel/categoría con casos límite
- ✅ `event_labeler.py` y `tree.py` — funciones puras de referencia
- ✅ Plan de contingencia documentado (qué hacer si κ entre 0,40-0,69 o <0,40)

**Lo que este paquete entrega**:
- §1 Pre-calibración interna (paso no-saltable de R3 del informeSoc.md)
- §2 Script de selección de corpus (especificación + signature para implementación en `AI-NativeV3-main/scripts/`)
- §3 Criterios de reclutamiento de docentes
- §4 Carta de invitación (template editable)
- §5 Acuerdo de confidencialidad (template editable)
- §6 Cronograma realista
- §7 Template de reporte intercoder
- §8 Decisiones operativas pendientes que requieren input del usuario

**Costo total estimado**: ~10h (pre-calibración director+codirector) + ~50-60h (2 docentes × 25-30h) + 2-4 semanas calendario para coordinación.

---

## 1. Pre-calibración interna (no saltable)

Por R3 del `informeSoc.md` y §3 del `manual-etiquetador-N4.md`: **antes de invitar a los 2 docentes externos**, director + co-director pilotean el manual sobre **20 eventos del Protocolo A + 5 episodios del Protocolo B**. Razón: si el manual tiene ambigüedades operacionales, el κ saldrá bajo no por desacuerdo conceptual sino por uso inconsistente de criterios. La pre-calibración detecta esto con ~10h de los directores vs ~50-60h docentes externos malgastadas.

### 1.1 Protocolo de pre-calibración (semana 0)

| Día | Actividad | Tiempo |
|---|---|---|
| 0 | Cortez + Garis reciben: este paquete + `manual-etiquetador-N4.md` + 20 eventos Protocolo A + 5 episodios Protocolo B (output del script §2 modo `--mode=internal-calibration --n-events=20 --n-episodes=5`) | 1h lectura |
| 1-3 | Cada uno etiqueta **independientemente** (no conversan). Llenan campos `nivel_propuesto_por_etiquetador` (Protocolo A) o `categoria_propuesta_por_etiquetador` (Protocolo B) en los YAML | 4-6h cada uno |
| 4 | Sesión conjunta de 90 min: comparar etiquetas → identificar discrepancias → para cada una: ¿es por ambigüedad del manual o por error de uno? Si es por ambigüedad: añadir caso límite al manual §1.3 o §2.3 | 1.5h |
| 5 | Re-etiquetar los 20 eventos + 5 episodios con manual actualizado. Computar κ interno | 1.5h |

### 1.2 Decisión de avance post-pre-calibración

- κ_interno ≥ 0,70 → **invitar a los 2 docentes UTN** (saltar a §3).
- κ_interno entre 0,40 y 0,69 → segunda iteración del manual + segunda ronda interna sobre 20 eventos NUEVOS.
- κ_interno < 0,40 → revisar operacionalización de fondo. **No invitar docentes hasta resolver.**

### 1.3 Bumpear manual a 1.1.0

Cuando termine la pre-calibración, bumpear `manual-etiquetador-N4.md` a versión `1.1.0` incorporando los casos límite descubiertos. La versión 1.1.0 es la que se entrega a los docentes externos. **Cada ronda intercoder se hace con un manual congelado**; rondas con manuales distintos no son comparables.

---

## 2. Script de selección de corpus

### 2.1 Especificación

**Path sugerido**: `AI-NativeV3-main/scripts/select-intercoder-corpus.py`

**Pre-requisitos**:
- Acceso a las 4 bases del piloto (`academic_main`, `ctr_store`, `classifier_db`, `content_db`)
- Variables de entorno: `ACADEMIC_DB_URL`, `CTR_STORE_URL`, `CLASSIFIER_DB_URL`
- A1 cerrada (re-clasificación de las 106 históricas con `LABELER_VERSION=1.2.0`) — sino el corpus contiene mezcla de versiones

**Signature propuesta**:

```bash
python scripts/select-intercoder-corpus.py \
  --mode {internal-calibration | protocol-a | protocol-b | full} \
  --n-events 200 \
  --n-episodes 50 \
  --seed 20260520 \
  --output-dir docs/research/intercoder-corpus/round-01/ \
  --truncate-content-chars 40 \
  --include-consent-records \
  [--dry-run]
```

### 2.2 Comportamiento esperado

**Modo `internal-calibration`** (para §1 pre-calibración):
- 20 eventos del Protocolo A (5 por nivel cognitivo N1-N4)
- 5 episodios del Protocolo B (~2 reflexiva + 2 superficial + 1 delegación pasiva)
- Output: 25 archivos YAML (formato del `manual-etiquetador-N4.md` §1.5 y §2.4)

**Modo `protocol-a`** (para validación con docentes externos):
- 200 eventos estratificados, 50 por nivel cognitivo N1-N4
- Selección sugerida (per manual §1.2):
  - 50 eventos N1: `lectura_enunciado` + `anotacion_creada` con override N1
  - 50 eventos N2: `edicion_codigo` con `origin=student_typed` + `anotacion_creada` sin overrides
  - 50 eventos N3: `codigo_ejecutado` + `tests_ejecutados` etiquetados N3 por regla v1.2.0
  - 50 eventos N4: `prompt_enviado`, `tutor_respondio`, `intento_adverso_detectado`, `edicion_codigo` copy, `anotacion_creada` override N4, `tests_ejecutados` N4
- Preservar contexto ±60s de cada evento (eventos cercanos que afectan overrides temporales)
- Truncar `payload.content` a 40 chars (privacidad — consentimiento informado no cubre piloto-1 textual completo, ver `docs/limitaciones-declaradas.md`)
- Output: 200 archivos YAML en `output-dir/protocol-a/`
- Output auxiliar: `output-dir/ground-truth-protocol-a.csv` con (`event_id`, `nivel_funcion_pura`) — para computar κ después; **NO entregar a etiquetadores**

**Modo `protocol-b`** (validación de árbol de apropiación):
- 50 episodios cerrados distribuidos ~16-17 por categoría (apropiacion_reflexiva, apropiacion_superficial, delegacion_pasiva)
- Para episodios de Protocolo B: NO truncar prompts del estudiante (la categoría depende del discurso) — **requiere consentimiento informado específico**
- Output: 50 archivos YAML en `output-dir/protocol-b/` + `ground-truth-protocol-b.csv`

**Modo `full`**: ejecuta protocol-a + protocol-b en una sola corrida (recomendado para round real).

**Modo `--dry-run`**: usa datos sintéticos (no DB) para verificar el flujo. Útil para probar el formato de output antes de tener DB real.

### 2.3 Reproducibilidad

- `--seed` fija el random sample. Misma seed + mismo dataset → mismos eventos seleccionados.
- Persistir la seed en `output-dir/metadata.json` junto con timestamps, `classifier_config_hash` vigente, versión del manual usado, n total disponible por estrato.

### 2.4 Validación post-selección

Antes de entregar a los 2 docentes externos:
1. `grep -c "nivel_propuesto_por_etiquetador: ___" output-dir/protocol-a/*.yaml` → 200 (todos los campos vacíos para llenar)
2. `cat output-dir/ground-truth-protocol-a.csv | tail -n +2 | awk -F, '{print $2}' | sort | uniq -c` → exactamente `50 N1 / 50 N2 / 50 N3 / 50 N4`
3. Manual inspection de 5-10 fichas aleatorias para confirmar que `payload.content` está truncado a 40 chars

### 2.5 Quién implementa el script

- **Esfuerzo**: 8-12h dev + 2h verificación con `--dry-run`.
- **Dependencias**: `event_labeler.py::label_event` (función pura ya existente), SQLAlchemy queries sobre `ctr_store.events` + `classifier_db.classifications`.
- **Bloqueador externo**: A1 cerrada (post `scripts/reclassify-legacy-106.py` corrida contra DB real UTN — sub-sprint 4 ya lo creó).
- **Owner**: dev backend desde `AI-NativeV3-main/`.

---

## 3. Criterios de selección y reclutamiento de docentes

### 3.1 Perfil del etiquetador ideal

Por convenio del proyecto + recomendación de `informeSoc.md`:

- **Docente con experiencia en programación universitaria**, idealmente CS1/CS2 o cátedras introductorias relacionadas a la programación.
- **Familiaridad con el contexto del piloto UTN** — conoce la modalidad evaluativa de la cátedra y los perfiles típicos de estudiantes de los cursos involucrados.
- **Disponibilidad real de 25-30h durante 4-6 semanas calendarias** para etiquetado + reunión de calibración + sesión final de revisión.
- **Independencia académica del proyecto**: NO debe ser autor del paper ni participante en el desarrollo del código del sistema instrumental. Razón: la validación intercoder pierde valor si los etiquetadores ya internalizaron las decisiones del clasificador.
- **Capacidad de seguir un manual operacional con disciplina**: la convergencia de κ exige que los etiquetadores no improvisen, sino que apliquen el manual con consistencia. Docentes que tienden a "interpretar libremente" son problemáticos.

### 3.2 Cuántos y cómo

- **Cantidad**: 2 etiquetadores. ADR-046 fija esta cantidad.
- **Selección sugerida**: 1 docente con perfil más teórico (afín a Mislevy/Evidence-centered design) + 1 docente con perfil más operativo (afín a la implementación práctica de CS1). Los dos perfiles aportan triangulación cualitativa: cuando discrepan, la razón del desacuerdo suele revelar matices distintos del modelo.
- **Backup**: identificar a 1 docente adicional como respaldo en caso de que algún titular se baje. La calibración del backup es opcional hasta que se active.

### 3.3 Compensación

A decidir con dirección del programa de doctorado. Opciones típicas:
- Reconocimiento como anotadores en una publicación derivada del piloto (mencionados en agradecimientos del paper o como co-autores de un paper técnico secundario).
- Carga académica reconocida formalmente por la facultad si el convenio lo permite.
- Pago por hora si hay presupuesto del PID/UTN asignado.

---

## 4. Carta de invitación (template editable)

> Estimado/a [NOMBRE DOCENTE],
>
> En el marco del proyecto de tesis doctoral "Modelo AI-Native con Trazabilidad Cognitiva N4 para la Formación en Programación Universitaria" (Cortez, UTN — Garis, UTN-FRM), te invitamos a participar como **etiquetador externo independiente** en la validación intercoder del clasificador cognitivo del sistema.
>
> **Qué se valida**: dos componentes del sistema clasificador, ambos formalizados en ADR-046 del repositorio:
> 1. **Protocolo A — Etiquetado de eventos N1-N4**: 200 eventos del Cognitive Trace Record (CTR) del piloto, estratificados 50 por nivel cognitivo. Validás que la función automática del sistema etiquete eventos correctamente según el modelo.
> 2. **Protocolo B — Etiquetado de episodios por apropiación**: 50 episodios cerrados clasificados en una de tres categorías (apropiación reflexiva, apropiación superficial, delegación pasiva). Validás que el árbol de decisión del sistema clasifique episodios correctamente.
>
> **Umbral**: el estudio busca κ ≥ 0,70 en al menos 2 de 3 pares (sistema vs vos, sistema vs otro etiquetador, vos vs otro etiquetador). Umbral elegido por consistencia con literatura del campo (Landis & Koch, 1977; AERA/APA/NCME, 2014).
>
> **Compromiso de tiempo estimado**:
> - **Lectura del manual y formato del corpus**: 2-3h.
> - **Etiquetado independiente del Protocolo A** (200 eventos): 12-15h, distribuibles en 4-6 sesiones a tu conveniencia durante 2-3 semanas.
> - **Etiquetado independiente del Protocolo B** (50 episodios): 8-12h, distribuibles en 3-4 sesiones durante 1-2 semanas posteriores.
> - **Sesión de calibración inicial** (online, conjunta con el segundo etiquetador y la dirección): 1.5h.
> - **Sesión final de revisión** (online, conjunta para casos discrepantes): 1.5-2h.
> - **Total**: aproximadamente **25-30h** distribuidas en **4-6 semanas calendario**.
>
> **Material que recibís**:
> - Manual del etiquetador (`manual-etiquetador-N4.md`, versión 1.1.0 post-pre-calibración) — guía operacional con criterios por nivel/categoría y casos límite resueltos.
> - 200 fichas YAML del Protocolo A + 50 dossiers YAML del Protocolo B, generados con seed reproducible.
> - Plantilla de Google Sheets o herramienta similar para que registres tus etiquetas.
> - Acuerdo de confidencialidad sobre el contenido de los episodios (los prompts de los estudiantes son material sensible — ver §5 abajo).
>
> **Lo que NO recibís**:
> - Las etiquetas que produjo el sistema automático ni las etiquetas del otro etiquetador. Trabajás independientemente.
> - Acceso al código del clasificador (no es necesario para etiquetar — el manual es autosuficiente).
>
> **Reconocimiento**: tu participación queda reconocida en los agradecimientos del paper Cortez & Garis (CONAIISI 2025) y en la tesis doctoral de Cortez. Si el estudio intercoder se publica como artículo técnico independiente, sos co-autor.
>
> ¿Aceptás participar? Si querés discutir detalles antes de confirmar, podemos agendar una llamada de 30 minutos.
>
> Saludos cordiales,
> Alberto Cortez (cortezalberto@gmail.com)
> Ana Garis ([CONTACTO GARIS])

---

## 5. Acuerdo de confidencialidad (template editable)

> **ACUERDO DE CONFIDENCIALIDAD — ESTUDIO INTERCODER PROYECTO AI-NATIVE N4**
>
> Entre [NOMBRE DOCENTE], en adelante "el Etiquetador", y Alberto A. Cortez (director de tesis doctoral UTN), en adelante "el Investigador Principal", se acuerda lo siguiente:
>
> 1. **Objeto**: el Etiquetador recibe acceso a material de investigación derivado del piloto pedagógico AI-Native N4 ejecutado en la cátedra [NOMBRE CÁTEDRA] de la UTN durante el período [PERÍODO]. El material incluye:
>    - Eventos del Cognitive Trace Record de los estudiantes participantes (prompts truncados a 40 caracteres en Protocolo A, prompts completos en Protocolo B).
>    - Episodios cerrados con sus cadenas de eventos asociadas.
>    - Identificadores pseudonimizados de estudiantes (UUID `student_pseudonym`, NO datos personales identificables).
>
> 2. **Compromisos del Etiquetador**:
>    a. NO copiar, transferir, publicar ni distribuir el material a terceros.
>    b. Almacenar el material localmente en dispositivos personales con protección de acceso razonable (contraseña de sesión + cifrado de disco si aplica).
>    c. NO intentar des-anonimizar a los estudiantes mediante cruzamiento con otros datos a los que el Etiquetador tenga acceso por su rol docente.
>    d. Eliminar el material al cierre del estudio (post-publicación del paper derivado).
>    e. Mantener confidencialidad sobre el contenido específico de los prompts de los estudiantes incluso después del cierre del estudio.
>
> 3. **Compromisos del Investigador Principal**:
>    a. NO incluir en el material entregado al Etiquetador información personal identificable de los estudiantes.
>    b. Asegurar que los estudiantes cuyos datos se incluyan en Protocolo B hayan otorgado consentimiento informado específico para uso del contenido textual completo de sus prompts en investigación.
>    c. Mencionar al Etiquetador en los agradecimientos del paper y de la tesis derivados del estudio (o como co-autor si corresponde, según §3.3 del paquete de coordinación).
>
> 4. **Vigencia**: este acuerdo rige desde la fecha de firma hasta la publicación del paper derivado o hasta 24 meses desde la firma, lo que ocurra primero.
>
> 5. **Jurisdicción**: cualquier disputa derivada de este acuerdo se resuelve en la jurisdicción de la Universidad Tecnológica Nacional.
>
> Firmado en [LUGAR] a los [DÍA] días del mes de [MES] de [AÑO].
>
> _______________________
> [NOMBRE DOCENTE], Etiquetador
>
> _______________________
> Alberto A. Cortez, Investigador Principal

> **Nota operativa**: este template requiere revisión jurídica institucional UTN antes de la firma. La cláusula §2.c es particularmente sensible — un docente de la cátedra del piloto puede ya conocer a los estudiantes por contexto, y el acuerdo no debe poner al Etiquetador en posición de violar una expectativa razonable.

---

## 6. Cronograma realista

Asumiendo aprobación coautoral del paquete + acceso a DB UTN razonablemente expedito:

| Semana | Hito | Responsable | Dependencias |
|---|---|---|---|
| 0 | Implementar `scripts/select-intercoder-corpus.py` con `--dry-run` funcional | Dev backend | A1 cerrada (DB UTN accesible) |
| 0 | Corrida `--mode=internal-calibration` → 20 eventos + 5 episodios YAML | Cortez | Script listo |
| 1 | Pre-calibración Cortez + Garis (3-5 días de etiquetado independiente + sesión 90 min) | Cortez + Garis | Material de calibración listo |
| 1 | Bumpear `manual-etiquetador-N4.md` a 1.1.0 con casos límite descubiertos | Cortez | Sesión de calibración cerrada |
| 2 | Identificar y contactar 2 docentes UTN candidatos | Cortez + dirección programa | Manual 1.1.0 |
| 2 | Reuniones de presentación con cada docente (1 cada uno) | Cortez | Docentes contactados |
| 3 | Firma del acuerdo de confidencialidad + entrega del manual 1.1.0 | Cortez + 2 docentes | Reuniones cerradas + revisión jurídica UTN |
| 3 | Corrida `--mode=full` → 200 + 50 YAML + ground-truth CSV | Cortez | Acuerdo firmado |
| 3 | Sesión inicial de calibración conjunta (2 docentes + dirección, 1.5h online) | Cortez + Garis + 2 docentes | Material entregado |
| 4-6 | Etiquetado independiente del Protocolo A por ambos docentes | 2 docentes | Sesión inicial cerrada |
| 7-8 | Etiquetado independiente del Protocolo B por ambos docentes | 2 docentes | Protocolo A cerrado |
| 8 | Computo κ por pares (3 pares: sistema vs A1, sistema vs A2, A1 vs A2) por Protocolo | Cortez (script analytics-service) | Etiquetados cerrados |
| 8 | Sesión final de revisión de casos discrepantes (2 docentes + dirección, 1.5-2h online) | Cortez + Garis + 2 docentes | κ computado |
| 9 | Decisión de gate: κ ≥ 0,70 en 2 de 3 pares por Protocolo → activar features OFF + actualizar paper §7.1 con κ real reportado | Cortez + Garis | Sesión final cerrada |
| 9 | Si κ entre 0,40-0,69 en algún par: segunda ronda con remuestreo de 50 nuevos eventos/episodios | Cortez + 2 docentes (potencialmente) | Reporte de discrepancia |

**Total**: aproximadamente **8-10 semanas calendario** desde script implementado hasta gate cerrado, asumiendo buena coordinación. Si κ no cierra en primera ronda, sumar 4-6 semanas más para segunda ronda.

**Riesgo crítico de cronograma**: si las semanas 4-8 caen sobre vacaciones académicas o finales, la disponibilidad de los docentes cae drásticamente. Coordinar inicio del estudio con el calendario académico UTN.

---

## 7. Template de reporte intercoder

Cuando se cierre el estudio (post sesión final de revisión), Cortez produce un reporte estructurado para anexar al paper §7.1 y al cuerpo de la tesis. Path sugerido: `docs/research/reporte-intercoder-round-01-{fecha}.md`.

### 7.1 Estructura del reporte

```markdown
# Reporte intercoder — Round 01 ({fecha cierre})

## 1. Configuración
- Manual usado: manual-etiquetador-N4.md v1.1.0 (hash: ...)
- Script de selección: scripts/select-intercoder-corpus.py v1.0.0 (seed: 20260520)
- Etiquetadores: [INICIALES DOCENTE 1], [INICIALES DOCENTE 2]
- Período: {fecha inicio} a {fecha cierre}

## 2. Resultados Protocolo A (200 eventos)

| Par | κ Cohen | IC 95% bootstrap | Acuerdo (%) | Discrepancias |
|---|---|---|---|---|
| Sistema vs Etiquetador 1 | X.XX | [X.XX, X.XX] | XX% | XX |
| Sistema vs Etiquetador 2 | X.XX | [X.XX, X.XX] | XX% | XX |
| Etiquetador 1 vs Etiquetador 2 | X.XX | [X.XX, X.XX] | XX% | XX |

**Veredicto Protocolo A**: [κ ≥ 0,70 en 2 de 3 pares] ✅ o ❌

## 3. Resultados Protocolo B (50 episodios)

[Misma tabla que §2 pero para B]

**Veredicto Protocolo B**: ✅ o ❌

## 4. Análisis cualitativo de discrepancias

[Para cada par, listado de eventos/episodios discrepantes con análisis: ¿error del etiquetador, ambigüedad residual del manual, fallo legítimo del clasificador?]

## 5. Decisiones derivadas

- Si veredicto ambos protocolos ✅: activar `socratic_compliance_enabled = True` y `lexical_anotacion_override_enabled = True`. Bumpear `LABELER_VERSION` a `2.0.0` (cambio semántico). Re-clasificar las 106 históricas con el nuevo labeler.
- Si veredicto algún protocolo ❌: segunda ronda con remuestreo + manual 1.2.0.

## 6. Anexos
- Tablas de etiquetado completas (Protocolo A y B) en `intercoder-corpus/round-01/labels/`.
- Script de análisis κ usado: `scripts/compute-kappa.py`.
- Reproducibilidad: con seed 20260520 + manual v1.1.0 + corpus en `intercoder-corpus/round-01/` → mismas etiquetas y mismo κ.
```

### 7.2 Para el paper §7.1

El paper §7.1 debe actualizarse con κ reales reportados (no genéricos). Texto sugerido (placeholder):

> "La validación intercoder ejecutada con dos docentes UTN independientes sobre el corpus dual A+B (n_A=200, n_B=50) durante el período [fechas] arrojó coeficientes κ de Cohen de: Protocolo A [X.XX (sistema-A1), X.XX (sistema-A2), X.XX (A1-A2)]; Protocolo B [X.XX, X.XX, X.XX]. El umbral κ ≥ 0,70 se alcanzó en [N] de 3 pares para Protocolo A y [N] de 3 pares para Protocolo B, validando [el etiquetador / el árbol de apropiación / ambos] del sistema instrumental."

---

## 8. Decisiones operativas pendientes que requieren input del usuario

Estas son las decisiones que solo Cortez (eventualmente con Garis y dirección del programa) puede tomar:

1. **Identidad de los 2 docentes candidatos**: nombres concretos + nivel de compromiso esperado. Idealmente confirmar disponibilidad antes de implementar el script de selección.
2. **Compensación**: forma concreta (autoría, agradecimiento, pago, carga académica reconocida).
3. **Backup**: 1 docente adicional como reserva.
4. **Revisión jurídica del acuerdo de confidencialidad**: pasar el template §5 por la oficina jurídica UTN antes de mandar a los docentes.
5. **Consentimiento informado de los estudiantes para Protocolo B**: confirmar que los estudiantes cuyos episodios se incluyan en Protocolo B firmaron consentimiento específico para uso del contenido textual completo. Si no, restringir Protocolo B a episodios con consentimiento ya otorgado o solicitar consentimiento adicional retroactivo.
6. **Fechas concretas**: alinear el cronograma §6 con el calendario académico UTN (evitar finales y vacaciones).
7. **Quién implementa el script de selección**: ¿dev interno del proyecto, becario contratado, o el propio Cortez? El esfuerzo estimado es 8-12h, no trivial pero acotado.

---

## 9. Riesgos identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Docentes no disponibles en cronograma | Media | Alto | Identificar 2 + 1 backup ANTES de implementar el script; coordinar con calendario académico UTN |
| κ < 0,70 en primera ronda Protocolo A | Media | Medio | Pre-calibración interna §1 reduce este riesgo; plan de contingencia ADR-046 lo cubre |
| κ < 0,70 en primera ronda Protocolo B (más probable) | Alta | Medio | Manual del etiquetador §2.3 advierte que el árbol tiene categorías más interpretativas; sesión final de revisión es donde se resuelve la discrepancia |
| Falta de consentimiento informado para Protocolo B textual completo | Alta si no se planificó | Alto | Verificar consentimiento existente del piloto; si no cubre prompts completos, restringir Protocolo B a episodios con consentimiento explícito |
| Bajo presupuesto / motivación de docentes (sin compensación adecuada) | Media | Alto | Decisión §8.2 prioritaria; reconocimiento como co-autores suele ser suficiente en contexto académico UTN |
| Acceso a DB UTN retrasado más de 4 semanas | Media | Alto | Mientras tanto, ejecutar pre-calibración con `--dry-run` (datos sintéticos) — no es lo ideal pero permite avanzar el manual y la coordinación |

---

## 10. Anexos: referencias cruzadas

### 10.1 Archivos relevantes

- **`AI-NativeV3-main/docs/adr/046-kappa-threshold-070-paper-alignment.md`** — decisión académica formal (umbral + protocolo dual). Fuente de verdad.
- **`AI-NativeV3-main/docs/research/manual-etiquetador-N4.md`** (versión 1.0.0 pendiente bumpear a 1.1.0 post-pre-calibración) — guía operacional para los 2 docentes.
- **`AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/event_labeler.py`** — función pura del Protocolo A.
- **`AI-NativeV3-main/apps/classifier-service/src/classifier_service/services/tree.py`** — árbol del Protocolo B.
- **`AI-NativeV3-main/docs/limitaciones-declaradas.md`** — registro de gates pendientes (incluyendo consentimiento informado para corpus textual completo).
- **`docs/research/plan-accion.md` A2** (del wrapper) — la acción que este paquete destraba.

### 10.2 Referencias bibliográficas

- Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics*, 33(1), 159-174.
- AERA, APA, & NCME (2014). *Standards for educational and psychological testing*. American Educational Research Association.
- Mislevy, R. J., Steinberg, L. S., & Almond, R. G. (2003). Focus article: On the structure of educational assessments. *Measurement*, 1(1), 3-62.
- Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement*, 20(1), 37-46.
- ADR-046 — Umbral kappa intercoder a 0,70 + protocolo dual.

### 10.3 Quién hace qué (resumen)

| Tarea | Responsable | Esfuerzo |
|---|---|---|
| Implementar `scripts/select-intercoder-corpus.py` | Dev backend desde subdir | 8-12h |
| Pre-calibración interna (etiquetar 20+5) | Cortez + Garis | 4-6h cada uno + 1.5h sesión |
| Bumpear manual a 1.1.0 | Cortez (sub-agente puede ayudar con redacción) | 1-2h |
| Identificar y contactar docentes | Cortez + dirección programa | semanas calendario |
| Revisión jurídica acuerdo confidencialidad | Oficina jurídica UTN | semanas calendario |
| Verificar consentimiento informado estudiantes Protocolo B | Cortez + comité ético UTN | semanas calendario |
| Etiquetado de los 2 docentes | 2 docentes UTN | 25-30h cada uno, 4-6 semanas calendario |
| Computo κ + reporte | Cortez (script analytics-service ya existe) | 4-6h post-etiquetado |
| Activación de features OFF si gate ✅ | Dev backend desde subdir | 2-3h + tests |

---

**Generado**: 2026-05-20 por sesión de coordinación post-cleanup docs gobernanza. Espejo estructural del `revision-coautoral-instrumentos-2026-05-20.md` para que el formato sea familiar a Garis.
