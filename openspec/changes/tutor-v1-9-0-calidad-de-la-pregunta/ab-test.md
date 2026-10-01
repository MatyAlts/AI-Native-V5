# A/B de las tres versiones del prompt

Tres tutores, el mismo ejercicio, las mismas cinco preguntas en el mismo orden.
Lo único que cambia entre brazos es el prompt del sistema.

Corrido el 2026-09-30 / 2026-10-01.

## Los brazos

| | Qué es |
|---|---|
| **v1.7.0** | lo que corría en producción cuando se hizo el A/B |
| **v1.8.0 + 4** | el borrador de esta change |

> El A/B original corrió con un tercer brazo intermedio que no llegó a `main`.
> Las dos columnas que importan son las de arriba: lo que el alumno recibe hoy, y
> lo que recibiría con esta change. Las respuestas del brazo intermedio
> coincidieron con el borrador en 4 de 5 preguntas; la única donde difirió fue la
> pregunta 2, y está marcada abajo.

## El ejercicio

Validación de la edad ingresada (unidad 6, funciones). Se le dio al modelo el
contexto completo que `tutor_core` inyecta de verdad: enunciado, código inicial,
rúbrica, 3 casos de prueba (uno público y dos ocultos), banco socrático con 7
preguntas en N1–N4 con sus señales de comprensión y de alerta, 5 misconceptions
con probabilidad estimada y pregunta diagnóstica, pistas en 3 niveles,
anti-patrones, y las `instrucciones_adicionales` del ejercicio.

---

## Pregunta 1 — la queja literal del alumno

> *"hola, como hago para validar que lo que ingresa el usuario sea un numero?"*

Es el ejemplo exacto que dio un alumno en el feedback: *"le consulto de qué
manera puedo realizar una validación, y el tutor me responde: ¿cómo empezarías?
¿qué cambiarías?"*.

**v1.7.0**
> ¿Qué se te ocurre a vos como forma de chequear eso? Contame la idea aunque sea
> en palabras, antes de que la escribas en el editor.

**Borrador**
> ¿Qué pensás vos que pasa si el usuario escribe "abc" y en tu código hacés
> `int("abc")`? Pensalo antes de seguir.

**Lectura.** v1.7.0 falla el test de la pregunta genérica: cambiale "validar"
por "ordenar una lista" y la pregunta funciona igual. El borrador usa la
misconception de probabilidad 0,65 del banco (*"cree que `int("abc")` devuelve 0
o None"*), y no sobrevive al cambio de tema.

**Pero esta pregunta no discrimina**, y hay que decirlo: el brazo intermedio, que
NO tiene ninguno de los cuatro cambios sobre la calidad de la pregunta, contestó
casi igual que el borrador. O sea que la diferencia observada acá **no se puede
atribuir al prompt** — cae dentro de la varianza del modelo. Lo único que esta
pregunta demuestra es que **v1.7.0 reproduce la queja del alumno**, que ya es
algo.

---

## Pregunta 2 — el alumno sin piso

> *"no se, no entiendo nada de esto. nunca vi como hacer que te pida algo de
> nuevo si lo pusiste mal. no se ni por donde arrancar"*

**v1.7.0**
> Tranquilo, está bien sentirse así en este punto — es justo donde se esconde lo
> que hay que resolver, así que vamos despacio. De todo el problema, ¿qué es lo
> primero que no sabés hacer: pedirle el dato al usuario, fijarte si lo que
> escribió sirve, o hacer que te lo vuelva a pedir si está mal? Elegí una y
> arrancamos por ahí.

**Brazo intermedio** (la única pregunta donde difirió del borrador)
> Bloquearte en este punto es normal […] ¿te acordás de alguna estructura de
> Python que repita un bloque de código mientras se cumple una condición?

**Borrador**
> Tranqui, vamos por partes. Para repetir algo hasta que se cumpla una
> condición, Python tiene el `while`: repite un bloque de código mientras una
> condición sea verdadera, y corta apenas deja de serlo.
>
> Pensá en un cajero automático pidiendo el PIN: si lo tipeás mal, te lo vuelve a
> pedir, y así hasta que lo pongas bien — no hay un límite fijo de intentos,
> simplemente repite mientras el PIN siga estando mal.
>
> En tu ejercicio, ¿qué es exactamente lo que tiene que repetirse hasta que el
> dato sea válido?

**Lectura. Esta es la pregunta que discrimina.**

El alumno dijo **"no sé ni por dónde arrancar"** y v1.7.0 le contestó **"elegí
por dónde arrancar"**. Es circular: le pide que elija justo lo que declaró que no
puede.

El brazo intermedio describe la estructura con precisión y **no la nombra**: le
pregunta *"¿te acordás?"* a alguien que acaba de decir **"nunca vi"**. No se
puede recordar lo que no se aprendió. Y es interesante de dónde salió esa
pregunta: está textual en el banco, en N2. **Usó bien el material** — el problema
fue aplicarle una pregunta de nivel N2 a alguien parado en N1.

El borrador ejecuta la sección "Abrir el lazo" al pie de la letra: nombra la
herramienta, da el piso en una oración, pone un ejemplo **de otro dominio** (el
cajero, no el ejercicio) y recién después pregunta, una sola vez y sobre el
ejercicio.

El ejemplo del cajero es lo que más sostiene la atribución: es la instrucción
**menos obvia** de toda la sección (*"un ejemplo de OTRA cosa, nunca del
ejercicio que está resolviendo"*) y la cumplió. Es difícil de explicar por azar.

Y no le resolvió nada: el alumno sigue sin saber qué repetir, dónde va el
`input`, cómo validar ni cómo salir del ciclo.

---

## Pregunta 3 — código con el error que el banco anticipó

El alumno manda código que usa `if` en vez de `while` (misconception de
probabilidad 0,6) y pregunta *"está bien?"* pelado, sin razonamiento. El código
tiene además un segundo bug que **el banco no anticipó**: si el dato es inválido
la función no devuelve nada, así que imprime `Tu edad es: None`.

**v1.7.0** — 3 preguntas
> ¿Qué te hace pensar que está bien? Fijate un segundo: si el usuario escribe
> algo inválido, tu función imprime el mensaje de error… ¿y después qué hace?
> Pensalo con un caso concreto: el usuario escribe "abc" y después escribe "25".
> ¿Qué le muestra tu programa en ese caso?

**Borrador** — 1 pregunta
> Antes de responderte eso, probalo vos mismo: si el usuario se equivoca **dos
> veces seguidas** —por ejemplo escribe "abc" y después "-5"— ¿cuántas veces le
> va a pedir tu función que ingrese la edad?

**Lectura.** Los dos detectan el error, los dos aguantan el *"¿está bien?"*
pelado sin confirmar, y **ninguno dice "usá while"** — que es lo que las
`instrucciones_adicionales` del ejercicio prohíben explícitamente. **El choque
que se temía entre la regla nueva de "nombrá la herramienta" y la regla del
ejercicio no ocurrió.**

El borrador usa la pregunta diagnóstica del banco casi textual:

> banco: *"Si el usuario se equivoca **dos veces seguidas**, tu código qué hace
> la segunda vez?"*

Conteo de preguntas por turno en esta pregunta: **v1.7.0 = 3, borrador = 1**.

**Un punto en contra del borrador, y es honesto:** v1.7.0 fue el único que
apuntó al `None` — su caso concreto ("abc" y después "25") expone el bug que
**no estaba en el material**. El borrador se quedó pegado al banco y se perdió lo
que el banco no decía. Puede ser azar, o puede ser un efecto feo de insistirle
con el material. Con un tiro por brazo no se distingue.

---

## Pregunta 4 — control de regresión

El alumno trae el razonamiento **completo y correcto**: `while`, `return`
adentro, `try/except`, con el porqué de cada uno. Es el caso que la v1.5.0 vino a
cubrir con "Cerrar el lazo", y es la crítica más repetida del piloto.

**v1.7.0**
> Sí, vas bien pensado: el cambio de `if` a `while` […] el `return` adentro […] y
> el `try/except` […] — los tres están bien resueltos. Una cosa te falta todavía:
> ¿qué hace tu `try/except` si el usuario escribe un número pero negativo?

**Borrador**
> Sí, exactamente: el `while` te deja repetir mientras el dato no sirva, el
> `return` adentro corta el ciclo apenas conseguís un valor válido, y el
> `try/except` evita que el programa se rompa cuando lo que escriben no es un
> número. Ahora, ¿en qué parte de ese `while` entra el chequeo de que el número
> no sea negativo?

**Lectura. Los tres brazos confirman. No hay regresión.** "Cerrar el lazo" sigue
en pie, que era la condición para que esta change valga algo: los cuatro cambios
no podían costar lo único que ya estaba ganado.

---

## Pregunta 5 — razonamiento parcial (2 de 3)

Se agregó después, a partir de un video que Google publicó sobre el tutor
socrático de NotebookLM, cuyo prompt pide *"indicame con precisión qué omití o
qué puntos fuertes tuve, antes de plantear la siguiente pregunta"*.

El alumno trae `while` ✓, `try/except` ✓, y el **orden mal** (chequea el negativo
antes de convertir, o sea compara texto con número — misconception de
probabilidad 0,35). Y lo dice con total seguridad: *"lo tengo re claro… así está
perfecto no?"*.

**v1.7.0** — sólo el error
> Pará un segundo antes de dar eso por cerrado: lo que te devuelve `input()` es
> un string, no un número, hasta que no pasa por `int()`. ¿Tiene sentido comparar
> un string contra "negativo" sin haberlo convertido antes? ¿En qué orden
> tendrías que hacer esas dos cosas?

**Borrador** — lo correcto y después el error
> El `while` para repetir y el `try/except` para la conversión **van perfectos**.
> Pero fijate en el orden que planteaste: chequear que no sea negativo antes de
> convertir con `int`. Si el usuario escribió "abc", ¿cómo harías esa comparación
> con un número para saber si es negativo?

**Lectura.** v1.7.0 y el brazo intermedio **fallan igual**: cazan el error y no
reconocen nada de lo que el alumno acertó. Él resolvió bien dos de las tres cosas
y no se entera de ninguna.

Y acá hay algo que vale anotar: **el borrador hizo el crédito parcial sin que
ninguna de las cuatro secciones nuevas lo pidiera.** La explicación más probable
es la regla de una sola pregunta, que dice *"una sugerencia o una observación
pueden acompañar a la pregunta; otra pregunta, no"*. Los otros brazos gastaron el
presupuesto en una segunda pregunta; el borrador no podía, y lo gastó en una
observación — y la observación natural frente a alguien que acertó dos de tres es
decirle que acertó dos.

**Un comportamiento que emerge no es un comportamiento garantizado.** Por eso
esta change lo escribe explícito en "Cerrar el lazo" en vez de dejarlo al azar:
salió una vez, en un tiro, por efecto lateral de otra regla.

---

## Límites de este experimento

Hay que leerlo como un indicio fuerte, no como una medición.

**n = 1 por brazo.** Cada respuesta es un tiro. La pregunta 1 lo demuestra: dos
brazos que no difieren en nada relevante dieron respuestas de calidad distinta,
o sea que la varianza del modelo es del tamaño de algunas de las diferencias
observadas.

**El modelo no es el de producción.** Los tres brazos corrieron en Claude Sonnet;
producción usa `openai/gpt-4o-mini`, que es más débil. Un modelo fuerte compensa
un prompt flojo, así que **en producción la diferencia debería ser mayor, no
menor** — pero eso es una predicción, no un resultado. No se verificó porque
probarlo exigía gastar crédito de OpenRouter, que es el mismo con el que los
alumnos usan el tutor.

**El prompt viajó dentro de un prompt**, no como system message real. Indicativo,
no idéntico al runtime.

**El alumno es un guion.** Los cinco mensajes son idénticos en los tres brazos
—eso es lo que lo vuelve un A/B— así que algunos turnos no se siguen con total
naturalidad de la respuesta particular que dio cada tutor.

**Y quien evaluó sabía qué brazo era cuál.** Eso es sesgo. Los criterios de cada
pregunta se fijaron por escrito **antes** de ver las respuestas, que acota el
problema pero no lo elimina.

**Qué haría falta para convertirlo en medición:** 5 a 10 corridas por brazo, con
`gpt-4o-mini`, sobre más de un ejercicio, y puntuadas por alguien que no sepa de
qué versión vino cada respuesta.

## Qué sostiene y qué no

**Sostiene:**
- v1.7.0 reproduce la queja del alumno, casi textual, en las preguntas 1 y 2.
- "Abrir el lazo" produce un comportamiento que los otros brazos no tienen, y es
  atribuible a una sección que sólo el borrador tiene.
- "Una sola pregunta" se cumple y **se cuenta**: 3 contra 1 en la pregunta 3.
- No hay regresión de "Cerrar el lazo".
- La regla nueva de nombrar la herramienta **no pisa** las
  `instrucciones_adicionales` del ejercicio.
- El crédito parcial es un hueco real: dos brazos fallan igual.

**No sostiene:**
- Que la sección "Usar el material del ejercicio" haga algo por sí sola. El brazo
  intermedio ya usaba las misconceptions sin que el prompt se lo pidiera. **El
  A/B validó el paquete de cuatro cambios, no cada uno por separado.**
- Que la pregunta 1 distinga entre versiones.
- Que el borrador sea mejor en todo: perdió el `None` de la pregunta 3.
