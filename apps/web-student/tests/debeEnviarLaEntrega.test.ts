/**
 * BUG-1: la entrega se re-enviaba sola y borraba la devolucion del docente.
 *
 * La cadena completa, que es lo que hace que esto sea grave y no cosmetico:
 *
 *   1. El docente califica una entrega y la DEVUELVE para corregir
 *      (`graded` -> `returned`). El alumno puede volver a editar.
 *   2. El alumno entra al episodio para leer la devolucion.
 *   3. La hidratacion de `EpisodePage` ve `estado === "closed"` y llama a
 *      `onExit()` **sola**, sin que el alumno apriete nada.
 *   4. `handleExit` crea/obtiene la entrega y, con el guard viejo
 *      (`draft || returned`), la re-envia: `returned` -> `submitted`.
 *   5. La devolucion del docente desaparece.
 *
 * El alumno abre el episodio para LEER lo que le escribieron, y el solo hecho
 * de abrirlo se lo borra. Nadie apreto nada.
 */

import { describe, expect, test } from "vitest"
import { debeEnviarLaEntrega } from "../src/routes/episodio.$id"

describe("BUG-1 — una entrega devuelta NO se re-envia sola", () => {
  test("`returned` no se re-envia", () => {
    // El corazon del bug. Si esto vuelve a dar true, se borran devoluciones.
    expect(debeEnviarLaEntrega("returned")).toBe(false)
  })

  test("`draft` si se envia: para la TP monolitica, cerrar el episodio ES entregar", () => {
    // El otro lado. Sin esto la card del selector se queda en "Empezar" aunque
    // el alumno haya terminado, y el fix de arriba habria roto el flujo normal.
    expect(debeEnviarLaEntrega("draft")).toBe(true)
  })

  test("una entrega ya enviada o calificada no se toca", () => {
    expect(debeEnviarLaEntrega("submitted")).toBe(false)
    expect(debeEnviarLaEntrega("graded")).toBe(false)
  })

  test("un estado que no conocemos NO dispara un envio", () => {
    // Falla cerrado: el dia que aparezca un estado nuevo, el default seguro es
    // no enviar. Enviar por defecto es como aparecio este bug.
    expect(debeEnviarLaEntrega("en_revision")).toBe(false)
    expect(debeEnviarLaEntrega("")).toBe(false)
  })
})
