# ADR-059 — Aislamiento para ejecución server-side de Java: Judge0 gestionado, con kernel compartido declarado

- **Estado**: **Aceptado**
- **Fecha**: 2026-07-28
- **Firmado por**: Alberto Cortez, 2026-07-28 — leyó el documento y aprobó la decisión de aislamiento. Con esto queda levantado el gate que bloqueaba la change `java-execution-engine`.
- **Deciders**: Alberto Cortez (director de tesis — decisión de seguridad y su defensa académica). Juani Sarmiento (planteo técnico e implementación). Matías Torres Altamirano (infraestructura).
- **Tags**: seguridad, aislamiento, ejecucion-codigo, java, sandbox, judge0, piloto-2
- **Resuelve**: el gate de decisión de la change `java-execution-engine` (tareas 1.1, 1.2 y 1.4 de su `tasks.md`). **Bloquea toda la change**: sin este ADR firmado no se escribe una línea del servicio de ejecución.
- **Modifica**: [ADR-033](033-sandbox-pyodide-only-piloto-1.md) — que difería la ejecución server-side "hasta ADR especifico de isolation (ej. gVisor)".

## Contexto y problema

Hoy **todo el código de alumnos corre en el navegador del alumno** (ADR-033). El sandbox es Pyodide con controles artesanales: watchdog por trazado de opcodes con corte a 5s, `input()` sustituido para no bloquear, e importaciones al DOM bloqueadas. Los casos de prueba ocultos nunca viajan al navegador.

Ese diseño se eligió deliberadamente para **no agregar superficie de seguridad ni un servicio más que operar**. Java lo rompe de raíz: no hay forma de correr una JVM en el navegador.

La epic `java-authoring-experience` (cerrada, 41/43) dejó al alumno escribiendo Java con el tutor acompañándolo, pero **sin poder ejecutar**. Cerrar ese ciclo mueve la ejecución de código no confiable del navegador del alumno **a infraestructura nuestra**, que además aloja los datos de ~87 estudiantes reales y la cadena CTR que sostiene el claim central de la tesis.

El ADR-033 dejó la puerta entreabierta con una condición explícita (su línea 58):

> ejecución server-side de hidden, se desbloquea con ADR especifico de isolation (**ej. gVisor**).

**gVisor y Judge0 no son equivalentes, y esa diferencia es el corazón de este ADR.**

## Decisión

Se adopta **Judge0 en su modalidad gestionada (cloud del proveedor)** como motor de ejecución de Java, con los controles obligatorios de la sección siguiente.

### D1 — Se declara explícitamente que el aislamiento elegido es más débil que el ejemplo del ADR-033

| | gVisor (ejemplo del ADR-033) | Judge0 / `isolate` (esta decisión) |
|---|---|---|
| Mecanismo | Intercepta syscalls en **espacio de usuario**; el kernel del host casi no se toca | Namespaces + cgroups del **kernel del host** |
| Kernel | Kernel propio reimplementado en Go | **Compartido con el anfitrión** |
| Consecuencia de un fallo del kernel | Contenido por la capa de intercepción | **Escapa al host** |

Esto **no se hereda tácitamente del ADR-033: se declara**. La elección es estrictamente más débil en aislamiento que el ejemplo que ese ADR menciona, y se acepta por tres razones:

1. **Judge0 resuelve el problema completo, gVisor no.** gVisor es una capa de aislamiento, no un motor de ejecución: encima habría que construir compilación de Java, límites por corrida, inyección de casos y normalización de resultados. Los artefactos de la change declaran "construir el sandbox" como **non-goal** explícito.
2. **En modalidad gestionada, el kernel compartido no es nuestro.** El contenedor privilegiado y su host corren en infraestructura del proveedor, físicamente separada de la que aloja `academic_main`, `ctr_store`, `classifier_db` y `content_db`. Un escape aterriza en una máquina del proveedor **sin datos del piloto**.
3. **El alcance del daño está acotado por diseño.** El servicio de ejecución es el único que habla con Judge0; el navegador nunca lo toca. No viajan credenciales de la plataforma ni datos de estudiantes: solo el código del alumno y los casos de prueba del ejercicio.

### D2 — Vive fuera del VPS de producción

**Judge0 NO se despliega en el VPS del piloto.** Se evaluó y se descarta:

- El VPS viene con la memoria muy comprometida (~89%), y la regla operativa vigente es desplegar de a un servicio por vez. Judge0 no es un servicio: es API + workers + su propio Postgres + su propio Redis, más una JVM por corrida concurrente.
- `isolate` exige **contenedor privilegiado**. Un contenedor privilegiado en el mismo host que las bases con datos de estudiantes anula la razón de ser de este ADR: si el aislamiento que elegimos es el más débil, la separación física es la mitigación que lo compensa. **No es negociable.**
- No está confirmado que EasyPanel permita contenedores privilegiados.

La dirección del sandbox va **por configuración** (variable de entorno), así que migrar de gestionado a self-hosted más adelante no toca código.

### D3 — Autoalojar en el futuro requiere una enmienda a este ADR

Si se decide autoalojar (por costo o por soberanía del dato), esa decisión **vuelve acá**, y antes de contratar el servidor hay que verificar dos cosas que hacen que Judge0 directamente no levante:

- **cgroups v1**: `isolate` lo requiere. Las distribuciones recientes traen **v2** por omisión. Comprobar con `stat -fc %T /sys/fs/cgroup/` (debe decir `tmpfs` para v1, no `cgroup2fs`) **antes de pagar**.
- Capacidad de correr contenedores privilegiados en esa plataforma.

## Controles obligatorios

Son **requisitos de despliegue, no recomendaciones**. Se verifican sobre el despliegue real (tarea 8.4 de la change), no se asumen.

### C1 — Versión mínima: Judge0 **1.13.1** o superior

Las versiones anteriores tienen dos vulnerabilidades de **escape de sandbox con CVSS 10.0** (el máximo de la escala):

| CVE | CVSS | Naturaleza |
|---|---|---|
| **CVE-2024-28185** | **10.0** | La aplicación no contempla *symlinks* dentro del directorio del sandbox: permite escribir archivos arbitrarios y ejecutar código **fuera** del sandbox |
| **CVE-2024-28189** | **10.0** | *Bypass del parche* del anterior, vía `chown` sobre un archivo no confiable dentro del sandbox: un symlink a un archivo externo permite ejecutar `chown` fuera |

Ambas se corrigen en **1.13.1** (publicada el 2024-04-18). En modalidad gestionada, **verificar con el proveedor la versión que corre** — no se asume que esté actualizado. Si el proveedor no la declara, es motivo para no usarlo.

### C2 — Red deshabilitada dentro del contenedor de ejecución

El código del alumno **no debe tener salida de red**. Sin esto, un ejercicio puede exfiltrar, descargar cargas útiles o usarse para atacar terceros desde nuestra identidad. Judge0 lo expone como opción por submission: se fija en el servicio de ejecución, no se deja al cliente elegirlo.

### C3 — Credenciales no predeterminadas

El `docker-compose` de Judge0 trae credenciales por defecto para su Postgres y su Redis. Si alguna vez se autoaloja, se cambian **antes** de exponer nada. En gestionado, aplica al token de API: vive como variable de entorno, nunca en disco ni en logs, y rota si se filtra.

### C4 — El sandbox no alcanza la red interna de la plataforma

Verificable, no asumido (tarea 8.5): Judge0 no debe poder resolver ni alcanzar ninguna de las cuatro bases lógicas, ni Redis, ni ningún servicio interno. En gestionado esto es consecuencia de la separación, pero **se comprueba igual**.

### C5 — Monitoreo de costo desde el día uno

Ejecutar en el navegador era gratis. Compilar y ejecutar Java cuesta por corrida. Con ~87 alumnos y una clase entera ejecutando en la misma ventana, el gasto se descubre por factura si no se mide antes. Complementa las cuotas por alumno, que **fallan cerradas** por decisión de la change (a diferencia del resto de los límites del sistema, que fallan abiertos a propósito).

## Consecuencias

**Positivas**

- El alumno ejecuta Java y ve resultados de casos de prueba, cerrando el ciclo pedagógico que la epic anterior dejó abierto.
- Los casos ocultos se ejecutan **sin que el navegador los vea nunca** — una propiedad que la ejecución client-side no puede dar y que ADR-033 registraba como ventaja pendiente del server-side.
- Cero huella de memoria en el VPS del piloto.
- La respuesta a "¿cómo aislaron la ejecución de código?" ante el tribunal es un documento, no una improvisación.

**Negativas, aceptadas**

- **Aislamiento más débil que gVisor**, con kernel compartido. Es el intercambio central de este ADR y está declarado, no escondido.
- **Dependencia de un tercero** para una pieza del camino crítico del alumno. Se mitiga con degradación: si Judge0 no responde, el editor vuelve al estado explícito de "ejecución no disponible" y el alumno **sigue** con el enunciado y el tutor. Ejecutar es un agregado, no un bloqueante del episodio.
- **Costo recurrente** donde antes había cero.
- **El código del alumno sale de nuestra infraestructura** hacia el proveedor. No son datos personales —es código de ejercicios— pero conviene declararlo en el consentimiento del piloto si todavía no lo cubre.

**Neutras**

- Python **no se toca**: sigue en Pyodide, instantáneo y gratis. Este ADR no revierte ADR-033 para Python, solo lo extiende para Java.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| **gVisor + runner propio** | Aislamiento más fuerte y sin contradecir ADR-033, pero exige construir compilación, límites, inyección de casos y normalización de resultados. Declarado non-goal. Reconsiderable en piloto-2 si el aislamiento pasa a ser requisito duro. |
| **Judge0 autoalojado en VPS aparte** | Viable y probablemente el destino final. Se difiere: primero validar el flujo completo sin invertir en infraestructura. Requiere la enmienda de D3. |
| **Judge0 en el VPS de producción** | **Descartado.** Contenedor privilegiado junto a las bases con datos de estudiantes, sobre un host al ~89% de memoria y una plataforma gestionada que probablemente no lo permita. Anula la mitigación que compensa el kernel compartido. |
| **Seguir sin ejecución de Java** | Es el estado actual y es honesto (el editor lo dice explícitamente), pero deja el curso de POO sin validación automática y al docente sin poder verificar sus propios ejercicios. |

## Verificación

Antes de declarar la change cerrada:

- [ ] Versión de Judge0 confirmada ≥ 1.13.1 **con el proveedor** (C1)
- [ ] Red deshabilitada comprobada con un ejercicio que intente salir a internet (C2)
- [ ] Token de API fuera de disco y de logs (C3)
- [ ] Comprobado que el sandbox no alcanza las 4 bases ni Redis (C4, tarea 8.5)
- [ ] Monitoreo de costo activo antes de habilitar para alumnos (C5)
- [ ] Habilitación progresiva: una comisión antes que todas (tarea 9.3)

## Referencias

- [ADR-033](033-sandbox-pyodide-only-piloto-1.md) — sandbox Pyodide-only en piloto-1; este ADR levanta su condición para Java.
- CVE-2024-28185 y CVE-2024-28189 — escapes de sandbox de Judge0, CVSS 10.0, corregidos en 1.13.1 (2024-04-18).
- `openspec/changes/java-execution-engine/` — proposal, design y specs de la change que este ADR desbloquea.
