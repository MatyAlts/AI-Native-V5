## ADDED Requirements

### Requirement: PageContainer subtitles SHALL NOT expose raw UUID slices

Los subtítulos del componente `PageContainer` en el `web-teacher` SHALL render el `nombre` o `codigo` de la comisión seleccionada, NUNCA un slice del UUID raw. Las views afectadas son `MaterialesView.tsx`, `TareasPracticasView.tsx`, y `ProgressionView.tsx`.

La fuente del display string SHALL ser `comision?.nombre || comision?.codigo || ""`. Mientras el contrato TS de `Comision` no exponga formalmente `nombre`, el cast `(c as any).nombre` SHALL ser usado como soft-fallback.

#### Scenario: Comisión con `nombre` definido

- **WHEN** la comisión seleccionada tiene `nombre = "A-Mañana"` y `codigo = "A-MA"`
- **THEN** el subtítulo SHALL renderizar `"A-Mañana"` (preferencia por `nombre`)

#### Scenario: Comisión sin `nombre`, fallback a `codigo`

- **WHEN** la comisión seleccionada tiene `nombre = undefined` o `null`, y `codigo = "B-TA"`
- **THEN** el subtítulo SHALL renderizar `"B-TA"` (fallback a `codigo`)

#### Scenario: Sin comisión seleccionada

- **WHEN** no hay comisión seleccionada (selector vacío)
- **THEN** el subtítulo SHALL renderizar string vacío o un placeholder neutro, NUNCA `"Comision: aaaaaaaa..."` (slice de UUID)

### Requirement: 0 instancias de UUID slice como subtítulo en frontends

El repo SHALL NOT contener ningún match para el patrón `"Comision: \${.*slice"` en archivos `apps/web-*/src/**/*.tsx` después de aplicar este change.

#### Scenario: Verificación post-PR con ripgrep

- **WHEN** se ejecuta `rg "Comision: \\\$\\{.*slice" apps/web-teacher/src/` desde la raíz del repo
- **THEN** el comando SHALL devolver 0 matches y exit code 1 (no encontrado)
