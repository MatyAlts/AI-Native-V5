/**
 * Pagina "Mis notas" del web-student.
 *
 * Change `alumno-ve-su-nota-sin-depender-del-listado`: un docente archiva un
 * TP al cerrar el cuatrimestre. El alumno deja de verlo en `TareaSelector`
 * (que solo itera TPs `published`), y con eso pierde el acceso a su propia
 * nota y a la correccion. El dato estaba (el endpoint de calificacion no
 * mira el estado de la TP) y el permiso estaba — lo que faltaba era la
 * puerta. Esta pantalla es esa puerta: lista las entregas de la comision
 * directamente, sin pasar por la TP.
 *
 * Shape confirmado (ver proposal.md): lista en DOS grupos ("con nota" /
 * "sin corregir todavia"), NO grilla de cards (anti-referencia 3 de
 * PRODUCT.md), NO tabs (anti-referencia 1), nota tabular a la derecha — NO
 * el template de numero grande con label chico (baneado explicitamente).
 *
 * Es por comision, no global: si el alumno cursa dos materias son dos
 * "vistas" (un picker, igual que MiProgresoPage) — `listMisEntregas` toma
 * `comision_id`.
 *
 * El limite de 50 de `listMisEntregas` es real: si se llega, se avisa en vez
 * de truncar en silencio (principio 5 de PRODUCT.md).
 */
import { HelpButton } from "@platform/ui"
import { useNavigate } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { GradeDetailView } from "../components/GradeDetailView"
import { type Entrega, type MateriaInscripta, listMisEntregas, listMisMaterias } from "../lib/api"
import { helpContent } from "../utils/helpContent"

const LIMITE_ENTREGAS = 50

// ─── Agrupamiento (puro, testeado directo) ────────────────────────────────

/**
 * Separa las entregas en los dos grupos del shape: `conNota` (graded /
 * returned — tienen calificacion) y `sinCorregir` (submitted — entregadas,
 * esperando correccion). Los `draft` (nunca entregados) no entran a NINGUNO
 * de los dos: no hay nada que mostrar todavia, y mostrarlos en "sin
 * corregir" mentiria ("el docente no la corrigio" implica que SI se
 * entrego). `TareaSelector` sigue siendo la puerta para continuar un draft.
 *
 * `nota_final` ya viene resuelta en la entrega (mismo batch que
 * `tarea_codigo`/`tarea_titulo`, ver `evaluation-service::_notas_metadata`)
 * — esta funcion NO pide nada, sólo agrupa y ordena lo que ya llegó.
 *
 * Ordena ambos grupos por `submitted_at` descendente — la entrega mas
 * reciente arriba, mismo criterio en los dos grupos.
 */
export function agruparEntregas(entregas: Entrega[]): {
  conNota: Entrega[]
  sinCorregir: Entrega[]
} {
  const porFechaDesc = (a: Entrega, b: Entrega) => {
    const ta = a.submitted_at ? new Date(a.submitted_at).getTime() : 0
    const tb = b.submitted_at ? new Date(b.submitted_at).getTime() : 0
    return tb - ta
  }

  const conNota = entregas
    .filter((e) => e.estado === "graded" || e.estado === "returned")
    .sort(porFechaDesc)

  const sinCorregir = entregas.filter((e) => e.estado === "submitted").sort(porFechaDesc)

  return { conNota, sinCorregir }
}

// ─── Lista (presentacional, pura — sin fetch, sin router) ─────────────────
//
// Esta función NUNCA pide calificaciones: la nota ya viene en cada
// `Entrega` (ver `agruparEntregas`). La versión anterior pedía
// `getCalificacion` una vez por fila en paralelo — hasta 50 requests por
// carga de pantalla, un costo real en las netbooks que varios alumnos
// reportaron. No reintroducir ese fetch acá.

export interface MisNotasListProps {
  conNota: Entrega[]
  sinCorregir: Entrega[]
  limitReached: boolean
  onSelect: (entrega: Entrega) => void
}

export function MisNotasList({ conNota, sinCorregir, limitReached, onSelect }: MisNotasListProps) {
  return (
    <div className="space-y-8">
      {limitReached && (
        <output
          data-testid="mis-notas-limite"
          className="block rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-xs text-warning/90"
        >
          Estamos mostrando las primeras {LIMITE_ENTREGAS} entregas. Si entregaste mas, puede faltar
          alguna aca — consulta con tu docente.
        </output>
      )}

      {conNota.length > 0 && (
        <section aria-labelledby="mis-notas-con-nota-title">
          <h2
            id="mis-notas-con-nota-title"
            className="text-[11px] font-mono uppercase tracking-[0.12em] text-muted mb-2"
          >
            Con nota
          </h2>
          <ul className="divide-y divide-border rounded-xl border border-border bg-surface overflow-hidden">
            {conNota.map((entrega) => (
              <FilaItem key={entrega.id} entrega={entrega} onSelect={onSelect} />
            ))}
          </ul>
        </section>
      )}

      {sinCorregir.length > 0 && (
        <section aria-labelledby="mis-notas-sin-corregir-title">
          <h2
            id="mis-notas-sin-corregir-title"
            className="text-[11px] font-mono uppercase tracking-[0.12em] text-muted mb-2"
          >
            Sin corregir todavia
          </h2>
          <ul className="divide-y divide-border rounded-xl border border-border bg-surface overflow-hidden">
            {sinCorregir.map((entrega) => (
              <FilaItem key={entrega.id} entrega={entrega} onSelect={onSelect} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function FilaItem({
  entrega,
  onSelect,
}: {
  entrega: Entrega
  onSelect: (entrega: Entrega) => void
}) {
  const tareaLabel = entrega.tarea_codigo ?? "TP"
  const tituloLabel = entrega.tarea_titulo ?? "(sin titulo)"
  const entregado = entrega.submitted_at ? formatDateShort(entrega.submitted_at) : null
  const corregido = entrega.graded_at ? formatDateShort(entrega.graded_at) : null
  const nota = entrega.nota_final ?? null

  return (
    <li>
      <button
        type="button"
        data-testid="mis-notas-row"
        onClick={() => onSelect(entrega)}
        className="press-shrink w-full flex items-center justify-between gap-4 px-4 py-3 text-left hover:bg-surface-alt focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand focus-visible:outline-offset-[-2px] transition-colors"
      >
        <div className="min-w-0">
          <p className="text-xs font-mono uppercase tracking-wider text-muted">
            {tareaLabel} <span className="text-muted-soft">·</span> {tituloLabel}
          </p>
          <p className="text-xs text-muted-soft mt-0.5">
            {entregado && <>entregado {entregado}</>}
            {corregido && <> · corregido {corregido}</>}
            {nota === null && " · el docente no la corrigio todavia"}
          </p>
        </div>
        <div className="shrink-0 text-right">
          {nota !== null ? (
            <p
              data-testid="mis-notas-nota"
              className="font-mono text-lg font-semibold tabular-nums text-ink"
            >
              {nota.toFixed(2)}
            </p>
          ) : (
            <p data-testid="mis-notas-nota-pendiente" className="text-sm text-muted-soft">
              <span aria-hidden="true">—</span>
              <span className="sr-only">Sin calificar todavia</span>
            </p>
          )}
        </div>
      </button>
    </li>
  )
}

// ─── Estados auxiliares ───────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-3" data-testid="mis-notas-loading">
      {[0, 1, 2].map((i) => (
        <div key={i} className="skeleton h-14 rounded-lg" />
      ))}
    </div>
  )
}

function ErrorPanel({ error }: { error: string }) {
  return (
    <div
      role="alert"
      data-testid="mis-notas-error"
      className="rounded-xl border border-danger/30 bg-danger-soft p-6"
    >
      <p className="text-sm font-semibold text-danger mb-2">No pudimos cargar tus notas.</p>
      <p className="text-xs font-mono text-danger/80 break-all">{error}</p>
    </div>
  )
}

function EmptyState() {
  return (
    <div
      data-testid="mis-notas-empty"
      className="rounded-xl border border-border bg-surface p-8 text-center"
    >
      <p className="text-base font-medium text-ink mb-2">Todavia no entregaste nada</p>
      <p className="text-sm text-muted max-w-md mx-auto leading-relaxed">
        Cuando entregues un trabajo practico vas a poder ver aca su nota y la correccion del
        docente, aunque el TP se archive despues.
      </p>
    </div>
  )
}

// ─── Orquestador ───────────────────────────────────────────────────────────

export function MisNotasPage() {
  const navigate = useNavigate()

  const [materias, setMaterias] = useState<MateriaInscripta[] | null>(null)
  const [materiasError, setMateriasError] = useState<string | null>(null)
  const [selectedComisionId, setSelectedComisionId] = useState<string | null>(null)

  const [entregas, setEntregas] = useState<Entrega[] | null>(null)
  const [loadingEntregas, setLoadingEntregas] = useState(false)
  const [entregasError, setEntregasError] = useState<string | null>(null)

  const [selected, setSelected] = useState<Entrega | null>(null)

  useEffect(() => {
    let cancelled = false
    listMisMaterias()
      .then((data) => {
        if (!cancelled) setMaterias(data)
      })
      .catch((e) => {
        if (!cancelled) setMateriasError(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [])

  const comisionId = selectedComisionId ?? materias?.[0]?.comision_id ?? null

  // `listMisEntregas` ya trae `nota_final` resuelta por fila (mismo batch
  // que `tarea_codigo`/`tarea_titulo`, ver `evaluation-service::
  // _notas_metadata`) — no hace falta un segundo fetch de calificaciones acá.
  useEffect(() => {
    if (!comisionId) return
    let cancelled = false
    setLoadingEntregas(true)
    setEntregasError(null)

    listMisEntregas(comisionId)
      .then((lista) => {
        if (!cancelled) setEntregas(lista)
      })
      .catch((e) => {
        if (!cancelled) setEntregasError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoadingEntregas(false)
      })
    return () => {
      cancelled = true
    }
  }, [comisionId])

  if (selected) {
    return <GradeDetailView entrega={selected} onBack={() => setSelected(null)} />
  }

  // BUG reportado por QA: `materias === null` solo no distingue "todavia no
  // resolvio" de "rechazo y nunca va a resolver" — el `.catch` de abajo
  // setea `materiasError` pero nunca `materias`, asi que sin el chequeo del
  // error acá esto quedaba `true` para siempre (skeleton eterno, el
  // `ErrorPanel` de mas abajo —gateado por `!loading && error`— nunca se
  // montaba). La propiedad que esto tiene que cumplir: si hay un error, no
  // se sigue cargando. `loadingEntregas` no tiene este bug porque se resetea
  // en un `.finally()` que corre siempre, haya o no error.
  const loadingMaterias = materias === null && materiasError === null
  const loading = loadingMaterias || (!!comisionId && loadingEntregas && entregas === null)
  const error = materiasError ?? entregasError
  const { conNota, sinCorregir } = entregas
    ? agruparEntregas(entregas)
    : { conNota: [], sinCorregir: [] }
  const limitReached = (entregas?.length ?? 0) >= LIMITE_ENTREGAS
  const materiaActual = materias?.find((m) => m.comision_id === comisionId) ?? null
  const comisionLabel = materiaActual
    ? (materiaActual.comision_nombre ?? `Comision ${materiaActual.comision_codigo}`)
    : null

  return (
    <div className="page-enter flex-1 overflow-y-auto px-6 py-10">
      <div className="max-w-3xl mx-auto">
        <button
          type="button"
          onClick={() => navigate({ to: "/" })}
          className="press-shrink inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink mb-6"
          data-testid="mis-notas-back"
        >
          <span aria-hidden="true">←</span>
          Volver a mis materias
        </button>

        <header className="mb-8 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
              Mis notas
            </h1>
            <p className="text-sm text-muted leading-relaxed mt-2 max-w-xl">
              Tu nota y la correccion del docente quedan aca aunque el trabajo practico se archive.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {comisionLabel && (
              <p
                data-testid="mis-notas-comision"
                className="text-xs font-mono uppercase tracking-wider text-muted"
              >
                {materiaActual?.codigo} <span className="text-muted-soft">·</span> {comisionLabel}
              </p>
            )}
            <HelpButton title="Mis notas" content={helpContent.misNotas} />
          </div>
        </header>

        {materias && materias.length > 1 && (
          <ComisionPicker
            materias={materias}
            selected={comisionId}
            onSelect={setSelectedComisionId}
          />
        )}

        {loading && <LoadingSkeleton />}
        {!loading && error && <ErrorPanel error={error} />}
        {!loading && !error && conNota.length === 0 && sinCorregir.length === 0 && <EmptyState />}
        {!loading && !error && (conNota.length > 0 || sinCorregir.length > 0) && (
          <MisNotasList
            conNota={conNota}
            sinCorregir={sinCorregir}
            limitReached={limitReached}
            onSelect={setSelected}
          />
        )}
      </div>
    </div>
  )
}

function ComisionPicker({
  materias,
  selected,
  onSelect,
}: {
  materias: MateriaInscripta[]
  selected: string | null
  onSelect: (comisionId: string) => void
}) {
  return (
    <fieldset className="mb-6 m-0 p-0 border-0">
      <legend className="text-[11px] font-mono uppercase tracking-[0.12em] text-muted mb-2 p-0">
        Materia
      </legend>
      <div className="flex flex-wrap gap-2">
        {materias.map((m) => {
          const active = m.comision_id === selected
          return (
            <button
              key={m.inscripcion_id}
              type="button"
              onClick={() => onSelect(m.comision_id)}
              aria-pressed={active}
              className={`press-shrink px-3 py-1.5 rounded-md border text-xs font-medium transition-colors ${
                active
                  ? "border-accent-brand/40 bg-accent-brand-soft text-accent-brand-deep"
                  : "border-border bg-surface text-body hover:bg-surface-alt"
              }`}
            >
              <span className="font-mono">{m.codigo}</span>
              <span className="text-muted-soft mx-1">·</span>
              {m.nombre}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}

function formatDateShort(iso: string): string {
  try {
    // `toLocaleDateString(..., { day: "2-digit", month: "2-digit" })` no
    // rellena el mes de un solo dígito en todos los runtimes (depende de los
    // datos ICU disponibles) — "12/9" en vez de "12/09". El shape confirmado
    // (proposal.md) usa dd/mm con cero a la izquierda siempre, así que se
    // arma a mano en vez de confiar en el formateador.
    const d = new Date(iso)
    const day = String(d.getDate()).padStart(2, "0")
    const month = String(d.getMonth() + 1).padStart(2, "0")
    return `${day}/${month}`
  } catch {
    return iso
  }
}
