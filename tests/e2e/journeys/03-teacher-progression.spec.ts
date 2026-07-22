import { expect, test } from "@playwright/test"
import { COMISION_B_ID, WEB_TEACHER_URL } from "../fixtures/seeded-ids"

/**
 * Journey 3 — web-teacher / Progresion.
 *
 * Flujo:
 *  1. Navegar a /progression?comisionId=B-Tarde (cohorte balanceada del seed,
 *     con varios estudiantes -> labels mejorando/estable visibles).
 *  2. Assert: 4 cards resumen (Mejorando / Estable / Empeorando / Datos
 *     insuficientes) renderizan.
 *  3. Assert: al menos 1 fila de estudiante con `data-testid=student-row`.
 */

test.describe("web-teacher / Progresion", () => {
  test("muestra 4 cards resumen y al menos 1 fila de estudiante", async ({ page }) => {
    await page.goto(`${WEB_TEACHER_URL}/progression?comisionId=${COMISION_B_ID}`)

    // 2. 4 cards resumen.
    await expect(page.getByText(/^Mejorando$/)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/^Estable$/)).toBeVisible()
    await expect(page.getByText(/^Empeorando$/)).toBeVisible()
    await expect(page.getByText(/^Datos insuficientes$/)).toBeVisible()

    // 3. Al menos 1 fila de estudiante. El seed B-Tarde tiene 6 estudiantes con
    //    >=3 episodios cada uno, asi que la lista no deberia estar vacia.
    const rows = page.getByTestId("student-row")
    await expect(rows.first()).toBeVisible({ timeout: 10_000 })
    expect(await rows.count()).toBeGreaterThanOrEqual(1)
  })
})
