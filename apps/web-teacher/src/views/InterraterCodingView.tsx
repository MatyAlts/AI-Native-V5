import { PageContainer } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useState } from "react"
import {
  type AcademicContext,
  AcademicContextSelector,
} from "../components/AcademicContextSelector"
import {
  comisionesApi,
  getInterraterProgress,
  getInterraterSample,
  saveInterraterRating,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"
import { EpisodeProcessTrace, PROFILES } from "./interraterShared"

interface OrchestratorProps {
  getToken: () => Promise<string | null>
}

// El docente confirma que hizo el entrenamiento (sección Entrenamiento /
// Recalibración) con una casilla. Se recuerda por materia en localStorage.
const attestKey = (materiaId: string) => `interrater_attested_${materiaId}`

/**
 * Orquestador de la codificación inter-jueces, GLOBAL de materia:
 *   1. El docente elige una materia (AcademicContextSelector).
 *   2. Marca la casilla "Realicé el entrenamiento de recalibración".
 *   3. Codifica a ciegas el corpus con-tutor de la materia (los ~113 episodios).
 * El entrenamiento en sí vive en su propia sección (`/entrenamiento-recalibracion`).
 */
export function InterraterView({ getToken }: OrchestratorProps) {
  const [ctx, setCtx] = useState<AcademicContext | null>(null)
  const [attested, setAttested] = useState(false)

  useEffect(() => {
    if (!ctx) {
      setAttested(false)
      return
    }
    setAttested(localStorage.getItem(attestKey(ctx.materiaId)) === "1")
  }, [ctx])

  const handleAttest = useCallback(
    (value: boolean) => {
      if (!ctx) return
      if (value) localStorage.setItem(attestKey(ctx.materiaId), "1")
      else localStorage.removeItem(attestKey(ctx.materiaId))
      setAttested(value)
    },
    [ctx],
  )

  return (
    <PageContainer
      title="Codificación a ciegas (inter-jueces)"
      description="Elegí una materia, confirmá que hiciste el entrenamiento y codificá su corpus de episodios SIN ver la etiqueta de la máquina. Tu codificación se cruza con la de otros jueces y con el clasificador para computar κ."
      helpContent={helpContent.interraterCoding}
    >
      <div className="space-y-6 max-w-4xl">
        <AcademicContextSelector value={ctx} onChange={setCtx} getToken={getToken} />

        {!ctx && (
          <div className="rounded-xl border border-border bg-canvas px-6 py-8 text-center text-sm text-muted">
            Elegí una materia arriba para empezar.
          </div>
        )}

        {ctx && (
          <>
            <AttestCheckbox attested={attested} onChange={handleAttest} />
            {attested && <InterraterCoding materiaId={ctx.materiaId} getToken={getToken} />}
          </>
        )}
      </div>
    </PageContainer>
  )
}

function AttestCheckbox({
  attested,
  onChange,
}: {
  attested: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="rounded-xl border border-border bg-white px-6 py-4">
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={attested}
          onChange={(e) => onChange(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0"
        />
        <span className="text-sm">
          <strong>Realicé el entrenamiento de recalibración</strong> y voy a completar los
          episodios.
          <br />
          <span className="text-muted">
            ¿No lo hiciste todavía?{" "}
            <Link
              to="/entrenamiento-recalibracion"
              className="underline font-medium hover:opacity-80"
            >
              Ir al entrenamiento
            </Link>
            .
          </span>
        </span>
      </label>
    </div>
  )
}

interface CodingProps {
  materiaId: string
  getToken: () => Promise<string | null>
}

function InterraterCoding({ materiaId, getToken }: CodingProps) {
  const [episodes, setEpisodes] = useState<{ episode_id: string; comision_id: string }[]>([])
  const [coded, setCoded] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Materia → TODAS sus comisiones (mismo set para todos los codificadores).
      const comisiones = await comisionesApi.listByMateria(materiaId, getToken)
      const comisionIds = comisiones.map((c) => c.id)
      if (comisionIds.length === 0) {
        setEpisodes([])
        setCoded(new Set())
        return
      }
      const [sample, progress] = await Promise.all([
        getInterraterSample(comisionIds, getToken),
        getInterraterProgress(materiaId, getToken),
      ])
      setEpisodes(sample.episodes)
      setCoded(new Set(progress.rated_episode_ids))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [materiaId, getToken])

  useEffect(() => {
    void load()
  }, [load])

  const markCoded = useCallback((episodeId: string) => {
    setCoded((prev) => {
      const next = new Set(prev)
      next.add(episodeId)
      return next
    })
  }, [])

  const codedCount = useMemo(
    () => episodes.filter((e) => coded.has(e.episode_id)).length,
    [episodes, coded],
  )

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-canvas px-6 py-4 text-sm">
        <p className="font-semibold mb-1">Codificación a ciegas — corpus con tutor</p>
        <p className="text-muted">
          No se muestra la etiqueta del clasificador. Revisá la traza de cada episodio con "Ver
          proceso" y elegí el perfil. Podés re-etiquetar las veces que quieras.{" "}
          <Link
            to="/entrenamiento-recalibracion"
            className="underline font-medium hover:opacity-80"
          >
            Repasar el entrenamiento
          </Link>
          .
        </p>
      </div>

      {loading && <div className="text-sm text-muted">Cargando episodios de la materia…</div>}
      {error && <div className="p-3 rounded bg-danger-soft text-danger text-sm">{error}</div>}

      {!loading && !error && (
        <>
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div className="text-sm">
              <span className="font-medium">{codedCount}</span> de{" "}
              <span className="font-medium">{episodes.length}</span> codificados
            </div>
            <button
              type="button"
              onClick={() => void load()}
              className="px-3 py-1.5 text-sm border border-border rounded hover:bg-canvas"
            >
              Recargar
            </button>
          </div>

          {episodes.length === 0 && (
            <div className="text-sm text-muted">
              No hay episodios codificables en esta materia todavía.
            </div>
          )}

          <div className="space-y-3">
            {episodes.map((ep) => (
              <EpisodeCodingCard
                key={ep.episode_id}
                episodeId={ep.episode_id}
                comisionId={ep.comision_id}
                materiaId={materiaId}
                getToken={getToken}
                isCoded={coded.has(ep.episode_id)}
                onCoded={() => markCoded(ep.episode_id)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function EpisodeCodingCard({
  episodeId,
  comisionId,
  materiaId,
  getToken,
  isCoded,
  onCoded,
}: {
  episodeId: string
  comisionId: string
  materiaId: string
  getToken: () => Promise<string | null>
  isCoded: boolean
  onCoded: () => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showProcess, setShowProcess] = useState(false)

  const handleRate = async (label: string) => {
    setSaving(true)
    setSaveError(null)
    try {
      await saveInterraterRating(
        {
          episode_id: episodeId,
          comision_id: comisionId,
          materia_id: materiaId,
          label,
          protocol: "ejes",
        },
        getToken,
      )
      setSelected(label)
      onCoded()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className={`rounded-xl border bg-white p-4 transition-colors ${
        isCoded ? "border-green-300 bg-green-50/30" : "border-border"
      }`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="font-mono text-[11px] text-muted-soft uppercase tracking-wider">
          Episodio {episodeId.slice(0, 12)}
        </span>
        {isCoded && (
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-800">
            ✓ Codificado
          </span>
        )}
        <button
          type="button"
          onClick={() => setShowProcess((v) => !v)}
          className="ml-auto px-3 py-1 text-xs border border-border rounded hover:bg-canvas"
        >
          {showProcess ? "Ocultar proceso" : "Ver proceso"}
        </button>
      </div>

      {showProcess && (
        <div className="mb-4">
          <EpisodeProcessTrace episodeId={episodeId} getToken={getToken} />
        </div>
      )}

      <div>
        <div className="text-[11px] font-semibold text-muted mb-1.5 uppercase tracking-wider">
          ¿Cómo codificás este episodio?
        </div>
        <div className="flex flex-wrap gap-2">
          {PROFILES.map((p) => {
            const isSelected = selected === p.label
            return (
              <button
                key={p.label}
                type="button"
                disabled={saving}
                onClick={() => void handleRate(p.label)}
                className={`flex-1 min-w-[150px] px-3 py-2 rounded text-white text-xs font-medium transition disabled:opacity-50 ${p.color} ${
                  isSelected
                    ? "ring-2 ring-offset-2 ring-[#111111]"
                    : "opacity-70 hover:opacity-100"
                }`}
              >
                {p.display}
              </button>
            )
          })}
        </div>
        {saving && <p className="mt-2 text-xs text-muted">Guardando…</p>}
        {saveError && <p className="mt-2 text-xs text-danger">No se pudo guardar: {saveError}</p>}
      </div>
    </div>
  )
}
