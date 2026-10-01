# Tareas

## El enfoque, decidido antes de empezar

**Dos buffers, no centinelas.**

El shim de Pyodide ya controla las dos escrituras: la del prompt
(`if prompt: _out.write(str(prompt))`) y la del `print` del alumno. Entonces:

- **buffer de pantalla** — lo que el alumno ve en la terminal: prompts + prints.
  **No cambia.** El alumno tiene que seguir viendo su mensaje, si no el
  ejercicio pierde sentido.
- **buffer de comparacion** — solo la salida que produjo el codigo del alumno
  via `print` / `sys.stdout.write`. El prompt del `input` **no entra**.

**No usar un centinela** (un marcador tipo `\x00PROMPT\x00` alrededor del
texto): si el alumno imprime esa secuencia, la comparacion se rompe de una
forma que nadie va a diagnosticar.

Si al leer el codigo real resulta que los dos buffers no se pueden separar,
**pará y reportá** en vez de inventar un centinela. Es una decision de diseno,
no un detalle.

## 0. Red de seguridad (antes de tocar nada)

- [x] Correr los tests existentes de comparacion y anotar el baseline exacto:
      `packages/contracts` (los de `comparacionSalida`), los de
      `apps/execution-service` que usan `outputs_match` / `normalize_output`, y
      los de `apps/web-student` y `apps/web-teacher` que tocan el runner.
- [x] Si alguno falla YA, **no lo arregles**: anotalo como fallo pre-existente y
      reportalo. Hay 10 fallos pre-existentes conocidos en la suite Python.
      (Ninguno de los tests tocados por esta change vino rojo — ver informe final.)

## 1. La tabla de paridad primero (es el contrato)

`tests/fixtures/paridad-salida.json` es la tabla compartida que cotejan la
implementacion TS y la Python. Los casos nuevos van **ahi primero**, y las dos
implementaciones los tienen que pasar.

- [x] Caso: prompt de un solo `input` + salida → coincide con el `expected` sin
      el prompt.
- [x] Caso: **varios** `input` seguidos (el de E3 tiene cuatro) → los cuatro
      prompts salen de la comparacion.
- [x] Caso: el alumno escribe un mensaje **distinto** al del banco → coincide
      igual.
- [x] Caso: `input()` **pelado**, sin mensaje → **sigue coincidiendo** (no se
      rompe a quien ya aprendio a escribirlo asi).
- [x] Caso: el alumno imprime **de mas** con un `print` que el ejercicio no
      pedia → **sigue fallando**. Lo que se ignora es el prompt del `input`, no
      cualquier salida extra. Este es el caso que separa el fix de un
      aflojamiento del comparador.
- [x] Caso: el prompt es lo UNICO que se imprime (el alumno no imprime nada
      mas) → la salida comparada queda vacia.

## 2. El shim del alumno

`apps/web-student/src/components/CodeEditor.tsx` — el `_feed` (cerca de la
linea 1184) y la captura de stdout.

- [x] RED: test que falle con el codigo de hoy.
- [x] GREEN: separar los dos buffers.
- [x] El buffer de pantalla sigue mostrando el prompt. Verificalo con un test,
      no de ojo.

## 3. El shim del docente

`apps/web-teacher/src/lib/pyodideRunner.ts`.

- [x] Mismo cambio. **Si queda solo en uno de los dos, reabrimos la asimetria
      del PR #92**: el docente valida en verde lo que al alumno le da rojo. Ese
      incidente lo reporto un docente el 2026-09-10 con estas palabras: *"me
      puse a testear porque tenia todo bien y me daba mal las pruebas"*.

## 4. El comparador canonico y su gemela

- [x] `packages/contracts/src/comparacionSalida.ts` — recibe la salida ya
      separada; no deberia necesitar adivinar nada.
- [x] `apps/execution-service/src/execution_service/services/docker_runner.py`
      (`normalize_output` / `outputs_match`) — paridad con la tabla.
- [x] Los dos pasan **los mismos** casos de `paridad-salida.json`.

## 5. Java queda afuera, y se escribe

- [x] Dejar dicho en el codigo (no solo en esta change) que el fix es Python por
      construccion: en Java el prompt es un `print` comun y no hay forma de
      distinguirlo. Donde vive el comparador, un comentario corto con el porque.

## 6. Verificacion contra el caso real

- [x] La solucion de la pista de E2 (`scripts/seed_ejercicios_p6_funciones.py`,
      linea 480), **con el mensaje puesto**, contra el `expected` de la linea
      318: tiene que **pasar**. Hoy da `False` — es el caso que abrio esta
      change.
- [x] Lo mismo con E3 (pista en linea 713, `expected` en 551), que tiene
      **cuatro** `input` con mensaje.
- [x] Mostrar el comando y su salida. Sin eso es un juicio, no evidencia.
      (Ver informe final — script de verificacion que corre las soluciones
      REALES de E2/E3 con el algoritmo de dos buffers contra `outputs_match`
      real del execution-service.)

## 7. Lo que NO se toca

- [x] Los 30 `expected` del seed. **Ni uno.** Si tocas datos, el enfoque elegido
      dejo de ser el elegido.
- [x] El gate de publicacion. Es otra change.
- [x] La pantalla de resultados de la prueba. Es otra change.
- [x] Nada del tutor ni de sus prompts.

## Modo TDD estricto

Esta activo. Para cada tarea: RED (test que viste fallar) → GREEN (lo minimo)
→ TRIANGULATE (segundo caso con otros datos) → REFACTOR (tests verdes despues
de cada paso).

El informe final lleva la tabla de evidencia del ciclo, y los resultados en
categorias tipadas: **EVIDENCIA** (comando + salida + timestamp), **JUICIO**
(quien, contra que lo comparo, confianza), **SUPUESTO** (lo que diste por
sentado y que hiciste en lugar de verificarlo).
