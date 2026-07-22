## Context

Hoy todo el código de alumnos corre en el navegador, con un sandbox armado a mano sobre el intérprete embebido: vigilancia de cómputo por trazado de opcodes con corte a los 5 segundos, sustitución de la entrada estándar para no bloquear, y bloqueo de importaciones que darían acceso al DOM. Los casos ocultos nunca llegan al navegador — el backend directamente no se los manda, y el contrato del evento de trazabilidad tiene el conteo de ocultos acotado a cero por validación, no por convención.

Ese diseño se eligió deliberadamente: sin componente nuevo que operar y sin superficie de seguridad nueva. Java lo rompe de raíz, porque no hay forma de correr una máquina virtual de Java en el navegador.

Restricción de infraestructura real: el servidor de producción viene corriendo con la memoria muy comprometida, y el despliegue es sobre una plataforma gestionada donde no está confirmado que se puedan correr contenedores privilegiados.

## Goals / Non-Goals

**Goals:**

- Que el alumno ejecute Java y vea resultados de casos de prueba con la misma experiencia que hoy tiene en Python.
- Que el docente pueda verificar un ejercicio Java antes de asignarlo.
- Que los casos ocultos se ejecuten sin que el navegador los vea nunca.
- Que un fallo de infraestructura jamás se registre como un fallo pedagógico del alumno.
- Que el costo de cómputo esté acotado por alumno.

**Non-Goals:**

- **No soportar múltiples archivos.** Java admite varias clases en un mismo archivo, y con eso se enseña POO real. El editor y el contrato de trazabilidad asumen un archivo único; cambiarlo es un proyecto aparte con su propio ADR.
- **No unificar el runner del alumno con el del docente.** Son dos implementaciones separadas por decisión explícita del proyecto. Ambas ganan rama Java; no se fusionan acá.
- **No sustituir la ejecución de Python.** Sigue en el navegador: es instantánea, gratuita y ya funciona.
- **No construir el sandbox.** Se integra uno existente.

## Decisions

### D1 — Servicio propio, no un endpoint dentro del tutor

**Radio de impacto.** El sandbox exige privilegios de contenedor. Si la lógica que le habla vive dentro del servicio del tutor —que además maneja el flujo de conversación, las sesiones de todos los episodios activos y el streaming— cualquier compromiso de ese proceso queda en el mismo radio que el componente que dialoga con un sandbox privilegiado. Aislado, un compromiso expone solo su propio alcance.

**Despliegue diferenciado.** El sandbox conviene que viva en un servidor aparte por la restricción de memoria y por aislamiento. Un servicio que le habla desde otra máquina es operacionalmente un despliegue distinto del tutor.

**Regla operativa existente.** Redesplegar el servicio del tutor con alumnos trabajando desincroniza la secuencia de eventos y rompe episodios sin recuperación. Sumarle un motivo más de redespliegue —ajustar cuotas, cambiar la dirección del sandbox— es empeorar un problema conocido.

**Alternativa considerada**: endpoint en el tutor, menos servicios que operar. Es un argumento real —fue la razón de elegir ejecución en el navegador— pero no sobrevive a los tres puntos anteriores.

### D2 — Asíncrono con consulta de estado, no petición-respuesta bloqueante

El cliente recibe un identificador y consulta el resultado.

Compilar y arrancar una máquina virtual de Java no es instantáneo, y a eso se le suma la latencia de red y la cola del sandbox. Con una clase entera ejecutando en la misma ventana de dos minutos —el caso real, no el peor teórico— la cola puede tardar. Una petición síncrona deja el editor congelado sin poder distinguir "está compilando" de "se colgó".

**Alternativa descartada**: petición síncrona con tiempo de espera generoso. Simple de implementar y mala para el alumno: sin señal de progreso, cualquier espera se lee como una falla.

### D3 — El resultado se traduce al formato existente de casos de prueba

El servicio traduce la salida del sandbox al mismo formato que produce hoy la ejecución en el navegador.

Así la vista de resultados del editor se reusa sin cambios, y —más importante— **el evento de trazabilidad tiene la misma forma para los dos lenguajes**. Un investigador analizando el corpus no necesita saber qué motor ejecutó.

### D4 — El fallo de infraestructura es un estado propio, no cero tests pasados

El contrato de trazabilidad distingue explícitamente "los tests corrieron y fallaron" de "los tests no pudieron correr".

Sin esa distinción, un tiempo de espera agotado se registra como el alumno fallando todos los casos. El clasificador usa el conteo de fallidos para separar dos niveles de apropiación, así que un problema de red **degradaría la clasificación pedagógica de un episodio real de la tesis**.

Es la decisión más importante de esta change para la integridad del corpus.

### D5 — Las cuotas fallan cerradas, a diferencia del resto del sistema

El sistema tiene precedente de limitación por ventana deslizante con comportamiento tolerante ante fallo del almacén de conteo: si no responde, no bloquea. Para el chat es correcto —es protección de presupuesto, no de seguridad crítica.

Para ejecución server-side no: si el conteo se cae y las cuotas se desactivan, un alumno puede saturar el sandbox, que consume CPU y dinero reales. **Las cuotas de ejecución fallan cerradas.**

Además se apoyan en los límites que el propio sandbox aplica por corrida —tiempo de CPU, memoria, procesos— que no dependen de ningún almacén externo. Dos capas: una por corrida y otra por alumno.

**Alternativa descartada**: replicar el comportamiento tolerante por consistencia. La consistencia no es un valor cuando los dos casos tienen consecuencias distintas.

### D6 — El análisis de errores de Java es un módulo nuevo

El módulo actual usa expresiones regulares del formato de traza del intérprete de Python. Un error de compilación o una traza de excepción de Java tienen formato completamente distinto y no coinciden con ninguna.

Se escribe un módulo hermano. No se parametriza el existente: no hay nada que parametrizar cuando el formato entero es otro.

### D7 — Un único archivo, explícitamente

El editor mantiene un solo campo de código y el evento de trazabilidad un solo snapshot, sin nombre de archivo.

Java permite varias clases en un mismo archivo con una sola pública, y con eso se enseña herencia, polimorfismo y encapsulamiento. Es el 70% de un curso inicial de POO sin tocar el editor ni el contrato de trazabilidad.

Múltiples archivos exigiría nombre de archivo en el evento, lo cual cambia la forma del payload y toca la parte de la tesis. Proyecto aparte, con su ADR.

### D8 — El evento se emite después de tener el resultado

Coherente con cómo funciona hoy el registro de ejecución de casos: recibe conteos ya calculados.

Pero aparece un caso que con ejecución en el navegador no existía: si el proceso muere entre que el sandbox devolvió el resultado y que el evento se emitió, esa ejecución ya se pagó en cómputo y cuota, y para el clasificador nunca existió. Se cubre con clave de idempotencia, que el endpoint actual de registro de casos **no usa** aunque otros eventos del tutor sí.

## Risks / Trade-offs

**Vulnerabilidad conocida de escape de sandbox** → Controles obligatorios en el ADR: versión mínima, red deshabilitada en el contenedor, credenciales no predeterminadas. Verificados en el despliegue, no asumidos.

**Contenedor privilegiado** → Para aislar el código del alumno se corre un contenedor con menos aislamiento del anfitrión. Mitigación no negociable: vive en un servidor separado del que aloja las bases con datos de estudiantes.

**El sandbox no levanta por la versión de la interfaz de control de recursos del núcleo** → Confirmar la distribución antes de contratar el servidor. Es una tarde perdida si se descubre después.

**Saturación con una clase entera ejecutando a la vez** → Dimensionar los procesos de trabajo contra el número real de alumnos concurrentes, no contra el valor por omisión. Es un cálculo explícito, no un supuesto.

**El sandbox se cae a mitad de un episodio** → El editor degrada: el alumno sigue viendo el enunciado y conversando con el tutor. Ejecutar es un agregado, no un bloqueante del episodio.

**Costo sin techo** → D5, dos capas de límite. Y monitoreo del gasto desde el día uno, no cuando llegue la factura.

**Latencia percibida** → El alumno de Python tiene respuesta instantánea. El de Java va a esperar en **cada** corrida, no solo la primera. El texto de espera actual fue escrito asumiendo que la espera es rara — conviene uno propio que explique que está compilando en el servidor.

## Migration Plan

1. ADR de aislamiento firmado. Bloquea todo lo demás.
2. Decisión de infraestructura y provisión, verificando la compatibilidad de núcleo antes de pagar.
3. Servicio de ejecución con la dirección del sandbox por configuración, y cuotas. Se desarrolla y prueba contra un sandbox local sin depender del paso 2.
4. Rama de ejecución en el editor del alumno.
5. Rama en el panel de prueba del docente.
6. Registro en la trazabilidad con la distinción de fallo de infraestructura.

**Rollback**: apagar el servicio devuelve el editor al estado explícito de "ejecución no disponible" que dejó la change anterior. Ningún alumno queda bloqueado; el tutor sigue funcionando y los episodios siguen siendo válidos.

## Open Questions

**¿Se ejecutan los casos ocultos en cada corrida del alumno, o solo al entregar?** Ejecutarlos siempre multiplica el costo por el número de casos. Solo al entregar es más barato y da menos retroalimentación. Es decisión pedagógica, no técnica.

**¿Cuánto es una cuota razonable?** El sistema tiene un valor de referencia para mensajes de chat por minuto. Compilar y ejecutar Java es más caro que un mensaje, así que el límite debería ser menor — pero el número sale de medir, no de estimar.

**¿Qué se le muestra al docente cuando el sandbox está caído y quiere verificar un ejercicio?** Distinto del caso del alumno: el docente está creando contenido, no resolviendo. Bloquear la publicación de un ejercicio que no se pudo verificar es defendible, y también lo es advertir y permitir.
