# Comparación: `gaby.docx` vs `paper16mayo.docx`

**Fecha del análisis**: 2026-05-16
**Archivos comparados**:
- `docs/papers/gaby.docx` (47 KB, fecha de archivo 2026-05-16 17:20, fecha declarada de generación 2026-05-10)
- `paper16mayo.docx` (42 KB, fecha de archivo 2026-05-16 23:30, generado en esta sesión a partir de `docs/papers/paper-draft.md`)

**Método**: ambos archivos convertidos a markdown con pandoc + `--wrap=none`, diff de estructura de secciones, lectura de bloques específicos, identificación de contenido único en cada uno.

---

## 0. Resumen ejecutivo

La evolución **no es estrictamente lineal**. `paper16mayo.docx` tiene siete contribuciones cognitivas nuevas que `gaby.docx` no incorpora; recíprocamente, `gaby.docx` tiene un Apéndice A operativo completo, una sub-sección sobre reproducibilidad del estado del sistema y una sección de Procedencia que `paper16mayo.docx` perdió. La situación es de **dos ramas paralelas** con valor complementario: la lectura honesta es que **una versión final óptima sería el merge de ambas**, no la simple sustitución de una por la otra.

| Aspecto | `gaby.docx` (versión PID, 2026-05-10) | `paper16mayo.docx` (versión cognitiva, 2026-05-16) |
|---|---|---|
| **Origen declarado** | Procedencia explícita: ppcona.docx + ppconarev.md + papermod.md + 10 decisiones académicas resueltas el 2026-05-10 + ADR-046 | paper-draft.md base + 7 ediciones derivadas del análisis cognitivo externo (informeSocra1.md → plan1Socra.md → CS01-CS08) |
| **Pre-ediciones consolidadas** | ✅ Las 10 decisiones académicas (Camino 1 + protocolo dual + 4 temáticas) | ✅ Las 10 decisiones académicas heredadas + las 7 ediciones cognitivas adicionales |
| **Aportes cognitivos CS01-CS08** | ❌ Ninguno (versión previa al análisis cognitivo del 2026-05-16) | ✅ Las 7 ediciones consolidadas en texto |
| **Apéndice A operativo** | ✅ A.1 sharding CTR, A.2 Casbin+RLS, A.3 manifest-config, A.4 Tabla de constantes auditables | ❌ Ausente |
| **§7 con sub-secciones** | ✅ 7.1 kappa + 7.2 reproducibilidad del estado del sistema + 7.3 equidad | ❌ Solo §7.4 equidad; el resto en prosa sin sub-secciones |
| **Procedencia del documento** | ✅ Sección explícita al final | ❌ Reemplazada por "Notas para coautores" (texto provisional) |
| **Cierre operativo** | ✅ "Generado: 2026-05-10" | ⚠️ "Notas para coautores" |

---

## 1. Métricas comparadas

| Métrica | `gaby.docx` | `paper16mayo.docx` |
|---|---|---|
| Tamaño del .docx | 47.091 bytes | 41.741 bytes |
| Líneas en markdown (post-pandoc) | 415 | 379 |
| Caracteres totales | ~105.297 | ~94.610 |
| Secciones principales (§1-§10) | ✓ | ✓ |
| Apéndice A | ✓ (4 sub-secciones) | — |
| Sub-secciones §7 (7.1, 7.2, 7.3) | 3 sub-secciones | 1 sub-sección (§7.4) |
| Bibliografía | ✓ | ✓ |
| Procedencia | ✓ | "Notas para coautores" en su lugar |

---

## 2. Lo que `paper16mayo.docx` tiene y `gaby.docx` NO tiene

Estas son las siete ediciones consolidadas en `paper16mayo.docx` derivadas del análisis cognitivo externo (`informeSocra1.md`) y planificadas en `plan1Socra.md` como CS01-CS08:

### 2.1 CS01 — Enunciación explícita de MI1, MI2, MI3 en §4.3

`paper16mayo.docx` agrega cuatro párrafos en §4.3 enumerando los tres marcos interpretativos de tercer orden:

- **MI1**: Calidad epistémica de la trayectoria.
- **MI2**: Apropiación reflexiva en sentido fuerte.
- **MI3**: Coherencia estructural multidimensional como horizonte evaluativo.
- Más un párrafo final distinguiendo MI (tercer orden, validación indirecta) de H1-H3 (segundo orden, contrastables).

`gaby.docx` menciona MI1-MI3 en la Fig. 2 pero **no los enuncia** en el cuerpo (agujero académico que el análisis cognitivo identificó).

### 2.2 CS02 — Distinción `cii_evolution_intra` vs `cii_evolution_longitudinal` en prosa

`paper16mayo.docx` reescribe el párrafo de §4.5 sobre la correspondencia 3 dimensiones → 5 métricas para distinguir explícitamente:
- **CII evolución intra-episodio**: pendiente intra-episodio de complejidad de prompts.
- **CII evolución longitudinal**: pendiente inter-episodio de la categoría de apropiación a través de tareas análogas.

`gaby.docx` tiene la formulación anterior donde "CII evolución" se mencionaba sin distinguir las dos escalas temporales, lo cual era epistemológicamente ambiguo.

### 2.3 CS03 — Distinción CCD-piloto-1 vs CCD-conceptual en Tabla 3

`paper16mayo.docx` agrega a la celda CCD de la Tabla 3:

> "La operacionalización de CCD vigente en piloto-1 (CCD-piloto-1) considera únicamente las anotaciones explícitas del estudiante como fuente de verbalización reflexiva, ya que la clasificación automática del tipo de prompt en categorías epistemológicas (Eje B post-defensa) no está implementada en el sistema instrumental actual y los prompts se emiten con etiqueta uniforme. La CCD conceptual completa (CCD-conceptual) incluiría también prompts reflexivos y se materializará post-implementación del clasificador semántico; la validación intercoder κ ≥ 0,70 del piloto-1 valida CCD-piloto-1, no CCD-conceptual."

`gaby.docx` no declara esta limitación de la operacionalización vigente — un reviewer competente podría detectar la discrepancia y cuestionar la integridad metodológica.

### 2.4 CS05 — Process assessment vs learning assessment en §9

`paper16mayo.docx` agrega en §9 dos párrafos anclados en Pellegrino, Chudowsky y Glaser (2001):

> "El presente trabajo presenta un sistema de medición del proceso cognitivo del estudiante en interacción con un asistente de IA, no un sistema de medición del aprendizaje en sentido cognitivo estricto..."

`gaby.docx` no tematiza explícitamente esta distinción fundacional de la medición educativa contemporánea.

### 2.5 CS06 — Cognición distribuida declarada vs operacionalizada en §3

`paper16mayo.docx` agrega un párrafo nuevo al final de §3 tematizando la asimetría:

> "Las tesis de cognición distribuida (Hutchins, 1995) y mente extendida (Clark y Chalmers, 1998) sostienen que el sistema cognitivo relevante es el sistema acoplado estudiante-tutor-IDE-tests-enunciado. La operacionalización empírica del modelo N4 mediante las cinco coherencias agregadas mide, sin embargo, al estudiante como nodo del sistema..."

`gaby.docx` cita los mismos autores como anclajes teóricos pero **no señala la brecha** entre marco teórico declarado y operacionalización efectiva.

### 2.6 CS07 — Glosa "perfil tipológico de apropiación X" en §4.4

`paper16mayo.docx` introduce el sustantivo "perfil" como marcador léxico anti-reificación:

> "...la caracterización de tres perfiles tipológicos de apropiación de la IA observables al nivel N4: perfil de delegación pasiva, perfil de apropiación superficial y perfil de apropiación reflexiva..."

`gaby.docx` usa "tres tipos de apropiación" sin el sustantivo "perfil", lo cual aumenta el riesgo de reificación (que el lector lea la categoría como identidad estable del estudiante en lugar de patrón observacional del episodio).

### 2.7 CS08 — Ratio prompt:exec declarado como decisión del implementador

`paper16mayo.docx` agrega a la celda CT de la Tabla 3:

> "El 'rango saludable' del ratio prompt/(prompts+ejec) cercano a 1:1 es decisión de diseño del implementador y no derivación de literatura cognitiva establecida; queda como operacionalización inicial sujeta a calibración empírica post-piloto-1 sobre las classifications históricas."

`gaby.docx` presenta el ratio sin esta declaración, lo cual podría leerse como derivación teórica cuando es operacionalización inicial.

---

## 3. Lo que `gaby.docx` tiene y `paper16mayo.docx` NO tiene

### 3.1 Apéndice A — Notas operativas del sistema instrumental

`gaby.docx` cierra con un apéndice operativo de cuatro sub-secciones que `paper16mayo.docx` no incluye:

#### A.1 Sharding del CTR a nivel del bus

Documenta `NUM_PARTITIONS = 8`, la función de hash `shard = int.from_bytes(sha256(episode_id).digest()[:4], "big") % 8`, single-writer por partición a nivel del bus Redis Streams, y el gotcha de Windows con `asyncio.add_signal_handler` no implementado en `ProactorEventLoop` (workers crasheaban al arrancar; fix aplicado).

#### A.2 Control de acceso por rol con políticas Casbin y RLS

Documenta las **170 políticas Casbin** organizadas como tuplas `(rol, recurso, acción)` con 4 roles (`superadmin`, `docente_admin`, `docente`, `estudiante`), bumpeos por ADR-016 (+14), ADR-039 (+8) y ADR-041 (+7), complementadas con Row-Level Security de Postgres (ADR-001) como defensa en profundidad.

#### A.3 Dualidad manifest-config en el versionado del prompt del tutor

Documenta el gotcha de reproducibilidad: el manifest declarativo `ai-native-prompts/manifest.yaml` declara la versión activa, mientras que el `tutor-service` en runtime usa una constante de configuración propia (`default_prompt_version`) que debe mantenerse sincronizada. La alineación es responsabilidad operacional cubierta por test de consistencia (`test_manifest_yaml_existe_y_se_parsea`).

#### A.4 Constantes auditables del sistema (Tabla A.1)

Tabla con 8 constantes versionadas:
- `LABELER_VERSION = 1.2.0` (previas: 1.0.0, 1.1.0)
- `GUARDRAILS_CORPUS_VERSION = 1.2.0` (previa: 1.1.0)
- `MIN_STUDENTS_FOR_QUARTILES = 5`
- `MIN_EPISODES_FOR_LONGITUDINAL = 3`
- `NUM_PARTITIONS = 8`
- `ANOTACION_N1_WINDOW_SECONDS = 120`
- `ANOTACION_N4_WINDOW_SECONDS = 60`
- `GENESIS_HASH = "0" * 64`

### 3.2 §7.2 — Reproducibilidad como propiedad del estado del sistema

`gaby.docx` agrega una sub-sección entera sobre reproducibilidad que `paper16mayo.docx` no tiene. Reformula la garantía de reproducibilidad como **propiedad del estado completo del sistema en un tiempo determinado**, no como propiedad del clasificador aislado. Detalla:

- Múltiples hashes versionados que extienden la garantía: `classifier_config_hash`, `guardrails_corpus_hash`, `chunks_used_hash` (con fórmula explícita), `LABELER_VERSION`.
- Historia evolutiva del `LABELER_VERSION` (v1.0.0 → v1.1.0 ADR-023 → v1.2.0 ADR-034).
- Declaración honesta de la **deuda operacional del piloto-1**: 106 clasificaciones con hash legacy (pre-`LABELER_VERSION 1.2.0`) — siguen siendo reproducibles bit-a-bit contra su propio hash original; el plan de re-clasificación masiva (A1 del plan operativo) requiere acceso a la base de datos real del piloto.

### 3.3 Título de §7 más explícito

- `gaby.docx`: **"Protocolo de validación intercodificador y reproducibilidad del estado del sistema"** (compuesto).
- `paper16mayo.docx`: **"Protocolo de validación intercodificador del Clasificador N4"** (singular, sin mencionar reproducibilidad como objeto del protocolo).

### 3.4 Procedencia del documento

`gaby.docx` cierra con sección explícita de procedencia que documenta:
- Integración de las 10 decisiones académicas resueltas en mayo de 2026.
- Origen en `ppconarev.md`, `papermod.md` y `ppcona.docx` original.
- Generación: 2026-05-10.

`paper16mayo.docx` reemplaza esta sección con "Notas para coautores" que cita las mismas 10 decisiones pero como **agenda pendiente operacional** ("Para preparar el paper para submisión: 1. Releer el documento completo... 2. Verificar Agradecimientos..."), lo cual sugiere que `paper16mayo.docx` está construido sobre una base anterior al cierre de `gaby.docx`.

---

## 4. Lo que ambos comparten (sin cambios sustantivos)

- Título: idéntico.
- Autores (Cortez & Garis), afiliaciones (UTN-FRM, UNSL), email.
- Resumen y palabras clave: prácticamente idénticos.
- §1 Introducción, §2 Antecedentes, §3 Marco teórico (cuerpo principal), §4 Modelo N4 (excepto las 7 ediciones), §5 Operacionalización, §6 Diseño cuasi-experimental, §8 Hallazgos preliminares, §9 Discusión (excepto CS05), §10 Conclusiones.
- Hipótesis H1, H2, H3 con κ ≥ 0,70 y protocolo dual.
- Bibliografía y agradecimientos (sustancialmente similares).

---

## 5. Lectura: ¿evolución o divergencia?

### 5.1 La narrativa simple ("paper16mayo es la evolución natural de gaby") es **incorrecta**

Si paper16mayo fuera estrictamente posterior, contendría a gaby. No lo contiene: pierde Apéndice A, §7.2 sobre reproducibilidad del estado del sistema, y la sección de Procedencia. La fecha del archivo de paper16mayo es posterior (23:30 vs 17:20 del mismo día), pero el contenido sugiere que se construyó sobre una base anterior al cierre de gaby.

### 5.2 La narrativa correcta: **dos ramas paralelas**

Hay dos ramas de evolución del paper original (`ppcona.docx`):

```
            ppcona.docx (Cortez & Garis original)
                       │
       ┌───────────────┴───────────────┐
       │                               │
       ▼                               ▼
  ppconarev.md → papermod.md     paper-draft.md
       │                               │
       │ + 10 decisiones académicas    │ + 10 decisiones académicas (heredadas)
       │ + Apéndice A operativo        │
       │ + §7.2 reproducibilidad       │
       │ + Procedencia                 │
       │                               │
       ▼                               ▼
  gaby.docx                       paper-draft.md actualizado
  (2026-05-10)                         │
                                       │ + 7 ediciones CS01-CS08
                                       │   (informeSocra1.md → plan1Socra.md)
                                       │
                                       ▼
                                  paper16mayo.docx
                                  (2026-05-16)
```

Cada rama agregó cosas distintas a partir del estado post-10-decisiones.

### 5.3 Implicancia académica

**Para submisión académica**: la versión óptima del paper sería el **merge de ambas ramas**:
- **Cuerpo** = paper16mayo (con las 7 ediciones cognitivas que mejoran la validez de constructo y la honestidad epistemológica).
- **§7** = versión de gaby con sub-secciones 7.1 (kappa, ya tematizada en paper16mayo), 7.2 (reproducibilidad del estado del sistema — sección que paper16mayo perdió y que es académicamente importante), 7.3 (equidad), 7.4 (equidad de paper16mayo, equivalente a 7.3 de gaby — verificar redundancia).
- **Apéndice A** = el de gaby tal cual (notas operativas auditables contra el repositorio).
- **Procedencia** = la de gaby, ampliada con la entrada del 2026-05-16 (consolidación de las 7 ediciones cognitivas).

### 5.4 Probable causa del fork

`paper-draft.md` (la base de `paper16mayo.docx`) no incorporó las adiciones operativas y de reproducibilidad que dieron lugar a `gaby.docx`. Cuando se aplicaron las 7 ediciones cognitivas hoy (CS01-CS08), se aplicaron sobre la base más antigua. No es error del análisis cognitivo; es que el análisis cognitivo trabajó sobre `paper-draft.md` y no sobre `gaby.docx`. Si el autor lo hubiera planteado al inicio, las 7 ediciones se hubieran aplicado sobre `gaby.docx` y el merge no haría falta.

---

## 6. Recomendaciones

### 6.1 Para el cierre académico del paper

1. **Decidir cuál rama es la base canónica** para submisión:
   - **Opción A — Base gaby + las 7 ediciones**: tomar gaby.docx como base y aplicarle CS01-CS08 manualmente. Esfuerzo estimado: 4-6 h (las 7 ediciones son pequeñas en líneas; lo lento es localizar cada ubicación y mantener coherencia).
   - **Opción B — Base paper16mayo + Apéndice A y §7.2 de gaby**: tomar paper16mayo.docx y agregarle el Apéndice A + §7.2 + sección de Procedencia. Esfuerzo estimado: 2-3 h (los bloques de gaby están bien delimitados y son inyectables).
   - **Opción C — Documentar la divergencia y decidir merge en sesión coautoral**: tratar las dos ramas como insumos para la sesión coautoral con Ana Garis post-consolidación. Más conservador, requiere participación de la coautora.
   
   Recomendación: **Opción B**. Es más eficiente operacionalmente, paper16mayo es más reciente, las inyecciones de gaby son aditivas (apéndice + sub-sección + procedencia) sin riesgo de conflicto con el cuerpo cognitivo.

2. **Verificar bibliografía**: paper16mayo agrega referencia a Pellegrino, Chudowsky y Glaser (2001) en el cuerpo de §9 (CS05). Verificar si ya está en la bibliografía existente; si no, agregarla. gaby ya cita a Pellegrino et al. en §3 (evidence-centered design), por lo que la referencia ya debería estar.

3. **Actualizar tesis16mayo.docx**: si se elige Opción B para el paper, propagar Apéndice A y §7.2 a la tesis si corresponden (la tesis tiene §16 Métricas del sistema y §21 Documento maestro de unificación que pueden absorber parte del contenido operativo).

### 6.2 Para evitar la divergencia en el futuro

- **Single source of truth**: que `paper-draft.md` sea la única base editable y que `gaby.docx`, `paper16mayo.docx` y futuros sean **artefactos generados** desde la misma fuente, no fuentes en paralelo.
- **Workflow git**: si `gaby.docx` agregó Apéndice A y §7.2 sin que esos cambios estuvieran en `paper-draft.md`, esa edición se hizo directo sobre el docx — práctica frágil. Mejor: editar siempre el `.md` fuente y regenerar el `.docx`.
- **Convención de nombres**: archivos generados deberían tener fecha + versión legible (`paper-2026-05-10.docx`, `paper-2026-05-16-cognitive.docx`) en lugar de nombres que no revelan el contenido (`gaby.docx`).

---

## 7. Conclusión

`paper16mayo.docx` aporta **siete contribuciones de validez de constructo y honestidad epistemológica** derivadas del análisis cognitivo externo: MI1-MI3 enunciados explícitamente, distinción intra/longitudinal de CII en prosa, declaración de CCD-piloto-1 vs CCD-conceptual, glosa "perfil tipológico" anti-reificación, declaración del ratio prompt:exec como decisión del implementador, tematización de cognición distribuida declarada vs operacionalizada, y posicionamiento process vs learning assessment.

`gaby.docx` aporta un **Apéndice A operativo completo, una sub-sección §7.2 sobre reproducibilidad como propiedad del estado del sistema, y una sección de Procedencia** que documenta el origen del trabajo.

Las dos contribuciones son **complementarias**, no sustitutas. La versión óptima del paper para submisión requiere mergear las dos ramas, preferentemente tomando `paper16mayo.docx` como base e inyectándole las adiciones operativas de `gaby.docx`. Esta tarea es operacional (2-3 h) y no requiere participación coautoral adicional para los bloques aditivos; sí podría aprovecharse la sesión coautoral post-consolidación para validar el merge y discutir si conviene complementar alguna referencia bibliográfica nueva.

---

## 8. Referencias cruzadas

- `docs/papers/gaby.docx` — rama PID consolidada 2026-05-10 con 10 decisiones académicas + Apéndice A operativo.
- `paper16mayo.docx` (wrapper raíz) — rama cognitiva consolidada 2026-05-16 con 7 ediciones CS01-CS08.
- `docs/papers/paper-draft.md` — fuente markdown de paper16mayo.
- `informeSocra1.md` (wrapper) — análisis cognitivo externo origen de las 7 ediciones.
- `plan1Socra.md` (wrapper) — plan que estructuró CS01-CS24.
- `revision-coautoral-paper-2026-05-16.md` (wrapper) — material para sesión coautoral con Ana Garis post-consolidación.
- `tesis16mayo.docx` (wrapper) — tesis extendida sincronizada con las 7 ediciones de paper16mayo.
- `ppcona.docx`, `ppconarev.md`, `papermod.md` — antecedentes del paper que `gaby.docx` cita en su Procedencia.
- `ADR-046` — formalización del umbral κ ≥ 0,70 con protocolo dual (ambos papers lo citan).
