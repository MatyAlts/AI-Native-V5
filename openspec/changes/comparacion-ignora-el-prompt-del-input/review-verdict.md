# Veredicto de revision

Tres actores: un implementador, un QA que no tocó producción, y un auditor que
leyó los informes en vez del código. Nada de esto estaba en el chat y nada más;
queda acá para que se archive con la change.

## Lo que QA encontró, y habría rebotado el PR

**`tsc --noEmit` fallaba.** `CodeEditor.tsx` construía `TestCaseResult` sin el
campo `comparacion`, que esta change volvió obligatorio en la interfaz.

No era cosmético: QA leyó `.github/workflows/ci.yml` y confirmó que **dos jobs**
corren ese chequeo — `lint-frontend` (`turbo lint typecheck`) y
`build-frontend` (`tsc -b && vite build`). El PR llegaba rojo.

Vitest no lo atrapó porque usa esbuild, que no chequea tipos. **El implementador
lo había declarado como SUPUESTO antes de que nadie preguntara**: *"no corrí
`tsc`... esto no está verificado por nada"*. El supuesto era real. Declararlo
fue lo que hizo que se buscara.

### La corrección obvia era peligrosa

QA propuso `comparacion: c.comparacion ?? ""`. Se descartó.

El sitio es la rama **remota**, o sea Java. Ahí no hay prompt que separar —el
prompt es un `System.out.print` común, indistinguible de cualquier salida— así
que lo que se compara **es el stdout crudo**. El valor correcto es `c.got ?? ""`.

Con `""` no se rompe nada **hoy**, porque esa rama no llama a
`resolverVeredictosPython` (el veredicto lo trae el servidor en `c.status`). Y
eso es exactamente lo que la vuelve una mina: el día que alguien rutee Java por
el resolvedor, **cada caso compara su salida contra vacío y todos los ejercicios
de Java fallan**, sin que ningún test de hoy avise.

Quedaron 3 tests estructurales fijándolo (`tutorRunTestsBuffers.test.ts`),
verificados **por mutación**: cambiando el valor a `""`, 2 se ponen rojos.

## Lo que queda abierto, dicho por quien lo dejó

**Los 6 casos nuevos de `tests/fixtures/paridad-salida.json` son decorativos.**

El implementador lo declaró solo, sin que nadie preguntara: *"una vez separado
el buffer, lo que llega al comparador es indistinguible, en el string literal,
de un caso sin prompt"*. QA lo confirmó trazando los tres consumidores del
fixture —ninguno pasa por `_DualOut`/`_feed`, todos llaman al comparador sobre
los strings literales del JSON— y armó una tabla caso-nuevo contra
fila-preexistente equivalente. El auditor lo verificó por tercera vez, por su
cuenta, y confirmó que la convergencia es real y no una copia.

Se dejaron igual: su valor es documental (dejan constancia legible del caso E2 /
E3 que abrió la change), no cobertura mecánica nueva. **La cobertura real del
criterio que importa** —"un print de más sigue fallando"— vive en
`veredictoTests.test.ts` y en `comparacionSalida.test.ts` del web-teacher, donde
QA confirmó **por mutación** que discriminan de los dos lados.

**Ningún test ejecuta la separación real de buffers dentro de Pyodide del lado
del alumno.** `tutorRunTestsBuffers.test.ts` afirma por regex sobre el código
fuente. Es el patrón que el repo ya usa (`pyodideBootstrapCompila.test.ts`, con
el mismo comentario sobre por qué), porque Pyodide no corre en vitest — pero es
un hueco y queda dicho. La garantía descansa en: lectura de código, el test
estructural, y el test ejecutable equivalente del lado docente que viene del
PR #92.

**Nadie corrió la suite Python completa del monorepo.** Los tres lo declararon:
el runner raíz aborta por precondición de smoke (`Connection refused` en 11
puertos). El claim de los "10 fallos pre-existentes" **no se verificó** — no
aparecieron en el alcance de esta change, y eso es todo lo que se puede afirmar.

**Java no queda cubierto, y no por falta de trabajo.** En Python,
`input(prompt)` es una sola llamada que escribe y lee, así que el shim sabe qué
salida es el prompt. En Java son dos operaciones y el prompt es un print común.
QA trazó que para Java el docente y el alumno pasan por el **mismo** código
(`execution-service`), así que no hay dos implementaciones que puedan divergir:
la limitación es simétrica, no es una asimetría nueva, y el incidente del PR #92
no puede reabrirse por acá.

## Lo que el auditor encontró del orquestador

Dos cosas, las dos ciertas:

1. **La change vivía sin commitear** cuando se escribieron los tres informes.
   `git log origin/main..HEAD` no traía nada: ninguna evidencia anclaba a un
   SHA. Se corrigió commiteando.
2. **El archivo de claims que se le pasó al auditor estaba incompleto.** Omitía
   que QA sí había sugerido el fix `comparacion: c.comparacion ?? ""`, así que
   el auditor no pudo verificar esa atribución y la marcó como sin respaldo.
   Tenía razón sobre lo que tenía delante. QA lo había escrito textual; el
   resumen lo perdió.

El auditor no encontró ningún supuesto ascendido a evidencia en los tres
informes, y lo anotó como mérito: los tres declararon los suyos justo en los
puntos donde un informe más prolijo los habría escondido.

## Lo que esta change NO hace

**El gate que faltaba.** La causa raíz de que 30 casos rotos llegaran a
producción es que nada corre una solución de referencia contra los `test_cases`
antes de publicar o sembrar un ejercicio. Change aparte, y es la inversión de
verdad: esta arregla los casos de hoy, el gate arregla los de marzo.

**La pantalla de la prueba.** Un alumno dijo *"no entiendo qué es lo que muestra
la parte de prueba"*. Sobrevive a esta change: hoy muestra rojo sin mostrar qué
esperaba contra qué obtuvo.

**Las otras unidades.** No se revisaron. Esta change las arregla igual, porque
no depende de los datos — pero no se afirma que no tengan otros problemas.
