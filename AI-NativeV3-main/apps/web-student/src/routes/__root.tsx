/**
 * Root layout del web-student (post-craft Fase 2).
 *
 * Pattern espejo del web-teacher:
 *   - createRootRouteWithContext para que las rutas hijas reciban `getToken`
 *     sin prop drilling.
 *   - Header global SIN selector de comisión: el alumno YA NO elige comisión.
 *     La comisión es metadata de la materia (visible en /materia/:id).
 *   - <Outlet /> renderiza la ruta hija.
 *   - <AuditFooter /> al pie en TODAS las rutas (Design Principle 2 del PRODUCT.md:
 *     "auditabilidad visible, no oculta"). El footer hoy se monta SIN episodeId
 *     porque ese estado vive ahora dentro de /episodio/$id; cuando esa ruta
 *     este activa, va a inyectar el id via search/path param y el footer va a
 *     pollear el verify (mejora pendiente; el render con null sigue siendo válido).
 */
import { SignInButton, SignUpButton, UserButton, useAuth, useUser } from "@clerk/clerk-react"
import { AuditFooter, HelpButton } from "@platform/ui"
import { Outlet, createRootRouteWithContext } from "@tanstack/react-router"
import { useEffect, useRef } from "react"
import { TenantSelector } from "../components/TenantSelector"
import { helpContent } from "../utils/helpContent"

const DEFAULT_COMISION_ID = "aaaaaaaa-0001-0001-0001-aaaaaaaaaaaa"

export interface RouterContext {
  getToken: () => Promise<string | null>
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

function useAutoEnroll() {
  const { isSignedIn } = useAuth()
  const { user } = useUser()
  const enrolled = useRef(false)

  useEffect(() => {
    if (!isSignedIn || !user || enrolled.current) return
    enrolled.current = true

    fetch(`/api/v1/comisiones/${DEFAULT_COMISION_ID}/inscripciones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_pseudonym: user.id,
        fecha_inscripcion: new Date().toISOString().slice(0, 10),
      }),
    }).catch(() => {})
  }, [isSignedIn, user])
}

function RootLayout() {
  const { isSignedIn } = useAuth()
  useAutoEnroll()

  return (
    <div className="h-dvh bg-surface-alt text-ink flex flex-col overflow-hidden">
      <header className="border-b border-border-soft px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span
            aria-hidden="true"
            className="inline-block w-1.5 h-4 rounded-sm"
            style={{ backgroundColor: "var(--color-accent-brand)" }}
          />
          <h1 className="text-sm font-semibold tracking-tight text-ink">
            Plataforma N4 <span className="text-muted-soft mx-1">·</span> UTN
          </h1>
        </div>
        <div className="flex items-center gap-3">
          {isSignedIn ? (
            <>
              <TenantSelector />
              <HelpButton title="Tutor Socratico" content={helpContent.episode} />
              <UserButton afterSignOutUrl="/" />
            </>
          ) : (
            <>
              <SignInButton mode="modal">
                <button type="button" className="text-sm font-medium text-accent-brand hover:underline">
                  Iniciar sesion
                </button>
              </SignInButton>
              <SignUpButton mode="modal">
                <button type="button" className="text-sm font-medium bg-accent-brand text-white px-3 py-1.5 rounded-md hover:opacity-90">
                  Registrarse
                </button>
              </SignUpButton>
            </>
          )}
        </div>
      </header>

      {isSignedIn ? <Outlet /> : (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4">
            <h2 className="text-2xl font-bold text-ink">Bienvenido a Plataforma N4</h2>
            <p className="text-muted-soft">Inicia sesion para acceder a tus materias y tareas practicas.</p>
            <SignInButton mode="modal">
              <button type="button" className="bg-accent-brand text-white px-6 py-2 rounded-md font-medium hover:opacity-90">
                Iniciar sesion
              </button>
            </SignInButton>
          </div>
        </div>
      )}

      <AuditFooter episodeId={null} classifierHash={null} />
    </div>
  )
}
