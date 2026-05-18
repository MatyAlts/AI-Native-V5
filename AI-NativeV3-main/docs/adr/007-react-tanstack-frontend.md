# ADR-007 — React 19 + TanStack en frontends

- **Estado**: Aceptado
- **Fecha**: 2026-04
- **Deciders**: Alberto Cortez
- **Tags**: stack, frontend

## Contexto y problema

Definir el stack canónico de los tres frontends (`web-admin`, `web-teacher`, `web-student`). Deben compartir librerías (UI, auth, CTR client, contratos) para evitar reimplementar lógica y mantener consistencia visual.

Requisitos:

- Tablas grandes con filtros, sorting, paginación (web-admin).
- Formularios complejos con validación en tiempo real (rúbricas, provisioning, config de cursos).
- Streaming SSE del tutor (web-student).
- Editor Monaco integrado (web-student).
- Sin Server-Side Rendering necesario: las apps son SPAs detrás de auth.

## Opciones consideradas

### Opción A — React 19 + Vite + TanStack
Ecosistema React mainstream. Vite como bundler moderno. TanStack (Query, Router, Form, Table) cubre las necesidades de estado remoto, ruteo y tablas/formularios complejos.

### Opción B — Next.js 15
Más features integradas (SSR, ISR, Server Actions) pero no necesitamos ninguna. Complejidad extra de routing filesystem y Server Components que no aportan.

### Opción C — SvelteKit
Menor adopción. Biblioteca de componentes más chica. Candidatos de hiring más escasos.

### Opción D — Vue 3 + Nuxt
Funcional pero menor adopción en el ecosistema educativo argentino.

## Decisión

**Opción A — React 19 + Vite + TanStack.**

Stack específico:
- **React 19** con Hooks y Suspense.
- **Vite 6** como dev server y bundler.
- **TypeScript estricto** con `noUncheckedIndexedAccess` y `exactOptionalPropertyTypes`.
- **TanStack Router** (type-safe routing + code splitting).
- **TanStack Query** (estado remoto: caché, refetch, optimistic updates).
- **TanStack Form** (validación con Zod).
- **TanStack Table** (tablas grandes).
- **Tailwind CSS v4** + `shadcn/ui` como base de componentes.
- **Monaco Editor** para `web-student`.
- **Recharts** para gráficos.
- **Biome** para lint/format (más rápido que ESLint + Prettier).
- **Vitest + Testing Library + Playwright** para tests.

Deployment: archivos estáticos servidos por Nginx/CDN con config de runtime en `config.json` inyectado.

## Consecuencias

### Positivas
- TanStack Query hace el estado remoto trivial; Zustand queda solo para casos puntuales.
- Type-safety de punta a punta con Zod en la borde.
- Tres apps comparten `@platform/ui`, `@platform/auth-client`, `@platform/ctr-client`.
- Vite build <30s incluso para web-student con Monaco.

### Negativas
- TanStack Router es menos conocido que React Router — curva de aprendizaje.
- Tailwind v4 está en beta: riesgo de breaking changes hasta que se estabilice.
- shadcn/ui es copy-paste de componentes (no es una librería npm); cada cambio upstream requiere re-copiar.

### Neutras
- Migración a Next.js futura es posible si se necesita SSR.

## Referencias

- [TanStack docs](https://tanstack.com/)
- `apps/web-*/package.json`
- `packages/ui/`
