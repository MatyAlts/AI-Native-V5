import { existsSync, readFileSync } from "node:fs"
import path from "node:path"
import { expect, test } from "@playwright/test"
import { WEB_ADMIN_URL } from "../fixtures/seeded-ids"

const SHARED_DIR = path.resolve(__dirname, "../../../.dev-logs/e2e-shared")
const LAST_EPISODE_FILE = path.join(SHARED_DIR, "last-episode-id.txt")

/**
 * Journey 5 — cross-frontend / CTR integrity.
 *
 * Depende del journey 4: lee `episode_id` del archivo compartido (escrito al
 * final del journey 4). Si el archivo no existe, hacemos `test.skip()` con un
 * mensaje claro. Por convencion del runner (`fullyParallel: false` y orden
 * alfabetico de spec filenames `04-...` luego `05-...`), journey 4 siempre
 * corre primero.
 *
 * Este journey valida que el CTR escribio la cadena criptografica correcta —
 * depende de los 8 partition workers consumiendo Redis Streams. Si el verify
 * devuelve 404 sospechar de los workers.
 */

test.describe.configure({ mode: "serial" })

test.describe("cross-frontend / CTR integrity", () => {
  test("verifica el episodio recien cerrado por journey 4", async ({ page }) => {
    if (!existsSync(LAST_EPISODE_FILE)) {
      test.skip(
        true,
        `journey 4 no produjo episode_id (archivo ${LAST_EPISODE_FILE} no existe). Corre journey 4 primero o revisa por que fallo.`,
      )
      return
    }
    const episodeId = readFileSync(LAST_EPISODE_FILE, "utf8").trim()
    expect(episodeId, "archivo compartido vacio").toBeTruthy()

    // web-admin usa router state-based (no URL-based) — entrar via sidebar.
    await page.goto(`${WEB_ADMIN_URL}/`)
    await page.getByRole("button", { name: /Integridad CTR/i }).click()
    await page.getByLabel(/Episode ID/i).fill(episodeId)
    await page.getByRole("button", { name: /Verificar integridad/i }).click()

    const result = page.getByTestId("audit-result")
    await expect(result).toBeVisible({ timeout: 15_000 })
    await expect(result).toHaveAttribute("data-valid", "true")

    // events_count >= 4: journey 4 genera al menos episodio_abierto +
    // prompt_enviado + tutor_respondio + episodio_cerrado.
    const countAttr = await result.getAttribute("data-events-count")
    const count = Number.parseInt(countAttr ?? "0", 10)
    expect(count, `events_count esperado >= 4, obtenido ${countAttr}`).toBeGreaterThanOrEqual(4)
  })
})
