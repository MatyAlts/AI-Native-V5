/**
 * Vista "Uso de IA" (F11) — read-only para el docente.
 *
 * Muestra, para las BYOK keys visibles al docente, el uso y costo agregado por
 * periodo (tokens in/out, costo USD, requests). Es SOLO LECTURA: no crea, edita
 * ni revoca keys — eso vive en web-admin (rol admin). Aca el docente audita el
 * consumo de IA de sus materias/comisiones.
 *
 * Backend:
 *   GET /api/v1/byok/keys                     -> lista de keys del tenant (metadata,
 *                                                sin plaintext; incluye fingerprint_last4)
 *   GET /api/v1/byok/keys/{id}/usage?yyyymm=  -> agregado del mes (tokens/costo/requests).
 *                                                Stub-friendly: key sin uso -> 0s (no falla).
 *
 * Datos: TanStack Query. `["byok-keys"]` para la lista (key estable, se comparte
 * si otra vista la pide) + `["byok-usage", keyId, yyyymm]` por key/periodo. Una
 * key de usage que falla degrada esa card sin tumbar la vista.
 *
 * NOTA/RIESGO: `apps/ai-gateway/.../routes/byok.py` gatea TODOS los endpoints
 * BYOK (incluido GET /keys y /usage) tras `_check_admin` con
 * `_ADMIN_ROLES = {superadmin, docente_admin}` — un rol `docente` plano recibe
 * 403. En dev el proxy de web-teacher inyecta `x-user-roles: docente`, asi que
 * esta vista mostrara su estado de error (403) hasta que el backend habilite el
 * scope de lectura para el docente (o el docente tenga docente_admin). El
 * estado de error del DS surfacea esto de forma legible.
 */
import { Badge, HelpButton, KpiCard, Section, StateMessage } from "@platform/ui"
import { useQueries, useQuery } from "@tanstack/react-query"
import { Coins, Cpu, KeyRound } from "lucide-react"
import { useState } from "react"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
}

// ── Contratos del ai-gateway (KeyOut / UsageOut de routes/byok.py) ──────
interface ByokKey {
  id: string
  tenant_id: string
  scope_type: string
  scope_id: string | null
  provider: string
  fingerprint_last4: string
  monthly_budget_usd: number | null
  created_at: string
  created_by: string
  revoked_at: string | null
  last_used_at: string | null
}

interface ByokUsage {
  key_id: string
  yyyymm: string
  tokens_input_total: number
  tokens_output_total: number
  cost_usd_total: number
  request_count: number
}

// ── Fetch inline (api.ts es off-limits en este cambio; replicamos el minimo
//    de authHeaders/throwIfNotOk del API layer, igual que recalificarEntrega en
//    CorreccionesView). FOLLOW-UP: mover a `byokUsageApi` en lib/api.ts. ──────
async function fetchJson<T>(url: string, getToken: () => Promise<string | null>): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const token = await getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const r = await fetch(url, { headers })
  if (!r.ok) {
    const raw = await r.text()
    let detail = raw
    try {
      const parsed = JSON.parse(raw)
      detail = parsed.detail ?? parsed.title ?? raw
    } catch {
      /* respuesta no-JSON: usamos el texto crudo */
    }
    throw new Error(`${r.status}: ${detail}`)
  }
  return (await r.json()) as T
}

const listByokKeys = (getToken: () => Promise<string | null>) =>
  fetchJson<ByokKey[]>("/api/v1/byok/keys", getToken)

const getByokKeyUsage = (keyId: string, yyyymm: string, getToken: () => Promise<string | null>) =>
  fetchJson<ByokUsage>(`/api/v1/byok/keys/${keyId}/usage?yyyymm=${yyyymm}`, getToken)

// ── Helpers de presentacion ─────────────────────────────────────────────
const PROVIDER_LABEL: Record<string, string> = {
  anthropic: "Anthropic",
  gemini: "Gemini",
  mistral: "Mistral",
  openai: "OpenAI",
  openrouter: "OpenRouter",
}

const SCOPE_LABEL: Record<string, string> = {
  tenant: "Tenant",
  facultad: "Facultad",
  materia: "Materia",
}

const numberFmt = new Intl.NumberFormat("es-AR")

function fmtTokens(n: number): string {
  return numberFmt.format(n)
}

function fmtCost(n: number): string {
  return `$${n.toFixed(n > 0 && n < 1 ? 4 : 2)}`
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  const t = Date.parse(iso)
  return Number.isFinite(t) ? new Date(t).toLocaleDateString("es-AR") : "—"
}

/** Ultimos `count` meses en formato { value: "YYYYMM", label: "julio de 2026" }. */
function monthOptions(count = 6): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = []
  const now = new Date()
  for (let i = 0; i < count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const value = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`
    const label = d.toLocaleDateString("es-AR", { month: "long", year: "numeric" })
    out.push({ value, label })
  }
  return out
}

export function UsoIAView({ getToken }: Props) {
  const months = monthOptions()
  const [yyyymm, setYyyymm] = useState<string>(months[0]?.value ?? "")

  // Lista de keys visibles al docente. Key estable -> cache compartido.
  const keysQuery = useQuery({
    queryKey: ["byok-keys"],
    queryFn: () => listByokKeys(getToken),
  })
  const keys = keysQuery.data ?? []

  // Usage por (key, periodo). Independiente por card: una que falla no tumba
  // la vista. Se refetchea al cambiar el periodo (yyyymm entra en la key).
  const usageQueries = useQueries({
    queries: keys.map((k) => ({
      queryKey: ["byok-usage", k.id, yyyymm],
      queryFn: () => getByokKeyUsage(k.id, yyyymm, getToken),
    })),
  })

  const loading = keysQuery.isLoading
  const error = keysQuery.error ? String(keysQuery.error) : null

  // Agregados del periodo (best-effort: suma lo que resolvio).
  const resolved = usageQueries.map((q) => q.data).filter((u): u is ByokUsage => !!u)
  const totalIn = resolved.reduce((s, u) => s + u.tokens_input_total, 0)
  const totalOut = resolved.reduce((s, u) => s + u.tokens_output_total, 0)
  const totalCost = resolved.reduce((s, u) => s + u.cost_usd_total, 0)
  const totalReq = resolved.reduce((s, u) => s + u.request_count, 0)
  const aggregatePending = keys.length > 0 && usageQueries.some((q) => q.isLoading)

  return (
    <div className="page-enter space-y-10 max-w-7xl mx-auto p-6">
      {/* ═══ HERO ═════════════════════════════════════════════════════ */}
      <header className="flex items-start justify-between gap-6 animate-fade-in-down">
        <div className="flex flex-col gap-1.5 min-w-0">
          <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted">
            Panel docente · IA
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-ink leading-none">Uso de IA</h1>
          <p className="text-sm text-muted leading-relaxed mt-1.5 max-w-xl">
            Consumo de las claves de IA (BYOK) visibles para vos — tokens, costo y requests por
            periodo. Solo lectura: la gestion de claves vive en administracion.
          </p>
        </div>
        <HelpButton title="Uso de IA" content={helpContent.usoIa} />
      </header>

      {/* ═══ CONTROLES: periodo ═══════════════════════════════════════ */}
      <div className="flex items-center gap-3 animate-fade-in">
        <label
          htmlFor="uso-ia-periodo"
          className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted"
        >
          Periodo
        </label>
        <select
          id="uso-ia-periodo"
          value={yyyymm}
          onChange={(e) => setYyyymm(e.target.value)}
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-ink capitalize focus:outline-none focus:ring-2 focus:ring-accent-brand/40"
        >
          {months.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {/* ═══ STATS AGREGADAS ══════════════════════════════════════════ */}
      {!loading && !error && keys.length > 0 && (
        <section
          className="grid grid-cols-2 md:grid-cols-4 gap-3 animate-fade-in-up animate-delay-100"
          aria-label="Resumen agregado de uso de IA"
        >
          <KpiCard
            label="Tokens entrada"
            value={aggregatePending ? "…" : fmtTokens(totalIn)}
            hint="Suma del periodo"
          />
          <KpiCard
            label="Tokens salida"
            value={aggregatePending ? "…" : fmtTokens(totalOut)}
            hint="Suma del periodo"
          />
          <KpiCard
            label="Costo estimado"
            value={aggregatePending ? "…" : fmtCost(totalCost)}
            hint="USD del periodo"
            tone="brand"
          />
          <KpiCard
            label="Requests"
            value={aggregatePending ? "…" : fmtTokens(totalReq)}
            hint="Llamadas al proveedor"
          />
        </section>
      )}

      {/* ═══ LOADING ══════════════════════════════════════════════════ */}
      {loading && (
        <div className="space-y-4 animate-fade-in">
          <div className="skeleton h-24 rounded-2xl" />
          <div className="skeleton h-40 rounded-xl" />
          <div className="skeleton h-40 rounded-xl" />
        </div>
      )}

      {/* ═══ ERROR ════════════════════════════════════════════════════ */}
      {error && (
        <StateMessage variant="error" title="No pudimos cargar el uso de IA" description={error} />
      )}

      {/* ═══ EMPTY ════════════════════════════════════════════════════ */}
      {!loading && !error && keys.length === 0 && (
        <StateMessage
          variant="empty"
          title="No hay claves de IA visibles"
          description="No tenes claves BYOK asignadas a tus materias o comisiones. Pedile al admin de tu facultad que configure una clave de proveedor desde web-admin."
        />
      )}

      {/* ═══ LISTA DE KEYS ════════════════════════════════════════════ */}
      {!loading && !error && keys.length > 0 && (
        <Section title="Claves visibles" eyebrow={`${keys.length} clave(s)`}>
          <ul className="space-y-4">
            {keys.map((k, i) => {
              const q = usageQueries[i]
              const usage = q?.data
              const usageError = q?.error ? String(q.error) : null
              const revoked = !!k.revoked_at
              return (
                <li
                  key={k.id}
                  className="rounded-xl border border-border bg-surface p-5 animate-fade-in-up"
                  style={{ animationDelay: `${100 + i * 40}ms` }}
                >
                  {/* Cabecera de la key */}
                  <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
                    <div className="flex items-start gap-3 min-w-0">
                      <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-accent-brand-soft text-accent-brand-deep shrink-0">
                        <Cpu className="h-4 w-4" />
                      </span>
                      <div className="flex flex-col gap-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-ink">
                            {PROVIDER_LABEL[k.provider] ?? k.provider}
                          </span>
                          <Badge variant="info">{SCOPE_LABEL[k.scope_type] ?? k.scope_type}</Badge>
                          {revoked && <Badge variant="danger">Revocada</Badge>}
                        </div>
                        <span className="inline-flex items-center gap-1.5 font-mono text-xs text-muted">
                          <KeyRound className="h-3 w-3" />
                          ····{k.fingerprint_last4}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-0.5 text-xs text-muted">
                      <span>Ultimo uso: {fmtDate(k.last_used_at)}</span>
                      {k.monthly_budget_usd !== null && (
                        <span className="inline-flex items-center gap-1">
                          <Coins className="h-3 w-3" />
                          Presupuesto: {fmtCost(k.monthly_budget_usd)}/mes
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Usage del periodo */}
                  {q?.isLoading && (
                    <StateMessage variant="loading" title="Cargando uso del periodo..." />
                  )}
                  {usageError && (
                    <StateMessage
                      variant="error"
                      title="No pudimos cargar el uso de esta clave"
                      description={usageError}
                    />
                  )}
                  {usage && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <KpiCard label="Tokens entrada" value={fmtTokens(usage.tokens_input_total)} />
                      <KpiCard label="Tokens salida" value={fmtTokens(usage.tokens_output_total)} />
                      <KpiCard
                        label="Costo"
                        value={fmtCost(usage.cost_usd_total)}
                        hint="USD"
                        tone="brand"
                      />
                      <KpiCard label="Requests" value={fmtTokens(usage.request_count)} />
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </Section>
      )}
    </div>
  )
}
