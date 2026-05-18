## Context

El piloto UNSL llega a defensa doctoral con dos categorías de deuda visible al comité:

1. **Documental**: la "Agenda Cap 20" del CLAUDE.md ya tiene ADRs redactados para G6 (ADR-028) y G3-Fase-B (ADR-027), pero **G7-ML** (alertas predictivas con modelo entrenado sobre baseline individual del estudiante) sigue sin un ADR propio. El MVP estadístico (z-score vs cohorte) vive dentro de ADR-022, pero el comité va a preguntar específicamente por la versión >1σ vs trayecto propio mencionada en `audi1.md` G7. Sin un ADR único al que apuntar, la decisión sigue siendo "deuda silenciosa".
2. **Frontend visible**: tras el minimalist-ui pass, quedan cuatro papercuts pegados a la demo (HomePage sin métricas reales, subtítulos con UUID raw, tildes faltantes, sidebar sin separador). Ninguno bloquea funcionalidad, pero todos son pegan en la primera impresión del comité.

El estado actual del repo: ADRs 001-031 ocupados (último iter 2 cerró 031), 32 reservado. Tres frontends Vite + `packages/ui` con `Sidebar` compartido. KPI endpoints requeridos ya existen en el ROUTE_MAP del api-gateway; ninguno requiere extensión backend.

## Goals / Non-Goals

**Goals:**
- Cerrar el lado documental de G7-ML con un ADR formal (decisión = DIFERIR a piloto-2 + criterios cuantificables para revisitar).
- Eliminar 4 papercuts visibles del frontend pre-defensa, sin tocar lógica de negocio.
- Mantener la API pública del `Sidebar` compartido (no agregar props para esta separación visual).
- Degradación graciosa: ningún KPI debe romper la página si su endpoint falla en dev.

**Non-Goals:**
- Implementar G6, G7-ML o G3-Fase-B (ese ES el punto del Track A: declarar formalmente que NO se hacen pre-defensa).
- Crear endpoint nuevo en `analytics-service` para `integrity_compromised` agregado por tenant (deuda separada).
- Migrar a primitivo `Card` en `@platform/ui` (deferred — minimalist pass cerró ese debate).
- Introducir i18n para los strings con tildes (los strings se editan in-place; i18n es scope propio).
- Agregar páginas, rutas o navegación nueva.
- Tocar la SOT del `ComisionSelector` (sigue siendo URL search params + mirror localStorage).

## Decisions

### D1 — ADR-032 declara DIFERIR, no "won't do"

**Choice**: redactar ADR-032 con sección Decisión = "DIFERIR a piloto-2", criterio explícito de revisitar (dataset etiquetado mínimo + validación cruzada split por estudiante + calibración κ vs intervención docente real).

**Why over alternatives**:
- *Alternativa A: no redactar nada*. Rechazada — viola el principio del modelo híbrido honesto del CLAUDE.md ("redactá el ADR aunque diga decidimos NO hacer esto ahora") y deja al comité doctoral con deuda silenciosa que no puede defenderse.
- *Alternativa B: implementar G7-ML ahora*. Rechazada — sin dataset etiquetado mínimo, cualquier modelo es ruido. Defender un modelo malo es peor que defender la decisión de no tenerlo.
- *Alternativa C: ADRs separados para G6 y G3-Fase-B también*. Rechazada — verificación local confirma que ADR-027 y ADR-028 ya cubren esas dos decisiones formalmente; agregar duplicados ensucia el catálogo.

### D2 — KPIs usan endpoints existentes + degradación graciosa, no endpoint nuevo

**Choice**: los 3 KPI cards de la HomePage del web-admin consumen endpoints ya en el ROUTE_MAP (`/api/v1/universidades`, `/api/v1/comisiones?estado=activa`, `/api/v1/analytics/...`). Si un endpoint devuelve 401/403/5xx, la card cae a `—` con tooltip "Sin datos disponibles".

**Why over alternatives**:
- *Alternativa A: agregar endpoint agregado en `analytics-service`*. Rechazada — explícitamente fuera de scope; abrir ese hilo retrasa la defensa por una mejora cosmética.
- *Alternativa B: hardcodear ceros*. Rechazada — el comité va a preguntar y deshonesto es peor que ausencia.

**Tradeoff aceptado**: el KPI "Episodios cerrados (últimos 7 días)" requiere comisión específica para `/cohort/{id}/progression`; si no hay cohorte seleccionada, cae a `—`. Aceptable porque la HomePage es la primera vista (no se espera comisión seleccionada todavía).

### D3 — Subtítulos: `comision.nombre || comision.codigo` con soft-fallback

**Choice**: los 3 subtítulos del web-teacher (MaterialesView, TareasPracticasView, ProgressionView) leen `comision?.nombre || comision?.codigo || ""`. El cast TS sigue siendo `(c as any).nombre` mientras Epic 1 (`seed-template-id-and-manifest-reconcile`) no formalice el contrato.

**Why over alternatives**:
- *Alternativa A: bloquear hasta que Epic 1 formalice `nombre` en el tipo `Comision`*. Rechazada — Epic 1 ya está archivada (`2026-05-01-seed-template-id-and-manifest-reconcile`), pero el contrato TS puede no estar al día. Soft-fallback evita acoplar este change al estado del contrato.
- *Alternativa B: dejar el slice raw del UUID*. Rechazada — es exactamente lo que estamos arreglando.

### D4 — Sidebar: Tailwind utilities en el wrapper, no nueva prop

**Choice**: en `packages/ui/src/components/Sidebar.tsx`, agregar `pb-3 border-b border-slate-800/50 mb-3` directamente al wrapper del `topSlot` cuando `expanded === true`. Sin tocar la firma del componente.

**Why over alternatives**:
- *Alternativa A: agregar prop `topSlotSeparator?: boolean`*. Rechazada — sobre-ingeniería para una decisión visual fija. Si en el futuro distintos consumers necesitan distinta separación, ahí se introduce la prop.
- *Alternativa B: que cada consumer agregue las clases en el `topSlot` que pasan*. Rechazada — duplica la decisión visual en N lugares y viola DRY.

**Tradeoff aceptado**: si un consumer futuro NO quiere separador, va a tener que sobreescribirlo (override CSS). Aceptable porque hoy hay un solo consumer (`web-teacher`) y la separación es la decisión correcta para todos los topSlots actuales y previstos.

### D5 — Capabilities como ADDED, no MODIFIED

**Choice**: los 4 specs de este change usan `## ADDED Requirements`, no `## MODIFIED Requirements`, aunque el proposal los liste en "Modified Capabilities".

**Why**: ninguna de las 4 capabilities (`admin-home-kpis`, `web-teacher-page-headers`, `frontend-microcopy-tildes`, `sidebar-topslot-separation`) existe en `openspec/specs/` previo a este change. El instruction de OPSX para `MODIFIED` exige copiar el bloque entero de un requirement existente — sin spec base, no hay nada que copiar. Tratarlas como ADDED refleja la realidad sin fabricar historia.

El proposal usa "Modified Capabilities" en sentido laxo ("afectan comportamiento ya visible del sistema"), no en el sentido formal de OpenSpec ("modifican un requirement preexistente"). Esta nota documenta la interpretación para que el archive sync no se confunda.

## Risks / Trade-offs

- **Slot ADR-032 colisiona** → verificar `ls docs/adr/` **inmediatamente antes** del PR (no desde caché). Si entre tanto se asignó 032, mover este change a 033 sin tocar el resto de los artifacts.
- **KPI endpoint devuelve 401/403 en dev** → la card debe caer a `—` con tooltip; cubierto por test unitario que mockea endpoint failure y verifica que `HomePage` no crashea.
- **Soft-fallback `(c as any).nombre` queda sin tipar** → riesgo de regresión si Epic 1 cambia el contrato. Mitigación: cuando el tipo `Comision` formalice `nombre: string | null`, sacar el cast `as any` (deuda trackeada en `BUGS-PILOTO.md`, no en este change).
- **Comité doctoral pregunta "¿por qué no piloto-2 ya?"** sobre G7-ML → ADR-032 sección "Criterio para revisitar" debe explicitar dataset mínimo (longitud de trayecto ≥ N episodios) que hoy no existe. Ese es el contenido defendible.
- **Tilde fix es text replace, no i18n** → si en el futuro se introduce i18n, estos strings van a tener que migrar como cualquier otro. Aceptado: i18n es scope propio.

## Migration Plan

Este change es puramente aditivo — no hay migración de datos, schema o contratos. Plan de deploy:

1. PR único cubriendo Track A (1 ADR + cross-reference en CLAUDE.md) + Track B (4 fixes frontend + 2 tests).
2. CI: `make lint typecheck test` debe pasar (incluye los 2 tests nuevos).
3. Verificación manual local: levantar los 3 frontends, confirmar que (a) HomePage muestra 3 KPI cards, (b) subtítulos del web-teacher no muestran UUIDs, (c) tildes presentes, (d) sidebar tiene línea separadora.
4. Merge. No hay rollback complejo: si algo regresa, revert del commit alcanza.

## Open Questions

- Ninguna que bloquee. La pregunta abierta del comité doctoral sobre "¿cuándo piloto-2?" se contesta con el contenido del ADR-032 (criterio cuantificable de revisitar), no con esta epic.
