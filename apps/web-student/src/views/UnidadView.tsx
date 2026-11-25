/**
 * Pagina de una unidad en el campus del alumno (HU-035):
 * `/curso/$comisionId/unidad/$unidadId?pestana=introduccion|tps`.
 *
 * Sigue el prototipo aprobado (`Unidad.dc.html`, `UnidadTps.dc.html`) y usa
 * todo el ancho: ruta, "Unidad N" (por posicion) arriba del nombre sin el
 * prefijo "Unidad N · ", links a la unidad anterior y siguiente, y dos
 * pestañas: la introduccion que escribio el docente (en el recuadro aislado)
 * y los trabajos practicos PUBLICADOS de esa unidad, con su cantidad.
 *
 * Cada TP es una tarjeta: titulo, cuando se entrego o cuando vence, "Ejercicios
 * X de Y" con una barra (Y sale de `GET /tareas-practicas/<id>/ejercicios`, una
 * query por TP; X de los `ejercicio_estados` completados de su entrega; sin
 * ejercicios no hay barra) y el estado (`lib/estadoTp.ts`). Cada TP lleva al
 * flujo de siempre: `/materia/<materia_id>?tareaId=<tp>` abre ese TP directo.
 *
 * Una unidad que todavia no abrio solo dice cuando abre: ni introduccion (el
 * backend tampoco la manda, `unidad_para_lector`) ni links a TPs.
 */
import { HelpButton, HtmlAislado } from "@platform/ui"
import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { type AvailableTarea, type Entrega, type TokenGetter, listEjerciciosTp } from "../lib/api"
import { estaEntregada, tituloSinPrefijo } from "../lib/avanceCampus"
import { type TipoEstadoTp, estadoTp } from "../lib/estadoTp"
import { diaDeInstante, formatearFecha, unidadAbierta } from "../lib/fechaCampus"
import { helpContent } from "../utils/helpContent"
import {
  BarraAvance,
  CampusCargando,
  CampusError,
  CampusPagina,
  CursoNoEncontrado,
  EYEBROW,
  PESTANA,
  PESTANA_ACTIVA,
  PESTANA_INACTIVA,
  RutaCampus,
  Separador,
  TARJETA,
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

export function UnidadView({ comisionId, unidadId, pestana, getToken, hoy }: UnidadViewProps) {
  const { materias, unidades, tareas, materia, unidadesOrdenadas, publicadas, porTp } =
    useCampusComision(comisionId, getToken)

  if (materias.isLoading || unidades.isLoading) return <CampusCargando />
  if (materias.error) return <CampusError texto="No pudimos cargar tus cursos." />
  if (!materia) return <CursoNoEncontrado />
  if (unidades.error) return <CampusError texto="No pudimos cargar la unidad." />

  const indice = unidadesOrdenadas.findIndex((u) => u.id === unidadId)
  const unidad = unidadesOrdenadas[indice]
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
  const titulo = tituloSinPrefijo(unidad.nombre)
  const anterior = unidadesOrdenadas[indice - 1]
  const siguiente = unidadesOrdenadas[indice + 1]

  return (
    <CampusPagina>
      <header className="flex flex-col gap-2.5 animate-fade-in-down">
        <RutaCampus>
          <Link to="/" className="text-muted hover:text-body no-underline">
            Mis cursos
          </Link>
          <Separador />
          <Link
            to="/curso/$comisionId"
            params={{ comisionId }}
            className="text-muted hover:text-body no-underline"
          >
            {materia.nombre}
          </Link>
        </RutaCampus>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1 min-w-0">
            <span className={EYEBROW}>Unidad {indice + 1}</span>
            <h1 className="text-3xl font-semibold tracking-tight text-ink leading-tight">
              {titulo}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            {anterior && (
              <VecinaUnidad comisionId={comisionId} unidadId={anterior.id} nombre={anterior.nombre}>
                ← Anterior
              </VecinaUnidad>
            )}
            {siguiente && (
              <VecinaUnidad
                comisionId={comisionId}
                unidadId={siguiente.id}
                nombre={siguiente.nombre}
              >
                Siguiente →
              </VecinaUnidad>
            )}
            <HelpButton title={titulo} content={helpContent.campusUnidad} />
          </div>
        </div>
        {unidad.descripcion && (
          <p className="text-sm text-muted leading-relaxed max-w-2xl">{unidad.descripcion}</p>
        )}
        {abierta && (
          <div
            role="tablist"
            aria-label="Secciones de la unidad"
            className="flex flex-wrap gap-1 border-b border-border mt-1"
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
              <span className="text-[11px] font-semibold px-[7px] py-0.5 rounded-full bg-accent-brand-soft/50 text-accent-brand-deep">
                {tps.length}
              </span>
            </Pestana>
          </div>
        )}
      </header>

      {!abierta ? (
        <div className={`${TARJETA} border-border p-6 text-sm text-body`}>
          Esta unidad abre el {formatearFecha(unidad.fecha_apertura ?? "")}
        </div>
      ) : pestana === "introduccion" ? (
        <section role="tabpanel" aria-label="Introducción">
          {unidad.introduccion_html ? (
            <HtmlAislado html={unidad.introduccion_html} titulo="Introducción de la unidad" />
          ) : (
            <p className="text-sm text-muted">Esta unidad todavía no tiene introducción</p>
          )}
        </section>
      ) : (
        <section role="tabpanel" aria-label="Trabajos prácticos" className="flex flex-col gap-3">
          {tareas.isLoading && <p className="text-sm text-muted">Cargando trabajos prácticos...</p>}
          {tareas.error && (
            <p className="text-sm text-danger">No pudimos cargar los trabajos prácticos.</p>
          )}
          {!tareas.isLoading && !tareas.error && tps.length === 0 && (
            <p className="text-sm text-muted">
              Esta unidad todavía no tiene trabajos prácticos publicados.
            </p>
          )}
          {tps.map((tp) => (
            <TarjetaTp
              key={tp.id}
              tp={tp}
              materiaId={materia.materia_id}
              entrega={porTp.get(tp.id) ?? null}
              getToken={getToken}
              hoy={hoy}
            />
          ))}
        </section>
      )}
    </CampusPagina>
  )
}

function VecinaUnidad({
  comisionId,
  unidadId,
  nombre,
  children,
}: {
  comisionId: string
  unidadId: string
  nombre: string
  children: ReactNode
}) {
  return (
    <Link
      to="/curso/$comisionId/unidad/$unidadId"
      params={{ comisionId, unidadId }}
      search={{ pestana: "introduccion" }}
      title={nombre}
      className="px-3 py-2 rounded-md bg-surface-alt text-[13px] text-ink no-underline hover:bg-sidebar-bg-edge transition-colors"
    >
      {children}
    </Link>
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
      className={`${PESTANA} ${activa ? PESTANA_ACTIVA : PESTANA_INACTIVA}`}
    >
      {children}
    </Link>
  )
}

const CHIP: Record<TipoEstadoTp, string> = {
  calificado: "bg-success-soft text-success",
  esperando: "bg-accent-brand-soft/50 text-accent-brand-deep",
  en_curso: "bg-warning-soft text-warning",
  pendiente: "bg-surface-alt text-muted",
}

/**
 * La linea de abajo del titulo: cuando se entrego (si ya se mando) o cuando
 * vence / cerro (`fecha_fin`). Las dos son instantes: se pasan al dia de
 * Argentina antes de comparar o mostrar.
 */
function detalleTp(tp: AvailableTarea, entrega: Entrega | null, hoy: string): string | null {
  if (estaEntregada(entrega)) {
    const dia = diaDeInstante(entrega?.submitted_at)
    return dia ? `Entregado el ${formatearFecha(dia)}` : null
  }
  const fin = diaDeInstante(tp.fecha_fin)
  if (!fin) return null
  return fin >= hoy ? `Vence el ${formatearFecha(fin)}` : `Cerró el ${formatearFecha(fin)}`
}

function TarjetaTp({
  tp,
  materiaId,
  entrega,
  getToken,
  hoy,
}: {
  tp: AvailableTarea
  materiaId: string
  entrega: Entrega | null
  getToken: TokenGetter
  hoy: string
}) {
  const ejercicios = useQuery({
    queryKey: ["campus", "ejercicios-tp", tp.id],
    queryFn: () => listEjerciciosTp(tp.id, getToken),
    staleTime: 5 * 60 * 1000,
  })
  const estado = estadoTp(entrega)
  const detalle = detalleTp(tp, entrega, hoy)
  const total = Array.isArray(ejercicios.data) ? ejercicios.data.length : 0
  const hechos = Math.min(
    total,
    (entrega?.ejercicio_estados ?? []).filter((e) => e.completado).length,
  )
  return (
    <Link
      to="/materia/$id"
      params={{ id: materiaId }}
      search={{ tareaId: tp.id }}
      className={`${TARJETA} flex flex-wrap items-center gap-4 px-5 py-[18px] no-underline text-ink hover:border-accent-brand/60 transition-colors ${
        estado.tipo === "en_curso" ? "border-accent-brand/40" : "border-border"
      }`}
    >
      <span className="flex flex-col gap-1 flex-[1_1_320px] min-w-0">
        <span className="text-base font-semibold leading-snug">{tp.titulo}</span>
        {detalle && <span className="text-[13px] text-muted">{detalle}</span>}
      </span>
      {total > 0 && (
        <span className="flex flex-col gap-1.5 flex-[0_1_200px] min-w-[140px]">
          <span className="text-xs text-body">{`Ejercicios ${hechos} de ${total}`}</span>
          <BarraAvance valor={hechos} max={total} etiqueta="Ejercicios completados" />
        </span>
      )}
      <span
        className={`shrink-0 whitespace-nowrap text-[13px] font-medium px-3 py-1 rounded-full ${CHIP[estado.tipo]}`}
      >
        {estado.etiqueta}
      </span>
    </Link>
  )
}
