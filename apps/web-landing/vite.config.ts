import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  // Se sirve bajo /landing/ (ver infrastructure/nginx-frontends.conf). La raiz
  // `/` la ocupa web-student como catch-all — no se mueve para no romper URLs
  // de alumnos del piloto en curso. Sin este `base`, los assets del bundle se
  // pedirian a /assets/* y nginx los resolveria contra web-student (404).
  base: "/landing/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5172,
  },
  build: {
    outDir: "dist",
    // Los sourcemaps eran el 78% del dist (18 MB de 23 en el student) y nginx
    // los sirve publicos con `immutable, max-age=1 anio` — o sea que cualquiera
    // se bajaba el codigo fuente entero. Y no los consumia nadie: ningun
    // frontend tiene error tracker que los suba. Se apagan por default; para
    // debuggear un build de prod, `VITE_SOURCEMAP=1 pnpm build`.
    sourcemap: process.env.VITE_SOURCEMAP === "1",
  },
})
