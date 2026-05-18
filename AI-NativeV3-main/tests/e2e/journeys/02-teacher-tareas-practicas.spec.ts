import { expect, test } from "@playwright/test"
import { COMISION_A_ID, WEB_TEACHER_URL } from "../fixtures/seeded-ids"

/**
 * Journey 2 — web-teacher / Trabajos Practicos.
 *
 * Flujo:
 *  1. Navegar a /tareas-practicas?comisionId=A. La comision A-Manana entra
 *     directo via search param (no hace falta abrir el selector).
 *  2. Esperar que la tabla muestre al menos 2 TPs (TP-01 y TP-02 del seed).
 *  3. Click "+ Nuevo TP" -> modal abre.
 *  4. Click el boton "X" de cierre del modal -> modal cierra.
 */

test.describe("web-teacher / Tareas Practicas", () => {
  test("lista TPs y abre/cierra modal de Nuevo TP", async ({ page }) => {
    await page.goto(`${WEB_TEACHER_URL}/tareas-practicas?comisionId=${COMISION_A_ID}`)

    // 2. Tabla con >=2 TPs publicadas. La fila contiene el codigo del TP.
    await expect(page.getByRole("cell", { name: "TP-01" })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole("cell", { name: "TP-02" })).toBeVisible()

    // 3. Click "+ Nuevo TP" -> modal abre.
    await page.getByRole("button", { name: /Nuevo TP/i }).click()
    const modal = page.getByRole("dialog")
    await expect(modal).toBeVisible()
    await expect(modal).toContainText(/Nuevo trabajo practico/i)

    // 4. Cerrar modal sin guardar (presionando Escape).
    await page.keyboard.press("Escape")
    await expect(modal).toBeHidden()
  })
})
