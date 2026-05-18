import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import "./index.css"

// Selector dinámico de tenant: inyectamos `x-selected-tenant` en todo
// fetch a `/api/*`. El proxy de Vite lo lee y lo propaga como
// `X-Tenant-Id` al api-gateway. Si no hay selección guardada, omitimos
// el header y el proxy cae al default (UTN). Patch a window.fetch para
// no tocar cada call site del codebase.
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
})

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Missing #root element")

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
