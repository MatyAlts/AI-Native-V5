/**
 * Los cinco valores de `appropriation` tienen color, y la leyenda dice la verdad.
 *
 * POR QUE EXISTE
 * --------------
 * El 2026-09-29, mirando el panel del docente en produccion, aparecieron dos
 * defectos que ningun test veia:
 *
 *   1. La leyenda de `ProgressionView` decia "Autonomo" con el VERDE de
 *      `apropiacion_reflexiva`. Los puntos verdes de la pantalla eran reflexiva;
 *      los `autonomo` de verdad salian grises y sin entrada en la leyenda. El
 *      docente leia el grafico al reves, y `autonomo` es el 62% del corpus.
 *
 *   2. `sin_clasificar` no estaba en el mapa de colores. Ese mismo dia se
 *      reclasificaron 158 episodios del sumidero B2b, y los 158 pasaron a un
 *      color de fallback que ninguna leyenda explica.
 *
 * Los dos vienen de lo mismo: los colores de los puntos y los de la leyenda
 * eran DOS listas escritas a mano. Estos tests atan las dos al mismo origen.
 */
import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const RAIZ = join(__dirname, "..")
const TOKENS = readFileSync(
  join(RAIZ, "../../packages/ui/src/tokens/theme.css"),
  "utf-8",
)
const PROGRESSION = readFileSync(join(RAIZ, "src/views/ProgressionView.tsx"), "utf-8")
const LONGITUDINAL = readFileSync(
  join(RAIZ, "src/views/StudentLongitudinalView.tsx"),
  "utf-8",
)

/** Los cinco de `Classification.appropriation` (CLAUDE.md, ADR-062). */
const LOS_CINCO = [
  "delegacion_pasiva",
  "apropiacion_superficial",
  "apropiacion_reflexiva",
  "autonomo",
  "sin_clasificar",
] as const

describe("los cinco regimenes tienen su token", () => {
  it.each(["reflexiva", "superficial", "delegacion", "autonomo", "sin-clasificar"])(
    "--color-appropriation-%s esta definido",
    (sufijo) => {
      expect(TOKENS).toMatch(
        new RegExp(`--color-appropriation-${sufijo}:\\s*oklch\\(`),
      )
    },
  )

  it("autonomo NO usa el gris neutro: es un regimen observado, no un hueco", () => {
    // El bug original. `autonomo` es el 62% del corpus; pintarlo del color de
    // "no hay dato" hacia que el docente leyera la mayoria de su cohorte como
    // ausencia de informacion.
    expect(PROGRESSION).not.toMatch(/autonomo:\s*"var\(--color-neutral\)"/)
    expect(LONGITUDINAL).not.toMatch(
      /label === "autonomo"\) return "var\(--color-neutral\)"/,
    )
  })

  it("sin_clasificar SI es gris apagado: tiene que retroceder, no competir", () => {
    const m = TOKENS.match(/--color-appropriation-sin-clasificar:\s*oklch\(([^)]+)\)/)
    expect(m).not.toBeNull()
    const croma = Number((m?.[1] ?? "").trim().split(/\s+/)[1])
    expect(croma).toBeLessThan(0.05)
  })
})

describe("ProgressionView: el mapa cubre los cinco", () => {
  it.each(LOS_CINCO)("%s tiene entrada en LABEL_COLOR_VAR", (valor) => {
    // Lo que falte cae al `?? var(--color-level-meta)` y sale de un color que
    // ninguna leyenda explica.
    const mapa = PROGRESSION.slice(
      PROGRESSION.indexOf("const LABEL_COLOR_VAR"),
      PROGRESSION.indexOf("const LEYENDA_APROPIACION"),
    )
    expect(mapa).toContain(`${valor}:`)
  })

  it("la leyenda se genera del mapa, no de una lista paralela", () => {
    // El guardian de verdad: si alguien vuelve a escribir los colores a mano
    // en el JSX, las dos listas pueden volver a decir cosas distintas.
    expect(PROGRESSION).toContain("LEYENDA_APROPIACION.map")
    expect(PROGRESSION).toContain("LABEL_COLOR_VAR[valor]")
  })

  it("la leyenda nombra los cinco", () => {
    const leyenda = PROGRESSION.slice(
      PROGRESSION.indexOf("const LEYENDA_APROPIACION"),
      PROGRESSION.indexOf("interface Props"),
    )
    for (const valor of LOS_CINCO) expect(leyenda).toContain(valor)
  })

  it("ninguna entrada de la leyenda hardcodea un color", () => {
    const leyenda = PROGRESSION.slice(
      PROGRESSION.indexOf("const LEYENDA_APROPIACION"),
      PROGRESSION.indexOf("interface Props"),
    )
    expect(leyenda).not.toContain("var(--color-appropriation")
  })
})

describe("StudentLongitudinalView: la leyenda dejo de mentir", () => {
  it('ya no llama "Autonomo" al verde de reflexiva', () => {
    // `colors[2]` es `--color-appropriation-reflexiva` (resolveScoreColors).
    // La leyenda lo etiquetaba "Autonomo".
    expect(LONGITUDINAL).not.toMatch(
      /backgroundColor: colors\[2\] \}\}\s*\/>\s*Autonomo\s*</,
    )
  })

  it("nombra autonomo y sin_clasificar con sus colores propios", () => {
    expect(LONGITUDINAL).toContain("var(--color-appropriation-autonomo)")
    expect(LONGITUDINAL).toContain("var(--color-appropriation-sin-clasificar)")
  })
})
