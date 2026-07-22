## Context

`java-language-model` dejó el lenguaje en la base y en los contratos. Esta change lo hace visible y elegible en las tres superficies: el formulario del docente, el selector del alumno y el editor.

Estado verificado del frontend:

- Los tipos del cliente HTTP no tienen `language` en ninguna app (`apps/web-student/src/lib/api.ts:584-618,919-941`; `apps/web-teacher/src/lib/api.ts:1904-1945`).
- `CodeEditor` declara `language?: "python"` — una unión de un solo miembro, con el comentario *"en F6+ extendible a más lenguajes"* (`CodeEditor.tsx:114`).
- El efecto que carga Pyodide sale temprano si el lenguaje no es Python (`CodeEditor.tsx:442`), pero el botón de ejecutar solo se deshabilita por `loading || running || testing` (`CodeEditor.tsx:973`), y `loading` ya es `false`.
- Monaco se importa dinámicamente completo, sin configuración de tree-shaking de lenguajes en ningún `vite.config.ts`.
- El sistema de diseño expone `Badge` con variantes de severidad, niveles N1–N4 y apropiación. No hay rampa por lenguaje.

Estado verificado de los prompts:

- `PromptLoader.load()` es genérico en el nombre de familia, sin whitelist. Verifica `sha256` del contenido contra el `manifest.yaml` de la versión **si existe**, y falla ruidosamente si no coincide.
- El tutor-service **no lee el manifest en runtime**: usa su propio config. Los dos deben alinearse a mano; hay un test que lo cubre.
- Solo `tutor/v1.0.1/` tiene `manifest.yaml`. v1.0.0, v1.1.0 y v1.2.0 no.

## Goals / Non-Goals

**Goals:**

- Que un docente pueda crear un ejercicio Java sin tocar la API a mano.
- Que el alumno sepa en qué lenguaje trabaja antes de abrir el editor y dentro de él.
- Que el editor coloree Java correctamente y que el rótulo accesible diga la verdad.
- Que la mezcla de lenguajes en una TP se bloquee en el cliente, no solo con un 422.
- Que el tutor socrático deje de ejemplificar exclusivamente en Python, con la gobernanza que faltó en el bump anterior.
- Que la ausencia de ejecución sea explícita y no un botón muerto.

**Non-Goals:**

- **No implementar ejecución de Java.** Eso es `java-execution-engine`.
- **No crear una familia de prompt separada para Java** (fundamentado en el proposal).
- **No unificar los dos runners de Pyodide** (el del alumno y el del docente). El del docente se adapta cuando exista ejecución server-side.
- **No inventar colores por lenguaje** en el sistema de diseño.

## Decisions

### D1 — Un badge neutro, sin color propio por lenguaje

`Badge` tiene hoy variantes con significado: severidad, niveles N1–N4, apropiación, adversarial. Cada color codifica algo pedagógico.

El lenguaje de programación no tiene una escala ni una carga semántica que justifique color. Un badge neutro con el nombre alcanza. Inventar `variant="python"` / `variant="java"` rompería la disciplina de "solo colores con significado" que el resto del sistema respeta.

**Alternativa descartada**: colores de marca (azul Python, naranja Java). Le da peso visual a algo que es metadata, y compite con los colores que sí significan algo.

### D2 — El editor bloquea la ejecución con explicación, no con silencio

Mientras no exista ejecución server-side, el botón de ejecutar para un lenguaje sin runtime queda **deshabilitado y explicado**, no habilitado e inerte.

Hoy el camino es silencioso: el efecto de Pyodide sale temprano, `loading` pasa a `false`, el botón queda clickeable y el guard de ejecución retorna sin hacer nada. El alumno hace click y no pasa absolutamente nada.

Esta change hace que existan ejercicios Java reales, así que ese camino deja de ser teórico. Un estado vacío que explica por qué es infinitamente mejor que un control que finge funcionar.

**Alternativa descartada**: ocultar el botón. Ocultar un control hace que el alumno crea que no existe la funcionalidad, en vez de entender que todavía no está disponible.

### D3 — El bloqueo de mezcla de lenguajes se hace en cliente **y** en servidor

El servidor ya rechaza la mezcla (`java-language-model`). El cliente la previene.

No es redundancia: el backend protege la integridad, el frontend protege el tiempo del docente. Componer una TP entera y descubrir la mezcla recién al agregar el último ejercicio es una experiencia mala y evitable — el modal ya tiene la biblioteca completa cargada, así que sabe los lenguajes antes de que el docente elija.

### D4 — El tercer tipo de caso de prueba obliga a revisar los ternarios

El preview y la tabla de resultados de test cases del docente usan `type === "stdin_stdout" ? "stdin/stdout" : "pytest"`. Con `junit_assert` en el modelo, ese ternario **rotula Java como "pytest"**.

Es un bug de una línea que no rompe nada funcionalmente y desinforma al docente en la superficie donde más precisión necesita. Se arregla acá, no en la change de datos, porque es UI.

### D5 — Bump a v1.3.0 con el rigor que faltó en el anterior

El bump replica el patrón disciplinado de v1.0.0→v1.0.1, no el de v1.1.0→v1.2.0:

| Elemento | v1.0.1 | v1.2.0 | v1.3.0 (esta change) |
|---|---|---|---|
| `manifest.yaml` propio | sí | **no** | sí |
| Hash declarado | sí | **no** | sí |
| Test de contenido | sí | **no** | sí |
| Manifest global + config en un commit | sí | sí | sí |

La ausencia de `manifest.yaml` en v1.2.0 es lo que permitió que se editara in-place dos días después de activarse, sin que `PromptLoader` tuviera nada contra qué comparar.

**Alternativa descartada**: bumpear sin manifest, "como se hizo la última vez". Repetir el gap conocido en la change que justamente lo documenta sería difícil de defender.

### D6 — Las variantes Java de los generadores son documentos nuevos, no parches

`ejercicio_generator` y `tp_generator` tienen tablas de progresión por dificultad con construcciones sintácticas Python literales, bajo reglas marcadas "ESTRICTO". Java necesita su propia progresión: tipos primitivos y entrada/salida en básica; métodos, arreglos y métodos de `String` en intermedia; clases, excepciones y colecciones en avanzada.

Eso no se resuelve generalizando ejemplos. Se escribe.

**Alternativa descartada**: un solo prompt con progresiones condicionales por lenguaje. Duplica la complejidad del prompt para el modelo y hace más difícil ajustar una progresión sin tocar la otra.

## Risks / Trade-offs

**El alumno abre un ejercicio Java y no puede ejecutarlo** → D2: el editor lo dice explícitamente. El tutor sí funciona, así que el episodio tiene valor pedagógico real aunque la ejecución falte.

**El docente crea un ejercicio Java con casos de prueba que nunca puede verificar** → El panel de prueba del docente corre sobre su propio runner Pyodide, separado del editor del alumno. Con Java queda sin forma de verificar autoría. Se mitiga con el mismo mensaje explícito de D2, pero **la limitación es real y se resuelve recién en `java-execution-engine`**. Vale advertirlo en la UI de creación, no solo en la de prueba.

**Un episodio abierto en Python si el ejercicio cambia a Java** → No hay ningún guard hoy: el editor cambiaría de modo debajo del alumno a mitad de sesión, con un snapshot de código en el lenguaje anterior. El sistema ya resuelve algo análogo para el enunciado marcando deriva en la instancia; el lenguaje no tiene equivalente. Mitigación mínima: no permitir cambiar el lenguaje de un ejercicio con episodios abiertos.

**El bump del prompt parte el corpus** → El identificador de versión del prompt viaja en la metadata base de **todos** los eventos de la cadena. Los episodios pre y post v1.3.0 son distinguibles, que es lo correcto y lo que ya pasó en cada bump anterior. Con `manifest.yaml` y hash, la trazabilidad queda mejor que la de v1.2.0, no peor.

**Coautoría** → El diff son dos líneas. Consultar con Garis antes de mergear, no después.

## Migration Plan

1. Tipos del frontend y badges (solo lectura del campo nuevo, sin escritura).
2. Selector del docente y bloqueo de composición.
3. Hardcodes y Monaco, junto con el estado explícito de ejecución no disponible.
4. Prompt v1.3.0, con consulta previa a Garis. Manifest global y config en el mismo commit.
5. Variantes Java de los generadores.

Cada paso es independiente y desplegable por separado. Los pasos 1–3 son solo frontend, que se despliega como un único servicio.

**Rollback**: revertir el config del prompt a v1.2.0 restaura el comportamiento anterior sin tocar datos. Los cambios de frontend son reversibles con un redeploy.

## Open Questions

**¿Se advierte en la UI de creación que un ejercicio Java no podrá probarse todavía?** El docente puede crear casos de prueba que no tiene cómo verificar. Recomendación: sí, advertir en el momento de crear, no recién al intentar probar.

**¿Qué pasa si un docente cambia el lenguaje de un ejercicio que ya tiene episodios abiertos?** Recomendación de mitigación mínima en Risks. Si se quiere algo más fino —marcar deriva como se hace con el enunciado— es diseño aparte.
