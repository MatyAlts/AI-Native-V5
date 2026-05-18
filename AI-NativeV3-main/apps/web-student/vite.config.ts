import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { TanStackRouterVite } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// File-based routing con TanStack Router (mismo pattern que web-teacher).
// El plugin escanea `src/routes/` y genera `src/routeTree.gen.ts`
// automaticamente al startup / build. MUST ir ANTES de react() segun docs.
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
  plugins: [
    TanStackRouterVite({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
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
            // Dev: respetar headers del cliente (ModHeader/Requestly)
            // o usar defaults si el browser no los manda.
            proxyReq.removeHeader("authorization")
            const setDefault = (name: string, fallback: string) => {
              if (!proxyReq.getHeader(name)) proxyReq.setHeader(name, fallback)
            }
            setDefault("x-user-id", "e19354fb-c05a-4535-a0bf-a7d3ea09692d") // alumno01
            // Tenant dinámico: si el cliente manda `x-selected-tenant`
            // (escrito por el TenantSelector via monkey-patch en main.tsx),
            // usamos eso. Fallback a la Universidad Final E2E.
            const clientTenant = req.headers["x-selected-tenant"]
            const tenantFallback = "d6269f07-022f-4181-a24d-db7e16e655ae"
            const tenantId =
              typeof clientTenant === "string" && clientTenant.length === 36
                ? clientTenant
                : tenantFallback
            proxyReq.setHeader("x-tenant-id", tenantId)
            setDefault("x-user-email", "alumno01@demo-uni.edu")
            setDefault("x-user-roles", "estudiante,classifier_worker")
          })
        },
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  ...vitestConfig,
})
