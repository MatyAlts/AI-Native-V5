# Veredicto de revisión — `copiar-pegar-interno-en-el-episodio`

**2026-09-30.** Tres pases: implementador, QA y auditor. Este archivo existe
porque el auditor señaló que, sin él, **los nueve hallazgos de QA y los cinco
cambios posteriores no dejaban rastro en el repo** — vivían sólo en una
conversación.

---

## EVIDENCIA — estado final

```
$ cd apps/web-student && npx vitest run
  Test Files  47 passed (47)
  Tests  554 passed (554)                              (2026-09-30 16:59)
$ npx tsc --noEmit                                     → limpio
$ uv run pytest apps packages -q
  10 failed, 2675 passed, 100 skipped                  (2026-09-30 17:05)
```

> **Nota sobre esta cifra, y es una corrección.** El informe del orquestador
> había reportado `851 passed` — que es contracts + tutor + classifier +
> governance, una superficie **más chica** que la que el implementador ya había
> corrido (`apps -q` → 2271), y **sin los 10 fallos en la línea final**. El
> auditor lo marcó: reportar una superficie menor que el baseline, con los
> fallos caídos del resumen, hace que el estado se lea mejor de lo que es. Acá
> va la superficie completa, con los 10 adentro.

**Los 10 fallos son PREEXISTENTES.** QA no se conformó con «el diff no tocó
esos archivos»: revirtió `packages/contracts` al estado previo y volvió a
correrlos — los mismos 10, con el contrato viejo. Ese es el método correcto,
porque esos servicios **importan** contracts.

---

## Lo que QA encontró y se cerró

| # | Hallazgo | Cómo se cerró |
|---|---|---|
| 1 | **String mágico**: renombrar `data-tour="tutor-chat"` dejaba ADR-026 roto con 548 tests verdes. Cuatro consumidores, no dos | **Invertido a ALLOWLIST** (`data-copiable-interno`). El mismo accidente ahora **falla cerrado**: la consigna deja de ser copiable y degrada al comportamiento previo, en vez de volver pegable el código del tutor. Más `AllowlistCopiableInterno.test.ts`, que ata productor y consumidor |
| 2 | `copia_intentada` se podía borrar entero sin que ningún test lo notara | Test nuevo: el rastro de auditoría del copiado no puede desaparecer |
| 3 | **`metodo` mentía en las dos direcciones**: Ctrl+V, el camino más común, se registraba como «menú contextual», y tres tests lo cementaban | `metodoDeClipboard()` lo recupera mirando si hubo un `contextmenu` reciente. Las tres aserciones corregidas al valor honesto |
| 5 | **Editor→editor probablemente roto en navegador**: el change sacó el lector que sirve para Monaco y dejó `window.getSelection()`, que devuelve `""` dentro del textarea oculto | Vuelve a `editor.getSelection()` + `getModel().getValueInRange()`. El mock ahora modela esa selección, así que la costura es observable |
| 6 | **🔴 FUGA A de ADR-026**: `closest()` mira dónde EMPEZÓ la selección, no qué CONTIENE. Ctrl+A capturaba el panel del tutor | Se exige que la selección esté **contenida** en la región permitida. Test dedicado, verificado por mutación |
| 7 | **FUGA B**: un target de tipo `Text` esquivaba la exclusión porque `closest` sólo existe en `Element` | El allowlist normaliza a `Element` antes de consultar |
| 4 | `copia_intentada` cambió de significado y el docstring quedó falso | **Cerrado tras la auditoría** — ver abajo |

## Lo que el auditor encontró, sobre los informes

1. **El punto 4 de QA no se había tocado ni declarado.** `events.py` seguía diciendo *«bloqueado por la UI»* sobre un evento que ahora sale en un copiado exitoso. **Corregido**: el docstring explica el cambio de significado y advierte que **la serie no es continua** — cortar por `event_type` sin cortar por fecha mezcla intentos fallidos con copiados reales. El `event_type` no se renombra porque está en la cadena firmada de los episodios históricos.
2. **La tercera aserción del guardián pasaba vacía.** Estaba anclada en `indexOf('data-tour="tutor-chat"')`; con el atributo renombrado daba `-1`, el slice se volvía `slice(0,399)` y la aserción pasaba sin verificar nada. **Corregido**: ancla en el `aria-label`, y **falla ruidosamente** si el ancla se rompe. Verificado por mutación.
3. **El informe del orquestador no tenía sección de supuestos**, con tres puntos abiertos debajo. Corregido en la sección siguiente.
4. **El precedente citado para activar v1.9.0 es 2 de 3, no 3 de 3**: v1.6.0 y v1.7.0 tienen `OK (2026-09-28)` en el manifest; **v1.8.0 nunca cerró su revisión** y v1.9.0 ya pasó por encima.

---

## 🔴 LO QUE QUEDA ABIERTO — declarado, no cerrado

**Nada de esto se probó en un navegador real.** Los builds están prohibidos por
las reglas del proyecto y el mock de Monaco **no modela teclado ni textarea
oculto**. Lo que la suite prueba es qué hace el listener *cuando el evento
llega*; **no prueba que llegue**.

El supuesto de fondo sigue exactamente igual de no verificado que antes de
escribir los 17 tests: *sacar los `addCommand` deja que el evento nativo llegue
al DOM*.

**Los cuatro casos a probar en navegador antes de confiar en esto:**

1. Ctrl+V con algo externo → ¿aparece el cartel de bloqueo? *(¿llega el evento?)*
2. Seleccionar en la consigna → Ctrl+C → Ctrl+V en el editor → ¿pega? *(el caso que motiva el change)*
3. Seleccionar en Monaco → Ctrl+C → Ctrl+V → ¿pega? *(la fuga de `getSelection`)*
4. **Ctrl+A → Ctrl+C → Ctrl+V → ¿entra el código del tutor?** *(FUGA A)*

**Otros abiertos:**

- **Consigna→editor no se probó contra el componente real.** Los tests usan un
  stub, nunca `EnunciadoPanel`. Lo que se prueba es «un div marcado como
  copiable funciona».
- **`edicionPendiente.ts` no lo revisó nadie.** Cambió un tipo público
  (`paste: boolean` → `PasteOrigen`) y reescribió la precedencia de `origin`,
  que es la señal que alimenta el override N4 del labeler. Pasó por tres
  informes sin que ninguno lo nombrara.
- **El prompt v1.9.0 entero, el puntero activo del manifest y
  `config.py` tampoco los abrió nadie.** Es justo la superficie que toca la
  regla dura del proyecto: coautoría de Ana Garis.
- **Renombrar `data-copiable-interno` sigue sin romper los tests de
  comportamiento** — sólo el guardián. El allowlist hace que falle cerrado, que
  es lo que importa, pero la detección viene de un test de fuente, no de uno
  funcional.

---

## No es una barrera de seguridad, y nunca lo fue

Las devtools lo saltean en diez segundos, igual que el bloqueo anterior. Lo que
sostiene la tesis **no es que el alumno no pueda**, es que **todo queda
registrado con su procedencia en la cadena**. Cualquier redacción que afirme lo
primero es falsa.

## ADR-026 se respeta

El panel del tutor **no** entra al allowlist, y `copied_from_tutor` sigue sin
emitirse. Los criterios del ADR para revisitarlo —cohorte nueva, decisión
académica de estudiarlo como variable, o post-defensa con acuerdo del comité—
no se cumplen hoy, y esa es una conversación con el director de tesis.
