import { BookOpen, Code2, LineChart } from "lucide-react"
import { RoleSection } from "../components/RoleSection"

/** Apartado detallado para el alumno, en lenguaje simple. */
export function Alumno() {
  return (
    <RoleSection
      id="alumno"
      index="01"
      who="Para el alumno"
      title="Aprendés con guía, no con respuestas hechas."
      intro="El tutor de IA te acompaña mientras resolvés, te ayuda a pensar y te muestra en qué apoyás cada explicación. Todo pasa en el navegador y queda guardado de forma ordenada."
      clusters={[
        {
          icon: BookOpen,
          heading: "Una guía que te hace pensar",
          items: [
            "Un tutor de IA que te guía con preguntas, en vez de darte la solución hecha.",
            "Se apoya en el material de tu materia para responder.",
            "Te muestra de dónde sale cada explicación que te da.",
          ],
        },
        {
          icon: Code2,
          heading: "Programás sin instalar nada",
          items: [
            "Editor de código en el navegador, listo para usar.",
            "Corrés y probás tu código al instante.",
            "Ves qué pruebas pasan y cuáles todavía no.",
          ],
        },
        {
          icon: LineChart,
          heading: "Seguís tu propio camino",
          items: [
            "Trabajás sobre las tareas prácticas reales de tu cursada.",
            "Seguís tu progreso a lo largo de la materia.",
            "Todo tu trabajo queda guardado de forma ordenada y segura.",
          ],
        },
      ]}
    />
  )
}
