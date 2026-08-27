// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import { OnboardingProvider } from "@platform/ui"
import { useRouterState } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { alumnoOnboarding } from "./alumnoOnboarding"
import { useEstadoAlumno } from "./estado"

/**
 * Enchufa el onboarding progresivo al arbol del web-student.
 *
 * El motor de `@platform/ui` NO conoce el router: la ruta actual se la pasamos
 * nosotros. Por eso este componente vive aca y no en el paquete compartido.
 *
 * Se monta SOLO con el alumno ya autenticado (ver `routes/__root.tsx`): el
 * estado sale de endpoints que sin identidad devuelven 401, y ademas no tiene
 * sentido ensenarle la plataforma a quien todavia no entro.
 */
export function OnboardingAlumno({ children }: { children: ReactNode }) {
  const estado = useEstadoAlumno()
  // La prop del motor se llama `route` aunque su vecina sea `estado`: mezcla
  // idiomas, pero ya la consumen dos apps y sus tests. No se renombra.
  const route = useRouterState({ select: (s) => s.location.pathname })

  return (
    <OnboardingProvider flow={alumnoOnboarding} estado={estado} route={route}>
      {children}
    </OnboardingProvider>
  )
}
