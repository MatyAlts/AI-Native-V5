import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { routeTree } from "./routeTree.gen"

// Selector dinámico de tenant: inyectamos `x-selected-tenant` en todo
// fetch a `/api/*`. El proxy de Vite lo lee y lo propaga como
// `X-Tenant-Id` al api-gateway. Sin selección, el proxy cae al default.
export const SELECTED_TENANT_STORAGE_KEY = "selectedTenantId"
const originalFetch = window.fetch.bind(window)
window.fetch = (input, init) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  if (!url.startsWith("/api/")) return originalFetch(input, init)
  const tenantId = window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)
  if (!tenantId) return originalFetch(input, init)
  const headers = new Headers(init?.headers ?? {})
  headers.set("x-selected-tenant", tenantId)
  return originalFetch(input, { ...init, headers })
}

// Routing type-safe del web-student con file-based routes (espejo del web-teacher).
// El plugin TanStackRouterVite genera `routeTree.gen.ts` automaticamente al
// arrancar `pnpm dev` o `pnpm build`. Si el archivo no existe en CI, basta con
// pre-build de vite (el plugin lo crea on-the-fly).

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
})

// Placeholder de auth — cuando integremos keycloak-js, esto pasa al provider real.
const getToken = async (): Promise<string | null> => "dev-token"

const router = createRouter({
  routeTree,
  context: { getToken },
  defaultPreload: "intent",
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Missing #root element")

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
