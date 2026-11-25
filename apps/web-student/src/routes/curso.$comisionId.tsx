/**
 * Ruta /curso/$comisionId del web-student (HU-035): la pagina del curso del
 * campus (bienvenida + tarjetas de unidades). Ver `views/CursoView.tsx`.
 *
 * Es la ruta padre de `/curso/$comisionId/unidad/$unidadId` (nesting por
 * punto en el nombre del archivo): cuando la unidad esta activa, esta ruta
 * solo deja pasar el `<Outlet />` en vez de pintar el curso.
 */
import { Outlet, createFileRoute, useChildMatches } from "@tanstack/react-router"
import { hoyCampus } from "../lib/fechaCampus"
import { CursoView } from "../views/CursoView"

export const Route = createFileRoute("/curso/$comisionId")({
  component: CursoPage,
})

function CursoPage() {
  const { comisionId } = Route.useParams()
  const { getToken } = Route.useRouteContext()
  const hijos = useChildMatches()
  if (hijos.length > 0) return <Outlet />
  return (
    <CursoView key={comisionId} comisionId={comisionId} getToken={getToken} hoy={hoyCampus()} />
  )
}
