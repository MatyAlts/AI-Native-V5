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
 * reflexiva, ámbar = superficial, rojo = delegación, gris = autónomo (eje
 * ortogonal, fuera del continuo ordinal). Headers X-* + Bearer los inyecta el
 * monkey-patch de `main.tsx`. Backend: GET /api/v1/analytics/pedagogia.
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
  label: string
  n: number
}
interface DistribucionBlock {
  n_episodios_clasificados: number
  n_indeterminados: number
  por_apropiacion: Record<string, number>
  por_subgrupo: SubgrupoCount[]
}
interface CurvaPunto {
  posicion: number
  media_ordinal: number | null
  n_alumnos: number
}
interface CurvaApropiacionBlock {
  puntos: CurvaPunto[]
  min_alumnos: number
}
interface CurvaAdversaPunto {
  posicion: number
  media_adversos: number
  n_alumnos: number
}
interface CurvaAdversaBlock {
  n_eventos_total: number
  puntos: CurvaAdversaPunto[]
  min_alumnos: number
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
interface KappaPar {
  rater_a: string
  rater_b: string
  n_episodios: number
  kappa: number | null
  interpretacion: string | null
  ac1: number | null
  ac1_interpretacion: string | null
  acuerdo_observado: number | null
}
interface KappaBlock {
  disponible: boolean
  n_codificadores: number
  n_episodios_codificados: number
  n_gold: number
  maquina_vs_consenso: KappaPar | null
  pares_humano_humano: KappaPar[]
}
interface PedagogiaOut {
  scope_label: string
  comisiones_incluidas: string[]
  n_episodios_total: number
  distribucion: DistribucionBlock
  curva_apropiacion: CurvaApropiacionBlock
  curva_adversa: CurvaAdversaBlock
  validacion_kappa: KappaBlock
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
  // Eje ORTOGONAL al continuo: trabajo autonomo (sin tutor). Gris = token
  // neutral del design system. No participa de la curva/slope longitudinal.
  autonomo: {
    label: "Autónomo (sin tutor)",
    short: "Autónomo",
    bar: "bg-neutral",
    text: "text-neutral",
    soft: "bg-surface-alt",
    hex: "var(--color-neutral)",
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
const ORDINAL_HEX = [
  APR.delegacion_pasiva.hex,
  APR.apropiacion_superficial.hex,
  APR.apropiacion_reflexiva.hex,
]

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
    const qs = scopeValue === "general" ? `materia_id=${materiaId}` : `comision_id=${scopeValue}`
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
            <CurvaApropiacionSection block={data.curva_apropiacion} />
            <CurvaAdversaSection block={data.curva_adversa} />
            <KappaSection block={data.validacion_kappa} />
            <AblacionSection />
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

// ── Bloque ⭐ A: Curva agregada de apropiación ────────────────────────────

function CurvaApropiacionSection({ block }: { block: CurvaApropiacionBlock }): ReactNode {
  const pts = block.puntos
    .filter((p) => p.media_ordinal != null)
    .map((p) => ({ x: p.posicion, y: p.media_ordinal as number, n: p.n_alumnos }))
  const first = pts[0]
  const last = pts[pts.length - 1]
  const delta = first && last ? last.y - first.y : 0

  return (
    <Section
      n="★"
      title="Evolución de la cohorte"
      subtitle="¿Sube la apropiación a medida que usan el tutor?"
    >
      {pts.length < 2 ? (
        <Empty>
          Datos insuficientes para la curva (se necesitan posiciones con {block.min_alumnos}+
          alumnos).
        </Empty>
      ) : (
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-3 flex items-center gap-3">
            <span
              className={`text-sm font-medium ${delta > 0.05 ? "text-success" : delta < -0.05 ? "text-danger" : "text-muted"}`}
            >
              {delta > 0 ? "↑" : delta < 0 ? "↓" : "→"} {delta >= 0 ? "+" : ""}
              {delta.toFixed(2)} niveles entre el 1.º y el último episodio
            </span>
          </div>
          <LineChart
            points={pts}
            yMin={0}
            yMax={2}
            yTicks={[
              { value: 0, label: "Delegación" },
              { value: 1, label: "Superficial" },
              { value: 2, label: "Reflexiva" },
            ]}
            stroke="var(--color-success)"
            area
          />
          <p className="mt-3 text-xs text-muted">
            Apropiación promedio de la cohorte según el <strong>número de episodio</strong> del
            alumno (1.º, 2.º, 3.º…). Una pendiente ascendente es <strong>consistente con</strong> —
            no prueba de — un efecto del tutor: el piloto es observacional, sin grupo control. Cada
            punto agrega solo posiciones con {block.min_alumnos}+ alumnos.
          </p>
        </div>
      )}
    </Section>
  )
}

// ── Bloque ⭐ B: Intentos adversos en el tiempo ───────────────────────────

function CurvaAdversaSection({ block }: { block: CurvaAdversaBlock }): ReactNode {
  const pts = block.puntos.map((p) => ({ x: p.posicion, y: p.media_adversos, n: p.n_alumnos }))
  const first = pts[0]
  const last = pts[pts.length - 1]
  const delta = first && last ? last.y - first.y : 0
  const yMax = Math.max(0.5, ...pts.map((p) => p.y)) * 1.15

  return (
    <Section
      n="★"
      title="Intentos de sacarle la respuesta al tutor"
      subtitle="¿Dejan de intentar gamear al tutor con el tiempo?"
    >
      {block.n_eventos_total === 0 ? (
        <Empty>No se registraron intentos adversos en este scope.</Empty>
      ) : pts.length < 2 ? (
        <Empty>
          Datos insuficientes para la curva (posiciones con {block.min_alumnos}+ alumnos).
        </Empty>
      ) : (
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-3 flex items-center gap-3">
            <span
              className={`text-sm font-medium ${delta < -0.02 ? "text-success" : delta > 0.02 ? "text-danger" : "text-muted"}`}
            >
              {delta < 0 ? "↓" : delta > 0 ? "↑" : "→"} {delta >= 0 ? "+" : ""}
              {delta.toFixed(2)} intentos/alumno entre el 1.º y el último episodio
            </span>
            <span className="font-mono text-xs text-muted tabular-nums">
              {block.n_eventos_total} eventos en total
            </span>
          </div>
          <LineChart
            points={pts}
            yMin={0}
            yMax={yMax}
            yTicks={[
              { value: 0, label: "0" },
              { value: yMax / 2, label: (yMax / 2).toFixed(1) },
              { value: yMax, label: yMax.toFixed(1) },
            ]}
            stroke="var(--color-danger)"
            area
          />
          <p className="mt-3 text-xs text-muted">
            Intentos adversos promedio por alumno (tratar de que el tutor dé la respuesta) según el
            número de episodio. Esta señal es <strong>independiente del classifier</strong> (no hay
            circularidad). Una curva <strong>descendente</strong> es consistente con el tutor
            moldeando la conducta hacia un uso legítimo.
          </p>
        </div>
      )}
    </Section>
  )
}

// ── LineChart SVG genérico (sin chart libs, DESIGN.md) ────────────────────

function LineChart({
  points,
  yMin,
  yMax,
  yTicks,
  stroke,
  area = false,
}: {
  points: { x: number; y: number; n: number }[]
  yMin: number
  yMax: number
  yTicks: { value: number; label: string }[]
  stroke: string
  area?: boolean
}): ReactNode {
  const W = 640
  const H = 220
  const padL = 92
  const padR = 18
  const padT = 14
  const padB = 30
  const xs = points.map((p) => p.x)
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  const xFor = (x: number) =>
    padL + (xMax === xMin ? 0.5 : (x - xMin) / (xMax - xMin)) * (W - padL - padR)
  const yFor = (y: number) => H - padB - ((y - yMin) / (yMax - yMin || 1)) * (H - padT - padB)
  const linePts = points.map((p) => `${xFor(p.x).toFixed(1)},${yFor(p.y).toFixed(1)}`).join(" ")
  const areaPts = `${xFor(points[0]?.x ?? 0).toFixed(1)},${(H - padB).toFixed(1)} ${linePts} ${xFor(points[points.length - 1]?.x ?? 0).toFixed(1)},${(H - padB).toFixed(1)}`
  // Etiquetas de eje X: cada N para no saturar.
  const step = Math.max(1, Math.ceil(points.length / 10))

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ maxHeight: H }}
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Gridlines + labels Y */}
      {yTicks.map((t) => (
        <g key={t.value}>
          <line
            x1={padL}
            x2={W - padR}
            y1={yFor(t.value)}
            y2={yFor(t.value)}
            stroke="var(--color-border)"
            strokeWidth={1}
            strokeDasharray="2 3"
          />
          <text
            x={padL - 10}
            y={yFor(t.value) + 4}
            textAnchor="end"
            className="fill-[var(--color-muted)]"
            fontSize={11}
          >
            {t.label}
          </text>
        </g>
      ))}
      {/* Área */}
      {area && <polygon points={areaPts} fill={stroke} opacity={0.08} />}
      {/* Línea */}
      <polyline
        points={linePts}
        fill="none"
        stroke={stroke}
        strokeWidth={2.5}
        strokeLinejoin="round"
      />
      {/* Puntos + eje X */}
      {points.map((p, i) => (
        <g key={p.x}>
          <circle cx={xFor(p.x)} cy={yFor(p.y)} r={3.5} fill={stroke}>
            <title>{`Episodio ${p.x}: ${p.y.toFixed(2)} (n=${p.n})`}</title>
          </circle>
          {i % step === 0 && (
            <text
              x={xFor(p.x)}
              y={H - padB + 16}
              textAnchor="middle"
              className="fill-[var(--color-muted-soft)]"
              fontSize={10}
            >
              {p.x}
            </text>
          )}
        </g>
      ))}
      <text
        x={(padL + W - padR) / 2}
        y={H - 2}
        textAnchor="middle"
        className="fill-[var(--color-muted)]"
        fontSize={10}
      >
        Número de episodio del alumno
      </text>
    </svg>
  )
}

// ── Bloque ⭐ C: Validación con Cohen's κ ─────────────────────────────────

function KappaSection({ block }: { block: KappaBlock }): ReactNode {
  if (!block.disponible || block.n_codificadores === 0) {
    return (
      <Section n="★" title="Validación: acuerdo máquina–humano (κ)" subtitle="Cohen's kappa">
        <Empty>
          Todavía no hay codificación humana cargada en este scope. Cuando los docentes etiqueten
          episodios, acá aparece el κ máquina–humano y entre docentes.
        </Empty>
      </Section>
    )
  }
  return (
    <Section
      n="★"
      title="Validación: acuerdo máquina–humano (κ)"
      subtitle={`${block.n_episodios_codificados} codificados · ${block.n_gold} de consenso · ${block.n_codificadores} codificadores`}
    >
      <div className="space-y-5 rounded-lg border border-border bg-surface p-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Máquina vs consenso docente (gold)
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {block.maquina_vs_consenso ? (
              <KappaStat
                pair={block.maquina_vs_consenso}
                label="Clasificador vs consenso docente"
              />
            ) : (
              <p className="text-xs text-muted">
                Aún no hay episodios de consenso (codificados igual por ≥2 docentes).
              </p>
            )}
          </div>
        </div>
        {block.pares_humano_humano.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Entre docentes (techo de acuerdo)
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              {block.pares_humano_humano.map((p, i) => (
                <KappaStat key={i} pair={p} label={`${p.rater_a} vs ${p.rater_b}`} />
              ))}
            </div>
          </div>
        )}
      </div>
      <p className="mt-3 text-xs text-muted">
        Titular: <strong>Gwet's AC1</strong>, robusto a la paradoja de prevalencia (cuando una
        categoría domina, el κ se defla pese a alto acuerdo crudo). Se muestran también el κ de
        Cohen y el acuerdo crudo para total transparencia. El acuerdo se mide contra el{" "}
        <strong>consenso docente</strong> (episodios codificados igual por ≥2 docentes), no contra
        cada docente por separado, y no puede superar el techo humano–humano: si los docentes no
        concuerdan entre sí, no se le exige más a la máquina. La brecha vive sobre todo en el eje
        superficial↔reflexiva (la máquina decide por señales conductuales; el criterio docente lee
        la conversación). Un valor bajo es un hallazgo válido, no se maquilla. El piloto held-out
        del paper reporta κ = 0.68 sobre el <strong>juez aislado</strong> en el eje fino (n=95);
        este panel mide el <strong>sistema completo</strong> contra consenso docente, por eso los
        valores difieren sin contradecirse.
      </p>
    </Section>
  )
}

function KappaStat({ pair, label }: { pair: KappaPar; label: string }): ReactNode {
  const colorFor = (v: number | null) =>
    v == null ? "text-muted" : v >= 0.6 ? "text-success" : v >= 0.4 ? "text-warning" : "text-danger"
  const badgeFor = (v: number | null) =>
    v == null
      ? "bg-surface-alt text-muted"
      : v >= 0.6
        ? "bg-success-soft text-success"
        : v >= 0.4
          ? "bg-warning-soft text-[#854d0e]"
          : "bg-danger-soft text-danger"
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm text-ink">{label}</span>
        <span className="font-mono text-xs text-muted tabular-nums">n={pair.n_episodios}</span>
      </div>
      {/* AC1 como titular (corregido por prevalencia) */}
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className={`font-mono text-2xl tabular-nums ${colorFor(pair.ac1)}`}>
          {pair.ac1 == null ? "—" : `AC1 ${pair.ac1.toFixed(2)}`}
        </span>
        {pair.ac1_interpretacion && (
          <span className={`rounded-full px-2 py-0.5 text-xs ${badgeFor(pair.ac1)}`}>
            {pair.ac1_interpretacion}
          </span>
        )}
      </div>
      {/* κ y acuerdo crudo como contexto */}
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted">
        <span>
          κ{" "}
          <span className="font-mono tabular-nums text-ink">
            {pair.kappa == null ? "—" : pair.kappa.toFixed(2)}
          </span>
          {pair.interpretacion ? ` (${pair.interpretacion})` : ""}
        </span>
        {pair.acuerdo_observado != null && (
          <span>
            · acuerdo crudo{" "}
            <span className="font-mono tabular-nums text-ink">
              {Math.round(pair.acuerdo_observado * 100)}%
            </span>
          </span>
        )}
      </div>
    </div>
  )
}

// ── Bloque ⭐ D: Ablación — cuánto aporta el árbol de decisión ─────────────
// Resultado FIJO del piloto held-out 2026 (Tabla 4 del paper). No depende del
// scope en vivo: valida la ARQUITECTURA, no el corpus. Se recomputa offline
// (correr el juez sin el árbol consume LLM), por eso los números van pineados.

const ABLACION = {
  ceiling: 0.77,
  lift: 0.54,
  nGrises: 95,
  filas: [
    {
      label: "Baseline (clase mayoritaria)",
      kappa: 0.0,
      detalle: "κ = 0 por construcción",
      tono: "muted",
    },
    {
      label: "Mismo LLM, sin el árbol",
      kappa: 0.14,
      detalle: "zero-shot: solo los nombres de clase",
      tono: "danger",
    },
    {
      label: "Modelo abierto + árbol",
      kappa: 0.47,
      detalle: "Llama 3.3 70B, self-hosteable (n=92)",
      tono: "brand",
    },
    {
      label: "Juez + árbol de decisión",
      kappa: 0.68,
      detalle: "Gemini 2.5 Flash · IC 95% 0.53–0.83",
      tono: "success",
    },
  ],
} as const

const ABL_BAR: Record<string, string> = {
  muted: "bg-border-strong",
  danger: "bg-danger",
  brand: "bg-accent-brand",
  success: "bg-success",
}

function AblacionSection(): ReactNode {
  return (
    <Section
      n="★"
      title="¿Cuánto aporta el árbol de decisión?"
      subtitle="El mismo LLM, con y sin el árbol de 7 reglas · piloto held-out 2026"
    >
      <div className="rounded-lg border border-border bg-surface p-4">
        <p className="mb-5 text-sm text-ink">
          <span className="font-semibold text-success">+{ABLACION.lift.toFixed(2)} de κ</span> es lo
          que aporta el árbol: el mismo modelo, sin él, cae de{" "}
          <span className="font-mono tabular-nums">0.68</span> a{" "}
          <span className="font-mono tabular-nums">0.14</span>.
        </p>
        <div className="relative">
          {/* Techo humano calibrado (κ = 0.77): cota superior de lo alcanzable */}
          <div
            className="pointer-events-none absolute bottom-8 top-4 border-l border-dashed border-border-strong"
            style={{ left: `${ABLACION.ceiling * 100}%` }}
          >
            <span className="absolute -top-4 left-1.5 whitespace-nowrap text-[10px] font-medium text-muted">
              techo humano {ABLACION.ceiling.toFixed(2)}
            </span>
          </div>
          <div className="space-y-3.5 pt-4">
            {ABLACION.filas.map((f) => (
              <div key={f.label}>
                <div className="mb-1 flex items-baseline justify-between gap-2">
                  <span className="text-sm text-ink">{f.label}</span>
                  <span className="font-mono text-sm tabular-nums text-ink">
                    κ {f.kappa.toFixed(2)}
                  </span>
                </div>
                <div className="h-5 overflow-hidden rounded bg-surface-alt">
                  <div
                    className={`h-full ${ABL_BAR[f.tono]}`}
                    style={{ width: `${Math.max(f.kappa * 100, 1)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-muted-soft">{f.detalle}</p>
              </div>
            ))}
          </div>
        </div>
        <p className="mt-5 text-xs text-muted">
          Acuerdo (Cohen's κ) contra la referencia humana sobre los mismos {ABLACION.nGrises}{" "}
          episodios grises del eje fino (superficial↔reflexiva). El árbol de decisión,{" "}
          <strong>no el modelo</strong>, carga el desempeño: sin él, el LLM colapsa a la clase
          mayoritaria. Es un resultado <strong>fijo del piloto held-out</strong> (no se recomputa en
          vivo: correr el juez sin árbol consume LLM). La contraparte reproducible, un modelo
          abierto self-hosteable, llega a 0.47 (trade-off precisión / reproducibilidad).
        </p>
      </div>
    </Section>
  )
}

// ── Bloque 1: Distribución ────────────────────────────────────────────────

function DistribucionSection({ block }: { block: DistribucionBlock }): ReactNode {
  const total = block.n_episodios_clasificados
  // `autonomo` es eje ortogonal (gris): aparece en la distribucion pero NO en la
  // curva/matriz/senales (que viven en el continuo ordinal del backend).
  const order = [...APR_ORDER, "autonomo", "indeterminado"].filter(
    (k) => (block.por_apropiacion[k] ?? 0) > 0,
  )
  const maxSub = Math.max(1, ...block.por_subgrupo.map((s) => s.n))

  return (
    <Section n="1" title="Distribución de perfiles" subtitle={`${total} episodios clasificados`}>
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
            {block.n_indeterminados > 0 && (
              <p className="mt-2 text-xs text-muted-soft">
                {block.n_indeterminados} episodios quedaron indeterminados (sin perfil asignable);
                se excluyen de la trayectoria y las curvas.
              </p>
            )}
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
                      {sg.label}
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
  insuficiente: {
    text: "text-muted-soft",
    soft: "bg-surface-alt",
    arrow: "·",
    label: "Datos insuf.",
  },
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
          (mejorando − empeorando, sobre alumnos con 3+ episodios; rango −1 a +1).
          Operacionalización longitudinal: último tercio vs primer tercio en escala ordinal.
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
        <polyline
          points={poly}
          fill="none"
          stroke="var(--color-muted-soft, #94a3b8)"
          strokeWidth={1.5}
        />
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
          const pct =
            p.completitud_promedio == null ? null : Math.round(p.completitud_promedio * 100)
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
            className={
              pct > 60 ? "h-full bg-success" : pct > 40 ? "h-full bg-warning" : "h-full bg-danger"
            }
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
