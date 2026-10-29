/**
 * Vista "Pedidos de ayuda" (change alumno-pide-ayuda-al-docente).
 *
 * Lo que los alumnos de la comision le pidieron al docente desde el ejercicio,
 * con el dato adjunto: alumno, TP, ejercicio, categoria, mensaje, hora y el
 * episodio (si hay). MVP: sin respuesta escrita; el docente contesta como
 * siempre (en clase, por Moodle) y marca el pedido como resuelto, que es lo que
 * ve el alumno.
 *
 * Es ayuda HUMANA fuera del CTR: abrir esta pantalla o resolver un pedido no
 * modifica ningun episodio ni emite eventos.
 */
import { Badge, PageContainer } from "@platform/ui"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, ExternalLink, LifeBuoy, RefreshCw } from "lucide-react"
import { useMemo, useState } from "react"
import { useStudentProfiles } from "../hooks/useStudentProfiles"
import {
  type PedidoAyudaCategoria,
  type PedidoAyudaDocente,
  type PedidoAyudaEstado,
  listarPedidosAyuda,
  resolverPedidoAyuda,
  tareasPracticasApi,
} from "../lib/api"
import { studentShortLabel } from "../utils/docenteLabels"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

const CATEGORIA_LABEL: Record<PedidoAyudaCategoria, string> = {
  no_puedo_avanzar: "No puedo avanzar",
  error_plataforma: "Error de la plataforma",
  duda_consigna: "Duda sobre la consigna",
  otro: "Otro",
}

const CATEGORIA_VARIANT: Record<PedidoAyudaCategoria, "warning" | "danger" | "info" | "default"> = {
  no_puedo_avanzar: "warning",
  error_plataforma: "danger",
  duda_consigna: "info",
  otro: "default",
}

/** "hace 5 min" / "hace 2 h" / "hace 3 d". */
export function haceCuanto(iso: string, ahora: number = Date.now()): string {
  const ms = ahora - new Date(iso).getTime()
  if (Number.isNaN(ms) || ms < 0) return "recién"
  const min = Math.floor(ms / 60_000)
  if (min < 1) return "recién"
  if (min < 60) return `hace ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `hace ${h} h`
  return `hace ${Math.floor(h / 24)} d`
}

export function PedidosAyudaView({ comisionId, getToken }: Props) {
  const [tab, setTab] = useState<PedidoAyudaEstado>("pendiente")
  const queryClient = useQueryClient()
  const perfiles = useStudentProfiles(comisionId, getToken)

  const pedidosQuery = useQuery({
    queryKey: ["pedidos-ayuda", comisionId, tab],
    queryFn: () => listarPedidosAyuda({ comision_id: comisionId, estado: tab }, getToken),
  })

  // Nombre de la TP, best-effort: si falla, la fila dice "TP" sin romper nada.
  const tpsQuery = useQuery({
    queryKey: ["pedidos-ayuda-tps", comisionId],
    queryFn: () => tareasPracticasApi.list({ comision_id: comisionId, limit: 200 }, getToken),
  })
  const tpPorId = useMemo(() => {
    const m = new Map<string, string>()
    for (const t of tpsQuery.data?.data ?? []) m.set(t.id, `${t.codigo} · ${t.titulo}`)
    return m
  }, [tpsQuery.data])

  const resolver = useMutation({
    mutationFn: (id: string) => resolverPedidoAyuda(id, getToken),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pedidos-ayuda", comisionId] })
      void queryClient.invalidateQueries({ queryKey: ["pedidos-ayuda-pendientes", comisionId] })
    },
  })

  const pedidos = pedidosQuery.data?.data ?? []
  const pendientes = pedidosQuery.data?.meta.pendientes

  return (
    <PageContainer
      title="Pedidos de ayuda"
      description="Lo que tus alumnos te pidieron desde el ejercicio, con el trabajo, el ejercicio y el episodio adjuntos. Marcalo como resuelto cuando lo atiendas."
      eyebrow="Inicio · Pedidos de ayuda"
      helpContent={helpContent.pedidosAyuda}
    >
      <div className="flex items-center justify-between gap-3 mb-4">
        <div role="tablist" aria-label="Estado del pedido" className="flex gap-1">
          <TabButton activo={tab === "pendiente"} onClick={() => setTab("pendiente")}>
            Pendientes{pendientes !== undefined ? ` (${pendientes})` : ""}
          </TabButton>
          <TabButton activo={tab === "resuelto"} onClick={() => setTab("resuelto")}>
            Resueltos
          </TabButton>
        </div>
        <button
          type="button"
          onClick={() => void pedidosQuery.refetch()}
          className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Actualizar
        </button>
      </div>

      {(pedidosQuery.error || resolver.error) && (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-danger/40 bg-danger-soft p-3 text-sm text-danger"
        >
          {resolver.error
            ? `No se pudo marcar el pedido como resuelto: ${String(resolver.error)}`
            : `No pudimos cargar los pedidos: ${String(pedidosQuery.error)}`}
        </div>
      )}

      {pedidosQuery.isLoading && <p className="text-sm text-muted">Cargando…</p>}

      {!pedidosQuery.isLoading && !pedidosQuery.error && pedidos.length === 0 && (
        <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center">
          <LifeBuoy className="mx-auto mb-2 h-6 w-6 text-muted" aria-hidden="true" />
          <p className="text-sm text-muted">
            {tab === "pendiente"
              ? "No hay pedidos pendientes en esta comisión."
              : "Todavía no resolviste ningún pedido."}
          </p>
        </div>
      )}

      <ul className="space-y-3" data-testid="pedidos-ayuda-lista">
        {pedidos.map((p) => (
          <PedidoFila
            key={p.id}
            pedido={p}
            alumno={studentShortLabel(p.student_pseudonym, perfiles)}
            tp={tpPorId.get(p.tarea_practica_id) ?? "TP"}
            resolviendo={resolver.isPending && resolver.variables === p.id}
            onResolver={() => resolver.mutate(p.id)}
          />
        ))}
      </ul>
    </PageContainer>
  )
}

function TabButton({
  activo,
  onClick,
  children,
}: {
  activo: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={activo}
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        activo ? "bg-accent-brand-soft text-accent-brand-deep" : "text-muted hover:bg-surface-alt"
      }`}
    >
      {children}
    </button>
  )
}

function PedidoFila({
  pedido,
  alumno,
  tp,
  resolviendo,
  onResolver,
}: {
  pedido: PedidoAyudaDocente
  alumno: string
  tp: string
  resolviendo: boolean
  onResolver: () => void
}) {
  const [expandido, setExpandido] = useState(false)
  const mensaje = pedido.mensaje ?? ""
  const largo = mensaje.length > 160
  return (
    <li className="rounded-xl border border-border bg-surface p-4" data-testid="pedido-ayuda-fila">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium text-ink">{alumno}</span>
        <span className="text-muted">·</span>
        <span className="text-body">{tp}</span>
        {pedido.ejercicio_orden !== null && (
          <>
            <span className="text-muted">·</span>
            <span className="text-body">Ejercicio {pedido.ejercicio_orden}</span>
          </>
        )}
        <Badge variant={CATEGORIA_VARIANT[pedido.categoria] ?? "default"}>
          {CATEGORIA_LABEL[pedido.categoria] ?? pedido.categoria}
        </Badge>
        <span className="ml-auto text-xs text-muted">{haceCuanto(pedido.created_at)}</span>
      </div>

      {mensaje && (
        <p className="mt-2 whitespace-pre-wrap text-sm text-body">
          {largo && !expandido ? `${mensaje.slice(0, 160)}…` : mensaje}
          {largo && (
            <button
              type="button"
              onClick={() => setExpandido((v) => !v)}
              className="ml-1 text-xs text-accent-brand underline"
            >
              {expandido ? "ver menos" : "ver más"}
            </button>
          )}
        </p>
      )}

      {pedido.contexto?.error_visible && (
        <p className="mt-2 rounded bg-surface-alt px-2 py-1 font-mono text-xs text-muted">
          El alumno veía: {pedido.contexto.error_visible}
        </p>
      )}

      <div className="mt-3 flex items-center gap-3">
        {pedido.episode_id && (
          <Link
            to="/episode-timeline"
            search={{ episodeId: pedido.episode_id }}
            className="inline-flex items-center gap-1 text-xs text-accent-brand hover:underline"
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            Ver episodio
          </Link>
        )}
        {pedido.estado === "pendiente" ? (
          <button
            type="button"
            onClick={onResolver}
            disabled={resolviendo}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-alt disabled:opacity-50"
          >
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
            Marcar resuelto
          </button>
        ) : (
          <span className="ml-auto text-xs text-success">
            Resuelto {pedido.resuelto_at ? haceCuanto(pedido.resuelto_at) : ""}
          </span>
        )}
      </div>
    </li>
  )
}
