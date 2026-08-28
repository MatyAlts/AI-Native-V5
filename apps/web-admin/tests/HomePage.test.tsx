import { cleanup, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { HomePage } from "../src/pages/HomePage"
import { renderConQuery, setupFetchMock } from "./_mocks"

afterEach(() => {
  cleanup()
})

/**
 * Los 3 tests de este archivo vivieron rojos en `main` hasta que el CI empezo a
 * correr vitest. La causa NO era el harness que se sospechaba (los 3 mocks
 * matcheaban, `request()` recibia todo, el `QueryClientProvider` estaba):
 *
 *   BK-2 agrego a la HomePage una CUARTA query — `byokApi.list()` contra
 *   `/api/v1/byok/keys` — que el test nunca declaro. Caia en el default benigno
 *   de `setupFetchMock`, que devuelve el envelope pageable `{data, meta}`. La
 *   pagina hace `byokKeysQuery.data.some(...)` sobre lo que el contrato tipa
 *   como `ByokKey[]` → `data.some is not a function` DURANTE el render.
 *
 *   El primer render no explota (`isSuccess` todavia es false y corta el `&&`),
 *   asi que las cards commitean "..." y recien despues, cuando la query
 *   resuelve, el render tira. El sintoma que se veia era "las KPI cards se
 *   quedan en '...'", o sea un `isLoading` que no baja — a tres queries de
 *   distancia de la causa real.
 *
 * Es el MISMO gotcha que documenta `_mocks.tsx` para web-teacher: un endpoint
 * no declarado no falla, devuelve el shape equivocado y revienta lejos.
 */
const BYOK_CON_KEY_ACTIVA = () => [{ revoked_at: null }]

/** El panel de KPIs, para no confundir su label con el atajo del mismo nombre. */
function panelKpis() {
  return within(screen.getByRole("region", { name: "Plataforma en números" }))
}

describe("HomePage KPI cards", () => {
  it("renderiza 3 KPI cards con counts cuando los 3 endpoints responden", async () => {
    setupFetchMock({
      "/api/v1/byok/keys": BYOK_CON_KEY_ACTIVA,
      "/health": () => ({ status: "ready" }),
      "/api/v1/universidades": () => ({ data: [{}, {}], meta: { cursor_next: null } }),
      "/api/v1/comisiones": () => ({ data: [{}, {}, {}], meta: { cursor_next: null } }),
    })

    renderConQuery(<HomePage />)

    await waitFor(() => {
      expect(panelKpis().getByText("2")).toBeInTheDocument()
    })

    const kpis = panelKpis()
    // Exactamente 3 cards: el contrato de admin-home-kpis. El `li` es de
    // `HeroStatsPanel`; contarlos ancla que no se cuele una cuarta.
    expect(kpis.getAllByRole("listitem")).toHaveLength(3)
    expect(kpis.getByText("Universidades")).toBeInTheDocument()
    expect(kpis.getByText("3")).toBeInTheDocument()
    // NB-22: era "Comisiones activas" y contaba con `?estado=activa`, un estado
    // que no existe en el modelo `Comision` — contaba 0 siempre. El criterio
    // real es el total de comisiones no borradas del tenant.
    expect(kpis.getByText("Comisiones")).toBeInTheDocument()
    expect(kpis.getAllByText("registradas")).toHaveLength(2)
    // La tercera card es el estado del api-gateway. La de "Episodios cerrados"
    // se fue al footnote: sin comision seleccionada no hay cohorte que agregar,
    // y una card permanentemente en "—" no le dice nada a nadie.
    expect(kpis.getByText("API Gateway")).toBeInTheDocument()
    expect(kpis.getByText("Operativo")).toBeInTheDocument()
    expect(kpis.getByText(/Episodios cerrados/)).toBeInTheDocument()
    // Con las 3 queries OK ninguna card degrada.
    expect(kpis.queryByText("—")).toBeNull()
  })

  it("degrada graciosamente cuando un endpoint falla — la card afectada cae a '—' y el resto renderiza", async () => {
    setupFetchMock({
      "/api/v1/byok/keys": BYOK_CON_KEY_ACTIVA,
      "/health": () => ({ status: "ready" }),
      "/api/v1/universidades": {
        ok: false,
        status: 500,
        body: () => ({ detail: "internal error" }),
      },
      "/api/v1/comisiones": () => ({ data: [{}], meta: { cursor_next: null } }),
    })

    renderConQuery(<HomePage />)

    await waitFor(() => {
      // Comisiones renderiza count normal
      expect(panelKpis().getByText("1")).toBeInTheDocument()
    })

    // Universidades cae a "—" porque su endpoint dio 500 — la pagina NO crashea
    const kpis = panelKpis()
    expect(kpis.getAllByRole("listitem")).toHaveLength(3)
    expect(kpis.getByText("Universidades")).toBeInTheDocument()
    expect(kpis.getByText("—")).toBeInTheDocument()
    expect(kpis.getByText("sin datos")).toBeInTheDocument()
    // Y el resto de las cards sigue con sus datos reales.
    expect(kpis.getByText("Operativo")).toBeInTheDocument()
  })

  it("NO renderiza KPI card de integrity_compromised (NON-GOAL del proposal)", async () => {
    setupFetchMock({
      "/api/v1/byok/keys": BYOK_CON_KEY_ACTIVA,
      "/health": () => ({ status: "ready" }),
      "/api/v1/universidades": () => ({ data: [], meta: { cursor_next: null } }),
      "/api/v1/comisiones": () => ({ data: [], meta: { cursor_next: null } }),
    })

    renderConQuery(<HomePage />)

    await waitFor(() => {
      expect(panelKpis().getByText("API Gateway")).toBeInTheDocument()
    })

    expect(panelKpis().getAllByRole("listitem")).toHaveLength(3)
    expect(screen.queryByText(/integridad/i)).toBeNull()
    expect(screen.queryByText(/integrity/i)).toBeNull()
    expect(screen.queryByText(/comprometid/i)).toBeNull()
  })
})
