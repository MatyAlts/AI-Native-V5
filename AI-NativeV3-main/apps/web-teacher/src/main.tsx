import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import { routeTree } from "./routeTree.gen"

// Selector dinámico de tenant: inyectamos `x-selected-tenant` en todo
// fetch a `/api/*`. El proxy de Vite lo lee y lo propaga como
// `X-Tenant-Id` al api-gateway. Si no hay selección guardada, el proxy
// cae al default del docente01.
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

// ADR-022: routing type-safe del web-teacher con file-based routes.
// El plugin de Vite genera `routeTree.gen.ts` automáticamente al levantar
// `pnpm dev`. Si `routeTree.gen.ts` no existe en CI, agregar `--watch` o
// pre-build en el script de build.

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
