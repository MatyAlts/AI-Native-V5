/**
 * Home del web-student (rediseño v2 2026): "Mis materias".
 *
 * Layout claro 2026: page-enter + header con eyebrow + cards con hover-lift +
 * stagger animations + skeleton loading. Mantiene la decisión bicapa: cards
 * para N≤5, lista densa para N>5. Strip N1-N4 visible desde el primer pixel
 * en empty state (PRODUCT.md design principle #1: el modelo N4 es el producto).
 *
 * Bootstrap recovery: si hay `active-episode-id` en sessionStorage, redirigimos
 * a /episodio/:id antes de pintar la home — preserva la UX de "recuperar sesión".
 */
import { useQuery } from "@tanstack/react-query"
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router"
import { BookOpenText, Plus, Sparkles } from "lucide-react"
import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { MateriaCard } from "../components/MateriaCard"
import { type MateriaInscripta, listMisMaterias } from "../lib/api"

const ACTIVE_EPISODE_KEY = "active-episode-id"

export const Route = createFileRoute("/")({
  component: HomePage,
})

function HomePage() {
  const navigate = useNavigate()

  useEffect(() => {
    if (typeof window === "undefined") return
    const storedId = window.sessionStorage.getItem(ACTIVE_EPISODE_KEY)
    if (storedId) {
      navigate({ to: "/episodio/$id", params: { id: storedId } })
    }
  }, [navigate])

  const { data, isLoading, error } = useQuery({
    queryKey: ["mis-materias"],
    queryFn: () => listMisMaterias(),
    staleTime: 5 * 60 * 1000,
  })

  return (
    <HomeContent
      isLoading={isLoading}
      error={error ? String(error) : null}
      materias={data ?? []}
      onEnter={(materia) =>
        navigate({ to: "/materia/$id", params: { id: materia.materia_id } })
      }
    />
  )
}

export interface HomeContentProps {
  isLoading: boolean
  error: string | null
  materias: MateriaInscripta[]
  onEnter: (m: MateriaInscripta) => void
}

export function HomeContent({ isLoading, error, materias, onEnter }: HomeContentProps) {
  if (isLoading) {
    return (
      <div
        className="page-enter flex-1 px-6 py-12"
        data-testid="home-loading"
        aria-label="Cargando tus materias"
      >
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="space-y-3">
            <div className="skeleton h-3 w-32 rounded" />
            <div className="skeleton h-9 w-56 rounded" />
          </div>
          <div className="space-y-4">
            <div className="skeleton h-32 rounded-xl" />
            <div className="skeleton h-32 rounded-xl" />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-enter flex-1 flex items-center justify-center p-8">
        <div className="max-w-md text-center rounded-xl border border-danger/30 bg-danger-soft p-6">
          <p className="text-sm font-semibold text-danger mb-2">
            No pudimos cargar tus materias.
          </p>
          <p className="text-xs font-mono text-danger/80 break-all">{error}</p>
        </div>
      </div>
    )
  }

  if (materias.length === 0) {
    return <EmptyState />
  }

  const usaListaDensa = materias.length > 5

  return (
    <div className="page-enter flex-1 overflow-y-auto px-6 py-12">
      <div className="max-w-3xl mx-auto">
        <header className="animate-fade-in-down mb-8 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p
              className="text-[11px] font-mono uppercase tracking-[0.12em] text-muted mb-2"
              data-testid="home-kicker-periodo"
            >
              {firstPeriodoCodigo(materias) ?? "Cuatrimestre actual"}
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">
              Mis materias
            </h1>
            <p className="text-sm text-muted leading-relaxed mt-2 max-w-xl">
              Cada materia te lleva a sus unidades temáticas y tareas prácticas. El tutor te
              acompaña en cada ejercicio.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <JoinMateriaControl />
            <Link
              to="/reflexiones"
              data-testid="home-link-reflexiones"
              className="press-shrink shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-border bg-surface text-xs font-medium text-body hover:bg-accent-brand-soft hover:text-accent-brand-deep hover:border-accent-brand/40 transition-colors"
            >
              <BookOpenText className="h-3.5 w-3.5" aria-hidden="true" />
              Mis reflexiones
            </Link>
          </div>
        </header>

        {usaListaDensa ? (
          <DensaList materias={materias} onEnter={onEnter} />
        ) : (
          <ul className="space-y-4">
            {materias.map((m, idx) => (
              <li
                key={m.inscripcion_id}
                className="animate-fade-in-up"
                style={{ animationDelay: `${100 + idx * 60}ms` }}
              >
                <MateriaCard materia={m} onEnter={onEnter} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// Permite sumar OTRA materia cuando el alumno ya tiene al menos una. El input
// de invitación de `__root` solo aparece con 0 materias; este control reabre
// ese flujo (mismo endpoint idempotente `POST /comisiones/join`) sin tocar la
// máquina de estados de inscripción. Reusa los tokens visuales del input de
// código original para mantener consistencia.
function JoinMateriaControl({ label = "Unirse a otra materia" }: { label?: string }) {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const close = () => {
    if (submitting) return
    setOpen(false)
    setCode("")
    setError(null)
  }

  const submit = async () => {
    setError(null)
    setSubmitting(true)
    try {
      const r = await fetch("/api/v1/comisiones/join", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invite_code: code.trim().toUpperCase() }),
      })
      if (r.ok) {
        // Recarga para refrescar la lista de materias (el backend ya inscribió;
        // es idempotente si el código apunta a una comisión ya cursada).
        window.location.reload()
      } else if (r.status === 404) {
        setError("Codigo invalido. Pedile el codigo correcto a tu docente.")
        setSubmitting(false)
      } else {
        setError("No se pudo inscribir. Intenta de nuevo.")
        setSubmitting(false)
      }
    } catch {
      setError("No se pudo inscribir. Intenta de nuevo.")
      setSubmitting(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="home-join-otra"
        className="press-shrink shrink-0 inline-flex items-center gap-1.5 px-3 py-2 rounded-md border border-border bg-surface text-xs font-medium text-body hover:bg-accent-brand-soft hover:text-accent-brand-deep hover:border-accent-brand/40 transition-colors"
      >
        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
        {label}
      </button>

      {open && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Unirse a otra materia"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={close}
        >
          <div
            className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold text-ink">Unirte a otra materia</h2>
            <p className="text-sm text-muted-soft mt-1 mb-4">
              Ingresá el código que te dio tu docente para sumar otra materia.
            </p>
            <input
              type="text"
              value={code}
              autoFocus
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === "Enter" && code.length >= 3 && !submitting) submit()
              }}
              placeholder="Ej: C1-7X3K"
              maxLength={10}
              className="w-full px-4 py-3 text-center text-lg font-mono tracking-widest border border-border-soft rounded-lg bg-surface focus:outline-none focus:ring-2 focus:ring-accent-brand"
            />
            {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
            <div className="flex items-center justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={close}
                disabled={submitting}
                className="press-shrink px-4 py-2 rounded-md border border-border bg-surface text-sm font-medium text-body hover:bg-surface-alt transition-colors disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={code.length < 3 || submitting}
                className="press-shrink bg-accent-brand text-white px-5 py-2 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {submitting ? "Uniéndote…" : "Unirme"}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

function firstPeriodoCodigo(materias: MateriaInscripta[]): string | null {
  if (materias.length === 0) return null
  const m = materias[0]
  if (!m) return null
  return m.periodo_codigo
}

// ─── Empty state honesto + strip N1-N4 ─────────────────────────────────

interface LevelBlurb {
  level: "N1" | "N2" | "N3" | "N4"
  label: string
  description: string
  colorVar: string
}

const LEVELS: LevelBlurb[] = [
  {
    level: "N1",
    label: "Lectura",
    description: "Leés el enunciado y planeás tu abordaje.",
    colorVar: "var(--color-level-n1)",
  },
  {
    level: "N2",
    label: "Anotación",
    description: "Anotás tu plan, dudas, ideas.",
    colorVar: "var(--color-level-n2)",
  },
  {
    level: "N3",
    label: "Validación",
    description: "Corrés tests y debugeás.",
    colorVar: "var(--color-level-n3)",
  },
  {
    level: "N4",
    label: "Tutor",
    description: "Preguntás cuando te trabás.",
    colorVar: "var(--color-level-n4)",
  },
]

function EmptyState() {
  return (
    <div className="page-enter flex-1 overflow-y-auto px-6 py-12">
      <div className="max-w-3xl mx-auto">
        <header className="animate-fade-in-down mb-10">
          <div className="inline-flex items-center gap-2 mb-4 px-3 py-1 rounded-full bg-accent-brand-soft border border-accent-brand/20">
            <Sparkles className="h-3.5 w-3.5 text-accent-brand" />
            <span className="text-[10px] font-mono uppercase tracking-[0.12em] text-accent-brand-deep font-semibold">
              UTN · Plataforma del piloto
            </span>
          </div>
          <h1 className="text-3xl font-semibold leading-tight tracking-tight text-ink mb-4">
            Tutor socrático con trazabilidad cognitiva
          </h1>
          <p className="text-base text-body leading-relaxed max-w-2xl">
            No te da la respuesta — te acompaña a construirla. Cada interacción queda registrada
            en una cadena criptográfica verificable.
          </p>
        </header>

        <section
          aria-label="Cómo trabajás con el tutor"
          className="rounded-2xl border border-border bg-surface p-6 sm:p-8 mb-8 animate-fade-in-up animate-delay-100 relative overflow-hidden"
        >
          <div
            aria-hidden="true"
            className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-accent-brand via-accent-brand to-accent-brand/40"
          />
          <p className="text-[10px] font-mono uppercase tracking-[0.12em] font-semibold text-muted mb-5">
            Cómo trabajás
          </p>
          <ol className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-6">
            {LEVELS.map((lvl, idx) => (
              <li
                key={lvl.level}
                className="flex flex-col animate-fade-in-up"
                style={{ animationDelay: `${200 + idx * 80}ms` }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span
                    aria-hidden="true"
                    data-testid={`level-dot-${lvl.level.toLowerCase()}`}
                    className="inline-block w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: lvl.colorVar }}
                  />
                  <span className="text-sm font-semibold text-ink">
                    {lvl.level} {lvl.label}
                  </span>
                </div>
                <p className="text-xs text-muted leading-relaxed">{lvl.description}</p>
              </li>
            ))}
          </ol>
        </section>

        <div
          data-testid="home-empty-gap-b2"
          className="rounded-xl border border-border bg-surface px-5 py-5 max-w-xl animate-fade-in-up animate-delay-300"
        >
          <p className="text-sm font-semibold text-ink mb-1">
            Para empezar, unite a tu comisión
          </p>
          <p className="text-xs text-muted leading-relaxed mb-4">
            Ingresá el código que te dio tu docente o tu Dirección de Informática para ver
            las materias y las tareas prácticas de tu comisión.
          </p>
          <JoinMateriaControl label="Ingresar el código de mi comisión" />
        </div>
      </div>
    </div>
  )
}

function DensaList({
  materias,
  onEnter,
}: {
  materias: MateriaInscripta[]
  onEnter: (m: MateriaInscripta) => void
}) {
  return (
    <ul
      className="rounded-xl border border-border bg-surface divide-y divide-border-soft overflow-hidden"
      data-testid="home-densa-list"
    >
      {materias.map((m, idx) => {
        const comisionLabel = m.comision_nombre ?? `Comisión ${m.comision_codigo}`
        return (
          <li
            key={m.inscripcion_id}
            data-testid="materia-list-item"
            data-materia-codigo={m.codigo}
            className="px-5 py-4 flex items-start gap-4 hover:bg-surface-alt transition-colors animate-fade-in-up"
            style={{ animationDelay: `${50 + idx * 30}ms` }}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-xs font-mono text-muted">{m.codigo}</span>
                <span className="text-muted-soft">·</span>
                <span className="text-xs font-mono text-muted">{comisionLabel}</span>
              </div>
              <p className="text-sm font-medium text-ink">{m.nombre}</p>
              <p className="text-xs text-muted mt-0.5">
                {m.periodo_codigo}
                {m.horario_resumen && (
                  <>
                    <span className="text-muted-soft mx-1.5">·</span>
                    {m.horario_resumen}
                  </>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onEnter(m)}
              className="press-shrink shrink-0 px-3 py-1.5 rounded-md border border-border bg-surface text-xs font-medium text-body hover:bg-accent-brand-soft hover:text-accent-brand-deep hover:border-accent-brand/40 transition-colors"
            >
              Entrar
            </button>
          </li>
        )
      })}
    </ul>
  )
}
