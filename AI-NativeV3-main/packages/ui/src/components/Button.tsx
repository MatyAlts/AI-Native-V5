import type { ButtonHTMLAttributes, ReactNode } from "react"
import { cn } from "../utils/cn"

type Variant = "primary" | "secondary" | "ghost" | "danger"
type Size = "sm" | "md" | "lg"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
}

/* Paleta v2 — "Stack Blue institucional".
   primary: acento brand (#185FA5 OKLCH) — honra el favicon UNSL.
   secondary: surface-alt (off-white cálido) sobre ink — densidad académica, no SaaS.
   ghost: transparente con hover sutil sobre surface-alt.
   danger: severity profundo (no Tailwind red-600 saturado). */
const variants: Record<Variant, string> = {
  primary:
    "bg-accent-brand text-white hover:bg-accent-brand-deep focus-visible:ring-accent-brand",
  secondary:
    "bg-surface-alt text-ink hover:bg-border-soft focus-visible:ring-border-strong",
  ghost:
    "bg-transparent text-ink hover:bg-surface-alt focus-visible:ring-border-strong",
  danger: "bg-danger text-white hover:bg-danger/90 focus-visible:ring-danger",
}

const sizes: Record<Size, string> = {
  sm: "px-2.5 py-1 text-sm",
  md: "px-3.5 py-2 text-sm",
  lg: "px-5 py-2.5 text-base",
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}
