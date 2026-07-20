import type { LabelHTMLAttributes } from "react"
import { cn } from "../utils/cn"

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: wrapper genérico del design system — el consumidor provee `htmlFor` y/o children (texto + control) vía `...props`; la asociación se da en el call site.
    <label
      className={cn(
        "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
        className,
      )}
      {...props}
    />
  )
}
