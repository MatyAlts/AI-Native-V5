---
name: help-system-content
description: >
  Ensures HelpButton is always present in Dashboard pages and that help content
  follows the established structure in helpContent.tsx.
  Trigger: When adding a HelpButton to any Dashboard component, or creating a new Dashboard page.
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## When to Use

- Creating a new Dashboard page component
- Adding a form modal to an existing Dashboard page
- Any time `PageContainer` is used without a `helpContent` prop
- Any time a `Modal` for create/edit is added without a `HelpButton` inside it

---

## Context — Starting from Zero

`Dashboard/src/utils/helpContent.tsx` does not exist yet when this skill is first used.
The first Dashboard change must create it as an empty record and grow it as pages are added.

```tsx
// Dashboard/src/utils/helpContent.tsx — create this file on first Dashboard change
import type { ReactNode } from 'react'

type HelpContentMap = Record<string, ReactNode>

export const helpContent: HelpContentMap = {
  // Add one key per Dashboard page, following the structure below
}
```

Every subsequent Dashboard page appends its key to this record.

---

## Critical Patterns

### Rule 1: HelpButton is MANDATORY in ALL Dashboard pages

Every page MUST pass `helpContent` to `PageContainer`. No exceptions.

```tsx
// CORRECT
<PageContainer
  title="Mi Pagina"
  description="..."
  helpContent={helpContent.myPage}   // <-- always present
>

// WRONG - missing helpContent
<PageContainer title="Mi Pagina" description="...">
```

### Rule 2: Content lives in helpContent.tsx — NEVER inline in the page

All page-level help content goes in `Dashboard/src/utils/helpContent.tsx`.
Import it in the page, never write JSX inline for the page-level help.

```tsx
// In the page file
import { helpContent } from '../utils/helpContent'

<PageContainer helpContent={helpContent.categories} ...>
```

### Rule 3: Form modals get an inline HelpButton (size="sm")

Every create/edit modal includes a `HelpButton` at the top of the form that explains the fields.
This content IS inline (not in helpContent.tsx) because it describes the form, not the page.

```tsx
<Modal isOpen={modal.isOpen} onClose={modal.close} title="Nueva Categoria" ...>
  <form id="my-form" action={formAction} className="space-y-4">
    <div className="flex items-center gap-2 mb-2">
      <HelpButton
        title="Formulario de Categoria"
        size="sm"
        content={
          <div className="space-y-3">
            <p><strong>Completa los siguientes campos</strong> para crear o editar una categoria:</p>
            <ul className="list-disc pl-5 space-y-2">
              <li><strong>Nombre:</strong> Descripcion del campo. Es obligatorio.</li>
            </ul>
            <div className="bg-zinc-800 p-3 rounded-lg mt-3">
              <p className="text-orange-400 font-medium text-sm">Consejo:</p>
              <p className="text-sm mt-1">Texto del consejo.</p>
            </div>
          </div>
        }
      />
      <span className="text-sm text-[var(--text-tertiary)]">Ayuda sobre el formulario</span>
    </div>
    {/* form fields */}
  </form>
</Modal>
```

---

## helpContent.tsx Entry Structure

File: `Dashboard/src/utils/helpContent.tsx`

Every entry follows this exact JSX structure:

```tsx
myPage: (
  <div className="space-y-4 text-zinc-300">
    {/* 1. Page title */}
    <p className="text-lg font-medium text-[var(--text-inverse)]">Titulo de la Pagina</p>

    {/* 2. One-sentence intro */}
    <p>Breve descripcion de para que sirve esta pagina.</p>

    {/* 3. Feature list */}
    <ul className="list-disc list-inside space-y-2 ml-4">
      <li><strong>Accion principal:</strong> Descripcion de la accion.</li>
      <li><strong>Otra accion:</strong> Descripcion.</li>
    </ul>

    {/* 4. Tip/note box — use one of these variants: */}

    {/* Variant A — neutral tip (Consejo / Nota / Importante) */}
    <div className="bg-zinc-800 p-4 rounded-lg mt-4">
      <p className="text-orange-400 font-medium">Consejo:</p>
      <p className="text-sm mt-1">Texto del consejo.</p>
    </div>

    {/* Variant B — danger warning (cascade deletes, irreversible actions) */}
    <div className="bg-red-900/50 p-4 rounded-lg mt-4 border border-red-700">
      <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
      <p className="text-sm mt-1">Esta accion no se puede deshacer.</p>
    </div>
  </div>
),
```

**Rules for the tip box:**
- Use `bg-zinc-800` + `text-orange-400` for: Consejo, Nota, Importante, Horarios, Precios, Uso tipico, Programa de fidelidad
- Use `bg-red-900/50 border border-red-700` + `text-[var(--danger-text)]` only when the action causes irreversible data loss (cascade deletes)
- Always include exactly one tip box per entry (can add a second only if a page warrants both a tip and a warning)

---

## Example Entry — Categories page

Use this as a reference when writing the first entries:

```tsx
categories: (
  <div className="space-y-4 text-zinc-300">
    <p className="text-lg font-medium text-[var(--text-inverse)]">Gestion de Categorias</p>
    <p>
      Las categorias son las secciones principales del menu de una sucursal (ej: Comidas, Bebidas, Postres).
    </p>
    <ul className="list-disc list-inside space-y-2 ml-4">
      <li><strong>Crear categoria:</strong> Haz clic en "Nueva Categoria" para agregar una seccion al menu.</li>
      <li><strong>Editar categoria:</strong> Modifica nombre, icono, imagen y estado.</li>
      <li><strong>Ordenar:</strong> Define el orden de aparicion en el menu.</li>
      <li><strong>Subcategorias:</strong> Visualiza cuantas subcategorias tiene cada categoria.</li>
    </ul>
    <div className="bg-zinc-800 p-4 rounded-lg mt-4">
      <p className="text-orange-400 font-medium">Nota:</p>
      <p className="text-sm mt-1">
        Cada sucursal tiene su propio conjunto de categorias. Primero selecciona una sucursal desde el
        Dashboard para ver y gestionar sus categorias.
      </p>
    </div>
    <div className="bg-red-900/50 p-4 rounded-lg mt-2 border border-red-700">
      <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
      <p className="text-sm mt-1">
        Al eliminar una categoria se eliminaran todas sus subcategorias y productos.
      </p>
    </div>
  </div>
),
```

Tip box with a status list (tables page example):

```tsx
<div className="bg-zinc-800 p-4 rounded-lg mt-4">
  <p className="text-orange-400 font-medium">Estados de mesa:</p>
  <ul className="text-sm mt-2 space-y-1">
    <li><strong>Libre:</strong> Mesa disponible para nuevos clientes.</li>
    <li><strong>Solicito Pedido:</strong> Cliente esperando para ordenar.</li>
  </ul>
</div>
```

---

## Adding a New Entry — Checklist

1. If `Dashboard/src/utils/helpContent.tsx` does not exist yet — create it with the empty record shown above
2. Add a key to the `helpContent` record following the JSX structure (title → intro → list → tip box)
3. Write content in Spanish, no accents needed (avoid encoding issues)
4. Import `helpContent` in the new page and pass the key to `PageContainer`
5. Add a `size="sm"` `HelpButton` inside each create/edit modal in that page

---

## Tone Guidelines

- Language: Spanish (sin tildes para evitar encoding issues)
- Style: Instructivo y conciso — "Haz clic en X para Y"
- Feature list items: `<strong>Label:</strong> one-sentence explanation`
- Tip box label examples: "Consejo", "Nota", "Importante", "Advertencia", "Precios por sucursal", "Horarios", "Actualizacion masiva"
- No marketing language — just functional guidance

---

## Resources

- **Content file to create**: `Dashboard/src/utils/helpContent.tsx`
- **HelpButton component**: `Dashboard/src/components/ui/HelpButton.tsx` (create alongside the file)
- **PageContainer prop**: `helpContent?: ReactNode` — add this prop when scaffolding PageContainer
- **Reference page pattern**: see `dashboard-crud-page` skill for full page structure
