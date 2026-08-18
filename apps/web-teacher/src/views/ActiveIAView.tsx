/**
 * Vista de la integracion con Active-IA (Epic 2 de `correccion-activeia`).
 *
 * Dos cosas:
 *  - Conectar / desconectar la cuenta de Active-IA del docente.
 *  - Ver, por TP, el estado de sincronizacion de la rubrica de cada ejercicio.
 *
 * La cuenta es POR DOCENTE y no de la institucion: del lado de Active-IA los
 * `comision_id` y `rubrica_id` salen de la cuenta logueada, asi que cada tutor
 * ve solo sus comisiones.
 *
 * Convenciones:
 *  - useCallback para las fetchFns que van a deps de useEffect
 *  - Texto en espanol SIN tildes (encoding gotcha cp1252)
 */
import { PageContainer } from "@platform/ui"
import { AlertTriangle, Link2, Link2Off, RefreshCw } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import {
  type ActiveIACredencialEstado,
  type EjercicioSync,
  type EstadoSyncEjercicio,
  type SincronizacionTP,
  type TareaPractica,
  conectarActiveIA,
  desconectarActiveIA,
  getActiveIACredencial,
  getSincronizacionTP,
  listTareasPracticas,
  sincronizarTP,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

/**
 * Como se rotula cada estado.
 *
 * "Sin rubrica" NO es un error de sincronizacion: es que el ejercicio no tiene
 * rubrica local, o sea que no hay nada contra que corregir. Mezclarlo con
 * "sin sincronizar" haria que el docente busque el problema donde no esta.
 */
const ESTADO_UI: Record<EstadoSyncEjercicio, { label: string; clase: string }> = {
  sincronizado: { label: "Sincronizado", clase: "bg-success-soft text-success" },
  desactualizado: { label: "Desactualizado", clase: "bg-warning-soft text-warning" },
  sin_sincronizar: { label: "Sin sincronizar", clase: "bg-surface-alt text-body" },
  sin_rubrica: { label: "Sin rubrica", clase: "bg-surface-alt text-muted" },
}

/**
 * El backend tipa `estado` como string, asi que un valor nuevo del enum
 * llegaria aca sin que TypeScript lo frene. Sin fallback, `ESTADO_UI[x]` seria
 * `undefined` y la tabla entera se cae con pantalla blanca — un estado
 * desconocido tiene que degradar a "no se", no a una pagina rota.
 */
function estadoUI(estado: EstadoSyncEjercicio): { label: string; clase: string } {
  return ESTADO_UI[estado] ?? { label: estado, clase: "bg-surface-alt text-muted" }
}

export function ActiveIAView({ comisionId, getToken }: Props) {
  const [cred, setCred] = useState<ActiveIACredencialEstado | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [conectando, setConectando] = useState(false)

  const [tareas, setTareas] = useState<TareaPractica[]>([])
  const [tpSeleccionada, setTpSeleccionada] = useState<string>("")
  const [sync, setSync] = useState<SincronizacionTP | null>(null)
  const [sincronizando, setSincronizando] = useState(false)

  const fetchCred = useCallback(() => getActiveIACredencial(getToken), [getToken])
  const fetchTareas = useCallback(
    () => listTareasPracticas({ comision_id: comisionId }, getToken),
    [comisionId, getToken],
  )

  useEffect(() => {
    let cancelado = false
    setCargando(true)
    Promise.all([fetchCred(), fetchTareas()])
      .then(([c, t]) => {
        if (cancelado) return
        setCred(c)
        setTareas(t.data)
      })
      .catch((e) => {
        if (!cancelado) setError(String(e))
      })
      .finally(() => {
        if (!cancelado) setCargando(false)
      })
    return () => {
      cancelado = true
    }
  }, [fetchCred, fetchTareas])

  useEffect(() => {
    if (!tpSeleccionada) {
      setSync(null)
      return
    }
    let cancelado = false
    getSincronizacionTP(tpSeleccionada, getToken)
      .then((s) => {
        if (!cancelado) setSync(s)
      })
      .catch((e) => {
        if (!cancelado) setError(String(e))
      })
    return () => {
      cancelado = true
    }
  }, [tpSeleccionada, getToken])

  async function handleConectar() {
    setConectando(true)
    setError(null)
    try {
      setCred(await conectarActiveIA(username, password, getToken))
      // El password no queda en memoria mas de lo necesario.
      setPassword("")
    } catch (e) {
      setError(String(e))
    } finally {
      setConectando(false)
    }
  }

  async function handleDesconectar() {
    if (!window.confirm("Se va a desconectar tu cuenta de Active-IA. Confirmas?")) return
    setError(null)
    try {
      await desconectarActiveIA(getToken)
      setCred(await fetchCred())
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleSincronizar() {
    if (!tpSeleccionada) return
    setSincronizando(true)
    setError(null)
    try {
      setSync(await sincronizarTP(tpSeleccionada, getToken))
    } catch (e) {
      setError(String(e))
    } finally {
      setSincronizando(false)
    }
  }

  return (
    <PageContainer
      title="Correccion asistida (Active-IA)"
      description="Tu cuenta de Active-IA y el estado de las rubricas de cada ejercicio"
      helpContent={helpContent.activeIa}
    >
      {error && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs text-danger">
          {error}
        </div>
      )}

      {/* El aviso de simulacion va arriba de todo y no en una columna: si el
          simulador esta puesto, NADA de lo que muestra esta pantalla llego a
          Active-IA, y eso hay que decirlo una vez y fuerte. */}
      {(sync?.modo_simulado || cred?.modo_simulado) && (
        <div
          className="mb-4 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning-soft p-3 text-xs text-warning"
          data-testid="activeia-modo-simulado"
        >
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            <strong>Modo simulado.</strong> Active-IA todavia no expone los endpoints para recibir
            rubricas, asi que lo que ves NO se envio: los estados de abajo son de mentira y las
            rubricas marcadas con <code>MOCK-</code> no existen del otro lado. No dispares
            correcciones reales con esto puesto.
          </span>
        </div>
      )}

      {cargando ? (
        <p className="text-sm text-muted">Cargando...</p>
      ) : (
        <div className="space-y-6">
          {/* ── Cuenta ──────────────────────────────────────────────── */}
          <section className="rounded-lg border border-subtle p-4">
            <h3 className="mb-3 text-sm font-semibold text-ink">Tu cuenta de Active-IA</h3>
            {cred?.conectada ? (
              <div className="flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center gap-1.5 rounded bg-success-soft px-2 py-1 text-xs text-success">
                  <Link2 size={14} aria-hidden="true" />
                  Conectada como {cred.username}
                </span>
                {cred.last_login_at && (
                  <span className="text-xs text-muted">
                    Ultimo acceso: {new Date(cred.last_login_at).toLocaleString()}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => void handleDesconectar()}
                  data-testid="activeia-desconectar"
                  className="ml-auto inline-flex items-center gap-1.5 rounded border border-subtle px-3 py-1.5 text-xs text-secondary hover:bg-surface-hover"
                >
                  <Link2Off size={14} aria-hidden="true" />
                  Desconectar
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-muted">
                  Cada docente conecta su propia cuenta: del lado de Active-IA las comisiones y las
                  rubricas salen de la cuenta con la que se entra.
                </p>
                <div className="flex flex-wrap gap-2">
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Usuario de Active-IA"
                    autoComplete="username"
                    className="flex-1 min-w-[200px] rounded border border-subtle bg-surface px-3 py-1.5 text-sm"
                  />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Contrasena"
                    autoComplete="current-password"
                    className="flex-1 min-w-[200px] rounded border border-subtle bg-surface px-3 py-1.5 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => void handleConectar()}
                    disabled={conectando || !username || !password}
                    data-testid="activeia-conectar"
                    className="rounded px-4 py-1.5 text-sm font-medium text-white disabled:opacity-60"
                    style={{ backgroundColor: "var(--color-accent-brand)" }}
                  >
                    {conectando ? "Verificando..." : "Conectar"}
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* ── Rubricas por TP ─────────────────────────────────────── */}
          <section className="rounded-lg border border-subtle p-4">
            <h3 className="mb-3 text-sm font-semibold text-ink">Rubricas por trabajo practico</h3>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <select
                value={tpSeleccionada}
                onChange={(e) => setTpSeleccionada(e.target.value)}
                className="min-w-[260px] rounded border border-subtle bg-surface px-3 py-1.5 text-sm"
              >
                <option value="">Elegi un trabajo practico</option>
                {tareas.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.codigo} — {t.titulo}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void handleSincronizar()}
                disabled={!tpSeleccionada || sincronizando || !cred?.conectada}
                title={
                  cred?.conectada
                    ? "Empuja la rubrica de cada ejercicio a Active-IA"
                    : "Conecta tu cuenta primero"
                }
                data-testid="activeia-sincronizar"
                className="inline-flex items-center gap-1.5 rounded border border-subtle px-3 py-1.5 text-sm text-secondary hover:bg-surface-hover disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <RefreshCw size={14} aria-hidden="true" />
                {sincronizando ? "Sincronizando..." : "Sincronizar"}
              </button>
            </div>

            {sync && <TablaSync ejercicios={sync.ejercicios} />}
          </section>
        </div>
      )}
    </PageContainer>
  )
}

function TablaSync({ ejercicios }: { ejercicios: EjercicioSync[] }) {
  if (ejercicios.length === 0) {
    return <p className="text-xs text-muted">Este trabajo practico no tiene ejercicios.</p>
  }
  return (
    // overflow propio: la tabla no puede hacer scrollear la pagina entera.
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs" data-testid="activeia-tabla-sync">
        <thead className="text-muted">
          <tr>
            <th className="pb-2 font-normal">Ejercicio</th>
            <th className="pb-2 font-normal">Estado</th>
            <th className="pb-2 font-normal">Rubrica</th>
            <th className="pb-2 font-normal">Sincronizado</th>
          </tr>
        </thead>
        <tbody>
          {ejercicios.map((ej) => {
            const ui = estadoUI(ej.estado)
            return (
              <tr key={ej.ejercicio_id} className="border-t border-subtle">
                <td className="py-2 pr-3 text-body">{ej.titulo}</td>
                <td className="py-2 pr-3">
                  <span className={`inline-block rounded px-2 py-0.5 font-mono ${ui.clase}`}>
                    {ui.label}
                  </span>
                </td>
                <td className="py-2 pr-3 font-mono text-muted">
                  {ej.rubrica_id ?? "—"}
                  {ej.simulado && (
                    <span className="ml-1 text-warning" title="Rubrica simulada: no existe">
                      (simulada)
                    </span>
                  )}
                </td>
                <td className="py-2 text-muted">
                  {ej.sincronizado_at ? new Date(ej.sincronizado_at).toLocaleString() : "—"}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
