# Veredicto de revisión

Un implementador, un QA que no tocó producción, y el orquestador después. Queda
acá para que se archive con la change.

## El manifest no parseaba — y la gravedad que se le atribuyó era falsa

El `manifest.yaml` de v1.9.0 se commiteó siendo **YAML inválido**. Seis `": "`
dentro de escalares planos lo rompían — notas en prosa del tipo *"dijeron la
misma cosa de cuatro formas: le preguntan al tutor…"*. Los manifests de v1.5.0 a
v1.8.0 son todos válidos; este era el único roto. **Ese dato es cierto** y lo
verificaron por separado el orquestador y el auditor.

### La corrección, y es sobre lo que el orquestador escribió

La primera versión de este documento, el mensaje del commit `11bcff9` y un
comentario en el PR afirmaban que **el governance-service parsea este archivo al
cargar el prompt, que el parseo revienta, y que
`POST /api/v1/episodes` devuelve 500 dejando a los estudiantes sin poder abrir un
episodio**.

**Es falso.** Lo encontró el auditor leyendo el código en vez de la prosa que lo
describía:

- `PromptLoader._declared_hash()` es un parser de **líneas** hecho a mano. Su
  propio docstring lo dice: *"parseo minimal para no depender de PyYAML"*. Busca
  la clave `files:` y después una línea `system.md: <hash>`, y no le importa un
  `": "` dentro de una nota.
- `PromptLoader.active_configs()`, que lee el manifest raíz, hace lo mismo:
  *"Parseo mínimo — en producción reemplazar por PyYAML"*.
- **PyYAML no se importa en ningún lugar de `governance-service`.**

El auditor lo verificó ejecutando `_declared_hash()` contra el manifest roto tal
como estaba commiteado: devuelve el hash, sin excepción. El orquestador lo
reprodujo después, leyendo las dos funciones.

Así que el riesgo era **latente, no activo**. Lo que vale, y es bastante menos:

1. El archivo declara ser YAML y no lo era. Cualquier consumidor que lo lea con
   un parser de verdad revienta.
2. **El código dice que ese cambio está planeado** — el comentario de
   `active_configs` es literalmente *"en producción reemplazar por PyYAML"*. El
   día que se reemplace, deja de ser latente.
3. El manifest es el registro de auditoría de cada versión del prompt, y uno que
   no se abre con las herramientas del formato que declara es un registro peor.

### La lección que sí se sostiene

**Los tres lectores leyeron el archivo sin parsearlo:** los tests del prompt
sacan el sha256 con una expresión regular, la revisión de QA usó `rg`, y CI no
valida los YAML del repo de prompts. Que además el servicio tampoco lo parsee es
lo que convirtió un error latente en uno invisible.

Y una lección sobre el propio ciclo: **este hallazgo lo produjo el orquestador
después de que QA terminó, así que nadie lo revisó hasta el auditor.** El dato
era correcto y la consecuencia inventada, y la etiqueta que se le puso fue "el
hallazgo más grave de la change". Un hallazgo propio sin revisor se califica
solo, y se califica de más.

Lo cierra `apps/governance-service/tests/unit/test_manifests_de_prompts_parsean.py`,
sobre **todas** las versiones en disco y no sobre la última: el modo de falla no
tiene nada de particular a v1.9.0, y la próxima versión va a redactar sus notas
en prosa igual que esta. Verificado por mutación — reproduciendo el YAML roto tal
como estaba commiteado, tres tests se ponen rojos.

## La cuarta aserción vacua

`test_el_header_no_omite_que_v180_tambien_la_tiene_abierta` afirmaba
`"v1.8.0" in header`, que es **trivialmente cierto** en cualquier versión
derivada de v1.8.0: la cadena aparece cuatro veces en el header por motivos
ajenos ("Derivado de v1.8.0", "config.py sigue apuntando a v1.8.0", "no cambian
una letra respecto de v1.8.0").

QA lo demostró por mutación: borró la oración que el test dice verificar y el test
quedó en verde.

Es **la cuarta de esta forma en esta change**. Las otras tres se corrigieron en
el archivo del prompt; esta vivía en el archivo hermano y no se volvió a mirar.
Las cuatro:

| Aserción | Por qué pasaba sin medir |
|---|---|
| `"## Abrir el lazo" in texto` | matcheaba como substring dentro de `"### Abrir el lazo"` |
| `"adentro del editor" in texto` | la frase aparece en tres lugares del prompt |
| contexto `"No digas"` | prefijo demasiado estrecho; se puso rojo con una descripción legítima |
| `"v1.8.0" in header` | la versión se menciona cuatro veces por otros motivos |

El patrón es uno solo: **una subcadena corta buscada en un documento largo casi
siempre está, y por otra razón**.

## El manifest omitía el sexto cambio

Documentaba los cambios 1 a 5 y no el de la regla del portapapeles — el más
delicado de los seis, porque toca una regla de plataforma que el tutor venía
afirmando mal en producción. El manifest es el registro de auditoría que usa el
governance-service: una omisión ahí no es un olvido de redacción.

## Lo que QA verificó y cerró limpio

- **La propiedad central**, contra `origin/main` y no contra un test: los cuatro
  movimientos, los nueve principios (contó nueve) y "Cerrar el lazo" salvo el
  agregado quedan **byte a byte** como en v1.8.0.
- **El test de identidad que se acotó** discrimina: una mutación dentro de la
  sección y fuera del párrafo recortado lo pone rojo.
- **Las dos mitades del sexto cambio son ciertas** contra el `CodeEditor.tsx` de
  `main`: el alumno sí puede copiar y pegar adentro del editor, y el código no
  sale — el `Ctrl+C` llena una variable en memoria y no escribe al portapapeles
  del sistema. No se reemplazó una mentira por otra.
- **`config.py` y el manifest raíz** siguen los dos en v1.8.0, y el header del
  prompt lo dice.
- **Las reglas nuevas no se contradicen con las viejas**: el crédito parcial con
  "no confirmar sin razón", "Abrir el lazo" con el Principio 2 y GP2, y
  "nombrar la herramienta" con GP1 y `prohibido_dar_solucion` quedan
  reconciliados explícitamente en el texto.

## Lo que queda abierto, dicho por quien lo dejó

**La prioridad entre "nombrar la herramienta" y las `instrucciones_adicionales`
por ejercicio.** El prompt permite nombrar una herramienta; un ejercicio puede
prohibir nombrar una puntual (y de hecho lo hace: *"NO le digas 'usá while'"*).
El A/B mostró que en ese caso la instrucción del ejercicio ganó — pero fue **un
solo caso**, y el prompt no tiene una regla explícita de prioridad. Declarado en
`ab-test.md` como límite no resuelto.

**"Una sola pregunta por turno" contra la sección Mayéutica**, que hereda intacta
de v1.8.0 y describe una secuencia de cuatro preguntas. QA lo leyó como un punto
gris y no como un defecto: la Mayéutica habla de *"una conversación"*, no de un
turno. Pero el prompt no aclara que esos cuatro pasos se reparten en turnos
distintos, y ni el A/B ni ningún test lo ejercitaron.

**QA no mutó las 32 aserciones una por una.** Hizo mutación dirigida sobre los
puntos más riesgosos y, para el resto, verificó por `rg` que cada frase buscada
aparezca una sola vez en el lugar esperado. Lo declaró como más débil que una
mutación real, y lo es.

**El baseline de "546 antes" no se corrió directamente.** QA intentó con
`git worktree` y falló por entorno (`uv sync` completo, 3-5 min). Lo derivó por
aritmética: la rama no modifica ningún test preexistente, y 578 − 32 = 546.
Declarado como supuesto.

## Dos errores de proceso del orquestador

**`pytest | tail` enmascaró un rojo y se commiteó encima.** El exit code viene
del último comando del pipe. Desde ahí se redirige a archivo y se lee `$?`.

**Segundo PR seguido entregado con el linter sin correr.** En el #105 fue biome,
acá `ruff format`. Los tests y el typecheck estaban verdes y la verificación se
declaró completa igual. Quedó anotado en la memoria del proyecto.
