import { PageContainer } from "@platform/ui"
import { useState } from "react"
import { getInterraterAggregate, type InterraterAggregate, type InterraterPair } from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

const short = (id: string) => id.slice(0, 8)

export function InterraterAdminView({ comisionId, getToken }: Props) {
  const [data, setData] = useState<InterraterAggregate | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCompute = async () => {
    setLoading(true)
    setError(null)
    try {
      const d = await getInterraterAggregate(comisionId, "ejes", getToken)
      setData(d)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <PageContainer
      title="Acuerdo κ inter-jueces (admin)"
      description="Acuerdo agregado entre los docentes que codificaron a ciegas, y entre el clasificador y cada docente. Protocolo de 3 ejes."
      helpContent={helpContent.interraterAdmin}
    >
      <div className="space-y-6 max-w-5xl">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="text-sm text-muted">
            Comisión <span className="font-mono text-ink">{short(comisionId)}</span>
          </div>
          <button
            type="button"
            onClick={() => void handleCompute()}
            disabled={loading}
            className="px-4 py-1.5 text-sm bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border disabled:text-muted text-white rounded font-medium"
          >
            {loading ? "Calculando…" : "Calcular acuerdo"}
          </button>
        </div>

        {error && <div className="p-3 rounded bg-danger-soft text-danger text-sm">{error}</div>}

        {data && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <StatCard label="Codificadores (raters)" value={data.n_raters} />
              <StatCard label="Episodios codificados" value={data.n_episodes_codificados} />
            </div>

            <DistributionPanel distribution={data.distribution} />

            <PairsTable
              title="Profe vs Profe"
              subtitle="Acuerdo entre docentes (humano–humano)"
              pairs={data.pares_humano_humano}
            />
            <PairsTable
              title="Máquina vs Profe"
              subtitle="Acuerdo entre clasificador y cada docente"
              pairs={data.pares_maquina_humano}
            />
          </div>
        )}
      </div>
    </PageContainer>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <div className="text-xs text-muted uppercase tracking-wider">{label}</div>
      <div className="text-3xl font-semibold mt-1 text-ink">{value}</div>
    </div>
  )
}

function DistributionPanel({ distribution }: { distribution: Record<string, number> }) {
  const entries = Object.entries(distribution)
  const total = entries.reduce((acc, [, v]) => acc + v, 0)

  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <h3 className="font-medium mb-3 text-sm">Distribución de etiquetas</h3>
      {entries.length === 0 ? (
        <p className="text-xs text-muted">Sin codificaciones todavía.</p>
      ) : (
        <div className="space-y-2">
          {entries.map(([label, count]) => {
            const pct = total > 0 ? (count / total) * 100 : 0
            return (
              <div key={label} className="flex items-center gap-3">
                <div className="min-w-[200px] text-sm">{label}</div>
                <div className="flex-1 h-3 bg-border rounded overflow-hidden">
                  <div
                    className="h-full bg-accent-brand rounded"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="text-xs text-muted min-w-[70px] text-right">
                  {count} ({pct.toFixed(0)}%)
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function PairsTable({
  title,
  subtitle,
  pairs,
}: {
  title: string
  subtitle: string
  pairs: InterraterPair[]
}) {
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <h3 className="font-medium text-sm">{title}</h3>
      <p className="text-xs text-muted mb-3">{subtitle}</p>
      {pairs.length === 0 ? (
        <p className="text-xs text-muted">Sin pares con episodios en común.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted uppercase">
              <th className="text-left py-2 font-medium">Rater A</th>
              <th className="text-left py-2 font-medium">Rater B</th>
              <th className="text-center py-2 font-medium">Episodios</th>
              <th className="text-center py-2 font-medium">κ</th>
              <th className="text-left py-2 font-medium pl-4">Interpretación</th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((p) => {
              const goodKappa = p.kappa !== null && p.kappa >= 0.7
              return (
                <tr
                  key={`${p.rater_a}-${p.rater_b}`}
                  className="border-b border-border/50"
                >
                  <td className="py-2 font-mono text-xs">{short(p.rater_a)}</td>
                  <td className="py-2 font-mono text-xs">{short(p.rater_b)}</td>
                  <td className="py-2 text-center">{p.n_episodes}</td>
                  <td className="py-2 text-center">
                    {p.kappa === null ? (
                      <span className="text-muted">—</span>
                    ) : (
                      <span
                        className={`font-semibold px-2 py-0.5 rounded ${
                          goodKappa
                            ? "bg-green-100 text-green-800"
                            : "bg-danger-soft text-danger"
                        }`}
                      >
                        {p.kappa.toFixed(3)}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pl-4 text-xs text-muted">{p.interpretation ?? "—"}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
