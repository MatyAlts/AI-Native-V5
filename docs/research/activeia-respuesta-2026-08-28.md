# Respuesta de AI-Native a Active-IA

**De:** equipo de AI-Native (tutor.active-ia.com)
**Para:** equipo de Active-IA (api.active-ia.com)
**Fecha:** 28 de agosto de 2026
**Responde a:** su documento del 27/08 sobre los §4.1 y §4.2

---

> **Lo más importante primero, porque es la respuesta a su pregunta y no es la que esperan:** el
> `id` de un caso **público** sí es el de la definición del TP. El de un caso **oculto no**, y es a
> propósito — se lo reescribimos antes de mandárselo. Está en el §3, con la salida que proponemos.

---

## 1. §4.1 — Gracias por adaptarse, y tienen razón en el argumento

Aceptamos: `salida_obtenida` queda.

El argumento con el que lo justificaron es el correcto, y es mejor que el nuestro:

> Tocarlos para que coincidan con un documento que estaba mal es arreglar el artefacto equivocado.

Ese documento ya está corregido de nuestro lado (`activeia-cambios-pedidos.md` §3.4), con una nota
de por qué estaba mal, para que el próximo que lo lea no rearme el mismo parser.

### Y su lección del episodio nos aplica igual

> Cada capa nuestra se probaba con su propio diccionario inventado, y las dos estaban de acuerdo
> entre ellas y equivocadas respecto de ustedes. Dos tests verdes tapando el agujero.

Nos pasó lo mismo, en el mismo camino y el mismo día. Auditando encontramos que **nuestro
`_mapear` leía cuatro claves que nuestro propio sandbox no emite**: buscaba `compile_error`,
`test_results`, `passed` por caso y `actual`, cuando el productor emite `outcome`, `cases`,
`status` y `got`.

Ni una coincidía. Y el efecto era peor que el suyo:

> **Toda corrección de producción les mandaba el mismo objeto**, sin excepción:
> `{"compila": true, "error_compilacion": null, "total": 0, "pasados": 0, "casos": []}`
>
> Un alumno cuyo Java **no compila** viajaba como `compila: true`.

O sea que la sección de resultados que el §3.4 existe para darles **nunca llevó un dato real**. Y
tampoco tuvimos un error: la función no encontraba `compile_error`, así que salía por el camino
feliz. Ya está corregido.

Lo decimos porque cambia cómo leer lo que probaron hasta ahora: si vieron correcciones donde el
motor no podía explicar nada del resultado de ejecución, el dato no les estaba llegando **de los
dos lados a la vez**.

### `es_publico`

Nos parece bien cómo lo resolvieron, y sobre todo **dónde**:

> Filtramos en el código, no pidiéndoselo al motor en el prompt.

Es el mismo criterio con el que nosotros les pedimos que `depende_de_ejecucion` fuera
determinístico y no una instrucción. De un motor que ya demostró no honrar reglas declaradas, una
garantía declarativa no es una garantía.

---

## 2. §4.2 — Hecho, y gracias por el detalle que no preguntamos

Bajamos la cascada. Leemos **`nota` y nada más**.

Y el aviso del string era el que más valía:

> `nota` viaja como string JSON, no como número: `"85.50"`, con comillas.

Lo casteamos **explícito**, y a `Decimal`, no a `float`. Coincidimos con su razón para dejarlo así:
una nota no debería pasar por un float en ningún tramo. `float("8.325")` da `8.324999999999999`, y
eso terminaría escrito en la nota de un alumno.

Su observación de por qué el casteo tiene que ser visible es exactamente la correcta:

> `float("85.50")` funciona, así que un parser puede andar por accidente durante meses.

Hay 11 tests nuevos que fijan el contrato: el string con comillas, un decimal que un float no
representa exacto, el cero como nota legítima, y que los tres nombres viejos **ya no se lean**.
Verificados por reversión — volviendo la cascada, caen 8.

Una `nota` ilegible (vacía, `"N/A"`, `"8,5"` con coma) cae a `SIN_NOTA`, que en nuestro lado es
infraestructura y reintentable, en vez de escribir basura en la fila.

**No lo cambien a número.** Su recomendación es la correcta y el casteo queda de nuestro lado.

---

## 3. Su pregunta sobre el `id` — sí para los públicos, no para los ocultos

Preguntaron:

> ¿El `id` que mandan en el resultado es el mismo `id` que recibieron en la definición del TP?

**Depende del caso, y la diferencia es deliberada.**

### Casos públicos: sí

Va el `id` de la definición, tal cual. La correlación cierra.

### Casos ocultos: no. Se lo reescribimos antes de mandárselo

Nuestro sandbox reemplaza el `id` real por uno sintético y **posicional**: `hidden-1`, `hidden-2`,
según el orden de corrida. El comentario del código dice por qué:

> El id se reemplaza: el real puede aparecer en la rúbrica o en el JSON de importación del docente.

Es la misma decisión que ya conocen del §3.3.1 —de un caso oculto sólo mandamos lo mínimo— llevada
al identificador. Junto con el id se va el nombre, la entrada, la salida esperada, la obtenida y
hasta el error: cualquiera de esos permite reconstruir qué prueba el caso.

### Y hay algo peor, que conviene decir antes de que lo descubran

**El contador es posicional sobre el orden de corrida.** No es sólo que el id no sea el suyo: es
que `hidden-2` no identifica establemente al mismo caso entre dos corridas si el orden cambia.
Correlacionar por posición sería peor que no correlacionar, porque fallaría en silencio y en el
sentido más caro: describiendo el caso equivocado en la devolución de un alumno.

**Sobre la aclaración que hicieron.** Dicen que es seguro por construcción porque su schema rechaza
un caso oculto que traiga `salida_esperada`. Es cierto y está bien, pero cubre el canal de
publicación, no éste: lo que protegemos acá no es lo que ustedes almacenan —eso ya lo tienen—, es
que el **identificador que viaja en el resultado** no permita cruzarlo. Ese es el canal que
quedaría abierto si les mandáramos el id real.

### Lo que proponemos, si les sirve

Podemos mandar un **token opaco y estable por caso oculto**: un hash de `(ejercicio_ref, id_real)`
con un salt del tenant. Propiedades:

- **Estable** entre corridas, así que la correlación de su lado cierra siempre.
- **Opaco**: no permite reconstruir el caso desde el resultado, ni siquiera sabiendo el algoritmo,
  sin el salt.
- **Ustedes lo pueden precomputar** al publicar el TP, porque ahí tienen el `id_real` — y así
  correlacionan sin que nosotros mandemos nada más de lo que mandamos hoy.

Es un campo nuevo, no toca el contrato existente. **Díganos si les sirve y lo implementamos**, o si
prefieren empezar correlacionando sólo los públicos, que hoy ya funciona sin tocar nada.

---

## 4. Qué queda de cada lado

| Quién | Qué |
|---|---|
| **AI-Native** | ✅ Cascada de la nota bajada, `nota` casteado explícito a `Decimal`, 11 tests |
| **AI-Native** | ✅ `_mapear` corregido — les llegaba un objeto vacío en toda corrección |
| **AI-Native** | ✅ Documento de pedido corregido en el §3.4 |
| **Ambos** | ⬜ Decidir si va el token opaco para correlacionar los casos ocultos (§3) |
| **Ustedes** | ⬜ La **cuenta de coordinador** — sigue siendo el freno real de todo esto |

**Sobre lo último**: seguimos sin poder correr una sola corrección contra ustedes. Todo lo que
verificamos de este lado está probado contra un doble HTTP escrito leyendo sus documentos. Eso
atrapa nuestros errores —atrapó varios— pero no prueba que la integración funcione entre las dos
puntas.

Y este intercambio es la mejor prueba de por qué hace falta: los dos equipos teníamos un bug en el
mismo camino, los dos con los tests en verde, y ninguno de los dos lo vio hasta que el otro miró.
