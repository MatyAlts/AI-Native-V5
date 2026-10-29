## ADDED Requirements

### Requirement: El listado de entregas identifica las re-entregas
Cada entrega devuelta por el listado y por la lectura individual SHALL informar `es_reentrega`, que es verdadero si y sólo si la entrega está en `submitted` y ya tiene una calificación vigente (no borrada). El dato SHALL derivarse al leer, sin columna ni migración nuevas, y sin una consulta adicional por entrega.

#### Scenario: Entrega nueva
- **WHEN** el alumno entrega por primera vez y el docente lista las entregas
- **THEN** esa entrega viene con `es_reentrega=false` y `nota_final=null`

#### Scenario: Re-entrega
- **WHEN** el docente calificó, devolvió, y el alumno volvió a entregar
- **THEN** la entrega viene en `submitted` con `es_reentrega=true` y `nota_final` igual a la nota anterior

#### Scenario: Re-entrega ya corregida
- **WHEN** el docente re-califica esa re-entrega y la entrega pasa a `graded`
- **THEN** la entrega viene con `es_reentrega=false` (ya no está pendiente)

#### Scenario: Devuelta todavía sin re-entregar
- **WHEN** la entrega está `returned`
- **THEN** viene con `es_reentrega=false`

### Requirement: Filtro de re-entregas en el listado
El listado de entregas SHALL aceptar un filtro opcional `reentrega`. Con `reentrega=true` SHALL devolver sólo las entregas con `es_reentrega=true`; con `reentrega=false`, sólo las que no lo son; sin el parámetro, el comportamiento SHALL ser el de hoy. El filtro SHALL aplicarse en la consulta, de modo que la paginación por cursor devuelva páginas completas de lo pedido, y SHALL respetar el aislamiento por comisión del docente.

#### Scenario: Sólo re-entregas
- **WHEN** el docente pide `GET /entregas?comision_id=X&reentrega=true` y la comisión tiene 3 entregas nuevas y 2 re-entregas
- **THEN** recibe exactamente las 2 re-entregas

#### Scenario: Comisión ajena
- **WHEN** un docente pide `reentrega=true` sobre una comisión donde no está asignado
- **THEN** no recibe entregas de esa comisión

#### Scenario: Sin parámetro
- **WHEN** el docente lista sin `reentrega`
- **THEN** recibe las mismas entregas que antes de este cambio

### Requirement: La lista de Correcciones distingue las re-entregas
La lista de entregas de la vista Correcciones del web-teacher SHALL mostrar un badge "Re-entrega" con la nota anterior en cada entrega con `es_reentrega=true`, y SHALL ofrecer un control "Sólo re-entregas" que se combine con el filtro por estado y la búsqueda por alumno. La corrección por lote de pendientes SHALL respetar ese control.

#### Scenario: Badge en la tarjeta
- **WHEN** el docente abre Correcciones y hay una re-entrega con nota anterior 6
- **THEN** su tarjeta muestra "Entregada" y además "Re-entrega · antes 6", sin abrirla

#### Scenario: Entrega nueva sin badge
- **WHEN** la entrega es nueva
- **THEN** su tarjeta no muestra el badge "Re-entrega"

#### Scenario: Corregir sólo re-entregas
- **WHEN** el docente activa "Sólo re-entregas" y arranca la corrección por lote
- **THEN** la cola contiene sólo las re-entregas pendientes

### Requirement: Ejercicios pedidos en la re-entrega
Cuando una re-entrega conserve en sus ejercicios la marca de que el docente pidió corregirlos, la tarjeta SHALL mostrar cuáles ("Corrección pedida: ej. 2 y 4"), o "todos" si la marca está en todos. Si ningún ejercicio tiene la marca, la tarjeta SHALL mostrar sólo el badge "Re-entrega", sin inventar el detalle.

#### Scenario: Corrección parcial
- **WHEN** la re-entrega tiene la marca en los ejercicios 2 y 4
- **THEN** la tarjeta muestra "Corrección pedida: ej. 2 y 4"

#### Scenario: Re-entrega sin marca
- **WHEN** la re-entrega viene de una devolución anterior a la marca
- **THEN** la tarjeta muestra "Re-entrega" sin detalle de ejercicios
