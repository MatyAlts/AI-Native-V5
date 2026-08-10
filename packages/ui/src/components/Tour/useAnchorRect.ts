// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import { useEffect, useState } from "react"

export interface Rect {
  top: number
  left: number
  width: number
  height: number
}

/** Cuanto esperamos a que el ancla aparezca antes de degradar a card centrada. */
const TIMEOUT_MS = 2500
const POLL_MS = 100

/**
 * Resuelve `[data-tour="<anchor>"]` y devuelve su rect en coordenadas de viewport.
 *
 * Devuelve `null` en dos casos que el overlay trata igual (card centrada, sin recorte):
 * el paso no declara ancla, o el ancla no aparecio dentro del timeout. Ese segundo caso
 * es el que evita que un refactor de markup deje el tour colgado: pierde el spotlight,
 * no el contenido.
 */
export function useAnchorRect(anchor: string | undefined, stepId: string): Rect | null {
  const [rect, setRect] = useState<Rect | null>(null)

  // biome-ignore lint/correctness/useExhaustiveDependencies: `stepId` no se usa adentro; esta a proposito, para re-buscar el ancla cuando cambia el cartel aunque el selector sea el mismo (el nodo del DOM puede ser otro).
  useEffect(() => {
    if (!anchor) {
      setRect(null)
      return
    }

    let cancelado = false
    let el: HTMLElement | null = null
    let observer: ResizeObserver | null = null

    const medir = () => {
      if (cancelado || !el) return
      const r = el.getBoundingClientRect()
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height })
    }

    const enganchar = (encontrado: HTMLElement) => {
      el = encontrado
      // `nearest` en vez de `center`: si el elemento ya se ve, no movemos nada. Un salto
      // de scroll gratuito le hace perder al alumno de donde venia.
      encontrado.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" })
      medir()
      observer = new ResizeObserver(medir)
      observer.observe(encontrado)
      window.addEventListener("scroll", medir, true)
      window.addEventListener("resize", medir)
    }

    const inicio = Date.now()
    const buscar = () => {
      if (cancelado) return
      const encontrado = document.querySelector<HTMLElement>(`[data-tour="${anchor}"]`)
      if (encontrado) {
        enganchar(encontrado)
        return
      }
      if (Date.now() - inicio < TIMEOUT_MS) {
        window.setTimeout(buscar, POLL_MS)
      } else {
        setRect(null)
      }
    }

    setRect(null)
    buscar()

    return () => {
      cancelado = true
      observer?.disconnect()
      window.removeEventListener("scroll", medir, true)
      window.removeEventListener("resize", medir)
    }
  }, [anchor, stepId])

  return rect
}
