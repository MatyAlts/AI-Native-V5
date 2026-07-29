# ADR-060 — Ejecución de Java en contenedor Docker sin privilegios, reemplazando Judge0

- **Estado**: **Aceptado**
- **Fecha**: 2026-07-29
- **Firmado por**: Alberto Cortez, 2026-07-29 — revisó las mediciones del spike y aprobó el cambio de motor. El ADR-059 queda **superado en su elección de motor**; sus controles obligatorios siguen vigentes, re-expresados en la sección correspondiente de este documento.
- **Deciders**: Alberto Cortez (decisión de seguridad y su defensa académica). Juani Sarmiento (spike, medición e implementación). Matías Torres Altamirano (infraestructura).
- **Tags**: seguridad, aislamiento, ejecucion-codigo, java, docker, piloto-2
- **Reemplaza**: [ADR-059](059-aislamiento-ejecucion-java-judge0-gestionado.md) en su elección de motor. Mantiene intactos sus controles obligatorios, que se re-expresan para el motor nuevo.
- **Relacionado**: [ADR-033](033-sandbox-pyodide-only-piloto-1.md) — Python sigue en Pyodide y no se toca.

## Contexto y problema

El ADR-059 eligió **Judge0 gestionado** para ejecutar Java server-side. Al implementarlo aparecieron dos costos que ese ADR anticipó como riesgos pero no midió:

**1. Judge0 no levanta en distribuciones modernas.** Su aislador, `isolate`, exige **cgroups v1**. Las distros recientes traen **v2** por omisión. Confirmado en la práctica el 2026-07-28 sobre la máquina de desarrollo (Pop!_OS, kernel 6.18):

```
$ stat -fc %T /sys/fs/cgroup/
cgroup2fs          # v2 → isolate no arranca
```

El ADR-059 (D3) ya marcaba esto como pre-condición dura antes de contratar un servidor. Lo que no estaba dimensionado es que **también bloquea el desarrollo local**: durante toda la implementación hubo que trabajar contra un doble del contrato HTTP (`scripts/judge0-fake.py`), sin poder verificar ni una sola de las propiedades de seguridad reales.

**2. El contenedor privilegiado es lo que encarece todo.** `isolate` exige `--privileged`. De ahí sale la cadena entera de decisiones del ADR-059: no puede convivir con las bases de datos de estudiantes (D2), así que hay que pagar cloud o un servidor aparte, y hay que sostener los controles contra dos CVE de escape con **CVSS 10.0** (CVE-2024-28185 y CVE-2024-28189).

La pregunta que este ADR responde es: **¿hace falta Judge0 para ejecutar un archivo Java con límites?**

## Decisión

Se ejecuta el código del alumno en un **contenedor Docker efímero sin privilegios**, invocado por el `execution-service`. Se elimina la dependencia de Judge0.

```
docker run --rm
  --network=none                     # sin salida de red
  --memory=<limite> --cpus=<limite>  # límites explícitos por corrida
  --pids-limit=<limite>
  --read-only --tmpfs=/work:...      # sin escritura salvo un tmpfs acotado
  --cap-drop=ALL                     # sin capabilities
  --security-opt=no-new-privileges   # no puede escalar vía setuid
  --user=65534:65534                 # no corre como root
  eclipse-temurin:21-jdk
```

### D1 — El aislamiento es comparable, y la superficie es menor

Conviene ser preciso y no vender de más: **`isolate` y los namespaces de Docker usan el mismo mecanismo de fondo** (namespaces + cgroups del kernel del host). Ninguno de los dos es gVisor, y en ambos un fallo del kernel escapa. Esa parte del intercambio declarado en el ADR-059 **no cambia**.

Lo que sí cambia es todo lo demás:

| | Judge0 / `isolate` | Docker directo |
|---|---|---|
| Contenedor privilegiado | **Requerido** | **No** |
| Capabilities | Las del contenedor privilegiado | `--cap-drop=ALL` |
| cgroups v1 | **Requerido** | No, funciona con v2 |
| CVE de escape propios | 2, ambos CVSS 10.0 | Ninguno propio; los de Docker, que la plataforma ya asume |
| Piezas a operar | API + workers + Postgres + Redis propios | Ninguna: el Docker que ya corre |
| Costo | Plan cloud o servidor aparte | Cero |

Un contenedor sin privilegios, sin capabilities, sin red, read-only y con usuario no-root es una **superficie estrictamente menor** que un contenedor privilegiado. Por eso este ADR puede levantar la restricción de D2 del ADR-059: **el sandbox puede convivir con el resto de la plataforma**, porque ya no hay un proceso privilegiado al lado de las bases.

### D2 — Medido, no estimado

El spike (`scripts/spike-docker-runner.py`) corrió sobre la máquina de desarrollo el 2026-07-29:

| Escenario | Resultado |
|---|---|
| Compila y ejecuta | **0,76 s**, `exit=0`, stdout correcto |
| No compila | **0,56 s**, error de `javac` con el formato real (`Main.java:1: error: ';' expected`) |
| Bucle infinito | **cortado a los 10 s** por el límite de wall time |
| Salida a internet | **bloqueada** |
| **10 concurrentes** | total **1,42 s** · p50 1,35 s · **10/10 ok** |
| **30 concurrentes** | total **4,98 s** · p50 4,58 s · **30/30 ok** |

**Esto invalida el dimensionamiento de la tarea 1.6 del change**, que estimaba ~3 s por corrida y pedía ≥6 ejecuciones concurrentes. La medición real es sustancialmente mejor: una comisión entera (30 alumnos) ejecutando en la misma ventana se resuelve en **~5 segundos**.

El formato del error de compilación es además el que `web-student/src/lib/javaError.ts` ya sabe parsear: el módulo escrito para Judge0 funciona sin cambios.

### D3 — El riesgo se mueve, no desaparece: quién puede invocar `docker run`

**Este es el punto que el ADR-060 debe resolver antes de ir a producción.**

Si el `execution-service` monta `/var/run/docker.sock`, quien comprometa ese servicio tiene **control total del host** — sería peor que el problema original. La contención del contenedor no importa si el proceso que lo lanza puede lanzar cualquier otro.

Dos salidas, a decidir en la implementación:

1. **Socket-proxy restringido** (ej. `tecnativa/docker-socket-proxy` o equivalente) que solo permita `POST /containers/create` + `start` sobre **una imagen fija**, sin `--privileged` ni montajes arbitrarios.
2. **El invocador vive fuera de contenedor**, como servicio del host con un usuario dedicado en el grupo `docker`.

Mientras esto no esté resuelto, la ejecución de Java **no se habilita en producción**. Es el equivalente al gate que el ADR-059 puso sobre sí mismo.

## Controles obligatorios

Los del ADR-059 siguen vigentes, re-expresados para este motor. Se verifican sobre el despliegue real, no se asumen.

| # | Control | Cómo se cumple acá |
|---|---|---|
| **C1** | Versión mínima del sandbox | Imagen **pineada por digest**, no por tag. Un tag mutable permite que cambie el JDK bajo los pies. |
| **C2** | Red deshabilitada | `--network=none`, fijado server-side y no configurable por el caller. **Verificado en el spike.** |
| **C3** | Credenciales no predeterminadas | No aplica: no hay Postgres ni Redis propios del sandbox. Se reemplaza por **C3'**: el acceso al daemon de Docker es restringido (D3). |
| **C4** | El sandbox no alcanza la red interna | `--network=none` lo garantiza por construcción, no por configuración de firewall. |
| **C5** | Monitoreo de costo | Deja de ser costo de proveedor y pasa a ser **capacidad**: CPU y memoria del host. Se monitorea igual — la saturación degrada al resto de la plataforma. |

Controles nuevos que este motor habilita y conviene fijar:

- **C6** — `--cap-drop=ALL` y `--security-opt=no-new-privileges`.
- **C7** — usuario no-root dentro del contenedor.
- **C8** — `--read-only` con un único `tmpfs` acotado para los `.class`.
- **C9** — timeout externo además del límite del contenedor: `docker run` también se puede colgar si el daemon no responde.

## Consecuencias

**Positivas**

- **Sin contenedor privilegiado.** Es el cambio que más mueve la aguja: desaparece la razón por la que el sandbox tenía que vivir lejos de la plataforma.
- **Sin costo recurrente** y sin dependencia de un tercero en el camino crítico del alumno.
- **Funciona en la infraestructura que ya existe**, incluida la máquina de desarrollo: se pueden verificar de verdad las propiedades de seguridad, en vez de contra un doble.
- **Menos piezas que operar** en un piloto sin administrador de sistemas dedicado — que era el argumento original del ADR-033 para no hacer nada server-side.
- La respuesta ante el tribunal se simplifica: "sin privilegios, sin red, sin capabilities, usuario no-root, límites explícitos" es más fácil de defender que justificar un contenedor privilegiado.

**Negativas, aceptadas**

- **Hay que escribir el runner** (~200 líneas). El design del change lo declaraba non-goal, pero ese non-goal asumía que Judge0 era el camino sin fricción, y resultó no levantar en distros modernas.
- **Sin catálogo de lenguajes.** Judge0 trae ~60; acá cada lenguaje nuevo es una imagen y un comando. Para el alcance real —Python (que sigue en Pyodide) y Java— no es una pérdida.
- **El acceso al daemon de Docker es el nuevo punto sensible** (D3). Se resuelve antes de producción.
- **Kernel compartido**: igual que Judge0. No es una regresión, pero tampoco una mejora en esa dimensión.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| **Judge0 gestionado** (ADR-059) | Funciona, pero cuesta, agrega dependencia externa y su versión hay que verificarla con el proveedor. Sigue siendo el plan B si el runner propio da problemas. |
| **Judge0 autoalojado** | Suma el contenedor privilegiado y la exigencia de cgroups v1 sobre infraestructura propia. Lo peor de los dos mundos. |
| **gVisor** | Aislamiento estrictamente más fuerte (kernel propio en espacio de usuario). Sigue siendo la respuesta si el aislamiento pasa a ser requisito duro; es compatible con este diseño, porque `docker run --runtime=runsc` es un cambio de una bandera. **Camino de evolución natural.** |
| **Piston** | Más liviano que Judge0 pero sigue siendo un servicio a operar, sin ventaja clara sobre invocar Docker directo. |

Vale registrar lo último: elegir Docker directo **no cierra la puerta a gVisor**. Si más adelante el aislamiento tiene que ser más fuerte, se instala `runsc` y se agrega una bandera al comando. Con Judge0 esa evolución no existía.

## Verificación

Antes de habilitar en producción:

- [ ] D3 resuelto: acceso al daemon de Docker restringido (socket-proxy o invocador fuera de contenedor)
- [ ] Imagen pineada por digest (C1)
- [ ] Red bloqueada, comprobada con un ejercicio que intente salir (C2) — *ya verificado en el spike*
- [ ] Contenedor sin capabilities ni escalada de privilegios (C6)
- [ ] Usuario no-root (C7)
- [ ] Prueba de carga sobre el hardware real de producción, no sobre la máquina de desarrollo
- [ ] Habilitación progresiva: una comisión antes que todas

## Referencias

- [ADR-059](059-aislamiento-ejecucion-java-judge0-gestionado.md) — decisión previa (Judge0 gestionado), que este ADR reemplaza en la elección de motor.
- [ADR-033](033-sandbox-pyodide-only-piloto-1.md) — Pyodide-only en piloto-1. Python no se toca.
- `scripts/spike-docker-runner.py` — el spike que produjo las mediciones de D2.
- `apps/execution-service/src/execution_service/services/docker_runner.py` — implementación del runner.
