/**
 * El dead-letter del CTR deja de ser silencioso PARA EL ALUMNO.
 *
 * `CTRClient` (`@platform/ctr-client`) ya documenta su callback `onDrop` como
 * "nunca en silencio" y `EpisodePage.tsx` ya lo cableaba — pero solo a
 * `console.error`. Nada visible para quien esta usando la pagina: si la
 * sesion se vence y el 401 persiste mas alla de los reintentos (ver el fix de
 * `index.ts` — 401 ahora es reintentable), el evento termina en dead-letter
 * con razon "exhausted" y el alumno nunca se entera de que algo no se
 * registro.
 *
 * Este archivo prueba el CABLEADO: que invocar el `onDrop` que `EpisodeView`
 * le pasa al `CTRClient` efectivamente actualiza la UI. La LOGICA del
 * mensaje (por que "exhausted" muestra aviso y "rejected" no) esta probada
 * aparte en `ctrDropAviso.test.ts` — separar las dos cosas evita que este
 * archivo tenga que reproducir reintentos reales contra timers.
 *
 * Por que se mockea `@platform/ctr-client` en vez de dejarlo correr real
 * ------------------------------------------------------------------------
 * Llegar a "exhausted" de verdad implica agotar `maxAttempts` (default 8)
 * con backoff exponencial real (~90s de delays encadenados) — nada de eso es
 * configurable desde `EpisodePage.tsx` (no expone `maxAttempts`/`scheduler`
 * al construir el cliente). Reproducirlo con fake timers seria fragil y
 * lento para lo que este archivo necesita afirmar, que es mas angosto: SI el
 * CTRClient llama a `onDrop`, ENTONCES el alumno lo ve. Ese límite entre "la
 * libreria dispara onDrop" (cubierto en `packages/ctr-client/src/index.test.ts`)
 * y "la pagina reacciona a onDrop" (cubierto acá) es deliberado.
 */
import { act, render, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { EpisodeView } from "../src/pages/EpisodePage"
import { setupFetchMock } from "./_mocks"
import { resetMonacoMock } from "./_monacoMock"

/** Captura el `onDrop` que `EpisodeView` le pasa al constructor real. */
const ctrClientMock: {
  onDrop: ((event: unknown, reason: string) => void) | null
} = { onDrop: null }

vi.mock("@platform/ctr-client", () => {
  class CTRClientFake {
    constructor(opts: { onDrop?: (event: unknown, reason: string) => void }) {
      ctrClientMock.onDrop = opts.onDrop ?? null
    }
    flush() {
      return Promise.resolve()
    }
    dispose() {}
    pendingCount() {
      return 0
    }
    emit() {}
    codigoEjecutado() {}
    edicionCodigo() {}
    testsEjecutados() {}
    lecturaEnunciado() {}
    anotacionCreada() {}
    pestanaPerdida() {}
    pestanaRecuperada() {}
    copiaIntentada() {}
    pegaIntentada() {}
  }
  return { CTRClient: CTRClientFake }
})

const TAREA_ID = "tp-aviso-dead-letter"
const EPISODIO_ID = "ep-aviso-dead-letter"

const TAREA_BASE = {
  codigo: "TP-aviso",
  titulo: "TP del aviso",
  enunciado: "Enunciado",
  fecha_inicio: null,
  fecha_fin: null,
  peso: "1.00",
  estado: "published",
  version: 1,
  inicial_codigo: null,
  language: "python",
}

function montar() {
  setupFetchMock({
    "/resume": () => ({ ok: true }),
    [`/api/v1/tareas-practicas/${TAREA_ID}`]: () => ({ id: TAREA_ID, ...TAREA_BASE }),
    [`/api/v1/episodes/${EPISODIO_ID}`]: () => ({
      episode_id: EPISODIO_ID,
      tarea_practica_id: TAREA_ID,
      comision_id: "com-1",
      estado: "open",
      opened_at: "2026-08-27T10:00:00Z",
      closed_at: null,
      last_code_snapshot: null,
      messages: [],
      notes: [],
      ejercicio_id: null,
      ejercicio_orden: null,
    }),
  })
  return render(<EpisodeView episodeId={EPISODIO_ID} onExit={() => {}} />)
}

beforeEach(() => {
  resetMonacoMock()
  window.sessionStorage.clear()
  window.localStorage.clear()
  ctrClientMock.onDrop = null
})

describe("EpisodeView — aviso visible cuando el CTR descarta un evento", () => {
  it('reason "exhausted" (reintentos agotados — probable sesion vencida) muestra el aviso', async () => {
    const { getByTestId } = montar()

    await waitFor(() => expect(ctrClientMock.onDrop).not.toBeNull())

    act(() => {
      ctrClientMock.onDrop?.(
        { event_type: "edicion_codigo", event_uuid: "u-1", attempts: 8 },
        "exhausted",
      )
    })

    const aviso = await waitFor(() => getByTestId("ctr-dead-letter-aviso"))
    expect(aviso.textContent).toMatch(/sesión/i)
    expect(aviso.textContent).toMatch(/código está a salvo/i)
  })

  it('reason "rejected" (evento invalido, no la sesion) NO muestra el aviso', async () => {
    const { queryByTestId } = montar()

    await waitFor(() => expect(ctrClientMock.onDrop).not.toBeNull())

    act(() => {
      ctrClientMock.onDrop?.(
        { event_type: "edicion_codigo", event_uuid: "u-2", attempts: 1 },
        "rejected",
      )
    })

    // `act()` ya flushea el setState sincronico del handler antes de volver
    // acá — no hace falta un `waitFor` para una ausencia.
    expect(queryByTestId("ctr-dead-letter-aviso")).toBeNull()
  })
})
