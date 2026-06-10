import { SignIn } from "@clerk/clerk-react"
import type { ReactNode } from "react"

export function LoginPage(): ReactNode {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-alt">
      <div className="flex flex-col items-center gap-6">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-foreground">AI-Native N4</h1>
          <p className="text-sm text-muted-foreground mt-1">Panel de administración</p>
        </div>
        <SignIn routing="hash" />
      </div>
    </div>
  )
}
