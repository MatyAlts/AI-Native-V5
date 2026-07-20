import type { Transition, Variants } from "framer-motion"

/** Easing expo-out: entrada sobria, sensacion de aterrizaje. */
export const EXPO_OUT = [0.16, 1, 0.3, 1] as const

/** Viewport compartido para reveals al scroll: se dispara una vez, con margen. */
export const VIEWPORT = { once: true, margin: "-12% 0px -12% 0px" } as const

/** Contenedor que escalona la entrada de sus hijos. */
export function staggerParent(stagger = 0.08, delayChildren = 0): Variants {
  return {
    hidden: {},
    visible: {
      transition: { staggerChildren: stagger, delayChildren },
    },
  }
}

/** Hijo que sube y aparece. `reduced` colapsa el desplazamiento. */
export function fadeUp(reduced: boolean, y = 22, duration = 0.8): Variants {
  return {
    hidden: reduced ? { opacity: 0 } : { opacity: 0, y },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration, ease: EXPO_OUT },
    },
  }
}

/** Transicion para el dibujado de un trazo (stroke-dashoffset via pathLength). */
export function drawStroke(reduced: boolean, duration = 1.4, delay = 0): Transition {
  return reduced ? { duration: 0.001, delay: 0 } : { duration, delay, ease: EXPO_OUT }
}
