// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { cn } from "../../utils/cn"
import type { TourPlacement } from "./types"
import { type Rect, useAnchorRect } from "./useAnchorRect"

const CARD_W = 340
const MARGEN = 16
const GAP = 14
/** Aire alrededor del elemento iluminado. Sin esto el recorte lo estrangula. */
const PAD = 6

/**
 * Clases de los botones del pie. Viven aca y no en cada provider para que los dos
 * consumidores (tour lineal y onboarding por estado) se vean igual sin duplicar
 * estilos: el pie lo arma cada provider, pero los botones son los mismos.
 */
export const CLASE_BOTON_PRIMARIO =
  "bg-ink px-3 py-1.5 text-xs font-medium text-surface hover:bg-ink/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-strong focus-visible:ring-offset-1"

export const CLASE_BOTON_SECUNDARIO =
  "px-2 py-1.5 text-xs text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-strong"

export const CLASE_BOTON_TEXTO =
  "text-xs text-muted underline underline-offset-4 hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-strong"

export interface TourOverlayProps {
  /**
   * Clave estable del contenido mostrado (id del paso o del cartel). Re-dispara la
   * medicion del ancla y el foco cuando cambia.
   */
  id: string
  title: string
  body: ReactNode
  /** Valor de `data-tour` del elemento a iluminar. Omitir = card centrada, sin recorte. */
  anchor?: string | undefined
  placement?: TourPlacement | undefined
  /** Renglon superior, tipo "2 / 5". Solo lo usa el tour lineal. */
  contador?: string | undefined
  /** Pie del cartel. Cada provider arma el suyo; se alinea a la derecha. */
  footer: ReactNode
  /**
   * Toma la pantalla: velo, captura de clicks y `aria-modal`.
   *
   * El tour lineal va en `true` (es un recorrido: no hay nada que operar mientras
   * corre). El onboarding por estado va en `false`, porque su cartel pide HACER algo
   * y bloquear justo la accion que estas pidiendo no es un tour, es una pared. Ademas
   * es lo que permite que el cartel se retire solo cuando `doneWhen` pasa a true.
   *
   * Default: `true`.
   */
  modal?: boolean | undefined
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max)
}

/**
 * Ubica la card contra el recorte. Prueba el lado pedido, y si no entra prueba el
 * opuesto antes de resignarse: es mejor cruzar de lado que quedar pegado al borde
 * tapando justo lo que se esta senalando.
 */
function ubicar(
  rect: Rect,
  cardH: number,
  preferido: TourPlacement | undefined,
): { top: number; left: number } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const entraAbajo = rect.top + rect.height + GAP + cardH < vh - MARGEN
  const entraArriba = rect.top - GAP - cardH > MARGEN
  const entraDerecha = rect.left + rect.width + GAP + CARD_W < vw - MARGEN
  const entraIzquierda = rect.left - GAP - CARD_W > MARGEN

  let lado = preferido ?? "bottom"
  if (lado === "bottom" && !entraAbajo) lado = entraArriba ? "top" : entraDerecha ? "right" : "left"
  else if (lado === "top" && !entraArriba)
    lado = entraAbajo ? "bottom" : entraDerecha ? "right" : "left"
  else if (lado === "right" && !entraDerecha)
    lado = entraIzquierda ? "left" : entraAbajo ? "bottom" : "top"
  else if (lado === "left" && !entraIzquierda)
    lado = entraDerecha ? "right" : entraAbajo ? "bottom" : "top"

  const top =
    lado === "bottom"
      ? rect.top + rect.height + GAP
      : lado === "top"
        ? rect.top - GAP - cardH
        : rect.top
  const left =
    lado === "right"
      ? rect.left + rect.width + GAP
      : lado === "left"
        ? rect.left - GAP - CARD_W
        : rect.left

  return {
    top: clamp(top, MARGEN, Math.max(MARGEN, vh - cardH - MARGEN)),
    left: clamp(left, MARGEN, Math.max(MARGEN, vw - CARD_W - MARGEN)),
  }
}

/**
 * Cartel del onboarding. Es puramente presentacional y sirve a los dos mecanismos:
 * no sabe de pasos, de contadores ni de estado. Quien lo usa decide que dice el pie.
 */
export function TourOverlay({
  id,
  title,
  body,
  anchor,
  placement,
  contador,
  footer,
  modal = true,
}: TourOverlayProps) {
  const rect = useAnchorRect(anchor, id)
  const cardRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    if (!rect) {
      setPos(null)
      return
    }
    const h = cardRef.current?.offsetHeight ?? 200
    setPos(ubicar(rect, h, placement))
  }, [rect, placement])

  // El foco se lleva al cartel cada vez que cambia el contenido, no solo al montar:
  // el nodo se reusa entre pasos, asi que sin esto el lector de pantalla anuncia el
  // primer cartel y despues se queda mudo.
  //
  // SOLO en modal. Un cartel no-modal aparece cuando cambia el ESTADO, o sea cuando
  // resuelve un refetch de fondo: robarle el foco ahi le saca al alumno el cursor de
  // donde estaba escribiendo, sin que haya hecho nada. Un aviso que no bloquea se
  // anuncia por la live region (`role="status"` abajo) y no mueve el foco.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `id` no se usa adentro; esta a proposito, es lo que identifica "cambio el cartel".
  useEffect(() => {
    if (modal) cardRef.current?.focus()
  }, [id, modal])

  const centrada = !rect

  // Este contenedor NO lleva `aria-live`. Envolvia tambien al recorte, cuyo `style`
  // muta en cada scroll; en el modal quedaba podado por el `aria-modal` del hijo, y
  // ademas duplicaba lo que ya anuncia el foco. El anuncio vive ahora donde
  // corresponde: el `role="status"` de la card, solo en el caso no-modal.
  return createPortal(
    <div className={cn("fixed inset-0 z-[100]", !modal && "pointer-events-none")}>
      {/* Capa que come clicks. NO cierra nada: salir del tour es explicito (el boton
          del pie o Escape). Un clic al aire no puede costarle al usuario no volver a
          ver el recorrido nunca mas. */}
      {modal && <div className="absolute inset-0" aria-hidden="true" />}

      {/* El velo se pinta como sombra proyectada del recorte: borde limpio, sin blur
          ni tinte. La pantalla no se vuelve otra cosa, solo se apaga alrededor.
          Sin `modal` no hay velo — queda solo el aro sobre lo que se senala. */}
      {centrada
        ? modal && (
            <div
              className="pointer-events-none absolute inset-0 bg-ink/60 motion-safe:animate-[fade-in_200ms_var(--ease-out-quart)]"
              aria-hidden="true"
            />
          )
        : rect && (
            <div
              aria-hidden="true"
              className={cn(
                "pointer-events-none absolute rounded-[3px] ring-1 motion-safe:transition-all motion-safe:duration-300",
                modal ? "ring-surface/70" : "ring-border-strong",
              )}
              style={{
                top: rect.top - PAD,
                left: rect.left - PAD,
                width: rect.width + PAD * 2,
                height: rect.height + PAD * 2,
                transitionTimingFunction: "var(--ease-out-quart)",
                ...(modal
                  ? {
                      boxShadow:
                        "0 0 0 200vmax color-mix(in oklch, var(--color-ink) 60%, transparent)",
                    }
                  : {}),
              }}
            />
          )}

      <div
        ref={cardRef}
        // Dos roles, porque son dos cosas distintas y el lector de pantalla las trata
        // distinto. El tour ES la tarea: dialogo, y el foco entra. El cartel del
        // onboarding acompana una tarea que sigue siendo del usuario: `status`, que se
        // anuncia sin secuestrar nada. Poner `dialog` en el no-modal seria mentirle al
        // lector: le diria que el resto de la pagina esta inerte cuando no lo esta.
        // biome-ignore lint/a11y/useSemanticElements: el <dialog> nativo tiene API showModal/close imperativa y stacking quirks que no encajan con el portal controlado de React; mismo criterio que Modal.tsx.
        role={modal ? "dialog" : "status"}
        {...(modal ? { "aria-modal": true, tabIndex: -1 } : {})}
        aria-labelledby={`cartel-${id}`}
        className={cn(
          "pointer-events-auto absolute w-[340px] max-w-[calc(100vw-2rem)]",
          "border border-border bg-surface p-5",
          "shadow-[0_8px_28px_-12px_color-mix(in_oklch,var(--color-ink)_45%,transparent)]",
          "outline-none motion-safe:animate-[fade-in-up_260ms_var(--ease-out-quart)]",
        )}
        style={
          centrada
            ? { top: "50%", left: "50%", transform: "translate(-50%, -50%)" }
            : (pos ?? { top: -9999, left: -9999 })
        }
      >
        {contador && (
          <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{contador}</p>
        )}
        <h2
          id={`cartel-${id}`}
          className={cn("text-lg font-semibold leading-snug text-ink", contador && "mt-2")}
        >
          {title}
        </h2>
        <div className="mt-2 space-y-2 text-sm leading-relaxed text-body">{body}</div>

        <div className="mt-5 flex items-center justify-end gap-2 border-t border-border-soft pt-4">
          {footer}
        </div>
      </div>
    </div>,
    document.body,
  )
}
