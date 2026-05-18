import { PageContainer } from "@platform/ui"
import { useState } from "react"
import { useViewMode } from "../hooks/useViewMode"
import {
  type AppropriationLabel,
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

const CATEGORIES: AppropriationLabel[] = [
  "delegacion_pasiva",
  "apropiacion_superficial",
  "apropiacion_reflexiva",
]

const CATEGORY_COLORS: Record<AppropriationLabel, string> = {
  delegacion_pasiva: "bg-danger hover:bg-danger",
  apropiacion_superficial: "bg-warning hover:bg-warning",
  apropiacion_reflexiva: "bg-green-600 hover:bg-green-700",
}

interface EpisodeToRate {
  episode_id: string
  classifier_label: AppropriationLabel
  summary: string
}

interface Props {
  getToken: () => Promise<string | null>
  episodes: EpisodeToRate[]
}

export function KappaRatingView({ getToken, episodes }: Props) {
  const [humanLabels, setHumanLabels] = useState<Record<string, AppropriationLabel>>({})
  const [result, setResult] = useState<KappaResult | null>(null)
  const [computing, setComputing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode] = useViewMode()
  const isDocente = viewMode === "docente"

  const allLabeled = episodes.every((e) => humanLabels[e.episode_id])
  const labeledCount = Object.keys(humanLabels).length

  const categoryLabels = isDocente ? APPROPRIATION_DOCENTE : APPROPRIATION_INVESTIGADOR

  const handleLabel = (episodeId: string, label: AppropriationLabel) => {
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

            <div className="space-y-3">
              {episodes.map((ep) => {
                const currentLabel = humanLabels[ep.episode_id]
                return (
                  <EpisodeRatingCard
                    key={ep.episode_id}
                    episode={ep}
                    {...(currentLabel ? { currentLabel } : {})}
                    onLabel={(l) => handleLabel(ep.episode_id, l)}
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
  categoryLabels,
  isDocente,
}: {
  episode: EpisodeToRate
  currentLabel?: AppropriationLabel
  onLabel: (l: AppropriationLabel) => void
  categoryLabels: Record<string, string>
  isDocente: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-xs text-muted">
            {isDocente ? episode.episode_id.slice(0, 8) : episode.episode_id.slice(0, 12)}
          </div>
          <p className="text-sm mt-1 line-clamp-2">{episode.summary}</p>
        </div>
        <div className="text-xs text-right shrink-0">
          <div className="text-muted">{isDocente ? "El sistema evaluo:" : "Modelo dijo:"}</div>
          <div className="font-medium">
            {categoryLabels[episode.classifier_label] ?? episode.classifier_label}
          </div>
        </div>
      </div>

      <div className="flex gap-2">
        {CATEGORIES.map((cat) => {
          const selected = currentLabel === cat
          return (
            <button
              key={cat}
              type="button"
              onClick={() => onLabel(cat)}
              className={`flex-1 px-3 py-2 rounded text-white text-xs font-medium transition ${CATEGORY_COLORS[cat]} ${
                selected ? "ring-2 ring-offset-2 ring-[#111111]" : "opacity-70"
              }`}
            >
              {categoryLabels[cat] ?? cat}
            </button>
          )
        })}
      </div>
    </div>
  )
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
          {CATEGORIES.map((c) => {
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
              {CATEGORIES.map((c) => (
                <th key={c} className="text-center py-2 font-medium text-xs px-2">
                  {APPROPRIATION_INVESTIGADOR[c] ?? c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CATEGORIES.map((row) => (
              <tr key={row} className="border-b border-border/50">
                <td className="py-2 pr-4 text-xs text-muted">
                  {APPROPRIATION_INVESTIGADOR[row] ?? row}
                </td>
                {CATEGORIES.map((col) => {
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
          {CATEGORIES.map((c) => {
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
