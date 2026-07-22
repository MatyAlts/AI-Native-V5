## Context

La plataforma es la materialización de la tesis doctoral de Alberto Cortez. La cadena CTR append-only y la reproducibilidad bit-a-bit del clasificador son las propiedades que sostienen el claim académico — si se rompen, se cae el argumento.

El piloto corre en vivo con ~87 alumnos generando eventos reales, todos en Python. El soporte de Java introduce, por primera vez, **heterogeneidad en el corpus**. Esta change construye la maquinaria para que esa heterogeneidad sea visible y controlable en el análisis, en vez de invisible.

Estado actual verificado:

- `language` existe solo en `EdicionCodigoPayload` (`packages/contracts/src/platform_contracts/ctr/events.py:289`), un evento repetido N veces por episodio. `EpisodioAbiertoPayload` (líneas 46-81) no lo tiene.
- Ningún endpoint de analytics filtra ni etiqueta por lenguaje. Verificado por grep sobre `apps/analytics-service/src/` y `packages/platform-ops/src/platform_ops/academic_export.py`: cero referencias a `language`.
- `packages/platform-ops/src/platform_ops/cec_features.py` usa `ast.parse` (líneas 27, 74). Está desconectado del pipeline (cero imports desde `classifier-service`), bloqueado tras los 4 gates de ADR-051.
- Los umbrales de `subgrupo.py:14-18` declaran en comentario estar calibrados sobre datos de prod del 2026-06-10 — es decir, sobre comportamiento con Pyodide.

El equipo ya tiene un precedente de honestidad metodológica que este diseño imita: ADR-023/CS08 declara explícitamente *"esto es operacionalización del implementador, no derivación de literatura"*, y ADR-018 distingue "CII-piloto-1" de "CII-conceptual" como constructos que requieren validación separada.

## Goals / Non-Goals

**Goals:**

- Que cualquier análisis del corpus pueda separar Python de Java sin inferencias ni joins frágiles.
- Que una cohorte mixta **nunca** se reporte como homogénea por omisión.
- Que CEC, si algún día se conecta, no produzca valores falsos sobre código que no puede parsear.
- Que el confound de calibración quede documentado como limitación declarada, no descubierto por un jurado.

**Non-Goals:**

- **No recalibrar los umbrales del clasificador para Java.** Eso requiere datos Java que todavía no existen, y una decisión de Cortez sobre el constructo.
- **No conectar CEC al pipeline ni acelerar los gates de ADR-051.** Esta change lo deja seguro para cuando alguien los destrabe; no los destraba.
- **No modificar el pipeline activo del clasificador.** Cero cambios en `pipeline.py`, `ct.py`, `ccd.py`, `cii.py`, `tree.py`, `subgrupo.py`.
- **No decidir si apropiación es un constructo transferible.** Eso es de Cortez. Esta change implementa la maquinaria que las tres respuestas posibles necesitan por igual.

## Decisions

### D1 — El lenguaje del episodio se resuelve server-side, nunca se acepta del cliente

El lenguaje se deriva del `Ejercicio`/`TareaPractica` en el momento de abrir el episodio, dentro de `tutor-service`, que ya consulta `AcademicClient` para validar las 6 condiciones de apertura.

**Alternativa descartada**: aceptarlo del frontend, como se hace hoy con `edicion_codigo`. Un dato de procedencia que el cliente puede alterar no sirve como evidencia en una tesis sobre trazabilidad. Y el precedente está: hoy el frontend manda `"python"` hardcodeado, que es exactamente el tipo de dato que parece real y no lo es.

### D2 — El lenguaje va en el payload de apertura, no en un evento nuevo

Agregar un campo al payload de `episodio_abierto` en vez de crear un tipo de evento `lenguaje_declarado`.

Fundamento verificado: agregar campos con default a un payload CTR **no afecta** `classifier_config_hash` ni obliga a bumpear `LABELER_VERSION`, porque el labeler y el feature extractor solo consultan un conjunto acotado y conocido de campos por `event_type` (documentado en `CLAUDE.md`, sección "Propiedades críticas"). Los eventos históricos conservan su `self_hash` original, calculado contra el modelo previo.

**Alternativa descartada**: un evento nuevo entraría al feature extraction y obligaría a sumarlo a `_EXCLUDED_FROM_FEATURES` (`pipeline.py:63-69`) **con ADR de respaldo**, porque cada exclusión requiere justificación documentada. Costo mayor, beneficio nulo.

### D3 — La respuesta de analytics siempre declara los lenguajes que contiene

El filtro es opcional (preserva el comportamiento actual), pero la **declaración no lo es**: toda respuesta incluye qué lenguajes componen el resultado.

Un filtro opcional sin declaración obligatoria resuelve el caso del investigador que sabe que tiene que filtrar, y no hace nada por el que no sabe. El segundo es el caso peligroso. Si la respuesta dice `languages: ["python", "java"]`, la mezcla es imposible de no ver.

**Alternativa descartada**: filtro obligatorio. Rompe todos los callers existentes y los frontends, para resolver un problema que la declaración resuelve sin romper nada.

### D4 — CEC distingue "no medible" de "medido como neutro"

El guard devuelve una señal explícita de no-aplicabilidad, no los valores por defecto.

Hoy el fail-soft de `cec_features.py` devuelve `naming_consistency=1.0`, `depth_variance=0.0` → `component_depth=1.0`, `component_granularity=0.5`, que agregan a `cec_summary ≈ 0.83`. Eso no es "sin datos": es **un score alto**, indistinguible de código Python excelente. Un episodio Java entero quedaría marcado con coherencia estructural casi impecable por no poder parsearse.

El fail-soft se diseñó para errores transitorios de tipeo del alumno, donde caer a neutro es razonable. "El corpus entero es de otro lenguaje" no es ese caso.

**Alternativa descartada**: escribir un parser AST de Java. Es un proyecto propio, y CEC ni siquiera está conectado. El guard cuesta órdenes de magnitud menos y elimina el riesgo completo.

### D5 — El confound de calibración se documenta, no se corrige

Los umbrales quedan como están. Se documenta que fueron calibrados sobre comportamiento con Pyodide y que la latencia de ejecución server-side los sesga de forma sistemática y unidireccional para Java.

Corregirlos exige datos Java que no existen todavía. Documentarlo cuesta nada y es lo que permite que el análisis controle por eso.

## Risks / Trade-offs

**El lenguaje del ejercicio cambia después de abierto el episodio** → El valor del payload es un snapshot del momento de apertura, no una referencia viva. Es lo correcto para trazabilidad: la cadena CTR registra qué pasó, no qué pasa ahora. Documentarlo explícitamente para que nadie lo lea como referencia.

**Los episodios anteriores a esta change no declaran lenguaje** → Todos son Python (el sistema no soportaba otra cosa). La ausencia del campo es interpretable sin ambigüedad como `python`. Documentarlo en el spec, no inferirlo en el código.

**El filtro se agrega y nadie lo usa** → La declaración obligatoria de D3 lo mitiga: aunque el análisis no filtre, la mezcla es visible en cada respuesta.

**Alguien destraba los gates de ADR-051 sin leer esta change** → El guard vive en el propio `cec_features.py`, no en un caller. Se activa solo, sin depender de que quien conecte CEC se acuerde.

**Sobrecarga de una consulta extra al abrir episodio** → `tutor-service` ya consulta `AcademicClient` en ese camino para validar las 6 condiciones. El lenguaje viene en la misma respuesta; no hay round-trip nuevo.

## Migration Plan

1. Campo nuevo con default en el contrato → retrocompatible por construcción; los eventos viejos deserializan sin cambios.
2. Emisión del lenguaje en `tutor-service`.
3. Filtro + declaración en analytics y export. Aditivo: los callers existentes no se tocan.
4. Guard de CEC. Aislado, sin efecto en el pipeline activo.

Sin migración de datos. Sin re-clasificación. Sin bump de `LABELER_VERSION`.

**Rollback**: cada paso es independiente y aditivo. Revertir el guard de CEC o el filtro de analytics no deja datos inconsistentes.

## Open Questions

**Para Cortez, antes del primer episodio Java** — ¿"apropiación de la IA" es un constructo transferible entre lenguajes de programación? Las tres salidas son legítimas: misma variable con el lenguaje como covariable; dos variables validadas por separado; o misma variable con umbrales recalibrados sobre datos Java. Esta change implementa la maquinaria que las tres necesitan, y no prejuzga cuál se elige. Pero si la decisión no se toma antes de que existan datos Java, se toma sola por omisión.

**Para el equipo** — ¿el export académico debe poder exportar cohortes mixtas, o rechazarlas? Depende de la respuesta anterior. Si la tesis trata los lenguajes como poblaciones separadas, un export mixto es un error metodológico que conviene bloquear, no solo declarar.
