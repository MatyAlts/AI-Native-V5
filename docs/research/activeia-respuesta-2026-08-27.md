# Respuesta de AI-Native a Active-IA

**De:** equipo de AI-Native (tutor.active-ia.com)
**Para:** equipo de Active-IA (api.active-ia.com)
**Fecha:** 27 de agosto de 2026
**Responde a:** su documento del 24/08 («Está construida. Esto es lo que falta para encenderla»)

---

> **Lo primero, porque cambia el estado de la conversación:** migramos nuestro cliente al
> endpoint del §3.4. Hasta hoy hablábamos el camino viejo —subir un zip, disparar, poletear— y
> eso significa que **el contrato del que ustedes dicen "no cambia" nunca lo habíamos
> implementado**. Ahora sí. Lo explicamos en el §2.
>
> Y de paso encontramos un error **nuestro** en el documento que les mandamos: el detalle por
> caso que describimos en el §3.4 no es el que nuestro código envía. Está en el §4.1 y es lo
> más urgente de este documento si ya escribieron el parser.

---

## 1. Sus cuatro puntos, contestados

| # | Qué pedían | Estado |
|---|---|---|
| 1 | `depende_de_ejecucion` por criterio | **Hecho.** 34 criterios marcados en los 7 ejercicios del piloto (§3) |
| 2 | Personería, por escrito | **[PENDIENTE DE COMPLETAR ANTES DE ENVIAR]** |
| 3 | Confirmar el contrato + ventana de staging | **Confirmado de nuestro lado** (§4), y sí, queremos la ventana |
| 4 | ¿Quién puede pedir una anonimización? | **Sólo un administrador de ustedes** (§5) |

---

## 2. Migramos al endpoint nuevo, y hay un malentendido que conviene deshacer

Su §3.3 dice: *«El contrato que ya implementaron NO cambia. `{alumno_ref, codigo,
resultado_tests}` sigue siendo válido tal cual.»*

**Nosotros nunca implementamos ese contrato.** Lo pedimos en el §3.4 de nuestro documento, pero
el cliente que teníamos escrito hablaba el flujo anterior, que era el único que existía cuando
lo escribimos:

| Lo que hacía nuestro cliente hasta hoy | Lo que hace desde hoy |
|---|---|
| `POST /entregas/` (multipart con zip) → `POST /correcciones/entregas/{id}/corregir` → `GET` cada 5s hasta 150s | `POST /correcciones/ejercicios/{ejercicio_ref}/corregir`, una llamada |

No había nada roto: el camino viejo funciona. Pero lo que ustedes construyeron es lo que
habíamos pedido y es mejor, así que migramos. Con eso desaparecen de nuestro código el zip, todo
el manejo del 409 y todo el polling.

**Confirmamos su §4.2:** no ramificamos por conflicto. Reintentar es exactamente la misma
llamada. Tenemos un test que falla si alguien reintroduce la rama del 409.

### Lo que esta migración arregló de nuestro lado, y que ustedes venían señalando

El «`comision_id` mal cableado» que nos marcaron era peor de lo que parecía, y la causa no era
la que suponíamos.

Nuestra ruta pasaba un parámetro llamado `activeia_comision_id`, pero lo que le pasaba era el
`external_ref` del **ejercicio** — nuestro propio sincronizador escribe ahí el UUID del
ejercicio. O sea que les mandábamos un id de ejercicio en el campo `comision_id`. **El nombre
del parámetro mentía**, y por eso sobrevivió a las revisiones.

El endpoint nuevo lo cierra por construcción: el ejercicio va en la URL, que es su lugar, y no
hay campo de comisión que confundir.

---

## 3. `depende_de_ejecucion` — hecho, y qué criterio usamos

Su explicación del §3.1 nos convenció, incluido el argumento de por qué va determinístico en su
backend y no en el prompt. *«Una garantía declarativa no es una garantía»* es exactamente la
lección del bug 2, y coincidimos.

**Marcados los 34 criterios de los 7 ejercicios del piloto** (TP1 E1-E3, TP2 E1-E4, materia
Paradigmas): **14 en `true`, 20 en `false`**.

La regla que aplicamos, por si les sirve para leer lo que les llega:

> `true` **sólo** si el criterio no se puede juzgar leyendo el código.

Y no lo decidimos con una heurística sobre el texto, aunque escribimos una: el error no es
simétrico. **Marcar de más es peor que no marcar.** Un criterio de diseño marcado como
dependiente se cierra en 0 cada vez que un alumno no compila — o sea le baja la nota por algo que
sí hizo, que es literalmente el modo de falla que fuimos a reportarles. No marcar, en cambio,
sólo deja la garantía apagada. Así que ante la duda va `false`, y cada uno de los 34 lo revisó
una persona.

Los que quedaron en `true` son de dos clases: **formato y salida** («cada línea sale con el
formato exacto pedido», «los tres rótulos con su sangría») y **comportamiento con un valor
concreto** («Charla 0.0, Taller 5000.0 con notebook», «sin confirmar, `getTicket()` da null»,
«el saldo nunca queda negativo»).

Tres que dejamos en `false` y que muestran bien dónde pusimos el límite:

- **«La excepción propia, verificada»** (extiende `Exception`, no `RuntimeException`) — es el
  mismo ejemplo que ustedes usaron en su documento.
- **«Suma polimórfica sin instanceof»** — ningún test puede verificar la *ausencia* de un
  `instanceof`. Sólo se lee.
- **«Wildcard acotado»** y **«Lista efectivamente tipada»** — son propiedades de compilación. Si
  compila, ya están.

También hay cuatro donde la mayor parte se lee y una puntita necesita correr — por ejemplo
*«`inscribir()` la declara y la lanza, con el mensaje exacto»*. Quedaron en `false`: marcarlos
haría que el alumno pierda **todo** el criterio, incluida la parte que sí hizo.

**Sobre el sync:** verificamos que nunca sincronizamos una sola rúbrica con ustedes, así que no
hay nada viejo del otro lado que corregir. **La primera sincronización ya va a llegar con las
marcas puestas.**

---

## 4. El contrato, confirmado contra nuestro doble

Reescribimos nuestro doble HTTP al protocolo nuevo. Es una especificación ejecutable: 19 tests
que fallan si lo que enviamos deja de coincidir con esto.

**Lo que enviamos:**

```json
POST /api/v1/correcciones/ejercicios/{ejercicio_ref}/corregir
{
  "alumno_ref": "<pseudónimo del alumno>",
  "codigo": "...",
  "resultado_tests": {
    "compila": true,
    "error_compilacion": null,
    "total": 4,
    "pasados": 4,
    "casos": [ ... ]
  }
}
```

- **`ejercicio_ref` es el mismo `external_ref`** con el que ese ejercicio quedó vinculado en el
  último sync. Lo leemos del vínculo guardado, no lo re-derivamos.
- **No mandamos `comision_external_ref`.** Su comisión de integración es la respuesta correcta
  para nosotros; mandarles un id de comisión que ustedes no conocen sería peor que no mandar
  nada. Si algún día modelamos cohortes, avisamos antes.
- **`alumno_ref` es un pseudónimo**, nunca el nombre ni el legajo del alumno.

### 4.1 Corrección a NUESTRO documento: el detalle por caso no es el que les describimos

Esto es un error nuestro y es el punto más accionable de esta respuesta.

El §3.4 de nuestro documento mostraba los casos así:

```json
{ "id": "t1", "paso": true, "entrada": "...", "esperado": "...", "obtenido": "..." }
```

**Nuestro código no envía eso.** Envía esto:

```json
{ "id": "t1", "nombre": "suma de dos enteros", "paso": true,
  "salida_obtenida": "...", "es_publico": true }
```

Tres diferencias, y las tres tienen motivo:

| Campo | Qué pasó |
|---|---|
| `obtenido` → **`salida_obtenida`** | Nombre distinto. Si armaron el parser leyendo nuestro documento, este campo les llega vacío y el motor pierde la salida real del alumno — que es justamente el hecho que el §3.4 existe para darles. |
| `entrada` y `esperado` | **No los mandamos, a propósito.** Es la misma decisión que ya compartimos sobre los casos ocultos: lo que no reciben no lo pueden citar. Nuestro documento los mostraba por descuido. |
| `nombre`, `es_publico` | Los agregamos y no estaban documentados. `es_publico` les dice si ese caso puede citarse en la devolución al alumno. |

**Nos avisan qué prefieren:** podemos renombrar `salida_obtenida` a `obtenido` de nuestro lado en
una línea, o lo dejan como está y ajustan el parser. Nos da igual; lo que no da igual es que
quede sin decidir.

### 4.2 Una pregunta sobre la respuesta

Su documento describe el pedido en detalle pero no el nombre del campo de la nota. Hoy leemos
`nota_100` y, si no viene, probamos `nota`, `nota_final` y `calificacion`. **Confírmennos cuál
es** y dejamos uno solo: esa cascada de alternativas es exactamente el tipo de cosa que
funciona hasta que un día devuelve el campo equivocado.

Lo que sí tomamos como confirmado de su §3.2:

- `criterios_sin_ejecucion` viene como lista aparte. **Ya lo mostramos distinto** en el panel del
  docente: esos criterios dicen «sin verificar» en lugar de su puntaje, con la aclaración de que
  el cero no significa que el alumno no lo haya hecho. Tenían razón en que merecen leerse
  distinto.
- La respuesta **no trae nota agregada del TP**. El promedio ponderado lo hacemos nosotros, con
  el cálculo a la vista del docente.

### 4.3 La ventana de staging: sí, y cuanto antes

Queremos apuntar el cliente a su staging antes de producción, por el mismo motivo que ustedes:
preferimos que una diferencia aparezca ahí.

**Aceptamos la cuenta de coordinador acotada** mientras la de servicio no exista, con las contras
que declararon entendidas y aceptadas: que caduca, que no se revoca sola, y que en la auditoría
las acciones figuran como de una persona. Que sea temporal está claro de los dos lados.

**Por qué canal recibimos la credencial: [PENDIENTE DE COMPLETAR ANTES DE ENVIAR]**

---

## 5. Quién puede pedir una anonimización

**Sólo un administrador de ustedes.** Pedido manual, no automatizado desde nuestro sistema.

Es más lento, y lo elegimos igual: un borrado irreversible de datos de un alumno debería tener
una persona identificable que lo autorizó y quede en su auditoría. Un procedimiento automático
nuestro disparándolo del otro lado deja el rastro del lado equivocado — y en un piloto que
sostiene una tesis sobre trazabilidad, sería incoherente pedir auditabilidad para todo menos
para el borrado.

### Sobre la limitación que declararon

Agradecemos que hayan dicho de frente que la anonimización cubrirá la base viva y no los
respaldos históricos, y que hayan señalado ustedes mismos que eso afecta el alcance del
compromiso que firmamos con los alumnos.

**Lo llevamos a la dirección del proyecto junto con el punto 2.** Si hace falta que los respaldos
queden cubiertos, volvemos con una propuesta de política de retención en vez de pedirles algo
sin haberlo pensado.

---

## 6. Lo que queda abierto, de los dos lados

| Qué | De quién | Bloquea |
|---|---|---|
| Personería por escrito | Nuestro | Encender con datos de alumnos reales |
| Canal de entrega de la credencial | A definir entre los dos | Que nos la puedan mandar |
| Confirmar el nombre del campo de la nota (§4.2) | Suyo | Sacar la cascada de alternativas |
| Decidir `salida_obtenida` vs `obtenido` (§4.1) | A definir entre los dos | Que la salida real del alumno les llegue |
| Cuenta de servicio (§3.5) | Suyo | Probar con identidad de máquina |
| Borrado por alumno (§3.6) | Suyo | Cerrar nuestro procedimiento de olvido |

---

## Cierre

Su documento del 24/08 llegó con el estado de cada punto y con el razonamiento detrás de las
decisiones, no sólo con el resultado. Eso es lo que nos permitió migrar el cliente en un día en
vez de descubrir las diferencias contra producción — y de paso encontrar dos errores nuestros
que no habríamos buscado: el `comision_id` que era un id de ejercicio, y el detalle por caso que
documentamos distinto de como lo mandamos.

Quedamos esperando el §4.1 y el §4.2, que son los dos que necesitan una respuesta de ustedes
antes de la primera corrida contra staging.
