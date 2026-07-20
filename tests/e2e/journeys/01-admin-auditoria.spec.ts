import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"
import {
  COMISION_A_ID,
  DOCENTE_USER_ID,
  STUDENT_A1_ID,
  TENANT_ID,
  WEB_ADMIN_URL,
} from "../fixtures/seeded-ids"

/**
 * Journey 1 — web-admin / Auditoria CTR.
 *
 * Flujo:
 *  1. Resolver un episode_id cerrado del seed (consultar via api-gateway un
 *     listado de episodios del student A1; tomar el primero closed).
 *  2. Navegar a /auditoria, pegar el id, click "Verificar integridad".
 *  3. Assertear que aparece `data-testid=audit-result` con `data-valid=true`.
 */

test.describe("web-admin / Auditoria CTR", () => {
  test("verifica un episodio cerrado del seed y muestra valid=true", async ({ page, request }) => {
    // 1. Buscar un episodio del student A1 via api-gateway -> analytics-service.
    //    El endpoint devuelve solo episodios cerrados+clasificados (lo que
    //    necesita la auditoria CTR).
    const listRes = await request.get(
      `http://127.0.0.1:8000/api/v1/analytics/student/${STUDENT_A1_ID}/episodes?comision_id=${COMISION_A_ID}`,
      {
        headers: {
          "X-Tenant-Id": TENANT_ID,
          "X-User-Id": DOCENTE_USER_ID,
          "X-User-Email": "docente@demo-uni.edu",
          "X-User-Roles": "docente_admin",
        },
      },
    )
    expect(listRes.ok(), "no se pudo listar episodios del student A1").toBeTruthy()
    const list = (await listRes.json()) as {
      n_episodes: number
      episodes: Array<{ episode_id: string; closed_at: string | null }>
    }
    const closed = list.episodes.find((e) => e.closed_at !== null)
    expect(closed, "no hay episodios closed del student A1; revisa el seed").toBeTruthy()
    if (!closed) throw new Error("unreachable")
    const episodeId = closed.episode_id

    // 2. Navegar al web-admin y entrar a Auditoria via sidebar.
    //    web-admin usa router interno por state (no URL-based) — clickear el item.
    await page.goto(`${WEB_ADMIN_URL}/`)
    await page.getByRole("button", { name: /Integridad CTR/i }).click()

    const input = page.getByLabel(/Episode ID/i)
    await input.fill(episodeId)

    await page.getByRole("button", { name: /Verificar integridad/i }).click()

    // 3. El resultado debe aparecer con valid=true.
    const result = page.getByTestId("audit-result")
    await expect(result).toBeVisible({ timeout: 10_000 })
    await expect(result).toHaveAttribute("data-valid", "true")
    await expect(result).toContainText(/Cadena integra|Cadena íntegra/i)
  })
})

/**
 * Smoke A11y — web-admin home.
 *
 * Corre axe-core con tags wcag2a + wcag2aa sobre la home del web-admin.
 * - critical/serious === 0 → falla el test (regresion bloqueante).
 * - moderate/minor → solo log (no falla; los reporta para fix futuro).
 *
 * NOTA: este test NO depende del seed ni del api-gateway — solo necesita que
 * los frontends Vite esten levantados (web-admin en :5173). Si el global-setup
 * los esta levantando para el journey principal, este test reusa esa instancia.
 */
test.describe("web-admin / a11y smoke", () => {
  test("home no tiene violations critical/serious (wcag2a + wcag2aa)", async ({ page }) => {
    await page.goto(`${WEB_ADMIN_URL}/`)
    // Esperar al primer landmark/heading para asegurar render del shell.
    await page.waitForLoadState("domcontentloaded")

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()

    const blocking = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    )
    const advisory = results.violations.filter(
      (v) => v.impact === "moderate" || v.impact === "minor",
    )

    if (advisory.length > 0) {
      console.warn(
        `[a11y][web-admin] ${advisory.length} advisory violations (moderate/minor):`,
        advisory.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
      )
    }

    if (blocking.length > 0) {
      console.error(
        `[a11y][web-admin] ${blocking.length} BLOCKING violations (critical/serious):`,
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
