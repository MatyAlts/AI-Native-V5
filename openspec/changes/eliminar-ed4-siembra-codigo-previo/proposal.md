## Why

**El campo vacio tambien es una decision del docente**, y ED-4 la reinterpreta
como un silencio.

`inicial_codigo` existe para que el docente elija que ve el alumno al abrir el
episodio. Cuando lo deja vacio esta eligiendo "que arranque vacio". ED-4 lee ese
vacio como "no se expreso" y siembra el editor con el codigo del ejercicio
anterior de la misma TP.

Decision del dueno del producto, 2026-09-28, textual:

> «No quiero que el alumno tenga el codigo de ejercicios anteriores. Para algo
> existe `inicial_codigo`: el docente elige que ve el alumno al arrancar el
> episodio.»

### Y hay un segundo motivo, que no se ve

El evento `edicion_codigo` del CTR lleva
`origin: Literal["student_typed", "copied_from_tutor", "pasted_external", "snippet_expanded"] | None`
(`packages/contracts/src/platform_contracts/ctr/events.py:324-325`).
**Ninguno de los cuatro significa "heredado del ejercicio anterior".**

La siembra entra muda: el alumno toca una tecla y el primer `edicion_codigo` se
va a la **cadena criptografica append-only** con el codigo heredado adentro,
indistinguible de lo que escribio el. De ahi lo levanta `tutor_core.py:1318-1321`
como `current_code`, el tutor lo lee como del alumno, y el classifier saca
features sobre eso. **Es contaminacion del dato que sostiene la tesis.**

### Evidencia

- **Video del 2026-09-28**: el editor abre con 7 lineas heredadas y el alumno las
  selecciona todas para borrarlas a mano — copiar y pegar esta bloqueado en la
  plataforma. La linea 1 es exactamente
  `LANGUAGE_PLACEHOLDER.python` (`apps/web-student/src/lib/api.ts:774`), que es el
  **ultimo** eslabon de la cascada: prueba que el ejercicio de origen tampoco
  tenia `inicial_codigo`.
- El ejercicio del video **no esta entre los 25 del piloto**. Es una TP donde el
  docente dejo el campo vacio, y `apps/web-teacher/src/views/EjerciciosView.tsx:820`
  convierte el campo vacio en `null`.
- ED-4 se construyo el **2026-08-27** (`1b70b29`, fecha de autor). Ventana de
  contaminacion: ~32 dias.

## What Changes

Se saca **el cuarto eslabon** de la cascada, y solo ese.

- `cascadaCodigo.ts:66-76` — `resolverCascadaDeCodigo` deja de consultar
  `codigoPrevio`.
- `codigoPrevio.ts:118` — `resolverSiembra`, la mitad que LEE.
- `codigoPrevio.ts:160` — `resolverCodigoAPersistir`, la mitad que ESCRIBE.
- `EpisodePage.tsx:548-570` (hidratacion), `:699`
  (`persistirCodigoParaElProximoEjercicio`), `:737` (cerrar), `:790` (pausar).

**Las dos mitades salen juntas.** Dejar la que escribe sin la que lee acumula
basura en `sessionStorage` sin lector, y eso es peor que no tocarlo porque parece
intencional.

Con ED-4 fuera, un ejercicio con `inicial_codigo: null` cae al **placeholder del
lenguaje**. Eso es exactamente el comportamiento pedido.

### Lo que NO se toca — tres casos legitimos

1. **`snapshot` del propio episodio** (`cascadaCodigo.ts:67`, prioridad 1). F5,
   volver de una pausa, cruzar el breakpoint mobile. Pisarlo es borrarle trabajo
   al alumno. Test dedicado: `CodeEditorRemonte.test.tsx`.
2. **Los scaffolds del docente** (prioridades 2 y 3). Son literalmente la
   decision que esta change protege.
3. **REAPERTURA** (`apps/tutor-service/routes/episodes.py:511-528`). Reabrir un
   ejercicio cerrado crea un episodio nuevo sin eventos; sin el fallback el
   alumno pierde lo escrito. Esta scopeado al **mismo** ejercicio, asi que no es
   ED-4.

   > **Nota de QA, 2026-09-28**: el informe del implementador cito
   > `ExerciseListViewDevolucion.test.tsx` como verificacion de este caso, y
   > ese archivo prueba otra cosa (que el boton «Volver a abrir» aparece y
   > que manda `completado: false`). **REAPERTURA es 100% backend** y no lo
   > alcanza un test de React. La verificacion correcta son los 4 tests de
   > `apps/tutor-service/tests/unit/test_get_episode_state.py -k reapertura`,
   > que QA corrio en verde. La conclusion se sostiene; la evidencia citada
   > apuntaba al archivo equivocado.

## Impact

- **`apps/web-student`**: los 4 archivos de arriba. Baseline de la suite:
  **573 passed / 45 files** (2026-09-28).
- **59 tests en 4 archivos especifican ED-4** y hay que **reescribirlos a la
  politica nueva, no borrarlos**: `cascadaCodigo.test.ts` (tiene un `describe`
  llamado «LA regla: el arrastre no pisa al docente»), `codigoPrevio.test.ts`,
  `CodigoPrevioSiembra.test.tsx`, `CodigoPrevioPersistencia.test.tsx`.
- **Sin cambios de backend.** El contrato del CTR no cambia.
- **Sin migracion.**

## Gobernanza

Nivel **MEDIO**: logica de negocio de cara al alumno. Se implementa con
checkpoints; el diff se revisa antes del deploy.

## Fuera de alcance

**Los episodios ya contaminados.** Desde el 2026-08-27 hay episodios en la cadena
con codigo de otro ejercicio adentro, firmados como si fueran del alumno. Esta
change corta la sangre; no limpia lo que ya entro. La deteccion es una consulta
SQL sobre el CTR (el primer `edicion_codigo` de un episodio empieza con el ultimo
codigo de otro episodio del mismo alumno y la misma TP) y va por separado, contra
la base real, despues del deploy.
