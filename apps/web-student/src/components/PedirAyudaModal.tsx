/**
 * "Pedir ayuda a tu docente" (change alumno-pide-ayuda-al-docente).
 *
 * Ayuda HUMANA fuera del tutor: el pedido le llega a los docentes de la
 * comision con el ejercicio y el episodio adjuntos. NO emite nada al CTR y NO
 * toca el episodio: abrir el modal es una superposicion, el alumno sigue en el
 * ejercicio (no se pausa, no se cierra, no se abandona).
 *
 * Exporta dos piezas:
 *   - `PedirAyudaModal`: el modal controlado.
 *   - `PedirAyudaBoton`: el boton secundario + su modal, para pegar en un header.
 */
import { Modal } from "@platform/ui"
import { LifeBuoy } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import {
  type PedidoAyuda,
  type PedidoAyudaCategoria,
  type PedidoAyudaCreate,
  PedidoAyudaError,
  type TokenGetter,
  crearPedidoAyuda,
  listarMisPedidosAyuda,
} from "../lib/api"

export type PantallaPedido = "episodio" | "episodio_error" | "lista_ejercicios"

const CATEGORIAS: { value: PedidoAyudaCategoria; label: string }[] = [
  { value: "no_puedo_avanzar", label: "No puedo avanzar" },
  { value: "error_plataforma", label: "Error de la plataforma" },
  { value: "duda_consigna", label: "Duda sobre la consigna" },
  { value: "otro", label: "Otro" },
]

const CATEGORIA_LABEL: Record<PedidoAyudaCategoria, string> = {
  no_puedo_avanzar: "No puedo avanzar",
  error_plataforma: "Error de la plataforma",
  duda_consigna: "Duda sobre la consigna",
  otro: "Otro",
}

const MAX_MENSAJE = 1000

export interface PedirAyudaContexto {
  tareaPracticaId: string
  pantalla: PantallaPedido
  ejercicioOrden?: number | undefined
  episodeId?: string | undefined
  entregaId?: string | undefined
  /** Texto de error que el alumno tenia en pantalla (se manda como diagnostico). */
  errorVisible?: string | undefined
  /** Ejercicios de la TP: si se pasan y no hay `ejercicioOrden`, se ofrece elegir uno. */
  ejercicios?: { orden: number; titulo: string }[] | undefined
  getToken?: TokenGetter | undefined
}

interface PedirAyudaModalProps extends PedirAyudaContexto {
  isOpen: boolean
  onClose: () => void
}

/** Frase para el alumno a partir del rechazo del servidor. */
function motivoDelRechazo(e: unknown): string {
  if (e instanceof PedidoAyudaError) {
    if (e.detail) return e.detail
    if (e.status === 403) {
      return "No estás inscripto en la comisión de este trabajo. Hablá con tu docente."
    }
    if (e.status === 429) return "Esperá un momento antes de mandar otro pedido."
    if (e.status === 409) return "Ya tenés pedidos sin responder en este trabajo."
  }
  return "No pudimos enviar tu pedido. Probá de nuevo en unos segundos."
}

function cuando(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" })
}

export function PedirAyudaModal({
  isOpen,
  onClose,
  tareaPracticaId,
  pantalla,
  ejercicioOrden,
  episodeId,
  entregaId,
  errorVisible,
  ejercicios,
  getToken,
}: PedirAyudaModalProps) {
  const [categoria, setCategoria] = useState<PedidoAyudaCategoria | null>(null)
  const [mensaje, setMensaje] = useState("")
  const [ordenElegido, setOrdenElegido] = useState<string>("")
  const [enviando, setEnviando] = useState(false)
  const [enviado, setEnviado] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mios, setMios] = useState<PedidoAyuda[]>([])

  const cargarMios = useCallback(async () => {
    setMios(await listarMisPedidosAyuda(tareaPracticaId, getToken))
  }, [tareaPracticaId, getToken])

  useEffect(() => {
    if (!isOpen) return
    // Al reabrir arranca limpio: el pedido anterior ya salio.
    setCategoria(null)
    setMensaje("")
    setOrdenElegido("")
    setEnviado(false)
    setError(null)
    void cargarMios()
  }, [isOpen, cargarMios])

  const ofreceSelector = ejercicioOrden === undefined && (ejercicios?.length ?? 0) > 0

  async function enviar() {
    if (!categoria || enviando || enviado) return
    setEnviando(true)
    setError(null)
    const orden = ejercicioOrden ?? (ordenElegido ? Number(ordenElegido) : undefined)
    const texto = mensaje.trim()
    const payload: PedidoAyudaCreate = {
      tarea_practica_id: tareaPracticaId,
      categoria,
      contexto: {
        pantalla,
        ...(errorVisible ? { error_visible: errorVisible.slice(0, 300) } : {}),
        ...(typeof navigator !== "undefined" && navigator.userAgent
          ? { user_agent: navigator.userAgent.slice(0, 300) }
          : {}),
      },
      ...(texto ? { mensaje: texto } : {}),
      ...(orden !== undefined ? { ejercicio_orden: orden } : {}),
      ...(episodeId ? { episode_id: episodeId } : {}),
      ...(entregaId ? { entrega_id: entregaId } : {}),
    }
    try {
      await crearPedidoAyuda(payload, getToken)
      setEnviado(true)
      void cargarMios()
    } catch (e) {
      setError(motivoDelRechazo(e))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Pedir ayuda a tu docente" size="sm">
      <div className="space-y-4" data-testid="pedir-ayuda-modal">
        <p className="text-xs text-muted leading-relaxed">
          Esto le llega a tu docente, no al tutor. No es una pista: el tutor sigue siendo tu ayuda
          para resolver el ejercicio.
        </p>

        {enviado ? (
          <output className="block rounded-md border border-success/40 bg-success-soft px-3 py-2 text-sm text-success">
            Tu pedido le llegó a tu docente.
          </output>
        ) : (
          <>
            <fieldset className="space-y-1.5">
              <legend className="text-sm font-medium text-ink mb-1">¿Qué te pasa?</legend>
              {CATEGORIAS.map((c) => (
                <label key={c.value} className="flex items-center gap-2 text-sm text-body">
                  <input
                    type="radio"
                    name="pedido-ayuda-categoria"
                    value={c.value}
                    checked={categoria === c.value}
                    onChange={() => setCategoria(c.value)}
                  />
                  {c.label}
                </label>
              ))}
            </fieldset>

            {ofreceSelector && (
              <div>
                <label htmlFor="pedido-ayuda-ejercicio" className="block text-sm text-ink mb-1">
                  ¿En qué ejercicio? (opcional)
                </label>
                <select
                  id="pedido-ayuda-ejercicio"
                  value={ordenElegido}
                  onChange={(e) => setOrdenElegido(e.target.value)}
                  className="w-full rounded border border-border bg-surface px-2 py-1.5 text-sm"
                >
                  <option value="">Ninguno en particular</option>
                  {ejercicios?.map((e) => (
                    <option key={e.orden} value={e.orden}>
                      {e.orden}. {e.titulo}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div>
              <label htmlFor="pedido-ayuda-mensaje" className="block text-sm text-ink mb-1">
                Mensaje (opcional)
              </label>
              <textarea
                id="pedido-ayuda-mensaje"
                value={mensaje}
                maxLength={MAX_MENSAJE}
                rows={4}
                onChange={(e) => setMensaje(e.target.value)}
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-sm"
              />
              <p className="mt-0.5 text-right text-xs font-mono text-muted">
                {mensaje.length}/{MAX_MENSAJE}
              </p>
            </div>

            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}

            <button
              type="button"
              onClick={() => void enviar()}
              disabled={!categoria || enviando}
              className="w-full rounded px-4 py-2 text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: "var(--color-accent-brand)" }}
            >
              {enviando ? "Enviando…" : "Enviar"}
            </button>
          </>
        )}

        {mios.length > 0 && (
          <section
            aria-label="Tus pedidos en este trabajo"
            className="border-t border-border-soft pt-3"
          >
            <h3 className="text-sm font-medium text-ink mb-2">Tus pedidos en este trabajo</h3>
            <ul className="space-y-1.5">
              {mios.map((p) => (
                <li key={p.id} className="flex items-start justify-between gap-2 text-xs text-body">
                  <span>
                    {CATEGORIA_LABEL[p.categoria] ?? p.categoria}
                    {p.ejercicio_orden ? ` · ejercicio ${p.ejercicio_orden}` : ""}
                    <span className="block text-muted">{cuando(p.created_at)}</span>
                  </span>
                  <span
                    className={
                      p.estado === "resuelto"
                        ? "shrink-0 rounded bg-success-soft px-1.5 py-0.5 text-success"
                        : "shrink-0 rounded bg-surface-alt px-1.5 py-0.5 text-muted"
                    }
                  >
                    {p.estado === "resuelto" ? "Resuelto" : "Pendiente"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Modal>
  )
}

/** Boton secundario (no compite con el tutor) que abre el modal. */
export function PedirAyudaBoton(props: PedirAyudaContexto & { className?: string }) {
  const [abierto, setAbierto] = useState(false)
  const { className, ...contexto } = props
  return (
    <>
      <button
        type="button"
        onClick={() => setAbierto(true)}
        data-testid="pedir-ayuda-button"
        data-tour="pedir-ayuda"
        className={
          className ??
          "inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-body hover:bg-surface-alt"
        }
      >
        <LifeBuoy className="h-3.5 w-3.5" aria-hidden="true" />
        Pedir ayuda a tu docente
      </button>
      <PedirAyudaModal isOpen={abierto} onClose={() => setAbierto(false)} {...contexto} />
    </>
  )
}
