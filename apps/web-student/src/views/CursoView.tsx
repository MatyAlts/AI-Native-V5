/**
 * Pagina del curso en el campus del alumno (HU-035): `/curso/$comisionId`.
 *
 * Titulo = nombre de la materia; la bienvenida que escribio el docente
 * (HU-033) en el recuadro aislado; y una tarjeta por unidad, en orden. Una
 * unidad abierta es un link a `/curso/<c>/unidad/<u>` con la cantidad de TPs
 * publicados; una que todavia no abrio no tiene link y dice cuando abre.
 *
 * Los datos salen de endpoints que ya existian (`/materias/mias`, la
 * bienvenida, `/unidades`, `/tareas-practicas` publicadas) con react-query;
 * `["mis-materias"]` es la misma key que la home y la barra, asi que entrar
 * desde la home no repite ese fetch.
 */
import { HtmlAislado, PageContainer } from "@platform/ui"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  type AvailableTarea,
  type TokenGetter,
  type Unidad,
  getBienvenida,
  listMisMaterias,
  listTodasLasTareas,
  listUnidades,
} from "../lib/api"
import { formatearFecha, unidadAbierta } from "../lib/fechaCampus"
import { helpContent } from "../utils/helpContent"

export interface CursoViewProps {
  comisionId: string
  getToken: TokenGetter
  /** "YYYY-MM-DD" en Argentina (`hoyCampus()`); inyectable para las pruebas. */
  hoy: string
}

/** Queries del campus compartidas por la pagina del curso y la de la unidad. */
export function useCampusComision(comisionId: string, getToken: TokenGetter) {
  const materias = useQuery({
    queryKey: ["mis-materias"],
    queryFn: () => listMisMaterias(getToken),
    staleTime: 5 * 60 * 1000,
  })
  const unidades = useQuery({
    queryKey: ["campus", "unidades", comisionId],
    queryFn: () => listUnidades(comisionId, getToken),
  })
  const tareas = useQuery({
    queryKey: ["campus", "tareas", comisionId],
    queryFn: () => listTodasLasTareas(comisionId, getToken),
  })
  const materia = materias.data?.find((m) => m.comision_id === comisionId) ?? null
  const unidadesOrdenadas = [...(unidades.data ?? [])].sort((a, b) => a.orden - b.orden)
  // El backend ya filtra `estado=published`; se vuelve a filtrar aca para que
  // un borrador nunca se cuente ni se muestre aunque el filtro cambie.
  const publicadas = (tareas.data ?? []).filter((t) => (t.estado as string) === "published")
  return { materias, unidades, tareas, materia, unidadesOrdenadas, publicadas }
}

export function tpsDeUnidad(tareas: AvailableTarea[], unidadId: string): AvailableTarea[] {
  return tareas.filter((t) => t.unidad_id === unidadId)
}

export function cantidadTps(n: number): string {
  return n === 1 ? "1 trabajo práctico" : `${n} trabajos prácticos`
}

export function CursoView({ comisionId, getToken, hoy }: CursoViewProps) {
  const { materias, unidades, materia, unidadesOrdenadas, publicadas } = useCampusComision(
    comisionId,
    getToken,
  )
  const bienvenida = useQuery({
    queryKey: ["campus", "bienvenida", comisionId],
    queryFn: () => getBienvenida(comisionId, getToken),
  })

  if (materias.isLoading) return <CampusCargando />
  if (materias.error) return <CampusError texto="No pudimos cargar tus cursos." />
  if (!materia) return <CursoNoEncontrado />

  return (
    <div className="flex-1 overflow-y-auto">
      <PageContainer
        title={materia.nombre}
        eyebrow={
          <span className="normal-case tracking-normal font-normal">
            <Link to="/" className="text-muted hover:text-body no-underline">
              Mis cursos
            </Link>
            <span className="mx-1.5 text-muted-soft">/</span>
            {materia.comision_nombre ?? `Comisión ${materia.comision_codigo}`} ·{" "}
            {materia.periodo_codigo}
          </span>
        }
        helpContent={helpContent.campusCurso}
      >
        <div className="flex flex-wrap gap-2 -mt-4">
          <Link
            to="/mis-notas"
            search={{ comisionId }}
            className="text-sm px-3 py-1.5 rounded-md border border-border bg-surface text-body no-underline hover:bg-accent-brand-soft hover:text-accent-brand-deep hover:border-accent-brand/40 transition-colors"
          >
            Mis notas
          </Link>
          <Link
            to="/progreso"
            search={{ comisionId }}
            className="text-sm px-3 py-1.5 rounded-md border border-border bg-surface text-body no-underline hover:bg-accent-brand-soft hover:text-accent-brand-deep hover:border-accent-brand/40 transition-colors"
          >
            Mi progreso
          </Link>
        </div>

        {bienvenida.data && (
          <section aria-label="Bienvenida">
            <HtmlAislado html={bienvenida.data} titulo="Bienvenida del curso" />
          </section>
        )}

        <section aria-label="Unidades" className="space-y-3">
          <h2 className="text-lg font-semibold text-ink">Unidades</h2>
          {unidades.isLoading && <p className="text-sm text-muted">Cargando unidades...</p>}
          {unidades.error && (
            <p className="text-sm text-danger">No pudimos cargar las unidades del curso.</p>
          )}
          {!unidades.isLoading && !unidades.error && unidadesOrdenadas.length === 0 && (
            <p className="text-sm text-muted">Tu docente todavía no publicó unidades.</p>
          )}
          <div className="grid gap-4 grid-cols-[repeat(auto-fill,minmax(260px,1fr))]">
            {unidadesOrdenadas.map((u) => (
              <TarjetaUnidad
                key={u.id}
                comisionId={comisionId}
                unidad={u}
                abierta={unidadAbierta(u.fecha_apertura, hoy)}
                cantidad={tpsDeUnidad(publicadas, u.id).length}
              />
            ))}
          </div>
        </section>
      </PageContainer>
    </div>
  )
}

const TARJETA =
  "flex flex-col gap-3 rounded-lg border border-border bg-surface p-[18px] shadow-[0_1px_2px_0_rgba(0,0,0,0.04),0_1px_3px_0_rgba(0,0,0,0.05)]"

function TarjetaUnidad({
  comisionId,
  unidad,
  abierta,
  cantidad,
}: {
  comisionId: string
  unidad: Unidad
  abierta: boolean
  cantidad: number
}) {
  if (!abierta) {
    return (
      <div className={`${TARJETA} opacity-85`} data-testid="unidad-cerrada">
        <span className="self-start text-xs font-medium px-2.5 py-0.5 rounded-full bg-surface-alt text-muted">
          Abre el {formatearFecha(unidad.fecha_apertura ?? "")}
        </span>
        <span className="text-base font-semibold leading-snug text-ink">{unidad.nombre}</span>
        {unidad.descripcion && (
          <span className="text-sm text-muted leading-relaxed">{unidad.descripcion}</span>
        )}
      </div>
    )
  }
  return (
    <Link
      to="/curso/$comisionId/unidad/$unidadId"
      params={{ comisionId, unidadId: unidad.id }}
      className={`${TARJETA} hover-lift no-underline text-ink hover:border-accent-brand/60`}
    >
      <span className="text-base font-semibold leading-snug">{unidad.nombre}</span>
      {unidad.descripcion && (
        <span className="text-sm text-muted leading-relaxed">{unidad.descripcion}</span>
      )}
      <span className="mt-auto text-xs text-body">{cantidadTps(cantidad)}</span>
    </Link>
  )
}

export function CampusCargando() {
  return (
    <div className="flex-1 px-6 py-12" aria-label="Cargando">
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="skeleton h-9 w-56 rounded" />
        <div className="skeleton h-32 rounded-lg" />
      </div>
    </div>
  )
}

export function CampusError({ texto }: { texto: string }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <p className="text-sm font-medium text-danger">{texto}</p>
    </div>
  )
}

export function CursoNoEncontrado() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center space-y-3">
        <p className="text-sm font-medium text-body">
          Este curso no está entre tus inscripciones activas.
        </p>
        <Link to="/" className="text-sm underline text-body">
          Volver a mis cursos
        </Link>
      </div>
    </div>
  )
}
