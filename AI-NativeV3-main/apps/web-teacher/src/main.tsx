import { ClerkProvider, SignedIn, SignedOut, SignIn, useAuth, useUser } from "@clerk/clerk-react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode, useEffect, useState } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { comisionesApi } from "./lib/api"
import { routeTree } from "./routeTree.gen"
import { SELECTED_TENANT_STORAGE_KEY } from "./constants"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string
// Dev sin Clerk: si no hay publishable key, la identidad (docente) la inyecta
// el proxy de Vite y el backend corre con dev_trust_headers.
const DEV_NO_CLERK = !CLERK_PUBLISHABLE_KEY

const originalFetch = window.fetch.bind(window)
const apiBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")

// Espera robusta del token de Clerk para requests /api/. El interceptor
// best-effort anterior dejaba salir el request SIN Bearer cuando la sesion de
// Clerk todavia no estaba lista (window.Clerk inexistente, o session null en el
// primer render). Esos requests caian a dev_trust en el gateway y usaban el
// user_id por defecto del nginx -> el front terminaba pidiendo datos de una
// comision ajena -> 403 de identidad cruzada (assert_comision_access). Ahora,
// con un usuario logueado, esperamos hasta tener token (con timeout duro) antes
// de mandar; solo salimos sin Bearer si Clerk confirma que no hay sesion.
type ClerkLike = {
  loaded?: boolean
  load?: () => Promise<unknown>
  user?: unknown
  session?: { getToken: () => Promise<string | null> } | null
}
async function getClerkToken(): Promise<string | null> {
  if (DEV_NO_CLERK) return null
  const deadlineMs = Date.now() + 5000
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
  const readClerk = () => (window as unknown as { Clerk?: ClerkLike }).Clerk
  let clerk = readClerk()
  while (!clerk && Date.now() < deadlineMs) {
    await sleep(50)
    clerk = readClerk()
  }
  if (!clerk) return null
  if (clerk.loaded === false && clerk.load) await clerk.load()
  while (Date.now() < deadlineMs) {
    const token = await clerk.session?.getToken().catch(() => null)
    if (token) return token
    // Clerk cargado sin sesion ni usuario => deslogueado: no tiene sentido esperar.
    if (clerk.loaded && !clerk.session && !clerk.user) return null
    await sleep(50)
  }
  return null
}

window.fetch = async (input, init) => {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  const isRelativeApi = rawUrl.startsWith("/api/")
  const targetUrl = isRelativeApi && apiBase ? `${apiBase}${rawUrl}` : rawUrl

  if (!isRelativeApi) return originalFetch(targetUrl, init)
  const headers = new Headers(init?.headers ?? {})
  const tenantId = window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)
  if (tenantId) headers.set("x-selected-tenant", tenantId)
  // Adjuntar el token de Clerk a TODO request /api/ (cubre el push de perfil y
  // cualquier fetch suelto que no pase por authHeaders). Si ya viene Authorization
  // (de lib/api authHeaders), lo respetamos. En dev sin Clerk, window.Clerk no
  // existe y el try/catch deja que el gateway use los headers X-* del proxy.
  if (!headers.has("Authorization")) {
    // Espera el token de Clerk antes de mandar (con un usuario logueado nunca
    // sale sin Bearer). En dev sin Clerk devuelve null y el gateway cae a los
    // headers X-* del proxy de Vite.
    const token = await getClerkToken()
    if (token) headers.set("Authorization", `Bearer ${token}`)
  }
  return originalFetch(targetUrl, { ...init, headers })
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
})

const router = createRouter({
  routeTree,
  basepath: "/teacher",
  context: { getToken: async () => null },
  defaultPreload: "intent",
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

function InnerApp() {
  const { getToken } = useAuth()
  const { user } = useUser()
  // null = resolviendo; true = staff de al menos una comision; false = no docente.
  const [esDocente, setEsDocente] = useState<boolean | null>(null)

  // Re-vincula la identidad de Clerk con las comisiones que el admin le asigno
  // por email (POST /users/me/profile, idempotente) y RECIEN DESPUES resuelve si
  // es docente. Modelo: todos arrancan como alumno; solo es docente quien el
  // admin asigno a una comision (existe en usuarios_comision). El orden importa:
  // si consultaramos /comisiones/mis antes de re-vincular, daria vacio y
  // rebotaria a un docente real.
  useEffect(() => {
    if (!user) return
    let cancelled = false
    const email = user.primaryEmailAddress?.emailAddress ?? null
    const fullName =
      user.fullName ?? [user.firstName, user.lastName].filter(Boolean).join(" ").trim() ?? null
    ;(async () => {
      if (email) {
        try {
          await fetch("/api/v1/users/me/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ full_name: fullName || null, email }),
          })
        } catch {
          /* best-effort: la re-vinculacion no debe bloquear el chequeo siguiente */
        }
      }
      try {
        const res = await comisionesApi.listMine()
        if (!cancelled) setEsDocente(res.items.length > 0)
      } catch {
        if (!cancelled) setEsDocente(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user])

  // No es docente (sin comisiones asignadas): lo mandamos directo al panel de
  // alumno (`/`), donde puede ingresar el codigo de su comision. Modelo: todos
  // son alumnos hasta que el admin los asigne como docentes de una comision.
  // replace() para no dejar /teacher en el historial (evita volver con "atras").
  useEffect(() => {
    if (esDocente === false) window.location.replace("/")
  }, [esDocente])

  if (esDocente !== true) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-canvas text-sm text-muted">
        {esDocente === null ? "Verificando tu acceso…" : "Te llevamos a tu pantalla…"}
      </div>
    )
  }

  return <RouterProvider router={router} context={{ getToken }} />
}

// Dev sin Clerk: router sin token (el proxy mete los headers de identidad).
function DevApp() {
  return <RouterProvider router={router} context={{ getToken: async () => null }} />
}

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Missing #root element")

createRoot(rootElement).render(
  <StrictMode>
    {DEV_NO_CLERK ? (
      <QueryClientProvider client={queryClient}>
        <DevApp />
      </QueryClientProvider>
    ) : (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
        {/* Sin sesion: pantalla de login de Clerk. Con sesion: la app (y el
            push de perfil que vincula al docente con sus comisiones). */}
        <SignedOut>
          <div className="min-h-screen flex items-center justify-center bg-canvas">
            {/* forceRedirectUrl: sin esto Clerk redirige a "/" (que es el
                web-student) tras el login. Forzamos quedarnos en /teacher. */}
            <SignIn forceRedirectUrl="/teacher/" signUpForceRedirectUrl="/teacher/" />
          </div>
        </SignedOut>
        <SignedIn>
          <QueryClientProvider client={queryClient}>
            <InnerApp />
          </QueryClientProvider>
        </SignedIn>
      </ClerkProvider>
    )}
  </StrictMode>,
)
