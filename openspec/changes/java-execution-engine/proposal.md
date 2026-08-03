## Why

Con `java-authoring-experience` el alumno escribe Java y el tutor lo guía, pero **no puede ejecutar nada**. Esta change cierra el ciclo: el alumno corre su código, ve pasar los tests, y el episodio produce la misma evidencia de trazabilidad que produce hoy un episodio Python.

Es el trabajo grande y el riesgo real de todo el soporte multi-lenguaje, por una razón que conviene decir sin rodeos: **hoy el código de los alumnos corre en el navegador del alumno. Con Java pasa a correr en nuestro servidor.** Si el código de un alumno hace algo raro con Pyodide, es su navegador. Con ejecución server-side, es infraestructura que además aloja datos de estudiantes reales.

**No existe ningún motor de ejecución server-side.** Verificado: cero resultados de runner/executor/sandbox/judge en `apps/` y `packages/`. No hay stub, no hay nada a medio construir.

## What Changes

- **Servicio de ejecución nuevo**, intermediario entre el alumno y el sandbox. Cuatro responsabilidades que el sandbox por sí solo no cubre: inyectar los casos de prueba ocultos sin mandárselos al navegador, aplicar cuotas por alumno, traducir el resultado al formato de casos de prueba del sistema, y emitir el evento de trazabilidad.
- **Integración con un sandbox de ejecución de código de terceros**, con los controles de seguridad que su vulnerabilidad conocida exige.
- **Cuotas de ejecución por alumno**, que hoy no existen. Con ejecución en el navegador eran innecesarias: el costo lo pagaba el alumno. Con ejecución server-side, cada corrida consume CPU y dinero.
- **Rama de ejecución en el editor del alumno**, reemplazando el estado "no disponible" que dejó la change anterior.
- **Rama de ejecución en el panel de prueba del docente**, que corre sobre un runner propio y separado del editor del alumno. Sin esto, **el docente no puede verificar un ejercicio Java antes de asignarlo**.
- **Análisis de errores de compilación y ejecución de Java**, que no es una extensión del existente sino un módulo nuevo: el actual usa expresiones regulares del formato de traza de Python.
- **Distinción entre "falló la infraestructura" y "fallaron los tests"** en el contrato de trazabilidad. Hoy no existe.

## Capabilities

### New Capabilities

- `code-execution-service`: servicio que ejecuta código de alumnos en un entorno aislado, inyecta los casos ocultos, aplica cuotas, traduce resultados y registra la ejecución en la cadena de trazabilidad. Es el intermediario que hace que el navegador nunca hable directo con el sandbox.
- `java-runtime-editor`: el alumno ejecuta su código Java y ve resultados de casos de prueba desde el editor; el docente verifica un ejercicio Java antes de asignarlo. Incluye el análisis de errores de compilación y ejecución propios de Java.
- `execution-quotas`: límites de ejecución por alumno que protegen el costo y la capacidad de la infraestructura, con comportamiento definido ante fallo del mecanismo de conteo.

### Modified Capabilities

Ninguna de las 13 de `openspec/specs/` cubre ejecución de código.

## Impact

- **Servicio nuevo**: se despliega, se monitorea y se mantiene. Es un servicio más que operar en un piloto sin administrador de sistemas dedicado — exactamente el costo que la decisión original de ejecutar en el navegador quiso evitar.
- **Infraestructura nueva**: el sandbox necesita privilegios de contenedor para aislar procesos. Y hay un requisito de kernel poco documentado: la herramienta de aislamiento depende de la versión de la interfaz de control de recursos que las distribuciones recientes ya no traen por omisión. **Provisionar el servidor con la distribución equivocada hace que el sandbox no levante.** Confirmarlo antes de contratar, no después.
- **tutor-service**: el evento de ejecución deja de declarar un entorno fijo.
- **web-student y web-teacher**: rama de ejecución en el editor y en el panel de prueba del docente, más el análisis de errores nuevo.
- **Costo recurrente**: la ejecución en el navegador era gratis. Compilar y ejecutar Java consume CPU real, por corrida, con ~87 alumnos.

## Gate de decisión — bloquea toda la change

**Un ADR de aislamiento, firmado, antes de la primera línea de código.**

No es formalidad. La decisión vigente sobre ejecución de código dice textualmente que la ejecución server-side *"se desbloquea con ADR específico de isolation"*, y menciona como ejemplo una tecnología de aislamiento que **intercepta llamadas al sistema en espacio de usuario**. El sandbox que se propone usar emplea aislamiento por espacios de nombres y grupos de control, que **comparte el núcleo con el anfitrión**. Un fallo del núcleo escapa.

No son equivalentes. Elegirlo es una decisión de seguridad estrictamente más débil que la que el ADR vigente ilustra, y eso hay que **declararlo y justificarlo**, no heredarlo tácitamente. Un tribunal doctoral que pregunte por el aislamiento del piloto merece una respuesta escrita.

El ADR debe además registrar como controles obligatorios —no recomendaciones— las mitigaciones de la vulnerabilidad conocida de escape de sandbox de ese producto: versión mínima, red deshabilitada en el contenedor, y credenciales de base de datos no predeterminadas.

**El número siguiente libre hay que verificarlo.** El 034 ya está tomado por la decisión sobre casos de prueba como documento estructurado.

## Decisión de infraestructura — bloquea el despliegue, no el código

Dónde vive el sandbox y quién lo paga. Tres opciones, con la restricción real de que el servidor de producción viene corriendo con la memoria muy comprometida:

| Opción | Evaluación |
|---|---|
| Servicio gestionado por terceros | Cero huella de memoria en el servidor actual. La forma más rápida y barata de validar el flujo completo antes de invertir en infraestructura |
| Servidor propio aparte | La única opción autoalojada viable. Aísla el contenedor privilegiado del servidor que aloja los datos de alumnos, y no compite por memoria |
| Mismo servidor de producción | Descartable: memoria comprometida, más un contenedor privilegiado sobre una plataforma gestionada que probablemente ni lo permita |

Se escribe el servicio con la dirección del sandbox por configuración, de modo que **esta decisión no bloquea el desarrollo**, solo la validación de punta a punta.

## Lo que esta change protege explícitamente

**El clasificador usa el conteo de casos fallidos para distinguir dos niveles de apropiación.** Si una caída del sandbox o un tiempo de espera agotado se registra como "el alumno falló los tests", **contamina la clasificación pedagógica** de un episodio real de la tesis con un fallo de infraestructura.

Esa distinción no existe hoy en el contrato de trazabilidad, y con ejecución en el navegador no hacía falta. Ahora sí.

Y hay un agujero relacionado: el endpoint que registra la ejecución de casos de prueba **no usa clave de idempotencia**, a diferencia de otros eventos del tutor. Con ejecución en el navegador, perder un evento era gratis. Con ejecución server-side, la corrida ya consumió cómputo, dinero y cuota del alumno — y si el evento se pierde, para el clasificador esa ejecución nunca existió.
