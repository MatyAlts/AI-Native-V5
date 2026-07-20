## ADDED Requirements

### Requirement: Sidebar topSlot in expanded mode SHALL be visually separated from first NavGroup

El componente `Sidebar` compartido (`packages/ui/src/components/Sidebar.tsx`) SHALL renderizar el `topSlot` con separación visual respecto del primer `NavGroup` cuando el Sidebar está en modo expanded. La separación se logra agregando las utilities Tailwind `pb-3 border-b border-slate-800/50 mb-3` al wrapper del `topSlot` cuando `expanded === true`.

La firma pública del componente `Sidebar` NO SHALL cambiar — no se introduce prop `topSlotSeparator` ni similar. La decisión visual queda fija en el componente.

#### Scenario: Sidebar expanded con topSlot

- **WHEN** el `Sidebar` se renderiza con `expanded={true}` y un `topSlot` no vacío
- **THEN** el wrapper del `topSlot` SHALL tener las clases `pb-3`, `border-b`, `border-slate-800/50`, y `mb-3` aplicadas

#### Scenario: Sidebar collapsed con topSlot

- **WHEN** el `Sidebar` se renderiza con `expanded={false}` y un `topSlot` no vacío
- **THEN** el wrapper del `topSlot` NO SHALL tener las clases de separación (`pb-3 border-b ...`) — la separación solo aplica en expanded

#### Scenario: Sidebar expanded sin topSlot

- **WHEN** el `Sidebar` se renderiza con `expanded={true}` y `topSlot={undefined}` o ausente
- **THEN** no SHALL renderizarse ningún wrapper de topSlot, y el primer `NavGroup` SHALL ser el primer elemento del Sidebar sin separadores residuales

### Requirement: Web-teacher sidebar SHALL show separator between ComisionSelector and first NavGroup

En la app `web-teacher`, donde el `Sidebar` recibe `<ComisionSelectorRouted />` como `topSlot`, el separador SHALL ser visible al usuario cuando el sidebar está expanded.

#### Scenario: Web-teacher en modo expanded

- **WHEN** el usuario carga `web-teacher` con el sidebar en modo expanded
- **THEN** entre el `ComisionSelector` y el primer grupo de navegación SHALL aparecer una línea horizontal sutil (border-bottom + spacing)
