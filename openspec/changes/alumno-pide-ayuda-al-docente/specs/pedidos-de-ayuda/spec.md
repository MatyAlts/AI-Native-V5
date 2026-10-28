## Purpose

Permite que un alumno le pida ayuda a una persona (los docentes de su comisión) desde adentro de un ejercicio, con el contexto del ejercicio y del episodio adjunto, sin pasar por el tutor ni por el CTR, para que los problemas lleguen con datos para diagnosticar.

## ADDED Requirements

### Requirement: El alumno crea un pedido de ayuda con contexto adjunto
El sistema SHALL permitir a un alumno crear un pedido de ayuda indicando el trabajo práctico, una categoría (`no_puedo_avanzar`, `error_plataforma`, `duda_consigna`, `otro`) y, opcionalmente, un mensaje libre de hasta 1000 caracteres, el número de ejercicio, el identificador de episodio, el identificador de entrega y un diagnóstico mínimo de pantalla. El sistema MUST derivar la comisión del trabajo práctico (no la acepta del cliente), MUST registrar la hora del servidor y el alumno autenticado, y MUST dejar el pedido en estado `pendiente`.

#### Scenario: Pedido desde un ejercicio abierto
- **WHEN** un alumno inscripto en la comisión de la TP envía un pedido con TP, ejercicio 2, `episode_id`, categoría `no_puedo_avanzar` y un mensaje
- **THEN** el sistema responde 201 con el pedido en estado `pendiente`, la comisión de la TP, el ejercicio 2, el `episode_id` y la hora del servidor

#### Scenario: Pedido sin episodio (el ejercicio no se abrió)
- **WHEN** un alumno envía un pedido con TP y categoría `error_plataforma` y sin `episode_id`
- **THEN** el sistema responde 201 y el pedido queda con `episode_id` vacío

#### Scenario: Episodio que no existe en la base
- **WHEN** un alumno envía un pedido con un `episode_id` que el CTR nunca persistió
- **THEN** el sistema acepta el pedido igual y guarda ese `episode_id` tal cual, sin validarlo contra el CTR

#### Scenario: Categoría inválida o mensaje demasiado largo
- **WHEN** un alumno envía una categoría fuera de las cuatro permitidas, o un mensaje de más de 1000 caracteres, o claves de diagnóstico no permitidas
- **THEN** el sistema responde 422 y no crea el pedido

### Requirement: Sólo un alumno inscripto puede pedir ayuda sobre una TP de su comisión
El sistema MUST rechazar el pedido si la TP no existe, si el alumno no tiene una inscripción vigente en la comisión de la TP, o si se indica una entrega que no es del alumno o no es de esa TP.

#### Scenario: Alumno no inscripto
- **WHEN** un alumno sin inscripción en la comisión de la TP envía un pedido
- **THEN** el sistema responde 403 y no crea el pedido

#### Scenario: TP inexistente
- **WHEN** un alumno envía un pedido sobre una TP que no existe
- **THEN** el sistema responde 422 y no crea el pedido

#### Scenario: Entrega ajena
- **WHEN** un alumno envía un pedido con el `entrega_id` de otro alumno
- **THEN** el sistema responde 422 y no crea el pedido

#### Scenario: Un docente no crea pedidos
- **WHEN** un usuario sin rol de estudiante intenta crear un pedido
- **THEN** el sistema responde 403

### Requirement: Límite anti-spam por alumno
El sistema MUST rechazar un pedido nuevo si el mismo alumno creó otro en los últimos 60 segundos (429), o si ya tiene 3 pedidos `pendiente` en la misma TP (409). Los pedidos resueltos no cuentan para el tope.

#### Scenario: Dos pedidos seguidos
- **WHEN** un alumno crea un pedido y 10 segundos después intenta crear otro
- **THEN** el segundo recibe 429 con un mensaje que dice cuánto esperar

#### Scenario: Tope de pendientes
- **WHEN** un alumno con 3 pedidos pendientes en la TP intenta un cuarto
- **THEN** recibe 409 "Ya tenés 3 pedidos sin responder en este trabajo"

#### Scenario: Un pedido resuelto libera el cupo
- **WHEN** el docente marca resuelto uno de esos 3 pedidos y el alumno vuelve a pedir pasado el minuto
- **THEN** el pedido nuevo se crea con 201

### Requirement: El alumno ve sus propios pedidos
El sistema SHALL devolverle al alumno sus pedidos (opcionalmente filtrados por TP), con categoría, mensaje, ejercicio, estado y fechas, y MUST NOT devolverle pedidos de otros alumnos.

#### Scenario: Listado propio
- **WHEN** un alumno pide sus pedidos de una TP
- **THEN** recibe sólo los suyos, del más nuevo al más viejo, con su estado

### Requirement: Los docentes de la comisión ven los pedidos de su comisión
El sistema SHALL listar los pedidos de una comisión, filtrables por estado (`pendiente`/`resuelto`), con la cantidad de pendientes, sólo a los usuarios asignados a esa comisión como docentes y a los roles de supervisión (`docente_admin`, `superadmin`). El sistema MUST rechazar el listado a un docente de otra comisión y a un alumno.

#### Scenario: Docente de la comisión
- **WHEN** un docente asignado a la comisión lista los pedidos pendientes
- **THEN** recibe los pedidos pendientes de esa comisión, con alumno, TP, ejercicio, categoría, mensaje, `episode_id`, fecha, y el total de pendientes

#### Scenario: Docente de otra comisión
- **WHEN** un docente que no está asignado a la comisión lista sus pedidos
- **THEN** el sistema responde 404 y no devuelve ningún pedido

#### Scenario: Alumno intenta listar la comisión
- **WHEN** un alumno pide el listado de la comisión
- **THEN** el sistema responde 403

### Requirement: Un docente de la comisión marca un pedido como resuelto
El sistema SHALL permitir a un docente de la comisión del pedido (o a un rol de supervisión) marcarlo `resuelto`, registrando quién y cuándo. La operación MUST ser idempotente y MUST NOT existir el camino inverso en esta versión.

#### Scenario: Marcar resuelto
- **WHEN** un docente de la comisión marca resuelto un pedido pendiente
- **THEN** el pedido queda `resuelto` con el docente y la hora, y deja de contar como pendiente

#### Scenario: Marcar resuelto dos veces
- **WHEN** el pedido ya está resuelto y se vuelve a marcar
- **THEN** el sistema responde 200 sin cambiar quién ni cuándo lo resolvió

#### Scenario: Docente ajeno
- **WHEN** un docente de otra comisión intenta marcarlo resuelto
- **THEN** el sistema responde 404 y el pedido no cambia

### Requirement: Aislamiento por institución
Los pedidos MUST quedar aislados por institución (tenant) a nivel base de datos: con el tenant de otra institución configurado no se ve ni se puede insertar ningún pedido ajeno, y sin tenant configurado no se ve ninguno.

#### Scenario: Otra institución
- **WHEN** una sesión con el tenant B consulta la tabla de pedidos con pedidos sólo del tenant A
- **THEN** obtiene cero filas

### Requirement: El pedido de ayuda queda fuera de la traza cognitiva
Crear, listar o resolver un pedido MUST NOT emitir eventos al CTR, MUST NOT pasar por el tutor ni por el gateway de IA, y MUST NOT modificar el episodio. El registro operativo del pedido MUST ir sólo al log estructurado, sin el texto del mensaje.

#### Scenario: Crear un pedido no toca el CTR
- **WHEN** un alumno crea un pedido con `episode_id` durante un episodio abierto
- **THEN** no se publica ningún evento al CTR y la cadena del episodio no cambia

#### Scenario: El log no lleva el mensaje
- **WHEN** se crea un pedido con mensaje
- **THEN** el log `pedido_ayuda_creado` lleva ids y categoría, y no lleva el texto del mensaje

### Requirement: Botón de pedir ayuda en la pantalla del alumno
web-student SHALL mostrar un botón "Pedir ayuda a tu docente" en la pantalla del episodio (incluida la pantalla de error cuando el ejercicio no terminó de abrirse) y en la lista de ejercicios de la TP. El modal MUST pedir la categoría, ofrecer el mensaje opcional, aclarar que el pedido va al docente y no al tutor, confirmar el envío, mostrar los pedidos propios de la TP con su estado, y mostrar en lenguaje claro los rechazos por límite.

#### Scenario: Pedido desde la pantalla de error
- **WHEN** el ejercicio no terminó de abrirse y el alumno toca "Pedir ayuda a tu docente", elige "Error de la plataforma" y envía
- **THEN** el pedido sale con la TP, el ejercicio y el `episode_id` del intento fallido, y el modal muestra "Tu pedido le llegó a tu docente"

#### Scenario: Envío sin categoría
- **WHEN** el alumno no eligió categoría
- **THEN** el botón "Enviar" queda deshabilitado

#### Scenario: Límite alcanzado
- **WHEN** el servidor responde 429 o 409
- **THEN** el modal muestra el motivo y no da el pedido por enviado

### Requirement: Vista de pedidos de ayuda en web-teacher
web-teacher SHALL tener una entrada "Pedidos de ayuda" en el menú que muestre, para la comisión seleccionada, los pedidos en pestañas Pendientes / Resueltos, con alumno, TP, ejercicio, categoría, mensaje, antigüedad, acceso al episodio cuando hay `episode_id`, y la acción "Marcar resuelto". La tarjeta de cada comisión en "Mis comisiones" SHALL mostrar la cantidad de pedidos pendientes cuando es mayor que cero.

#### Scenario: Docente resuelve desde la lista
- **WHEN** el docente toca "Marcar resuelto" en un pendiente
- **THEN** el pedido pasa a la pestaña Resueltos y el contador de pendientes baja en uno

#### Scenario: Contador en Mis comisiones
- **WHEN** una comisión tiene 2 pedidos pendientes
- **THEN** su tarjeta muestra "2 pedidos de ayuda" con acceso a la vista
