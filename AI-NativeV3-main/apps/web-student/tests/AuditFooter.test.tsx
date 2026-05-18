/**
 * Tests del AuditFooter (shape alumno, brief D1).
 *
 * Cubre:
 *  - Render con prompt fijo + classifier truncado + cadena.
 *  - Truncate del hash (4 + 4 con elipsis).
 *  - Sin episodio activo: muestra "ultima verificacion: hace X" o "sin verificacion previa".
 *  - Con classifierHash prop: prevalece sobre session storage.
 *  - Persistencia en sessionStorage.
 */
import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { AuditFooter } from "@platform/ui"
import { setupFetchMock } from "./_mocks"

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AuditFooter", () => {
  test("renderiza el prompt y un placeholder cuando no hay hash ni episodio", () => {
    render(<AuditFooter episodeId={null} />)

    const footer = screen.getByTestId("audit-footer")
    expect(footer).toHaveTextContent(/prompt: tutor\/v1\.0\.0/i)
    expect(screen.getByTestId("audit-classifier-hash")).toHaveTextContent("pendiente")
    expect(screen.getByTestId("audit-chain-label")).toHaveTextContent(
      /sin verificacion previa/i,
    )
  })

  test("trunca el classifier hash a primer-4 + ultimos-4", () => {
    render(
      <AuditFooter
        episodeId={null}
        classifierHash="a3f8c1b2d4e5f6071829304142536475a3f8c1b2d4e5f6071829304142536475"
      />,
    )
    const node = screen.getByTestId("audit-classifier-hash")
    expect(node).toHaveTextContent("a3f8...6475")
  })

  test("con episodio activo, hace POST al verify y muestra el conteo", async () => {
    setupFetchMock({
      "/api/v1/audit/episodes/": () => ({
        episode_id: "ep-1",
        events_count: 470,
        is_intact: true,
        reason: null,
      }),
    })

    render(<AuditFooter episodeId="ep-1" />)

    await waitFor(() => {
      expect(screen.getByTestId("audit-chain-label")).toHaveTextContent(
        /470 eventos verificados/i,
      )
    })
  })

  test("persiste hash en sessionStorage al recibir classifierHash", () => {
    render(
      <AuditFooter
        episodeId={null}
        classifierHash="a3f8c1b2d4e5f6071829304142536475a3f8c1b2d4e5f6071829304142536475"
      />,
    )
    expect(sessionStorage.getItem("audit-classifier-hash")).toBe(
      "a3f8c1b2d4e5f6071829304142536475a3f8c1b2d4e5f6071829304142536475",
    )
  })

  test("hidrata desde sessionStorage si no hay classifierHash en props", () => {
    sessionStorage.setItem(
      "audit-classifier-hash",
      "deadbeef12345678abcdefdeadbeef12345678abcdefdeadbeef12345678abcd",
    )
    render(<AuditFooter episodeId={null} />)
    expect(screen.getByTestId("audit-classifier-hash")).toHaveTextContent("dead...abcd")
  })
})
