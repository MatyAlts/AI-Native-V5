/**
 * Aceptacion HU-020, plazo vencido del lado del alumno (orquestador, antes de
 * construir; el constructor no la modifica). Juani (23/11): "manda estos
 * arreglos a hacerse en una hu nueva" y "sisi" a los criterios.
 *
 * Hallazgos de la re-prueba en produccion del 23/11:
 *  F20  Con la TP vencida, "Volver a abrir" des-marca el ejercicio y despues
 *       no se puede abrir el episodio: el alumno queda trabado.
 *  F21  "Reintentar" en la pantalla de error abre un episodio que no queda
 *       atado al ejercicio (no guarda el contexto: falta el entregaId).
 *  F22  La pantalla "Abriendo episodio" dice "ventana fechas OK" aunque el
 *       plazo vencio.
 *  F23  Mi progreso dice "pendiente ordinal ... ADR-018" en la letra chica.
 *
 * Contratos nuevos:
 *  - `src/utils/reintentoApertura.ts` exporta
 *    `argumentosDeReintento(v: { ejercicioId: string | null; ejercicioOrden: number | null; entregaId?: string | null })`
 *    que devuelve `{ ejercicio: { id, orden } | null, entregaId: string | null }`.
 *    La vista "opening" de `materia.$id.tsx` guarda el `entregaId` y su
 *    "Reintentar" llama a `openEpisodeAndNavigate` con lo que devuelve.
 *  - `src/pages/MiProgresoPage.tsx` exporta `NOTA_TENDENCIA: string`, el texto
 *    de la letra chica de la tendencia, y la pagina muestra ese texto.
 *
 * C02  Con la TP vencida y la entrega en draft, no hay "Volver a abrir".
 * N01  Dentro del plazo, "Volver a abrir" sigue estando.
 * N02  En una re-entrega pedida por el docente (returned), sigue estando aunque
 *      la TP este vencida.
 * C03  El reintento conserva ejercicio y entrega.
 * C04  Si abrir fallo, la pantalla de carga no dice "ventana fechas OK".
 * C05  La letra chica de Mi progreso no dice "ADR" ni "pendiente ordinal".
 */
import { ConfirmProvider } from "@platform/ui"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ExerciseListView } from "../src/components/ExerciseListView"
import { OpeningStage } from "../src/components/OpeningStage"
import type { AvailableTarea, Entrega, TpEjercicio } from "../src/lib/api"
import * as progreso from "../src/pages/MiProgresoPage"
import * as reintento from "../src/utils/reintentoApertura"
import { setupFetchMock } from "./_mocks"

const COMISION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
const TAREA_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
const IDS = ["ejejejej-0001-0001-0001-000000000001", "ejejejej-0002-0002-0002-000000000002"]

const PASADO = new Date(Date.now() - 3 * 3600_000).toISOString()
const FUTURO = new Date(Date.now() + 3 * 86400_000).toISOString()

function makeEntrega(estado: "draft" | "returned"): Entrega {
  return {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    tenant_id: "t1",
    tarea_practica_id: TAREA_ID,
    comision_id: COMISION_ID,
    student_pseudonym: "b1b1b1b1-0001-0001-0001-000000000001",
    estado,
    ejercicio_estados: IDS.map((id, i) => ({
      ejercicio_id: id,
      orden: i + 1,
      completado: true,
      episode_id: `epepepep-000${i + 1}-0001-0001-00000000000${i + 1}`,
      completado_at: null,
    })),
    submitted_at: null,
    created_at: "2026-11-23T10:00:00Z",
    updated_at: "2026-11-23T10:00:00Z",
  } as Entrega
}

function makePairs(): TpEjercicio[] {
  return IDS.map((id, i) => ({
    id: `pair-${i + 1}`,
    tarea_practica_id: TAREA_ID,
    peso_en_tp: "1.0",
    ejercicio_id: id,
    orden: i + 1,
    ejercicio: {
      id,
      titulo: `Ej ${i + 1}`,
      enunciado_md: "x",
      inicial_codigo: null,
      unidad_tematica: "secuenciales",
      dificultad: "basica" as const,
      test_cases: [],
    },
  }))
}

function tarea(fecha_fin: string | null): AvailableTarea {
  return {
    id: TAREA_ID,
    codigo: "VERIF",
    titulo: "TP",
    enunciado: "x",
    fecha_inicio: null,
    fecha_fin,
    peso: "1.0",
    estado: "published",
    version: 1,
    inicial_codigo: null,
  }
}

function montar(entrega: Entrega, fecha_fin: string | null) {
  setupFetchMock({
    "/ejercicios": () => makePairs(),
    "/api/v1/entregas": () => entrega,
  })
  return render(
    <ExerciseListView
      tarea={tarea(fecha_fin)}
      comisionId={COMISION_ID}
      onSelectEjercicio={vi.fn()}
      onViewGrade={vi.fn()}
      onBack={vi.fn()}
    />,
    { wrapper: ConfirmProvider },
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("HU-020 · Volver a abrir con la TP vencida", () => {
  it("C02: draft vencida no ofrece Volver a abrir", async () => {
    montar(makeEntrega("draft"), PASADO)
    await waitFor(() => expect(screen.getByTestId("ejercicios-list")).toBeDefined())
    expect(screen.queryByTestId("ejercicio-reabrir-1")).toBeNull()
    expect(screen.queryByTestId("ejercicio-reabrir-2")).toBeNull()
  })

  it("N01: dentro del plazo sigue estando", async () => {
    montar(makeEntrega("draft"), FUTURO)
    await waitFor(() => expect(screen.getByTestId("ejercicio-reabrir-1")).toBeDefined())
  })

  it("N02: una re-entrega pedida por el docente sigue pudiendo reabrir vencida", async () => {
    montar(makeEntrega("returned"), PASADO)
    await waitFor(() => expect(screen.getByTestId("ejercicio-reabrir-1")).toBeDefined())
  })
})

describe("HU-020 · Reintentar abre el mismo ejercicio", () => {
  it("C03: el reintento conserva ejercicio y entrega", () => {
    const f = (reintento as Record<string, unknown>).argumentosDeReintento as
      | ((v: Record<string, unknown>) => {
          ejercicio: { id: string; orden: number } | null
          entregaId: string | null
        })
      | undefined
    expect(typeof f).toBe("function")
    if (!f) return
    expect(f({ ejercicioId: IDS[0], ejercicioOrden: 1, entregaId: "ent-1" })).toEqual({
      ejercicio: { id: IDS[0], orden: 1 },
      entregaId: "ent-1",
    })
    expect(f({ ejercicioId: null, ejercicioOrden: null, entregaId: null })).toEqual({
      ejercicio: null,
      entregaId: null,
    })
  })
})

describe("HU-020 · pantalla de carga con error", () => {
  it("C04: si abrir fallo por plazo, no dice 'ventana fechas OK'", () => {
    render(
      <OpeningStage
        tareaCodigo="VERIF"
        tareaTitulo="TP"
        episodeReady={false}
        errorMessage="Venció el plazo de esta TP. Ya no se puede trabajar en ella."
        onRetry={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.queryByText(/ventana fechas OK/i)).toBeNull()
  })
})

describe("HU-020 · Mi progreso sin jerga", () => {
  it("C05: la letra chica no dice ADR ni pendiente ordinal", () => {
    const nota = (progreso as Record<string, unknown>).NOTA_TENDENCIA
    expect(typeof nota).toBe("string")
    expect(String(nota).trim().length).toBeGreaterThan(0)
    expect(String(nota)).not.toMatch(/ADR|pendiente ordinal/i)
  })
})
