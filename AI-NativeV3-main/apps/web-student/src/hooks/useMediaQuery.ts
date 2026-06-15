/**
 * Hook chico para reaccionar a un media query via `matchMedia`.
 *
 * Devuelve `true` cuando el query matchea. SSR-safe: si `window` no existe
 * (o no hay `matchMedia`, p.ej. jsdom sin polyfill) devuelve `false`.
 *
 * Usado por EpisodePage para colapsar los 3 paneles redimensionables a un
 * selector de tabs bajo `lg` (390px los comprimia a ~130px c/u, inusable).
 */
import { useEffect, useState } from "react"

export function useMediaQuery(query: string): boolean {
  const getMatch = () => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false
    }
    return window.matchMedia(query).matches
  }

  const [matches, setMatches] = useState<boolean>(getMatch)

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return
    }
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    // Sync inicial por si el valor cambio entre el render y el effect.
    onChange()
    mql.addEventListener("change", onChange)
    return () => mql.removeEventListener("change", onChange)
  }, [query])

  return matches
}
