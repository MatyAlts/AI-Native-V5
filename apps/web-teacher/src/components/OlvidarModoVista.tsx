import { useEffect } from "react"

/**
 * HU-022: se monta dentro de `<SignedOut>`. Al cerrar sesion (UserButton de
 * Clerk) la pagina queda sin sesion y esto borra `localStorage["modo-vista"]`,
 * la eleccion "Ver como alumno" que comparten web-teacher y web-student (mismo
 * origen). Asi el proximo que entre en esa compu no queda en la vista de alumno.
 */
export function OlvidarModoVista() {
  useEffect(() => {
    try {
      window.localStorage.removeItem("modo-vista")
    } catch {
      /* sin localStorage no hay nada guardado */
    }
  }, [])
  return null
}
