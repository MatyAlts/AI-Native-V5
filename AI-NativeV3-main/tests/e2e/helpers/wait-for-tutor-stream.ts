import { type Page, expect } from "@playwright/test"

/**
 * Espera a que el ultimo mensaje del tutor (SSE streamed) tenga contenido
 * no vacio. NO usa `page.waitForTimeout` con valor fijo (anti-pattern para
 * SSE).
 *
 * Selector: `[data-testid=tutor-message-last]` — agregar ese testid en el
 * componente de chat del web-student (EpisodePage) para localizacion estable.
 *
 * Spec: D6 de design.md — "expect.poll con timeout >= 10s".
 */
export async function waitForTutorReply(page: Page, timeoutMs = 15_000): Promise<void> {
  await expect
    .poll(
      async () => {
        const last = page.getByTestId("tutor-message-last")
        if ((await last.count()) === 0) return ""
        const text = await last.textContent()
        return (text ?? "").trim()
      },
      { timeout: timeoutMs, message: "timed out waiting for tutor message" },
    )
    .not.toEqual("")
}
