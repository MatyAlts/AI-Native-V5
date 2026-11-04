import { createFileRoute } from "@tanstack/react-router"
import { EntrenamientoEstudioView } from "../views/estudio/EntrenamientoEstudioView"

// Entrenamiento-Recalibracion del estudio de codificacion ciega (change
// cibse-codificacion-ciega, design D13): codebook vigente, ejemplos y practica
// con anclas persistidas. El entrenamiento del piloto se retiro.
export const Route = createFileRoute("/entrenamiento-recalibracion")({
  component: function EntrenamientoRecalibracionRoute() {
    const { getToken } = Route.useRouteContext()
    return <EntrenamientoEstudioView getToken={getToken} />
  },
})
