# frontend-microcopy-tildes

## Purpose

Capability that ensures todos los strings visibles al usuario en los 3 frontends (`web-admin`, `web-teacher`, `web-student`) usen acentos correctos del español rioplatense. Cierra una deuda histórica donde un comentario "SIN tildes" había sido extendido por cargo cult desde scripts Python con stdout (regla cp1252 en Windows) a archivos TSX servidos al browser — cosas distintas, regla aplicable solo a la primera. Establece la separación clara: TSX visible al usuario USA tildes, Python stdout PRESERVA ASCII.

## Requirements

### Requirement: Visible UI strings in 3 frontends SHALL use proper Spanish accents

Todos los strings visibles al usuario en los 3 frontends (`web-admin`, `web-teacher`, `web-student`) SHALL usar los acentos correctos del español rioplatense. Las palabras afectadas en la primera pasada (`closing-adrs-and-frontend-polish`) incluyen `"administración"`, `"prácticos"`, `"prácticas"`, `"gestión"`, `"cátedra"`, `"automáticamente"`, `"canónicos"`, `"canónica"`, `"automáticas"`.

Para cualquier nuevo string visible que se agregue en futuros changes, las tildes correctas SHALL ser parte del primer commit — no se acepta deuda nueva.

#### Scenario: HomePage del web-admin renderiza con tildes

- **WHEN** el usuario carga la HomePage del `web-admin`
- **THEN** la palabra `"administración"` SHALL aparecer con tilde en el `é`, sin variantes ASCII

#### Scenario: TareasPracticasView del web-teacher renderiza con tildes

- **WHEN** el usuario navega a la vista de Tareas Prácticas en `web-teacher`
- **THEN** el header SHALL renderizar `"Trabajos prácticos"` con tilde en la `á`

### Requirement: Python scripts with stdout SHALL preserve ASCII contract

Los scripts Python del repo (`scripts/check-rls.py`, `apps/academic-service/src/academic_service/seeds/casbin_policies.py`, etc.) SHALL mantener los strings ASCII puros que imprimen a stdout. La regla del CLAUDE.md sobre cp1252 en Windows sigue vigente — el contrato de tildes es exclusivamente para UI visible (TSX), NO para Python stdout.

#### Scenario: scripts/check-rls.py mantiene `[OK]`/`[FAIL]` ASCII

- **WHEN** se inspecciona `scripts/check-rls.py`
- **THEN** los marcadores de status SHALL ser ASCII (`[OK]`, `[FAIL]`), NUNCA `✓` o `✗` o variantes con tildes

### Requirement: 0 instancias de palabras sin tildes en TSX visible

El repo SHALL NOT contener matches para los stems `practicos`, `practicas`, `administracion`, `gestion`, `automaticamente`, `automaticas`, `catedra`, `canonicos`, `canonica` (todos sin tilde) como palabras completas en archivos `apps/web-*/src/**/*.tsx`, excluyendo el directorio `routes/` que contiene URL slugs no traducibles del file-based router.

La verificación usa **word-boundary** (`-w` flag de ripgrep) para evitar falsos positivos sobre formas verbales legítimas que no llevan tilde (ej. `gestionar`, `gestiones`, infinitivos del verbo `gestionar`).

#### Scenario: Verificación post-PR con ripgrep

- **WHEN** se ejecuta `rg -iw "(practicos|practicas|administracion|gestion|automaticamente|automaticas|catedra|canonicos|canonica)" apps/web-*/src/ -g "*.tsx" -g "!**/routes/**"` desde la raíz del repo
- **THEN** el comando SHALL devolver 0 matches y exit code 1 (no encontrado)

#### Scenario: Verbos infinitivos legítimos sin tilde se preservan

- **WHEN** un archivo TSX contiene la palabra `gestionar` (infinitivo del verbo, correcto sin tilde)
- **THEN** la verificación con `-w` NO SHALL fallar — el word-boundary excluye `gestionar` del match de `gestion`

#### Scenario: Route paths del file-based router se preservan

- **WHEN** un archivo bajo `apps/web-*/src/routes/**/*.tsx` contiene un path slug como `/tareas-practicas` (definición canónica de ruta, NO user-facing copy)
- **THEN** la verificación con `-g "!**/routes/**"` NO SHALL fallar — los slugs de las rutas son contratos de URL del SPA, no microcopy traducible. Los labels visibles en el sidebar (en `__root.tsx`) sí deben tener tildes correctas; el slug debajo del label, NO.
