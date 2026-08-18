// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { CLASE_BOTON_PRIMARIO, TourOverlay } from "./TourOverlay"
import { guardarDescartes, leerDescartes } from "./persistencia"
import type { OnboardingFlow, OnboardingHint, OnboardingProgress } from "./types"

interface OnboardingContextValue {
  /** Id del cartel visible ahora, o `null`. Nunca hay dos a la vez, por diseno. */
  visible: string | null
  /** Descarta un cartel y lo persiste. Es lo que hacen el CTA y Escape. */
  descartar: (hintId: string) => void
  /** Progreso derivado del estado real. La barra que lo dibuja se difirio. */
  progreso: OnboardingProgress
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null)

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext)
  if (!ctx) throw new Error("useOnboarding necesita estar dentro de <OnboardingProvider>")
  return ctx
}

/**
 * Progreso de "primeros pasos N de M". Cuenta solo los carteles que piden una accion
 * (`countsTowardProgress !== false`): los que solo explican una pantalla no son un
 * paso que el usuario pueda "cumplir", y meterlos en el conteo lo vuelve mentira.
 */
export function useOnboardingProgress(): OnboardingProgress {
  return useOnboarding().progreso
}

interface OnboardingProviderProps<S> {
  flow: OnboardingFlow<S>
  /** Estado real de la app, en la forma que cada frontend calcule. */
  estado: S
  /**
   * Ruta actual, la aporta el host. El motor no conoce TanStack ni ningun router:
   * solo la compara, por segmento, contra la `route` que declare cada cartel.
   * Ver `matcheaRuta` abajo.
   */
  route: string
  children: ReactNode
}

/**
 * Match de ruta POR SEGMENTO, como manda el contrato:
 *     matchea  <=>  ruta === h.route || ruta.startsWith(h.route + "/")
 *
 * La barra es obligatoria. Un `startsWith` pelado es un bug con dientes en este repo:
 * web-teacher tiene `/episode-n-level` y `/episode-timeline`, asi que un hint declarado
 * en `/episode` se disparaba en las dos.
 *
 * Consecuencia buscada: un hint declarado en `/` matchea SOLO la home, no la app entera.
 */
function matcheaRuta(ruta: string, declarada: string | undefined): boolean {
  if (declarada === undefined) return true
  return ruta === declarada || ruta.startsWith(`${declarada}/`)
}

function aplica<S>(
  hint: OnboardingHint<S>,
  estado: S,
  route: string,
  descartados: ReadonlySet<string>,
): boolean {
  if (!matcheaRuta(route, hint.route)) return false
  if (descartados.has(hint.id)) return false
  return hint.unlockWhen(estado) && !hint.doneWhen(estado)
}

/**
 * ONBOARDING POR ESTADO: carteles sueltos que aparecen segun lo que el usuario YA HIZO
 * de verdad. No hay orden ni contador propio — el estado real de la app decide que
 * corresponde mostrar, y por eso es idempotente: un paso que nace cumplido no se
 * muestra nunca.
 *
 * Dos propiedades que sostienen todo y no se tocan sin leer `types.ts`:
 *
 *   1. UNO SOLO A LA VEZ. Se muestra el PRIMER cartel de la lista que aplique. Dos
 *      carteles simultaneos convierten la ayuda en ruido.
 *   2. El cartel se retira SOLO cuando `doneWhen` pasa a true, sin necesidad de que el
 *      usuario lo cierre. Eso es lo que evita el tutorial zombie: si cumplis el paso
 *      mientras el cartel esta abierto, el cartel desaparece en vez de seguir
 *      pidiendote algo que ya hiciste. Por eso el overlay va sin `modal`: bloquear la
 *      accion que estas pidiendo haria imposible cumplirla.
 *
 * Cerrar el cartel (CTA o Escape) lo descarta y lo persiste. No hay forma de cerrarlo
 * sin querer: el clic al fondo no descarta nada.
 */
export function OnboardingProvider<S>({
  flow,
  estado,
  route,
  children,
}: OnboardingProviderProps<S>) {
  const [descartados, setDescartados] = useState<ReadonlySet<string>>(() => leerDescartes(flow.id))

  // Cambiar el id del flow es cambiar de catalogo de descartes. Pasa poco (un flow por
  // app), pero si pasa hay que releer: los descartes del flow viejo no son los de este.
  const flowIdPrevio = useRef(flow.id)
  useEffect(() => {
    if (flowIdPrevio.current === flow.id) return
    flowIdPrevio.current = flow.id
    setDescartados(leerDescartes(flow.id))
  }, [flow.id])

  const descartar = useCallback(
    (hintId: string) => {
      if (descartados.has(hintId)) return
      const siguiente = new Set(descartados)
      siguiente.add(hintId)
      setDescartados(siguiente)
      guardarDescartes(flow.id, siguiente)
    },
    [descartados, flow.id],
  )

  // Se recalcula cuando cambia el estado o la ruta. Todo sale del estado real; lo unico
  // que aporta el localStorage es el set de descartados.
  const hint = useMemo(
    () => flow.hints.find((h) => aplica(h, estado, route, descartados)) ?? null,
    [flow, estado, route, descartados],
  )

  const progreso = useMemo<OnboardingProgress>(() => {
    const contables = flow.hints.filter((h) => h.countsTowardProgress !== false)
    const hechos = contables.filter((h) => h.doneWhen(estado)).length
    return { hechos, total: contables.length, completo: hechos === contables.length }
  }, [flow, estado])

  // Escape descarta el cartel visible. Junto con el CTA es la unica salida.
  useEffect(() => {
    if (!hint) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") descartar(hint.id)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [hint, descartar])

  const value = useMemo<OnboardingContextValue>(
    () => ({ visible: hint?.id ?? null, descartar, progreso }),
    [hint, descartar, progreso],
  )

  return (
    <OnboardingContext.Provider value={value}>
      {children}
      {hint && (
        <TourOverlay
          id={hint.id}
          title={hint.title}
          body={hint.body}
          anchor={hint.anchor}
          placement={hint.placement}
          modal={false}
          footer={
            <button
              type="button"
              onClick={() => descartar(hint.id)}
              className={CLASE_BOTON_PRIMARIO}
            >
              {hint.ctaLabel ?? "Entendido"}
            </button>
          }
        />
      )}
    </OnboardingContext.Provider>
  )
}
