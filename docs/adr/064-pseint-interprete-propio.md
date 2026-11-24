# ADR-064 — PSeInt como un lenguaje más: intérprete propio en TypeScript

- **Estado**: Propuesto (HU-030; se acepta con la demo de la historia)
- **Fecha**: 2026-11
- **Deciders**: Juani Sarmiento (alcance y criterios de aceptación del 24/11/2026)
- **Tags**: ejecución, lenguajes, web-student, web-teacher, execution-service, reproducibilidad
- **Relacionado**: [ADR-033](033-sandbox-pyodide-only-piloto-1.md) (Python en el navegador con Pyodide), [ADR-060](060-ejecucion-java-docker-directo-sin-judge0.md) (sandbox Docker sin privilegios y runner). HU-015 (Python en el servidor solo para la corrección con IA), cuyo patrón esta historia repite.

## Contexto y problema

Programación 1 enseña algoritmos con PSeInt antes de pasar a Python. La plataforma solo sabía Python y Java, así que los ejercicios de pseudocódigo quedaban afuera del tutor, del CTR y de la corrección con IA. Hacía falta que PSeInt fuera un lenguaje más: el alumno escribe, ejecuta y prueba; el docente prueba sus ejercicios; la corrección con IA tiene el resultado real de cada caso; y el CTR registra qué motor corrió.

PSeInt no tiene una especificación formal: el lenguaje es lo que hace el programa oficial, y cambia con su **perfil** (arreglos desde 0 o 1, si `=` asigna, si hay que definir variables, etc.).

## Drivers de la decisión

- El `Leer` tiene que ser **interactivo** en el navegador: se pide un dato por vez, con lo escrito antes ya en la consola, igual que el `input()` de Python.
- Lo que el alumno ve en el navegador y lo que corrige el servidor tiene que ser **la misma ejecución**: si no, la IA lee "falló" sobre código que al alumno le anduvo.
- Un ciclo infinito no puede congelar el navegador ni ocupar el sandbox.
- Errores en castellano, pensados para un alumno que recién empieza, con la línea.
- El sandbox del servidor no puede perder ninguno de los controles del ADR-060.
- La historia no puede romper Python ni Java, ni hacer obligatoria una imagen nueva para que el runner arranque.

## Decisión

1. **Intérprete propio en TypeScript** (`packages/pseint`): lexer, parser e intérprete sin DOM ni dependencias de runtime. El intérprete está escrito con generadores: cada `Leer` le pide el dato a quien lo ejecuta y espera (`await`), lo que sirve tanto para el diálogo del navegador como para la entrada por adelantado de los casos de prueba. Cada tanto cede el control al event loop. Corta por límite de pasos (`MAX_PASOS_POR_DEFECTO`, hoy 2.000.000) con estado `limite_excedido`. Los errores de sintaxis se detectan **antes de ejecutar**: un programa con un error no ejecuta nada.
2. **El alumno ejecuta y prueba en el navegador**, como con Pyodide. El docente también prueba en el navegador. El servidor ejecuta PSeInt **solo para la corrección con IA** (sin `episode_id`), con el mismo criterio que Python en HU-015: dentro de un episodio no ejecuta ni emite `tests_ejecutados`. `executor.LENGUAJES_DE_NAVEGADOR = {"python", "pseint"}` es la lista que decide eso.
3. **El servidor corre el mismo intérprete**: la imagen `infrastructure/pseint-sandbox.Dockerfile` empaqueta `packages/pseint/src/cli.ts` en `/opt/pseint/run.js` y el runner la lanza con las mismas banderas que Java y Python (`--network=none`, `--read-only`, `--cap-drop=ALL`, usuario no root). Salida 101 = error de sintaxis ("no compila", como Java). GitHub la publica en GHCR (`.github/workflows/pseint-sandbox.yml`).
4. **El perfil es el de PSeInt oficial 20250314 por defecto** (sin `--profile`): arreglos desde 1, `=` no asigna, `y`/`o` reservadas, `Para` descendente implícito, `Escribir a, b` sin separador, números con hasta 10 decimales, comparaciones con tolerancia. Las reglas están en `packages/pseint/PERFIL.md`.
5. **El árbitro es PSeInt oficial 20250314**, no nuestro intérprete: el corpus de paridad (`packages/pseint/tests/paridad/`) se corre contra el binario oficial con `generar_esperados.py`, y la prueba exige salida idéntica byte a byte (y misma línea en los errores). Una duda sobre el lenguaje se resuelve corriendo el oficial.
6. **Divergencia deliberada en `Leer`**: con la entrada por adelantado (casos, Probar, servidor), si `Leer` pide un dato y no quedan, es un **error de ejecución**. PSeInt oficial lee vacío y sigue; un caso con menos datos que los que pide el algoritmo es un error que no se deja pasar en silencio. Las otras divergencias (variables sin valor, choques de tipo de variables, mensajes propios) están listadas en `PERFIL.md`.
7. **La imagen es opcional (N06)**: con `PSEINT_IMAGE` vacía el runner arranca, Java y Python siguen, `/run` con PSeInt responde 503 `lenguaje_no_disponible` sin lanzar Docker, y la corrección sale con todos los casos `skipped` (no es fallo de infraestructura). `/health/live` del runner lista los lenguajes disponibles. Si la imagen se configura, va por digest (control C1).
8. **El CTR registra el motor**: `codigo_ejecutado.runtime` es `pseint-ts-X.Y.Z` (`VERSION` del paquete) para PSeInt y sigue siendo `pyodide-0.26` para Python. El tutor-service valida el valor con una expresión regular porque va a una cadena append-only.

## Alternativas consideradas

- **Compilar PSeInt oficial a WebAssembly.** Descartada. PSeInt es GPL: distribuirlo compilado dentro del bundle del frontend arrastra obligaciones de licencia sobre la plataforma. Además su intérprete está pensado para una consola de escritorio: el `Leer` bloquea esperando el teclado, y hacerlo interactivo en el navegador obliga a correrlo en un worker con memoria compartida (cabeceras COOP/COEP que hoy no servimos) o a reescribir su bucle principal. Con eso, el costo de mantener un port superaba el de un intérprete propio del subconjunto que se enseña.
- **Ejecutar PSeInt solo en el servidor** (el binario oficial en el sandbox, como Java). Descartada: cada Ejecutar costaría un contenedor, el `Leer` no podría ser interactivo (el stdin va completo y por adelantado) y el alumno esperaría segundos por algo que el navegador resuelve al instante.
- **Traducir PSeInt a Python y correrlo en Pyodide.** Descartada: los errores llegarían en términos de Python, las líneas no coincidirían con las del alumno y el perfil (arreglos desde 1, formato de números, `Para` descendente) quedaría disperso en una traducción frágil.
- **Hacer obligatoria `PSEINT_IMAGE`.** Descartada: un deploy que no la cargara tiraría el runner y con él Java y Python. PSeInt en el servidor solo hace falta para la corrección con IA.

## Consecuencias

- El intérprete es código nuestro que hay que mantener. La red es el corpus de paridad: un cambio de comportamiento se verifica contra el oficial antes de tocar el intérprete, y un caso nuevo se agrega al corpus con su esperado generado por el oficial.
- Cada cambio del intérprete publica una imagen con digest nuevo. Hasta que se copie a `PSEINT_IMAGE`, el servidor corrige con el intérprete anterior mientras el navegador usa el nuevo; el `runtime` del CTR dice qué versión corrió en el navegador.
- Los errores de PSeInt no cuentan como tropiezos (`platform_ops.tropiezos`), igual que los de Java: el detector entiende excepciones de Python.
- Lo que el perfil oficial hace y el nuestro no (subconjunto no cubierto, divergencias) queda escrito en `PERFIL.md`; ampliar el subconjunto es una historia nueva.

## Contexto del tutor para PSeInt (HU-034)

- **Qué se agrega.** Cuando el ejercicio o la TP declaran `language == "pseint"`, el tutor recibe una guía breve: el alumno escribe en PSeInt (perfil oficial 20250314) y suele ser su primer contacto con la programación; tiene que explicar con palabras simples y con el vocabulario de PSeInt, mostrar sintaxis o ejemplos siempre en PSeInt y nunca en Python, conocer las reglas del perfil que más confunden (`<-` asigna y `=` compara, `Dimension` y arreglos desde 1, `Y`/`O`/`NO` reservados, el nombre del `Algoritmo` no se repite en una variable, `Para` descendente) e invitar a usar el "Paso a paso" (prueba de escritorio), la pestaña "Diagrama" y la línea de los errores antes de dar pistas. Sigue siendo socrático.
- **Dónde.** El texto vive en `apps/tutor-service/src/tutor_service/services/contexto_pseint.py` y `TutorCore._build_ejercicio_context` lo agrega una sola vez como bloque `[Lenguaje del ejercicio: PSeInt]`, después de los datos del ejercicio y antes de `tutor_rules`, igual que el resto de la inyección pedagógica del ADR-048. Para Python, Java y los ejercicios sin `language` el contexto queda idéntico byte a byte (lo fija la aceptación `apps/tutor-service/tests/unit/test_hu034_tutor_pseint.py` con huellas sha256).
- **Por qué no se toca el prompt.** El prompt del tutor (`ai-native-prompts/`) es coautoría de Ana Garis y se mantiene intacto byte a byte; su huella la fija `apps/execution-service/tests/unit/test_hu030_despliegue.py`. Lo específico de un lenguaje es una particularidad del ejercicio, no del comportamiento general del tutor.
- **Versión.** `CONTEXTO_PSEINT_VERSION` (semver, hoy `1.0.0`), junto al texto y re-exportada desde `tutor_core`. Cualquier cambio de la guía la sube. El LLM no la ve.
