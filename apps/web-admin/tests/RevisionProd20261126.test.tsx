/**
 * Hallazgos de la revisión de prod del 2026-11-26 en el web-admin.
 *
 * 1. El home decía "API Gateway — no responde" con el gateway sano, porque
 *    `/api/v1/health` responde `{"status":"ok"}` y el mapa sólo conocía
 *    `ready`/`degraded`/`error`.
 * 2. "Clasificaciones N4" pide `/classifications/subgrupos`, que no existe en
 *    el backend: vuelve 422 y el bloque quedaba en "Cargando subgrupos..." para
 *    siempre. Ahora cualquier error lo muestra como no disponible.
 * 3. El selector de comisión mostraba sólo el código ("C1, C1, C2…"): ahora
 *    antepone el nombre de la materia.
 */
import { render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ComisionPicker } from "../src/components/ComisionPicker"
import { ClasificacionesPage } from "../src/pages/ClasificacionesPage"
import { HomePage } from "../src/pages/HomePage"
import { renderConQuery, setupFetchMock } from "./_mocks"

afterEach(() => {
  vi.unstubAllGlobals()
})

const MATERIAS = () => ({
  data: [
    { id: "m-prog1", nombre: "Programacion 1" },
    { id: "m-parad", nombre: "Paradigmas" },
  ],
  meta: { cursor_next: null },
})

const COMISIONES = () => ({
  data: [
    { id: "c-1", codigo: "C1", materia_id: "m-prog1" },
    { id: "c-2", codigo: "C1", materia_id: "m-parad" },
  ],
  meta: { cursor_next: null },
})

describe("revisión de prod 2026-11-26 — web-admin", () => {
  it("el home muestra el gateway Operativo cuando /health responde status=ok", async () => {
    setupFetchMock({
      "/api/v1/byok/keys": () => [{ revoked_at: null }],
      "/health": () => ({ status: "ok" }),
      "/api/v1/universidades": () => ({ data: [], meta: { cursor_next: null } }),
      "/api/v1/comisiones": () => ({ data: [], meta: { cursor_next: null } }),
    })

    renderConQuery(<HomePage />)

    const kpis = within(screen.getByRole("region", { name: "Plataforma en números" }))
    await waitFor(() => {
      expect(kpis.getByText("Operativo")).toBeInTheDocument()
    })
    expect(kpis.queryByText("no responde")).toBeNull()
  })

  it("el selector de comisión antepone el nombre de la materia al código", async () => {
    setupFetchMock({
      "/api/v1/materias": MATERIAS,
      "/api/v1/comisiones": COMISIONES,
    })

    render(<ComisionPicker value={null} onChange={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Programacion 1 · C1" })).toBeInTheDocument()
    })
    expect(screen.getByRole("option", { name: "Paradigmas · C1" })).toBeInTheDocument()
  })

  it("el selector sigue andando con el código solo si fallan las materias", async () => {
    setupFetchMock({
      "/api/v1/materias": { ok: false, status: 500, body: () => ({ detail: "boom" }) },
      "/api/v1/comisiones": COMISIONES,
    })

    render(<ComisionPicker value={null} onChange={() => {}} />)

    await waitFor(() => {
      expect(screen.getAllByRole("option", { name: "C1" })).toHaveLength(2)
    })
  })

  it("subgrupos con 422 se muestra como no disponible, no como cargando para siempre", async () => {
    setupFetchMock({
      "/api/v1/materias": MATERIAS,
      "/api/v1/comisiones": COMISIONES,
      "/api/v1/classifications/subgrupos": {
        ok: false,
        status: 422,
        body: () => ({ detail: "episode_id no es un UUID" }),
      },
      // Con episodios: el bloque de subgrupos sólo se monta si hay datos.
      "/api/v1/classifications/aggregated": () => ({
        comision_id: "c-1",
        period_days: 30,
        total_episodes: 2,
        distribution: {
          delegacion_pasiva: 1,
          apropiacion_superficial: 0,
          apropiacion_reflexiva: 1,
          autonomo: 0,
        },
        avg_ct_summary: null,
        avg_ccd_mean: null,
        avg_ccd_orphan_ratio: null,
        avg_cii_stability: null,
        avg_cii_evolution: null,
        timeseries: [],
      }),
    })

    renderConQuery(<ClasificacionesPage />)

    await waitFor(() => {
      expect(screen.getByText(/Disponible próximamente/)).toBeInTheDocument()
    })
    expect(screen.queryByText("Cargando subgrupos...")).toBeNull()
  })
})
