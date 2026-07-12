import { Component, type ErrorInfo, type ReactNode } from "react"
import { Button } from "./Button"

interface ErrorBoundaryProps {
  children: ReactNode
  /** Titulo del fallback. Default: "Algo salio mal". */
  title?: string
  /** Descripcion del fallback. */
  description?: string
}

interface ErrorBoundaryState {
  hasError: boolean
}

/**
 * Error boundary compartido: atrapa cualquier throw/null en el arbol de React
 * (durante el render, en lifecycle o en constructores) y muestra un fallback
 * sobrio con los tokens del design system en vez de dejar la pantalla en blanco.
 *
 * Es un class component a proposito: `getDerivedStateFromError` y
 * `componentDidCatch` no tienen equivalente en hooks. Se envuelve el root de
 * cada app (dentro del QueryClientProvider, por fuera del router) para que un
 * error en cualquier vista degrade gracioso y el usuario pueda reintentar.
 *
 * NO atrapa: errores en handlers async, dentro de setTimeout, en SSR ni en el
 * propio boundary. Para esos casos sigue valiendo el manejo local (try/catch).
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Deja rastro en la consola para debug (Sentry/logging real es agenda aparte).
    console.error("[ErrorBoundary] error atrapado:", error, info.componentStack)
  }

  private handleRetry = (): void => {
    // Re-monta el arbol: si el error fue transitorio, la vista se recupera sin
    // recargar. Si persiste, el boundary vuelve a atrapar y el usuario recarga.
    this.setState({ hasError: false })
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children

    const title = this.props.title ?? "Algo salio mal"
    const description =
      this.props.description ??
      "Ocurrio un error inesperado en esta pantalla. Podes reintentar o recargar la pagina."

    return (
      <div
        role="alert"
        className="flex min-h-screen flex-col items-center justify-center gap-5 bg-canvas px-6 py-10 text-center"
      >
        <div className="max-w-md space-y-2">
          <h1 className="text-lg font-semibold text-ink">{title}</h1>
          <p className="text-sm text-muted">{description}</p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Button variant="primary" onClick={this.handleRetry}>
            Reintentar
          </Button>
          <Button variant="secondary" onClick={this.handleReload}>
            Recargar la pagina
          </Button>
        </div>
      </div>
    )
  }
}
