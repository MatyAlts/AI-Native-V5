#!/usr/bin/env python3
"""Genera los esqueletos de los 3 frontends React del monorepo.

Cada frontend tiene:
- package.json con deps de React 19 + Vite + TanStack + Tailwind v4 + shadcn
- vite.config.ts
- tsconfig.json estricto
- index.html
- src/main.tsx + App.tsx con router placeholder
- src/config.ts con lectura de env
- tailwind setup
"""

from pathlib import Path
from textwrap import dedent

ROOT = Path("/home/claude/platform")
APPS = ROOT / "apps"

FRONTENDS = [
    {
        "name": "web-admin",
        "title": "Plataforma — Admin",
        "description": "Gestión institucional (superadmin y docente_admin)",
        "port": 5173,
    },
    {
        "name": "web-teacher",
        "title": "Plataforma — Docente",
        "description": "Gestión de contenido, rúbricas, seguimiento y corrección",
        "port": 5174,
    },
    {
        "name": "web-student",
        "title": "Plataforma — Estudiante",
        "description": "Resolución de problemas con tutor socrático",
        "port": 5175,
    },
]


def package_json(app: dict) -> str:
    name = app["name"]
    return dedent(f"""\
        {{
          "name": "@platform/{name}",
          "version": "0.1.0",
          "private": true,
          "type": "module",
          "scripts": {{
            "dev": "vite --port {app["port"]}",
            "build": "tsc -b && vite build",
            "preview": "vite preview",
            "lint": "biome check src",
            "lint:fix": "biome check --write src",
            "typecheck": "tsc --noEmit",
            "test": "vitest run",
            "test:watch": "vitest"
          }},
          "dependencies": {{
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
            "@tanstack/react-router": "^1.90.0",
            "@tanstack/react-query": "^5.60.0",
            "@tanstack/react-form": "^0.38.0",
            "@tanstack/react-table": "^8.20.0",
            "keycloak-js": "^25.0.0",
            "@platform/ui": "workspace:*",
            "@platform/auth-client": "workspace:*",
            "@platform/contracts": "workspace:*",
            "zod": "^3.23.0",
            "lucide-react": "^0.460.0",
            "clsx": "^2.1.0",
            "tailwind-merge": "^2.5.0"
          }},
          "devDependencies": {{
            "@biomejs/biome": "^1.9.0",
            "@tanstack/router-devtools": "^1.90.0",
            "@tanstack/router-plugin": "^1.90.0",
            "@types/react": "^19.0.0",
            "@types/react-dom": "^19.0.0",
            "@vitejs/plugin-react": "^4.3.0",
            "tailwindcss": "^4.0.0-beta.7",
            "@tailwindcss/vite": "^4.0.0-beta.7",
            "typescript": "~5.6.0",
            "vite": "^6.0.0",
            "vitest": "^2.1.0",
            "@testing-library/react": "^16.1.0",
            "jsdom": "^25.0.0"
          }}
        }}
    """)


def vite_config() -> str:
    return dedent("""\
        import { defineConfig } from "vite"
        import react from "@vitejs/plugin-react"
        import tailwindcss from "@tailwindcss/vite"
        import { TanStackRouterVite } from "@tanstack/router-plugin/vite"
        import path from "node:path"

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
                target: process.env.VITE_API_URL || "http://localhost:8000",
                changeOrigin: true,
                rewrite: (p) => p.replace(/^\\/api/, ""),
              },
            },
          },
          build: {
            outDir: "dist",
            sourcemap: true,
          },
          test: {
            environment: "jsdom",
            globals: true,
          },
        })
    """)


def tsconfig_json() -> str:
    return dedent("""\
        {
          "compilerOptions": {
            "target": "ES2023",
            "lib": ["ES2023", "DOM", "DOM.Iterable"],
            "jsx": "react-jsx",
            "module": "ESNext",
            "moduleResolution": "bundler",
            "resolveJsonModule": true,
            "allowImportingTsExtensions": true,
            "noEmit": true,
            "isolatedModules": true,
            "useDefineForClassFields": true,
            "allowSyntheticDefaultImports": true,
            "esModuleInterop": true,
            "forceConsistentCasingInFileNames": true,
            "strict": true,
            "noImplicitAny": true,
            "noImplicitReturns": true,
            "noImplicitThis": true,
            "noUnusedLocals": true,
            "noUnusedParameters": true,
            "noFallthroughCasesInSwitch": true,
            "noUncheckedIndexedAccess": true,
            "exactOptionalPropertyTypes": true,
            "skipLibCheck": true,
            "paths": {
              "@/*": ["./src/*"]
            }
          },
          "include": ["src", "vite.config.ts"]
        }
    """)


def index_html(app: dict) -> str:
    return dedent(f'''\
        <!doctype html>
        <html lang="es">
          <head>
            <meta charset="UTF-8" />
            <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <meta name="description" content="{app["description"]}" />
            <title>{app["title"]}</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.tsx"></script>
          </body>
        </html>
    ''')


def main_tsx(app: dict) -> str:
    return dedent("""\
        import { StrictMode } from "react"
        import { createRoot } from "react-dom/client"
        import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
        import App from "./App"
        import "./index.css"

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
    """)


def app_tsx(app: dict) -> str:
    return dedent(f"""\
        import {{ useEffect, useState }} from "react"

        interface HealthResponse {{
          service: string
          version: string
          status: string
        }}

        export default function App() {{
          const [health, setHealth] = useState<HealthResponse | null>(null)
          const [error, setError] = useState<string | null>(null)

          useEffect(() => {{
            fetch("/api/")
              .then((r) => r.json())
              .then(setHealth)
              .catch((e) => setError(String(e)))
          }}, [])

          return (
            <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-50">
              <header className="border-b border-slate-200 dark:border-slate-800 p-6">
                <h1 className="text-2xl font-semibold">{app["title"]}</h1>
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                  {app["description"]}
                </p>
              </header>

              <main className="p-6 max-w-4xl mx-auto space-y-4">
                <section className="rounded-lg border border-slate-200 dark:border-slate-800 p-6">
                  <h2 className="text-lg font-medium mb-2">Estado de la API</h2>
                  {{error && (
                    <p className="text-red-600 dark:text-red-400">Error: {{error}}</p>
                  )}}
                  {{!error && !health && <p>Conectando...</p>}}
                  {{health && (
                    <dl className="grid grid-cols-2 gap-2 text-sm">
                      <dt className="text-slate-500">Servicio</dt>
                      <dd className="font-mono">{{health.service}}</dd>
                      <dt className="text-slate-500">Estado</dt>
                      <dd className="font-mono">{{health.status}}</dd>
                      <dt className="text-slate-500">Versión</dt>
                      <dd className="font-mono">{{health.version}}</dd>
                    </dl>
                  )}}
                </section>

                <section className="rounded-lg border border-slate-200 dark:border-slate-800 p-6">
                  <h2 className="text-lg font-medium mb-2">Fase actual: F0 — Fundaciones</h2>
                  <p className="text-sm text-slate-600 dark:text-slate-400">
                    Este es el esqueleto inicial. La funcionalidad se desarrolla en fases
                    siguientes según el plan documentado en{{" "}}
                    <code className="font-mono text-xs">docs/plan-detallado-fases.md</code>.
                  </p>
                </section>
              </main>
            </div>
          )
        }}
    """)


def index_css() -> str:
    return dedent("""\
        @import "tailwindcss";

        @theme {
          --font-sans: "Inter", system-ui, sans-serif;
          --font-mono: "JetBrains Mono", ui-monospace, monospace;
        }

        html {
          font-family: var(--font-sans);
          -webkit-font-smoothing: antialiased;
        }

        code, pre {
          font-family: var(--font-mono);
        }
    """)


def biome_json() -> str:
    return dedent("""\
        {
          "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
          "organizeImports": { "enabled": true },
          "formatter": {
            "enabled": true,
            "indentStyle": "space",
            "indentWidth": 2,
            "lineWidth": 100
          },
          "linter": {
            "enabled": true,
            "rules": {
              "recommended": true,
              "correctness": {
                "noUnusedVariables": "error",
                "noUnusedImports": "error"
              },
              "style": {
                "noNonNullAssertion": "warn"
              },
              "suspicious": {
                "noExplicitAny": "warn"
              }
            }
          },
          "javascript": {
            "formatter": {
              "quoteStyle": "double",
              "semicolons": "asNeeded",
              "trailingCommas": "all"
            }
          }
        }
    """)


def vitest_setup() -> str:
    return dedent("""\
        import "@testing-library/jest-dom/vitest"
    """)


def readme(app: dict) -> str:
    return dedent(f"""\
        # {app["name"]}

        {app["description"]}

        **Puerto dev**: {app["port"]}

        ## Desarrollo local

        ```bash
        cd apps/{app["name"]}
        pnpm install        # solo primera vez si no lo instalaste desde root
        pnpm dev            # arranca en http://localhost:{app["port"]}
        ```

        El frontend proxyea `/api/*` al backend definido en `VITE_API_URL`
        (por defecto `http://localhost:8000`).

        ## Scripts

        ```bash
        pnpm build          # build de producción
        pnpm preview        # preview del build
        pnpm lint           # Biome lint
        pnpm lint:fix       # autofix
        pnpm typecheck      # tsc --noEmit
        pnpm test           # vitest
        ```

        ## Stack

        - React 19 + TypeScript estricto
        - Vite 6 como dev server y bundler
        - TanStack Router, Query, Form, Table
        - Tailwind CSS v4 (zero-config via plugin Vite)
        - Keycloak.js para autenticación
        - Biome para lint/format
        - Vitest + Testing Library para tests unitarios
    """)


def main() -> None:
    for app in FRONTENDS:
        app_dir = APPS / app["name"]
        src_dir = app_dir / "src"
        public_dir = app_dir / "public"
        tests_dir = app_dir / "tests"
        for d in (src_dir, public_dir, tests_dir):
            d.mkdir(parents=True, exist_ok=True)

        (app_dir / "package.json").write_text(package_json(app))
        (app_dir / "vite.config.ts").write_text(vite_config())
        (app_dir / "tsconfig.json").write_text(tsconfig_json())
        (app_dir / "biome.json").write_text(biome_json())
        (app_dir / "index.html").write_text(index_html(app))
        (app_dir / "README.md").write_text(readme(app))

        (src_dir / "main.tsx").write_text(main_tsx(app))
        (src_dir / "App.tsx").write_text(app_tsx(app))
        (src_dir / "index.css").write_text(index_css())
        (tests_dir / "setup.ts").write_text(vitest_setup())

        # Favicon placeholder
        (public_dir / "favicon.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#185FA5">'
            '<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>'
            "</svg>\n"
        )

        print(f"✓ {app['name']} generado")

    print(f"\nTotal: {len(FRONTENDS)} frontends creados")


if __name__ == "__main__":
    main()
