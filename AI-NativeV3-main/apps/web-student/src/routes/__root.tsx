import { SignInButton, SignUpButton, UserButton, useAuth, useUser } from "@clerk/clerk-react"
import { AuditFooter, HelpButton } from "@platform/ui"
import { Outlet, createRootRouteWithContext } from "@tanstack/react-router"
import { useCallback, useEffect, useState, type ReactNode } from "react"
import { setClerkUserId, clearClerkUserId, DEV_NO_CLERK, DEV_STUDENT_UUID } from "../auth"
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

// Identidad normalizada del alumno, independiente de Clerk. En modo Clerk se
// arma desde `useUser`; en dev se hardcodea (ver DevRootLayout).
interface AuthUser {
  id: string
  fullName: string | null
  email: string | null
}

/**
 * Resuelve inscripcion del alumno. Recibe el `authUser` ya normalizado para no
 * depender de hooks de Clerk: asi el path dev (sin ClerkProvider) lo reutiliza.
 * `isDev` evita derivar el pseudonym via clerkIdToUuid (en dev ya esta fijado
 * en memoria por setDevStudentId con el UUID exacto del seed).
 */
function useEnrollment(authUser: AuthUser | null, isDev: boolean) {
  const [state, setState] = useState<EnrollState>("loading")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!authUser) {
      clearClerkUserId()
      setState("loading")
      return
    }
    if (!isDev) setClerkUserId(authUser.id)

    let cancelled = false
    ;(async () => {
      // Auto-llenado + re-vinculación: en CADA carga pusheamos el perfil
      // (idempotente). Esto resuelve la asignación docente por email: si el
      // admin promovió este correo a docente, acá queda vinculado a su user_id.
      try {
        await fetch("/api/v1/users/me/profile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ full_name: authUser.fullName || null, email: authUser.email }),
        })
      } catch {
        /* silencioso */
      }
      if (cancelled) return

      // Ruteo por rol: si es docente (tiene comisiones asignadas), va al panel
      // docente. Así, tras ser promovido, un F5 lo lleva solo a /teacher/.
      try {
        const r = await fetch("/api/v1/comisiones/mis")
        if (r.ok) {
          const j = await r.json()
          if (!cancelled && Array.isArray(j.data) && j.data.length > 0) {
            window.location.href = "/teacher/"
            return
          }
        }
      } catch {
        /* si falla, seguimos como alumno */
      }
      if (cancelled) return

      // Flujo alumno: SIEMPRE re-validar contra el server. La comision cacheada
      // en localStorage puede estar stale (te movieron de comision, o quedo de
      // otra identidad que uso este browser) y daba estado "enrolled" con una
      // comision a la que el backend despues te tira 403. Usamos el cache solo
      // como render optimista (para no flickerear) y reconciliamos con
      // /materias/mias, que refleja las inscripciones vigentes.
      const saved = localStorage.getItem(ENROLLED_COMISION_KEY)
      if (saved) setState("enrolled")
      try {
        const r = await fetch("/api/v1/materias/mias")
        const j = await r.json()
        if (cancelled) return
        const comisiones = Array.isArray(j.data)
          ? j.data.map((m: { comision_id: string }) => m.comision_id)
          : []
        if (comisiones.length > 0) {
          // Si la cacheada ya no esta entre las vigentes, la reemplazamos.
          const valid = saved && comisiones.includes(saved) ? saved : comisiones[0]
          localStorage.setItem(ENROLLED_COMISION_KEY, valid)
          setState("enrolled")
        } else {
          // Sin inscripcion vigente: limpiar el cache stale y pedir codigo.
          localStorage.removeItem(ENROLLED_COMISION_KEY)
          setState("need-code")
        }
      } catch {
        // Error de red: si habia cache lo respetamos (ya seteamos "enrolled"
        // arriba, optimista); sin cache, pedimos codigo.
        if (!cancelled && !saved) setState("need-code")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authUser?.id, isDev])

  const enroll = useCallback(async (code: string) => {
    if (!authUser) return
    setError(null)

    // El código se resuelve server-side: el backend busca la comisión por
    // invite_code e inscribe al alumno. El frontend NUNCA lista los códigos.
    const r = await fetch("/api/v1/comisiones/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_code: code.trim().toUpperCase() }),
    })

    if (r.ok) {
      const comision = await r.json()
      localStorage.setItem(ENROLLED_COMISION_KEY, comision.id)
      setState("enrolled")
      window.location.reload()
    } else if (r.status === 404) {
      setError("Codigo invalido. Pedile el codigo correcto a tu docente.")
    } else {
      setError("No se pudo inscribir. Intenta de nuevo.")
    }
  }, [authUser?.id])

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

// Carcasa compartida: header + footer. Las acciones del header y el cuerpo se
// inyectan por props para que el path dev no monte componentes de Clerk.
function LayoutShell({
  headerActions,
  children,
  showAudit = true,
}: {
  headerActions: ReactNode
  children: ReactNode
  // FIX-18 (F-12): el footer expone versiones de prompt/labeler/clasificador.
  // Solo se muestra a usuarios autenticados, no en la pantalla de login.
  showAudit?: boolean
}) {
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
        <div className="flex items-center gap-3">{headerActions}</div>
      </header>

      {children}

      {showAudit && <AuditFooter episodeId={null} classifierHash={null} />}
    </div>
  )
}

// Cuerpo segun estado de inscripcion (compartido por ambos paths).
function EnrollmentBody({
  state,
  error,
  enroll,
}: {
  state: EnrollState
  error: string | null
  enroll: (code: string) => void
}) {
  if (state === "loading") {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-soft animate-pulse">Cargando...</p>
      </div>
    )
  }
  if (state === "need-code") {
    return <InviteCodeScreen onSubmit={enroll} error={error} />
  }
  return <Outlet />
}

// Path real: auth via Clerk.
function ClerkRootLayout() {
  const { isSignedIn } = useAuth()
  const { user } = useUser()
  const authUser: AuthUser | null =
    isSignedIn && user
      ? {
          id: user.id,
          fullName:
            user.fullName ?? [user.firstName, user.lastName].filter(Boolean).join(" ").trim() ?? null,
          email: user.primaryEmailAddress?.emailAddress ?? null,
        }
      : null
  const { state, error, enroll } = useEnrollment(authUser, false)

  const headerActions = isSignedIn ? (
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
  )

  return (
    <LayoutShell headerActions={headerActions} showAudit={!!isSignedIn}>
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
      ) : (
        <EnrollmentBody state={state} error={error} enroll={enroll} />
      )}
    </LayoutShell>
  )
}

// Path dev sin Clerk: alumno hardcodeado, siempre "logueado".
function DevRootLayout() {
  const authUser: AuthUser = {
    id: DEV_STUDENT_UUID,
    fullName: "Alumno 01 (dev)",
    email: "alumno01@demo-uni.edu",
  }
  const { state, error, enroll } = useEnrollment(authUser, true)

  const headerActions = (
    <>
      <TenantSelector />
      <HelpButton title="Tutor Socratico" content={helpContent.episode} />
      <span className="text-xs text-muted-soft">alumno01 · dev</span>
    </>
  )

  return (
    <LayoutShell headerActions={headerActions}>
      <EnrollmentBody state={state} error={error} enroll={enroll} />
    </LayoutShell>
  )
}

function RootLayout() {
  // Flag build-time constante: la rama nunca cambia entre renders.
  return DEV_NO_CLERK ? <DevRootLayout /> : <ClerkRootLayout />
}
