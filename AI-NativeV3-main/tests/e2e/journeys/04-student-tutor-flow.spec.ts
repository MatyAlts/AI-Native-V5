import { mkdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"
import {
  COMISION_A_ID,
  COMISION_A_NOMBRE,
  TENANT_ID,
  WEB_STUDENT_URL,
} from "../fixtures/seeded-ids"
import { waitForTutorReply } from "../helpers/wait-for-tutor-stream"

const SHARED_DIR = path.resolve(__dirname, "../../../.dev-logs/e2e-shared")
const LAST_EPISODE_FILE = path.join(SHARED_DIR, "last-episode-id.txt")

/**
 * Journey 4 — web-student / Tutor flow.
 *
 * Flujo:
 *  1. Mockear `/api/v1/comisiones/mis` (gap B.2 documentado en CLAUDE.md:
 *     el endpoint devuelve [] para students hasta que F9 destrabe el JWT
 *     con `comisiones_activas`). El mock retorna la comision A-Manana del
 *     seed para que el ComisionSelector auto-seleccione.
 *  2. Navegar a /. La comision A-Manana se auto-selecciona, el TareaSelector
 *     lista 2 TPs (TP-01, TP-02) del seed.
 *  3. Click "Empezar a trabajar" en TP-01.
 *  4. Episodio abre — la url se actualiza y el editor + chat aparecen.
 *  5. Mandar "que es una variable?" via el textarea + Enter.
 *  6. Esperar respuesta SSE (helper con expect.poll, timeout 15s).
 *  7. Click "Cerrar episodio" -> aparece el panel de clasificacion.
 *  8. Capturar episode_id y persistir en .dev-logs/e2e-shared/ para journey 5.
 */

test.describe("web-student / Tutor flow", () => {
  test("abre TP, manda turno, recibe respuesta SSE, cierra episodio", async ({ page }) => {
    // 1. Mock del listMine() para que el selector tenga la comision A.
    await page.route("**/api/v1/comisiones/mis*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
            {
              id: COMISION_A_ID,
              tenant_id: TENANT_ID,
              codigo: "A",
              nombre: COMISION_A_NOMBRE,
              materia_id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
              periodo_id: "12345678-1234-1234-1234-123456789abc",
              cupo_maximo: 50,
              horario: {},
              ai_budget_monthly_usd: "100.00",
              curso_config_hash: "0".repeat(64),
              created_at: "2026-04-30T00:00:00Z",
              deleted_at: null,
            },
          ],
          meta: { cursor_next: null, total: 1 },
        }),
      })
    })

    let capturedEpisodeId: string | null = null

    // Instalamos el listener ANTES del goto para asegurar que captura cualquier
    // POST /api/v1/episodes que dispare la app (la URL del fetch del frontend
    // es relativa "/api/v1/episodes"; Vite la proxea al api-gateway, asi que
    // resp.url() puede venir como http://localhost:5175/api/v1/episodes o el
    // origen proxeado segun la version de Playwright — usar `endsWith` cubre
    // ambos casos).
    page.on("response", async (resp) => {
      // POST /api/v1/episodes (open) devuelve 201 Created con { episode_id }.
      // resp.ok() cubre cualquier 2xx por si el contrato cambia.
      const url = resp.url()
      const isOpenEpisode =
        resp.request().method() === "POST" &&
        resp.ok() &&
        /\/api\/v1\/episodes(?:\?.*)?$/.test(url)
      if (!isOpenEpisode) return
      try {
        const json = (await resp.json()) as { episode_id?: string }
        if (json.episode_id && !capturedEpisodeId) {
          capturedEpisodeId = json.episode_id
        }
      } catch {
        // not JSON — ignore
      }
    })

    // 2. Navegar al web-student.
    await page.goto(`${WEB_STUDENT_URL}/`)

    // Esperar a que el TareaSelector renderice las TP cards (significa que
    // la comision se auto-selecciono y la lista cargo).
    const cards = page.getByTestId("tp-card")
    await expect(cards.first()).toBeVisible({ timeout: 20_000 })
    expect(await cards.count()).toBeGreaterThanOrEqual(2)

    // 3. Click "Empezar a trabajar" en la primera TP card. El order del seed
    //    no es estable (TP-01 vs TP-02), pero a este journey le da igual cual.
    await cards
      .first()
      .getByRole("button", { name: /Empezar a trabajar/i })
      .click()

    // 4. Episodio abierto: el textarea del tutor debe aparecer.
    const tutorInput = page.getByTestId("tutor-input")
    await expect(tutorInput).toBeVisible({ timeout: 20_000 })

    // 5. Mandar el turno.
    await tutorInput.fill("que es una variable?")
    await tutorInput.press("Enter")

    // 6. Esperar respuesta SSE.
    await waitForTutorReply(page, 20_000)

    // 7. Cerrar episodio. El boton "Cerrar episodio" vive en el panel del
    //    editor (no del chat).
    await page.getByRole("button", { name: /Cerrar episodio/i }).click()

    // El panel de clasificacion aparece al cerrar (puede no aparecer si el
    // pipeline mock falla; tolerable). Pero como minimo el textarea ya no
    // debe estar visible (el episodio ya no esta abierto).
    await expect(tutorInput).toBeHidden({ timeout: 15_000 })

    // 8. Persistir el episode_id capturado para el journey 5.
    expect(
      capturedEpisodeId,
      "no se pudo capturar episode_id del POST /api/v1/episodes/open",
    ).toBeTruthy()
    if (capturedEpisodeId) {
      mkdirSync(SHARED_DIR, { recursive: true })
      writeFileSync(LAST_EPISODE_FILE, capturedEpisodeId, "utf8")
    }
  })
})

/**
 * Smoke A11y — web-student home (TareaSelector + ComisionSelector).
 *
 * Corre axe-core con tags wcag2a + wcag2aa sobre la landing del web-student
 * (la pantalla con cards de TPs antes de abrir un episodio). Idealmente
 * tambien cubririamos EpisodePage, pero abrirla requiere ai-gateway+tutor
 * estables y polluiria el smoke con concerns del journey principal.
 *
 * - critical/serious === 0 → falla el test (regresion bloqueante).
 * - moderate/minor → solo log (no falla; los reporta para fix futuro).
 */
test.describe("web-student / a11y smoke", () => {
  test("home no tiene violations critical/serious (wcag2a + wcag2aa)", async ({ page }) => {
    // Mock del listMine() (mismo que el journey principal — sin esto el selector
    // queda vacio y axe analiza solo el shell, sin TareaSelector/cards).
    await page.route("**/api/v1/comisiones/mis*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [
            {
              id: COMISION_A_ID,
              tenant_id: TENANT_ID,
              codigo: "A",
              nombre: COMISION_A_NOMBRE,
              materia_id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
              periodo_id: "12345678-1234-1234-1234-123456789abc",
              cupo_maximo: 50,
              horario: {},
              ai_budget_monthly_usd: "100.00",
              curso_config_hash: "0".repeat(64),
              created_at: "2026-04-30T00:00:00Z",
              deleted_at: null,
            },
          ],
          meta: { cursor_next: null, total: 1 },
        }),
      })
    })

    await page.goto(`${WEB_STUDENT_URL}/`)
    await page.waitForLoadState("domcontentloaded")
    // Best-effort: esperar a las cards si llegan (no fallar si no — el smoke
    // no depende del seed estando vivo, solo de que el shell renderice).
    await page
      .getByTestId("tp-card")
      .first()
      .waitFor({ state: "visible", timeout: 10_000 })
      .catch(() => {})

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()

    const blocking = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    )
    const advisory = results.violations.filter(
      (v) => v.impact === "moderate" || v.impact === "minor",
    )

    if (advisory.length > 0) {
      console.warn(
        `[a11y][web-student] ${advisory.length} advisory violations (moderate/minor):`,
        advisory.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
      )
    }

    if (blocking.length > 0) {
      console.error(
        `[a11y][web-student] ${blocking.length} BLOCKING violations (critical/serious):`,
        JSON.stringify(
          blocking.map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            helpUrl: v.helpUrl,
            nodes: v.nodes.map((n) => ({ target: n.target, html: n.html })),
          })),
          null,
          2,
        ),
      )
    }

    expect(blocking, "violations critical/serious detectadas; ver console.error").toHaveLength(0)
  })
})
