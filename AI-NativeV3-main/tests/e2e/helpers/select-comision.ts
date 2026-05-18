import type { Page } from "@playwright/test"
import type {
  COMISION_A_NOMBRE,
  COMISION_B_NOMBRE,
  COMISION_C_NOMBRE,
} from "../fixtures/seeded-ids"

type ComisionName = typeof COMISION_A_NOMBRE | typeof COMISION_B_NOMBRE | typeof COMISION_C_NOMBRE

/**
 * Selecciona una comision en el `<select>` del header (ComisionSelector).
 *
 * Reusable en journeys 2, 3, 4. El selector renderiza un `<select>` real
 * (no Radix combobox), por lo que `selectOption({ label })` alcanza.
 */
export async function selectComision(page: Page, nombre: ComisionName): Promise<void> {
  const select = page.getByLabel(/Comisi(o|ó)n:/i)
  await select.waitFor({ state: "visible", timeout: 10_000 })
  await select.selectOption({ label: nombre })
}
