## 1. Gates que bloquean todo

- [ ] 1.1 Escribir el ADR de aislamiento y hacerlo firmar por Cortez. Debe declarar explícitamente que el aislamiento elegido comparte núcleo con el anfitrión, a diferencia del ejemplo que menciona la decisión vigente sobre ejecución de código, y justificar el intercambio.
- [ ] 1.2 Registrar en ese ADR, como controles obligatorios y no como recomendaciones, las mitigaciones de la vulnerabilidad conocida de escape de sandbox: versión mínima, red deshabilitada en el contenedor, credenciales de base no predeterminadas.
- [ ] 1.3 Verificar cuál es el número de ADR libre. El 034 ya está tomado por la decisión sobre casos de prueba.
- [ ] 1.4 Decisión de infraestructura con Maty: dónde vive el sandbox y quién lo paga.
- [ ] 1.5 🔴 Antes de contratar cualquier servidor, confirmar que su distribución soporta la versión de la interfaz de control de recursos que la herramienta de aislamiento necesita. Las distribuciones recientes traen por omisión la que no sirve, y el sandbox directamente no levanta.
- [ ] 1.6 Dimensionar los procesos de trabajo contra la concurrencia real. El valor por omisión escala con los núcleos disponibles; en un servidor chico son pocos, y el caso real es una clase entera ejecutando en la misma ventana de dos minutos. Calcularlo, no suponerlo.

## 2. Servicio de ejecución — esqueleto

- [ ] 2.1 Crear el servicio siguiendo el patrón de los existentes: aplicación, dependencias de autenticación por cabeceras del gateway, rutas de estado de salud con el helper compartido.
- [ ] 2.2 Asignarle un puerto libre y registrarlo en el mapa de rutas del gateway. Sin entrada ahí, el endpoint queda inalcanzable desde los frontends.
- [ ] 2.3 Configuración con la dirección del sandbox por variable de entorno, para que el desarrollo no dependa de la decisión de infraestructura.
- [ ] 2.4 Soporte de la firma de cabeceras del gateway, con el mismo interruptor apagado por omisión que usan los demás servicios.
- [ ] 2.5 Contenedor propio, alineado con los existentes. **Sin tolerar errores de migración en el arranque** — el servicio no tiene base propia, pero si alguna vez la tiene, no repetir el patrón que convierte un despliegue fallido en uno aparentemente exitoso.

## 3. Ejecución

- [ ] 3.1 Endpoint de solicitud de ejecución que responde de inmediato con un identificador.
- [ ] 3.2 Endpoint de consulta de estado y resultado.
- [ ] 3.3 Cliente del sandbox con los límites por ejecución explícitos, sin depender de sus valores por omisión.
- [ ] 3.4 Incorporación de los casos ocultos del lado del servidor, leyendo la definición completa del ejercicio sin el filtrado por visibilidad que aplica el endpoint público.
- [ ] 3.5 Test de que ninguna respuesta al cliente contiene el contenido, el nombre ni la salida esperada de un caso oculto.
- [ ] 3.6 Traducción del resultado del sandbox al formato de casos de prueba del sistema, para que la vista de resultados se reuse sin cambios.
- [ ] 3.7 Test de que la estructura del resultado es idéntica a la que produce la ejecución en el navegador.

## 4. Cuotas

- [ ] 4.1 Límite por alumno y ventana, configurable.
- [ ] 4.2 🔴 Fallo cerrado ante indisponibilidad del mecanismo de conteo. Es lo contrario del comportamiento de los demás límites del sistema, que fallan abiertos a propósito — acá la consecuencia es costo real sin techo.
- [ ] 4.3 Test explícito del fallo cerrado.
- [ ] 4.4 Test de que alcanzar el límite no bloquea el resto del episodio.
- [ ] 4.5 Métricas de ejecuciones en espera y de rechazos por cuota.

## 5. Trazabilidad

- [ ] 5.1 Emitir el evento de ejecución con el motor real, en lugar del valor fijo actual.
- [ ] 5.2 🔴 Distinguir en el contrato "los casos corrieron y fallaron" de "los casos no pudieron correr". Sin esto, una caída del sandbox se registra como el alumno fallando todos los casos, y el clasificador usa ese conteo para separar dos niveles de apropiación: un problema de red degradaría la clasificación pedagógica de un episodio real de la tesis.
- [ ] 5.3 Test de que un fallo de infraestructura no produce casos fallidos en el registro.
- [ ] 5.4 Clave de idempotencia en el registro de ejecución de casos. Hoy ese endpoint no la usa aunque otros eventos del tutor sí; con ejecución en servidor, perder un evento significa que la corrida se pagó y para el clasificador nunca existió.
- [ ] 5.5 Test de que un reintento no agrega un segundo evento a la cadena.
- [ ] 5.6 Verificar que el hash de configuración del clasificador y la versión del etiquetador no cambiaron.

## 6. Editor del alumno

- [ ] 6.1 Rama de ejecución que llama al servicio en lugar de cargar el entorno local, reemplazando el estado de "no disponible".
- [ ] 6.2 Consulta de estado con indicación de espera propia, que explique que se está compilando y ejecutando en el servidor. La espera ocurre en cada ejecución, no solo la primera.
- [ ] 6.3 Impedir una segunda solicitud mientras hay una en curso.
- [ ] 6.4 Módulo nuevo de análisis de errores de Java, para compilación y para excepciones en ejecución. No es una extensión del existente: ese usa expresiones regulares del formato de traza del otro lenguaje y no coincide con ninguno de los dos formatos de Java.
- [ ] 6.5 Señalar la línea en el editor cuando el error lo permita, sin señalar ninguna arbitraria cuando no.
- [ ] 6.6 Mensaje distinguible ante indisponibilidad del entorno, separado de un error del código del alumno.
- [ ] 6.7 Verificar que el camino del lenguaje ya soportado queda intacto: carga del entorno local, ejecución, casos de prueba, historial de corridas y marcadores de error.

## 7. Panel de prueba del docente

- [ ] 7.1 Rama de ejecución en el runner propio del docente, que es una implementación separada de la del editor del alumno por decisión explícita del proyecto.
- [ ] 7.2 Verificar que un ejercicio Java se puede probar contra todos sus casos, incluidos los ocultos.
- [ ] 7.3 Comportamiento definido ante sandbox caído. Es distinto del caso del alumno: el docente está creando contenido, y publicar un ejercicio que no se pudo verificar es una decisión con consecuencias.

## 8. Verificación

- [ ] 8.1 Smoke test del ciclo completo: alumno abre episodio Java, escribe, ejecuta, corre casos de prueba, ve resultados, cierra.
- [ ] 8.2 Smoke test del camino de fallo: sandbox no disponible, verificar que el registro lo distingue de casos fallidos.
- [ ] 8.3 Prueba de carga contra la concurrencia real esperada, no contra un caso cómodo. El escenario a medir es la clase entera ejecutando junta.
- [ ] 8.4 Verificar los controles de seguridad del ADR sobre el despliegue real: versión del sandbox, red deshabilitada, credenciales cambiadas. Verificados, no asumidos.
- [ ] 8.5 Confirmar que el sandbox no alcanza ninguna base de datos de la plataforma ni la red interna.
- [ ] 8.6 `make test-fast` y la batería de aislamiento por inquilino en verde.
- [ ] 8.7 Actualizar `CLAUDE.md` con el servicio nuevo, su puerto y su entrada en el mapa de rutas, y el conteo de smoke tests si cambió.

## 9. Puesta en producción

- [ ] 9.1 Monitoreo de costo desde el primer día, no cuando llegue la factura.
- [ ] 9.2 Documentar el procedimiento de apagado: cómo devolver el editor al estado de "ejecución no disponible" sin bloquear episodios en curso.
- [ ] 9.3 Habilitar el lenguaje para una comisión antes que para todas.
