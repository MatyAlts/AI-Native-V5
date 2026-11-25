/**
 * Barra izquierda del campus del alumno (HU-035).
 *
 * Solo "Mis cursos" (la home) y un link por curso del alumno, a
 * `/curso/<comision_id>`. El curso activo lleva `aria-current="page"` aunque el
 * alumno este dentro de una unidad (`/curso/<c>/unidad/<u>`): lo decide
 * `comisionActiva`, que `CampusShell` saca del path.
 *
 * No aparece en el episodio (`mostrarBarraCursos`): el episodio sigue siendo
 * pantalla completa como antes. En pantallas chicas la barra se apila arriba
 * como una fila con scroll horizontal.
 */
import { Link } from "@tanstack/react-router"
import type { MateriaInscripta } from "../lib/api"

/** false en `/episodio/...` (pantalla completa); true en el resto. */
export function mostrarBarraCursos(pathname: string): boolean {
  return !(pathname === "/episodio" || pathname.startsWith("/episodio/"))
}

/** comision_id del path `/curso/<id>` (o `/curso/<id>/unidad/...`), o null. */
export function comisionDelPath(pathname: string): string | null {
  const m = /^\/curso\/([^/]+)/.exec(pathname)
  return m?.[1] ? decodeURIComponent(m[1]) : null
}

type CursoBarra = Pick<MateriaInscripta, "comision_id" | "nombre" | "materia_id">

export interface BarraCursosProps {
  cursos: CursoBarra[]
  comisionActiva: string | null
}

const BASE_LINK =
  "flex items-center shrink-0 rounded-md no-underline transition-colors border-l-2 whitespace-nowrap md:whitespace-normal"

export function BarraCursos({ cursos, comisionActiva }: BarraCursosProps) {
  return (
    <nav
      aria-label="Mis cursos"
      data-testid="barra-cursos"
      className="shrink-0 bg-canvas border-b border-border md:border-b-0 md:border-r md:w-60 px-3 py-2 md:gap-1.5 md:px-4 md:py-6 flex md:flex-col gap-1 overflow-x-auto md:overflow-y-auto"
    >
      <Link
        to="/"
        activeOptions={{ exact: true }}
        className={`${BASE_LINK} text-sm px-2.5 py-2 md:py-2.5 border-transparent text-body hover:bg-sidebar-bg-edge`}
      >
        Mis cursos
      </Link>
      {cursos.map((c) => {
        const activo = c.comision_id === comisionActiva
        return (
          <Link
            key={c.comision_id}
            to="/curso/$comisionId"
            params={{ comisionId: c.comision_id }}
            activeOptions={{ exact: true }}
            aria-current={activo ? "page" : undefined}
            className={`${BASE_LINK} px-2.5 py-2 text-[13px] md:pl-[22px] ${
              activo
                ? "bg-accent-brand-soft text-accent-brand-deep font-medium border-accent-brand"
                : "border-transparent text-body hover:bg-sidebar-bg-edge"
            }`}
          >
            {c.nombre}
          </Link>
        )
      })}
    </nav>
  )
}
