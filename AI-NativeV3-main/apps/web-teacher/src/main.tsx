import { ClerkProvider, SignedIn, SignedOut, SignIn, useAuth, useUser } from "@clerk/clerk-react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode, useEffect } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { routeTree } from "./routeTree.gen"
import { SELECTED_TENANT_STORAGE_KEY } from "./constants"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string
// Dev sin Clerk: si no hay publishable key, la identidad (docente) la inyecta
// el proxy de Vite y el backend corre con dev_trust_headers.
const DEV_NO_CLERK = !CLERK_PUBLISHABLE_KEY

const originalFetch = window.fetch.bind(window)
const apiBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")
window.fetch = (input, init) => {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  const isRelativeApi = rawUrl.startsWith("/api/")
  const targetUrl = isRelativeApi && apiBase ? `${apiBase}${rawUrl}` : rawUrl

  if (!isRelativeApi) return originalFetch(targetUrl, init)
  const headers = new Headers(init?.headers ?? {})
  const tenantId = window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)
  if (tenantId) headers.set("x-selected-tenant", tenantId)
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

  // Auto-llenado del perfil del docente al loguearse con Clerk. Es lo que
  // dispara la resolucion server-side: el backend matchea este email con las
  // asignaciones que el admin creo por email (usuarios_comision) y vincula la
  // identidad real del docente a sus comisiones. Sin esto, el docente se
  // loguea pero nunca aparece como docente de ninguna comision.
  useEffect(() => {
    if (!user) return
    const email = user.primaryEmailAddress?.emailAddress ?? null
    if (!email) return
    const fullName =
      user.fullName ?? [user.firstName, user.lastName].filter(Boolean).join(" ").trim() ?? null
    const key = `teacherProfilePushed_${user.id}`
    if (sessionStorage.getItem(key)) return
    void fetch("/api/v1/users/me/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: fullName || null, email }),
    })
      .then((r) => {
        if (r.ok) sessionStorage.setItem(key, "1")
      })
      .catch(() => {
        /* silencioso: no bloquea el flujo del docente */
      })
  }, [user])

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
            <SignIn forceRedirectUrl="/teacher" signUpForceRedirectUrl="/teacher" />
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
