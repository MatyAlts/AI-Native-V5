import { Admin } from "./sections/Admin"
import { Alumno } from "./sections/Alumno"
import { Beneficios } from "./sections/Beneficios"
import { CTAFinal } from "./sections/CTAFinal"
import { Footer } from "./sections/Footer"
import { Hero } from "./sections/Hero"
import { Nav } from "./sections/Nav"
import { QueEs } from "./sections/QueEs"
import { Tutor } from "./sections/Tutor"

/**
 * Landing comercial de AI-Native: plataforma para enseñar a programar con un
 * tutor de IA que acompaña a cada alumno.
 *
 * Direccion: producto SaaS educativo serio. Base clara neutra + celeste como
 * acento. Lenguaje simple, sin jerga tecnica.
 *
 * Recorrido (scroll vertical):
 *   1. Hero: que hace el producto, en una frase
 *   2. Qué es: explicacion clara + como funciona en 3 pasos
 *   3. Para el alumno: funcionalidades detalladas
 *   4. Para el docente: funcionalidades detalladas
 *   5. Para la institucion: funcionalidades detalladas
 *   6. Beneficios: por que elegirla
 *   7. CTA final: pedir demo / conocer mas
 *   8. Footer: producto + links neutros
 */
export function App() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <QueEs />
        <Alumno />
        <Tutor />
        <Admin />
        <Beneficios />
        <CTAFinal />
      </main>
      <Footer />
    </>
  )
}
