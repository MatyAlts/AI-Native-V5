# STATUS — editor-muestra-codigo-entregado-al-reabrir

Fecha: 2026-10-28. Rama `feat/editor-muestra-codigo-entregado` sobre `origin/main` 18bffe9 (independiente del PR #126).
PR #122 estaba ABIERTO al aplicar: `getEntregaArtefacto` y sus tipos se copiaron IDENTICOS desde `origin/feat/alumno-mis-trabajos-corregidos`
(`diff` del `api.ts` completo contra el de esa rama: sin diferencias).

## 1.1 Linea base (web-student, origen/main)

| Chequeo | Resultado |
|---|---|
| `pnpm test` | 63 archivos, 675 passed |
| `tsc --noEmit` | limpio |
| `biome check src` | 18 errores en main (CRLF preexistente, incluye `index.css`); 15 en este checkout. Ninguno en archivos tocados |

## Final (6.2)

| Chequeo | Resultado |
|---|---|
| `pnpm test` | 65 archivos, 702 passed (+27: 6 cascada, 11 siembra, 10 cierre) |
| `tsc --noEmit` | limpio |
| `biome check` sobre los archivos tocados | limpio |

## 1.2 Reproduccion manual ANTES del fix

NO hecha con la UI (sin navegador en esta sesion). Lo que si se hizo: el test `TpDevueltaCerrarSinEditar.test.tsx` se corrio
contra el guard viejo (`if (!hayCodigo) return` sin la rama nueva) y dio 5 rojos por 0 PATCH, o sea reproduce el bloqueo
("cerrar sin tipear no marca"). Falta que un humano mire el paso 6 de `design.md` con la UI real.

## Negativos probados rojos (quitando su condicion)

- Match por `ejercicio_id` en `codigoEntregadoDe`: 1 rojo ((b) artefacto de otro ejercicio).
- Condicion `!borradorLocal && !state.last_code_snapshot` (pedir el artefacto siempre): 2 rojos ((a), (a')).
- `huboEdicionRef` ("edito y lo dejo vacio"): 1 rojo ((b)).
- Chequeo de origen (`snapshot`/`codigo-entregado`): 2 rojos (scaffold y placeholder).

## Decisiones

- Snapshot heredado vs codigo sellado distintos: gana el snapshot (D1 default; no se toca tutor-service).
- Resolucion del candidato extraida a `src/lib/codigoEntregado.ts` (funcion pura, 5.1).
- `ejercicioIdCtx` se deriva como primitivo fuera del efecto de hidratacion y entra a sus deps (igual criterio que `entregaId`).
- Los caminos de cierre "Siguiente ejercicio" y cierre del ReflectionModal comparten `markEjercicioCompletedOnce`: se prueban
  el cierre directo, la deduplicacion y el reintento por "Siguiente" cuando el primer PATCH falla.
- 6.5: el encabezado del main spec lo arregla el PR del otro change (tarea 7.5 alla); no se toca aca para no chocar.

## 6.1 Tesis

`git diff origin/main --stat -- apps/ctr-service apps/classifier-service packages/contracts ai-native-prompts apps/tutor-service apps/web-student/src/components/CodeEditor.tsx apps/web-student/src/lib/edicionPendiente.ts` -> VACIO.
`git diff origin/main --stat` solo toca `apps/web-student` y `openspec/`.
Tests de no-emision: cargar el codigo entregado y esperar > debounce -> 0 `edicion_codigo`; teclear una letra -> 1 con `diff_chars` 1.

## 6.3 Prueba local

Ver `prueba-local.md`. Verificado contra backend real solo el contrato `GET /entregas/{id}/artefacto`; la UI queda para un humano.

## 6.4 Aviso a Cortez (borrador)

Junto con el aviso del change `publicar-nota-y-pedir-correccion`: (1) el primer `edicion_codigo` de reaperturas con cadena cortada
ahora arranca del codigo entregado en vez del scaffold, y `diff_chars` mide solo lo que el alumno cambio (REAPERTURA ya lo hacia en el
caso comun desde el 24/09); (2) ejercicios cerrados sin cambios pasan a contar como completados (episodios cortos sin `edicion_codigo`).
El instrumento no cambia.
