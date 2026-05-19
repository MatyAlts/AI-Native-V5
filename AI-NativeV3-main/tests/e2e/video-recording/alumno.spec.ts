/**
 * Walkthrough Alumno — ~7-8 min con tutor Mistral REAL.
 *
 * Estrategia: paso-a-paso porque requiere interacción real (abrir episodio,
 * conversar con tutor, ejecutar código, cerrar, reflexionar).
 */
import { test } from "@playwright/test"

const STUDENT_URL = "http://localhost:5175"

test("walkthrough-alumno", async ({ page }) => {
  // ── 0:00 Home — Mis materias ──────────────────────────────────────
  await page.goto(`${STUDENT_URL}/`)
  await page.waitForLoadState("networkidle").catch(() => {})
  await page.waitForTimeout(8_000) // 0:08

  // ── 0:45 Entrar a la materia ──────────────────────────────────────
  try {
    await page.getByRole("button", { name: /Entrar/i }).click({ timeout: 5000 })
    await page.waitForLoadState("networkidle").catch(() => {})
  } catch {}
  await page.waitForTimeout(6_000) // 0:51

  // ── 1:15 Click en unidad "Variables y Tipos" ──────────────────────
  // (puede estar en otra unidad — usamos getByText con fallback)
  try {
    await page
      .getByRole("button")
      .filter({ hasText: /Variables y Tipos|Sin unidad asignada|Repetitivas/i })
      .first()
      .click({ timeout: 5000 })
    await page.waitForLoadState("networkidle").catch(() => {})
  } catch {}
  await page.waitForTimeout(7_000) // 1:22

  // ── 2:00 Abrir el primer TP — Click "Empezar"/"Continuar" ─────────
  try {
    await page
      .getByRole("button", { name: /Empezar|Continuar/i })
      .first()
      .click({ timeout: 5000 })
    await page.waitForLoadState("networkidle").catch(() => {})
  } catch {}
  await page.waitForTimeout(8_000) // 2:08 — esperar editor

  // ── 2:50 Mostrar consigna + editor + tutor ────────────────────────
  await page.waitForTimeout(10_000) // 3:00

  // ── 3:00 Tutor: escribir prompt ───────────────────────────────────
  try {
    const textarea = page.locator('textarea[placeholder*="Escrib"]').first()
    await textarea.click({ timeout: 5000 })
    await textarea.fill(
      "Hola, no entiendo bien la diferencia entre int y bool en Python. Bool es como un numero?",
    )
    await page.waitForTimeout(2_000) // 3:02

    // Click Enviar y esperar respuesta de Mistral
    await page
      .getByRole("button", { name: /^Enviar mensaje$|^Enviar$/ })
      .first()
      .click({ timeout: 5000 })
    await page.waitForTimeout(15_000) // 3:17 — Mistral tarda ~3-10s
  } catch {
    await page.waitForTimeout(17_000)
  }

  // ── 3:30 Pausa para mostrar respuesta socrática ───────────────────
  await page.waitForTimeout(10_000) // 3:40

  // ── 4:30 Editar código en Monaco ──────────────────────────────────
  try {
    const monacoEditor = page.locator(".monaco-editor textarea").first()
    await monacoEditor.click({ timeout: 5000 })
    await page.waitForTimeout(1_500)
    await monacoEditor.fill(`# Probar bool como int
print(True + True)  # esperado: 2
print(False == 0)   # esperado: True
print(type(True))   # esperado: <class 'bool'>
`)
    await page.waitForTimeout(3_000) // 4:33
  } catch {
    await page.waitForTimeout(4_500)
  }

  // ── 5:00 Ejecutar ─────────────────────────────────────────────────
  try {
    await page
      .getByRole("button", { name: /Ejecutar|▶/i })
      .first()
      .click({ timeout: 5000 })
    await page.waitForTimeout(8_000) // 5:08 — Pyodide tarda
  } catch {
    await page.waitForTimeout(8_000)
  }
  await page.waitForTimeout(5_000) // 5:13 — mostrar output

  // ── 5:30 Cerrar episodio ──────────────────────────────────────────
  try {
    await page
      .locator('[data-testid="close-episode-button"]')
      .click({ timeout: 5000 })
    await page.waitForTimeout(4_000) // 5:34 — modal aparece
  } catch {
    await page.waitForTimeout(4_000)
  }

  // ── 6:00 Modal reflexión — escribir y enviar ──────────────────────
  try {
    const reflexionTA = page.locator("textarea").first()
    await reflexionTA.click({ timeout: 5000 })
    await reflexionTA.fill(
      "Cuando el tutor me hizo la pregunta sobre True+True hice la prueba y vi que da 2. Me cerro que bool es una subclase de int.",
    )
    await page.waitForTimeout(4_000) // 6:04

    await page
      .getByRole("button", { name: /^Enviar$/ })
      .first()
      .click({ timeout: 5000 })
    await page.waitForLoadState("networkidle").catch(() => {})
  } catch {}
  await page.waitForTimeout(8_000) // 6:12 — pantalla de cierre con feedback

  // ── 7:00 Ir a Mis reflexiones ─────────────────────────────────────
  await page.goto(`${STUDENT_URL}/reflexiones`)
  await page.waitForLoadState("networkidle").catch(() => {})
  await page.waitForTimeout(8_000) // 7:08

  // ── 7:30 Cuestionarios de investigación ───────────────────────────
  await page.goto(
    `${STUDENT_URL}/instrumentos?comisionId=7b18f4d8-24b7-4034-979e-1fd464939f0e`,
  )
  await page.waitForLoadState("networkidle").catch(() => {})
  await page.waitForTimeout(10_000) // 7:48

  // ── 8:00 Scroll suave para mostrar el largo ───────────────────────
  await page.evaluate(() => {
    const sc = document.querySelector(".overflow-y-auto") as HTMLElement | null
    if (sc) {
      let pos = 0
      const id = setInterval(() => {
        pos += 80
        sc.scrollTop = pos
        if (pos > 900) clearInterval(id)
      }, 200)
    }
  })
  await page.waitForTimeout(6_000) // 8:06 — fin
})
