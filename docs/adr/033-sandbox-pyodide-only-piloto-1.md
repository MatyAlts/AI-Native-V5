# ADR-033 — Sandbox de tests: Pyodide-only en piloto-1

- **Estado**: Aceptado
- **Fecha**: 2026-05
- **Deciders**: Alberto Cortez, director de tesis
- **Tags**: sandbox, testing, frontend, seguridad
- **Epic**: ai-native-completion-and-byok / Sec 9

## Contexto y problema

El piloto necesita que el alumno pueda **auto-validar** su código contra tests
del docente — sin esto, la TP queda ciega a feedback inmediato y el alumno
depende del tutor para saber si su código funciona. Hay dos formas de armar el
sandbox:

1. **Client-side (Pyodide en el browser)**: el codigo y los tests corren en
   WebAssembly dentro del browser del alumno. Sin round-trip al servidor.
2. **Server-side (`sandbox-service` nuevo)**: el codigo viaja al backend, se
   ejecuta en un container con isolation (gVisor o equivalente), y los
   resultados vuelven al frontend.

## Drivers de la decisión

- **Velocidad de iteración del alumno**: Pyodide tiene latencia ~ms; server-side
  agrega ~hundreds de ms (red + container spinup).
- **Surface de seguridad**: server-side requiere isolation para evitar escape
  via `os.system`, syscalls, network. Es un componente nuevo a operar.
- **Tests hidden**: el spec exige que los tests `is_public=false` queden opacos
  al alumno (no expuestos en dev tools). Pyodide los expone si el frontend los
  recibe; server-side los puede ejecutar sin transferirlos.
- **Recursos del piloto**: no hay sysadmin dedicado al piloto-1. Operar un
  servicio adicional (puerto 8013, container isolation, monitoreo) es overhead.

## Opciones consideradas

### Opción A — Pyodide-only (elegida)

Tests publicos viajan al cliente y corren ahi. Tests hidden quedan en
`tareas_practicas.test_cases JSONB` con `is_public=false` y el endpoint
`GET /tareas-practicas/{id}/test-cases?include_hidden=false` los filtra antes
de mandar al cliente. **El backend NO ejecuta tests en piloto-1** — los hidden
son metadata para review manual del docente.

**Trade-off explicito**: el alumno con dev tools puede ver el codigo de los
tests publicos. Esto es aceptable porque tests publicos sirven de **especificacion**
visible — no son secreto.

### Opción B — Híbrido Pyodide + sandbox-service

Mejor cobertura (tests hidden ejecutables) pero requiere construir el
`sandbox-service` con container isolation, lo cual abre superficie de seguridad
sin necesidad pre-defensa.

## Decisión

**Pyodide-only en piloto-1**. Hidden tests quedan como metadata de docente
sin ejecucion automatica. Si en piloto-2 los docentes piden ejecucion real
de hidden, se desbloquea con ADR especifico de isolation (ej. gVisor).

## Consecuencias

### Positivas

- Latencia minima del feedback de tests al alumno.
- Sin componente nuevo que operar.
- Sin superficie de seguridad nueva (Pyodide corre en sandbox del browser).

### Negativas / trade-offs

- Tests `is_public=false` no se ejecutan automaticamente en piloto-1 — el
  docente los corre manual sobre los repos entregados o los pasa a piloto-2.
- El alumno con dev tools puede ver tests publicos (pero esto es by-design —
  son spec visible).
- Pyodide tarda ~5-10s en cargar el primer request — mitigado con lazy load
  + spinner explicito.

### Neutras

- Endpoint `GET /tareas-practicas/{id}/test-cases` filtra por rol: estudiante
  con `include_hidden=true` => 403, default `include_hidden=false` omite tests
  con `is_public=false`.
- El classifier IGNORA resultados de tests `is_public=false` (declarado en
  `_EXCLUDED_FROM_FEATURES` del pipeline). Preserva reproducibilidad bit-a-bit.

## Referencias

- Spec: `openspec/changes/ai-native-completion-and-byok/specs/sandbox-test-cases/spec.md`
- Pyodide docs: https://pyodide.org
- Spec del classifier: ADR-033 / ADR-034 / `apps/classifier-service/.../pipeline.py`
