/**
 * Aceptacion HU-010, el pie (orquestador, antes de construir; el constructor
 * no la modifica).
 *
 * C03  El pie de auditoria muestra la version del prompt del tutor que de
 *      verdad corre: la de `default_prompt_version` en la config del
 *      tutor-service (la que el CTR registra). En la prueba como alumno del
 *      21/11 decia tutor/v1.5.0 con el tutor en v1.11.0 (BUG-05). La prueba lee
 *      la config, asi que el proximo bump del prompt la pone en rojo si el pie
 *      queda atras.
 */
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { AuditFooter } from "@platform/ui"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

function versionDelTutor(): string {
  const config = readFileSync(
    resolve(__dirname, "../../tutor-service/src/tutor_service/config.py"),
    "utf-8",
  )
  const m = config.match(/default_prompt_version:\s*str\s*=\s*"(v[\d.]+)"/)
  if (!m?.[1]) throw new Error("no encontre default_prompt_version en la config del tutor")
  return m[1]
}

describe("HU-010 · el pie dice la version real del tutor (C03)", () => {
  it("la config del tutor esta en v1.11.0 (control)", () => {
    expect(versionDelTutor()).toBe("v1.11.0")
  })

  it("el pie muestra la misma version que corre el tutor", () => {
    sessionStorage.clear()
    render(<AuditFooter episodeId={null} />)
    expect(screen.getByTestId("audit-footer")).toHaveTextContent(
      `prompt: tutor/${versionDelTutor()}`,
    )
  })
})
