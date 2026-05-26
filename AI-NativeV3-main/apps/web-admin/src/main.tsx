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
const apiBase = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "")
window.fetch = (input, init) => {
  const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  const isRelativeApi = rawUrl.startsWith("/api/")
  const targetUrl = isRelativeApi && apiBase ? `${apiBase}${rawUrl}` : rawUrl

  const tenantId = isRelativeApi ? window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY) : null
  if (!tenantId) return originalFetch(targetUrl, init)
  const headers = new Headers(init?.headers ?? {})
  headers.set("x-selected-tenant", tenantId)
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

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Missing #root element")

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
