import path from "node:path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

/**
 * Suite aparte: los tests que corren PYODIDE DE VERDAD (`tests/pyodide/`).
 *
 * Vive fuera de `vite.config.ts` por dos razones, ninguna cosmetica:
 *
 * 1. **Costo.** Levantar el interprete cuesta ~1,5 s y el bootstrap del editor
 *    otro tanto; el test del watchdog espera 5 s de reloj porque el limite que
 *    verifica son 5 s. La suite normal corre en ~10 s y se corre en cada push:
 *    meterle esto adentro la vuelve otra cosa. Aca corre en su propio job.
 * 2. **Aislamiento.** Un interprete WASM por worker, `fileParallelism` apagado:
 *    varios Pyodide simultaneos en la misma maquina compiten por memoria y el
 *    watchdog —que mide tiempo de reloj— empieza a dar falsos positivos.
 *
 * NO hereda `vite.config.ts` a proposito: el plugin de TanStack Router regenera
 * `routeTree.gen.ts` al arrancar y aca no se renderiza ninguna ruta.
 *
 * Correr con: `pnpm test:pyodide`
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/pyodide/**/*.test.tsx", "tests/pyodide/**/*.test.ts"],
    // Un solo archivo a la vez: cada uno levanta su propio interprete WASM.
    fileParallelism: false,
    // Arrancar Pyodide + el bootstrap del editor no entra en los 5 s default.
    testTimeout: 60_000,
    hookTimeout: 60_000,
    alias: {
      "monaco-editor": path.resolve(__dirname, "./tests/_monacoMock.ts"),
    },
  },
} as Parameters<typeof defineConfig>[0])
