/**
 * Pagina de una unidad en el campus del alumno (HU-035):
 * `/curso/$comisionId/unidad/$unidadId?pestana=introduccion|tps`.
 *
 * Dos pestañas: la introduccion que escribio el docente (en el recuadro
 * aislado) y los trabajos practicos PUBLICADOS de esa unidad, cada uno con su
 * estado (`lib/estadoTp.ts`, sale de la entrega del alumno). Cada TP lleva al
 * flujo de siempre: `/materia/<materia_id>?tareaId=<tp>` abre ese TP directo.
 *
 * Una unidad que todavia no abrio solo dice cuando abre: ni introduccion (el
 * backend tampoco la manda, `unidad_para_lector`) ni links a TPs.
 */
import { HtmlAislado, PageContainer } from "@platform/ui"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { type AvailableTarea, type Entrega, type TokenGetter, listMisEntregas } from "../lib/api"
import { type TipoEstadoTp, estadoTp } from "../lib/estadoTp"
import { formatearFecha, unidadAbierta } from "../lib/fechaCampus"
import { helpContent } from "../utils/helpContent"
import {
  CampusCargando,
  CampusError,
  CursoNoEncontrado,
  tpsDeUnidad,
  useCampusComision,
} from "./CursoView"

export type PestanaUnidad = "introduccion" | "tps"

export interface UnidadViewProps {
  comisionId: string
  unidadId: string
  pestana: PestanaUnidad
  getToken: TokenGetter
  /** "YYYY-MM-DD" en Argentina (`hoyCampus()`); inyectable para las pruebas. */
  hoy: string
}

/** La entrega mas reciente de cada TP (por `updated_at`, si viene). */
export function entregaPorTp(entregas: Entrega[]): Map<string, Entrega> {
  const porTp = new Map<string, Entrega>()
  for (const e of entregas) {
    const previa = porTp.get(e.tarea_practica_id)
    if (!previa || (e.updated_at ?? "") > (previa.updated_at ?? "")) {
      porTp.set(e.tarea_practica_id, e)
    }
  }
  return porTp
}

export function UnidadView({ comisionId, unidadId, pestana, getToken, hoy }: UnidadViewProps) {
  const { materias, unidades, tareas, materia, unidadesOrdenadas, publicadas } = useCampusComision(
    comisionId,
    getToken,
  )
  const entregas = useQuery({
    queryKey: ["campus", "entregas", comisionId],
    queryFn: () => listMisEntregas(comisionId, getToken),
  })

  if (materias.isLoading || unidades.isLoading) return <CampusCargando />
  if (materias.error) return <CampusError texto="No pudimos cargar tus cursos." />
  if (!materia) return <CursoNoEncontrado />
  if (unidades.error) return <CampusError texto="No pudimos cargar la unidad." />

  const unidad = unidadesOrdenadas.find((u) => u.id === unidadId)
  if (!unidad) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-md text-center space-y-3">
          <p className="text-sm font-medium text-body">Esta unidad no existe en tu curso.</p>
          <Link
            to="/curso/$comisionId"
            params={{ comisionId }}
            className="text-sm underline text-body"
          >
            Volver al curso
          </Link>
        </div>
      </div>
    )
  }

  const abierta = unidadAbierta(unidad.fecha_apertura, hoy)
  const tps = tpsDeUnidad(publicadas, unidad.id)
  const porTp = entregaPorTp(entregas.data ?? [])

  return (
    <div className="flex-1 overflow-y-auto">
      <PageContainer
        title={unidad.nombre}
        {...(unidad.descripcion ? { description: unidad.descripcion } : {})}
        eyebrow={
          <span className="normal-case tracking-normal font-normal">
            <Link to="/" className="text-muted hover:text-body no-underline">
              Mis cursos
            </Link>
            <span className="mx-1.5 text-muted-soft">/</span>
            <Link
              to="/curso/$comisionId"
              params={{ comisionId }}
              className="text-muted hover:text-body no-underline"
            >
              {materia.nombre}
            </Link>
          </span>
        }
        helpContent={helpContent.campusUnidad}
      >
        {!abierta ? (
          <div className="rounded-lg border border-border bg-surface p-6 text-sm text-body">
            Esta unidad abre el {formatearFecha(unidad.fecha_apertura ?? "")}
          </div>
        ) : (
          <>
            <div
              role="tablist"
              aria-label="Secciones de la unidad"
              className="flex flex-wrap gap-1 border-b border-border -mt-4"
            >
              <Pestana
                comisionId={comisionId}
                unidadId={unidadId}
                valor="introduccion"
                activa={pestana === "introduccion"}
              >
                Introducción
              </Pestana>
              <Pestana
                comisionId={comisionId}
                unidadId={unidadId}
                valor="tps"
                activa={pestana === "tps"}
              >
                Trabajos prácticos
                <span className="ml-1.5 text-xs text-muted">{tps.length}</span>
              </Pestana>
            </div>

            {pestana === "introduccion" ? (
              <section role="tabpanel" aria-label="Introducción">
                {unidad.introduccion_html ? (
                  <HtmlAislado html={unidad.introduccion_html} titulo="Introducción de la unidad" />
                ) : (
                  <p className="text-sm text-muted">Esta unidad todavía no tiene introducción</p>
                )}
              </section>
            ) : (
              <section role="tabpanel" aria-label="Trabajos prácticos" className="space-y-3">
                {tareas.isLoading && (
                  <p className="text-sm text-muted">Cargando trabajos prácticos...</p>
                )}
                {tareas.error && (
                  <p className="text-sm text-danger">No pudimos cargar los trabajos prácticos.</p>
                )}
                {!tareas.isLoading && !tareas.error && tps.length === 0 && (
                  <p className="text-sm text-muted">
                    Esta unidad todavía no tiene trabajos prácticos publicados.
                  </p>
                )}
                {tps.map((tp) => (
                  <FilaTp
                    key={tp.id}
                    tp={tp}
                    materiaId={materia.materia_id}
                    entrega={porTp.get(tp.id) ?? null}
                  />
                ))}
              </section>
            )}
          </>
        )}
      </PageContainer>
    </div>
  )
}

function Pestana({
  comisionId,
  unidadId,
  valor,
  activa,
  children,
}: {
  comisionId: string
  unidadId: string
  valor: PestanaUnidad
  activa: boolean
  children: ReactNode
}) {
  return (
    <Link
      to="/curso/$comisionId/unidad/$unidadId"
      params={{ comisionId, unidadId }}
      search={{ pestana: valor }}
      replace
      role="tab"
      aria-selected={activa}
      className={`px-3.5 py-2.5 text-sm no-underline -mb-px border-b-2 ${
        activa
          ? "font-semibold text-accent-brand-deep border-accent-brand"
          : "text-body border-transparent hover:text-ink"
      }`}
    >
      {children}
    </Link>
  )
}

const CHIP: Record<TipoEstadoTp, string> = {
  calificado: "bg-success-soft text-success",
  esperando: "bg-accent-brand-soft text-accent-brand-deep",
  en_curso: "bg-warning-soft text-warning",
  pendiente: "bg-surface-alt text-muted",
}

const ZONA_CAMPUS = "America/Argentina/Buenos_Aires"

function cierre(fechaFin: string | null): string | null {
  if (!fechaFin) return null
  const d = new Date(fechaFin)
  if (Number.isNaN(d.getTime())) return null
  // `fecha_fin` es un instante (datetime), no una fecha: aca si corresponde
  // pasarlo a la hora de Argentina.
  return d.toLocaleDateString("es-AR", {
    timeZone: ZONA_CAMPUS,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  })
}

function FilaTp({
  tp,
  materiaId,
  entrega,
}: {
  tp: AvailableTarea
  materiaId: string
  entrega: Entrega | null
}) {
  const estado = estadoTp(entrega)
  const cierra = cierre(tp.fecha_fin)
  return (
    <Link
      to="/materia/$id"
      params={{ id: materiaId }}
      search={{ tareaId: tp.id }}
      className="flex items-center justify-between gap-4 rounded-lg border border-border bg-surface px-4 py-3 no-underline text-ink shadow-[0_1px_2px_0_rgba(0,0,0,0.04),0_1px_3px_0_rgba(0,0,0,0.05)] hover:border-accent-brand/60 transition-colors"
    >
      <span className="flex flex-col gap-0.5 min-w-0">
        <span className="text-sm font-semibold leading-snug">{tp.titulo}</span>
        {cierra && <span className="text-xs text-muted">Cierra el {cierra}</span>}
      </span>
      <span
        className={`shrink-0 text-xs font-medium px-2.5 py-0.5 rounded-full ${CHIP[estado.tipo]}`}
      >
        {estado.etiqueta}
      </span>
    </Link>
  )
}
