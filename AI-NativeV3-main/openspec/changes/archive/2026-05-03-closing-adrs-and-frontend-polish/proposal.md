## Why

El piloto UNSL (defensa doctoral próxima) opera bajo el principio del **modelo híbrido honesto** declarado en `CLAUDE.md`: *"Antes de cerrar un G como 'no se hace', redactá el ADR aunque diga decidimos NO hacer esto ahora porque X, criterio para piloto-2: Y."* Hoy quedan **dos** caras del mismo problema:

1. **Track A — Documental**: G6 (desacoplamiento instrumento-intervención) ya tiene ADR-028, G3-Fase-B ya tiene ADR-027, pero **G7-ML (alertas predictivas verdaderas con modelo entrenado sobre el trayecto individual del estudiante)** todavía no tiene un ADR propio que declare formalmente la decisión de **DIFERIR a piloto-2**. El MVP estadístico (z-score vs cohorte + cuartiles privacy-safe) se cubre dentro de ADR-022, pero el comité doctoral va a preguntar específicamente por la versión >1σ vs baseline propio del estudiante (mencionada literalmente en `audi1.md` G7), y esa decisión sigue siendo "deuda silenciosa": no hay un único ADR al que apuntar.
2. **Track B — Polish residual visible**: tras el minimalist-ui pass + auto-select (mem #4), quedan tres papercuts honestos pegados a la demo de defensa: la home del web-admin sigue siendo un bloque de texto sin métricas reales, varias páginas muestran subtítulos con UUID truncado en vez del nombre/código de la comisión, y hay tildes faltantes en titulares (legado del `check-rls`/cp1252 que se filtró a microcopy). El sidebar del web-teacher tiene el `ComisionSelector` pegado al primer NavGroup sin separación visual.

La oportunidad: **un único change pequeño** cierra el lado documental con un ADR (no tres como decía el brief original — verificación contra `docs/adr/` confirma que ADR-027 y ADR-028 ya existen) y el lado visible con cuatro fixes acotados, sin tocar lógica de negocio.

## What Changes

### Track A — Cierre documental (1 ADR nuevo + 2 cross-references)

- **Crear ADR-032** — "G7-ML: Alertas predictivas con modelo entrenado sobre baseline individual del estudiante (DIFERIDO a piloto-2)". Sección Decisión = **DIFERIR**. Criterio de revisitar: dataset etiquetado mínimo (longitud de trayecto ≥ N episodios), validación cruzada split por estudiante, calibración κ vs intervención docente real. Tesis Capítulo 20 ya declara el espacio.
- **Cross-reference desde `CLAUDE.md`** (sección "Modelo híbrido honesto") agregando ADR-032 al inventario de "Agenda Cap 20 con ADR redactado".
- **NO crear nuevos ADRs para G6 ni G3-Fase-B**: ADR-028 y ADR-027 ya cubren esas decisiones formalmente. El brief original asumía slots libres en 032/033/034 — verificación local confirma que sólo 032 corresponde.

### Track B — Frontend polish (4 ítems acotados)

1. **`web-admin` HomePage — KPI cards reales** (`apps/web-admin/src/pages/HomePage.tsx`): reemplazar la sección "Recursos disponibles" (lista textual) por **3 KPI cards** alimentadas por endpoints existentes en el ROUTE_MAP del api-gateway:
   - `# Universidades` ← `GET /api/v1/universidades` (count del array).
   - `# Comisiones activas` ← `GET /api/v1/comisiones?estado=activa` (filtro existente).
   - `# Episodios cerrados (últimos 7 días)` ← `GET /api/v1/analytics/cohort/{any}/progression` agregado, **o** caer a "—" si requiere comisión específica (degradación graciosa).
   - **Nota sobre `integrity_compromised`**: NO incluir como KPI en este pase. Hoy no hay endpoint público para "% de episodios con integrity_compromised=true a nivel tenant"; mostrar un 0 hardcoded sería deshonesto, y exponerlo requiere tocar `analytics-service`. Queda fuera de scope.
2. **`web-teacher` subtítulos con UUID truncado**: tres views (`MaterialesView.tsx:193`, `TareasPracticasView.tsx:197`, `ProgressionView.tsx:70`) hoy muestran `Comision: aaaaaaaa...` (slice del UUID). Reemplazar por `comision.nombre || comision.codigo` resuelto desde el contexto compartido. **Dependencia con Epic 1 (`seed-template-id-and-manifest-reconcile`)**: si Epic 1 todavía no expone `nombre` en la API, el fallback usa `codigo` ("A-Mañana", "B-Tarde") — soft-fallback documentado, no hard-block.
3. **Microcopy / tildes** en titulares y subtítulos visibles:
   - `web-admin/src/pages/HomePage.tsx:32`: `"administracion"` → `"administración"`.
   - `web-admin/src/utils/helpContent.tsx:9`: `"Administracion"` → `"Administración"`.
   - `web-teacher/src/views/TareasPracticasView.tsx:196`: `"Trabajos practicos"` → `"Trabajos prácticos"`.
   - `web-teacher/src/views/TemplatesView.tsx:154`: `"Gestion de templates canonicos a nivel catedra... se instancian automaticamente"` → con tildes correctas.
   - `web-student/src/components/TareaSelector.tsx:70,80` + `web-student/src/utils/helpContent.tsx:13`: `"trabajos practicos"` → `"trabajos prácticos"`.
   - **Excepción**: scripts Python con stdout (`check-rls.py`, `casbin_policies.py`) **se mantienen ASCII** — la regla de `CLAUDE.md` sobre cp1252 sigue vigente; este barrido es solo UI visible.
4. **`web-teacher` sidebar — separación del `topSlot`**: en `packages/ui/src/components/Sidebar.tsx`, agregar `pb-3 border-b border-slate-800/50 mb-3` al wrapper del `topSlot` cuando está expanded para separar el `ComisionSelector` del primer NavGroup. Sin tocar la firma del componente.

## Capabilities

### New Capabilities
- `admin-home-kpis`: KPI cards en `web-admin` HomePage alimentadas por endpoints existentes del api-gateway, con degradación graciosa cuando un endpoint no está disponible.

### Modified Capabilities
- `web-teacher-page-headers`: subtítulos de PageContainer dejan de exponer UUIDs truncados; usan el nombre o código de la comisión.
- `frontend-microcopy-tildes`: titulares y descripciones visibles en los 3 frontends corrigen tildes faltantes (no toca scripts ni stdout backend).
- `sidebar-topslot-separation`: el `topSlot` del Sidebar compartido tiene separación visual del primer NavGroup.

## Impact

- **Código tocado**: ~120 LOC netos. `apps/web-admin/src/pages/HomePage.tsx` (rewrite parcial: ~40 LOC), `packages/ui/src/components/Sidebar.tsx` (~3 LOC), 5 views/helpContent del web-teacher/student (string replaces). Tres views del web-teacher consumen el contexto de comisión que ya existe (`ComisionSelectorRouted` lo persiste en URL + localStorage).
- **Documentación**: 1 ADR nuevo (`docs/adr/032-g7-ml-alertas-predictivas-baseline-individual.md`), 1 sección actualizada en `CLAUDE.md`.
- **API**: cero contratos nuevos. Todos los endpoints usados ya están en el ROUTE_MAP (`/api/v1/universidades`, `/api/v1/comisiones`, `/api/v1/analytics/*`). El `nombre` de comisión queda como soft-dependency sobre Epic 1.
- **Tests**: `packages/ui` agrega 1 test de Sidebar verificando que el `topSlot` renderiza con el classes de separación. `apps/web-admin` agrega 1 test de HomePage que mockea los 3 endpoints y verifica que las cards renderizan los counts. Total: ~2 tests nuevos.
- **Riesgos**:
  - **Track A**: el ADR-032 puede invitar la pregunta "¿por qué no piloto-2 ahora mismo?" — la sección "Criterio para revisitar" debe explicitar el dataset mínimo (volumen de episodios + diversidad de trayectos) que hoy no existe.
  - **Track B item #1**: si los endpoints devuelven 401/403 en dev (caso del minimalist-ui pase 2 — `/api/` requiere auth), las KPI cards deben caer al estado `—` con tooltip explicativo, no romper la página.
  - **Track B item #2**: si Epic 1 no merge antes que este change, el fallback a `codigo` debe testearse explícitamente — el contrato TS de `Comision` ya tiene el cast `(c as any).nombre` documentado en mem #4.
  - **Track A**: verificar slot 032 disponible **inmediatamente antes** del PR (no desde caché): el catálogo cambia rápido — al cierre de iter 2 había 31 ADRs, hoy 32 reservados sin contar este. Si entre tanto se asigna 032, mover a 033 sin tocar el resto del proposal.
- **Non-goals**:
  - **Implementar G6, G7-ML o G3-Fase-B** — todo el punto del Track A es declarar formalmente que NO se hacen pre-defensa.
  - Migrar a un `Card` primitive en `@platform/ui` (deferred — minimalist pass ya cerró ese debate).
  - Agregar páginas nuevas, rutas o navegación.
  - Tocar la lógica del `ComisionSelector` o cambiar la SOT (sigue siendo URL search params + mirror localStorage).
  - Endpoint nuevo en `analytics-service` para `integrity_compromised` agregado por tenant — separar a un change propio si emerge la necesidad.
- **Acceptance criteria**:
  - `docs/adr/032-...md` existe con secciones Decisión = DIFERIR + Criterio para revisitar + Referencias a `audi1.md` G7 y ADR-022 (donde vive el MVP estadístico).
  - `CLAUDE.md` sección "Modelo híbrido honesto" lista ADR-032 junto a ADR-017/027/028 (los otros DIFERIDOS).
  - `web-admin` HomePage renderiza 3 KPI cards con datos reales en dev (con seeds activos) y cae a `—` graciosamente cuando un endpoint falla.
  - 0 instancias de `Comision: <hex>...` raw UUID como subtítulo en cualquier frontend (verificable con `rg "Comision: \\$\\{.*slice"` post-PR).
  - 0 instancias de "practicos"/"administracion"/"Gestion"/"automaticamente"/"catedra" sin tildes en archivos `apps/web-*/src/**/*.tsx` (verificable con `rg` post-PR; excluye scripts Python por ASCII contract).
  - Sidebar del web-teacher en expanded mode tiene una línea horizontal sutil entre `ComisionSelector` y el primer grupo de nav.
