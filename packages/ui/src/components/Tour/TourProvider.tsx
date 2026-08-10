// Contenido en espanol SIN tildes para evitar problemas de encoding en Windows/cp1252.
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  CLASE_BOTON_PRIMARIO,
  CLASE_BOTON_SECUNDARIO,
  CLASE_BOTON_TEXTO,
  TourOverlay,
} from "./TourOverlay"
import { estadoPendiente, guardarTour, leerTour } from "./persistencia"
import type { TourFlow, TourStatus } from "./types"

interface TourContextValue {
  /** Arranca el flow siempre, aunque ya se haya visto. Es el "volver a ver el tour". */
  start: (flow: TourFlow) => void
  /** Arranca solo si nunca se completo ni se salteo. Es el primer ingreso. */
  maybeStart: (flow: TourFlow) => void
  skip: () => void
  activo: boolean
}

const TourContext = createContext<TourContextValue | null>(null)

export function useTour(): TourContextValue {
  const ctx = useContext(TourContext)
  if (!ctx) throw new Error("useTour necesita estar dentro de <TourProvider>")
  return ctx
}

/**
 * Igual que `useTour` pero devuelve `null` en vez de tirar cuando no hay provider.
 *
 * Existe por un caso real: las vistas que disparan su propio tutorial tambien se
 * montan sueltas en los tests unitarios, sin chrome ni root layout. Ahi el tour
 * simplemente no existe, y eso no es motivo para romperle el render a la vista.
 *
 * Es la forma correcta de pedir el contexto de manera opcional. La alternativa que
 * aparece sola es envolver `useTour()` en un try/catch: funciona, porque el throw es
 * posterior al `useContext` y el orden de hooks queda estable, pero un hook adentro
 * de un try/catch se lee como un bug y el proximo que lo vea lo va a "arreglar".
 */
export function useTourOpcional(): TourContextValue | null {
  return useContext(TourContext)
}

interface TourProviderProps {
  children: ReactNode
  /** Router del app host. El provider no conoce TanStack ni ningun router concreto. */
  navigate: (route: string) => void
}

/**
 * Tour LINEAL: un recorrido paso 1..N que el usuario dispara o recibe en su primer
 * ingreso. Guarda el paso en curso, no solo si termino: es lo que hace que el tour
 * sobreviva a un `window.location.reload()` en el medio.
 *
 * Para los pasos que le piden al usuario HACER algo esta el otro mecanismo
 * (`OnboardingProvider`), que se apoya en el estado real de la app. Ver `types.ts`.
 */
export function TourProvider({ children, navigate }: TourProviderProps) {
  const [flow, setFlow] = useState<TourFlow | null>(null)
  const [indice, setIndice] = useState(0)

  const start = useCallback((f: TourFlow) => {
    guardarTour(f.id, estadoPendiente(f.steps[0]?.id))
    setFlow(f)
    setIndice(0)
  }, [])

  const maybeStart = useCallback((f: TourFlow) => {
    const { estado, paso } = leerTour(f.id)
    if (estado !== "pendiente") return
    // Retomamos donde quedo. Si el paso guardado ya no existe (el flow cambio sin
    // que se bumpeara el id), arrancamos de cero en vez de quedar fuera de rango.
    const i = paso ? f.steps.findIndex((s) => s.id === paso) : 0
    setFlow(f)
    setIndice(i >= 0 ? i : 0)
  }, [])

  const cerrar = useCallback(
    (estado: TourStatus) => {
      if (flow) guardarTour(flow.id, { estado })
      setFlow(null)
      setIndice(0)
    },
    [flow],
  )

  const skip = useCallback(() => cerrar("salteado"), [cerrar])

  const paso = flow?.steps[indice]

  const avanzarA = useCallback(
    (i: number) => {
      if (!flow) return
      guardarTour(flow.id, estadoPendiente(flow.steps[i]?.id))
      setIndice(i)
    },
    [flow],
  )

  const next = useCallback(() => {
    if (!flow) return
    if (indice >= flow.steps.length - 1) {
      cerrar("completado")
      return
    }
    avanzarA(indice + 1)
  }, [flow, indice, cerrar, avanzarA])

  const prev = useCallback(() => avanzarA(Math.max(0, indice - 1)), [indice, avanzarA])

  // La ruta del paso se aplica al entrar. Si el paso no declara ruta, no navegamos:
  // hay pasos que iluminan algo de la pantalla en la que el usuario ya esta.
  useEffect(() => {
    if (paso?.route) navigate(paso.route)
  }, [paso, navigate])

  // Escape saltea. Es la salida que todo overlay a pantalla completa debe tener, y
  // junto con el boton del pie es la UNICA: el clic al fondo no cierra nada.
  useEffect(() => {
    if (!flow) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") skip()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [flow, skip])

  const value = useMemo<TourContextValue>(
    () => ({ start, maybeStart, skip, activo: flow !== null }),
    [start, maybeStart, skip, flow],
  )

  const ultimo = flow ? indice === flow.steps.length - 1 : false

  return (
    <TourContext.Provider value={value}>
      {children}
      {flow && paso && (
        <TourOverlay
          id={paso.id}
          title={paso.title}
          body={paso.body}
          anchor={paso.anchor}
          placement={paso.placement}
          contador={`${indice + 1} / ${flow.steps.length}`}
          footer={
            <>
              <button type="button" onClick={skip} className={`mr-auto ${CLASE_BOTON_TEXTO}`}>
                Saltar el tour
              </button>
              {indice > 0 && (
                <button type="button" onClick={prev} className={CLASE_BOTON_SECUNDARIO}>
                  Atras
                </button>
              )}
              <button type="button" onClick={next} className={CLASE_BOTON_PRIMARIO}>
                {ultimo ? "Listo" : "Siguiente"}
              </button>
            </>
          }
        />
      )}
    </TourContext.Provider>
  )
}
