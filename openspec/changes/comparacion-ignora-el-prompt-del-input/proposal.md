# La comparacion de salida ignora el prompt del `input()`

## El problema, con evidencia

Un alumno reporto:

> "es muy estricto con las pautas del ejercicio... un ejemplo es cuando al hacer
> un input para el usuario, en varios ejercicios de la unidad 6 no se le podia
> poner un mensaje para guiar al usuario. Lo que genero confusion porque en
> clase y en el parcial se toma en cuenta la posicion del usuario a la hora de
> hacer un input."

Otros dos lo describieron por el sintoma, sin saber la causa:

> "los input no permiten poner mensajes para el usuario"

> "hubieron veces que hacia bien el codigo y me lo marcaba mal por la parte de
> prueba, pero a la hora de probar el codigo funcionaba"

Tres reportes, tres encuadres, dos canales distintos (planilla de feedback y
WhatsApp). Convergen.

**Reproducido** el 2026-09-30 con el comparador del propio repo
(`outputs_match` de `apps/execution-service/.../docker_runner.py`), sobre el
ejercicio E2 del seed `scripts/seed_ejercicios_p6_funciones.py`:

```
expected del banco:                              'Hola Marcos!'
siguiendo la pista  input("Ingrese su nombre: ")  'Ingrese su nombre: Hola Marcos!'  -> False
con  input()  pelado                              'Hola Marcos!'                    -> True
```

La **pista que escribio el docente** (`seed_...py:480`) falla su propio caso de
prueba (`:318`). El enunciado muestra el mensaje, la pista manda a escribirlo, y
el test lo rechaza.

Consecuencia: el alumno aprende a escribir `input()` pelado, que es **lo
contrario de lo que le ensenan en clase y le toman en el parcial**, y pierde
nota por haberlo hecho bien.

## Por que no alcanza con corregir los 30 `expected`

Era la opcion obvia: agregarle a cada `expected` el texto del prompt. Se
descarto, y el motivo es el que decide esta change.

Si el `expected` incluye el texto del prompt, el alumno queda obligado a
escribir el mensaje con **las palabras exactas del docente**. Un alumno que
escribe `input("Ingrese la edad: ")` donde el banco dice `"Edad: "` falla **por
la redaccion, no por el codigo**. La plataforma pasaria a calificar la eleccion
de palabras.

Y la rubrica **no evalua el texto del mensaje en ningun ejercicio**: evalua que
defina la funcion, que devuelva con `return`, que rechace texto y negativos. Que
el prompt entre a la comparacion es un accidente de como `input()` escribe a
stdout, no una decision pedagogica de nadie.

## Que se hace

El prompt del `input()` **sale de la comparacion**. El `expected` del banco no
se toca, y cualquier mensaje que el alumno escriba pasa igual.

Los 30 casos de la unidad 6 quedan correctos sin migrar un solo dato, y todo
ejercicio futuro con `input` nace correcto. Es la unica opcion que arregla los
de hoy y los que nadie escribio todavia.

## El limite: esto es Python, y en Java no se puede

En Python, `input(prompt)` es **una sola llamada** que escribe el prompt y lee
la linea, asi que el shim de Pyodide sabe que esa salida es un prompt y puede
separarla.

En Java no: el alumno hace `System.out.print("Edad: ")` y despues
`scanner.nextLine()`. Son dos operaciones y el prompt **es un print comun** —
indistinguible por construccion, no por falta de trabajo.

Entonces esta change cubre Python (que es Programacion 1, donde esta el
problema) y **no cubre Java**. Queda declarado, no asumido: si manana un
ejercicio de Java reporta lo mismo, esta change no lo arregla y hace falta otra
decision.

## Lo que NO entra

**El gate que faltaba.** La causa raiz de que 30 casos rotos llegaran a
produccion es que **nada corre una solucion de referencia contra los
`test_cases` antes de publicar o sembrar un ejercicio**: la ruta de
`academic-service` no llama al execution-service al crear/actualizar/publicar, y
el panel "Probar ejercicio" del web-teacher es opcional (el boton de guardar no
depende de haberlo corrido en verde). El seed, encima, postea directo a la API
de produccion y lo saltea entero.

Eso es una change aparte, y es la inversion de verdad: esta arregla los casos
de hoy, el gate arregla los de marzo. Se separa porque toca otro servicio, otro
flujo y otro criterio de "terminado".

**La pantalla de la prueba.** Un alumno dijo "no entiendo que es lo que muestra
la parte de prueba". Eso sobrevive a esta change: es una pantalla que hoy
muestra rojo sin mostrar que esperaba contra que obtuvo. Frontend, change
aparte.

**Las otras unidades.** No se revisaron. Esta change las arregla igual, porque
no depende de los datos — pero no se afirma que no haya otros problemas en
ellas.

## Riesgos

**Es un cambio de semantica de la comparacion, y la comparacion decide notas.**
No es un bug aislado: toca el criterio con el que se evalua todo ejercicio de
Python de la plataforma.

**Hay dos implementaciones que tienen que quedar en paridad.** La canonica en TS
(`packages/contracts/src/comparacionSalida.ts`, que usan web-student y
web-teacher) y su gemela en Python
(`apps/execution-service/.../docker_runner.py`). Estan cotejadas por la tabla
compartida `tests/fixtures/paridad-salida.json`. Si una se cambia sin la otra,
**el docente valida en verde lo que al alumno le da rojo** — que es exactamente
el incidente que un docente reporto el 2026-09-10 y que cerro el PR #92.

**Hay tres runners, no dos.** `apps/web-student/src/components/CodeEditor.tsx`
(el del alumno), `apps/web-teacher/src/lib/pyodideRunner.ts` (el del docente) y
el `execution-service` para Java. Un fix en dos de tres reabre la asimetria del
PR #92.

## Como se sabe que funciono

- La solucion de la pista de E2, con el mensaje puesto, **pasa**.
- La misma solucion con `input()` pelado **sigue pasando** (no se rompe a quien
  ya aprendio a escribirlo sin mensaje).
- Un alumno que escribe un mensaje **distinto** al del banco pasa igual.
- Un alumno que imprime **de mas** (un `print` que el ejercicio no pedia)
  **sigue fallando** — lo que se ignora es el prompt del `input`, no cualquier
  salida extra.
- La tabla de paridad TS/Python sigue verde, con casos nuevos para esto.
