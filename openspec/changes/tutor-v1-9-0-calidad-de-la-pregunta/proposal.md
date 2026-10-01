# Prompt del tutor v1.9.0 — la calidad de la pregunta

## El problema

Cuatro alumnos del piloto, por dos canales distintos, dijeron la misma cosa de
cuatro formas:

> *"me responde con preguntas que no me llevan a nada y terminé recurriendo a la
> documentación u otras fuentes. Le consulto de qué manera puedo realizar una
> validación, y el tutor me responde: ¿cómo empezarías? ¿qué cambiarías? ¿por qué
> creés que deberías validarlo?"*

> *"nunca me ha dicho una función o porción de código, estaría bueno que te
> enseñe (no que te resuelva el código)"*

> *"Preguntás alguna duda y responde con otra pregunta, en vez de mostrar ejemplo
> como ayuda"*

> *"estaría bueno que el tutor hiciese referencias bibliográficas al material del
> curso"* — **esta queda afuera**, ver abajo.

## El diagnóstico

Las tres primeras son el mismo defecto, y no es que el tutor sea demasiado
socrático.

**Los cuatro movimientos del método son todos de apertura, y los cuatro
presuponen que el estudiante ya tiene algo adentro.** La ironía suspende un
saber que cree tener, la mayéutica extrae una creencia latente, el elenchos
contradice una posición que sostuvo, la aporía desarma una certeza previa. Son
movimientos de **mitad de diálogo**.

En el Menón el esclavo ya sabe qué es un cuadrado; las preguntas le sacan una
geometría que nunca articuló. Si nunca hubiera visto un cuadrado, *"¿cómo
empezarías?"* no le saca nada, porque no hay nada que sacar.

Un alumno de primer año que nunca escuchó hablar del concepto está exactamente
ahí, y **es el caso más común, no el raro**.

Es el mismo defecto estructural que cerró la v1.5.0, del otro lado. Aquella le
puso **salida** al método (confirmar cuando el alumno acierta). Esta le pone
**entrada**: qué hacer cuando todavía no tiene de dónde agarrarse.

**Y hay un desbalance en el prompt que lo agrava.** Contá el espacio: cientos de
líneas para la FORMA de preguntar (cuatro movimientos, nueve principios, una
sección entera para cerrar el lazo) y **media oración** para el material del
ejercicio — el banco socrático N1–N4 con señales de comprensión y de alerta, las
misconceptions con probabilidad y pregunta diagnóstica, los anti-patrones. Todo
eso llega al modelo ricamente formateado (`tutor_core.py`, bloques 4 a 7) y el
prompt lo menciona una vez, de pasada, con un *"nunca para revelarlo"* al lado.

Cuando un modelo tiene la forma clarísima y el contenido en una nota al pie, sale
*"¿cómo empezarías?"*.

## Los cinco cambios

Ninguno toca guardrails. Los cinco son sobre la calidad de la pregunta.

1. **Una sola pregunta por turno** (antes: *"una o dos"*). Tres preguntas juntas
   no son tres oportunidades de pensar: son una pared. El alumno no sabe cuál
   contestar, contesta la más fácil, o no contesta ninguna.
2. **Nombrar una herramienta que el alumno no conoce no es resolver.** Nadie
   deduce `while`, `range()` ni `try/except` pensando con fuerza: eso se aprende
   o se busca. Esconderle el vocabulario no es método socrático — es esconderle
   el diccionario, y lo manda a buscarlo afuera. La línea está en **para qué** se
   nombra: dar el nombre y seguir preguntando, sí; escribir el bloque armado, no.
3. **Sección nueva "Abrir el lazo"** — la entrada del método, con cómo detectar
   que el alumno no tiene de dónde agarrarse y qué hacer entonces, incluida la
   regla de que el ejemplo sea **de otro dominio** y no del ejercicio.
4. **Sección nueva "Usar el material del ejercicio"** — el banco y las
   misconceptions pasan de media oración a sección propia, con el **test de la
   pregunta genérica**: *si le cambiás el tema y sigue funcionando, es una
   plantilla*. Y aclara qué significa "no revelar" (no le muestres el material)
   contra lo que no significa (no lo uses).
5. **Crédito parcial en "Cerrar el lazo"**, que hoy es binario. Falta el caso de
   *"acertaste en dos cosas, te falta esta tercera"* — que en primer año es el
   más común, porque casi nadie trae el razonamiento completo de una.

## El sexto cambio, que no es sobre la pregunta

Se agregó después, cuando el implementador detectó que el borrador traía
párrafos sobre el portapapeles que no estaban entre los cinco cambios. Al
verificarlo apareció un defecto vivo en el prompt que corre en producción.

`main` habilitó el pegado interno (commit `9a7206a`, *"copiar y pegar el propio
código adentro del editor"*). v1.8.0 dice **dos** cosas sobre eso:

1. *"en esta plataforma **copiar y pegar está bloqueado**, así que 'copiátelo a
   VS Code y después lo pegás'… no se puede ejecutar"* — la **premisa** quedó
   falsa (adentro del editor sí se puede), aunque la **conclusión** sigue siendo
   cierta: el `Ctrl+C` del editor no escribe en el portapapeles del sistema.
2. *"la plataforma **no permite copiar y pegar en el editor**"* — esta es
   directamente falsa. El título del propio commit que la invalidó dice
   "adentro del editor".

Quien mergeó el cambio argumentó que v1.8.0 seguía siendo verdadero, y **tenía
razón sobre la frase que citó** — la 1, por su conclusión. Su argumento **no
cubre la 2**.

**No es prolijidad.** Es el defecto que la v1.7.0 cerró con C5: el tutor afirmó
una regla de la plataforma que estaba mal, el alumno lo contradijo, y el tutor
cambió de postura sin corregirse. La regla que quedó fue *"él tiene el dato y
vos no"*. Un estudiante descubre que esta frase es falsa la primera vez que
aprieta `Ctrl+C` adentro del editor, y desde ahí deja de creerle al resto de lo
que el tutor le diga sobre la plataforma.

**Lo que NO se debilita:** el código sigue sin salir del editor —
`portapapelesInternoRef` es una variable en memoria y el código de
`CodeEditor.tsx` declara que no escribe al clipboard del SO. Así que el consejo
"llevátelo afuera" sigue siendo inejecutable, y pedirle al estudiante que pegue
su código en el chat sigue siendo un callejón sin salida. **Cambia el motivo, no
la conclusión ni la política.**

## La evidencia

Está en [`ab-test.md`](ab-test.md): tres brazos, el mismo ejercicio con todo su
material, las mismas cinco preguntas en el mismo orden, criterios fijados por
escrito antes de ver cada respuesta.

**Lo que sostiene:** v1.7.0 reproduce la queja del alumno casi textual; "Abrir el
lazo" produce un comportamiento que los otros brazos no tienen; "una sola
pregunta" se cumple y se cuenta (3 contra 1); no hay regresión de "Cerrar el
lazo"; la regla nueva de nombrar la herramienta no pisa las
`instrucciones_adicionales` del ejercicio; y el crédito parcial es un hueco real.

**Lo que NO sostiene, y hay que leerlo antes de aprobar:**

- **El A/B validó el paquete de cuatro cambios, no cada uno por separado.** En
  particular, el cambio 4 no se puede atribuir nada: el brazo intermedio ya usaba
  las misconceptions sin que el prompt se lo pidiera.
- **n = 1 por brazo**, y la pregunta 1 demuestra que la varianza del modelo es
  del tamaño de algunas diferencias observadas.
- **El modelo del A/B no es el de producción** (Sonnet contra `gpt-4o-mini`). La
  predicción es que en producción la diferencia sea mayor, porque un modelo
  fuerte compensa un prompt flojo — pero es una predicción.
- **El borrador perdió algo:** fue el único que no apuntó a un bug que el banco
  no anticipaba.

## Lo que queda afuera

**Las referencias al material de cátedra**, que un alumno pidió explícitamente.
No se arregla con el prompt:

- El RAG está **apagado a propósito** (`RAG_ENABLED=false`). El motivo está en
  `config.py`: la API de embeddings se cortó dos veces (429 el 2026-08-28, 402 el
  2026-09-22) y el fail-soft pagaba ~3s de backoff por mensaje esperando una API
  ya muerta.
- El propio comentario de ese flag dice *"apagarlo pierde las CITAS, no la
  clase"* — y las citas son justo lo que el alumno pide.
- Encima, el cliente del tutor **descarta** la página y la sección al parsear la
  respuesta del content-service, el prompt **prohíbe citar** textualmente, no
  existe campo de URL al campus en ningún modelo, y el frontend renderiza la cita
  como texto plano sin link.

Cuatro capas, más una decisión de costo. Change aparte, si alguna vez se decide
prender el RAG.

**Y una aclaración que esta change sí necesita:** el tutor **no está a ciegas**
sin RAG. Enunciado, rúbrica, casos de prueba, banco socrático N1–N4 y
misconceptions llegan al modelo por otras vías. Tiene con qué preguntar algo
concreto y pregunta *"¿cómo empezarías?"* igual — por eso esto es un arreglo de
prompt y no un desarrollo.

## El bloqueante, que no es técnico

**La revisión coautoral de Ana Garis.** Esta versión cambia el método —le agrega
la entrada, igual que la v1.5.0 le agregó la salida— así que la revisión es
condición y no formalidad.

Y hay deuda acumulada: **v1.8.0 está en `main` y en `config.py` sin su revisión
cerrada**. Esta sería la segunda esperando.

**`config.py` y el manifest raíz NO se tocan en esta change.** La versión viaja
en el repo, desactivada, y se activa cuando la revisión cierre. Eso es
deliberado: en la change del portapapeles se activó una versión sin revisar y el
header del prompt afirmaba lo contrario, lo que convirtió al prompt en algo que
le mentía al modelo sobre su propio estado.

## Cómo se sabe que funcionó

- Los cuatro movimientos, los nueve principios y "Cerrar el lazo" (salvo el
  agregado del crédito parcial) **byte a byte idénticos a v1.8.0**, afirmado por
  un test y no por la revisión.
- El manifest declara el sha256 real del archivo (el governance-service lo
  verifica fail-loud al cargar).
- `config.py` y `ai-native-prompts/manifest.yaml` siguen en v1.8.0, y el header
  del prompt **dice eso mismo** — afirmado por un test, porque los 21 tests que
  existen hoy no comparan lo que el header afirma contra lo que `config.py` hace.
