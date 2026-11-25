/**
 * Aceptacion HU-033 (orquestador, antes de construir; el constructor no la
 * modifica). El HTML del campus (bienvenida e introduccion) lo escribe el
 * docente y puede traer JS: se muestra SIEMPRE dentro de un recuadro aislado,
 * el mismo para la vista previa del docente y para el alumno (HU-035).
 *
 * Contrato: `<HtmlAislado html titulo />` exportado de `@platform/ui`.
 * Renderiza un <iframe title={titulo}> con `srcDoc` y `sandbox`.
 *
 * C04  El HTML del docente se muestra en el recuadro y sus scripts pueden
 *      correr (sandbox con allow-scripts).
 * N02  El recuadro NO comparte origen con la plataforma: sin
 *      allow-same-origin (con eso el JS leeria la sesion), sin
 *      allow-top-navigation (no puede sacar al usuario de la pagina) y sin
 *      allow-forms. Solo se permite allow-scripts y, opcional, allow-popups.
 * N04  El documento del recuadro lleva una politica de contenido que corta
 *      las conexiones del JS (connect-src 'none'): el script no puede
 *      mandar datos a ningun lado con fetch.
 * N06  El HTML no se inyecta en la pagina: no queda ningun <script> del
 *      docente en el documento de la plataforma.
 */
import { cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { HtmlAislado } from "../index"

afterEach(cleanup)

const HTML = "<h2>Bienvenidos</h2><script>window.__docente = 1</script>"

function recuadro(): HTMLIFrameElement {
  render(<HtmlAislado html={HTML} titulo="Bienvenida del curso" />)
  const iframe = document.querySelector('iframe[title="Bienvenida del curso"]')
  expect(iframe, "falta el iframe con el titulo").not.toBeNull()
  return iframe as HTMLIFrameElement
}

describe("HU-033 · recuadro aislado para el HTML del campus", () => {
  it("C04: muestra el HTML del docente con scripts permitidos", () => {
    const iframe = recuadro()
    const doc = iframe.getAttribute("srcdoc") ?? ""
    expect(doc).toContain("<h2>Bienvenidos</h2>")
    expect(doc).toContain("window.__docente = 1")
    const permisos = (iframe.getAttribute("sandbox") ?? "").split(/\s+/).filter(Boolean)
    expect(permisos).toContain("allow-scripts")
  })

  it("N02: sin mismo origen, sin navegar la pagina y sin formularios", () => {
    const iframe = recuadro()
    expect(iframe.hasAttribute("sandbox")).toBe(true)
    const permisos = (iframe.getAttribute("sandbox") ?? "").split(/\s+/).filter(Boolean)
    for (const p of permisos) {
      expect(["allow-scripts", "allow-popups"]).toContain(p)
    }
    expect(permisos).not.toContain("allow-same-origin")
    expect(permisos).not.toContain("allow-top-navigation")
  })

  it("N04: el documento corta las conexiones del JS", () => {
    const doc = recuadro().getAttribute("srcdoc") ?? ""
    // El valor de la CSP lleva comillas simples ('none'), asi que se lee
    // hasta la comilla doble que lo cierra.
    const csp = /<meta[^>]+http-equiv="Content-Security-Policy"[^>]*content="([^"]+)"/i.exec(doc)
    expect(csp, "falta la meta CSP en el srcdoc").not.toBeNull()
    expect(csp?.[1]).toMatch(/connect-src 'none'/)
    // La CSP va antes que el HTML del docente, asi rige para sus scripts.
    expect(doc.indexOf("Content-Security-Policy")).toBeLessThan(doc.indexOf("<h2>Bienvenidos</h2>"))
  })

  it("N06: el script del docente no queda en el documento de la plataforma", () => {
    recuadro()
    const scriptsSueltos = Array.from(document.querySelectorAll("script")).filter((s) =>
      (s.textContent ?? "").includes("__docente"),
    )
    expect(scriptsSueltos).toHaveLength(0)
    // El HTML viaja como atributo srcdoc del iframe; lo que no puede pasar es
    // que sus elementos existan en el documento de la plataforma.
    const titulos = Array.from(document.querySelectorAll("h2")).filter(
      (h) => h.textContent === "Bienvenidos",
    )
    expect(titulos).toHaveLength(0)
  })
})
