import { ClipboardCheck, PencilRuler, Users } from "lucide-react"
import { RoleSection } from "../components/RoleSection"

/** Apartado detallado para el docente (tutor), en lenguaje simple. */
export function Tutor() {
  return (
    <RoleSection
      id="docente"
      index="02"
      who="Para el docente"
      title="Armás, corregís y acompañás desde un solo lugar."
      intro="Preparás las actividades de tu materia, corregís con la rúbrica y el código del alumno a la vista, y ves cómo avanza toda la comisión para saber a quién darle una mano."
      reversed
      tinted
      clusters={[
        {
          icon: PencilRuler,
          heading: "Armás las actividades",
          items: [
            "Creás ejercicios y trabajos prácticos, o los generás con ayuda de IA.",
            "Armás la rúbrica de cada ejercicio.",
            "Subís los materiales de la materia y el tutor los usa.",
            "Probás el ejercicio y lo ves como lo vería el alumno.",
          ],
        },
        {
          icon: ClipboardCheck,
          heading: "Corregís con criterio",
          items: [
            "Corregís criterio por criterio con el código del alumno al lado.",
            "Corregís en lote, una entrega atrás de otra.",
            "Comparás distintos intentos de un mismo alumno.",
            "Exportás la actividad cuando la necesitás.",
          ],
        },
        {
          icon: Users,
          heading: "Acompañás a tu clase",
          items: [
            "Ves el progreso de toda la comisión y de cada alumno.",
            "Recibís alertas de quién necesita acompañamiento.",
            "Sabés cómo trabajó y progresó cada uno, con un registro confiable.",
          ],
        },
      ]}
    />
  )
}
