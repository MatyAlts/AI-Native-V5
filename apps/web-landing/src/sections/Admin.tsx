import { Building2, KeyRound, ShieldCheck } from "lucide-react"
import { RoleSection } from "../components/RoleSection"

/** Apartado detallado para el administrador (institucion), en lenguaje simple. */
export function Admin() {
  return (
    <RoleSection
      id="institucion"
      index="03"
      who="Para la institución"
      title="Toda la actividad ordenada y segura."
      intro="Gestionás materias, comisiones y personas desde un panel, con los datos de cada institución separados y protegidos, y un registro confiable de todo lo que pasa en la plataforma."
      clusters={[
        {
          icon: Building2,
          heading: "Ordenás la institución",
          items: [
            "Gestionás materias, comisiones, docentes y alumnos.",
            "Importás inscripciones en masa desde una planilla.",
            "Sumás varias instituciones, cada una con sus datos separados.",
          ],
        },
        {
          icon: ShieldCheck,
          heading: "Datos protegidos y en su lugar",
          items: [
            "Control de accesos según el rol de cada persona.",
            "Privacidad de los datos de alumnos y docentes.",
            "Registro confiable de toda la actividad.",
          ],
        },
        {
          icon: KeyRound,
          heading: "Controlás la IA",
          items: [
            "Configurás las claves de IA por materia.",
            "Elegís tu proveedor y mantenés el control del costo.",
          ],
        },
      ]}
    />
  )
}
