/**
 * Pagina del curso en el campus del alumno (HU-035): `/curso/$comisionId`.
 *
 * Sigue el prototipo aprobado (`Aula.dc.html`) y usa todo el ancho: ruta
 * arriba, el nombre de la materia con "Tu avance" (unidades completas) a la
 * derecha, una fila de secciones (Unidades, Mis notas, Mi progreso), la
 * bienvenida que escribio el docente (HU-033) en el recuadro aislado, y una
 * grilla de tarjetas, una por unidad en orden.
 *
 * Debajo, "Otros trabajos practicos": los TPs publicados que no estan en
 * ninguna unidad visible (`unidad_id` vacio, o una unidad borrada: la FK es
 * `ON DELETE SET NULL`). Sin esta seccion no tenian ningun camino: la pagina
 * de la materia redirige al campus y el campus solo lista TPs por unidad.
 *
 * Cada tarjeta: "Unidad N" (por posicion) con su estado a la derecha
 * (Completa / En curso / "Abre el dd/mm/aaaa"), el nombre sin el prefijo
 * "Unidad N · ", el resumen y abajo "N trabajos practicos" con "X de Y
 * entregados" y una barra. Una unidad abierta es un link a
 * `/curso/<c>/unidad/<u>` cuyo nombre accesible es el nombre completo; una que
 * todavia no abrio no tiene link. Sin TPs no hay barra ni "0 de 0".
 *
 * Los datos salen de endpoints que ya existian (`/materias/mias`, la
 * bienvenida, `/unidades`, `/tareas-practicas` publicadas, `/entregas`
 * propias) con react-query; `["mis-materias"]` es la misma key que la home y
 * la barra, asi que entrar desde la home no repite ese fetch.
 */
import { HelpButton, HtmlAislado } from "@platform/ui"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"
import {
  type AvailableTarea,
  type TokenGetter,
  type Unidad,
  getBienvenida,
  listMisEntregas,
  listMisMaterias,
  listTodasLasTareas,
  listUnidades,
} from "../lib/api"
import {
  type EstadoUnidad,
  cantidadEntregados,
  entregaPorTp,
  estadoUnidad,
  tituloSinPrefijo,
} from "../lib/avanceCampus"
import { formatearFecha } from "../lib/fechaCampus"
import { helpContent } from "../utils/helpContent"
import { TarjetaTp } from "./UnidadView"

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
  const entregas = useQuery({
    queryKey: ["campus", "entregas", comisionId],
    queryFn: () => listMisEntregas(comisionId, getToken),
  })
  const materia = materias.data?.find((m) => m.comision_id === comisionId) ?? null
  const unidadesOrdenadas = [...(unidades.data ?? [])].sort((a, b) => a.orden - b.orden)
  // El backend ya filtra `estado=published`; se vuelve a filtrar aca para que
  // un borrador nunca se cuente ni se muestre aunque el filtro cambie.
  const publicadas = (tareas.data ?? []).filter((t) => (t.estado as string) === "published")
  const porTp = entregaPorTp(entregas.data ?? [])
  return { materias, unidades, tareas, entregas, materia, unidadesOrdenadas, publicadas, porTp }
}

export function tpsDeUnidad(tareas: AvailableTarea[], unidadId: string): AvailableTarea[] {
  return tareas.filter((t) => t.unidad_id === unidadId)
}

/**
 * TPs que no cuelgan de ninguna unidad de la lista: sin `unidad_id`, o con el
 * de una unidad que el alumno no recibe (borrada). Sin esto quedan sin acceso.
 */
export function tpsSinUnidad(
  tareas: AvailableTarea[],
  unidades: ReadonlyArray<Pick<Unidad, "id">>,
): AvailableTarea[] {
  const ids = new Set(unidades.map((u) => u.id))
  return tareas.filter((t) => !t.unidad_id || !ids.has(t.unidad_id))
}

export function cantidadTps(n: number): string {
  return n === 1 ? "1 trabajo práctico" : `${n} trabajos prácticos`
}

export function CursoView({ comisionId, getToken, hoy }: CursoViewProps) {
  const { materias, unidades, entregas, materia, unidadesOrdenadas, publicadas, porTp } =
    useCampusComision(comisionId, getToken)
  const bienvenida = useQuery({
    queryKey: ["campus", "bienvenida", comisionId],
    queryFn: () => getBienvenida(comisionId, getToken),
  })

  if (materias.isLoading) return <CampusCargando />
  if (materias.error) return <CampusError texto="No pudimos cargar tus cursos." />
  if (!materia) return <CursoNoEncontrado />

  const tarjetas = unidadesOrdenadas.map((u, i) => {
    const tps = tpsDeUnidad(publicadas, u.id)
    const entregados = cantidadEntregados(tps, porTp)
    return {
      unidad: u,
      numero: i + 1,
      total: tps.length,
      entregados,
      estado: estadoUnidad(u.fecha_apertura, hoy, tps.length, entregados),
    }
  })
  // Solo con las unidades cargadas: mientras cargan, todo TP pareceria suelto.
  const sueltos = unidades.isSuccess ? tpsSinUnidad(publicadas, unidadesOrdenadas) : []
  const completas = tarjetas.filter((t) => t.estado === "completa").length
  const comision = materia.comision_nombre ?? `Comisión ${materia.comision_codigo}`

  return (
    <CampusPagina>
      <header className="flex flex-col gap-2.5 animate-fade-in-down">
        <RutaCampus>
          <Link to="/" className="text-muted hover:text-body no-underline">
            Mis cursos
          </Link>
          <Separador />
          <span>{materia.nombre}</span>
        </RutaCampus>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1 min-w-0">
            <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
              {materia.nombre}
            </h1>
            <p className="text-sm text-muted">
              {comision} · {materia.periodo_codigo}
            </p>
          </div>
          <div className="flex items-end gap-4">
            {/* Sin las entregas no se sabe que unidad esta completa. */}
            {tarjetas.length > 0 && entregas.isSuccess && (
              <div className="flex flex-col gap-1.5 min-w-[220px]">
                <div className="flex justify-between gap-3 text-xs text-body">
                  <span>Tu avance</span>
                  <span>
                    {completas} de {tarjetas.length} unidades
                  </span>
                </div>
                <BarraAvance
                  valor={completas}
                  max={tarjetas.length}
                  etiqueta="Unidades completas"
                  grosor="gruesa"
                />
              </div>
            )}
            <HelpButton title={materia.nombre} content={helpContent.campusCurso} />
          </div>
        </div>
        <nav
          aria-label="Secciones del curso"
          className="flex flex-wrap gap-1 border-b border-border mt-1.5"
        >
          <span className={`${PESTANA} ${PESTANA_ACTIVA}`} aria-current="page">
            Unidades
          </span>
          <Link
            to="/mis-notas"
            search={{ comisionId }}
            className={`${PESTANA} ${PESTANA_INACTIVA}`}
          >
            Mis notas
          </Link>
          <Link to="/progreso" search={{ comisionId }} className={`${PESTANA} ${PESTANA_INACTIVA}`}>
            Mi progreso
          </Link>
        </nav>
      </header>

      {bienvenida.data && (
        <section aria-label="Bienvenida">
          <HtmlAislado html={bienvenida.data} titulo="Bienvenida del curso" />
        </section>
      )}

      <section aria-labelledby="titulo-unidades" className="flex flex-col gap-3">
        <h2 id="titulo-unidades" className="sr-only">
          Unidades
        </h2>
        {unidades.isLoading && <p className="text-sm text-muted">Cargando unidades...</p>}
        {unidades.error && (
          <p className="text-sm text-danger">No pudimos cargar las unidades del curso.</p>
        )}
        {!unidades.isLoading && !unidades.error && tarjetas.length === 0 && (
          <p className="text-sm text-muted">Tu docente todavía no publicó unidades.</p>
        )}
        {tarjetas.length > 0 && (
          <ul className="grid gap-4 grid-cols-[repeat(auto-fill,minmax(260px,1fr))]">
            {tarjetas.map((t) => (
              <li key={t.unidad.id} className="flex">
                <TarjetaUnidad comisionId={comisionId} {...t} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {sueltos.length > 0 && (
        <section aria-labelledby="titulo-otros-tps" className="flex flex-col gap-3">
          <h2 id="titulo-otros-tps" className="text-base font-semibold text-ink">
            Otros trabajos prácticos
          </h2>
          <div className="flex flex-col gap-3">
            {sueltos.map((tp) => (
              <TarjetaTp
                key={tp.id}
                tp={tp}
                materiaId={materia.materia_id}
                entrega={porTp.get(tp.id) ?? null}
                getToken={getToken}
                hoy={hoy}
              />
            ))}
          </div>
        </section>
      )}
    </CampusPagina>
  )
}

// ── Piezas compartidas con la pagina de la unidad ──────────────────────

/** Contenedor de las paginas del campus: todo el ancho, padding del prototipo. */
export function CampusPagina({ children }: { children: ReactNode }) {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="page-enter flex flex-col gap-6 px-4 pt-6 pb-10 sm:px-6 md:px-10 md:pt-8 md:pb-14">
        {children}
      </div>
    </div>
  )
}

export function RutaCampus({ children }: { children: ReactNode }) {
  return (
    <nav aria-label="Ruta" className="text-xs text-muted">
      {children}
    </nav>
  )
}

export function Separador() {
  return (
    <span aria-hidden="true" className="mx-1.5 text-muted-soft">
      /
    </span>
  )
}

export const PESTANA =
  "inline-flex items-center gap-2 px-3.5 py-2.5 text-sm no-underline -mb-px border-b-2"
export const PESTANA_ACTIVA = "font-semibold text-accent-brand-deep border-accent-brand"
export const PESTANA_INACTIVA = "text-body border-transparent hover:text-ink"

export const EYEBROW = "text-[11px] font-semibold uppercase tracking-[0.08em] text-muted"

export const TARJETA =
  "rounded-lg border bg-surface shadow-[0_1px_2px_0_rgba(0,0,0,0.04),0_1px_3px_0_rgba(0,0,0,0.05)]"

/**
 * Barra fina de avance con `role="progressbar"`. El color sale del estado:
 * verde si esta todo, azul de marca si va por la mitad, gris si no empezo.
 */
export function BarraAvance({
  valor,
  max,
  etiqueta,
  grosor = "fina",
}: {
  valor: number
  max: number
  etiqueta: string
  grosor?: "fina" | "gruesa"
}) {
  const pct = max > 0 ? Math.min(100, Math.round((valor / max) * 100)) : 0
  const color = pct >= 100 ? "bg-success" : pct > 0 ? "bg-accent-brand" : "bg-border"
  const alto = grosor === "gruesa" ? "h-1.5" : "h-1"
  return (
    // biome-ignore lint/a11y/useFocusableInteractive: una barra de avance es de solo lectura; ARIA no le pide foco.
    <div
      role="progressbar"
      aria-label={etiqueta}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={valor}
      className={`${alto} w-full rounded-full bg-border-soft overflow-hidden`}
    >
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

// ── Tarjeta de unidad ──────────────────────────────────────────────────

const CHIP_UNIDAD: Record<EstadoUnidad, string> = {
  completa: "bg-success-soft text-success",
  en_curso: "bg-warning-soft text-warning",
  proxima: "bg-surface-alt text-muted",
}

function TarjetaUnidad({
  comisionId,
  unidad,
  numero,
  total,
  entregados,
  estado,
}: {
  comisionId: string
  unidad: Unidad
  numero: number
  total: number
  entregados: number
  estado: EstadoUnidad
}) {
  const proxima = estado === "proxima"
  const etiqueta = proxima
    ? `Abre el ${formatearFecha(unidad.fecha_apertura ?? "")}`
    : estado === "completa"
      ? "Completa"
      : "En curso"

  const titulo = tituloSinPrefijo(unidad.nombre)
  // Si se le saco el prefijo, lo visual ("Unidad N" + titulo) se oculta al
  // lector de pantalla y se le da el nombre completo una sola vez.
  const partido = titulo !== unidad.nombre
  const contenido = (
    <>
      {partido && <span className="sr-only">{unidad.nombre}</span>}
      <div className="flex items-center justify-between gap-2">
        <span className={EYEBROW} aria-hidden={partido || undefined}>
          Unidad {numero}
        </span>
        <span
          className={`shrink-0 text-xs font-medium px-2.5 py-0.5 rounded-full ${CHIP_UNIDAD[estado]}`}
        >
          {etiqueta}
        </span>
      </div>
      <span className="text-base font-semibold leading-snug" aria-hidden={partido || undefined}>
        {titulo}
      </span>
      {unidad.descripcion && (
        <span className="text-[13px] text-muted leading-relaxed">{unidad.descripcion}</span>
      )}
      <div className="mt-auto flex flex-col gap-1.5 pt-1">
        <div className="flex justify-between gap-2 text-xs text-body">
          <span>{cantidadTps(total)}</span>
          {!proxima && total > 0 && <span>{`${entregados} de ${total} entregados`}</span>}
        </div>
        {!proxima && total > 0 && (
          <BarraAvance valor={entregados} max={total} etiqueta="Trabajos entregados" />
        )}
      </div>
    </>
  )

  const base = `${TARJETA} flex flex-1 flex-col gap-3 p-[18px]`
  if (proxima) {
    return (
      <div className={`${base} border-border opacity-85`} data-testid="unidad-cerrada">
        {contenido}
      </div>
    )
  }
  return (
    <Link
      to="/curso/$comisionId/unidad/$unidadId"
      params={{ comisionId, unidadId: unidad.id }}
      aria-label={unidad.nombre}
      data-tarjeta-unidad
      className={`${base} hover-lift no-underline text-ink hover:border-accent-brand/60 ${
        estado === "en_curso" ? "border-accent-brand/40" : "border-border"
      }`}
    >
      {contenido}
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
