/**
 * Sección "Modelo de datos" — renderiza el ER del schema multi-tenant
 * (UNIVERSIDAD → FACULTAD → CARRERA → ... → EPISODE → EVENT → CLASSIFICATION)
 * usando Mermaid 11 con tema custom alineado a los tokens del sitio.
 *
 * Patrón de uso en React 19:
 *   1. mermaid.initialize({ startOnLoad: false, ... }) en module-load (idempotente).
 *   2. useEffect → mermaid.run({ nodes: [ref.current] }) cuando el div está montado.
 *   3. El div tiene className "mermaid" y como children el código del diagrama.
 *
 * Notas técnicas:
 *  - El SVG generado por Mermaid hereda font-family inline (los themeVariables).
 *  - Se usa overflow-x-auto en el container para mobile: el ER es ancho.
 *  - El fade-up del container es one-shot (whileInView con once).
 */
import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import mermaid from "mermaid"

// Mermaid se inicializa una sola vez por module-load. La función es idempotente:
// si el diagrama se re-renderiza, mermaid.run() respeta esta configuración.
mermaid.initialize({
  startOnLoad: false,
  securityLevel: "loose",
  theme: "base",
  themeVariables: {
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
    fontSize: "13px",
    primaryColor: "#FAFAF9",
    primaryTextColor: "#0A0A0A",
    primaryBorderColor: "#E5E5E5",
    lineColor: "#A3A3A3",
    secondaryColor: "#E8F0F9",
    tertiaryColor: "#FFFFFF",
    // ER-específico — alineado a paleta minimalista del sitio.
    mainBkg: "#FFFFFF",
    nodeBorder: "#E5E5E5",
    clusterBkg: "#FAFAF9",
    clusterBorder: "#E5E5E5",
    titleColor: "#0A0A0A",
    edgeLabelBackground: "#FFFFFF",
    relationLabelColor: "#737373",
    relationLabelBackground: "#FAFAF9",
    attributeBackgroundColorOdd: "#FAFAF9",
    attributeBackgroundColorEven: "#FFFFFF",
  },
})

const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

// Fuente de verdad del diagrama ER — entidades + relaciones verificadas
// contra el código real del repo (academic_main + ctr_store + classifier_db).
const ER_DIAGRAM = `erDiagram
    UNIVERSIDAD ||--o{ FACULTAD : contiene
    FACULTAD ||--o{ CARRERA : ofrece
    CARRERA ||--o{ PLAN_ESTUDIO : tiene
    PLAN_ESTUDIO ||--o{ MATERIA : compone
    MATERIA ||--o{ COMISION : se_dicta
    COMISION ||--o{ UNIDAD : agrupa
    COMISION ||--o{ TAREA_PRACTICA : ofrece
    UNIDAD ||--o{ TAREA_PRACTICA : contiene
    TAREA_PRACTICA }o--o{ EJERCICIO : vincula
    COMISION ||--o{ INSCRIPCION : registra
    COMISION ||--o{ USUARIOS_COMISION : asigna
    INSCRIPCION ||--o{ EPISODE : produce
    EPISODE ||--o{ EVENT : encadena
    EPISODE ||--o| CLASSIFICATION : recibe

    UNIVERSIDAD {
        uuid id PK
        uuid tenant_id "= id"
        string nombre
        string codigo
        string keycloak_realm
    }
    FACULTAD {
        uuid id PK
        uuid tenant_id FK
        uuid universidad_id FK
        string nombre
    }
    CARRERA {
        uuid id PK
        uuid tenant_id FK
        uuid facultad_id FK
        string nombre
        int duracion_semestres
    }
    PLAN_ESTUDIO {
        uuid id PK
        uuid tenant_id FK
        uuid carrera_id FK
        int anio_inicio
        bool vigente
    }
    MATERIA {
        uuid id PK
        uuid tenant_id FK
        uuid plan_id FK
        string nombre
        int horas_totales
    }
    COMISION {
        uuid id PK
        uuid tenant_id FK
        uuid materia_id FK
        uuid periodo_id FK
        string codigo
    }
    UNIDAD {
        uuid id PK
        uuid tenant_id FK
        uuid comision_id FK
        string nombre
        int orden
    }
    TAREA_PRACTICA {
        uuid id PK
        uuid tenant_id FK
        uuid comision_id FK
        uuid unidad_id FK
        text enunciado_md
        string estado
    }
    EJERCICIO {
        uuid id PK
        uuid tenant_id FK
        string titulo
        text enunciado_md
        jsonb test_cases
        jsonb rubrica
        jsonb banco_preguntas
    }
    INSCRIPCION {
        uuid id PK
        uuid tenant_id FK
        uuid comision_id FK
        uuid student_pseudonym
        string estado
    }
    USUARIOS_COMISION {
        uuid id PK
        uuid tenant_id FK
        uuid comision_id FK
        uuid user_id
        string rol
    }
    EPISODE {
        uuid id PK
        uuid tenant_id FK
        uuid student_pseudonym
        uuid problema_id
        string estado
        string last_chain_hash
    }
    EVENT {
        uuid event_uuid PK
        uuid episode_id FK
        int seq
        string event_type
        string self_hash
        string chain_hash
        jsonb payload
    }
    CLASSIFICATION {
        bigint id PK
        uuid episode_id FK
        string classifier_config_hash
        float ct_summary
        float ccd_mean
        float ccd_orphan_ratio
        float cii_stability
        float cii_evolution
        string appropriation
    }
`

type FooterFact = {
  eyebrow: string
  body: string
}

const FOOTER_FACTS: ReadonlyArray<FooterFact> = [
  {
    eyebrow: "RLS forced",
    body: "Cada tabla con tenant_id tiene RLS forzada por Postgres.",
  },
  {
    eyebrow: "Multi-tenant",
    body: "1 universidad = 1 tenant. ADR aplicado 2026-05-15.",
  },
  {
    eyebrow: "CTR append-only",
    body: "Events y Episodes nunca se modifican. Solo se cierran.",
  },
]

export function ModeloDatos() {
  // Usamos `mermaid.render()` que devuelve el SVG como string, en lugar de
  // `mermaid.run({ nodes })` que muta el DOM directamente. La versión imperativa
  // rompe con StrictMode (double-effect) y con re-renders de React 19.
  const [svgString, setSvgString] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void mermaid
      .render("modelo-datos-er", ER_DIAGRAM)
      .then(({ svg }) => {
        if (!cancelled) setSvgString(svg)
      })
      .catch((err: unknown) => {
        // eslint-disable-next-line no-console
        console.error("Mermaid render falló:", err)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section id="modelo-datos" className="relative w-full bg-bg px-6 py-32 md:px-12">
      <div className="mx-auto max-w-7xl">
        {/* Header. */}
        <div className="mb-16 max-w-3xl">
          <motion.span
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
            className="mb-6 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted"
          >
            <span className="inline-block h-px w-6 bg-border" />
            Modelo de datos
          </motion.span>

          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1.0, ease: EASE_OUT_EXPO, delay: 0.05 }}
            className="font-serif font-medium leading-[1.02] tracking-[-0.022em] text-ink"
            style={{ fontSize: "clamp(2.25rem, 4.5vw, 3.5rem)" }}
          >
            El árbol institucional, las entidades operativas.
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 1.0, ease: EASE_OUT_EXPO, delay: 0.15 }}
            className="mt-6 max-w-2xl text-base leading-relaxed text-muted md:text-lg"
          >
            Cada universidad es su propio tenant aislado. Aislamiento real por
            Row-Level Security.
          </motion.p>
        </div>

        {/* Contenedor del diagrama Mermaid. */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 1.0, ease: EASE_OUT_EXPO, delay: 0.1 }}
          className="overflow-x-auto rounded-lg border border-border bg-bg-elevated p-6 md:p-12"
        >
          {svgString ? (
            <div
              // biome-ignore lint/security/noDangerouslySetInnerHtml: SVG generado por Mermaid (no input externo)
              dangerouslySetInnerHTML={{ __html: svgString }}
              className="mx-auto flex min-w-[860px] justify-center text-ink [&_svg]:max-w-full [&_svg]:h-auto"
            />
          ) : (
            <pre className="mx-auto min-w-[860px] whitespace-pre-wrap font-mono text-xs text-muted">
              {ER_DIAGRAM}
            </pre>
          )}
        </motion.div>

        {/* Leyenda técnica (3 columnas). */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.9, ease: EASE_OUT_EXPO, delay: 0.2 }}
          className="mt-10 grid grid-cols-1 gap-8 md:grid-cols-3"
        >
          {FOOTER_FACTS.map((fact) => (
            <div
              key={fact.eyebrow}
              className="border-t border-border pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0"
            >
              <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
                {fact.eyebrow}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                {fact.body}
              </p>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}
