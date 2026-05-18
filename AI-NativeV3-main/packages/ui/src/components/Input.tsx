import type { InputHTMLAttributes } from "react"
import { cn } from "../utils/cn"

/**
 * Input — paleta v2.
 * Borde definido (no anémico), focus-ring brand acento Stack Blue.
 * Sin dark mode adhoc — los modales dark proveen su propio contexto.
 */
export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-9 w-full rounded-md border border-border bg-surface px-3 py-1 text-sm",
        "text-ink placeholder:text-muted-soft",
        "shadow-[0_1px_2px_0_rgba(0,0,0,0.03)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand focus-visible:border-accent-brand",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
}
