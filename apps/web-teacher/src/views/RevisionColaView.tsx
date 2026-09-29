/**
 * Cola de revisión humana (B3+B5, tareas 5.7/5.8).
 *
 * Consume `GET /api/v1/classifications/review-queue` (5.3) y
 * `POST /api/v1/classifications/{episode_id}/review` (5.4). Filas densas, no
 * grilla de cards (anti-referencia de PRODUCT.md); la decisión se abre EN la
 * fila, no en un modal, porque el docente necesita ver el contexto de la fila
 * mientras decide.
 *
 * Los 47 retenidos de hoy NO son una lista plana: son CUATRO preguntas
 * distintas, agrupadas por `estado_juez` en el orden inconsistente →
 * abstencion_traza_insuficiente → error_parseo → baja_confianza. El cuarto
 * estado (caso 4 de la Tabla 3.11, `regimen_llm.py:243`) no tiene casos en el
 * corpus de hoy porque el corpus todavía se clasificó con la regla booleana
 * vieja — pero el juez trivaluado YA lo puede emitir, así que está nombrado
 * acá desde el día uno y no cuando aparezca el primer caso real.
 *
 * Un QUINTO grupo, genérico, existe solo para lo verdaderamente desconocido:
 * un `estado_juez` que no es ninguno de los cuatro nombrados. Eso no es
 * información sobre el episodio — es evidencia de que el backend emitió un
 * estado que esta pantalla todavía no conoce (backend y frontend
 * desincronizados), y el copy lo dice así en vez de tratarlo como un motivo
 * más. Sirve de canario: si se agrega un sexto estado al `Literal` de
 * `regimen_llm.py` y nadie actualiza esta vista, el docente lo ve acá en vez
 * de que el episodio se pierda silenciosamente.
 *
 * `ReviewQueueItemOut` no trae cantidad de eventos ni transcripción — esos
 * viven en `ctr_store` (otra base) y el classifier-service no hace joins
 * cross-base. Por eso cada fila linkea a la vista de episodio existente
 * (`/episode-n-level`) en vez de traer ese detalle acá.
 */
import { Badge, PageContainer, StateMessage } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { useCallback, useEffect, useState } from "react"
import { type ReviewQueueItem, type TokenGetter, getReviewQueue, submitReview } from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string | undefined
  getToken: TokenGetter
}

interface GroupConfig {
  estado: string
  titulo: string
  descripcion: string
  badge: "warning" | "danger" | "info" | "default"
  /**
   * `false` = el episodio NO tiene veredicto que juzgar, asi que no se ofrece
   * decidir. Hoy solo el grupo "el juez no llego a correr": ahi el fallo es de
   * infraestructura y lo que corresponde es reclasificar, no que un docente
   * invente una etiqueta. La pantalla avisa que la decision REEMPLAZA la
   * etiqueta oficial y que esa es la que se cita en la tesis — ofrecer el boton
   * sobre un 502 es pedirle a una persona que firme un juicio que nadie emitio.
   */
  decidible?: boolean
}

// Orden fijo del shape brief, con el agregado del caso 4 de la Tabla 3.11
// (pedido por el coordinador, 2026-09-27): el juez contradiciendo la regla va
// primero porque es el único grupo donde la decisión del docente enseña algo
// sobre el clasificador. La abstención por traza insuficiente va segunda —
// antes que el JSON roto — porque el docente aprende más de una abstención
// que el sistema declaró bien que de una falla de formato. Los números NO se
// hardcodean (principio 4, PRODUCT.md) — se leen del largo de cada grupo ya
// filtrado.

const GROUP_ORDER: GroupConfig[] = [
  {
    estado: "inconsistente",
    titulo: "El juez contradijo a la regla determinista",
    descripcion: "El veredicto del juez y el del árbol no coinciden. Decidí quién tenía razón.",
    badge: "warning",
  },
  {
    // Caso 4 de la Tabla 3.11 (regimen_llm.py:243): ninguna dimensión hace
    // falsa la fórmula y alguna dimensión necesaria es "no evaluable" — la
    // traza no alcanza para decidir. NO es "el juez se equivocó" (eso es
    // `inconsistente`) ni "el juez rompió el formato" (eso es
    // `error_parseo`): el juez se abstuvo correctamente porque no había con
    // qué juzgar. La pregunta al docente es confirmar esa abstención o
    // aportar el juicio que el sistema no pudo emitir.
    estado: "abstencion_traza_insuficiente",
    titulo: "Abstención por traza insuficiente",
    descripcion:
      "La traza del episodio no alcanzaba para evaluar una dimensión decisiva. Confirmá la abstención o aportá el juicio que el sistema no pudo emitir.",
    badge: "warning",
  },
  {
    estado: "error_parseo",
    titulo: "El juez no devolvió un veredicto legible",
    descripcion: "El juez respondió JSON inválido. No hay veredicto semántico que juzgar acá.",
    badge: "danger",
  },
  {
    estado: "baja_confianza",
    titulo: "El juez no alcanzó el umbral de confianza",
    descripcion: "El umbral de 0,70 actuó sobre este episodio.",
    badge: "info",
  },
]

// Grupo defensivo (quinto): NO es un motivo del episodio, es información
// sobre una desincronización entre backend y frontend — el clasificador
// emitió un `estado_juez` que esta pantalla no tiene nombrado en
// `GROUP_ORDER`. El copy tiene que decir eso, no inventar una pregunta al
// docente sobre un episodio que en realidad está bien.
// El juez NO llego a correr. `classify_ep.py:199` escribe el motivo y hace
// `return` ANTES de setear `features["regimen_llm"]`, asi que estos episodios
// no tienen `estado_juez`: no hay veredicto, ni bueno ni malo. Medido en
// produccion el 2026-09-29: 18 de 23 items de la cola eran esto, todos con
// `502 Bad Gateway` del ai-gateway.
//
// Hasta ese dia caian en OTROS_GROUP, que le decia al docente que era una
// desincronizacion de frontend. Era falso y lo mandaba a reportar un bug que no
// existe — cuando lo que pasaba era que el gateway estaba caido.
const SIN_JUEZ_GROUP: GroupConfig = {
  estado: "__sin_juez__",
  titulo: "El juez no llego a correr",
  descripcion:
    "El clasificador no pudo consultar al modelo, asi que no hay veredicto que revisar. No es una decision pedagogica: es una falla de infraestructura. Estos episodios se reclasifican cuando el servicio vuelva — no hace falta que decidas nada.",
  badge: "danger",
  decidible: false,
}

const OTROS_GROUP: GroupConfig = {
  estado: "__otros__",
  titulo: "Estados que esta pantalla no conoce",
  descripcion:
    "El clasificador emitió un estado sin nombrar acá. No es información sobre el episodio: es una desincronización entre el backend y esta vista. Avisá para que se actualice el frontend.",
  badge: "default",
}

const VERDICT_OPTIONS: { value: string; label: string }[] = [
  { value: "delegacion_pasiva", label: "Delegación pasiva" },
  { value: "apropiacion_superficial", label: "Apropiación superficial" },
  { value: "apropiacion_reflexiva", label: "Apropiación reflexiva" },
  { value: "autonomo", label: "Autónomo (sin tutor)" },
]

function groupItems(items: ReviewQueueItem[]): { config: GroupConfig; items: ReviewQueueItem[] }[] {
  const grupos = GROUP_ORDER.map((config) => ({
    config,
    items: items.filter((i) => i.estado_juez === config.estado),
  }))
  const conocidos = new Set(GROUP_ORDER.map((g) => g.estado))
  // Dos cosas distintas que antes caian juntas:
  //   sin `estado_juez`        → el juez nunca corrio (infraestructura)
  //   con uno que no conozco   → desincronizacion backend/frontend de verdad
  const sinJuez = items.filter((i) => !i.estado_juez)
  const otros = items.filter((i) => i.estado_juez && !conocidos.has(i.estado_juez))
  if (sinJuez.length > 0) grupos.push({ config: SIN_JUEZ_GROUP, items: sinJuez })
  if (otros.length > 0) grupos.push({ config: OTROS_GROUP, items: otros })
  return grupos.filter((g) => g.items.length > 0)
}

// Errores de dominio de `submitReview`: `throwIfNotOk` (lib/api.ts) adjunta
// `status` y `detail` al Error. 400 → `detail` es un string (mensaje del
// dominio, ya legible). 409 → `detail` es `{message, retryable}`; el mensaje
// que ve el docente NO es el técnico del backend, es el que distingue las dos
// acciones posibles (reintentar vs. leer la decisión ajena).
function mensajeDeError(err: unknown): string {
  const e = err as { status?: number; detail?: unknown }
  if (e.status === 409 && e.detail && typeof e.detail === "object") {
    const detail = e.detail as { retryable?: boolean }
    return detail.retryable
      ? "El sistema reclasificó este episodio mientras decidías. Tu decisión sigue siendo válida: reintentá."
      : "Otro docente ya decidió sobre este episodio. Leé su decisión antes de insistir."
  }
  if (e.status === 400 && typeof e.detail === "string") {
    return e.detail
  }
  return String(err)
}

export function RevisionColaView({ comisionId, getToken }: Props) {
  const [items, setItems] = useState<ReviewQueueItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const fetchQueue = useCallback(() => getReviewQueue(comisionId, getToken), [comisionId, getToken])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchQueue()
      .then((res) => {
        if (!cancelled) setItems(res.items)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [fetchQueue])

  const handleReviewed = (episodeId: string) => {
    setItems((prev) => prev?.filter((i) => i.episode_id !== episodeId) ?? prev)
    setExpandedId(null)
  }

  const grupos = items ? groupItems(items) : []

  return (
    <PageContainer
      title="Cola de revisión"
      description="Episodios que el clasificador no pudo resolver solo. Cada grupo te pide una decisión distinta."
      eyebrow="Inicio · Cola de revisión"
      helpContent={helpContent.revisionCola}
    >
      {loading && <StateMessage variant="loading" title="Cargando la cola…" />}

      {!loading && error && (
        <StateMessage variant="error" title="No pudimos cargar la cola" description={error} />
      )}

      {!loading && !error && items && items.length === 0 && (
        <StateMessage
          variant="empty"
          title="No hay episodios retenidos en este momento."
          description="Puede ser que ya se revisó todo, o que el clasificador dejó de marcar episodios. La cola no distingue las dos cosas por sí sola."
        />
      )}

      {!loading && !error && items && items.length > 0 && (
        <div className="space-y-6" data-testid="revision-cola-grupos">
          {grupos.map(({ config, items: grupoItems }) => (
            <section key={config.estado} data-testid={`review-group-${config.estado}`}>
              <div className="flex items-baseline gap-2 mb-2">
                <Badge variant={config.badge}>{grupoItems.length}</Badge>
                <h2 className="text-sm font-semibold text-ink">{config.titulo}</h2>
              </div>
              <p className="text-xs text-muted mb-3">{config.descripcion}</p>
              <ul className="divide-y divide-border border border-border rounded-lg bg-surface">
                {grupoItems.map((item) => (
                  <ReviewRow
                    key={item.episode_id}
                    item={item}
                    expanded={expandedId === item.episode_id}
                    onToggle={() =>
                      setExpandedId((prev) => (prev === item.episode_id ? null : item.episode_id))
                    }
                    onReviewed={() => handleReviewed(item.episode_id)}
                    getToken={getToken}
                    decidible={config.decidible !== false}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </PageContainer>
  )
}

interface ReviewRowProps {
  item: ReviewQueueItem
  expanded: boolean
  onToggle: () => void
  onReviewed: () => void
  getToken: TokenGetter
  decidible: boolean
}

function ReviewRow({
  item,
  expanded,
  onToggle,
  onReviewed,
  getToken,
  decidible,
}: ReviewRowProps) {
  const [verdict, setVerdict] = useState("")
  const [reason, setReason] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const handleSubmit = async () => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      await submitReview(item.episode_id, { verdict, reason }, getToken)
      onReviewed()
    } catch (e) {
      setSubmitError(mensajeDeError(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <li data-testid={`review-row-${item.episode_id}`} className="p-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="font-mono text-xs text-ink break-all">{item.episode_id}</div>
          <div className="text-xs text-muted mt-0.5">
            {item.needs_review_reason ?? "sin motivo registrado"}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Link
            to="/episode-n-level"
            search={{ episodeId: item.episode_id }}
            className="text-xs text-muted hover:text-ink hover:underline"
          >
            Ver traza →
          </Link>
          <button
            type="button"
            onClick={onToggle}
            disabled={!decidible}
            title={
              decidible
                ? undefined
                : "No hay veredicto que revisar: el juez no llego a correr sobre este episodio"
            }
            className="press-shrink inline-flex items-center rounded-md border border-border bg-surface-alt px-3 py-1.5 text-xs font-medium text-ink transition-colors enabled:hover:bg-border-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            {!decidible ? "Sin veredicto" : expanded ? "Cerrar" : "Decidir"}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 rounded-md border border-border-soft bg-surface-alt p-3 space-y-3">
          <div className="rounded-md border border-warning/30 bg-warning-soft p-2.5 text-xs text-warning">
            Tu decisión reemplaza la etiqueta oficial del sistema: queda como la etiqueta vigente
            del episodio, la que se cita en la tesis. No se registra al lado.
          </div>

          <div>
            <label
              htmlFor={`verdict-${item.episode_id}`}
              className="block text-xs font-medium text-ink mb-1"
            >
              Veredicto
            </label>
            <select
              id={`verdict-${item.episode_id}`}
              value={verdict}
              onChange={(e) => setVerdict(e.target.value)}
              className="w-full border border-border rounded px-2.5 py-1.5 text-sm text-ink bg-surface focus:outline-none focus:ring-1 focus:ring-ink"
            >
              <option value="">Elegí un veredicto…</option>
              {VERDICT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor={`reason-${item.episode_id}`}
              className="block text-xs font-medium text-ink mb-1"
            >
              Motivo
            </label>
            <textarea
              id={`reason-${item.episode_id}`}
              rows={3}
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Por qué esta decisión…"
              className="w-full border border-border rounded px-2.5 py-1.5 text-sm text-ink bg-surface focus:outline-none focus:ring-1 focus:ring-ink resize-none"
            />
          </div>

          {submitError && <p className="text-xs text-danger">{submitError}</p>}

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!verdict || !reason.trim() || submitting}
              className="press-shrink inline-flex items-center rounded-md bg-accent-brand px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-brand-deep disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
            >
              {submitting ? "Confirmando…" : "Confirmar decisión"}
            </button>
            <button
              type="button"
              onClick={onToggle}
              disabled={submitting}
              className="press-shrink inline-flex items-center rounded-md px-3 py-1.5 text-xs font-medium text-muted hover:text-ink transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}
    </li>
  )
}
