# Tareas — eliminar ED-4

## 0. Red de seguridad (antes de tocar nada)

- [x] 0.1 `npx vitest run` en `apps/web-student`. Anotar el baseline exacto.
      Esperado: 573 passed / 45 files. **Si algo ya falla, PARAR y reportarlo
      como falla preexistente** — no arreglarlo.

## 1. RED — la politica nueva, antes del cambio

- [x] 1.1 Test: un ejercicio **sin** `inicial_codigo`, con codigo guardado de un
      ejercicio anterior de la misma TP, abre con el **placeholder del lenguaje**
      y no con lo heredado. Debe fallar hoy.
- [x] 1.2 Test: la cascada ya no consulta `codigoPrevio` en ninguna rama.

## 2. GREEN — sacar las dos mitades

- [x] 2.1 `cascadaCodigo.ts` — sacar el eslabon `codigoPrevio`.
- [x] 2.2 `codigoPrevio.ts` — `resolverSiembra` (lee) y `resolverCodigoAPersistir`
      (escribe). **Las dos.**
- [x] 2.3 `EpisodePage.tsx` — hidratacion (:548-570),
      `persistirCodigoParaElProximoEjercicio` (:699) y sus dos llamadas (:737
      cerrar, :790 pausar).
- [x] 2.4 Limpiar lo que quede huerfano: tipos, funciones, claves de
      `sessionStorage`, imports. Una limpieza a medias deja codigo muerto que el
      proximo lee como vivo.

## 3. TRIANGULA — que los tres casos legitimos sigan andando

- [x] 3.1 Con scaffold de TP: gana el scaffold.
- [x] 3.2 Con scaffold de ejercicio: gana el scaffold.
- [x] 3.3 Con `snapshot` del propio episodio: gana el snapshot (F5, pausa,
      breakpoint mobile). Cotejar contra `CodeEditorRemonte.test.tsx`.
- [x] 3.4 REAPERTURA: el alumno no pierde lo escrito al reabrir un ejercicio
      cerrado.
- [x] 3.5 Sin nada de lo anterior: placeholder del lenguaje.

## 4. Los 59 tests de ED-4

- [x] 4.1 Reescribir a la politica nueva, **no borrar**. Un test que decia «el
      scaffold de la TP le gana al codigo del ejercicio anterior» ahora dice «no
      existe codigo del ejercicio anterior; con scaffold gana el scaffold, sin
      scaffold gana el placeholder».
- [x] 4.2 Si un archivo queda sin razon de existir, borrarlo **y decirlo
      explicitamente** en el reporte, con cuantos tests se fueron y por que
      ninguno cubria algo que sobreviva.

## 5. Verificacion

- [x] 5.1 `npx vitest run` en verde, con el comando y el conteo antes/despues,
      y la diferencia explicada: cuantos reescritos, cuantos borrados, cuantos
      nuevos.
- [x] 5.2 Diff completo para revision humana.
- [x] 5.3 **NO correr builds** — prohibido por las reglas del proyecto.

## Fuera de alcance

- Los episodios ya contaminados (consulta SQL, despues del deploy).
- El backend. El contrato del CTR no cambia.
