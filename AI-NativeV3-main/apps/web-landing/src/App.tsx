/**
 * Landing page de AI-Native N4 — tesis doctoral UNSL.
 *
 * Estructura (scroll vertical, full-width):
 *   1. Hero
 *   2. Qué hace
 *   3. Arquitectura interactiva
 *   4. Las 5 coherencias N4
 *   5. Cadena criptográfica CTR
 *   6. Modelo de datos (UML)
 *   7. Flujo del alumno
 *   8. Stack técnico
 *   9. Números del piloto
 *   10. Acceso a los 3 frontends
 *   11. Para Neyen (guía QA)
 *   12. Footer
 */
import { Hero } from "./sections/Hero"
import { QueHace } from "./sections/QueHace"
import { Arquitectura } from "./sections/Arquitectura"
import { CoherenciasN4 } from "./sections/CoherenciasN4"
import { CadenaCTR } from "./sections/CadenaCTR"
import { ModeloDatos } from "./sections/ModeloDatos"
import { FlujoAlumno } from "./sections/FlujoAlumno"
import { Stack } from "./sections/Stack"
import { Metricas } from "./sections/Metricas"
import { Acceso } from "./sections/Acceso"
import { ParaNeyen } from "./sections/ParaNeyen"
import { Footer } from "./sections/Footer"

export function App() {
  return (
    <main className="bg-bg text-ink">
      <Hero />
      <QueHace />
      <Arquitectura />
      <CoherenciasN4 />
      <CadenaCTR />
      <ModeloDatos />
      <FlujoAlumno />
      <Stack />
      <Metricas />
      <Acceso />
      <ParaNeyen />
      <Footer />
    </main>
  )
}
