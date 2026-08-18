# Active-IA — cambios necesarios para integrar la corrección con AI-Native

**Para:** el equipo que mantiene `api.active-ia.com`
**De:** AI-Native (plataforma del tutor socrático N4, `tutor.active-ia.com`)
**Fecha:** 2026-08-18

---

## 1. Qué se quiere construir

En AI-Native, un alumno resuelve un Trabajo Práctico compuesto por **N ejercicios**. Cada
ejercicio tiene su propio enunciado, su propia rúbrica y sus propios casos de prueba, y el alumno
escribe el código en un editor dentro de la plataforma.

Queremos que el **docente** —no el alumno— pueda apretar un botón y que Active-IA corrija esa
entrega **ejercicio por ejercicio**, devolviendo nota y desglose por cada uno. El resultado lo ve
solo el docente, que decide qué hacer con eso. La nota final la sigue cargando una persona.

---

## 2. Lo que hoy no alcanza

Estas tres cosas están verificadas contra la API en vivo (2026-08-17):

### 2.1 El modelo es plano: una rúbrica por unidad

```
materia → unidad → rubrica_id
```

Nosotros necesitamos corregir **por ejercicio**, y un TP tiene cuatro. Con el modelo actual, los
cuatro ejercicios de un TP tendrían que compartir una sola rúbrica, o habría que crear cuatro
unidades artificiales que no representan nada real.

**Por qué importa y no es capricho:** juntar los cuatro ejercicios en un solo envío activa un modo
de fallo que ya está medido en el motor — *distingue presencia, no vínculo*. Con cuatro ejercicios
en el mismo archivo, una pieza del ejercicio 3 puede contar como cumplimiento de un criterio del 1.
Corrigiendo de a uno, eso desaparece.

### 2.2 El cruce depende de `cmid`, y nosotros no tenemos Moodle

El resolver actual cruza unidades por `cmid` (el `assign_id` de Moodle). **AI-Native no es Moodle
y no tiene `cmid` en ninguna parte** — verificado: cero ocurrencias en todo el monorepo.

Hoy eso deja el 100% del mapeo en manos de un archivo manual del tutor
(`~/.moodle-skill/activeia_rubricas.json`), lo cual para nosotros no escala: los ejercicios los crea
el docente desde la plataforma y pueden ser decenas.

### 2.3 No hay escritura de rúbricas, y el rol tutor no alcanza

```
GET  /rubricas/?materia_id=N     funciona con rol tutor
GET  /rubricas/{id}              403 — "Se requiere rol de coordinador o administrador"
POST /rubricas/                  no existe
```

Las rúbricas de nuestros ejercicios ya están escritas en AI-Native, criterio por criterio con su
puntaje. Queremos empujarlas, no volver a cargarlas a mano del otro lado.

---

## 3. El cambio pedido

### 3.1 Un nivel de "ejercicio" debajo del TP

```
materia
  └── trabajo_practico          (lo que hoy es "unidad")
        └── ejercicio           ← NUEVO
              ├── rubrica       criterios con puntaje
              ├── test_cases    los casos con su entrada y salida esperada
              └── peso          peso relativo dentro del TP
```

Un ejercicio es la **unidad de corrección**: se corrige contra su rúbrica y devuelve su nota.

### 3.2 Identificador externo propio, en lugar de `cmid`

Que `trabajo_practico` y `ejercicio` acepten un campo `external_ref` (string, único por materia),
donde AI-Native pone su propio UUID. Toda la integración cruza por ahí y **`cmid` deja de ser
necesario** para los clientes que no vienen de Moodle.

Esto no rompe nada existente: `cmid` sigue funcionando para el flujo de Moodle.

### 3.3 Endpoints de escritura

```
POST   /trabajos-practicos/                crea el TP con sus ejercicios anidados
PUT    /trabajos-practicos/by-ref/{ref}    crea o actualiza por external_ref (idempotente)
GET    /trabajos-practicos/by-ref/{ref}    lo busca por external_ref
```

**El `PUT` por `by-ref` es el que usa AI-Native**, y no `PUT /{id}`: nosotros no
guardamos el id de ustedes hasta después del primer push, así que un `PUT /{id}` haría
que la primera sincronización y las siguientes fueran dos caminos distintos. Con
`by-ref` es siempre la misma llamada, y reenviar el mismo TP actualiza en vez de
duplicar. Sin eso, cada publicación crearía un TP nuevo y el docente terminaría
eligiendo entre diez copias — y elegir mal no da una nota floja: **corrige otra cosa**.

**La respuesta tiene que devolver, por ejercicio, su `external_ref` y su `rubrica_id`.**
Es lo que nos deja saber con qué rúbrica se corrige cada uno. Emparejar por orden o por
título sería adivinar.

Cuerpo del POST, tal como se lo mandaríamos:

```json
{
  "external_ref": "uuid-del-tp-en-ai-native",
  "materia_external_ref": "uuid-de-la-materia-en-ai-native",
  "titulo": "TP 2 JAVA",
  "ejercicios": [
    {
      "external_ref": "uuid-del-ejercicio",
      "orden": 1,
      "titulo": "TP2 E1 - Cupo excedido y persistencia del evento",
      "enunciado_md": "...",
      "peso": 1.0,
      "rubrica": {
        "criterios": [
          { "nombre": "Excepcion propia verificada",
            "descripcion": "CupoExcedidoException extiende Exception, no RuntimeException",
            "puntaje_max": 2 }
        ]
      },
      "test_cases": [
        { "id": "t1", "nombre": "cupo alcanza para todos menos uno",
          "tipo": "stdin_stdout",
          "entrada": "EVT-1\nJornadas\n2\n3\n1001,Ana\n...",
          "salida_esperada": "Inscripto: Ana\n...",
          "es_publico": true },
        { "id": "t3", "nombre": "cupo 1 admite dos personas",
          "tipo": "stdin_stdout",
          "entrada": "...",
          "es_publico": false }
      ]
    }
  ]
}
```

Sobre `materia_external_ref` en lugar de `materia_id`: es el mismo criterio de 3.2. Un id
numérico de Active-IA nos obligaría a mantener de este lado un mapeo de ids ajenos que
vencen sin avisar, que es justo el problema que 3.2 viene a resolver. Mandamos nuestro
UUID de materia y ustedes lo resuelven una vez.

**Los `test_cases` no son para que Active-IA los ejecute** (ver 3.4). Van porque **son parte del
enunciado**: que el caso `t3` espere que pidiendo cupo 1 entren 2 personas le dice al motor cuál es
la regla de negocio. Sin eso, juzga el código sin saber qué se le pidió.

### 3.3.1 Los casos ocultos viajan SIN su salida esperada

Cada caso lleva `tipo` (`stdin_stdout`, `pytest_assert` o `junit_assert`) y `es_publico`.

Los casos con `"es_publico": false` son los **ocultos**: el alumno no los ve, y son
justamente los que codifican las reglas que tiene que inferir. Les mandamos el `id`, el
`nombre` y el `tipo` —para que el motor sepa que existen, cuántos son y qué evalúan— pero
**no la `salida_esperada` ni la `asercion`**.

No es desconfianza, es diseño: el PDF de devolución se le entrega al alumno, y **lo que
no recibieron no lo pueden citar**. Pedirles por escrito que no lo citen sería depender de
que se cumpla un párrafo, y de este motor ya está medido que no honra reglas declaradas
en su propia rúbrica (el 2026-08-17 la rúbrica pedía una penalización del 30% y aplicó 0%).
Un caso oculto que aparezca en una devolución deja de estar oculto para toda la cohorte.

Los `tipo` de assert tampoco viajan como entrada/salida: en ésos el código **es** el
criterio (`assert suma(2,3) == 5`), y mandarlo en `entrada` con la salida vacía haría que
el motor evaluara "el programa funciona" contra una aserción. Va en `asercion`, y sólo si
el caso es público.

### 3.4 La corrección recibe el resultado de los tests ya ejecutados

Esta es la parte más importante del pedido.

**AI-Native ejecuta el código del alumno en un sandbox real** (Docker sin privilegios, Java 21,
sin red, 10s de límite). Sabemos con certeza qué casos pasan y cuáles no, con qué entrada y qué
salió.

**Active-IA lee el código con Gemini.** Los tres modos de fallo documentados del motor salen todos
de eso:

- Le dio 100/100 a una entrega con "3 categorías OK" y "10 productos OK" donde ningún producto
  quedaba vinculado a ninguna categoría — *vio* las piezas.
- Le puso puntaje completo a una "búsqueda" que era `if puntajes[i] == 990` — *leyó* una búsqueda.
- Descuenta puntos por archivos que sí están en la entrega (bug del 2026-08-04, dejó a una alumna
  desaprobada).

**Un test ejecutado no se deja engañar por ninguna de esas cosas.** Entonces:

```
POST /correcciones/ejercicios/{ejercicio_ref}/corregir
{
  "alumno_ref": "pseudonimo-del-alumno",
  "codigo": "...",
  "resultado_tests": {
    "total": 4, "pasados": 4,
    "casos": [
      { "id": "t1", "paso": true,
        "entrada": "...", "esperado": "...", "obtenido": "..." }
    ]
  }
}
```

Y que el motor **use ese resultado como hecho establecido**, no como sugerencia: si los tests
pasan, el código funciona — no hace falta que Gemini lo deduzca. Que se concentre en lo que un test
no puede medir y que es lo que la rúbrica evalúa: si la excepción es verificada o de runtime, si
usó la interfaz o enumeró los tipos concretos, si el encapsulamiento es real.

### 3.5 Cuenta de servicio

Una cuenta con permiso para crear y actualizar TPs y rúbricas de una materia. Hoy el rol tutor no
puede ni leer los criterios de una rúbrica (403).

### 3.6 Borrado por alumno

```
DELETE /alumnos/{alumno_ref}/datos
```

AI-Native tiene un compromiso de anonimización con los alumnos del piloto: si uno pide retirarse,
hay un procedimiento que rota su identificador y borra sus datos. Ese procedimiento tiene que poder
alcanzar también lo que quedó en Active-IA.

---

## 4. Los bugs a corregir

Independientes de esta integración: afectan a todos los que ya usan Active-IA desde Moodle.

| # | Qué pasa | Evidencia |
|---|---|---|
| 1 | **Descuenta puntos por archivos que SÍ están en la entrega.** Dejó a una alumna desaprobada. | Reportado el 2026-08-04 · materia 22 · rúbrica 188 |
| 2 | **No aplica las penalizaciones que la propia rúbrica declara.** El criterio C5 decía "reducción del 30% del total" y la nota final fue la suma limpia: 48+14+15+10+0 = 87, cuando con el descuento daba ~61. | Medido el 2026-08-17 |
| 3 | **El desglose no cierra con sus subcriterios.** En el mismo caso, C5 figuraba 0/10 cuando sus subcriterios sumaban 5. | Medido el 2026-08-17 |
| 4 | **Cuenta presencia, no vínculo.** 100/100 a una entrega donde nada estaba conectado. | Caso control documentado |
| 5 | **Elogia como correcto código hardcodeado.** | `if puntajes[i] == 990` |
| 6 | **Recomienda cosas que la cátedra prohíbe.** Sugirió `try/except` en Programación 1, donde la consigna lo veda y lo repite tres veces. | Documentado |

Los bugs 2 y 3 son los más urgentes después del 1: producen un número plausible y mal, que es peor
que un error visible. **El punto 3.4 de este documento (mandar el resultado de los tests) mitiga
parcialmente los bugs 4 y 5, pero no los reemplaza.**

---

## 5. Lo que NO pedimos

Para acotar el alcance:

- **No pedimos que Active-IA ejecute código.** El sandbox es nuestro y funciona.
- **No pedimos que calcule la nota final del TP.** Devuelve una nota por ejercicio; el promedio
  ponderado lo hacemos nosotros y se lo mostramos desglosado al docente.
- **No pedimos que escriba en ningún lado nuestro.** La integración es de una sola dirección:
  nosotros mandamos, ustedes devuelven.
- **No pedimos cambios en el flujo de Moodle.** `cmid` sigue funcionando igual.
- **No pedimos corrección en lote.** Se dispara de a un ejercicio.

---

## 6. Prioridad, si hay que elegir

1. **Los bugs 1, 2 y 3.** Afectan notas reales hoy, con o sin esta integración.
2. **3.1 + 3.2** — el nivel de ejercicio y el `external_ref`. Sin eso no hay integración posible.
3. **3.3** — los endpoints de escritura.
4. **3.4** — recibir el resultado de los tests. Sin esto la integración funciona, pero hereda los
   modos de fallo del motor.
5. **3.5 y 3.6** — cuenta de servicio y borrado. El 3.6 puede ir después del piloto, pero antes de
   que un alumno lo pida.
