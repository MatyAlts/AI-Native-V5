// Constantes compartidas SIN dependencias del router. Vive aparte de main.tsx
// para romper el import circular main.tsx -> routeTree.gen -> componentes ->
// main.tsx (causaba "Cannot access X before initialization" en HMR).
export const SELECTED_TENANT_STORAGE_KEY = "selectedTenantId"
