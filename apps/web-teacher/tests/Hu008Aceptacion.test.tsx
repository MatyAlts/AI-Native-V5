/**
 * Aceptacion HU-008 (orquestador, antes de construir; el constructor no la modifica).
 *
 * El backend del PR #140 devuelve los veredictos de los jueces v2/v3 con su
 * forma propia: `raw.d1_verbalizacion..d4_autonomia` con `{valor, localizador,
 * cita}`, regimen que puede ser PASIVA o EVIDENCIA_INSUFICIENTE, `juez_version`,
 * y en v3 `es_frontera`/`frontera_entre`. La vista del docente solo conocia la
 * forma del juez v1 y se rompia ("Cannot read properties of undefined") con
 * cualquier veredicto `ok` del juez nuevo. Verificado en navegador el 20/11.
 *
 * C01  Un veredicto v3 `ok` se muestra sin romper: regimen, las 4 dimensiones
 *      con su valor y la cita del alumno.
 * C02  Un veredicto v2 `ok` PASIVA con autonomia `transferencia` se muestra.
 * C03  Un caso de frontera del v3 se marca como tal.
 * C04  Los estados nuevos del juez (`salida_invalida`,
 *      `derivado_evidencia_insuficiente`, `proveedor_no_disponible`) tienen
 *      mensaje propio en la vista del episodio y grupo propio en la cola de
 *      revision (no el grupo de "estados que esta pantalla no conoce").
 * N01  Un `raw` con forma desconocida no rompe la pagina.
 */
import { screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"
import { EpisodeNLevelView } from "../src/views/EpisodeNLevelView"
import { RevisionColaView } from "../src/views/RevisionColaView"
import { renderWithRouter, setupFetchMock } from "./_mocks"

const EPISODE_ID = "11111111-2222-3333-4444-555555555555"

const distribucion = {
  episode_id: EPISODE_ID,
  labeler_version: "1.3.0",
  distribution_seconds: { N1: 30, N2: 60, N3: 15, N4: 45, meta: 5 },
  distribution_ratio: { N1: 0.19, N2: 0.39, N3: 0.1, N4: 0.29, meta: 0.03 },
  total_events_per_level: { N1: 2, N2: 3, N3: 1, N4: 4, meta: 2 },
}

function dim(valor: string, cita = "", localizador = "") {
  return { valor, localizador, cita }
}

function rawV3(extra: Record<string, unknown> = {}) {
  return {
    d1_verbalizacion: dim("presente", "primero pienso en el caso base", "mensaje 2"),
    d2_verificacion: dim("presente", "lo probe con 0 y con 5", "mensaje 3"),
    d3_justificacion: dim("ausente"),
    d4_autonomia: dim("interlocutor", "yo lo haria con un for", "mensaje 1"),
    regimen: "REFLEXIVA",
    confianza: 0.8,
    justificacion_global: "Explica su plan y lo verifica con casos propios.",
    es_frontera: false,
    frontera_entre: [],
    ...extra,
  }
}

function veredicto(estado: string, regimen: string | null, raw: unknown, juez = "v3") {
  return {
    estado,
    regimen,
    confianza: raw ? 0.8 : null,
    raw,
    razon: "x",
    model_used: "google/gemini-2.5-flash",
    prompt_version: juez === "v3" ? "mtac_v2_juez_v3.0.0" : "mtac_v1_juez_v2.0.0",
    juez_version: juez,
  }
}

function clasificacion(appropriation: string, regimen_llm: unknown) {
  return {
    episode_id: EPISODE_ID,
    comision_id: "c1",
    classifier_config_hash: "hash",
    appropriation,
    appropriation_reason: "x",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: null,
    regimen_llm,
    pasiva_por_sobreuso: false,
  }
}

async function render(c: unknown) {
  localStorage.setItem("analytics-view-mode", "docente")
  setupFetchMock({
    "/n-level-distribution": () => distribucion,
    "/api/v1/classifications/": () => c,
  })
  renderWithRouter(<EpisodeNLevelView getToken={async () => "t"} initialEpisodeId={EPISODE_ID} />)
  await waitFor(() => {
    expect(screen.getByText(/veredicto del juez ia/i)).toBeInTheDocument()
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.removeItem("analytics-view-mode")
})

describe("HU-008 · veredictos de los jueces v2/v3 en la vista del episodio", () => {
  test("C01: v3 ok se muestra con regimen, dimensiones y citas", async () => {
    await render(clasificacion("apropiacion_reflexiva", veredicto("ok", "REFLEXIVA", rawV3())))
    expect(screen.getByText("Reflexiva")).toBeInTheDocument()
    for (const nombre of ["Verbalizacion", "Verificacion", "Justificacion", "Autonomia"]) {
      expect(screen.getByText(nombre)).toBeInTheDocument()
    }
    expect(screen.getByText(/primero pienso en el caso base/)).toBeInTheDocument()
    expect(screen.getByText(/yo lo haria con un for/)).toBeInTheDocument()
    expect(screen.getByText("interlocutor")).toBeInTheDocument()
    expect(screen.getByText(/Explica su plan/)).toBeInTheDocument()
  })

  test("C02: v2 ok PASIVA con autonomia transferencia", async () => {
    const raw = rawV3({
      d1_verbalizacion: dim("ausente"),
      d2_verificacion: dim("ausente"),
      d3_justificacion: dim("ausente"),
      d4_autonomia: dim("transferencia", "pasame el codigo", "mensaje 1"),
      regimen: "PASIVA",
      es_frontera: undefined,
      frontera_entre: undefined,
    })
    await render(clasificacion("delegacion_pasiva", veredicto("ok", "PASIVA", raw, "v2")))
    expect(screen.getByText("Pasiva")).toBeInTheDocument()
    expect(screen.getByText("transferencia")).toBeInTheDocument()
    expect(screen.getByText(/pasame el codigo/)).toBeInTheDocument()
  })

  test("C03: un caso de frontera del v3 se marca", async () => {
    const raw = rawV3({ es_frontera: true, frontera_entre: ["REFLEXIVA", "SUPERFICIAL"] })
    await render(clasificacion("apropiacion_reflexiva", veredicto("ok", "REFLEXIVA", raw)))
    expect(screen.getByText(/frontera/i)).toBeInTheDocument()
  })

  test("C03: sin frontera no aparece la marca", async () => {
    await render(clasificacion("apropiacion_reflexiva", veredicto("ok", "REFLEXIVA", rawV3())))
    expect(screen.queryByText(/frontera/i)).not.toBeInTheDocument()
  })

  test.each(["salida_invalida", "derivado_evidencia_insuficiente", "proveedor_no_disponible"])(
    "C04: el estado %s tiene mensaje propio",
    async (estado) => {
      await render(clasificacion("sin_clasificar", veredicto(estado, null, null)))
      expect(screen.queryByText("Sin lectura disponible.")).not.toBeInTheDocument()
    },
  )

  test("N01: un raw con forma desconocida no rompe la pagina", async () => {
    await render(clasificacion("apropiacion_reflexiva", veredicto("ok", "REFLEXIVA", { otra: 1 })))
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()
  })
})

describe("HU-008 · cola de revision", () => {
  test.each(["salida_invalida", "derivado_evidencia_insuficiente", "proveedor_no_disponible"])(
    "C04: %s no cae en el grupo de estados desconocidos",
    async (estado) => {
      const ep = "99999999-9999-9999-9999-999999999999"
      setupFetchMock({
        "/api/v1/classifications/review-queue": () => ({
          n: 1,
          items: [
            {
              episode_id: ep,
              comision_id: "44444444-4444-4444-4444-444444444444",
              classification_id: 9,
              appropriation: "sin_clasificar",
              needs_review_reason: `juez_eje_fino_${estado}: x`,
              estado_juez: estado,
            },
          ],
        }),
      })
      renderWithRouter(<RevisionColaView comisionId={undefined} getToken={async () => "t"} />)
      await waitFor(() => {
        expect(screen.getByText(ep)).toBeInTheDocument()
      })
      expect(screen.queryByText(/esta pantalla no conoce/i)).not.toBeInTheDocument()
    },
  )
})
