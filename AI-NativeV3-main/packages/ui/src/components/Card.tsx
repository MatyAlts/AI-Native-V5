import type { HTMLAttributes } from "react"
import { cn } from "../utils/cn"

/**
 * Card — contenedor base con jerarquía estructural visible.
 *
 * Paleta v2: surface blanco sobre canvas off-white, borde definido (no
 * `border-slate-200` anémico), sombra suave. Densidad académica > whitespace
 * SaaS — padding 16px (p-4) por default, no p-6 que infla el chrome.
 */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface",
        "shadow-[0_1px_2px_0_rgba(0,0,0,0.04),0_1px_3px_0_rgba(0,0,0,0.05)]",
        className,
      )}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col gap-1 p-4 pb-3 border-b border-border-soft", className)}
      {...props}
    />
  )
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "text-base font-semibold leading-tight tracking-tight text-ink",
        className,
      )}
      {...props}
    />
  )
}

export function CardDescription({
  className,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs text-muted leading-relaxed", className)} {...props} />
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...props} />
}

export function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 p-4 pt-3 border-t border-border-soft",
        className,
      )}
      {...props}
    />
  )
}
