## Why

Esta change existe para que el soporte de Java **no arruine el corpus de la tesis doctoral**. No entrega valor funcional al docente ni al alumno. Entrega validez metodológica.

Tres hallazgos de la exploración, todos verificados contra código:

**1. No hay forma de segmentar el dataset por lenguaje.** El campo `language` vive únicamente en `EdicionCodigoPayload` (`packages/contracts/src/platform_contracts/ctr/events.py:289`) — un evento que se repite N veces por episodio. `EpisodioAbiertoPayload` no lo tiene. Y **ningún endpoint de analytics filtra ni etiqueta por lenguaje**: ni `kappa`, ni `progression`, ni `cii-evolution-longitudinal`, ni `cohort-adversarial`, ni `alerts`, ni el export académico (`packages/platform-ops/src/platform_ops/academic_export.py`). Si entran episodios Java sin esto, el corpus se mezcla **sin un error, sin un warning**. Se descubre meses después, analizando datos, cuando ya no hay vuelta atrás.

**2. Existe un indicador Python-específico esperando para contaminar todo.** `packages/platform-ops/src/platform_ops/cec_features.py` (CEC, Coherencia Estructural del Código, ADR-051) usa `import ast` y `ast.parse(code)`. Hoy está desconectado del pipeline, bloqueado tras 4 gates. Pero **esos gates son independientes del roadmap de Java** y pueden destrabarse en paralelo. Si CEC se conecta con episodios Java presentes, `ast.parse` falla en el 100% de los snapshots, y el fail-soft **no devuelve "sin datos"** — devuelve los defaults (`naming_consistency=1.0`, `depth_variance=0.0`, `component_granularity=0.5` → `cec_summary ≈ 0.83`). Un score alto, sistemático y falso, **indistinguible de "código Python perfecto"**. El fail-soft se diseñó para errores transitorios de tipeo, no para "el corpus entero es de otro lenguaje".

**3. Los umbrales del clasificador están calibrados sobre Pyodide.** Está escrito en el código: *"Umbrales calibrados sobre datos reales de prod (2026-06-10)"* (`apps/classifier-service/src/classifier_service/services/subgrupo.py:14-18`). Esos datos son de alumnos con ejecución instantánea client-side. Java con ejecución server-side introduce latencia estructural —red, `javac`, arranque de JVM— que reduce la frecuencia de `codigo_ejecutado` por unidad de tiempo de forma **sistemática y unidireccional**. Eso deflaciona `dim_experimentacion` (`EXEC_SCALE=8`) y corre la clasificación hacia `escribe_sin_validar` o `apropiacion_superficial` **por fricción de infraestructura, no por menor apropiación real**. No es ruido aleatorio: es un confound.

## What Changes

- **`language` a nivel de episodio, no solo de evento de edición.** Agregar el lenguaje al payload de apertura del episodio, resuelto server-side desde el `Ejercicio`/`TareaPractica` (nunca desde el cliente). Sin esto, segmentar exige inspeccionar eventos repetidos o hacer join cross-base.
- **Segmentación por lenguaje en los 6 endpoints de analytics y en el export académico**: parámetro opcional de filtro y el lenguaje presente en la respuesta. Sin el parámetro, el comportamiento actual se preserva — pero la respuesta SIEMPRE declara qué lenguajes contiene, para que una lectura mixta sea visible en vez de silenciosa.
- **Guard de lenguaje en CEC**: `cec_features.py` rechaza explícitamente los snapshots cuyo lenguaje no es Python, devolviendo "no aplica" en vez de valores por defecto. La diferencia entre "no medible" y "medido como perfecto" es la diferencia entre un dato faltante y un dato falso.
- **Distinción entre "sin datos" y "valor neutro"** en el contrato de features del clasificador, para que el guard de arriba tenga dónde apoyarse.
- **Documentar el confound de calibración** como limitación declarada, siguiendo el patrón de honestidad que el repo ya usa en ADR-023/CS08 (*"esto es operacionalización del implementador, no derivación de literatura"*).

## Capabilities

### New Capabilities

- `episode-language-provenance`: el lenguaje del episodio queda registrado en la cadena CTR en el momento de apertura, resuelto server-side desde el ejercicio. Es el ancla que permite segmentar el corpus sin inferencias ni joins frágiles.
- `analytics-language-segmentation`: los endpoints de analytics y el export académico aceptan filtro por lenguaje y declaran siempre qué lenguajes contiene el resultado. Una cohorte mixta nunca se reporta como homogénea.
- `cec-language-guard`: el módulo de Coherencia Estructural del Código rechaza explícitamente lo que no puede parsear, en vez de devolver valores por defecto que se leen como excelencia.

### Modified Capabilities

Ninguna de las 13 de `openspec/specs/` cubre analytics ni el pipeline de features.

## Impact

- **packages/contracts**: campo de lenguaje en el payload de apertura de episodio. Es un campo **nuevo con default** — verificado que agregar campos opcionales a un payload CTR no afecta `classifier_config_hash` ni obliga a bumpear `LABELER_VERSION`, porque el labeler y el feature extractor solo consultan un conjunto acotado de campos por `event_type` (documentado en `CLAUDE.md`, sección de propiedades críticas). Los eventos históricos conservan su `self_hash` original.
- **tutor-service**: al abrir el episodio, resolver el lenguaje desde el ejercicio y emitirlo. Ya consulta `AcademicClient` para validar las 6 condiciones de apertura, así que el dato está a mano.
- **analytics-service**: 6 endpoints ganan filtro y declaración de lenguaje.
- **packages/platform-ops**: `academic_export.py` incluye el lenguaje por episodio; `cec_features.py` gana el guard.
- **classifier-service**: **cero cambios en el pipeline activo**. El guard de CEC vive en `platform-ops` y CEC sigue desconectado. Esta change no lo conecta ni acelera sus gates — lo deja seguro para cuando alguien los destrabe.

## Decisión que requiere firma de Cortez

**¿"Apropiación de la IA" es un constructo transferible entre lenguajes de programación?**

Ni los documentos de diseño ni ningún ADR lo declaran. El repo ya sentó el precedente de tratar esto explícitamente: ADR-018 distingue "CII-piloto-1" de "CII-conceptual" como cosas distintas que requieren validación distinta.

Las tres salidas posibles, todas legítimas:

1. **Misma variable, dos poblaciones** → reportar el lenguaje como covariable/moderador en todo análisis.
2. **Dos variables** → validar y reportar por separado; no promediar entre lenguajes.
3. **Misma variable, umbrales recalibrados** → recalibrar `subgrupo.py`/`tree.py`/`ct.py` sobre datos Java, con el bump de versión y la re-clasificación que eso implica.

**Esta change implementa la maquinaria de segmentación que las tres opciones necesitan.** No prejuzga cuál se elige. Pero la decisión tiene que tomarse **antes de que exista el primer episodio Java** — después ya hay datos generados y la decisión se tomó sola, por omisión.
