## ADDED Requirements

### Requirement: Un episodio que no se puede cargar no saca al alumno en silencio

Cuando la pantalla de un episodio no logra obtener el estado del episodio porque el servidor responde "no encontrado" aun después de los reintentos existentes, el web-student SHALL mostrar dentro de la pantalla un mensaje de error explícito que diga que el ejercicio no terminó de abrirse, con una acción para reintentar la carga y otra para volver. El web-student SHALL NO navegar fuera del episodio automáticamente en ese caso. El marcador de episodio activo guardado en el navegador SHALL limpiarse para que volver a la lista no reabra el mismo episodio. Una respuesta de "acceso denegado" SHALL conservar el comportamiento previo.

#### Scenario: El episodio todavía no existe

- **WHEN** el alumno entra a un episodio recién abierto y la consulta de estado responde "no encontrado" en todos los reintentos
- **THEN** la pantalla muestra el mensaje de error con las acciones "Reintentar" y "Volver", y el alumno sigue en la pantalla del episodio

#### Scenario: Reintentar cuando el episodio ya se persistió

- **WHEN** el alumno ve el mensaje de error y pulsa "Reintentar", y esta vez la consulta de estado responde con el episodio
- **THEN** la pantalla carga el episodio normalmente, sin el mensaje de error

#### Scenario: Volver a la lista

- **WHEN** el alumno ve el mensaje de error y pulsa "Volver"
- **THEN** sale del episodio por el mismo camino de salida que ya existía, y el marcador de episodio activo ya no está guardado

#### Scenario: Episodio ajeno

- **WHEN** la consulta de estado responde "acceso denegado"
- **THEN** el comportamiento es el mismo que antes de este cambio
