// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
//
// Tests del ONBOARDING POR ESTADO contra el contrato de `types.ts`.
//
// La regla que se testea es una sola, y esta escrita en el contrato:
//     se muestra  <=>  unlockWhen(estado) && !doneWhen(estado) && !fueDescartado(id)
//
// Superficie de API asumida (unico lugar a tocar si el motor la nombra distinto):
//   <OnboardingProvider flow={flow} estado={estado} route="/x">{children}</OnboardingProvider>
//   useOnboardingProgress(): OnboardingProgress   // lee del contexto del provider
//   El cartel se cierra con su boton primario (`ctaLabel`, default "Entendido").
//
// Nada de esto testea pixeles: ni posiciones, ni clases, ni sombras.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactElement, ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OnboardingProvider, useOnboardingProgress } from "./OnboardingProvider"
import type { OnboardingFlow, OnboardingHint } from "./types"

/** Estado de ejemplo: la forma que cada app calcula. El motor es agnostico de esto. */
interface Estado {
  inscripto: boolean
  tpsPublicados: number
  entregas: number
}

const ESTADO_CERO: Estado = { inscripto: false, tpsPublicados: 0, entregas: 0 }

function hint(over: Partial<OnboardingHint<Estado>> & { id: string }): OnboardingHint<Estado> {
  return {
    title: `Titulo de ${over.id}`,
    body: <p>Cuerpo de {over.id}</p>,
    unlockWhen: () => true,
    doneWhen: () => false,
    ...over,
  }
}

function flujo(hints: OnboardingHint<Estado>[], id = "onboarding-test"): OnboardingFlow<Estado> {
  return { id, hints }
}

function Progreso() {
  const p = useOnboardingProgress()
  return <span data-testid="progreso">{`${p.hechos}/${p.total}/${p.completo ? "si" : "no"}`}</span>
}

function renderOnboarding(
  flow: OnboardingFlow<Estado>,
  estado: Estado,
  route = "/",
  children: ReactNode = <Progreso />,
) {
  return render(
    <OnboardingProvider flow={flow} estado={estado} route={route}>
      {children}
    </OnboardingProvider>,
  )
}

/** Vuelve a renderizar el mismo provider con estado/ruta nuevos. */
function reRenderOnboarding(
  rerender: (ui: ReactElement) => void,
  flow: OnboardingFlow<Estado>,
  estado: Estado,
  route = "/",
) {
  rerender(
    <OnboardingProvider flow={flow} estado={estado} route={route}>
      <Progreso />
    </OnboardingProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

describe("OnboardingProvider — la regla central", () => {
  it("muestra el hint cuando unlockWhen es true, doneWhen es false y no fue descartado", () => {
    const h = hint({ id: "unite", title: "Unite a una comision" })
    renderOnboarding(flujo([h]), ESTADO_CERO)
    expect(screen.getByText("Unite a una comision")).toBeInTheDocument()
  })

  it("NO muestra el hint si unlockWhen da false (precondicion no dada)", () => {
    const h = hint({
      id: "entregar",
      title: "Entrega tu primer TP",
      unlockWhen: (s) => s.tpsPublicados > 0,
    })
    renderOnboarding(flujo([h]), ESTADO_CERO)
    expect(screen.queryByText("Entrega tu primer TP")).toBeNull()
  })

  it("NO muestra el hint si doneWhen da true, AUNQUE nunca se haya descartado (idempotencia)", () => {
    // El caso real: el alumno se inscribio por afuera de la app. El paso nace cumplido.
    const h = hint({
      id: "unite",
      title: "Unite a una comision",
      doneWhen: (s) => s.inscripto,
    })
    renderOnboarding(flujo([h]), { ...ESTADO_CERO, inscripto: true })
    expect(screen.queryByText("Unite a una comision")).toBeNull()
  })

  it("renderiza a sus children siempre, haya o no cartel", () => {
    const h = hint({ id: "unite", doneWhen: () => true })
    renderOnboarding(flujo([h]), ESTADO_CERO, "/", <p>contenido de la app</p>)
    expect(screen.getByText("contenido de la app")).toBeInTheDocument()
  })
})

describe("OnboardingProvider — anti-zombie", () => {
  it("con el cartel abierto, si el estado pasa a doneWhen=true el cartel se retira SOLO", () => {
    const h = hint({
      id: "unite",
      title: "Unite a una comision",
      doneWhen: (s) => s.inscripto,
    })
    const f = flujo([h])
    const { rerender } = renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByText("Unite a una comision")).toBeInTheDocument()

    reRenderOnboarding(rerender, f, { ...ESTADO_CERO, inscripto: true })
    expect(screen.queryByText("Unite a una comision")).toBeNull()
  })

  it("ese retiro NO es un descarte: si el estado vuelve atras, el cartel vuelve a aparecer", () => {
    const h = hint({
      id: "unite",
      title: "Unite a una comision",
      doneWhen: (s) => s.inscripto,
    })
    const f = flujo([h])
    const { rerender } = renderOnboarding(f, ESTADO_CERO)
    reRenderOnboarding(rerender, f, { ...ESTADO_CERO, inscripto: true })
    expect(screen.queryByText("Unite a una comision")).toBeNull()

    reRenderOnboarding(rerender, f, ESTADO_CERO)
    expect(screen.getByText("Unite a una comision")).toBeInTheDocument()
  })

  it("un hint con la precondicion sin dar no se muestra, y aparece cuando se cumple", () => {
    // El docente todavia no publico ningun TP: no le pidas que corrija entregas.
    const h = hint({
      id: "corregir",
      title: "Corregi la primera entrega",
      unlockWhen: (s) => s.tpsPublicados > 0,
      doneWhen: (s) => s.entregas > 0,
    })
    const f = flujo([h])
    const { rerender } = renderOnboarding(f, ESTADO_CERO)
    expect(screen.queryByText("Corregi la primera entrega")).toBeNull()

    reRenderOnboarding(rerender, f, { ...ESTADO_CERO, tpsPublicados: 2 })
    expect(screen.getByText("Corregi la primera entrega")).toBeInTheDocument()
  })
})

describe("OnboardingProvider — descarte", () => {
  it("cerrar el cartel lo descarta en el acto", async () => {
    const h = hint({ id: "unite", title: "Unite a una comision" })
    renderOnboarding(flujo([h]), ESTADO_CERO)
    await userEvent.click(screen.getByRole("button", { name: /entendido/i }))
    expect(screen.queryByText("Unite a una comision")).toBeNull()
  })

  it("el descarte persiste: al remontar no vuelve a aparecer", async () => {
    const f = flujo([hint({ id: "unite", title: "Unite a una comision" })])
    const primera = renderOnboarding(f, ESTADO_CERO)
    await userEvent.click(screen.getByRole("button", { name: /entendido/i }))
    primera.unmount()

    renderOnboarding(f, ESTADO_CERO)
    expect(screen.queryByText("Unite a una comision")).toBeNull()
  })

  it("el descarte es por id: descartar uno no descarta al siguiente", async () => {
    const f = flujo([
      hint({ id: "uno", title: "Cartel uno" }),
      hint({ id: "dos", title: "Cartel dos" }),
    ])
    renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByText("Cartel uno")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /entendido/i }))
    expect(screen.queryByText("Cartel uno")).toBeNull()
    expect(screen.getByText("Cartel dos")).toBeInTheDocument()
  })

  // Misma regresion que en el tour lineal: cerrar es explicito. Un clic al aire no
  // puede costarle al usuario el cartel que le explica lo unico que falta hacer.
  // La card del onboarding es `role="status"`, no `dialog`: no bloquea la pagina, asi
  // que decirle al lector de pantalla que el resto esta inerte seria mentirle. El
  // `dialog` queda para el tour lineal, que si ES la tarea.
  it("un clic en el FONDO no descarta el cartel", () => {
    const f = flujo([hint({ id: "unite", title: "Unite a una comision" })])
    renderOnboarding(f, ESTADO_CERO)
    const card = screen.getByRole("status")
    const contenedor = card.parentElement
    for (const hijo of Array.from(contenedor?.children ?? [])) {
      if (hijo === card) continue
      fireEvent.click(hijo)
    }
    if (contenedor) fireEvent.click(contenedor)
    expect(screen.getByText("Unite a una comision")).toBeInTheDocument()
  })

  it("usa el ctaLabel del hint cuando esta declarado", () => {
    const f = flujo([hint({ id: "unite", ctaLabel: "Dale, vamos" })])
    renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByRole("button", { name: /dale, vamos/i })).toBeInTheDocument()
  })
})

describe("OnboardingProvider — uno solo a la vez", () => {
  it("con dos hints que califican, muestra unicamente el primero de la lista", () => {
    const f = flujo([
      hint({ id: "uno", title: "Cartel uno" }),
      hint({ id: "dos", title: "Cartel dos" }),
    ])
    renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByText("Cartel uno")).toBeInTheDocument()
    expect(screen.queryByText("Cartel dos")).toBeNull()
  })

  it("si el primero no califica, muestra el siguiente que si califica", () => {
    const f = flujo([
      hint({ id: "uno", title: "Cartel uno", doneWhen: () => true }),
      hint({ id: "dos", title: "Cartel dos", unlockWhen: () => false }),
      hint({ id: "tres", title: "Cartel tres" }),
    ])
    renderOnboarding(f, ESTADO_CERO)
    expect(screen.queryByText("Cartel uno")).toBeNull()
    expect(screen.queryByText("Cartel dos")).toBeNull()
    expect(screen.getByText("Cartel tres")).toBeInTheDocument()
  })
})

// El match es POR SEGMENTO, no por prefijo crudo:
//     matchea  <=>  ruta === h.route || ruta.startsWith(h.route + "/")
// La barra es obligatoria, y en este repo la diferencia tiene dientes: web-teacher
// tiene /episode-n-level y /episode-timeline, asi que con `startsWith` pelado un hint
// declarado en /episode se dispara en las dos.
describe("OnboardingProvider — filtrado por route", () => {
  it("la ruta declarada matchea a si misma: /episodio en /episodio", () => {
    const f = flujo([hint({ id: "ep", title: "Cartel del episodio", route: "/episodio" })])
    renderOnboarding(f, ESTADO_CERO, "/episodio")
    expect(screen.getByText("Cartel del episodio")).toBeInTheDocument()
  })

  it("matchea los descendientes: /episodio en /episodio/abc", () => {
    const f = flujo([hint({ id: "ep", title: "Cartel del episodio", route: "/episodio" })])
    renderOnboarding(f, ESTADO_CERO, "/episodio/abc")
    expect(screen.getByText("Cartel del episodio")).toBeInTheDocument()
  })

  it("no se muestra en una ruta de otro segmento", () => {
    const f = flujo([hint({ id: "ep", title: "Cartel del episodio", route: "/episodio" })])
    renderOnboarding(f, ESTADO_CERO, "/comisiones")
    expect(screen.queryByText("Cartel del episodio")).toBeNull()
  })

  // El caso real del repo. Con `startsWith` crudo estos dos pasan igual y el bug queda
  // sin candado; por eso van con las rutas que existen de verdad en web-teacher.
  it("NO matchea una ruta hermana que comparte prefijo: /episode en /episode-n-level", () => {
    const f = flujo([hint({ id: "ep", title: "Cartel del episodio", route: "/episode" })])
    renderOnboarding(f, ESTADO_CERO, "/episode-n-level")
    expect(screen.queryByText("Cartel del episodio")).toBeNull()
  })

  it("NO matchea /episode-timeline, y sigue matcheando /episode y /episode/abc", () => {
    const f = flujo([hint({ id: "ep", title: "Cartel del episodio", route: "/episode" })])
    const { rerender } = renderOnboarding(f, ESTADO_CERO, "/episode-timeline")
    expect(screen.queryByText("Cartel del episodio")).toBeNull()

    reRenderOnboarding(rerender, f, ESTADO_CERO, "/episode")
    expect(screen.getByText("Cartel del episodio")).toBeInTheDocument()

    reRenderOnboarding(rerender, f, ESTADO_CERO, "/episode/abc")
    expect(screen.getByText("Cartel del episodio")).toBeInTheDocument()
  })

  // Consecuencia buscada de la regla nueva, no un bug: "/" dejo de ser comodin.
  // Un hint que quiera aplicar en toda la app no declara `route`.
  it("un hint declarado en / matchea SOLO la home, no toda la app", () => {
    const f = flujo([hint({ id: "home", title: "Cartel de la home", route: "/" })])
    const { rerender } = renderOnboarding(f, ESTADO_CERO, "/")
    expect(screen.getByText("Cartel de la home")).toBeInTheDocument()

    reRenderOnboarding(rerender, f, ESTADO_CERO, "/comisiones")
    expect(screen.queryByText("Cartel de la home")).toBeNull()
  })

  it("con route '/' ninguna ruta cuelga como descendiente: /alumnos tampoco matchea", () => {
    // Caso borde de la concatenacion: "/" + "/" da "//", que no prefija a nada real.
    // O sea "/" identifica exactamente la home. Para aplicar en toda la app se omite
    // `route`; no se declara "/".
    const f = flujo([hint({ id: "home", title: "Cartel de la home", route: "/" })])
    renderOnboarding(f, ESTADO_CERO, "/alumnos")
    expect(screen.queryByText("Cartel de la home")).toBeNull()
  })

  it("un hint sin route aplica en cualquier ruta", () => {
    const f = flujo([hint({ id: "global", title: "Cartel global" })])
    const { rerender } = renderOnboarding(f, ESTADO_CERO, "/")
    expect(screen.getByText("Cartel global")).toBeInTheDocument()

    reRenderOnboarding(rerender, f, ESTADO_CERO, "/otra/cosa/profunda")
    expect(screen.getByText("Cartel global")).toBeInTheDocument()
  })

  it("el primero de la lista que califica es el primero POR RUTA, no el primero absoluto", () => {
    const f = flujo([
      hint({ id: "otra-ruta", title: "Cartel de otra ruta", route: "/otra" }),
      hint({ id: "esta-ruta", title: "Cartel de esta ruta", route: "/aca" }),
    ])
    renderOnboarding(f, ESTADO_CERO, "/aca/adentro")
    expect(screen.queryByText("Cartel de otra ruta")).toBeNull()
    expect(screen.getByText("Cartel de esta ruta")).toBeInTheDocument()
  })
})

describe("useOnboardingProgress", () => {
  it("cuenta solo los hints con countsTowardProgress !== false", () => {
    const f = flujo([
      hint({ id: "cuenta-1" }),
      hint({ id: "cuenta-2" }),
      hint({ id: "no-cuenta", countsTowardProgress: false }),
    ])
    renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByTestId("progreso")).toHaveTextContent("0/2/no")
  })

  it("los hechos salen del estado real, no de un contador propio", () => {
    const f = flujo([
      hint({ id: "unite", doneWhen: (s) => s.inscripto }),
      hint({ id: "entregar", doneWhen: (s) => s.entregas > 0 }),
    ])
    renderOnboarding(f, { ...ESTADO_CERO, inscripto: true })
    expect(screen.getByTestId("progreso")).toHaveTextContent("1/2/no")
  })

  it("un paso cumplido cuenta aunque nunca se haya mostrado (unlockWhen false)", () => {
    const f = flujo([
      hint({ id: "unite", doneWhen: (s) => s.inscripto }),
      hint({ id: "entregar", unlockWhen: () => false, doneWhen: (s) => s.entregas > 0 }),
    ])
    renderOnboarding(f, { ...ESTADO_CERO, inscripto: true, entregas: 3 })
    expect(screen.getByTestId("progreso")).toHaveTextContent("2/2/si")
  })

  it("completo es true cuando hechos === total", () => {
    const f = flujo([
      hint({ id: "unite", doneWhen: (s) => s.inscripto }),
      hint({ id: "no-cuenta", countsTowardProgress: false, doneWhen: () => false }),
    ])
    renderOnboarding(f, { ...ESTADO_CERO, inscripto: true })
    expect(screen.getByTestId("progreso")).toHaveTextContent("1/1/si")
  })

  it("descartar un cartel NO lo cuenta como hecho: el progreso sale del estado", async () => {
    const f = flujo([hint({ id: "unite", title: "Unite a una comision" })])
    renderOnboarding(f, ESTADO_CERO)
    await userEvent.click(screen.getByRole("button", { name: /entendido/i }))
    expect(screen.getByTestId("progreso")).toHaveTextContent("0/1/no")
  })

  it("el progreso se recalcula cuando cambia el estado", () => {
    const f = flujo([hint({ id: "unite", doneWhen: (s) => s.inscripto })])
    const { rerender } = renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByTestId("progreso")).toHaveTextContent("0/1/no")

    reRenderOnboarding(rerender, f, { ...ESTADO_CERO, inscripto: true })
    expect(screen.getByTestId("progreso")).toHaveTextContent("1/1/si")
  })
})

describe("OnboardingProvider — persistencia rota", () => {
  it("con localStorage roto el cartel se muestra igual y cerrarlo no explota", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError: acceso a localStorage denegado")
    })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError")
    })
    const f = flujo([hint({ id: "unite", title: "Unite a una comision" })])
    renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByText("Unite a una comision")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /entendido/i }))
    expect(screen.queryByText("Unite a una comision")).toBeNull()
    vi.restoreAllMocks()
  })

  it("con los descartes perdidos, lo ya cumplido sigue sin mostrarse (sale del estado)", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError")
    })
    const f = flujo([
      hint({ id: "unite", title: "Unite a una comision", doneWhen: (s) => s.inscripto }),
      hint({ id: "otro", title: "Cartel siguiente" }),
    ])
    renderOnboarding(f, { ...ESTADO_CERO, inscripto: true })
    expect(screen.queryByText("Unite a una comision")).toBeNull()
    expect(screen.getByText("Cartel siguiente")).toBeInTheDocument()
    vi.restoreAllMocks()
  })

  it("descartes corruptos en storage no rompen el motor", () => {
    vi.spyOn(Storage.prototype, "getItem").mockReturnValue("{no-es-json")
    const f = flujo([hint({ id: "unite", title: "Unite a una comision" })])
    renderOnboarding(f, ESTADO_CERO)
    expect(screen.getByText("Unite a una comision")).toBeInTheDocument()
    vi.restoreAllMocks()
  })
})
