import { motion, useReducedMotion } from "framer-motion"
import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react"
import { EXPO_OUT, VIEWPORT } from "../lib/motion"

type RevealProps = {
  children: ReactNode
  /** Retraso de entrada, en segundos. */
  delay?: number
  /** Desplazamiento vertical inicial. */
  y?: number
  className?: string
  as?: ElementType
} & Omit<ComponentPropsWithoutRef<typeof motion.div>, "children" | "className">

/**
 * Wrapper de reveal al scroll. Un solo movimiento sobrio (subir + aparecer),
 * disparado al entrar en viewport. Respeta prefers-reduced-motion colapsando
 * el desplazamiento a un fade minimo.
 */
export function Reveal({ children, delay = 0, y = 22, className, as, ...rest }: RevealProps) {
  const reduced = useReducedMotion()
  const MotionTag = as ? motion(as) : motion.div

  return (
    <MotionTag
      className={className}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={VIEWPORT}
      transition={{ duration: 0.8, ease: EXPO_OUT, delay }}
      {...rest}
    >
      {children}
    </MotionTag>
  )
}
