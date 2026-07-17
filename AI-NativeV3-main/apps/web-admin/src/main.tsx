import { ClerkProvider, SignIn, SignedIn, SignedOut } from "@clerk/clerk-react"
import { installApiFetchInterceptor } from "@platform/auth-client/fetch"
import { ConfirmProvider, ErrorBoundary } from "@platform/ui"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import "./index.css"
import { SELECTED_TENANT_STORAGE_KEY } from "./constants"

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string
// Dev sin Clerk: si no hay publishable key, la identidad la inyecta el proxy
// de Vite (x-user-id/x-tenant-id/x-user-roles) y el backend corre con
// dev_trust_headers. Permite levantar el front sin cuenta Clerk.
const DEV_NO_CLERK = !CLERK_PUBLISHABLE_KEY

// Interceptor de fetch compartido (P-18/P-13/P-12): reescritura /api/,
// Authorization Bearer con espera corta y cacheada del token de Clerk, y
// timeout por request. La unica pieza especifica del admin es el header
// x-selected-tenant. Sin Bearer el gateway responderia 401 en prod (no hay
// proxy de Vite que inyecte X-* fuera de dev).
installApiFetchInterceptor({
  apiBase: (import.meta.env.VITE_API_URL ?? "") as string,
  devNoClerk: DEV_NO_CLERK,
  dynamicHeaders: () => ({
    "x-selected-tenant": window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY),
  }),
})

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

const appTree = (
  <QueryClientProvider client={queryClient}>
    <ErrorBoundary>
      <ConfirmProvider>
        <App />
      </ConfirmProvider>
    </ErrorBoundary>
  </QueryClientProvider>
)

createRoot(rootElement).render(
  <StrictMode>
    {DEV_NO_CLERK ? (
      appTree
    ) : (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
        {/* Sin sesión: pantalla de login de Clerk. Con sesión: la app. El acceso
            real al panel lo da el rol superadmin (gateway CLERK_ADMIN_EMAILS). */}
        <SignedOut>
          <div className="min-h-screen flex items-center justify-center">
            <SignIn forceRedirectUrl="/admin/" signUpForceRedirectUrl="/admin/" />
          </div>
        </SignedOut>
        <SignedIn>{appTree}</SignedIn>
      </ClerkProvider>
    )}
  </StrictMode>,
)
