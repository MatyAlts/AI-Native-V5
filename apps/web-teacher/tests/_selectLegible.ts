// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
/**
 * Un `<select>` nativo tiene que declarar fondo y color de letra propios.
 *
 * Por que: el preflight de Tailwind le pone `background-color: transparent` a todo
 * `select`. Chrome en Windows no puede pintar transparente la lista que despliega y
 * la pinta NEGRA, con la letra oscura heredada encima: ilegible (reportado en la
 * prueba local del PR #138, 05/11/2026). Los selects del resto del panel ya traen
 * `bg-*` y `text-ink` (ver `ComisionSelector.tsx`); este chequeo lo exige donde se use.
 */
import { expect } from "vitest"

export function esperarSelectsLegibles(raiz: ParentNode, minimo = 1): void {
  const selects = Array.from(raiz.querySelectorAll("select"))
  expect(selects.length).toBeGreaterThanOrEqual(minimo)
  for (const select of selects) {
    const clases = Array.from(select.classList)
    const nombre = select.id || select.getAttribute("aria-label") || select.outerHTML.slice(0, 80)
    expect(
      clases.some((c) => /^bg-(?!transparent$|opacity)/.test(c)),
      `select sin fondo propio: ${nombre}`,
    ).toBe(true)
    expect(clases, `select sin color de letra propio: ${nombre}`).toContain("text-ink")
  }
}
