import { HelpButton, Modal, PageContainer } from "@platform/ui"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Key } from "lucide-react"
import { type ReactNode, useState } from "react"
import {
  type ByokKey,
  type ByokKeyCreate,
  HttpError,
  byokApi,
  facultadesApi,
  materiasApi,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

type ModalState =
  | { type: "none" }
  | { type: "create" }
  | { type: "rotate"; key: ByokKey }
  | { type: "revoke"; key: ByokKey }
  | { type: "usage"; key: ByokKey }

const inputClass =
  "w-full rounded-md border border-border px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-brand"

function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: ReactNode
}): ReactNode {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: children es el control wrappeado por el padre
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-body">
        {label}
        {required && <span className="text-danger ml-0.5">*</span>}
      </span>
      {children}
    </label>
  )
}

export function ByokPage(): ReactNode {
  const [scopeTypeFilter, setScopeTypeFilter] = useState<string>("")
  const [modal, setModal] = useState<ModalState>({ type: "none" })
  const queryClient = useQueryClient()

  const keysQuery = useQuery({
    queryKey: ["byok-keys", { scope_type: scopeTypeFilter }],
    queryFn: () => byokApi.list(scopeTypeFilter ? { scope_type: scopeTypeFilter } : undefined),
  })

  const revokeMutation = useMutation({
    mutationFn: (id: string) => byokApi.revoke(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["byok-keys"] })
      setModal({ type: "none" })
    },
  })

  const keys: ByokKey[] = keysQuery.data ?? []

  const errorMsg = keysQuery.error
    ? keysQuery.error instanceof HttpError
      ? `${keysQuery.error.status}: ${keysQuery.error.detail || keysQuery.error.title}`
      : String(keysQuery.error)
    : null

  return (
    <PageContainer
      title="BYOK Keys"
      eyebrow="Inicio · BYOK Keys"
      description="Gestion de claves de proveedor LLM por tenant o materia (Bring Your Own Key)."
      helpContent={helpContent.byok}
    >
      <div className="space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <label htmlFor="scope-filter" className="text-sm font-medium text-body">
              Filtrar por scope:
            </label>
            <select
              id="scope-filter"
              value={scopeTypeFilter}
              onChange={(e) => setScopeTypeFilter(e.target.value)}
              className="rounded-md border border-border px-3 py-1.5 text-sm"
            >
              <option value="">Todos</option>
              <option value="tenant">Tenant</option>
              <option value="materia">Materia</option>
              <option value="facultad">Facultad</option>
            </select>
          </div>
          <button
            type="button"
            onClick={() => setModal({ type: "create" })}
            className="flex items-center gap-1.5 rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep"
          >
            <Key size={14} />
            Nueva key
          </button>
        </div>

        {errorMsg && (
          <div className="rounded-md border border-danger/40 bg-danger-soft p-4 text-sm text-danger">
            {errorMsg}
          </div>
        )}

        <div className="rounded-lg border border-border-soft bg-surface overflow-hidden">
          {keysQuery.isLoading ? (
            <div className="p-8 text-center text-muted text-sm">Cargando...</div>
          ) : keys.length === 0 ? (
            <div className="p-8 text-center text-muted text-sm">
              <div className="flex flex-col items-center gap-3">
                <Key size={32} className="text-muted-soft" />
                <p className="font-medium">No hay BYOK keys configuradas</p>
                <p className="text-xs text-muted-soft">
                  Crea una key para que el ai-gateway use tu propia clave de proveedor LLM.
                </p>
                <button
                  type="button"
                  onClick={() => setModal({ type: "create" })}
                  className="mt-1 rounded-md bg-accent-brand text-white px-4 py-1.5 text-sm hover:bg-accent-brand-deep"
                >
                  Crear primera key
                </button>
              </div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-surface-alt border-b border-border-soft text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">Scope</th>
                  <th className="px-4 py-2 font-medium">Scope ID</th>
                  <th className="px-4 py-2 font-medium">Provider</th>
                  <th className="px-4 py-2 font-medium">Fingerprint</th>
                  <th className="px-4 py-2 font-medium">Budget (USD/mes)</th>
                  <th className="px-4 py-2 font-medium">Estado</th>
                  <th className="px-4 py-2 font-medium">Creada</th>
                  <th className="px-4 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id} className="border-b border-border-soft hover:bg-surface-alt">
                    <td className="px-4 py-2 font-mono text-xs">{k.scope_type}</td>
                    <td className="px-4 py-2 font-mono text-xs text-muted">
                      {k.scope_id ? `${k.scope_id.slice(0, 8)}…` : "—"}
                    </td>
                    <td className="px-4 py-2 font-medium">{k.provider}</td>
                    <td className="px-4 py-2 font-mono text-xs">…{k.fingerprint_last4}</td>
                    <td className="px-4 py-2 text-xs">
                      {k.monthly_budget_usd !== null ? `$${k.monthly_budget_usd}` : "—"}
                    </td>
                    <td className="px-4 py-2">
                      {k.revoked_at ? (
                        <span className="rounded-full bg-danger-soft text-danger px-2 py-0.5 text-xs">
                          Revocada
                        </span>
                      ) : (
                        <span className="rounded-full bg-success-soft text-success px-2 py-0.5 text-xs">
                          Activa
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-xs text-muted">
                      {new Date(k.created_at).toLocaleDateString("es-AR")}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setModal({ type: "usage", key: k })}
                          className="text-xs text-accent-brand-deep hover:text-accent-brand-deep"
                        >
                          Uso
                        </button>
                        {!k.revoked_at && (
                          <>
                            <button
                              type="button"
                              onClick={() => setModal({ type: "rotate", key: k })}
                              className="text-xs text-warning/85 hover:text-warning"
                            >
                              Rotar
                            </button>
                            <button
                              type="button"
                              onClick={() => setModal({ type: "revoke", key: k })}
                              className="text-xs text-danger hover:text-danger"
                            >
                              Revocar
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {modal.type === "create" && (
        <CreateKeyModal
          onClose={() => setModal({ type: "none" })}
          onCreated={() => {
            void queryClient.invalidateQueries({ queryKey: ["byok-keys"] })
            setModal({ type: "none" })
          }}
        />
      )}

      {modal.type === "rotate" && (
        <RotateKeyModal
          byokKey={modal.key}
          onClose={() => setModal({ type: "none" })}
          onRotated={() => {
            void queryClient.invalidateQueries({ queryKey: ["byok-keys"] })
            setModal({ type: "none" })
          }}
        />
      )}

      {modal.type === "revoke" && (
        <Modal
          isOpen
          onClose={() => setModal({ type: "none" })}
          title="Revocar BYOK key"
          size="sm"
        >
          <div className="space-y-4">
            <p className="text-sm text-body">
              Esta accion es <strong>irreversible</strong>. La key con fingerprint{" "}
              <code className="font-mono bg-surface-alt px-1 rounded">
                …{modal.key.fingerprint_last4}
              </code>{" "}
              ({modal.key.provider} / {modal.key.scope_type}) quedara revocada y el ai-gateway no
              podra usarla.
            </p>
            {revokeMutation.error && (
              <div className="rounded-md border border-danger/40 bg-danger-soft p-3 text-xs text-danger">
                {revokeMutation.error instanceof HttpError
                  ? revokeMutation.error.detail || revokeMutation.error.title
                  : String(revokeMutation.error)}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModal({ type: "none" })}
                className="rounded-md border border-border px-4 py-2 text-sm hover:bg-surface-alt"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => revokeMutation.mutate(modal.key.id)}
                disabled={revokeMutation.isPending}
                className="rounded-md bg-danger text-white px-4 py-2 text-sm font-medium hover:bg-danger disabled:opacity-50"
              >
                {revokeMutation.isPending ? "Revocando..." : "Revocar key"}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {modal.type === "usage" && (
        <UsagePanel
          byokKey={modal.key}
          onClose={() => setModal({ type: "none" })}
        />
      )}
    </PageContainer>
  )
}

function CreateKeyModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}): ReactNode {
  const [form, setForm] = useState<ByokKeyCreate>({
    scope_type: "tenant",
    provider: "anthropic",
    plaintext_value: "",
  })
  const [error, setError] = useState<string | null>(null)

  const facultadesQuery = useQuery({
    queryKey: ["facultades"],
    queryFn: () => facultadesApi.list(),
    enabled: form.scope_type === "facultad",
  })
  const materiasQuery = useQuery({
    queryKey: ["materias"],
    queryFn: () => materiasApi.list(),
    enabled: form.scope_type === "materia",
  })

  const createMutation = useMutation({
    mutationFn: (data: ByokKeyCreate) => byokApi.create(data),
    onSuccess: onCreated,
    onError: (err) => {
      setError(
        err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err),
      )
    },
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    createMutation.mutate(form)
  }

  return (
    <Modal isOpen onClose={onClose} title="Nueva BYOK key" size="lg">
      <form onSubmit={submit} className="space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <HelpButton
            size="sm"
            title="Crear BYOK key"
            content={
              <div className="space-y-2 text-muted-soft text-sm">
                <p>
                  <strong>Scope type:</strong> tenant aplica a toda la universidad; materia solo a
                  esa materia (resolver usa materia primero).
                </p>
                <p>
                  <strong>Scope ID:</strong> UUID de la materia o facultad. Dejar vacio para scope
                  tenant.
                </p>
                <p>
                  <strong>Plaintext value:</strong> La API key del proveedor. Se encripta con
                  AES-256-GCM y nunca se devuelve en claro.
                </p>
              </div>
            }
          />
          <span className="text-sm text-muted">Completa los campos de la nueva key</span>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Scope type" required>
            <select
              value={form.scope_type}
              onChange={(e) => {
                const next = { ...form, scope_type: e.target.value as ByokKeyCreate["scope_type"] }
                delete next.scope_id
                setForm(next)
              }}
              className={inputClass}
            >
              <option value="tenant">Tenant</option>
              <option value="materia">Materia</option>
              <option value="facultad">Facultad</option>
            </select>
          </Field>

          <Field label={form.scope_type === "facultad" ? "Facultad" : form.scope_type === "materia" ? "Materia" : "Scope"}>
            {form.scope_type === "tenant" ? (
              <select disabled className={inputClass}>
                <option>— Aplica a todo el tenant —</option>
              </select>
            ) : (
              <select
                value={form.scope_id ?? ""}
                onChange={(e) => {
                  const next = { ...form }
                  if (e.target.value) {
                    next.scope_id = e.target.value
                  } else {
                    delete next.scope_id
                  }
                  setForm(next)
                }}
                className={inputClass}
              >
                <option value="">Seleccionar...</option>
                {form.scope_type === "facultad" &&
                  (facultadesQuery.data?.data ?? []).map((f) => (
                    <option key={f.id} value={f.id}>{f.nombre} ({f.codigo})</option>
                  ))}
                {form.scope_type === "materia" &&
                  (materiasQuery.data?.data ?? []).map((m) => (
                    <option key={m.id} value={m.id}>{m.nombre} ({m.codigo})</option>
                  ))}
              </select>
            )}
          </Field>

          <Field label="Provider" required>
            <select
              value={form.provider}
              onChange={(e) =>
                setForm({ ...form, provider: e.target.value as ByokKeyCreate["provider"] })
              }
              className={inputClass}
            >
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="mistral">Mistral</option>
            </select>
          </Field>

          <Field label="Budget mensual (USD)">
            <input
              type="number"
              step="0.01"
              min={0}
              value={form.monthly_budget_usd ?? ""}
              onChange={(e) => {
                const next = { ...form }
                if (e.target.value) {
                  next.monthly_budget_usd = Number(e.target.value)
                } else {
                  delete next.monthly_budget_usd
                }
                setForm(next)
              }}
              placeholder="Sin limite"
              className={inputClass}
            />
          </Field>

          <div className="col-span-2">
            <Field label="API Key (plaintext)" required>
              <input
                type="password"
                value={form.plaintext_value}
                onChange={(e) => setForm({ ...form, plaintext_value: e.target.value })}
                required
                minLength={8}
                placeholder="sk-ant-..."
                className={inputClass}
              />
            </Field>
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-danger/40 bg-danger-soft p-3 text-xs text-danger">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-4 py-2 text-sm hover:bg-surface-alt"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded-md bg-accent-brand text-white px-4 py-2 text-sm font-medium hover:bg-accent-brand-deep disabled:opacity-50"
          >
            {createMutation.isPending ? "Creando..." : "Crear key"}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function RotateKeyModal({
  byokKey,
  onClose,
  onRotated,
}: {
  byokKey: ByokKey
  onClose: () => void
  onRotated: () => void
}): ReactNode {
  const [plaintext, setPlaintext] = useState("")
  const [error, setError] = useState<string | null>(null)

  const rotateMutation = useMutation({
    mutationFn: () => byokApi.rotate(byokKey.id, plaintext),
    onSuccess: onRotated,
    onError: (err) => {
      setError(
        err instanceof HttpError ? `${err.status}: ${err.detail || err.title}` : String(err),
      )
    },
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    rotateMutation.mutate()
  }

  return (
    <Modal isOpen onClose={onClose} title="Rotar BYOK key" size="md">
      <form onSubmit={submit} className="space-y-4">
        <div className="rounded-md bg-surface-alt border border-border-soft p-3 text-sm">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <span className="text-muted">Provider:</span>
            <span className="font-medium">{byokKey.provider}</span>
            <span className="text-muted">Fingerprint actual:</span>
            <code className="font-mono">…{byokKey.fingerprint_last4}</code>
            <span className="text-muted">Scope:</span>
            <span>{byokKey.scope_type}</span>
          </div>
        </div>

        <Field label="Nueva API Key (plaintext)" required>
          <input
            type="password"
            value={plaintext}
            onChange={(e) => setPlaintext(e.target.value)}
            required
            minLength={8}
            placeholder="sk-ant-..."
            className={inputClass}
          />
        </Field>

        {error && (
          <div className="rounded-md border border-danger/40 bg-danger-soft p-3 text-xs text-danger">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-4 py-2 text-sm hover:bg-surface-alt"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={rotateMutation.isPending || !plaintext}
            className="rounded-md bg-warning text-white px-4 py-2 text-sm font-medium hover:bg-warning disabled:opacity-50"
          >
            {rotateMutation.isPending ? "Rotando..." : "Rotar key"}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function UsagePanel({
  byokKey,
  onClose,
}: {
  byokKey: ByokKey
  onClose: () => void
}): ReactNode {
  const usageQuery = useQuery({
    queryKey: ["byok-usage", byokKey.id],
    queryFn: () => byokApi.usage(byokKey.id),
  })

  // Backend devuelve single object con el agregado mensual (default mes actual).
  // Si nunca se usó la key, devuelve `{request_count: 0, ..._total: 0}` (no 404).
  const usage = usageQuery.data
  const isEmpty = !usage || usage.request_count === 0

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={`Uso de key …${byokKey.fingerprint_last4} (${byokKey.provider})`}
      size="lg"
    >
      <div className="space-y-4">
        {usageQuery.isLoading ? (
          <div className="text-center text-muted text-sm py-8">Cargando...</div>
        ) : isEmpty ? (
          <div className="rounded-lg border border-border-soft bg-surface-alt/40 p-6 text-center">
            <p className="text-sm font-medium text-body mb-1">Sin uso registrado este mes</p>
            <p className="text-xs text-muted leading-relaxed max-w-sm mx-auto">
              Esta key no fue resuelta por ningún call de IA en {usage?.yyyymm ?? "el período actual"}.
              El contador se incrementa cuando docente o alumno disparan completions
              con materia/facultad/tenant que matchean el scope de la key.
            </p>
          </div>
        ) : (
          <>
            {/* Stats header con cifras grandes */}
            <div className="grid grid-cols-4 gap-3">
              <div className="rounded-lg border border-border-soft bg-surface p-3">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-muted">
                  Período
                </div>
                <div className="font-mono text-base font-semibold text-ink mt-1">
                  {usage.yyyymm.slice(0, 4)}-{usage.yyyymm.slice(4)}
                </div>
              </div>
              <div className="rounded-lg border border-accent-brand/30 bg-accent-brand-soft/40 p-3">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-muted">
                  Requests
                </div>
                <div className="font-mono text-2xl font-semibold text-accent-brand-deep leading-none mt-1">
                  {usage.request_count.toLocaleString()}
                </div>
              </div>
              <div className="rounded-lg border border-border-soft bg-surface p-3">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-muted">
                  Tokens (in / out)
                </div>
                <div className="font-mono text-base font-semibold text-ink leading-none mt-1">
                  {usage.tokens_input_total.toLocaleString()}
                  <span className="text-muted-soft mx-1">/</span>
                  {usage.tokens_output_total.toLocaleString()}
                </div>
              </div>
              <div className="rounded-lg border border-success/30 bg-success-soft/40 p-3">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-muted">
                  Costo USD
                </div>
                <div className="font-mono text-2xl font-semibold text-success leading-none mt-1">
                  ${usage.cost_usd_total.toFixed(4)}
                </div>
              </div>
            </div>
            <p className="text-xs text-muted leading-relaxed">
              Agregado del mes actual. Para historial multi-mes (deuda v1.1) hay que
              llamar al endpoint con <code className="font-mono text-[11px] bg-surface-alt px-1 rounded">?yyyymm=</code>.
            </p>
          </>
        )}
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-4 py-2 text-sm hover:bg-surface-alt"
          >
            Cerrar
          </button>
        </div>
      </div>
    </Modal>
  )
}
