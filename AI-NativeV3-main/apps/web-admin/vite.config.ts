import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// NOTE: @tanstack/router-plugin (TanStackRouterVite) intentionally NOT wired —
// routing en este frontend es useState-based (App.tsx + Sidebar.tsx); el
// plugin escaneaba src/routes/ inexistente y tiraba ENOENT al startup.
// Migración a TanStack Router type-safe está prevista para F2-F3. Cuando llegue,
// re-importar { TanStackRouterVite } from "@tanstack/router-plugin/vite" y
// agregar TanStackRouterVite({ target: "react", autoCodeSplitting: true }) al
// inicio del array `plugins` (debe ir ANTES de react()). Dep ya está en package.json.
// `test` es config de Vitest, no de Vite. Vitest la lee del mismo archivo
// pero la firma de `defineConfig` de vite (con exactOptionalPropertyTypes)
// la rechaza. Para evitar acoplar el typecheck al paquete `vitest/config`
// (que arrastra otra versión de vite y rompe los plugin types), declaramos
// el bloque por separado y lo mergeamos con un type que lo permite.
const vitestConfig = {
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
} as const

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://127.0.0.1:8000",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            // Dev-only: el api-gateway no tiene JWT validator (Keycloak
            // sin realm). Inyectamos X-* para que dev_trust_headers acepte.
            proxyReq.removeHeader("authorization")
            proxyReq.setHeader("x-user-id", "33333333-3333-3333-3333-333333333333")
            // Tenant dinámico: si el cliente manda `x-selected-tenant`
            // (escrito por el selector de universidad del admin), usamos eso.
            // Fallback al tenant UTN cuando no hay selección (primer arranque
            // o usuario fuera del selector).
            const clientTenant = req.headers["x-selected-tenant"]
            const tenantId =
              typeof clientTenant === "string" && clientTenant.length === 36
                ? clientTenant
                : "7a7a143c-31f8-461b-be08-d86ac36b41a3"
            proxyReq.setHeader("x-tenant-id", tenantId)
            proxyReq.setHeader("x-user-email", "admin@demo-uni.edu")
            proxyReq.setHeader("x-user-roles", "docente_admin,superadmin")
          })
        },
      },
      // /health del api-gateway (sin auth) — usado por el HomePage para mostrar
      // estado live. No va por /api porque el ROUTE_MAP no lo registra.
      "/health": {
        target: process.env.VITE_API_URL || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  ...vitestConfig,
})
