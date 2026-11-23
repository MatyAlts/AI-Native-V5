import { useEffect } from "react"
import { olvidarModoVista } from "../utils/modoVista"

/**
 * HU-022: se monta dentro de `<SignedOut>`. Al cerrar sesion (UserButton de
 * Clerk) la pagina queda sin sesion y esto borra `localStorage["modo-vista"]`.
 */
export function OlvidarModoVista() {
  useEffect(() => {
    olvidarModoVista()
  }, [])
  return null
}
