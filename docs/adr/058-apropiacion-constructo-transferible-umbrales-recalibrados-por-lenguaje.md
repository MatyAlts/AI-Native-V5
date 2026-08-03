# ADR-058 — Apropiación como constructo transferible entre lenguajes, con umbrales de instrumento recalibrados por lenguaje

- **Estado**: Aceptado
- **Fecha**: 2026-07-23
- **Deciders**: Alberto Cortez, director de tesis (decisión de constructo). Neyén Bianchi (planteo e implementación de la maquinaria).
- **Tags**: constructo, apropiacion, multi-lenguaje, java, calibracion, cec, analytics, export, piloto-2
- **Resuelve**: el gate de decisión de la change `multi-language-research-integrity` (sección 1 de su `tasks.md`). Desbloquea las secciones 4 (segmentación en analytics) y 5 (export académico).

## Contexto y problema

El piloto AI-Native N4 mide **apropiación de la IA** (delegación pasiva ↔ apropiación reflexiva) sobre un corpus histórico **100% Python**: 169 ejercicios de banco y 31 TPs, todos Python (medido 2026-07-23). La epic `java-language-model` (cerrada) habilita que nazcan ejercicios y TPs en Java, que convivirán con Python en la misma materia y los mismos temas (POO, herencia, etc.).

Antes del primer episodio Java hay que responder una pregunta de constructo que ni el código ni el implementador pueden decidir: **¿"apropiación de la IA" es un constructo transferible entre lenguajes de programación?** El `design.md` de la change enumeró tres salidas legítimas, y dejó explícito que si la decisión no se toma antes de que existan datos Java, **se toma sola por omisión** (el sistema trataría todo como comparable sin haberlo validado).

Hay una tensión que cualquier lector crítico de la tesis va a señalar, y que este ADR debe resolver de frente: la plataforma ya construyó instrumentos **calibrados sobre Python** que se niegan a medir Java —el guard de CEC devuelve `no_aplicable` para código no-Python (sección 6 de la change), y `EXEC_SCALE`/`PAUSE_THRESHOLD` están sesgados por la latencia de compilación de Java (sección 7)—. Si a la vez se afirma que "la apropiación se mide igual en todos los lenguajes", aparece una contradicción aparente: *¿el constructo transfiere o no?*

## Decisión

Se adopta la **salida 3: misma variable, umbrales de instrumento recalibrados por lenguaje**.

La contradicción aparente se disuelve separando **dos niveles que no son lo mismo**:

1. **Constructo** — *apropiación cognitiva de la IA*. Es **el mismo** en todos los lenguajes. Un estudiante puede delegar pasivamente o apropiarse reflexivamente sin importar si escribe Python o Java; el fenómeno pedagógico que la tesis estudia no cambia de naturaleza con la sintaxis. La variable es **una sola**.

2. **Instrumento / umbrales** — las operacionalizaciones concretas (CEC vía AST de Python, `EXEC_SCALE`, `PAUSE_THRESHOLD`, `CORRELATION_WINDOW`) están **calibradas sobre Python** y **no transfieren sin recalibrar**. Sus constantes se derivaron de datos reales de prod que eran Python (ver `subgrupo.py:14-18`).

En consecuencia:

- **No son dos constructos** (queda descartada la salida 2 "dos variables validadas por separado"). No se bloquean los exports mixtos: Python y Java miden la **misma** variable de apropiación. Esto **cierra la tarea 1.3** de la change sin agregar el bloqueo de mezcla.
- **Los umbrales se recalibran por lenguaje** cuando existan datos Java suficientes. Hasta entonces, los instrumentos calibrados-para-Python se comportan honestamente frente a Java: CEC devuelve `no_aplicable` (no una puntuación-fantasma), y las métricas sensibles a latencia se declaran sesgadas (sección 7). Esa es la política de holding hasta la recalibración.
- **El lenguaje es dato de procedencia de primer orden**: se resuelve server-side al abrir el episodio (`episode-language-provenance`, ya implementado), viaja al payload `episodio_abierto`, se segmenta en analytics (sección 4) y se declara en el export (sección 5). Sin la etiqueta de lenguaje por episodio, la recalibración futura sería imposible de aplicar retroactivamente.

## Drivers de la decisión

- **D1 — Fidelidad epistemológica sobre conveniencia.** Afirmar "mismo constructo, mismos umbrales" (salida 1, covariable pura) sería más barato pero es empíricamente indefendible mientras los umbrales estén calibrados solo sobre Python: un CEC de un `for` anidado en Java no significa lo mismo que en Python. La recalibración reconoce que el instrumento —no el constructo— es dependiente del lenguaje.
- **D2 — Consistencia interna con las secciones 6 y 7.** Esta decisión es la que vuelve coherente el guard de CEC (`no_aplicable` para Java) y la documentación del sesgo. Un evaluador que cruce el ADR con el código no encuentra contradicción: constructo único, instrumento recalibrable.
- **D3 — No prejuzgar sin datos.** Recalibrar exige datos Java que hoy no existen. La decisión fija la política (*se recalibrará*) sin inventar constantes Java prematuras — mismo criterio de honestidad que ADR-023/CS08 (operacionalización declarada) y ADR-018 (constructo-piloto vs constructo-conceptual).
- **D4 — Comparabilidad preservada.** Al ser una sola variable, los análisis longitudinales y de cohorte pueden agregar Python y Java **una vez recalibrados los umbrales**, sin partir el constructo en dos mitades incomparables.
- **D5 — La procedencia habilita la retroactividad.** Etiquetar el lenguaje por episodio desde ahora (aunque hoy todo sea Python) permite aplicar la futura recalibración Java sobre los episodios correctos sin ambigüedad.

## Opciones consideradas

### Salida 1 — Misma variable con el lenguaje como covariable (descartada)

Un solo constructo; el lenguaje entra como covariable estadística para controlar su efecto, **sin** recalibrar umbrales.

**Por qué se descarta**: la covariable puede absorber un desplazamiento sistemático, pero no arregla que un umbral esté mal calibrado para Java (la relación umbral↔constructo puede ser no lineal y no monotónica entre lenguajes). Además deja sin justificar por qué CEC devuelve `no_aplicable` en vez de una puntuación ajustada por covariable. Es la opción más barata y la menos defendible mientras no haya calibración Java.

### Salida 2 — Dos variables validadas por separado (descartada)

`apropiación-Python` y `apropiación-Java` como constructos distintos, cada uno validado por su lado; exports mixtos bloqueados.

**Por qué se descarta**: contradice el núcleo pedagógico de la tesis. La apropiación cognitiva es el fenómeno de interés y no cambia de naturaleza con el lenguaje; tratarla como dos constructos fragmentaría el análisis longitudinal (un estudiante que pasa de Python a Java dejaría de ser comparable consigo mismo) e impediría el objetivo de convivencia Python/Java sobre los mismos temas. Es la decisión que agregaría la tarea 1.3 (bloqueo de mezcla) — que con esta elección **no aplica**.

### Salida 3 — Misma variable con umbrales recalibrados por lenguaje (elegida)

Ya descrita en la sección Decisión.

**Ventajas**:
- Constructo único → comparabilidad longitudinal y de cohorte preservada.
- Reconoce la dependencia-de-lenguaje donde realmente vive (el instrumento), no donde no está (el constructo).
- Internamente consistente con el guard de CEC y la doc de sesgo ya en curso.

**Desventajas**:
- La recalibración es trabajo futuro condicionado a la existencia de datos Java suficientes.
- Mientras tanto, las métricas estructurales/temporales de episodios Java quedan como `no_aplicable` o declaradas-sesgadas — hay una ventana donde Java se mide con menos instrumentos que Python.

## Criterios de éxito

1. Los exports mixtos (Python + Java) **no** se rechazan; el export declara los lenguajes presentes (sección 5 de la change).
2. Analytics segmenta por lenguaje y expone filtro opcional por lenguaje sin romper el comportamiento actual sin el parámetro (sección 4).
3. El guard de CEC (`no_aplicable` para no-Python) y la doc del sesgo (sección 7) referencian este ADR como la decisión de constructo que los fundamenta.
4. El lenguaje viaja como dato de procedencia por episodio desde la apertura (ya cumplido por `episode-language-provenance`).

## Criterios de revisita (para la recalibración)

- **Gate de datos**: existe un volumen de episodios Java suficiente para calibrar los umbrales de instrumento (CEC, `EXEC_SCALE`, `PAUSE_THRESHOLD`, `CORRELATION_WINDOW`) sobre datos Java reales.
- **Gate de calibración**: dirección + docentes UTN revisan y fijan los umbrales Java; se documenta en un ADR posterior y se amplía `SUPPORTED_LANGUAGES` de `cec_features.py` (hoy `frozenset({"python"})`) si CEC pasa a ser aplicable a Java.
- Al cumplirse ambos, la parte "los instrumentos Java quedan `no_aplicable`/sesgados" de este ADR queda superseded por el ADR de recalibración.

## Consecuencias

### Positivas
- Resuelve el gate de decisión sin prejuzgar con constantes Java inventadas.
- Deja la tesis internamente consistente entre el discurso de constructo y el comportamiento del código.
- Habilita las secciones 4 y 5 de la change.

### Negativas
- Ventana temporal donde Java se mide con menos instrumentos que Python (los calibrados-Python quedan `no_aplicable`/sesgados hasta recalibrar).
- Compromete trabajo futuro de recalibración condicionado a datos que aún no existen.

### Neutras
- No cambia el contrato del CTR, ni `classifier_config_hash`, ni `LABELER_VERSION`. El lenguaje es dato de procedencia inerte para el feature extraction del classifier (verificado en `episode-language-provenance`).
- La tarea 1.3 de la change (bloqueo de exports mixtos) **no aplica** bajo esta decisión.

## Referencias

- `openspec/changes/multi-language-research-integrity/` — proposal, design y tasks. Este ADR resuelve su sección 1.
- ADR-051 — Esqueleto de CEC bloqueado por A1. El instrumento cuyos umbrales son Python-calibrados; su guard de lenguaje (sección 6) se funda en esta decisión.
- ADR-023 / CS08 — precedente de honestidad metodológica ("operacionalización del implementador, no derivación de literatura").
- ADR-018 — distinción "CII-piloto-1" vs "CII-conceptual" como constructos que requieren validación separada. Patrón análogo de separar operacionalización de constructo.
- `apps/classifier-service/src/classifier_service/services/subgrupo.py:14-18` — calibración original de umbrales sobre datos de prod (Python).
- `packages/platform-ops/src/platform_ops/cec_features.py` — guard de lenguaje (`SUPPORTED_LANGUAGES`, `CECStatus`).
