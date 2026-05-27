import { SignInButton, SignUpButton, UserButton, useAuth, useUser } from "@clerk/clerk-react"
import { AuditFooter, HelpButton } from "@platform/ui"
import { Outlet, createRootRouteWithContext } from "@tanstack/react-router"
import { useCallback, useEffect, useState } from "react"
import { setClerkUserId, clearClerkUserId } from "../main"
import { TenantSelector } from "../components/TenantSelector"
import { helpContent } from "../utils/helpContent"

const ENROLLED_COMISION_KEY = "enrolledComisionId"

export interface RouterContext {
  getToken: () => Promise<string | null>
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

type EnrollState = "loading" | "need-code" | "enrolled"

function useEnrollment() {
  const { isSignedIn } = useAuth()
  const { user } = useUser()
  const [state, setState] = useState<EnrollState>("loading")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isSignedIn || !user) {
      clearClerkUserId()
      setState("loading")
      return
    }
    setClerkUserId(user.id)

    const saved = localStorage.getItem(ENROLLED_COMISION_KEY)
    if (saved) {
      setState("enrolled")
    } else {
      // Verificar si ya tiene inscripción
      fetch("/api/v1/materias/mias").then(async (r) => {
        const j = await r.json()
        if (j.data && j.data.length > 0) {
          localStorage.setItem(ENROLLED_COMISION_KEY, j.data[0].comision_id)
          setState("enrolled")
        } else {
          setState("need-code")
        }
      }).catch(() => setState("need-code"))
    }
  }, [isSignedIn, user])

  const enroll = useCallback(async (code: string) => {
    if (!user) return
    setError(null)
    const uuid = localStorage.getItem("clerkDerivedUserId") || user.id

    // Buscar comisión por invite_code
    const r1 = await fetch("/api/v1/comisiones?limit=100")
    const j1 = await r1.json()
    const comision = j1.data?.find((c: { invite_code?: string }) => c.invite_code === code.trim().toUpperCase())

    if (!comision) {
      setError("Codigo invalido. Pedile el codigo correcto a tu docente.")
      return
    }

    // Inscribir
    const r2 = await fetch(`/api/v1/comisiones/${comision.id}/inscripciones`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-user-id": uuid },
      body: JSON.stringify({
        student_pseudonym: uuid,
        fecha_inscripcion: new Date().toISOString().slice(0, 10),
      }),
    })

    if (r2.status === 201 || r2.status === 409) {
      localStorage.setItem(ENROLLED_COMISION_KEY, comision.id)
      setState("enrolled")
      window.location.reload()
    } else {
      setError("No se pudo inscribir. Intenta de nuevo.")
    }
  }, [user])

  return { state, error, enroll }
}

function InviteCodeScreen({ onSubmit, error }: { onSubmit: (code: string) => void; error: string | null }) {
  const [code, setCode] = useState("")

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center space-y-6 max-w-sm">
        <div>
          <h2 className="text-2xl font-bold text-ink">Unirte a una comision</h2>
          <p className="text-muted-soft mt-2">Ingresa el codigo que te dio tu docente para acceder a la materia.</p>
        </div>
        <div className="space-y-3">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="Ej: C1-7X3K"
            className="w-full px-4 py-3 text-center text-lg font-mono tracking-widest border border-border-soft rounded-lg bg-surface focus:outline-none focus:ring-2 focus:ring-accent-brand"
            maxLength={10}
          />
          <button
            type="button"
            onClick={() => onSubmit(code)}
            disabled={code.length < 3}
            className="w-full bg-accent-brand text-white px-6 py-3 rounded-lg font-medium hover:opacity-90 disabled:opacity-50"
          >
            Unirme a la comision
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      </div>
    </div>
  )
}

function RootLayout() {
  const { isSignedIn } = useAuth()
  const { state, error, enroll } = useEnrollment()

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

      {!isSignedIn ? (
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
      ) : state === "loading" ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-muted-soft animate-pulse">Cargando...</p>
        </div>
      ) : state === "need-code" ? (
        <InviteCodeScreen onSubmit={enroll} error={error} />
      ) : (
        <Outlet />
      )}

      <AuditFooter episodeId={null} classifierHash={null} />
    </div>
  )
}
