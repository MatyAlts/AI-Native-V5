// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
//
// Tests del TOUR LINEAL contra el contrato de `types.ts`.
//
// Lo que se testea es la maquina de estados (arranque, resume, salida), no el layout:
// nada de posiciones, clases ni sombras.
//
// Superficie de API asumida:
//   <TourProvider navigate={fn}>{children}</TourProvider>
//   useTour(): { start, maybeStart, skip, activo }
//   El overlay expone role="dialog" y botones accesibles: "Siguiente" / "Listo" /
//   "Atras" / "Saltar el tour".
//
// Los pasos de prueba NO declaran `anchor` a proposito: sin ancla, el overlay degrada a
// card centrada y no se cuelga del polling de useAnchorRect (que tiene sus propios tests).
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useEffect } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { TourProvider, useTour } from "./TourProvider"
import type { TourFlow } from "./types"

function flujo(id = "flow-test"): TourFlow {
  return {
    id,
    steps: [
      { id: "p1", title: "Paso uno", body: <p>cuerpo uno</p> },
      { id: "p2", title: "Paso dos", body: <p>cuerpo dos</p> },
      { id: "p3", title: "Paso tres", body: <p>cuerpo tres</p> },
    ],
  }
}

type Modo = "maybe" | "start" | "ninguno"

function Arranque({ flow, modo }: { flow: TourFlow; modo: Modo }) {
  const { maybeStart, start } = useTour()
  useEffect(() => {
    if (modo === "maybe") maybeStart(flow)
    if (modo === "start") start(flow)
  }, [flow, modo, maybeStart, start])
  return null
}

function renderTour(flow: TourFlow, modo: Modo = "maybe", navigate = vi.fn()) {
  const utils = render(
    <TourProvider navigate={navigate}>
      <Arranque flow={flow} modo={modo} />
    </TourProvider>,
  )
  return { ...utils, navigate }
}

const siguiente = () => screen.getByRole("button", { name: /siguiente/i })
const listo = () => screen.getByRole("button", { name: /^listo$/i })

/** Recorre el tour entero hasta completarlo. */
async function completarTour(pasos: number) {
  for (let i = 0; i < pasos - 1; i++) {
    await userEvent.click(siguiente())
  }
  await userEvent.click(listo())
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

describe("TourProvider — arranque", () => {
  it("maybeStart arranca el tour en el primer ingreso", () => {
    renderTour(flujo())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("maybeStart NO arranca si el tour ya se completo", async () => {
    const f = flujo()
    const primera = renderTour(f)
    await completarTour(3)
    expect(screen.queryByRole("dialog")).toBeNull()
    primera.unmount()

    renderTour(f)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("maybeStart NO arranca si el tour ya se salteo", async () => {
    const f = flujo()
    const primera = renderTour(f)
    await userEvent.click(screen.getByRole("button", { name: /saltar el tour/i }))
    primera.unmount()

    renderTour(f)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("start arranca SIEMPRE, aunque el tour ya se haya completado (ver de nuevo)", async () => {
    const f = flujo()
    const primera = renderTour(f)
    await completarTour(3)
    primera.unmount()

    renderTour(f, "start")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("start arranca desde el primer paso aunque hubiera un paso guardado", async () => {
    const f = flujo()
    const primera = renderTour(f)
    await userEvent.click(siguiente())
    expect(screen.getByText("Paso dos")).toBeInTheDocument()
    primera.unmount()

    renderTour(f, "start")
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("activo refleja si hay un tour en curso", async () => {
    renderTour(flujo())
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /saltar el tour/i }))
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

describe("TourProvider — resume", () => {
  it("persiste el paso en curso y al remontar retoma ahi, no en el principio", async () => {
    const f = flujo()
    const primera = renderTour(f)
    await userEvent.click(siguiente())
    expect(screen.getByText("Paso dos")).toBeInTheDocument()
    primera.unmount()

    renderTour(f)
    expect(screen.getByText("Paso dos")).toBeInTheDocument()
    expect(screen.queryByText("Paso uno")).toBeNull()
  })

  it("retoma el ultimo paso tambien despues de dos avances", async () => {
    const f = flujo()
    const primera = renderTour(f)
    await userEvent.click(siguiente())
    await userEvent.click(siguiente())
    expect(screen.getByText("Paso tres")).toBeInTheDocument()
    primera.unmount()

    renderTour(f)
    expect(screen.getByText("Paso tres")).toBeInTheDocument()
  })

  it("resume defensivo: si el paso guardado ya no existe en el flow, arranca de cero", async () => {
    const viejo = flujo("flow-mutante")
    const primera = renderTour(viejo)
    await userEvent.click(siguiente())
    expect(screen.getByText("Paso dos")).toBeInTheDocument()
    primera.unmount()

    // Mismo id de flow (no se bumpeo) pero los pasos cambiaron de nombre.
    const nuevo: TourFlow = {
      id: "flow-mutante",
      steps: [
        { id: "otro-1", title: "Otro paso uno", body: <p>x</p> },
        { id: "otro-2", title: "Otro paso dos", body: <p>y</p> },
      ],
    }
    renderTour(nuevo)
    expect(screen.getByText("Otro paso uno")).toBeInTheDocument()
  })

  it("Atras vuelve al paso anterior", async () => {
    renderTour(flujo())
    await userEvent.click(siguiente())
    await userEvent.click(screen.getByRole("button", { name: /atras/i }))
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })
})

describe("TourProvider — salidas", () => {
  it("Escape saltea el tour", async () => {
    renderTour(flujo())
    await userEvent.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("Escape deja el tour como salteado (no vuelve a arrancar solo)", async () => {
    const f = flujo()
    const primera = renderTour(f)
    await userEvent.keyboard("{Escape}")
    primera.unmount()

    renderTour(f)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("el boton 'Saltar el tour' saltea", async () => {
    renderTour(flujo())
    await userEvent.click(screen.getByRole("button", { name: /saltar el tour/i }))
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("el ultimo paso cierra el tour como completado", async () => {
    renderTour(flujo())
    await completarTour(3)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  // REGRESION: hoy la capa que come clicks tiene onClick={onSkip}. Un clic en el fondo
  // del overlay NO puede descartar ni saltear nada: es la forma mas facil de perder el
  // tour sin querer, justo mientras el usuario intenta leerlo.
  it("un clic en el FONDO del overlay NO saltea ni cierra el tour", () => {
    renderTour(flujo())
    const dialog = screen.getByRole("dialog")
    const contenedor = dialog.parentElement
    expect(contenedor).not.toBeNull()

    for (const hijo of Array.from(contenedor?.children ?? [])) {
      if (hijo === dialog) continue
      fireEvent.click(hijo)
    }
    if (contenedor) fireEvent.click(contenedor)

    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Paso uno")).toBeInTheDocument()
  })

  it("un clic en el fondo tampoco deja el tour marcado como visto", () => {
    const f = flujo()
    const primera = renderTour(f)
    const dialog = screen.getByRole("dialog")
    const contenedor = dialog.parentElement
    for (const hijo of Array.from(contenedor?.children ?? [])) {
      if (hijo === dialog) continue
      fireEvent.click(hijo)
    }
    primera.unmount()

    renderTour(f)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})

describe("TourProvider — navegacion", () => {
  it("navega a la route del paso cuando el paso la declara", () => {
    const f: TourFlow = {
      id: "flow-nav",
      steps: [{ id: "p1", title: "Paso uno", body: <p>x</p>, route: "/ejercicios" }],
    }
    const navigate = vi.fn()
    renderTour(f, "maybe", navigate)
    expect(navigate).toHaveBeenCalledWith("/ejercicios")
  })

  it("NO navega si el paso no declara route", () => {
    const navigate = vi.fn()
    renderTour(flujo(), "maybe", navigate)
    expect(navigate).not.toHaveBeenCalled()
  })

  it("navega al entrar a un paso posterior con route propia", async () => {
    const f: TourFlow = {
      id: "flow-nav-2",
      steps: [
        { id: "p1", title: "Paso uno", body: <p>x</p> },
        { id: "p2", title: "Paso dos", body: <p>y</p>, route: "/correcciones" },
      ],
    }
    const navigate = vi.fn()
    renderTour(f, "maybe", navigate)
    await userEvent.click(siguiente())
    expect(navigate).toHaveBeenCalledWith("/correcciones")
  })
})
