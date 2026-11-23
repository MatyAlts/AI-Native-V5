/**
 * Aceptacion HU-018, ronda de arreglos (orquestador, antes de corregir; el
 * constructor no la modifica). Sale de la verificacion independiente del PR
 * #148 (22/11). Juani: "vos terminas todo entonces".
 *
 * R02c Mi progreso pide las alertas a `/student/me/alerts` (ver la aceptacion
 *      revisada de analytics), no a `/student/{pseudonimo}/alerts`.
 * R03  Una pasiva que vino SOLO de la regla de sobreuso no se le muestra al
 *      alumno en la lista de TPs como "el tutor hizo gran parte".
 * R04  En Mi progreso un episodio autonomo dice que trabajo sin tutor, no
 *      "Sin datos suficientes".
 * R05  La lista de ejercicios usa `porcentajesDePeso` (nada vigilaba que la
 *      pantalla la use).
 * R06  Con veredicto del juez, si el subgrupo es del mismo eje que la etiqueta
 *      oficial, se conserva su mensaje (mas preciso que el generico).
 * R07  El mensaje de cierre por defecto no usa jerga del modelo.
 */
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { appropriationLabel } from "../src/components/TareaSelector"
import type { Classification } from "../src/lib/api"
import { buildPedagogicalFeedback } from "../src/pages/EpisodePage"
import { modoDeEpisodio } from "../src/pages/MiProgresoPage"

const fuente = (rel: string) => readFileSync(resolve(__dirname, "..", rel), "utf-8")

function clasif(over: Record<string, unknown>): Classification {
  return {
    episode_id: "e",
    comision_id: "c",
    classifier_config_hash: "h",
    appropriation: "apropiacion_superficial",
    appropriation_reason: "",
    ct_summary: null,
    ccd_mean: null,
    ccd_orphan_ratio: null,
    cii_stability: null,
    cii_evolution: null,
    is_current: true,
    subgrupo: null,
    pasiva_por_sobreuso: false,
    ...over,
  } as unknown as Classification
}

function sg(key: string, eje: string) {
  return {
    key,
    label: key,
    accion_docente: "x",
    eje,
    dimensiones: { autonomia: 0.5, experimentacion: 0.5, persistencia: 0.5, foco: 0.5 },
  }
}

describe("HU-018 · ronda de arreglos", () => {
  it("R02c: Mi progreso pide /student/me/alerts", () => {
    const src = fuente("src/pages/MiProgresoPage.tsx")
    expect(src).toMatch(/student\/me\/alerts/)
    expect(src).not.toMatch(/student\/\$\{[^}]+\}\/alerts/)
  })

  it("R03: la pasiva por sobreuso no dice que el tutor hizo el trabajo", () => {
    const label = appropriationLabel("delegacion_pasiva", true)
    expect(label).toMatch(/muchas consultas/i)
    expect(label).not.toMatch(/tutor hizo/i)
    expect(appropriationLabel("delegacion_pasiva", false)).toMatch(/tutor hizo/i)
  })

  it("R04: un episodio autonomo dice que trabajo sin tutor", () => {
    expect(typeof modoDeEpisodio).toBe("function")
    const modo = modoDeEpisodio({ appropriation: "autonomo" } as never)
    expect(modo?.short ?? "").toMatch(/sin tutor/i)
    expect(modoDeEpisodio({ appropriation: null } as never)).toBeUndefined()
  })

  it("R05: la lista de ejercicios usa porcentajesDePeso", () => {
    const src = fuente("src/components/ExerciseListView.tsx")
    expect(src).toMatch(/porcentajesDePeso\(/)
    expect(src).not.toMatch(/peso \* 100/)
  })

  it("R06: juez REFLEXIVA con subgrupo reflexivo conserva su mensaje", () => {
    const f = buildPedagogicalFeedback(
      clasif({
        appropriation: "apropiacion_reflexiva",
        subgrupo: sg("colaborador_reflexivo", "reflexiva"),
        regimen_llm: { estado: "ok" },
      }),
    )
    expect(f.mensaje).toMatch(/para pensar/i)
  })

  it("R06: juez SUPERFICIAL con desenganchado conserva 'mitad de camino'", () => {
    const f = buildPedagogicalFeedback(
      clasif({
        appropriation: "apropiacion_superficial",
        subgrupo: sg("desenganchado", "superficial"),
        regimen_llm: { estado: "ok" },
      }),
    )
    expect(f.titulo).toMatch(/mitad de camino/i)
  })

  it("R07: el cierre por defecto no usa jerga", () => {
    const f = buildPedagogicalFeedback(clasif({ appropriation: "autonomo", subgrupo: null }))
    expect(`${f.titulo} ${f.mensaje}`).not.toMatch(/apropiaci[oó]n|coherencia/i)
  })
})
