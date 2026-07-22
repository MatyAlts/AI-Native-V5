import { cn } from "@platform/ui"
import type { ComponentPropsWithoutRef, ReactNode } from "react"

/** Contenedor centrado con padding fluido. Ancho maximo de lectura comoda. */
export function Wrap({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("mx-auto w-full max-w-[1240px] px-[clamp(20px,5vw,72px)]", className)}>
      {children}
    </div>
  )
}

/** Label de seccion en Martian Mono, versales, celeste. Con un tick a la izquierda. */
export function Kicker({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn("kicker inline-flex items-center gap-3", className)}>
      <span className="h-px w-8 bg-celeste-deep/60" aria-hidden="true" />
      {children}
    </span>
  )
}

type CTAProps = ComponentPropsWithoutRef<"a"> & {
  variant?: "solid" | "ghost"
}

/** CTA de la landing: pill celeste solido (accion principal) o ghost con borde tinta. */
export function CTA({ variant = "solid", className, children, ...rest }: CTAProps) {
  return (
    <a
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-full px-7 py-3.5 text-[15px] font-semibold transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-celeste-deep focus-visible:ring-offset-paper",
        variant === "solid"
          ? "bg-celeste text-white shadow-[0_10px_28px_-10px_rgba(47,132,198,0.55)] hover:bg-celeste-deep hover:shadow-[0_14px_34px_-10px_rgba(47,132,198,0.6)] hover:-translate-y-0.5"
          : "border border-ink/20 text-ink hover:border-ink/45 hover:bg-ink/[0.03]",
        className,
      )}
      {...rest}
    >
      {children}
    </a>
  )
}
