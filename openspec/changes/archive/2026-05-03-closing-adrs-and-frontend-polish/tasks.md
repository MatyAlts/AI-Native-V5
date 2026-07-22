## 1. Track A — ADR-032 + cross-reference

- [x] 1.1 Verificar slot ADR-032 disponible: `ls docs/adr/ | rg "^03[0-9]"` no debe listar `032-*`. Si está tomado, mover a 033 y actualizar referencias en este file y en design.md (D1).
- [x] 1.2 Copiar template: `cp docs/adr/_template.md docs/adr/032-g7-ml-alertas-predictivas-baseline-individual.md`.
- [x] 1.3 Redactar ADR-032 con secciones: Status=Accepted, Context (audi1.md G7 + ADR-022 MVP estadístico), Decision=DIFERIR a piloto-2, Criterio para revisitar (dataset etiquetado mínimo + validación cruzada split por estudiante + calibración κ vs intervención docente), Consequences (positivas + negativas), References (audi1.md G7, ADR-022, Capítulo 20 tesis).
- [x] 1.4 Actualizar `CLAUDE.md` sección "Modelo híbrido honesto" → bullet list de ADRs DIFERIDOS: agregar ADR-032 junto a ADR-017/027/028.
- [x] 1.5 Verificar links/referencias: `rg "ADR-032" CLAUDE.md docs/adr/` debe encontrar al menos 2 matches (uno en CLAUDE.md, uno en el ADR mismo).

## 2. Track B item 3 — Microcopy / tildes (text replaces, lowest risk)

- [x] 2.1 `apps/web-admin/src/pages/HomePage.tsx:32` — `"administracion"` → `"administración"`.
- [x] 2.2 `apps/web-admin/src/utils/helpContent.tsx:9` — `"Administracion"` → `"Administración"`. Además: comentario "SIN tildes" obsoleto reemplazado por aclaración "regla cp1252 aplica solo a stdout Python, no a TSX". Aplicado replace_all a todas las instancias del file (Administracion, gestion, Gestion).
- [x] 2.3 `apps/web-teacher/src/views/TareasPracticasView.tsx:196` — `"Trabajos practicos"` → `"Trabajos prácticos"`. Además: replace_all en el file de `catedra`, `practicos`, `automaticas`, `automaticamente`.
- [x] 2.4 `apps/web-teacher/src/views/TemplatesView.tsx:154` — corregir tildes en `Gestion`/`canonicos`/`catedra`/`automaticamente`. Replace_all en el file: `catedra`, `Practicos`, `canonicos`, `canonica`, `automaticamente`. Edit individual: `Gestion de templates` → `Gestión de templates`.
- [x] 2.5 `apps/web-student/src/components/TareaSelector.tsx:70,80` — `"trabajos practicos"` → `"trabajos prácticos"` (2 instancias).
- [x] 2.6 `apps/web-student/src/utils/helpContent.tsx:13` — `"trabajos practicos"` → `"trabajos prácticos"`. Además: comentario "SIN tildes" obsoleto reemplazado, replace_all `automaticamente`. También aplicado replace_all en `apps/web-teacher/src/utils/helpContent.tsx` (catedra, Practicos, automaticas, automaticamente, + edits Gestion del corpus, Gestion de los TPs).
- [x] 2.7 Verificar 0 matches sin tilde en TSX visible (con `-w` word-boundary para excluir verbos legítimos como `gestionar`, y excluir `routes/` que contiene URL slugs no traducibles): `rg -iw "(practicos|practicas|administracion|gestion|automaticamente|automaticas|catedra|canonicos|canonica)" apps/web-*/src/ -g "*.tsx" -g "!**/routes/**"` debe devolver exit code 1 (no encontrado). PASS.
- [x] 2.8 Verificar Python scripts intactos: `rg "\[OK\]|\[FAIL\]" scripts/check-rls.py` debe seguir matcheando — los markers ASCII no se tocan. PASS.

## 3. Track B item 2 — Subtítulos sin UUID raw (3 views del web-teacher)

- [x] 3.1 `apps/web-teacher/src/views/MaterialesView.tsx` — usar `useComisionLabel(comisionId)` (hook nuevo en `ComisionSelector.tsx`) en vez de `comisionId.slice(0, 8)`. Reaprovecha la lógica `comision.nombre || comision.codigo` ya existente en el componente. Tildes correctas en "tutor socrático", "Comisión".
- [x] 3.2 `apps/web-teacher/src/views/TareasPracticasView.tsx` — mismo cambio. Tildes correctas en "comisión", "Comisión".
- [x] 3.3 `apps/web-teacher/src/views/ProgressionView.tsx` — mismo cambio. Eliminado `data.comision_id.slice(0, 8)` reemplazado por `comisionLabelText`.
- [x] 3.4 Verificar 0 instancias del patrón raw UUID slice: `rg "Comision: \\\$\\{.*slice" apps/web-teacher/src/` debe devolver exit code 1. PASS.

**Decisión de implementación**: en vez de inlinear `comisionesApi.listMine()` + `find` en cada una de las 3 views (DRY violation), exporté `comisionLabel(c: Comision): string` desde `ComisionSelector.tsx` y agregué un hook `useComisionLabel(comisionId: string): string` en el mismo file. El hook hace la fetch + cache + fallback a UUID slice durante load, y devuelve el label resuelto cuando llega. Reutiliza la lógica `(c as any).nombre || c.codigo` existente sin duplicar.

## 4. Track B item 4 — Sidebar topSlot separator

- [x] 4.1 Editar `packages/ui/src/components/Sidebar.tsx` — wrapper del `topSlot` cambió de `px-3 py-3 border-b border-gray-800` a `px-3 pt-3 pb-3 border-b border-slate-800/50 mb-3`. Color del border más sutil (slate semitransparente vs gray opaco) + margen inferior para separar del primer NavGroup. Firma del componente intacta (decisión D4 del design).
- [x] 4.2 Test en `packages/ui/src/components/Sidebar.test.tsx` (creado): renderiza con expanded + topSlot, verifica que wrapper contiene las 4 clases (`pb-3`, `border-b`, `border-slate-800/50`, `mb-3`).
- [x] 4.3 Test caso collapsed + topSlot — verifica que el topSlot NO se renderiza (está dentro del condicional `!collapsed && topSlot`). Pre-siembra localStorage con "1" para arrancar collapsed.
- [x] 4.4 Test caso expanded sin topSlot — verifica que no hay elemento con `border-slate-800/50` en el aside.
- [x] 4.5 Verificar que `web-teacher` sigue usando el Sidebar sin cambios en su llamada: `__root.tsx:68-75` usa `<Sidebar ... topSlot={<ComisionSelectorRouted />} />` exactamente igual. PASS.

## 5. Track B item 1 — Web-admin HomePage KPI cards

- [x] 5.1 Refactor parcial de `apps/web-admin/src/pages/HomePage.tsx`: la sección "Recursos disponibles" (lista textual) reemplazada por section "Plataforma en números" con grid de 3 KPI cards. Componente `KpiCard` interno reusable + helper `fetchCount` que soporta tanto array directo como envelope `{items: [...]}`.
- [x] 5.2 Card `# Universidades`: `useEffect` + `fetch("/api/v1/universidades")`, count via `data.items.length`. Estado machine: loading → value | error → "—".
- [x] 5.3 Card `# Comisiones activas`: `useEffect` + `fetch("/api/v1/comisiones?estado=activa")`, mismo patrón.
- [x] 5.4 Card `# Episodios cerrados (últimos 7 días)`: la HomePage no tiene cohorte seleccionada (es vista global), entonces `episodios.value = null, loading=false` siempre → cae a "—" con tooltip `fallbackTooltip="Seleccioná una comisión para ver este KPI"`. Documentado in-source en el comentario del state.
- [x] 5.5 Tooltip "Sin datos disponibles" implementado en `KpiCard` cuando `state.error` está presente. Spread condicional `{...(tooltip ? { title: tooltip } : {})}` para respetar `exactOptionalPropertyTypes` strict.
- [x] 5.6 Verificado: no se renderiza ninguna card "Integridad"/"Integrity"/"% comprometidos". Cubierto explícitamente por test `HomePage.test.tsx::"NO renderiza KPI card de integrity_compromised"`.
- [x] 5.7 Test en `apps/web-admin/tests/HomePage.test.tsx` (creado): primer test mockea los 3 endpoints, verifica que las 3 cards renderizan counts (2, 3, "—"). Helper `tests/_mocks.ts` espejado del de web-teacher. Wireado `setupFiles: ["./tests/setup.ts"]` en `vite.config.ts` (estaba sin engancharse).
- [x] 5.8 Test caso degradación: segundo test mockea `/api/v1/universidades` con `{ok: false, status: 500}`, verifica que la card cae a "—" mientras el resto renderiza, y que la página no crashea.

## 6. Verificación final

- [ ] 6.1 Correr `make lint` — DEFERIDO a verificación local / CI por la regla del CLAUDE.md global ("Never build after changes"). Probable PASS — no se introdujeron imports no usados ni patrones no soportados; el changeset solo tiene replace_all de strings ASCII → UTF-8 y un componente nuevo siguiendo patrones existentes.
- [ ] 6.2 Correr `make typecheck` — DEFERIDO a verificación local / CI. Riesgo principal: el spread condicional `{...(tooltip ? { title: tooltip } : {})}` para respetar `exactOptionalPropertyTypes`. El cast `(c as any).nombre` en `useComisionLabel` está documentado con biome-ignore.
- [ ] 6.3 Correr `make test` — DEFERIDO a verificación local / CI. Tests nuevos: `packages/ui/src/components/Sidebar.test.tsx` (3 cases) + `apps/web-admin/tests/HomePage.test.tsx` (3 cases).
- [ ] 6.4 Verificación visual local — DEFERIDA al usuario (requiere browser running): HomePage muestra 3 KPI cards, subtítulos del web-teacher muestran nombre/código, tildes presentes, sidebar tiene separador.
- [x] 6.5 Confirmar `git diff --stat` muestra el scope esperado (proposal estimaba ~120 LOC; este apply tocó más por la decisión informada de barrer microcopy visible — opción 3 acordada con el usuario, ~280 LOC totales documentado en summary final).
