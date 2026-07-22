## Why

Después de `java-language-model`, el lenguaje existe en la base y viaja por la API — pero **ninguna interfaz lo lee**. Un docente no puede crear un ejercicio Java desde la UI, y un alumno no sabe en qué lenguaje está el que le tocó.

Esta change hace el lenguaje visible y elegible. No agrega ejecución: el alumno escribe Java y el tutor socrático lo guía, sin correr el código. Eso ya es un curso de POO conceptual funcionando —clases, herencia, polimorfismo, diseño— que es la mayor parte de un curso inicial.

Tres hallazgos de la exploración que redefinen el alcance:

**1. El lenguaje no llega al editor por ningún camino.** La cadena `Ejercicio.language → API → TareaSelector → EpisodePage → CodeEditor → evento CTR` está cortada en el primer eslabón: los tipos del frontend (`apps/web-student/src/lib/api.ts:584-618,919-941`) no tienen el campo. Hay que enhebrarlo entero.

**2. Los hardcodes de `"python"` son cuatro, no tres.** A los conocidos —`CodeEditor.tsx:114` (union de un solo miembro), `EpisodePage.tsx:799` (payload del evento CTR), `EpisodePage.tsx:755` (`badge="Python"`)— se suma uno que ningún documento de diseño listaba: el `aria-label` del botón de ejecución dice literalmente `"Ejecutar codigo Python"` (`CodeEditor.tsx:975`). Un alumno con lector de pantalla escucharía el lenguaje equivocado.

**3. El prompt del tutor ya es agnóstico; el problema es de gobernanza, no de contenido.** Leídas las 291 líneas de `ai-native-prompts/prompts/tutor/v1.2.0/system.md`, los 4 movimientos socráticos y los 9 principios no dependen del lenguaje. Solo hay dos menciones a Python, ambas ilustrativas (líneas 47 y 133) — y una de ellas, *"los strings en Python son inmutables"*, **también es cierta en Java**: está mal etiquetada, no mal razonada.

Pero el archivo se autodeclara *"DRAFT, no activo en manifest"* en sus primeras 8 líneas mientras corre en producción con ~87 alumnos desde el 2026-05-20, y fue **editado in-place dos días después de activarse** (commit `0d69d17`) sin bump de versión ni hash-lock. Como v1.2.0 nunca tuvo `manifest.yaml`, el `PromptLoader` no tenía nada contra qué comparar y la mutación pasó sin fallar. Hoy la etiqueta "v1.2.0" **no identifica un texto único**.

## What Changes

- **Selector de lenguaje al crear y editar ejercicios**, en el formulario del docente. El grid de datos básicos ya agrupa unidad temática y dificultad — es su lugar natural.
- **Aviso de lenguaje al componer una TP**: el modal de composición trae la biblioteca completa y permite multiselección sin ninguna noción de lenguaje. Se agrega el bloqueo en cliente, para que el docente no descubra la mezcla recién con un 422 del backend.
- **Badge de lenguaje** en el selector de tareas del alumno y en la cabecera del editor, reemplazando el `"Python"` fijo.
- **Los cuatro hardcodes**, incluido el `aria-label`.
- **Monaco en el lenguaje correcto**: cambio de una palabra. El paquete ya se importa completo sin tree-shaking de lenguajes, así que el tokenizer de Java **ya viaja en el bundle actual** — el riesgo de peso que cabría suponer no existe acá.
- **Prompt del tutor v1.3.0**: generaliza las dos menciones a Python, con el rigor de gobernanza que le faltó al bump anterior — `manifest.yaml` propio con hash declarado, actualización del manifest global y del config efectivo en el mismo commit, y test golden de contenido.
- **Fence de lenguaje en el contexto del tutor**: `tutor_core.py:1931` hardcodea ` ```python ` al inyectar el código inicial del ejercicio. Es el único fence hardcodeado del builder — el código que el alumno escribe en vivo ya usa un fence genérico sin etiqueta.
- **Variantes Java de los dos generadores por IA**. Ambos, no uno: `tp_generator` está tan atado a Python como `ejercicio_generator`, o más — su tabla de construcciones por dificultad es sintaxis Python literal (`def`, `try/except`, comprehensions, `import math`) bajo una regla marcada "ESTRICTO".

## Capabilities

### New Capabilities

- `language-authoring-ui`: el docente elige el lenguaje al crear un ejercicio y ve bloqueada la mezcla al componer una TP; el alumno ve en qué lenguaje está trabajando antes de abrir el editor y dentro de él. Incluye el editor en el modo de sintaxis correcto y el rótulo accesible correspondiente.
- `multi-language-prompts`: el prompt del tutor deja de ejemplificar en un único lenguaje, y los generadores por IA producen ejercicios y TPs con progresiones de dificultad propias de cada lenguaje. Incluye la gobernanza del bump: versión nueva con hash declarado y verificación de contenido.

### Modified Capabilities

Ninguna de las 13 de `openspec/specs/` cubre la UI de autoría ni los prompts.

## Impact

- **web-teacher**: selector en el formulario de ejercicios (`views/EjerciciosView.tsx:684`); bloqueo en el modal de composición (`views/TareasPracticasView.tsx`); columna o badge de lenguaje en el listado. Hay un detalle de UI que se rompe en silencio si se pasa por alto: el preview y la tabla de resultados de test cases usan un ternario `type === "stdin_stdout" ? "stdin/stdout" : "pytest"` — con un tercer tipo, `junit_assert` **se rotularía como "pytest"**.
- **web-student**: badge en `components/TareaSelector.tsx` y en la cabecera del editor (`pages/EpisodePage.tsx:755`); tipos del cliente HTTP con el campo nuevo; los cuatro hardcodes; Monaco con el lenguaje del ejercicio.
- **packages/ui**: `Badge` ya existe con variantes de severidad y de niveles N1–N4. No hay rampa de color por lenguaje de programación, y **no conviene inventarla**: el sistema mantiene la disciplina de que el color signifique algo. Un badge neutro alcanza.
- **ai-native-prompts**: `tutor/v1.3.0/` con `system.md` y `manifest.yaml`; variantes Java de `ejercicio_generator` y `tp_generator`.
- **tutor-service**: `config.py` apunta a v1.3.0; fence de lenguaje en `tutor_core.py:1931`.
- **governance-service**: **cero cambios**. `PromptLoader` es genérico en el nombre de familia y no tiene whitelist — verificado.
- **Ejecución**: fuera de scope. El botón de ejecutar sigue sin funcionar para Java, y esta change **debe dejarlo fallando de forma visible** en vez de silenciosa (ver abajo).

## Riesgo de orden (restricción no negociable)

**`multi-language-research-integrity` tiene que estar mergeada antes de que esta change shippee.**

Esta es la change que hace un ejercicio Java alcanzable por un alumno. Desde el primer episodio Java entran eventos al CTR, y si la segmentación por lenguaje no existe todavía, el corpus de la tesis se mezcla sin ningún error visible.

## El fallo silencioso empeora antes de mejorar

Hoy, con lenguaje distinto de Python, el botón "Ejecutar" **no se deshabilita**: el efecto que carga Pyodide sale temprano y deja `loading` en `false`, así que el botón queda habilitado y clickeable. Al clickear, el guard de `runCode` retorna sin hacer nada. Sin mensaje, sin error, sin spinner. Verificado, no inferido.

Esta change hace que existan ejercicios Java reales, así que ese camino pasa de teórico a cotidiano. **Mientras `java-execution-engine` no exista, el editor tiene que decir explícitamente que la ejecución todavía no está disponible para este lenguaje.** Un botón que no hace nada es peor que un botón deshabilitado con explicación.

## Decisión de gobernanza que requiere consulta

**El prompt del tutor es coautoría con Ana Garis**, y la regla del proyecto es que no se toca sin consultar. El diff real son dos líneas de generalización de ejemplos — trivial de revisar.

Se evaluó la alternativa de crear una familia `tutor-java` separada, que el governance-service ya soporta sin cambios de código. **Se descarta**: duplicaría 291 líneas de doctrina pedagógica, obligaría a revisar un segundo documento completo con Garis, agregaría lógica de selección de prompt por lenguaje, y crearía dos copias que van a divergir — que es exactamente lo que ya pasó con la mutación no versionada de mayo. El método socrático no depende del lenguaje que el alumno esté aprendiendo.
