# web-teacher-page-headers

## Purpose

Capability that ensures los subtítulos del componente `PageContainer` en las views del `web-teacher` exponen el nombre o código humano-legible de la comisión seleccionada, NUNCA un slice raw del UUID. Esto reemplaza el patrón `${comisionId.slice(0, 8)}...` (que mostraba `Comision: aaaaaaaa...`) por un display amigable resuelto via hook `useComisionLabel(comisionId)` exportado desde `ComisionSelector.tsx` — DRY pragmatic que reaprovecha la lógica `nombre || codigo` ya existente.

Soft-dependency declarada: mientras el contrato TS de `Comision` no exponga formalmente `nombre`, el cast `(c as any).nombre` se preserva como mecanismo forward-compat. Cuando Epic 1 (`seed-template-id-and-manifest-reconcile`, ya archivada) o un change futuro agregue `nombre: string | null` al type, el cast se elimina sin tocar el contrato runtime.

## Requirements

### Requirement: PageContainer subtitles SHALL NOT expose raw UUID slices

Los subtítulos del componente `PageContainer` en el `web-teacher` SHALL render el `nombre` o `codigo` de la comisión seleccionada, NUNCA un slice del UUID raw. Las views afectadas son `MaterialesView.tsx`, `TareasPracticasView.tsx`, y `ProgressionView.tsx`.

La fuente del display string SHALL ser `comision?.nombre || comision?.codigo || ""`. Mientras el contrato TS de `Comision` no exponga formalmente `nombre`, el cast `(c as any).nombre` SHALL ser usado como soft-fallback.

La resolución `comisionId → label` SHALL hacerse via hook reutilizable `useComisionLabel(comisionId)` exportado desde `apps/web-teacher/src/components/ComisionSelector.tsx` para evitar duplicación de la fetch+find en cada view.

#### Scenario: Comisión con `nombre` definido

- **WHEN** la comisión seleccionada tiene `nombre = "A-Mañana"` y `codigo = "A-MA"`
- **THEN** el subtítulo SHALL renderizar `"A-Mañana"` (preferencia por `nombre`)

#### Scenario: Comisión sin `nombre`, fallback a `codigo`

- **WHEN** la comisión seleccionada tiene `nombre = undefined` o `null`, y `codigo = "B-TA"`
- **THEN** el subtítulo SHALL renderizar `"B-TA"` (fallback a `codigo`)

#### Scenario: Sin comisión seleccionada

- **WHEN** no hay comisión seleccionada (selector vacío)
- **THEN** el subtítulo SHALL renderizar string vacío o un placeholder neutro, NUNCA `"Comision: aaaaaaaa..."` (slice de UUID)

#### Scenario: Fetch del listado de comisiones falla

- **WHEN** la llamada a `comisionesApi.listMine()` falla (red caída, 500, timeout)
- **THEN** el hook `useComisionLabel` SHALL devolver el slice del UUID como fallback inicial para evitar layout shift, sin lanzar excepciones que rompan el render de la página

### Requirement: 0 instancias de UUID slice como subtítulo en frontends

El repo SHALL NOT contener ningún match para el patrón `"Comision: \${.*slice"` en archivos `apps/web-*/src/**/*.tsx` después de aplicar cualquier change que toque subtítulos del PageContainer.

#### Scenario: Verificación post-PR con ripgrep

- **WHEN** se ejecuta `rg "Comision: \\\$\\{.*slice" apps/web-teacher/src/` desde la raíz del repo
- **THEN** el comando SHALL devolver 0 matches y exit code 1 (no encontrado)
