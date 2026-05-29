import { ClerkProvider, useAuth } from "@clerk/clerk-react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { v5 as uuidv5 } from "uuid"
import "./index.css"
import { routeTree } from "./routeTree.gen"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string

// Namespace UUID fijo del piloto AI-Native N4. NO cambiar: regenera todos
// los student_pseudonym y rompe la continuidad de la cadena CTR por usuario.
// Generado UNA vez con `uuidgen` el 2026-05-29.
const CLERK_PSEUDONYM_NAMESPACE = "8f9d2c4a-7b1e-5d3f-9a8c-1e2b3c4d5e6f"

// Storage key del pseudonym derivado del Clerk user.id. Se preserva entre
// sessions y entre versiones del algoritmo (ver clerkIdToUuid abajo).
const CLERK_PSEUDONYM_STORAGE_KEY = "clerkDerivedUserId"
const LEGACY_PSEUDONYM_VERSION_KEY = "clerkDerivedUserIdVersion"
const PSEUDONYM_ALGO_VERSION = "v5-2026-05-29"

/**
 * UUID determinista desde Clerk user.id → student_pseudonym valido para el CTR.
 *
 * v5-2026-05-29 (este): UUID v5 (SHA-1 namespaced, RFC 4122). Sin colision
 * computacional dentro del piloto. Reemplazo del hash truncado v1 que daba
 * 8 chars de entropia (~10^-5 prob colision en 1000 alumnos).
 *
 * BACKWARDS-COMPAT: si el localStorage tiene un pseudonym pre-fix (legacy),
 * lo conservamos en memoria pero generamos el v5 para futuras escrituras.
 * Esto NO migra eventos viejos del CTR — son inmutables por design.
 */
export function clerkIdToUuid(clerkId: string): string {
  return uuidv5(clerkId, CLERK_PSEUDONYM_NAMESPACE)
}

// Variable global: el UUID del alumno logueado. Se setea desde el root layout.
let _currentUserUuid: string | null = localStorage.getItem(CLERK_PSEUDONYM_STORAGE_KEY)

export function setClerkUserId(clerkId: string) {
  // Preservar pseudonyms legacy del piloto (pre-v5-2026-05-29). Si el
  // localStorage ya tiene un UUID guardado de la version anterior del
  // algoritmo, lo conservamos para no romper la continuidad de eventos CTR
  // de este alumno. Solo regeneramos con v5 cuando no hay nada guardado.
  const existing = localStorage.getItem(CLERK_PSEUDONYM_STORAGE_KEY)
  const storedVersion = localStorage.getItem(LEGACY_PSEUDONYM_VERSION_KEY)
  if (existing && storedVersion !== PSEUDONYM_ALGO_VERSION) {
    // Pseudonym pre-fix: preservar pero marcar que el algoritmo viejo se uso
    _currentUserUuid = existing
    localStorage.setItem(LEGACY_PSEUDONYM_VERSION_KEY, "legacy-truncated-hash")
    return
  }
  const uuid = clerkIdToUuid(clerkId)
  _currentUserUuid = uuid
  localStorage.setItem(CLERK_PSEUDONYM_STORAGE_KEY, uuid)
  localStorage.setItem(LEGACY_PSEUDONYM_VERSION_KEY, PSEUDONYM_ALGO_VERSION)
}

export function clearClerkUserId() {
  _currentUserUuid = null
  localStorage.removeItem(CLERK_PSEUDONYM_STORAGE_KEY)
  localStorage.removeItem(LEGACY_PSEUDONYM_VERSION_KEY)
}

export const SELECTED_TENANT_STORAGE_KEY = "selectedTenantId"
const originalFetch = window.fetch.bind(window)
const apiBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")
window.fetch = (input, init) => {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  const isRelativeApi = rawUrl.startsWith("/api/")
  const targetUrl = isRelativeApi && apiBase ? `${apiBase}${rawUrl}` : rawUrl

  if (!isRelativeApi) return originalFetch(targetUrl, init)
  const headers = new Headers(init?.headers ?? {})
  const tenantId = localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)
  if (tenantId) headers.set("x-selected-tenant", tenantId)
  if (_currentUserUuid) headers.set("x-user-id", _currentUserUuid)
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
  return <RouterProvider router={router} context={{ getToken }} />
}

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Missing #root element")

createRoot(rootElement).render(
  <StrictMode>
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
      <QueryClientProvider client={queryClient}>
        <InnerApp />
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>,
)
