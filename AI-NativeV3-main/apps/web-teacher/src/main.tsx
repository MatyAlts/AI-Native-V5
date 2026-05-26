import { ClerkProvider, useAuth } from "@clerk/clerk-react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { routeTree } from "./routeTree.gen"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string

export const SELECTED_TENANT_STORAGE_KEY = "selectedTenantId"
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
