/**
 * HU-035: columna izquierda "Mis cursos" + contenido. Solo se monta con el
 * alumno ya inscripto (rama "enrolled" del layout raiz). En el episodio no hay
 * barra (`mostrarBarraCursos`): queda pantalla completa como antes. Los cursos
 * salen de `["mis-materias"]`, la misma query que la home, y el curso activo
 * del path `/curso/<id>`.
 *
 * El `<Outlet/>` va SIEMPRE en la misma posicion del arbol; segun la ruta solo
 * se muestra u oculta `BarraCursos`. Si el Outlet cambiara de lugar (por
 * ejemplo, suelto en el episodio y envuelto en el resto), React volveria a
 * montar la pagina que se esta yendo: la del episodio reescribia
 * `active-episode-id` y la home redirigia de nuevo al episodio, en bucle.
 * Lo fija `tests/Hu035bSalidaEpisodio.test.tsx`.
 *
 * Sin barra, el contenedor queda con un solo hijo `flex-1 min-h-0 flex-col`,
 * asi que el episodio conserva la altura fija y el scroll por panel.
 */
import { useQuery } from "@tanstack/react-query"
import { Outlet, useRouterState } from "@tanstack/react-router"
import { listMisMaterias } from "../lib/api"
import { BarraCursos, comisionDelPath, mostrarBarraCursos } from "./BarraCursos"

export function CampusShell() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const conBarra = mostrarBarraCursos(pathname)
  const { data: cursos } = useQuery({
    queryKey: ["mis-materias"],
    queryFn: () => listMisMaterias(),
    staleTime: 5 * 60 * 1000,
    enabled: conBarra,
  })
  return (
    <div className="flex-1 min-h-0 flex flex-col md:flex-row">
      {conBarra ? (
        <BarraCursos cursos={cursos ?? []} comisionActiva={comisionDelPath(pathname)} />
      ) : null}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">
        <Outlet />
      </div>
    </div>
  )
}
