/**
 * Tests de RevisionColaView (B3+B5, tarea 5.7).
 *
 * Cubre:
 * - La cola agrupa por los cuatro estados NOMBRADOS del juez (inconsistente,
 *   abstencion_traza_insuficiente, error_parseo, baja_confianza), en ese orden.
 * - Un grupo sin episodios no se renderiza.
 * - `abstencion_traza_insuficiente` (caso 4 de la Tabla 3.11 — agregado por el
 *   juez trivaluado, `regimen_llm.py:243`) cae en SU grupo nombrado, no en el
 *   defensivo. Esto es una guarda hacia adelante y no una regresión: hoy el
 *   corpus todavía se clasificó con la regla booleana vieja y este estado no
 *   aparece en producción — el test certifica que cuando aparezca, la
 *   pantalla no lo esconde.
 * - Un `estado_juez` que NO existe en el `Literal` del backend (ej. un sexto
 *   estado agregado ahí y no acá) cae en el grupo defensivo con el copy de
 *   DESINCRONIZACIÓN backend/frontend — no un copy sobre el episodio. También
 *   guarda hacia adelante: hoy no hay ningún estado sin nombrar.
 * - Una decisión exitosa saca la fila de la cola.
 * - 400 (verdict fuera de dominio) muestra el error tal cual lo manda el backend.
 * - 409 con `retryable: true` (ganó el pipeline) vs `retryable: false` (ganó otro
 *   docente) muestran mensajes DISTINTOS.
 * - El estado vacío no afirma que "todo está revisado" — dice que no hay
 *   retenidos EN ESTE MOMENTO (principio 5, honestidad técnica).
 */
import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, test, vi } from "vitest"
import { RevisionColaView } from "../src/views/RevisionColaView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const fakeGetToken = async () => "test-token"

const EP_INCONSISTENTE = "11111111-1111-1111-1111-111111111111"
const EP_ERROR_PARSEO = "22222222-2222-2222-2222-222222222222"
const EP_BAJA_CONFIANZA = "33333333-3333-3333-3333-333333333333"
const COMISION_ID = "44444444-4444-4444-4444-444444444444"

function queueWith(items: Record<string, unknown>[]) {
  return { n: items.length, items }
}

const ITEM_INCONSISTENTE = {
  episode_id: EP_INCONSISTENTE,
  comision_id: COMISION_ID,
  classification_id: 1,
  appropriation: "apropiacion_superficial",
  needs_review_reason: "juez_eje_fino_inconsistente: el juez dijo REFLEXIVA, el arbol SUPERFICIAL",
  estado_juez: "inconsistente",
}

const ITEM_ERROR_PARSEO = {
  episode_id: EP_ERROR_PARSEO,
  comision_id: COMISION_ID,
  classification_id: 2,
  appropriation: "apropiacion_superficial",
  needs_review_reason: "juez_eje_fino_error_parseo: JSON invalido",
  estado_juez: "error_parseo",
}

const ITEM_BAJA_CONFIANZA = {
  episode_id: EP_BAJA_CONFIANZA,
  comision_id: COMISION_ID,
  classification_id: 3,
  appropriation: "apropiacion_superficial",
  needs_review_reason: "juez_eje_fino_baja_confianza: confianza 0.42 < 0.70",
  estado_juez: "baja_confianza",
}

const EP_ABSTENCION = "55555555-5555-5555-5555-555555555555"
const ITEM_ABSTENCION = {
  episode_id: EP_ABSTENCION,
  comision_id: COMISION_ID,
  classification_id: 4,
  appropriation: "apropiacion_superficial",
  needs_review_reason:
    "juez_eje_fino_abstencion_traza_insuficiente: verificacion no_evaluable, justificacion ausente",
  estado_juez: "abstencion_traza_insuficiente",
}

const EP_ESTADO_DESCONOCIDO = "66666666-6666-6666-6666-666666666666"
const ITEM_ESTADO_DESCONOCIDO = {
  episode_id: EP_ESTADO_DESCONOCIDO,
  comision_id: COMISION_ID,
  classification_id: 5,
  appropriation: "apropiacion_superficial",
  needs_review_reason: "juez_eje_fino_algo_que_el_backend_agrego_y_el_frontend_no_conoce",
  // Deliberadamente NO uno de los 5 valores de `Estado` en regimen_llm.py: es
  // el caso "el backend emitió algo que esta pantalla no tiene nombrado".
  estado_juez: "un_estado_inventado_que_no_existe_en_el_backend",
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("RevisionColaView", () => {
  test("agrupa la cola por los tres estados del juez, en orden", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () =>
        queueWith([ITEM_INCONSISTENTE, ITEM_ERROR_PARSEO, ITEM_BAJA_CONFIANZA]),
    })
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
    })

    expect(screen.getByText(/contradijo a la regla determinista/i)).toBeInTheDocument()
    expect(screen.getByText(/no devolvió un veredicto legible/i)).toBeInTheDocument()
    expect(screen.getByText(/no alcanzó el umbral de confianza/i)).toBeInTheDocument()

    // Orden: inconsistente antes que error_parseo antes que baja_confianza.
    expect(document.body.innerHTML.indexOf(EP_INCONSISTENTE)).toBeLessThan(
      document.body.innerHTML.indexOf(EP_ERROR_PARSEO),
    )
    expect(document.body.innerHTML.indexOf(EP_ERROR_PARSEO)).toBeLessThan(
      document.body.innerHTML.indexOf(EP_BAJA_CONFIANZA),
    )
  })

  test("un grupo sin episodios no se renderiza", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([ITEM_INCONSISTENTE]),
    })
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
    })

    expect(screen.queryByText(/no devolvió un veredicto legible/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/no alcanzó el umbral de confianza/i)).not.toBeInTheDocument()
  })

  test("estado vacío no afirma que todo está revisado", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([]),
    })
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(/en este momento/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(/todo.*revisad/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/al día/i)).not.toBeInTheDocument()
  })

  test("una decisión exitosa saca la fila de la cola", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () =>
        queueWith([ITEM_INCONSISTENTE, ITEM_ERROR_PARSEO]),
      "/api/v1/classifications/11111111-1111-1111-1111-111111111111/review": {
        ok: true,
        status: 201,
        body: () => ({
          review_id: 1,
          episode_id: EP_INCONSISTENTE,
          previous_classification_id: 1,
          new_classification_id: 99,
          verdict: "apropiacion_reflexiva",
        }),
      },
    })
    const user = userEvent.setup()
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
    })

    const fila = screen.getByTestId(`review-row-${EP_INCONSISTENTE}`)
    await user.click(within(fila).getByRole("button", { name: /decidir/i }))

    const veredictoSelect = within(fila).getByLabelText(/veredicto/i)
    await user.selectOptions(veredictoSelect, "apropiacion_reflexiva")
    const motivoInput = within(fila).getByLabelText(/motivo/i)
    await user.type(motivoInput, "El alumno justificó cada paso con evidencia citable.")
    await user.click(within(fila).getByRole("button", { name: /confirmar decisión/i }))

    await waitFor(() => {
      expect(screen.queryByText(EP_INCONSISTENTE)).not.toBeInTheDocument()
    })
    // La otra fila sigue.
    expect(screen.getByText(EP_ERROR_PARSEO)).toBeInTheDocument()
  })

  test("400 (verdict fuera de dominio) muestra el error del dominio", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([ITEM_INCONSISTENTE]),
      [`/api/v1/classifications/${EP_INCONSISTENTE}/review`]: {
        ok: false,
        status: 400,
        body: () => ({ detail: "verdict 'banana' no es válido. Valores conocidos: [...]" }),
      },
    })
    const user = userEvent.setup()
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
    })
    const fila = screen.getByTestId(`review-row-${EP_INCONSISTENTE}`)
    await user.click(within(fila).getByRole("button", { name: /decidir/i }))
    await user.selectOptions(within(fila).getByLabelText(/veredicto/i), "apropiacion_reflexiva")
    await user.type(
      within(fila).getByLabelText(/motivo/i),
      "motivo cualquiera con longitud suficiente",
    )
    await user.click(within(fila).getByRole("button", { name: /confirmar decisión/i }))

    await waitFor(() => {
      expect(within(fila).getByText(/verdict 'banana' no es válido/i)).toBeInTheDocument()
    })
    // La fila NO se sacó: el POST falló.
    expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
  })

  test("409 con retryable=true muestra el mensaje de reintentar (ganó el pipeline)", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([ITEM_INCONSISTENTE]),
      [`/api/v1/classifications/${EP_INCONSISTENTE}/review`]: {
        ok: false,
        status: 409,
        body: () => ({
          detail: { message: "La clasificación vigente cambió.", retryable: true },
        }),
      },
    })
    const user = userEvent.setup()
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
    })
    const fila = screen.getByTestId(`review-row-${EP_INCONSISTENTE}`)
    await user.click(within(fila).getByRole("button", { name: /decidir/i }))
    await user.selectOptions(within(fila).getByLabelText(/veredicto/i), "apropiacion_reflexiva")
    await user.type(
      within(fila).getByLabelText(/motivo/i),
      "motivo cualquiera con longitud suficiente",
    )
    await user.click(within(fila).getByRole("button", { name: /confirmar decisión/i }))

    await waitFor(() => {
      expect(
        within(fila).getByText(
          /el sistema reclasificó este episodio mientras decidías\. tu decisión sigue siendo válida: reintentá/i,
        ),
      ).toBeInTheDocument()
    })
  })

  test("409 con retryable=false muestra el mensaje de otro docente", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([ITEM_INCONSISTENTE]),
      [`/api/v1/classifications/${EP_INCONSISTENTE}/review`]: {
        ok: false,
        status: 409,
        body: () => ({
          detail: { message: "Otro docente ya decidió.", retryable: false },
        }),
      },
    })
    const user = userEvent.setup()
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
    })
    const fila = screen.getByTestId(`review-row-${EP_INCONSISTENTE}`)
    await user.click(within(fila).getByRole("button", { name: /decidir/i }))
    await user.selectOptions(within(fila).getByLabelText(/veredicto/i), "apropiacion_reflexiva")
    await user.type(
      within(fila).getByLabelText(/motivo/i),
      "motivo cualquiera con longitud suficiente",
    )
    await user.click(within(fila).getByRole("button", { name: /confirmar decisión/i }))

    await waitFor(() => {
      expect(
        within(fila).getByText(
          /otro docente ya decidió sobre este episodio\. leé su decisión antes de insistir/i,
        ),
      ).toBeInTheDocument()
    })
  })

  // Guarda hacia adelante (no regresión): certifica que cuando el juez
  // trivaluado empiece a producir `abstencion_traza_insuficiente` en
  // producción, la cola lo muestre con su propio nombre — no lo cuente en el
  // grupo genérico, que reproduciría el defecto que este change entero vino
  // a arreglar (una ausencia de información indistinguible de otra cosa).
  test("abstencion_traza_insuficiente cae en su grupo nombrado, no en el defensivo", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([ITEM_ABSTENCION]),
    })
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_ABSTENCION)).toBeInTheDocument()
    })
    expect(screen.getByText(/abstención por traza insuficiente/i)).toBeInTheDocument()
    // No cae en el grupo defensivo genérico.
    expect(screen.queryByText(/esta pantalla no conoce/i)).not.toBeInTheDocument()
  })

  // Guarda hacia adelante (no regresión): hoy el backend nunca emite un
  // `estado_juez` fuera del `Literal` de 5 valores, así que este caso no
  // ocurre en producción. Certifica que si backend y frontend se
  // desincronizan (se agrega un sexto estado y esta pantalla no se actualiza),
  // el docente lo VE en vez de perderlo — y que el copy dice lo que es
  // (desincronización), no algo sobre el episodio.
  test("un estado_juez desconocido cae en el grupo defensivo con copy de desincronización", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([ITEM_ESTADO_DESCONOCIDO]),
    })
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_ESTADO_DESCONOCIDO)).toBeInTheDocument()
    })
    expect(screen.getByText(/esta pantalla no conoce/i)).toBeInTheDocument()
    // NO debe caer en ninguno de los cuatro grupos nombrados.
    expect(screen.queryByText(/contradijo a la regla determinista/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/abstención por traza insuficiente/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/no devolvió un veredicto legible/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/no alcanzó el umbral de confianza/i)).not.toBeInTheDocument()
  })

  test("la decisión declara que reemplaza la etiqueta oficial antes de confirmar", async () => {
    setupFetchMock({
      "/api/v1/classifications/review-queue": () => queueWith([ITEM_INCONSISTENTE]),
    })
    const user = userEvent.setup()
    renderWithRouter(<RevisionColaView comisionId={undefined} getToken={fakeGetToken} />)

    await waitFor(() => {
      expect(screen.getByText(EP_INCONSISTENTE)).toBeInTheDocument()
    })
    const fila = screen.getByTestId(`review-row-${EP_INCONSISTENTE}`)
    await user.click(within(fila).getByRole("button", { name: /decidir/i }))

    expect(within(fila).getByText(/reemplaza la etiqueta oficial/i)).toBeInTheDocument()
  })
})
