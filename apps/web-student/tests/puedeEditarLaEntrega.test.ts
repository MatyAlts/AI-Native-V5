/**
 * "¿Puedo mandarla sola?" y "¿el alumno puede seguir laburando?" son DOS preguntas.
 *
 * EL BUG (QA 2026-08-31)
 * ----------------------
 * `ExerciseListView` usaba `debeEnviarLaEntrega` para las dos, y difieren justo
 * en `returned`:
 *
 *   - `debeEnviarLaEntrega` contesta "¿la mando SOLO porque el alumno salió del
 *     episodio?". Ahí `returned` tiene que dar false, porque el envío automático
 *     pasa la entrega a `submitted` y le BORRA la devolución que vino a leer.
 *     Ese bug ya se cerró y su test vive en `debeEnviarLaEntrega.test.ts`.
 *
 *   - `puedeEditarLaEntrega` contesta "¿el alumno puede abrir un ejercicio y
 *     apretar Entregar?". Ahí `returned` tiene que dar TRUE: devolver un TP es
 *     justamente pedirle que lo retome.
 *
 * Con una sola función para las dos, el botón "Devolver al estudiante" le
 * mostraba al alumno el cartel
 *
 *     "Devuelta para revisar. Tu docente devolvió la entrega con observaciones."
 *
 * y le sacaba TODAS las herramientas para revisar: ni botón de ejercicio ni
 * botón de entregar. Un docente podía pasarse semanas devolviendo TP creyendo
 * que los alumnos los recibían para corregir.
 *
 * El backend nunca se confundió: `submit_entrega` y `mark_ejercicio_completado`
 * aceptan `draft` Y `returned` desde siempre. El único que las mezclaba era el
 * frontend — y como el frontend es el que dibuja los botones, era el que
 * decidía.
 */
import { describe, expect, it } from "vitest"
import { debeEnviarLaEntrega, puedeEditarLaEntrega } from "../src/lib/entregaGuard"

describe("puedeEditarLaEntrega", () => {
  it("returned SI se puede editar", () => {
    // El corazón del fix. Verificado por reversión: con
    // `estado === "draft"` esto da false y el alumno recibe la devolución sin
    // un solo botón con el que responderla.
    expect(puedeEditarLaEntrega("returned")).toBe(true)
  })

  it("draft se puede editar", () => {
    expect(puedeEditarLaEntrega("draft")).toBe(true)
  })

  it("submitted y graded NO", () => {
    // Ya está en manos del docente. Dejar editar acá cambiaría lo entregado
    // después de entregado, y el hash del artefacto dejaría de certificar el
    // momento que la entrega declara.
    expect(puedeEditarLaEntrega("submitted")).toBe(false)
    expect(puedeEditarLaEntrega("graded")).toBe(false)
  })

  it("un estado desconocido NO habilita nada", () => {
    // Default cerrado: si mañana aparece un estado nuevo, el frontend no lo
    // trata como editable por omisión.
    expect(puedeEditarLaEntrega("en_revision")).toBe(false)
    expect(puedeEditarLaEntrega("")).toBe(false)
  })
})

describe("las dos preguntas no son la misma", () => {
  it("difieren EXACTAMENTE en returned", () => {
    // Este es el test que documenta por qué existen las dos. Si alguien las
    // unifica "para simplificar", acá se entera de cuál de los dos bugs
    // está reabriendo.
    const estados = ["draft", "returned", "submitted", "graded", ""]
    const distintos = estados.filter((e) => debeEnviarLaEntrega(e) !== puedeEditarLaEntrega(e))

    expect(distintos).toEqual(["returned"])
  })

  it("returned: no se manda sola, pero el alumno la puede trabajar", () => {
    expect(debeEnviarLaEntrega("returned")).toBe(false)
    expect(puedeEditarLaEntrega("returned")).toBe(true)
  })
})
