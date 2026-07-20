/**
 * Walkthrough Admin — ~6-7 min.
 *
 * Estrategia: navegación por URL directa donde es posible, con clicks
 * silenciados (try/catch) solo cuando hay que interactuar. Cada sección
 * tiene un timeout FIJO que SIEMPRE corre, garantizando duración total
 * consistente para sincronizar voz.
 */
import { test } from "@playwright/test"

const ADMIN_URL = "http://localhost:5173"
const EPISODE_REAL = "d938f6de-de58-4158-8cbb-51bad97e0240"

async function clickMenu(page, label: string) {
  // Click silenciado al sidebar — si no encuentra el botón, sigue sin error
  try {
    await page.getByRole("button", { name: new RegExp(label, "i") }).first().click({ timeout: 5000 })
  } catch {
    // ignoring — el wait posterior da tiempo de igual
  }
}

test("walkthrough-admin", async ({ page }) => {
  // ── 0:00 Intro: home admin ────────────────────────────────────────
  await page.goto(`${ADMIN_URL}/`)
  await page.waitForLoadState("networkidle").catch(() => {})
  await page.waitForTimeout(8_000) // 0:08

  // ── 0:30 Universidades ────────────────────────────────────────────
  await clickMenu(page, "^Universidades$")
  await page.waitForTimeout(10_000) // 0:40

  // ── 1:15 Facultades ───────────────────────────────────────────────
  await clickMenu(page, "Facultades")
  await page.waitForTimeout(10_000) // 1:25

  // ── 2:00 Carreras ─────────────────────────────────────────────────
  await clickMenu(page, "^Carreras$")
  await page.waitForTimeout(8_000) // 2:08

  // ── 2:30 Planes ───────────────────────────────────────────────────
  await clickMenu(page, "^Planes$")
  await page.waitForTimeout(8_000) // 2:38

  // ── 3:00 Materias ─────────────────────────────────────────────────
  await clickMenu(page, "^Materias$")
  await page.waitForTimeout(12_000) // 3:12 — destacar PROG1 UTN

  // ── 3:45 Comisiones ───────────────────────────────────────────────
  await clickMenu(page, "^Comisiones$")
  await page.waitForTimeout(12_000) // 3:57 — mostrar las 5 comisiones

  // ── 4:30 Períodos ─────────────────────────────────────────────────
  await clickMenu(page, "Per[ií]odos")
  await page.waitForTimeout(8_000) // 4:38

  // ── 5:00 Bulk Import ──────────────────────────────────────────────
  await clickMenu(page, "Bulk.?Import")
  await page.waitForTimeout(10_000) // 5:10

  // ── 5:45 Clasificaciones ──────────────────────────────────────────
  await clickMenu(page, "Clasificaciones")
  await page.waitForTimeout(8_000) // 5:53

  // ── 6:15 Auditoría CTR (CLIMAX) ───────────────────────────────────
  await clickMenu(page, "Integridad CTR|Auditor")
  await page.waitForTimeout(4_000) // 6:19

  // Pegar el episode_id real
  try {
    const input = page.locator('input[placeholder*="00000000"]').first()
    await input.fill(EPISODE_REAL, { timeout: 5000 })
    await page.waitForTimeout(3_000) // 6:22

    // Click Verificar
    await page
      .getByRole("button", { name: /Verificar integridad/i })
      .click({ timeout: 5000 })
    await page.waitForTimeout(8_000) // 6:30 — mostrar "Cadena íntegra = true"
  } catch {
    await page.waitForTimeout(11_000) // si algo falla, mantener timing total
  }

  // Final
  await page.waitForTimeout(6_000) // 6:36 — outro
})
