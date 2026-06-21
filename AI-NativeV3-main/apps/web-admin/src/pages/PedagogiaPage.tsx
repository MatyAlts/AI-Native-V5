/**
 * Sección "Pedagogía" del panel admin.
 *
 * Dashboard agregado sobre TODOS los episodios de un scope (materia entera o
 * comisión puntual). Cinco bloques construidos desde datos que ya existen, sin
 * codificación manual de docentes:
 *
 *   1. Distribución de perfiles de apropiación + subgrupos.
 *   2. Trayectoria longitudinal por estudiante (la pregunta central de la tesis).
 *   3. Matriz estudiante x perfil.
 *   4. Triangulación perfil vs completitud (proxy honesto: piloto sin notas).
 *   5. Señales: coherencias CT/CCD/CII promedio por perfil.
 *
 * Dataviz SVG inline (sin chart libs, ver DESIGN.md). Color semántico: verde =
 * reflexiva, ámbar = superficial, rojo = delegación. Headers X-* + Bearer los
 * inyecta el monkey-patch de `main.tsx`. Backend: GET /api/v1/analytics/pedagogia.
 */
import { PageContainer } from "@platform/ui"
import { type ReactNode, useEffect, useMemo, useState } from "react"
import { helpContent } from "../utils/helpContent"

// ── Tipos (espejo de PedagogiaOut del analytics-service) ──────────────────

interface ComisionScope {
  comision_id: string
  nombre: string
  n_episodios: number
  n_alumnos: number
}
interface MateriaScope {
  materia_id: string
  nombre: string
  codigo: string
  n_episodios: number
  comisiones: ComisionScope[]
}
interface ScopesOut {
  materias: MateriaScope[]
}

interface SubgrupoCount {
  key: string
  n: number
}
interface DistribucionBlock {
  n_episodios_clasificados: number
  por_apropiacion: Record<string, number>
  por_subgrupo: SubgrupoCount[]
}
interface TrayectoriaAlumno {
  student: string
  n_episodios: number
  primera: string | null
  ultima: string | null
  max_alcanzada: string | null
  label: string
  serie_ordinal: number[]
}
interface TrayectoriaBlock {
  n_alumnos: number
  n_con_datos: number
  mejorando: number
  estable: number
  empeorando: number
  insuficiente: number
  net_progression_ratio: number
  alumnos: TrayectoriaAlumno[]
}
interface MatrizFila {
  student: string
  counts: Record<string, number>
  total: number
  dominante: string | null
}
interface MatrizBlock {
  perfiles: string[]
  filas: MatrizFila[]
}
interface TriangulacionPerfil {
  apropiacion: string
  n_alumnos: number
  completitud_promedio: number | null
}
interface TriangulacionBlock {
  sin_notas_finales: boolean
  n_alumnos_con_entrega: number
  por_perfil: TriangulacionPerfil[]
}
interface SenalesPerfil {
  apropiacion: string
  n: number
  ct_promedio: number | null
  ccd_promedio: number | null
  cii_promedio: number | null
}
interface SenalesBlock {
  por_perfil: SenalesPerfil[]
}
interface PedagogiaOut {
  scope_label: string
  comisiones_incluidas: string[]
  n_episodios_total: number
  distribucion: DistribucionBlock
  trayectoria: TrayectoriaBlock
  matriz: MatrizBlock
  triangulacion: TriangulacionBlock
  senales: SenalesBlock
}

// ── Vocabulario semántico de apropiación ──────────────────────────────────

interface AprStyle {
  label: string
  short: string
  bar: string
  text: string
  soft: string
  hex: string
}
const APR = {
  apropiacion_reflexiva: {
    label: "Apropiación reflexiva",
    short: "Reflexiva",
    bar: "bg-success",
    text: "text-success",
    soft: "bg-success-soft",
    hex: "var(--color-success)",
  },
  apropiacion_superficial: {
    label: "Apropiación superficial",
    short: "Superficial",
    bar: "bg-warning",
    text: "text-warning",
    soft: "bg-warning-soft",
    hex: "var(--color-warning)",
  },
  delegacion_pasiva: {
    label: "Delegación pasiva",
    short: "Delegación",
    bar: "bg-danger",
    text: "text-danger",
    soft: "bg-danger-soft",
    hex: "var(--color-danger)",
  },
  indeterminado: {
    label: "Indeterminado",
    short: "Indet.",
    bar: "bg-border-strong",
    text: "text-muted",
    soft: "bg-surface-alt",
    hex: "var(--color-muted-soft, #94a3b8)",
  },
} satisfies Record<string, AprStyle>
const aprStyle = (k: string): AprStyle => APR[k as keyof typeof APR] ?? APR.indeterminado
// ordinal 0/1/2 -> color (delegación, superficial, reflexiva)
const ORDINAL_HEX = [APR.delegacion_pasiva.hex, APR.apropiacion_superficial.hex, APR.apropiacion_reflexiva.hex]

const APR_ORDER = ["apropiacion_reflexiva", "apropiacion_superficial", "delegacion_pasiva"]

// ── Página ────────────────────────────────────────────────────────────────

export function PedagogiaPage(): ReactNode {
  const [scopes, setScopes] = useState<ScopesOut | null>(null)
  const [materiaId, setMateriaId] = useState<string | null>(null)
  // scope value: "general" o un comision_id concreto.
  const [scopeValue, setScopeValue] = useState<string>("general")

  const [data, setData] = useState<PedagogiaOut | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 1. Cargar el árbol de scopes (materias -> comisiones).
  useEffect(() => {
    let cancelled = false
    fetch("/api/v1/analytics/pedagogia/scopes")
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((s: ScopesOut) => {
        if (cancelled) return
        setScopes(s)
        const first = s.materias[0]
        if (first) setMateriaId(first.materia_id)
      })
      .catch((e) => {
        if (!cancelled) setError(`No se pudo cargar el selector: ${e.message}`)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const materia = useMemo(
    () => scopes?.materias.find((m) => m.materia_id === materiaId) ?? null,
    [scopes, materiaId],
  )

  // 2. Cargar el bundle al cambiar el scope.
  useEffect(() => {
    if (!materiaId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const qs =
      scopeValue === "general"
        ? `materia_id=${materiaId}`
        : `comision_id=${scopeValue}`
    fetch(`/api/v1/analytics/pedagogia?${qs}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: PedagogiaOut) => {
        if (cancelled) return
        setData(d)
        setLoading(false)
      })
      .catch((e) => {
        if (cancelled) return
        setError(`Error cargando análisis: ${e.message}`)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [materiaId, scopeValue])

  return (
    <PageContainer
      title="Pedagogía"
      eyebrow="Inicio · Pedagogía"
      description={
        data
          ? `${data.scope_label} · ${data.n_episodios_total} episodios`
          : "Análisis pedagógico agregado sobre todos los episodios"
      }
      helpContent={helpContent.pedagogia}
    >
      <div className="space-y-8">
        {/* Selector materia + scope */}
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wide text-muted">Materia</span>
            <select
              value={materiaId ?? ""}
              onChange={(e) => {
                setMateriaId(e.target.value)
                setScopeValue("general")
              }}
              className="h-9 min-w-56 rounded-md border border-border-strong bg-surface px-3 text-sm shadow-sm"
            >
              {scopes?.materias.map((m) => (
                <option key={m.materia_id} value={m.materia_id}>
                  {m.nombre} ({m.n_episodios} ep.)
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium uppercase tracking-wide text-muted">Alcance</span>
            <select
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              className="h-9 min-w-56 rounded-md border border-border-strong bg-surface px-3 text-sm shadow-sm"
              disabled={!materia}
            >
              <option value="general">General — todas las comisiones</option>
              {materia?.comisiones.map((c) => (
                <option key={c.comision_id} value={c.comision_id}>
                  {c.nombre} ({c.n_episodios} ep. · {c.n_alumnos} alumnos)
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger-soft p-4 text-danger">
            <p className="font-medium">No se pudo cargar</p>
            <p className="mt-1 text-sm">{error}</p>
          </div>
        )}

        {loading && !data && <p className="text-sm text-muted">Computando análisis…</p>}

        {data && (
          <div className={loading ? "space-y-8 opacity-50 transition-opacity" : "space-y-8"}>
            <DistribucionSection block={data.distribucion} />
            <TrayectoriaSection block={data.trayectoria} />
            <MatrizSection block={data.matriz} />
            <TriangulacionSection block={data.triangulacion} />
            <SenalesSection block={data.senales} />
          </div>
        )}
      </div>
    </PageContainer>
  )
}

// ── Bloque 1: Distribución ────────────────────────────────────────────────

function DistribucionSection({ block }: { block: DistribucionBlock }): ReactNode {
  const total = block.n_episodios_clasificados
  const order = [...APR_ORDER, "indeterminado"].filter((k) => (block.por_apropiacion[k] ?? 0) > 0)
  const maxSub = Math.max(1, ...block.por_subgrupo.map((s) => s.n))

  return (
    <Section
      n="1"
      title="Distribución de perfiles"
      subtitle={`${total} episodios clasificados`}
    >
      {total === 0 ? (
        <Empty>No hay episodios clasificados en este scope.</Empty>
      ) : (
        <div className="space-y-6">
          {/* Barra apilada horizontal */}
          <div>
            <div className="flex h-12 w-full overflow-hidden rounded-md">
              {order.map((k) => {
                const v = block.por_apropiacion[k] ?? 0
                const pct = (v / total) * 100
                const s = aprStyle(k)
                return (
                  <div
                    key={k}
                    className={`${s.bar} flex items-center justify-center`}
                    style={{ width: `${pct}%` }}
                    title={`${s.label}: ${v} (${pct.toFixed(0)}%)`}
                  >
                    {pct > 9 && (
                      <span className="px-1 text-xs font-medium text-white tabular-nums">
                        {pct.toFixed(0)}%
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
            <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
              {order.map((k) => {
                const v = block.por_apropiacion[k] ?? 0
                const s = aprStyle(k)
                return (
                  <div key={k} className="flex items-center gap-2 text-sm">
                    <span className={`h-3 w-3 rounded-sm ${s.bar}`} />
                    <span className="text-ink">{s.label}</span>
                    <span className="font-mono text-xs text-muted tabular-nums">{v}</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Desglose por subgrupo */}
          {block.por_subgrupo.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                Por subgrupo
              </p>
              <div className="space-y-1.5">
                {block.por_subgrupo.map((sg) => (
                  <div key={sg.key} className="flex items-center gap-3">
                    <span className="w-48 shrink-0 truncate text-sm text-ink" title={sg.key}>
                      {sg.key}
                    </span>
                    <div className="h-4 flex-1 overflow-hidden rounded bg-surface-alt">
                      <div
                        className="h-full bg-accent-brand"
                        style={{ width: `${(sg.n / maxSub) * 100}%` }}
                      />
                    </div>
                    <span className="w-8 text-right font-mono text-xs text-muted tabular-nums">
                      {sg.n}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Section>
  )
}

// ── Bloque 2: Trayectoria (hero) ──────────────────────────────────────────

const LABEL_STYLE = {
  mejorando: { text: "text-success", soft: "bg-success-soft", arrow: "↑", label: "Mejoró" },
  estable: { text: "text-muted", soft: "bg-surface-alt", arrow: "→", label: "Estable" },
  empeorando: { text: "text-danger", soft: "bg-danger-soft", arrow: "↓", label: "Empeoró" },
  insuficiente: { text: "text-muted-soft", soft: "bg-surface-alt", arrow: "·", label: "Datos insuf." },
} satisfies Record<string, { text: string; soft: string; arrow: string; label: string }>

function TrayectoriaSection({ block }: { block: TrayectoriaBlock }): ReactNode {
  const pctMejora =
    block.n_con_datos > 0 ? Math.round((block.mejorando / block.n_con_datos) * 100) : 0
  const conDatos = block.alumnos.filter((a) => a.label !== "insuficiente")
  const insuf = block.alumnos.filter((a) => a.label === "insuficiente")

  return (
    <Section
      n="2"
      title="Trayectoria de apropiación"
      subtitle="¿El tutor mueve a los alumnos hacia la reflexión?"
    >
      {/* Headline honesto */}
      <div className="mb-5 rounded-lg border border-border bg-surface p-4">
        <p className="text-lg leading-snug text-ink">
          <span className="font-semibold text-success">{block.mejorando}</span> de{" "}
          <span className="font-semibold">{block.n_con_datos}</span> alumnos con datos suficientes
          (3+ episodios) <span className="font-semibold">mejoraron</span> su perfil de apropiación a
          lo largo del cursado{block.n_con_datos > 0 ? ` (${pctMejora}%)` : ""}.
        </p>
        <div className="mt-3">
          <ProgressionBar block={block} />
        </div>
        <p className="mt-3 text-xs text-muted">
          Índice de progresión neta:{" "}
          <span className="font-mono tabular-nums text-ink">
            {block.net_progression_ratio >= 0 ? "+" : ""}
            {block.net_progression_ratio.toFixed(2)}
          </span>{" "}
          (mejorando − empeorando, sobre alumnos con 3+ episodios; rango −1 a +1). Operacionalización
          longitudinal: último tercio vs primer tercio en escala ordinal.
        </p>
      </div>

      {/* Filas por alumno */}
      <div className="max-h-[28rem] overflow-y-auto rounded-lg border border-border">
        <div className="grid grid-cols-[6rem_1fr_9rem_6rem] items-center gap-2 border-b border-border bg-surface-alt px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
          <span>Alumno</span>
          <span>Trayectoria temporal</span>
          <span>Tendencia</span>
          <span className="text-right">Episodios</span>
        </div>
        {conDatos.map((a) => (
          <TrajRow key={a.student} a={a} />
        ))}
        {insuf.length > 0 && (
          <div className="border-t border-border bg-surface-alt px-4 py-2 text-xs text-muted-soft">
            {insuf.length} alumnos con 1–2 episodios: datos insuficientes para inferir progresión.
          </div>
        )}
      </div>
    </Section>
  )
}

function ProgressionBar({ block }: { block: TrayectoriaBlock }): ReactNode {
  const segs: { k: string; v: number; cls: string; label: string }[] = [
    { k: "mejorando", v: block.mejorando, cls: "bg-success", label: "Mejoraron" },
    { k: "estable", v: block.estable, cls: "bg-border-strong", label: "Estables" },
    { k: "empeorando", v: block.empeorando, cls: "bg-danger", label: "Empeoraron" },
    { k: "insuficiente", v: block.insuficiente, cls: "bg-surface-alt", label: "Insuf." },
  ]
  const total = block.n_alumnos || 1
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full">
        {segs.map((s) => (
          <div
            key={s.k}
            className={s.cls}
            style={{ width: `${(s.v / total) * 100}%` }}
            title={`${s.label}: ${s.v}`}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {segs.map((s) => (
          <span key={s.k} className="flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-sm ${s.cls}`} />
            {s.label} <span className="font-mono tabular-nums text-ink">{s.v}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

function TrajRow({ a }: { a: TrayectoriaAlumno }): ReactNode {
  const ls = LABEL_STYLE[a.label as keyof typeof LABEL_STYLE] ?? LABEL_STYLE.estable
  return (
    <div className="grid grid-cols-[6rem_1fr_9rem_6rem] items-center gap-2 border-b border-border px-4 py-2 last:border-b-0 hover:bg-surface-alt">
      <span className="font-mono text-xs text-muted">{a.student}</span>
      <Sparkline serie={a.serie_ordinal} />
      <span className={`flex items-center gap-1.5 text-sm font-medium ${ls.text}`}>
        <span aria-hidden className="text-base leading-none">
          {ls.arrow}
        </span>
        {ls.label}
      </span>
      <span className="text-right font-mono text-sm tabular-nums text-ink">{a.n_episodios}</span>
    </div>
  )
}

function Sparkline({ serie }: { serie: number[] }): ReactNode {
  const W = 200
  const H = 34
  const pad = 5
  if (serie.length === 0) {
    return <span className="text-xs text-muted-soft">sin datos</span>
  }
  const n = serie.length
  const xFor = (i: number) => (n === 1 ? W / 2 : pad + (i / (n - 1)) * (W - 2 * pad))
  const yFor = (v: number) => H - pad - (v / 2) * (H - 2 * pad)
  const poly = serie.map((v, i) => `${xFor(i).toFixed(1)},${yFor(v).toFixed(1)}`).join(" ")
  const last = serie[serie.length - 1] ?? 0
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
      {[0, 1, 2].map((g) => (
        <line
          key={g}
          x1={pad}
          x2={W - pad}
          y1={yFor(g)}
          y2={yFor(g)}
          stroke="var(--color-border)"
          strokeWidth={1}
          strokeDasharray="2 3"
        />
      ))}
      {n > 1 && (
        <polyline points={poly} fill="none" stroke="var(--color-muted-soft, #94a3b8)" strokeWidth={1.5} />
      )}
      {serie.map((v, i) => (
        <circle
          key={i}
          cx={xFor(i)}
          cy={yFor(v)}
          r={i === n - 1 ? 3.5 : 2.5}
          fill={ORDINAL_HEX[v] ?? "var(--color-muted-soft, #94a3b8)"}
        />
      ))}
      <circle
        cx={xFor(n - 1)}
        cy={yFor(last)}
        r={5}
        fill="none"
        stroke={ORDINAL_HEX[last] ?? "var(--color-muted-soft, #94a3b8)"}
        strokeWidth={1.5}
      />
    </svg>
  )
}

// ── Bloque 3: Matriz alumno x perfil ──────────────────────────────────────

function MatrizSection({ block }: { block: MatrizBlock }): ReactNode {
  const maxCell = Math.max(
    1,
    ...block.filas.flatMap((f) => block.perfiles.map((p) => f.counts[p] ?? 0)),
  )
  return (
    <Section n="3" title="Matriz alumno × perfil" subtitle={`${block.filas.length} alumnos`}>
      {block.filas.length === 0 ? (
        <Empty>Sin alumnos clasificados en este scope.</Empty>
      ) : (
        <div className="max-h-[28rem] overflow-auto rounded-lg border border-border">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 bg-surface-alt">
              <tr className="text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-2 text-left font-semibold">Alumno</th>
                {block.perfiles.map((p) => (
                  <th key={p} className="px-3 py-2 text-center font-semibold">
                    {aprStyle(p).short}
                  </th>
                ))}
                <th className="px-3 py-2 text-right font-semibold">Total</th>
                <th className="px-4 py-2 text-left font-semibold">Dominante</th>
              </tr>
            </thead>
            <tbody>
              {block.filas.map((f) => (
                <tr key={f.student} className="border-t border-border">
                  <td className="px-4 py-1.5 font-mono text-xs text-muted">{f.student}</td>
                  {block.perfiles.map((p) => {
                    const v = f.counts[p] ?? 0
                    const intensity = v / maxCell
                    const s = aprStyle(p)
                    return (
                      <td key={p} className="px-3 py-1.5 text-center">
                        {v > 0 ? (
                          <span
                            className={`inline-flex h-7 w-7 items-center justify-center rounded font-mono text-xs tabular-nums ${s.text}`}
                            style={{
                              backgroundColor: s.hex,
                              opacity: 0.18 + intensity * 0.55,
                            }}
                          >
                            <span className="text-ink">{v}</span>
                          </span>
                        ) : (
                          <span className="text-muted-soft">·</span>
                        )}
                      </td>
                    )
                  })}
                  <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums text-ink">
                    {f.total}
                  </td>
                  <td className="px-4 py-1.5">
                    {f.dominante && (
                      <span className={`text-xs font-medium ${aprStyle(f.dominante).text}`}>
                        {aprStyle(f.dominante).short}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  )
}

// ── Bloque 4: Triangulación ───────────────────────────────────────────────

function TriangulacionSection({ block }: { block: TriangulacionBlock }): ReactNode {
  return (
    <Section
      n="4"
      title="Triangulación: perfil vs completitud"
      subtitle={`${block.n_alumnos_con_entrega} alumnos con entregas`}
    >
      {block.sin_notas_finales && (
        <p className="mb-4 rounded-md bg-warning-soft px-3 py-2 text-xs text-[#854d0e]">
          Honestidad metodológica: el piloto no tiene notas finales cargadas. Se usa la{" "}
          <strong>completitud de ejercicios</strong> (fracción de ejercicios marcados como
          completados en las entregas) como proxy de desempeño.
        </p>
      )}
      <div className="space-y-3">
        {block.por_perfil.map((p) => {
          const s = aprStyle(p.apropiacion)
          const pct = p.completitud_promedio == null ? null : Math.round(p.completitud_promedio * 100)
          return (
            <div key={p.apropiacion} className="flex items-center gap-3">
              <span className={`w-28 shrink-0 text-sm font-medium ${s.text}`}>{s.short}</span>
              <div className="h-6 flex-1 overflow-hidden rounded bg-surface-alt">
                {pct != null && (
                  <div
                    className={`flex h-full items-center justify-end ${s.bar} pr-2`}
                    style={{ width: `${Math.max(pct, 6)}%` }}
                  >
                    <span className="text-xs font-medium text-white tabular-nums">{pct}%</span>
                  </div>
                )}
              </div>
              <span className="w-24 text-right text-xs text-muted">
                {pct == null ? "sin entregas" : `${p.n_alumnos} alumnos`}
              </span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

// ── Bloque 5: Señales (coherencias por perfil) ────────────────────────────

function SenalesSection({ block }: { block: SenalesBlock }): ReactNode {
  return (
    <Section
      n="5"
      title="Señales que respaldan cada perfil"
      subtitle="Coherencias CT / CCD / CII promedio"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {block.por_perfil.map((p) => {
          const s = aprStyle(p.apropiacion)
          return (
            <div key={p.apropiacion} className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className={`text-sm font-semibold ${s.text}`}>{s.short}</span>
                <span className="font-mono text-xs text-muted tabular-nums">n={p.n}</span>
              </div>
              <CoherBar label="Temporal (CT)" value={p.ct_promedio} />
              <CoherBar label="Código↔Discurso (CCD)" value={p.ccd_promedio} />
              <CoherBar label="Inter-iteración (CII)" value={p.cii_promedio} />
            </div>
          )
        })}
      </div>
      <p className="mt-3 text-xs text-muted">
        CCD usa una ventana temporal conservadora (operacionalización declarada en el ADR); valores
        promedio sobre los episodios de cada perfil.
      </p>
    </Section>
  )
}

function CoherBar({ label, value }: { label: string; value: number | null }): ReactNode {
  const pct = value == null ? null : Math.round(value * 100)
  return (
    <div className="mb-2.5 last:mb-0">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="font-mono tabular-nums text-ink">
          {value == null ? "—" : value.toFixed(2)}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-alt">
        {pct != null && (
          <div
            className={pct > 60 ? "h-full bg-success" : pct > 40 ? "h-full bg-warning" : "h-full bg-danger"}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  )
}

// ── Primitivas de layout ──────────────────────────────────────────────────

function Section({
  n,
  title,
  subtitle,
  children,
}: {
  n: string
  title: string
  subtitle?: string
  children: ReactNode
}): ReactNode {
  return (
    <section>
      <header className="mb-4 flex items-baseline gap-3">
        <span className="font-mono text-sm text-muted-soft tabular-nums">{n}</span>
        <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
        {subtitle && <span className="text-sm text-muted">· {subtitle}</span>}
      </header>
      {children}
    </section>
  )
}

function Empty({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="rounded-lg border border-border bg-surface-alt p-8 text-center text-sm text-muted">
      {children}
    </div>
  )
}
