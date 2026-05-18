---
name: Plataforma AI-Native N4
description: Sistema visual del piloto UNSL — riguroso, transparente, pedagógico
colors:
  ink: "#0f172a"
  surface: "#ffffff"
  surface-alt: "#f8fafc"
  surface-canvas: "#f8fafc"
  border: "#e2e8f0"
  border-strong: "#cbd5e1"
  muted: "#64748b"
  muted-soft: "#94a3b8"
  accent-primary: "#2563eb"
  accent-primary-deep: "#1d4ed8"
  brand-stack-blue: "#185fa5"
  sidebar-shell: "#111827"
  sidebar-shell-edge: "#1f2937"
  sidebar-active-marker: "#3b82f6"
  success: "#1f9d55"
  success-soft: "#ecfdf3"
  warning: "#d8a200"
  warning-soft: "#fff8e7"
  danger: "#cf2d2d"
  danger-soft: "#fdecec"
  level-n1: "#22c55e"
  level-n2: "#3b82f6"
  level-n3: "#eab308"
  level-n4: "#f97316"
  level-meta: "#94a3b8"
  appropriation-reflexiva: "#16a34a"
  appropriation-superficial: "#f59e0b"
  appropriation-delegacion: "#dc2626"
  adversarial-jailbreak-indirect: "#a855f7"
  adversarial-jailbreak-substitution: "#dc2626"
  adversarial-jailbreak-fiction: "#06b6d4"
  adversarial-persuasion-urgency: "#f59e0b"
  adversarial-prompt-injection: "#7f1d1d"
typography:
  display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.011em"
  headline:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.011em"
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    letterSpacing: "0.05em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  xl: "12px"
  pill: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent-primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.accent-primary-deep}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  button-secondary:
    backgroundColor: "#e2e8f0"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  button-ghost:
    backgroundColor: "#ffffff00"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "4px 12px"
    height: "36px"
  modal:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "24px"
  modal-dark:
    backgroundColor: "#18181b"
    textColor: "#fafafa"
    rounded: "{rounded.xl}"
    padding: "24px"
  badge-default:
    backgroundColor: "#f1f5f9"
    textColor: "#334155"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  badge-success:
    backgroundColor: "{colors.success-soft}"
    textColor: "#065f46"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  badge-warning:
    backgroundColor: "{colors.warning-soft}"
    textColor: "#854d0e"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  badge-danger:
    backgroundColor: "{colors.danger-soft}"
    textColor: "#7f1d1d"
    rounded: "{rounded.pill}"
    padding: "2px 10px"
  sidebar-shell:
    backgroundColor: "{colors.sidebar-shell}"
    textColor: "#f3f4f6"
    width: "256px"
  sidebar-shell-collapsed:
    backgroundColor: "{colors.sidebar-shell}"
    textColor: "#f3f4f6"
    width: "64px"
---

# Design System: Plataforma AI-Native N4

## 1. Overview

**Creative North Star: "El cuaderno de laboratorio doctoral".**

Este sistema visual existe para servir a una tesis doctoral — no a un producto comercial. Cada decisión está subordinada a tres objetivos: que el comité doctoral perciba **gravitas técnica** sin decoración, que el docente universitario pueda **leer densidad informativa** sin filtros de marketing, y que el estudiante **vea al tutor socrático como un instrumento de pensamiento**, no como un chatbot que regala respuestas.

Hoy, el sistema captura un compromiso parcial. La paleta primitiva (Inter sans, JetBrains mono, slate-neutral, blue-600 como acento) es **sobria pero genérica**: suficiente para no parecerse a Coursera o Kahoot, insuficiente para tener identidad propia frente a "cualquier dashboard B2B 2024". El compromiso real está en otro lado: en el **vocabulario semántico cromático** dedicado al modelo N4 (cinco colores nominales para N1/N2/N3/N4/meta, tres para apropiación pedagógica, cinco para categorías adversarias, cinco para severidad ordinal). Ese vocabulario es la firma del producto y debe protegerse — por más que esté hoy hardcoded en componentes, no en tokens.

Este DESIGN.md captura el estado actual con honestidad. El próximo paso natural es promover los colores N1-N4 y de apropiación a `@theme` (donde viven solo los tokens semánticos de severidad), unificar la escala de slate (hoy mezclada con `gray-*` en el sidebar y `zinc-*` en los modals dark), y comprometerse con un acento más distintivo que `blue-600`. Una pasada `impeccable bolder` está justificada.

**Key Characteristics:**

- Tipografía sans-única (Inter + JetBrains Mono para todo lo criptográfico)
- Paleta neutral fría (slate) como base; colores cromáticos reservados para semántica pedagógica y de severidad
- Densidad académica: cards de KPI sin gigantismo, tablas tabulares, hashes mostrados truncados pero **mostrados**
- Sidebar oscuro persistente (admin/teacher) sobre canvas claro (slate-50) — alto contraste estructural
- SVG inline para todo lo dataviz (sparklines, stacked bars, severity bars). Cero chart libs.
- Tokens `success/warning/danger` declarados en OKLCH (`@theme`) para ramping perceptual; el resto del UI vive todavía en hex/Tailwind defaults

## 2. Colors

Estrategia de color: **Restrained con vocabulario semántico extendido**. La paleta de "chrome" (sidebar, fondos, bordes, texto base) es deliberadamente sobria y monocromática. La paleta de "contenido" (N1-N4, apropiación, severidad adversaria) es saturada y nominal — cada color significa una cosa exacta y reaparece coherentemente en todas las vistas pedagógicas.

### Primary

- **Stack Blue Brand** (`#185FA5`): único hex usado en los favicons SVG de los 3 frontends. Forma "stack/layers" de 3 capas. NO se usa en ningún otro lado del UI hoy — es marca de pestaña, no acento operativo. *Hallazgo: el favicon promete una identidad que el resto del UI no honra.*
- **Accent Blue** (`#2563EB` — Tailwind `blue-600`): único acento operativo. Botón primary, focus rings, links de Markdown, marker de item activo en sidebar (`#3b82f6` / `blue-500` para el border-left de 2px). Es el "azul de SaaS B2B 2024" que el PRODUCT.md banea — está hoy por inercia, no por compromiso.

### Secondary

(omitido — el sistema actual no tiene paleta secundaria comprometida)

### Tertiary

(omitido)

### Neutral

- **Ink** (`#0F172A` — `slate-900`): texto principal, headings, valores numéricos densos.
- **Muted** (`#64748B` — `slate-500`): metadatos, labels secundarios, timestamps, hashes truncados.
- **Muted Soft** (`#94A3B8` — `slate-400`): hints, placeholders, "datos insuficientes", sparkline grids.
- **Border** (`#E2E8F0` — `slate-200`): borde por defecto de cards e inputs.
- **Border Strong** (`#CBD5E1` — `slate-300`): borde de inputs en estado hover/focus contextual.
- **Surface** (`#FFFFFF`): fondo de cards, modals light, inputs.
- **Surface Canvas** (`#F8FAFC` — `slate-50`): fondo del body en web-student, fondo de table headers.
- **Sidebar Shell** (`#111827` — `gray-900`): chrome del sidebar persistente (admin/teacher). NO comparte escala con el resto: usa Tailwind `gray-*`, no `slate-*`. *Inconsistencia documentada para impeccable shape.*

### Semantic State (declarados en `@theme` de los 3 frontends como OKLCH)

- **Success** (`oklch(0.62 0.14 145)` ≈ `#1F9D55`): readiness=ready, integridad CTR válida, "mejorando" en progresión, "Sin alertas" verde calmo.
- **Warning** (`oklch(0.78 0.14 75)` ≈ `#D8A200`): readiness=degraded, alertas pedagógicas medias, panel de N alertas detectadas.
- **Danger** (`oklch(0.58 0.20 27)` ≈ `#CF2D2D`): readiness=error, integridad CTR rota, "empeorando" en progresión, errores de validación.
- **Soft variants** (`success-soft`, `warning-soft`, `danger-soft`): backgrounds tinteados (oklch L≈0.95) para banners de estado.

### Pedagogical: el modelo N4

Cinco colores **dedicados** para la jerarquía cognitiva. Hoy hardcoded en `EpisodeNLevelView.tsx` — DEBEN promoverse a tokens `--color-level-*` en una próxima iteración para que el comité doctoral encuentre coherencia entre vistas.

- **N1 — Comprensión / planificación** (`#22C55E` — `green-500`): lectura del enunciado, primera pasada conceptual.
- **N2 — Elaboración estratégica** (`#3B82F6` — `blue-500`): notas, anotaciones, planificación.
- **N3 — Validación** (`#EAB308` — `yellow-500`): tests, ejecución, debugging.
- **N4 — Interacción con IA** (`#F97316` — `orange-500`): prompts al tutor, lecturas de respuesta, edición tras tutor.
- **meta — Apertura/cierre del episodio** (`#94A3B8` — `slate-400`): eventos no-cognitivos, neutros.

### Pedagogical: apropiación (clasificación final)

Tres colores ordinales para el resultado del classifier sobre el episodio. Aparece en el panel de cierre del web-student y en las trayectorias del web-teacher.

- **Apropiación reflexiva** (`#16A34A` — `green-600`): el outcome buscado.
- **Apropiación superficial** (`#F59E0B` — `amber-500`): trabajo intermedio.
- **Delegación pasiva** (`#DC2626` — `red-600`): copy-paste sin elaboración.

### Adversarial: categorías de guardrail (ADR-019)

Cinco colores nominales para detección preprocesamiento. Hardcoded en `CohortAdversarialView.tsx`. Cada categoría tiene su hue propio para separación visual sin recurrir solo a labels.

- **Jailbreak indirecto** (`#A855F7` — `purple-500`)
- **Jailbreak (sustitución)** (`#DC2626` — `red-600`)
- **Jailbreak (ficción)** (`#06B6D4` — `cyan-500`)
- **Persuasión por urgencia** (`#F59E0B` — `amber-500`)
- **Prompt injection** (`#7F1D1D` — `red-900`, deliberadamente más oscuro porque es la categoría más severa)

### Adversarial: severidad ordinal 1-5

Rampa ordinal del más leve al más severo. Hardcoded como `SEVERITY_COLORS`.

- **Sev 1** `#94A3B8` (slate-400) → **Sev 2** `#FBBF24` (amber-400) → **Sev 3** `#FB923C` (orange-400) → **Sev 4** `#EF4444` (red-500) → **Sev 5** `#7F1D1D` (red-900).

### Named Rules

**The Auditable Hex Rule.** Cualquier hash, UUID, hex de chain, cualquier valor que viva en el CTR o en un attestation, se renderiza en `JetBrains Mono` (no Inter) y se muestra **truncado pero presente** (ej. `12345678…abc`). Nunca escondido tras "Verificar". El usuario debe poder leer el primer y último tramo a ojo desnudo.

**The Color-Plus-Form Rule.** Niveles N1-N4, severidades 1-5 y outcomes de apropiación nunca dependen sólo de color. Siempre tienen label textual al lado, emoji o forma (`↑/↓/→`). Esto es accesibilidad WCAG (`PRODUCT.md` Sección 7) y a la vez honestidad técnica: el comité con presbicia cromática no debe perder información.

**The One-Accent Rule.** Hoy hay un único acento cromático operativo: `accent-primary` (`#2563EB`). Cualquier introducción de un segundo acento (verde-marca, magenta editorial, mostaza académico) requiere un ADR de identidad visual previo. La paleta nominal pedagógica/adversaria es vocabulario semántico, no acento.

## 3. Typography

**Display Font:** Inter (con fallback `system-ui, sans-serif`).
**Body Font:** Inter (misma familia — sistema sans-único).
**Mono Font:** JetBrains Mono (con fallback `ui-monospace, monospace`).

**Character:** Tipografía técnica sin pretensiones editoriales. La elección de Inter es funcional — máxima legibilidad en pantalla a tamaños chicos (las KPI cards llegan a `text-xs`/12px), tabular-nums por defecto en KPIs (`tabular-nums` en `HomePage.tsx`). JetBrains Mono carga el peso simbólico: cada vez que aparece, el lector sabe que está leyendo algo verificable bit-a-bit (hashes, UUIDs de episodio, chain integrity output).

### Hierarchy

Definida en `@layer base` de cada `index.css` + reforzada en componentes específicos.

- **Display** (600, `1.5rem`/24px, lh 1.15, `letter-spacing: -0.011em`): único H1 de cada page, en el header de `PageContainer`. Tracking ligeramente cerrado para densidad académica.
- **Headline** (600, `1.125rem`/18px, lh 1.2): títulos de sección dentro de page (h2). Trayectorias individuales, "Por categoría", "Estado de la plataforma".
- **Title** (600, `0.875rem`/14px, lh 1.3): títulos de cards y sub-secciones (h3). Coherence cards en classification panel, "Tutor socrático" en chat header.
- **Body** (400, `0.875rem`/14px, lh 1.55): texto general. Mensajes de chat, descripciones, paragraph en prose. `body { line-height: 1.55 }` global, deliberadamente más generoso que el default Tailwind (1.5).
- **Label** (500, `0.75rem`/12px, `letter-spacing: 0.05em`, uppercase opcional): KPI labels ("Eventos totales", "Slope promedio"), section dividers en sidebar (`uppercase tracking-wider`), column headers de tablas.
- **Mono** (400, `0.75rem`/12px, lh 1.4): hashes, UUIDs, chain output, `<code>` inline en markdown.

### Named Rules

**The Tabular Numbers Rule.** Cualquier KPI numérico usa `tabular-nums` (lining + monospaced figures de Inter). No bailes de ancho de dígitos al actualizar valores. Aplica a cards del HomePage, cards de evolution longitudinal, conteos de eventos adversos, severity bars.

**The Mono Means Verifiable Rule.** Si un valor está en `JetBrains Mono`, es porque el usuario podría — en principio — verificarlo contra el CTR o una attestation. No usar mono para decoración. No usar mono para precios, código de TP, IDs cortos legibles.

**The Spanish Without Accents in Backend-Touching Strings Rule.** Strings que el backend pueda re-renderizar (export DOCX, scripts CLI con stdout cp1252 en Windows) van sin tildes (ver `helpContent.tsx`, página de Auditoría). El UI puro sí lleva tildes correctas. La regla nace de un bug real (cp1252 + Unicode rompe `check-rls.py` y otros scripts).

## 4. Elevation

Sistema **chato por defecto, con dos sombras tonales mínimas**. La depth se transmite mayoritariamente por borders + bg de slate, no por shadow stacks.

### Shadow Vocabulary

- **Card resting** (`box-shadow: 0 1px 2px rgba(0,0,0,0.05)` — Tailwind `shadow-sm`): única sombra ambient del sistema. Aplicada a `Card`, `Input`, stacked bars de N4. Es lo más cerca que el UI llega de "lift".
- **Modal floating** (`box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25)` — Tailwind `shadow-2xl`): única sombra estructural. Reservada para `Modal` + `HelpButton` modal. La diferencia entre `shadow-sm` y `shadow-2xl` es deliberadamente dramática — no hay shadows intermedios.
- **Hover micro-lift** (`hover:shadow-sm`): trayectorias clickables en `ProgressionView` agregan `shadow-sm` solo en hover. Es la única transición de elevación del sistema.

### Layering / z-index

- Capa única documentada: `z-50` para el backdrop del modal (`fixed inset-0 z-50` en `Modal.tsx`).
- Backdrop usa `bg-black/60 backdrop-blur-sm`. **El blur del backdrop es el único `backdrop-filter` del sistema** — no se usa para crear "glassmorphism" en panels ni cards.

### Named Rules

**The Flat-By-Default Rule.** Las superficies son chatas en reposo. La elevación aparece sólo en (a) modals, (b) hover de elementos navegables. No hay `shadow-md`, `shadow-lg`, `shadow-xl` en uso — saltar de `shadow-sm` directo a `shadow-2xl` codifica en el sistema que "elevarse" significa "salir del flujo normal de la página", no "ser un poco más importante".

**The No-Glassmorphism Rule.** El `backdrop-blur` está confinado al backdrop del modal. Cualquier card con `backdrop-blur` o `bg-white/60` simulando un panel translúcido sobre contenido es prohibido — empuja el sistema hacia el lado SaaS/marketing que PRODUCT.md banea.

## 5. Components

### Buttons (`packages/ui/src/components/Button.tsx`)

- **Shape:** `rounded-md` (6px). Esquinas perceptiblemente redondeadas pero no pill-shaped — densidad académica > friendliness consumer.
- **Primary:** `bg-blue-600 text-white`, hover `bg-blue-700`, focus ring `ring-blue-600`. Tres tamaños (`sm`/`md`/`lg`) con padding `px-2.5 py-1` → `px-5 py-2.5`. Por default `md`.
- **Secondary:** `bg-slate-200 text-slate-900`, hover `slate-300`. Para acciones secundarias en el mismo formulario.
- **Ghost:** `bg-transparent`, hover `bg-slate-100`. Para "Cambiar TP", "Cancelar".
- **Danger:** `bg-red-600 text-white`. Reservado para acciones destructivas (no usado masivamente hoy — la app casi no tiene acciones destructivas reales por la invariante CTR append-only).
- **Disabled:** `opacity-50 cursor-not-allowed`. Aplicado uniformemente.
- **Anti-pattern presente:** algunas pages del web-admin (`UniversidadesPage`, `MateriasPage`, etc.) declaran botones inline con clases duplicadas en lugar de usar el componente `Button`. Migrar es tarea de `impeccable shape`.

### Cards / Containers (`packages/ui/src/components/Card.tsx` + uso ad-hoc)

- **Corner Style:** `rounded-lg` (8px). Más generoso que botones.
- **Background:** `bg-white` light, `bg-slate-900` dark.
- **Border:** `1px solid slate-200` light / `slate-800` dark. Borde + sombra `shadow-sm`. Las cards NUNCA flotan sin borde — el border es el load-bearing element, la sombra es complemento sutil.
- **Internal Padding:** `p-6` (24px) por default. KPI cards usan `p-4` (16px) — más densidad.
- **Anti-pattern presente:** la mitad de las cards del web-teacher se construyen inline con `rounded-lg border border-slate-200 bg-white p-4` en lugar de usar `<Card>`. Funcionalmente idéntico, mantenibilidad pobre. El componente existe pero está infrautilizado.

### Inputs (`packages/ui/src/components/Input.tsx`)

- **Shape:** `rounded-md` (6px), `h-9` (36px), `px-3 py-1`.
- **Style:** `border slate-300`, fondo blanco, sombra `shadow-sm`. Texto `text-sm`.
- **Focus:** `focus-visible:ring-2 ring-blue-600`. Outline `none`. NO se usa border-shift en focus — solo el ring azul de 2px.
- **Mono context:** UUIDs y hashes se ingresan con `className="font-mono text-sm"` adicional (visto en AuditoriaPage, EpisodeNLevelView, StudentLongitudinalView). El UUID display se acompaña de un `<p className="text-xs text-slate-500">` explicativo.
- **Validation:** `aria-invalid="true"` + texto de error en `text-[var(--color-danger)]` debajo. No hay shake animations ni red borders.

### Modals (`packages/ui/src/components/Modal.tsx`)

Componente más comprometido del sistema (con tests Vitest dedicados).

- **Variants:** `light` (default — `bg-white border slate-200`) y `dark` (`bg-zinc-900 border-zinc-700`). Variant `dark` se usa exclusivamente para `HelpButton` modal — codifica que la ayuda es un layer separado del contenido editable.
- **Sizes:** `sm` (max-w-md) / `md` (max-w-lg) / `lg` (max-w-2xl) / `xl` (max-w-3xl). Form modals usan `sm`. Help modals usan `xl`.
- **Shape:** `rounded-xl` (12px), `shadow-2xl`, `max-h-[85vh]`, header con border-bottom + close button.
- **Backdrop:** `bg-black/60 backdrop-blur-sm`. Click-outside cierra. Escape cierra. Body scroll lock vía `overflow: hidden`.
- **Header:** `px-6 py-4 border-b`, título `text-lg font-semibold`, close `<X />` icon (lucide).

### Help System (`HelpButton` + `PageContainer`)

Componente obligatorio en toda page (regla declarada en CLAUDE.md). El icono `<HelpCircle />` (lucide) en el header de `PageContainer`, click abre modal `dark` `xl` con contenido pre-escrito (sin tildes — cp1252-safe). El contenido se centraliza por frontend en `src/utils/helpContent.tsx`, NUNCA inline en la page.

### Sidebar (`packages/ui/src/components/Sidebar.tsx`)

Sidebar persistente fijo a la izquierda — pieza más distintiva del UI admin/teacher. NO usa la escala slate del resto del sistema: usa `gray-*` (Tailwind grayscale, neutro azulado leve). Inconsistencia heredada.

- **Shell:** `bg-gray-900 text-gray-100`, border-right `border-gray-800`.
- **Width:** `w-64` (256px) expanded / `w-16` (64px) collapsed. Toggle persistente en `localStorage` por `storageKey`.
- **Active item:** `bg-gray-800 text-white border-l-2 border-blue-500 pl-[10px]`. **El border-left de 2px es el único side-stripe permitido del sistema** (codifica selección de nav, no severidad).
- **Group labels:** `text-xs uppercase tracking-wider text-gray-400` cuando expanded, separator hairline cuando collapsed.
- **Collapse button:** abajo, full-width, ghost — chevron izquierda + label "Colapsar" / chevron derecha solo cuando collapsed.

### Badge (`packages/ui/src/components/Badge.tsx`)

- **Shape:** `rounded-full px-2.5 py-0.5 text-xs font-medium` (pill).
- **Variants:** `default` (slate-100/700), `success` (emerald-100/800), `warning` (amber-100/800), `danger` (red-100/800), `info` (blue-100/800).
- **Uso real:** mezclado. Se usa en Sidebar (count de items), pero las severidades adversarias y los quartiles se estilizan inline con `bg-* text-*` en lugar del componente. Otra deuda de consolidación.

### StateMessage (`packages/ui/src/components/StateMessage.tsx`)

Primitiva crítica para honestidad técnica. Variants: `loading`, `empty`, `error`. Usa los semantic tokens `var(--color-danger)` + `--color-danger-soft`. Spinner es un círculo SVG con `animate-spin` — única animación motivada del sistema (solo loading state).

### EmptyHero (`packages/ui/src/components/EmptyHero.tsx`)

Empty state primario (estudiante sin comisión, etc.). Icono lucide en círculo `bg-slate-100`, título `text-xl semibold`, descripción `text-base leading-relaxed`. CTA opcional `bg-slate-900 text-white` (inverted dark). Hint `text-xs slate-400` al pie.

### Signature Components (vistas N4 del web-teacher)

Las tres vistas del ADR-022 G7 son las que más cargan la identidad del producto y merecen documentación específica:

**EpisodeNLevelView (Stacked Bar Horizontal)** — barra apilada de 5 colores N1-N4-meta, ancho proporcional al tiempo en cada nivel, etiqueta interna `font-medium text-white` solo si la fracción > 8%. Debajo, grid responsivo de 5 mini-cards con dot de color, label completo, segundos/porcentaje/conteo.

**StudentLongitudinalView (Sparklines + Slope Arrows)** — tabla por template con sparkline SVG inline (120×36px, 3 puntos ordinales 0/1/2 = delegación/superficial/reflexiva, dashed grid, polyline gris), flecha de tendencia (`↑/↓/→`) coloreada según slope, valor numérico mono. Banner de alertas con `border-l-4 border-amber-400 bg-amber-50` — *anti-pattern declarado* (ver Don'ts).

**CohortAdversarialView (Category Bars + Severity Histogram)** — barras horizontales por categoría (cada una con su hue dedicado), severity histogram de 5 barras verticales con altura proporcional, tabla de eventos recientes con timestamp / categoría / severidad / pseudónimo / texto matched en `<code>` block.

### Code + Tutor (web-student EpisodePage)

Layout dual `grid grid-cols-2`: Monaco editor (Pyodide) izquierda, chat derecha. Chat bubbles: usuario `bg-blue-600 text-white ml-auto`, tutor `bg-slate-100 dark:bg-slate-800`. ClassificationPanel post-cierre usa cards de coherencia (CT/CCD/CII) con `Meter` (barra horizontal de 8px alto, color verde/amarillo/rojo según valor — banneable para `bolder`). Hash de classifier `font-mono` truncado a 16 chars.

## 6. Do's and Don'ts

### Do:

- **Do** usar `JetBrains Mono` para todo lo que viva en el CTR, attestations, hashes, UUIDs de episodio. Si lo verifica el comité doctoral o un auditor externo, va en mono.
- **Do** mostrar `insufficient_data: true`, `degraded`, `pending_attestation` literalmente — con label, no con icono ambiguo. La honestidad técnica es asset académico (PRODUCT.md Sección "Design Principles" #5).
- **Do** acompañar siempre N1/N2/N3/N4 + severidad ordinal con label textual o emoji o forma además del color (`Color-Plus-Form Rule`). WCAG 2.1 AA es piso obligatorio.
- **Do** usar `tabular-nums` para KPIs y métricas numéricas que actualizan (HomePage, evolution stats).
- **Do** usar `<PageContainer>` y `<HelpButton>` en TODA page nueva (regla dura del repo). El contenido va en `helpContent.tsx`, nunca inline.
- **Do** preferir SVG inline para dataviz simple (sparklines, stacked bars). Cero chart libs hasta que haya un caso de uso que lo justifique con ADR.
- **Do** declarar el color directo del nivel/severidad/categoría como constante exportada con su rol explícito (`LEVEL_COLORS`, `SEVERITY_COLORS`, `CATEGORY_COLORS`). Mejor todavía: promover a `--color-level-*` en `@theme` cuando se haga `impeccable bolder`.

### Don't:

- **Don't** parecerte a Moodle / Blackboard / WebCT — jerarquía pobre, formularios de los 2000s, "carpetitas-dentro-de-carpetitas" (PRODUCT.md anti-ref #1). Specifically: no anidamientos profundos de tabs/accordions, no botones grises sin estado claro, no typography del sistema sin escala definida.
- **Don't** parecerte a Coursera / Udemy / EdX marketing — gradient-text, hero-grandes "aprende programación", cards de cursos idénticas (PRODUCT.md anti-ref #2). Específicamente: nada de `bg-gradient-to-r from-X to-Y` en titulares, nada de hero buttons gigantes con shadow-glow.
- **Don't** caer en el SaaS dashboard genérico tipo Stripe-clone (PRODUCT.md anti-ref #3). Específicamente: nada de "hero-metric template" (big number + small label + 3-supporting-stats grid identical for every section), nada de identical card grids 3×N que vuelven cada vista una replica de la anterior, nada de navy-y-violet predeterminado.
- **Don't** parecerte a EdTech gamificado (Kahoot, Duolingo) — colores chillones, microinteracciones constantes, badges-y-streaks (PRODUCT.md anti-ref #4). Las únicas animaciones permitidas son `animate-spin` en loading y `animate-pulse` en jobs en running. Cero confetti, cero rebote, cero gradientes saturados.
- **Don't** parecerte a SIU Guaraní / Comdoc — visual de los 90s, formularios infinitos, sin polish (PRODUCT.md anti-ref #5). Específicamente: nada de `<table>` raw sin border-radius del wrapper, nada de form fields sin padding, nada de status messages en color rojo sin border-radius o icon de error.
- **Don't** usar `border-left` >1px como stripe coloreado para denotar severidad o estado. **Bug presente hoy**: `StudentLongitudinalView.tsx` línea 251 usa `border-l-4 border-amber-400 bg-amber-50` para el panel de alertas — reemplazar por `<Card>` con `bg-amber-50 border-amber-200` o un `Badge` separado del banner. La única excepción legítima del sistema es el `border-l-2` del item activo del Sidebar (selección de nav).
- **Don't** usar `text-transparent bg-clip-text bg-gradient-*` (gradient text) en ningún titular o número. Banneado por la skill `impeccable` y por PRODUCT.md anti-ref #2.
- **Don't** introducir `backdrop-blur` en cards o panels para crear glassmorphism. El único `backdrop-blur` legítimo está en el backdrop del modal (`Modal.tsx` línea 84). No replicar.
- **Don't** mezclar la escala `gray-*` con `slate-*` en componentes nuevos. Hoy el sidebar usa `gray-*` (deuda heredada) y el resto del UI usa `slate-*`. Cualquier componente nuevo va en `slate-*`. Unificar es trabajo de `impeccable shape`.
- **Don't** mezclar `zinc-*` (modal dark variant) con `slate-*` (modal light variant) sin razón. Hoy es decisión heredada para que el modal `dark` (HelpButton) tenga un negro más neutral que el `slate-900`. Si se cuestiona, va a ADR.
- **Don't** poner UUIDs / hashes detrás de un botón "Verificar" o un tooltip — se muestran inline, truncados con `…` central, en `font-mono`. Auditabilidad visible (PRODUCT.md Design Principle #2).
- **Don't** usar `#000` puro o `#FFF` puro como text color. Usar `slate-900` (`#0F172A`) como ink y `slate-50` (`#F8FAFC`) como surface canvas — el contraste residual evita el "scanner glare" que cansa al lector denso.
- **Don't** definir colores N1-N4 nuevos en componentes. Si un componente nuevo necesita los 4 niveles, importar `LEVEL_COLORS` desde donde ya viven. Mejor a futuro: usar `var(--color-level-n1)` etc. cuando se promuevan a `@theme`.
- **Don't** asumir cohorte de 6 estudiantes para layouts. Toda vista debe escalar a N=200 sin reescritura (PRODUCT.md Design Principle #4). Tabla > grid de cards cuando N>20. Virtual scroll cuando N>100.
- **Don't** introducir nuevas chart libraries (Recharts, D3, Chart.js) sin ADR. SVG inline ha sido suficiente para sparklines, stacked bars y severity histograms. Cualquier introducción debe justificar el bundle cost.
