import { createFileRoute } from "@tanstack/react-router"
import { CodificacionEstudioView } from "../views/estudio/CodificacionEstudioView"

// Codificacion (inter-jueces) del estudio de codificacion ciega (change
// cibse-codificacion-ciega, design D13). La codificacion del piloto por materia
// se retiro de la UI; su agregado sigue en /interrater-admin.
export const Route = createFileRoute("/interrater")({
  component: function InterraterRoute() {
    const { getToken } = Route.useRouteContext()
    return <CodificacionEstudioView getToken={getToken} />
  },
})
