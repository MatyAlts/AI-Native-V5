/**
 * Sección "Stack técnico" — muestra cada decisión tecnológica del monorepo
 * como pill de texto (sin logos). Categorizado en grupos lógicos (backend,
 * datos, frontend, auth, observabilidad, IA, infra) pero presentado como un
 * único grid responsive en cascada para que el ojo lo lea como bloque
 * unificado tipo Linear.
 */
import { motion } from "framer-motion"

const TECHNOLOGIES: ReadonlyArray<string> = [
  // Backend
  "Python 3.12",
  "FastAPI",
  "SQLAlchemy 2.0",
  "Alembic",
  "Pydantic",
  "Casbin",
  "structlog",
  "OpenTelemetry",
  "asyncpg",
  "httpx",
  // Datos
  "PostgreSQL 16",
  "RLS",
  "pgvector",
  "Redis Streams",
  "MinIO",
  // Frontend
  "React 19",
  "TypeScript",
  "Vite 6",
  "Tailwind v4",
  "TanStack Router",
  "TanStack Query",
  "Framer Motion",
  "Pyodide",
  "Monaco",
  // Auth
  "Keycloak 25",
  "LDAP federation",
  "JWT RS256",
  // Observabilidad
  "Prometheus",
  "Grafana",
  "Loki",
  "Jaeger",
  // IA
  "Mistral",
  "OpenAI",
  "Anthropic",
  "Gemini",
  // Infra
  "Docker Compose",
  "uv",
  "pnpm + turbo",
]

const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1]

export function Stack() {
  return (
    <section className="bg-bg py-32">
      <div className="mx-auto max-w-6xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: EASE_OUT_EXPO }}
          className="mb-20 max-w-3xl"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            Stack
          </p>
          <h2 className="mt-4 font-serif text-[56px] leading-[1.05] tracking-tight text-ink">
            Construido con tecnologías serias.
          </h2>
          <p className="mt-6 text-lg text-muted">
            Cada decisión documentada en 43 ADRs.
          </p>
        </motion.div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
          {TECHNOLOGIES.map((tech, index) => (
            <motion.span
              key={tech}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{
                duration: 0.4,
                ease: EASE_OUT_EXPO,
                delay: index * 0.02,
              }}
              whileHover={{ y: -2 }}
              className="inline-flex items-center justify-center rounded-full border border-border bg-bg-elevated px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-soft transition-colors duration-200 hover:border-ink hover:shadow-[0_2px_8px_rgba(10,10,10,0.04)]"
            >
              {tech}
            </motion.span>
          ))}
        </div>
      </div>
    </section>
  )
}
