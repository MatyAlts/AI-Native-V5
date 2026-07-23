## Context

Fundación de datos del soporte multi-lenguaje. Todo lo de acá está verificado contra el código real, no derivado del diseño en documento.

Estado actual:

- No existe ningún campo de lenguaje en `Ejercicio` (`apps/academic-service/src/academic_service/models/operacional.py:408`) ni en `TareaPractica` (`:214`).
- `TestCaseSchema.type` admite dos tipos, ambos de Python (`packages/contracts/src/platform_contracts/academic/ejercicio.py:142`).
- `TareaPractica.test_cases` está tipado como lista de diccionarios sueltos y **no reusa** `TestCaseSchema` — acepta cualquier tipo sin validar.
- `publish()` solo verifica que el estado sea borrador (`services/tarea_practica_service.py:216`). Existe `TpEjerciciosValidator` (`ejercicio.py:263`) escrito para validar composición y **nunca se invoca**.
- El banco de ejercicios es reusable entre TPs mediante una relación de muchos a muchos, sin ninguna restricción que impida mezclar.

Restricción que gobierna el diseño: **el núcleo de la tesis no se toca**. Verificado que el clasificador no parsea código (cero uso del módulo de análisis sintáctico en `apps/classifier-service/src/`) y que su hash de configuración depende solo de la versión del árbol y del perfil de referencia (`services/pipeline.py:40-56`), sin incluir eventos ni payloads.

## Goals / Non-Goals

**Goals:**

- Que el lenguaje sea un atributo de primera clase del banco de ejercicios y de las TPs.
- Que el banco se pueda filtrar por lenguaje.
- Que una TP no pueda publicarse mezclando lenguajes, ni vacía, ni con pesos inconsistentes.
- Que nada de esto altere la trazabilidad ni la reproducibilidad de la tesis.

**Non-Goals:**

- **No tocar ninguna interfaz.** El campo viaja por la API y ninguna UI lo consume todavía.
- **No ejecutar Java.**
- **No unificar el tipado de casos de prueba** entre ejercicio y TP. Es un refactor con radio propio.
- **No revalidar retroactivamente** las TPs ya publicadas.

## Decisions

### D1 — El lenguaje vive en el ejercicio y en la TP, no en la materia ni en la unidad

**Descartada la materia**: es la plantilla atemporal del plan de estudios. Una misma materia puede dictarse en un lenguaje en una comisión y en otro en otra del mismo período — el modelo ya soporta varias comisiones por materia sin acoplamiento de lenguaje. Ponerlo ahí acopla currícula con implementación.

**Descartada la unidad**: es operacional y efímera, agrupa TPs dentro de una comisión. No tiene ninguna relación con los ejercicios — no hay clave foránea entre ellos, y el campo de unidad temática del ejercicio es texto libre sin vínculo con esa tabla. Son dos conceptos con nombre parecido y cero relación.

**Elegidos ejercicio y TP**: ambos ya tienen código inicial (el andamiaje, que hoy asume Python) y casos de prueba (el artefacto ejecutable). Los dos dependen enteramente del lenguaje. La TP monolítica lo necesita porque lleva su propio código y casos sin componerse del banco.

### D2 — Sin restricción de valores en la base; el conjunto admitido vive en el contrato

Hay precedente para las dos posturas y gana el más reciente: una migración de junio **eliminó** la restricción de valores del campo de unidad temática para hacerlo texto libre, con el argumento de que cada materia define los suyos.

Una restricción cerrada obliga a una migración por cada lenguaje futuro. La validación vive en el contrato, que ya es el punto de control real de la API.

### D3 — Valor por omisión en la base, sin relleno posterior

El motor completa las filas existentes en la misma sentencia de alteración de tabla. El banco es enteramente Python hoy, así que el valor por omisión es semánticamente correcto y no un marcador de posición. Evita el patrón de tres pasos: nulo, actualizar, exigir no nulo.

Sigue el patrón de una migración previa que agrega una columna a una tabla que **ya tiene aislamiento por inquilino activo** — no requiere política nueva ni índice adicional. Solo las tablas nuevas necesitan habilitar y forzar el aislamiento junto con su política.

### D4 — El tipo de caso de prueba nuevo va en dos lugares, no en uno

En el contrato tipado es un cambio de una palabra. Pero el campo equivalente de la TP está tipado como lista de diccionarios sueltos, tanto en el modelo como en el esquema, y hoy acepta cualquier tipo sin validar. Las TPs monolíticas pasan por ahí.

Esta change no unifica los dos caminos, pero sí aplica el conjunto de tipos admitidos en ambos.

### D5 — La validación de composición se engancha en dos puntos

Al publicar como red final, y al agregar un ejercicio como bloqueo temprano.

Solo al publicar sería tarde: el docente compone una TP entera mezclando lenguajes y se entera al final. El método que agrega un ejercicio ya carga el ejercicio real, así que tiene el lenguaje sin consultas adicionales.

### D6 — El validador recibe los ejercicios resueltos, no solo sus identificadores

Hoy valida sobre la entrada de creación de la asociación, que solo tiene identificador, orden y peso. La regla de un único lenguaje **no se puede expresar con esa entrada**.

| Opción | Intercambio |
|---|---|
| Agregar el lenguaje a la entrada de creación | Contamina el formato de entrada con un campo derivado; el cliente podría mentir |
| **El validador recibe los lenguajes ya resueltos** ✔ | El servicio resuelve, el validador valida. El dato sale de la base |

### D7 — Consulta explícita al validar, nunca la relación diferida

El repositorio no hace carga anticipada de la relación de ejercicios. El propio código que crea una versión nueva de una TP documenta que iterar esa relación diferida falla en el controlador asíncrono, y por eso ahí resuelve con una consulta explícita.

La validación replica ese patrón. Preguntar directamente por la relación parece natural y falla en tiempo de ejecución.

### D8 — La regla de "no vacía" es nueva, no sale gratis del validador existente

El validador arranca retornando conforme si la lista de ejercicios está vacía. Engancharlo tal cual no cierra el defecto de la TP vacía.

Y la regla correcta no es "tiene ejercicios" sino "tiene ejercicios **o** casos de prueba propios": una TP monolítica legítima no tiene asociaciones con el banco.

### D9 — La regla de suma de pesos NO se adopta

El validador existente exige que los pesos de los ejercicios sumen 1.0. Esa regla queda fuera.

Medición contra la base del piloto, previa a escribir código:

| Dato | Valor |
|---|---|
| Asociaciones ejercicio–TP con peso `1.0000` | **169 de 169** |
| TPs publicadas cuya suma de pesos ≠ 1.0 | **25 de 27** |
| TPs que cumplen la regla | 2 — ambas con **un único ejercicio**, o sea por accidente |
| Cálculos de calificación que consumen el campo | **ninguno** |

El origen del dato es el formulario del docente, que propone `1.0` y nadie modifica. No hay una convención de "pesos como unidades absolutas" pensada por alguien: hay un valor por defecto que quedó.

Aplicar la regla habría impedido republicar prácticamente todas las TPs del piloto, para proteger la consistencia de un número que no participa de ningún cálculo.

**Alternativa descartada — migrar los datos a fracciones (1/N)**: tocar 169 filas de producción del piloto en curso para satisfacer una regla que nadie usa. Riesgo sin beneficio.

**Alternativa descartada — reescribir la regla como "pesos relativos, normalizados al calificar"**: es la lectura correcta de los datos y probablemente el diseño deseable. Pero exige implementar la ponderación en el servicio de evaluación, que hoy ignora el campo por completo. Es un cambio de producto, no de soporte multi-lenguaje.

## Risks / Trade-offs

**Fallo del controlador asíncrono al validar** → D7: consulta explícita, con un test que cubra ese camino específico.

**TPs publicadas que ya violan las reglas nuevas** → **Medido el 2026-07-23, antes de escribir código.** Con la regla de pesos incluida, 25 de 27 TPs publicadas habrían quedado sin poder republicarse. Retirada esa regla (D9), ninguna TP del piloto viola las reglas restantes: todas tienen órdenes únicos, ejercicios sin repetir y contenido. El riesgo queda en cero, no mitigado sino eliminado.

**El valor por omisión queda pegado al esquema** → Se puede quitar tras agregar la columna. Decisión: dejarlo. Que un ejercicio nuevo sin lenguaje explícito sea Python es razonable mientras Python sea el lenguaje principal del piloto.

**Divergencia entre el repositorio y la base de producción** → La migración se escribe idempotente desde el día uno, verificando la existencia de la columna antes de agregarla. No es paranoia: ya se encontró una columna agregada a mano en producción, salteándose el sistema de migraciones, y no se sabe cuánta divergencia más hay.

## Migration Plan

1. Contratos: campo de lenguaje, tipo de caso de prueba nuevo, reglas del validador. Sin efecto en runtime hasta que los servicios los usen.
2. Modelo y migración, idempotente.
3. Esquemas y endpoints: el campo viaja, el filtro funciona.
4. Validación de composición enganchada en los dos puntos.

Los pasos 1 a 3 son aditivos y no cambian ningún comportamiento existente. El paso 4 es el único que puede rechazar algo que antes pasaba.

**Rollback**: revertir el paso 4 restaura el comportamiento permisivo sin dejar datos inconsistentes. La columna puede quedarse sin efecto adverso.

## Open Questions

**¿Conviene unificar el tipado de casos de prueba entre ejercicio y TP?** Fuera de alcance acá, pero la duplicación va a seguir costando cada vez que se agregue un tipo. Vale un refactor propio.

## Hallazgos fuera de scope

Descubiertos midiendo la base antes de escribir código. Ninguno es de soporte multi-lenguaje; los tres necesitan dueño.

**1. `peso_en_tp` es decorativo.** Se guarda, se transporta, se muestra — y ningún cálculo lo consume. O se implementa la ponderación en la calificación, o se retira el campo. Tenerlo a medias es peor que cualquiera de las dos: sostiene la ilusión de que las notas se ponderan.

**2. La vista del alumno muestra "Peso: 100%" en cada ejercicio.** El componente que lista los ejercicios de una TP renderiza el peso como porcentaje. Con todos los pesos en `1.0`, un TP de diez ejercicios muestra diez veces "Peso: 100%". Está en producción hoy. No rompe nada y le miente al alumno.

**3. El formulario del docente propone `1.0` como peso por defecto.** Es la causa raíz de los otros dos. Cualquier decisión sobre el campo tiene que empezar por acá.
