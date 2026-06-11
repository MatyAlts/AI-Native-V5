import { PageContainer } from "@platform/ui"
import { useState } from "react"
import { useViewMode } from "../hooks/useViewMode"
import {
  type RatingLabel,
  type KappaRating,
  type KappaResult,
  computeKappa,
} from "../lib/api"
import {
  APPROPRIATION_DOCENTE,
  APPROPRIATION_INVESTIGADOR,
  kappaToDocente,
} from "../utils/docenteLabels"
import { helpContent } from "../utils/helpContent"

// Protocolos de etiquetado configurables (decision 2026-06-11).
const PROTOCOLS = {
  ejes: ["delegacion_pasiva", "apropiacion_superficial", "apropiacion_reflexiva"],
  subgrupos: [
    "autonomo_competente", "autonomo_trabado", "colaborador_reflexivo",
    "colaborador_funcional", "escribe_sin_validar", "indeterminado",
    "desenganchado", "dependiente",
  ],
  niveles: ["N1", "N2", "N3", "N4"],
} as const satisfies Record<string, readonly RatingLabel[]>

type ProtocolKey = keyof typeof PROTOCOLS

const PROTOCOL_LABELS: Record<ProtocolKey, string> = {
  ejes: "3 ejes",
  subgrupos: "8 subgrupos",
  niveles: "Niveles N1-N4",
}

// Record<string,string> (no Record<RatingLabel,...>) para no exigir las 15
// keys del tipo ampliado. Subgrupos heredan el color de su eje; N1-N4 en azules.
const CATEGORY_COLORS: Record<string, string> = {
  delegacion_pasiva: "bg-danger hover:bg-danger",
  apropiacion_superficial: "bg-warning hover:bg-warning",
  apropiacion_reflexiva: "bg-green-600 hover:bg-green-700",
  dependiente: "bg-danger hover:bg-danger",
  desenganchado: "bg-amber-400 hover:bg-amber-500",
  escribe_sin_validar: "bg-warning hover:bg-warning",
  colaborador_funcional: "bg-amber-400 hover:bg-amber-500",
  indeterminado: "bg-stone-400 hover:bg-stone-500",
  colaborador_reflexivo: "bg-green-600 hover:bg-green-700",
  autonomo_competente: "bg-green-700 hover:bg-green-800",
  autonomo_trabado: "bg-green-500 hover:bg-green-600",
  N1: "bg-sky-400 hover:bg-sky-500",
  N2: "bg-blue-500 hover:bg-blue-600",
  N3: "bg-indigo-500 hover:bg-indigo-600",
  N4: "bg-violet-600 hover:bg-violet-700",
}

interface EpisodeToRate {
  episode_id: string
  classifier_label: RatingLabel
  summary: string
}

interface Props {
  getToken: () => Promise<string | null>
  episodes: EpisodeToRate[]
}

export function KappaRatingView({ getToken, episodes }: Props) {
  const [humanLabels, setHumanLabels] = useState<Record<string, RatingLabel>>({})
  const [result, setResult] = useState<KappaResult | null>(null)
  const [computing, setComputing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"

  const allLabeled = episodes.every((e) => humanLabels[e.episode_id])
  const labeledCount = Object.keys(humanLabels).length

  const categoryLabels = isDocente ? APPROPRIATION_DOCENTE : APPROPRIATION_INVESTIGADOR
  const [protocol, setProtocol] = useState<ProtocolKey>("ejes")
  const activeCategories: RatingLabel[] = [...PROTOCOLS[protocol]]

  const handleLabel = (episodeId: string, label: RatingLabel) => {
    setHumanLabels((prev) => ({ ...prev, [episodeId]: label }))
  }

  const handleCompute = async () => {
    setComputing(true)
    setError(null)
    try {
      const ratings: KappaRating[] = episodes.map((e) => {
        const raterB = humanLabels[e.episode_id]
        if (!raterB) {
          throw new Error(`Episodio ${e.episode_id} sin etiqueta humana`)
        }
        return {
          episode_id: e.episode_id,
          rater_a: e.classifier_label,
          rater_b: raterB,
        }
      })
      const r = await computeKappa(ratings, getToken)
      setResult(r)
    } catch (e) {
      setError(String(e))
    } finally {
      setComputing(false)
    }
  }

  const handleReset = () => {
    setHumanLabels({})
    setResult(null)
    setError(null)
  }

  return (
    <PageContainer
      title={
        isDocente ? "Validacion de tu criterio de evaluacion" : "Inter-rater agreement (Kappa)"
      }
      description={
        isDocente
          ? "Compará tu evaluacion con la del sistema automatico. Cuanto mas coincidan, mas confiable es la evaluacion."
          : "Compara tu juicio con el del clasificador automatico N4. Target de la tesis: kappa >= 0.70 (acuerdo sustancial, Landis y Koch 1977). Alineado con paper Cortez & Garis y ADR-046."
      }
      helpContent={helpContent.kappaRating}
    >
      <div className="space-y-6 max-w-5xl">
        {!result && (
          <>
            <div className="rounded-xl border border-amber-300 bg-amber-50 px-6 py-4 text-sm text-amber-900">
              <p className="font-semibold mb-1">Modo entrenamiento — episodios sinteticos</p>
              <p>
                Este lote es para calibrar tu criterio de evaluacion (curva de aprendizaje del
                coding). <strong>NO son los episodios reales del piloto.</strong> El kappa que
                resulte aca mide tu consistencia con el modelo sobre datos de practica, no valida
                la fiabilidad inter-rater del piloto real.
              </p>
            </div>
            {isDocente && (
              <div className="rounded-xl border border-border bg-white px-6 py-4 text-sm text-muted">
                <p className="text-ink font-medium mb-1">Como funciona</p>
                <p>
                  Para cada trabajo, el sistema ya tiene su evaluacion automatica. Vos tenes que
                  marcar como evaluarias cada uno. Al terminar, comparamos ambas evaluaciones para
                  ver que tan alineados estan.
                </p>
              </div>
            )}

            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="text-sm">
                <span className="font-medium">{labeledCount}</span> de{" "}
                <span className="font-medium">{episodes.length}</span>{" "}
                {isDocente ? "trabajos evaluados" : "episodios etiquetados"}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleReset}
                  disabled={labeledCount === 0}
                  className="px-3 py-1.5 text-sm border border-border rounded hover:bg-canvas disabled:opacity-40"
                >
                  Reiniciar
                </button>
                <button
                  type="button"
                  onClick={handleCompute}
                  disabled={!allLabeled || computing}
                  className="px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border disabled:text-muted text-white rounded font-medium"
                >
                  {computing
                    ? "Calculando..."
                    : isDocente
                      ? "Comparar evaluaciones"
                      : "Calcular Kappa"}
                </button>
              </div>
            </div>

            {!isDocente && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted">Protocolo de etiquetado:</span>
                {(Object.keys(PROTOCOLS) as ProtocolKey[]).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setProtocol(p)
                      handleReset()
                    }}
                    className={`px-3 py-1 rounded border text-xs transition ${
                      protocol === p
                        ? "bg-accent-brand text-white border-accent-brand"
                        : "border-border hover:bg-canvas"
                    }`}
                  >
                    {PROTOCOL_LABELS[p]}
                  </button>
                ))}
              </div>
            )}

            <div className="space-y-3">
              {episodes.map((ep) => {
                const currentLabel = humanLabels[ep.episode_id]
                return (
                  <EpisodeRatingCard
                    key={ep.episode_id}
                    episode={ep}
                    {...(currentLabel ? { currentLabel } : {})}
                    onLabel={(l) => handleLabel(ep.episode_id, l)}
                    categories={activeCategories}
                    categoryLabels={categoryLabels}
                    isDocente={isDocente}
                  />
                )
              })}
            </div>
          </>
        )}

        {error && <div className="p-3 rounded bg-danger-soft text-danger text-sm">{error}</div>}

        {result &&
          (isDocente ? (
            <DocenteResultPanel result={result} onReset={handleReset} />
          ) : (
            <InvestigadorResultPanel result={result} onReset={handleReset} />
          ))}
      </div>
    </PageContainer>
  )
}

function EpisodeRatingCard({
  episode,
  currentLabel,
  onLabel,
  categories,
  categoryLabels,
  isDocente,
}: {
  episode: EpisodeToRate
  currentLabel?: RatingLabel
  onLabel: (l: RatingLabel) => void
  categories: RatingLabel[]
  categoryLabels: Record<string, string>
  isDocente: boolean
}) {
  const agreement = currentLabel
    ? currentLabel === episode.classifier_label
      ? "match"
      : "diff"
    : null

  return (
    <div
      className={`rounded-xl border bg-white p-4 transition-colors ${
        agreement === "match"
          ? "border-green-300 bg-green-50/30"
          : agreement === "diff"
            ? "border-amber-300 bg-amber-50/30"
            : "border-border"
      }`}
    >
      <div className="mb-3">
        <div className="flex items-center gap-2 mb-2">
          <span className="font-mono text-[11px] text-muted-soft uppercase tracking-wider">
            Episodio {isDocente ? episode.episode_id.slice(0, 8) : episode.episode_id.slice(0, 12)}
          </span>
          {agreement && (
            <span
              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                agreement === "match"
                  ? "bg-green-100 text-green-800"
                  : "bg-amber-100 text-amber-800"
              }`}
            >
              {agreement === "match" ? "✓ Coincidís" : "△ Diferís"}
            </span>
          )}
        </div>
        <p className="text-sm leading-relaxed text-ink">{episode.summary}</p>
      </div>

      <div className="rounded-lg bg-canvas border border-border-soft px-3 py-2 mb-3 flex items-center gap-2 text-xs">
        <span className="text-muted shrink-0">
          {isDocente ? "El sistema evaluó:" : "Clasificador automático:"}
        </span>
        <span
          aria-hidden="true"
          className="inline-block w-2 h-2 rounded-full"
          style={{ backgroundColor: appropriationDotColor(episode.classifier_label) }}
        />
        <span className="font-semibold text-ink">
          {categoryLabels[episode.classifier_label] ?? episode.classifier_label}
        </span>
      </div>

      <div>
        <div className="text-[11px] font-semibold text-muted mb-1.5 uppercase tracking-wider">
          {isDocente ? "¿Cómo lo evaluarías vos?" : "Tu rating"}
        </div>
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => {
            const selected = currentLabel === cat
            return (
              <button
                key={cat}
                type="button"
                onClick={() => onLabel(cat)}
                className={`flex-1 min-w-[120px] px-3 py-2 rounded text-white text-xs font-medium transition ${CATEGORY_COLORS[cat] ?? "bg-stone-400 hover:bg-stone-500"} ${
                  selected ? "ring-2 ring-offset-2 ring-[#111111]" : "opacity-70 hover:opacity-100"
                }`}
              >
                {categoryLabels[cat] ?? cat}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function appropriationDotColor(label: RatingLabel): string {
  if (label === "apropiacion_reflexiva") return "#16a34a"
  if (label === "apropiacion_superficial") return "#f59e0b"
  return "#dc2626" // delegacion_pasiva
}

function DocenteResultPanel({
  result,
  onReset,
}: {
  result: KappaResult
  onReset: () => void
}) {
  const docente = kappaToDocente(result.kappa)

  return (
    <div className="space-y-5">
      <div className={`rounded-xl p-6 ${docente.color}`}>
        <div className="text-2xl font-semibold mb-2">{docente.label}</div>
        <p className="text-sm">{docente.description}</p>
        <div className="mt-4 text-sm opacity-80">
          Sobre {result.n_episodes} trabajos evaluados. Coincidieron en el{" "}
          {(result.observed_agreement * 100).toFixed(0)}% de los casos.
        </div>
      </div>

      <div className="rounded-xl border border-border bg-white p-4">
        <h3 className="font-medium mb-3 text-sm">Coincidencia por tipo</h3>
        <div className="space-y-2">
          {Object.keys(result.per_class_agreement).map((c) => {
            const val = result.per_class_agreement[c] ?? 0
            return (
              <div key={c} className="flex items-center gap-3">
                <div className="min-w-[180px] text-sm">{APPROPRIATION_DOCENTE[c] ?? c}</div>
                <div className="flex-1 h-3 bg-border rounded overflow-hidden">
                  <div
                    className="h-full rounded"
                    style={{
                      width: `${val * 100}%`,
                      backgroundColor:
                        val >= 0.7
                          ? "var(--color-success)"
                          : val >= 0.4
                            ? "#f59e0b"
                            : "var(--color-danger)",
                    }}
                  />
                </div>
                <div className="text-xs text-muted min-w-[50px] text-right">
                  {(val * 100).toFixed(0)}%
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <button
        type="button"
        onClick={onReset}
        className="px-4 py-2 border border-border rounded hover:bg-canvas"
      >
        Evaluar otro grupo
      </button>
    </div>
  )
}

function InvestigadorResultPanel({
  result,
  onReset,
}: {
  result: KappaResult
  onReset: () => void
}) {
  const { kappa, interpretation, confusion_matrix, per_class_agreement } = result
  // Categorias presentes en el resultado (soporta cualquier protocolo elegido).
  const cats = Object.keys(confusion_matrix)

  const interpretationColor =
    kappa >= 0.81
      ? "text-green-700 bg-green-50"
      : kappa >= 0.61
        ? "text-green-700 bg-green-50"
        : kappa >= 0.41
          ? "text-warning/85 bg-warning-soft"
          : "text-danger bg-danger-soft"

  return (
    <div className="space-y-5">
      <div className={`rounded-xl p-6 ${interpretationColor}`}>
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-sm opacity-80">Cohen's Kappa</div>
            <div className="text-5xl font-semibold mt-1">{kappa.toFixed(4)}</div>
          </div>
          <div className="text-right">
            <div className="text-sm opacity-80">Interpretacion</div>
            <div className="text-lg font-medium mt-1">{interpretation}</div>
          </div>
        </div>
        <div className="mt-4 text-sm opacity-80">
          Sobre {result.n_episodes} episodios. Acuerdo observado:{" "}
          {(result.observed_agreement * 100).toFixed(1)}%. Esperado por azar:{" "}
          {(result.expected_agreement * 100).toFixed(1)}%.
        </div>
      </div>

      <div className="rounded-xl border border-border bg-white p-4">
        <h3 className="font-medium mb-3">Matriz de confusion</h3>
        <p className="text-xs text-muted mb-3">
          Filas = etiqueta del modelo · Columnas = etiqueta humana
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 font-medium"> </th>
              {cats.map((c) => (
                <th key={c} className="text-center py-2 font-medium text-xs px-2">
                  {APPROPRIATION_INVESTIGADOR[c] ?? c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cats.map((row) => (
              <tr key={row} className="border-b border-border/50">
                <td className="py-2 pr-4 text-xs text-muted">
                  {APPROPRIATION_INVESTIGADOR[row] ?? row}
                </td>
                {cats.map((col) => {
                  const val = confusion_matrix[row]?.[col] ?? 0
                  const isDiagonal = row === col
                  return (
                    <td
                      key={col}
                      className={`text-center py-2 px-2 ${
                        isDiagonal ? "bg-green-50 font-medium" : ""
                      }`}
                    >
                      {val}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-border bg-white p-4">
        <h3 className="font-medium mb-3">Acuerdo por clase</h3>
        <div className="space-y-2">
          {cats.map((c) => {
            const val = per_class_agreement[c] ?? 0
            return (
              <div key={c} className="flex items-center gap-3">
                <div className="min-w-[180px] text-sm">{APPROPRIATION_INVESTIGADOR[c] ?? c}</div>
                <div className="flex-1 h-3 bg-border rounded overflow-hidden">
                  <div
                    className="h-full bg-accent-brand rounded"
                    style={{ width: `${val * 100}%` }}
                  />
                </div>
                <div className="text-xs text-muted min-w-[50px] text-right">
                  {(val * 100).toFixed(1)}%
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <button
        type="button"
        onClick={onReset}
        className="px-4 py-2 border border-border rounded hover:bg-canvas"
      >
        Clasificar otro batch
      </button>
    </div>
  )
}
