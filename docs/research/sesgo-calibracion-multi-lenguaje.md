# Confound de calibración multi-lenguaje — limitación declarada

> **Para quien interpreta los datos del piloto** (dirección, jurado, analista): este
> documento enumera un sesgo *conocido y sistemático* que afecta a las métricas de
> apropiación cuando el episodio es de un lenguaje distinto de Python. No es un bug a
> corregir en el código: es una limitación de calibración que el análisis **debe
> controlar**. Se documenta acá —y no solo en comentarios de código— porque lo tiene
> que leer quien lee los números, no quien lee el `.py`.

- **Fecha**: 2026-07-23
- **Origen**: change `multi-language-research-integrity`, sección 7 (`tasks.md`).
- **Decisión de constructo que lo enmarca**: [ADR-058](../adr/058-apropiacion-constructo-transferible-umbrales-recalibrados-por-lenguaje.md) — apropiación es un constructo **transferible** entre lenguajes, pero los **umbrales de instrumento se recalibran por lenguaje**. Este documento es la cara "instrumento" de esa decisión.

## En una frase

Los umbrales del clasificador se calibraron sobre el comportamiento de estudiantes ejecutando **Python en Pyodide** (client-side, ejecución casi instantánea). Un episodio **Java** ejecuta con **compilación + corrida server-side**, que introduce latencia mecánica. Esa latencia no es señal cognitiva, pero cae dentro de umbrales que sí la tratan como tal — sesgando las métricas de forma **sistemática y unidireccional**.

## De dónde viene la calibración

Los umbrales se fijaron sobre **datos reales de prod, todos Python** (ver `apps/classifier-service/src/classifier_service/services/subgrupo.py:14-18`: *"Umbrales calibrados sobre datos reales de prod (2026-06-10)"*). El corpus histórico del piloto es homogéneo: 169 ejercicios y 31 TPs, 100% Python (medido 2026-07-23). Nunca hubo comportamiento no-Python contra el cual calibrar, por construcción.

## Métricas afectadas y dirección del sesgo

| Métrica | Constante | Dónde | Efecto en Java | Certeza |
|---|---|---|---|---|
| `dim_experimentacion` | `EXEC_SCALE = 8` | `subgrupo.py:28,135-137` | **A la baja** | Alta (fórmula) |
| `CCD_mean` | `CORRELATION_WINDOW = 2 min` | `ccd.py:83,188` | **A la baja** | Alta (fórmula) |
| Coherencia Temporal (CT) | `PAUSE_THRESHOLD = 5 min` | `ct.py:22,73,85` | Ventanas fragmentadas / conflación espera↔pausa | Media (mecanismo) |
| CEC (3 sub-coherencias) | AST de Python | `cec_features.py` | **No medible** → `no_aplicable` | N/A (ya resuelto, sección 6) |

### `dim_experimentacion` — a la baja (grounded en fórmula)

`dim_experimentacion(events) = min(1.0, (n_codigo_ejecutado + n_tests_ejecutados) / EXEC_SCALE)` con `EXEC_SCALE = 8` (`subgrupo.py:135-137`).

En Pyodide, ejecutar cuesta ~nada, así que un estudiante experimentador dispara muchos `codigo_ejecutado` en poco tiempo. En Java, cada corrida cuesta compilación + ejecución server-side: **menos ejecuciones por unidad de tiempo con idéntica actitud experimental**. Como el numerador cuenta ejecuciones y el divisor (8) se fijó sobre frecuencias Python, un estudiante Java igual de experimentador obtiene un `dim_experimentacion` **menor**. El sesgo es a la baja y unidireccional.

### `CCD_mean` — a la baja (grounded en fórmula)

`ccd_mean = max(0.0, 1.0 - avg_gap / CORRELATION_WINDOW.total_seconds())` con `CORRELATION_WINDOW = 2 min` (`ccd.py:188`).

La Coherencia Código-Discurso correlaciona anotaciones con respuestas del tutor dentro de una ventana de 2 min. Si entre la anotación y la respuesta se interpone una compilación Java, `avg_gap` crece. Como `ccd_mean` es **linealmente decreciente en `avg_gap`**, la latencia mecánica **baja el CCD_mean** aunque el acoplamiento código-discurso del estudiante sea idéntico. Sesgo a la baja.

### Coherencia Temporal (CT) — ventanas fragmentadas (mecanismo)

CT parte la secuencia de eventos en ventanas separadas por pausas mayores a `PAUSE_THRESHOLD = 5 min` (`ct.py:73,85`). En Python, una pausa de 5 min es señal cognitiva (el estudiante piensa). En Java, parte de esa espera puede ser **compilación/build mecánico**, no pausa cognitiva. El umbral **conflaciona pensar con esperar**: una sesión de trabajo Java continua puede fragmentarse en más ventanas por esperas de compilación. La dirección del efecto sobre el score final de CT depende de cómo agregue las ventanas, por eso se declara a nivel de *mecanismo* y no como dirección numérica cerrada — pero el confound es real y va en contra de la comparabilidad cruda Python↔Java.

### CEC — no medible, ya resuelto

CEC opera sobre el AST de Python. Java no es medible con estos umbrales: el guard de `compute_cec` devuelve `no_aplicable` sin puntuación (sección 6 de la change, fundado en ADR-058). No es "sesgo": es ausencia declarada de medición, que es lo correcto — mejor un hueco honesto que un score-fantasma.

## Qué hacer al interpretar los datos

1. **No comparar scores Java vs Python crudos.** El lenguaje es una covariable de confusión sobre el instrumento (no sobre el constructo — ver ADR-058). Controlá por lenguaje antes de comparar.
2. **Segmentar por lenguaje.** Analytics expone el lenguaje por episodio y filtro opcional (sección 4). Usalo: un promedio de cohorte mixta sin segmentar mezcla dos calibraciones.
3. **Esperar la recalibración para conclusiones fuertes sobre Java.** Los umbrales Java se recalibrarán sobre datos Java reales cuando existan (ADR-058, criterios de revisita). Hasta entonces, las métricas Java son **indicativas, no calibradas**.

## Estado

Se **documenta, no se corrige** (design de la change, driver D5). Corregir los umbrales exige datos Java que todavía no existen; documentar el confound cuesta nada y es lo que habilita que el análisis lo controle. La recalibración es trabajo futuro condicionado (ADR-058).

## Referencias

- [ADR-058](../adr/058-apropiacion-constructo-transferible-umbrales-recalibrados-por-lenguaje.md) — decisión de constructo (transferible) + umbrales recalibrables por lenguaje.
- `apps/classifier-service/src/classifier_service/services/subgrupo.py:14-18,28` — calibración original sobre Pyodide + `EXEC_SCALE`.
- `apps/classifier-service/src/classifier_service/services/ct.py:22` — `PAUSE_THRESHOLD`.
- `apps/classifier-service/src/classifier_service/services/ccd.py:83,188` — `CORRELATION_WINDOW` y fórmula de `ccd_mean`.
- `packages/platform-ops/src/platform_ops/cec_features.py` — guard de lenguaje de CEC (sección 6).
- `openspec/changes/multi-language-research-integrity/design.md` — driver D5.
