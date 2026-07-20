/**
 * Walkthrough Docente — ~8 min.
 *
 * Estrategia: navegación por URL directa siempre que se pueda. Cada sección
 * tiene un timeout FIJO que SIEMPRE corre.
 */
import { test } from "@playwright/test"

const TEACHER_URL = "http://localhost:5174"
const COM = "7b18f4d8-24b7-4034-979e-1fd464939f0e"
const STUDENT_DEMO = "c1c1c1c1-0001-0001-0001-000000000001"

async function navAndWait(page, path: string, waitMs: number) {
  await page.goto(`${TEACHER_URL}${path}`)
  await page.waitForLoadState("networkidle").catch(() => {})
  await page.waitForTimeout(waitMs)
}

test("walkthrough-docente", async ({ page }) => {
  // ── 0:00 Dashboard + KPIs ─────────────────────────────────────────
  await navAndWait(page, `/?comisionId=${COM}`, 10_000) // 0:10

  // ── 0:45 Trabajos Prácticos (skipeamos plantillas por simplicidad) ──
  await navAndWait(page, `/tareas-practicas?comisionId=${COM}`, 12_000) // 0:57

  // ── 1:45 Unidades ─────────────────────────────────────────────────
  await navAndWait(page, `/unidades?comisionId=${COM}`, 10_000) // 1:55

  // ── 2:30 Templates / Plantillas ───────────────────────────────────
  await navAndWait(page, `/templates?comisionId=${COM}`, 10_000) // 2:40

  // ── 3:15 Progresión (cohorte) ─────────────────────────────────────
  await navAndWait(page, `/progression?comisionId=${COM}`, 13_000) // 3:28

  // ── 4:15 Evolución por estudiante (drill-down) ────────────────────
  await navAndWait(
    page,
    `/student-longitudinal?comisionId=${COM}&studentId=${STUDENT_DEMO}`,
    15_000,
  ) // 4:30

  // ── 5:15 Cuartiles CII ────────────────────────────────────────────
  await navAndWait(page, `/cohort-quartiles?comisionId=${COM}`, 12_000) // 5:27

  // ── 6:10 Intentos adversos ────────────────────────────────────────
  await navAndWait(page, `/cohort-adversarial?comisionId=${COM}`, 13_000) // 6:23

  // ── 7:00 Instrumentos research ────────────────────────────────────
  await navAndWait(page, `/instrumentos-cohorte?comisionId=${COM}`, 15_000) // 7:15

  // ── 8:00 Inter-rater (kappa) ──────────────────────────────────────
  await navAndWait(page, `/kappa?comisionId=${COM}`, 8_000) // 8:08
  // Click una categoría del primer episodio
  try {
    await page
      .getByRole("button", { name: /Aut[oó]nomo/i })
      .first()
      .click({ timeout: 4000 })
    await page.waitForTimeout(3_000) // 8:11 — destacar "✓ Coincidís"
  } catch {
    await page.waitForTimeout(3_000)
  }

  // ── 8:45 Banco de ejercicios ──────────────────────────────────────
  await navAndWait(page, `/ejercicios?comisionId=${COM}`, 8_000) // 8:53

  // ── 9:15 Exportar ─────────────────────────────────────────────────
  await navAndWait(page, `/export?comisionId=${COM}`, 8_000) // 9:23 — outro
})
