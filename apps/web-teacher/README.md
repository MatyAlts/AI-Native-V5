# web-teacher

Gestión de contenido, rúbricas, seguimiento y corrección

**Puerto dev**: 5174

## Desarrollo local

```bash
cd apps/web-teacher
pnpm install        # solo primera vez si no lo instalaste desde root
pnpm dev            # arranca en http://localhost:5174
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
