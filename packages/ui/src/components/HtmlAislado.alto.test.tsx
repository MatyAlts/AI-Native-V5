/**
 * Aceptacion HU-035, vuelta de diseño (orquestador, antes de construir; el
 * constructor no la modifica). Pedido de Juani en la demo del 25/11: el
 * recuadro de la bienvenida dejaba un hueco blanco (alto fijo de 400px) y el
 * contenido largo quedaba scrolleando adentro. El recuadro tiene que tomar el
 * alto de su contenido, sin abrir el aislamiento.
 *
 * Contrato:
 *  - `documentoAislado(html)` agrega, despues de la CSP, un script que avisa
 *    el alto real con `parent.postMessage({ tipo: "html-aislado:altura",
 *    altura }, "*")` al cargar y cada vez que cambia (ResizeObserver).
 *  - `HtmlAislado` escucha `message` y SOLO acepta los que vienen de su propio
 *    iframe (`event.source === iframe.contentWindow`) con ese `tipo` y una
 *    altura numerica: pone `style.height` en px, entre 120 y 4000.
 *  - El sandbox sigue siendo solo `allow-scripts`.
 *
 * C08  El recuadro toma el alto que informa su contenido.
 * N10  Un mensaje de otra ventana, de otro tipo o con una altura que no es
 *      numero no cambia el alto (otro recuadro de la pagina no lo maneja).
 * N11  Alturas absurdas se acotan (un script no puede hacer la pagina infinita).
 */
import { act, cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { HtmlAislado, documentoAislado } from "../index"

afterEach(cleanup)

function montar(titulo = "Bienvenida del curso"): HTMLIFrameElement {
  render(<HtmlAislado html="<p>Hola</p>" titulo={titulo} />)
  return document.querySelector(`iframe[title="${titulo}"]`) as HTMLIFrameElement
}

function avisar(source: Window | null, data: unknown) {
  act(() => {
    window.dispatchEvent(new MessageEvent("message", { data, source }))
  })
}

describe("HU-035 · el recuadro toma el alto de su contenido", () => {
  it("C08: el documento trae el aviso de alto despues de la CSP", () => {
    const doc = documentoAislado("<p>Hola</p>")
    expect(doc).toContain("html-aislado:altura")
    expect(doc).toContain("postMessage")
    expect(doc.indexOf("Content-Security-Policy")).toBeLessThan(doc.indexOf("html-aislado:altura"))
  })

  it("C08: aplica el alto que informa su propio iframe", () => {
    const iframe = montar()
    avisar(iframe.contentWindow, { tipo: "html-aislado:altura", altura: 640 })
    expect(iframe.style.height).toBe("640px")
    avisar(iframe.contentWindow, { tipo: "html-aislado:altura", altura: 300 })
    expect(iframe.style.height).toBe("300px")
  })

  it("N10: ignora mensajes de otra ventana, de otro tipo o sin numero", () => {
    const iframe = montar()
    avisar(iframe.contentWindow, { tipo: "html-aislado:altura", altura: 500 })
    expect(iframe.style.height).toBe("500px")
    avisar(window, { tipo: "html-aislado:altura", altura: 900 })
    avisar(iframe.contentWindow, { tipo: "otra-cosa", altura: 900 })
    avisar(iframe.contentWindow, { tipo: "html-aislado:altura", altura: "900" })
    avisar(iframe.contentWindow, "html-aislado:altura")
    expect(iframe.style.height).toBe("500px")
  })

  it("N10: dos recuadros en la pagina no se pisan", () => {
    render(
      <>
        <HtmlAislado html="<p>a</p>" titulo="A" />
        <HtmlAislado html="<p>b</p>" titulo="B" />
      </>,
    )
    const a = document.querySelector('iframe[title="A"]') as HTMLIFrameElement
    const b = document.querySelector('iframe[title="B"]') as HTMLIFrameElement
    avisar(a.contentWindow, { tipo: "html-aislado:altura", altura: 700 })
    expect(a.style.height).toBe("700px")
    expect(b.style.height).not.toBe("700px")
  })

  it("N11: acota alturas absurdas", () => {
    const iframe = montar()
    avisar(iframe.contentWindow, { tipo: "html-aislado:altura", altura: 999999 })
    expect(iframe.style.height).toBe("4000px")
    avisar(iframe.contentWindow, { tipo: "html-aislado:altura", altura: 3 })
    expect(iframe.style.height).toBe("120px")
  })

  it("el aislamiento no cambia", () => {
    const iframe = montar()
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts")
  })
})
