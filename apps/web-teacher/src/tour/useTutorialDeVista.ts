// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import { type TourFlow, useTourOpcional } from "@platform/ui"
import { useEffect, useRef } from "react"

/**
 * Dispara el tutorial de UNA vista (capa 2) la primera vez que el docente entra.
 *
 * Convivencia con el panoramico (capa 1) — el problema real que resuelve esta guarda:
 * el panoramico NAVEGA por estas mismas vistas, asi que cada vista se monta con un
 * tour ya corriendo. Sin guarda, el tutorial de la vista se abriria encima; y si solo
 * miraramos `activo` en el momento de disparar, se abriria igual apenas el panoramico
 * termine, porque el efecto vuelve a correr cuando `activo` pasa a false.
 *
 * Por eso la guarda es por VISITA y no por instante: si al montar (o en cualquier
 * momento antes de disparar) hay un tour activo, esta visita queda bloqueada para
 * siempre. El tutorial arranca la proxima vez que el docente entre por su cuenta.
 *
 * `listo` posterga el disparo hasta que la vista tenga algo que iluminar. Un tutorial
 * disparado sobre una pantalla en blanco degrada a cuatro cards centradas y no ensena
 * nada: los pasos anclados no encuentran su ancla.
 */
export function useTutorialDeVista(flow: TourFlow, listo = true): void {
  const tour = useTourOpcional()
  const maybeStart = tour?.maybeStart
  const activo = tour?.activo ?? false
  const bloqueado = useRef(false)
  const disparado = useRef(false)

  useEffect(() => {
    if (activo && !disparado.current) bloqueado.current = true
  }, [activo])

  useEffect(() => {
    if (!maybeStart || !listo || activo || bloqueado.current || disparado.current) return
    disparado.current = true
    maybeStart(flow)
  }, [flow, listo, activo, maybeStart])
}
