import { motion, type Variants } from "framer-motion"

/**
 * Sección "Para Neyen" — guía operativa para el QA del piloto.
 *
 * Es la sección más informativa de la landing: 7 bloques narrativos en
 * vertical (no grid), fondo oscuro `bg-ink` con texto claro para destacarse
 * como "callout" técnico. Cada bloque entra con fade-up + stagger 0.1s.
 * Los code blocks usan `bg-ink-soft` (algo más claro que el fondo) y
 * pueden hacer scroll horizontal.
 */

const EXPO_OUT = [0.16, 1, 0.3, 1] as const

const blockFadeUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.8,
      ease: EXPO_OUT,
      delay: index * 0.1,
    },
  }),
}

const codeBlockVariants: Variants = {
  hidden: { opacity: 0, scale: 0.98 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.7, ease: EXPO_OUT },
  },
}

// --- Contenido textual de los bloques ---

const SETUP_COMMANDS = `cd AI-NativeV3-main
docker compose -f infrastructure/docker-compose.dev.yml up -d
uv sync --all-packages && pnpm install

# migraciones + seeds (solo primera vez)
bash scripts/migrate-all.sh
uv run python -m academic_service.seeds.casbin_policies
uv run python scripts/seed-3-comisiones.py
uv run python scripts/seed-ejercicios-piloto.py

# levantar stack
bash scripts/dev-start-all.sh &
make dev`

type Scenario = {
  title: string
  steps: ReadonlyArray<string>
  successCriterion: string
}

const SCENARIOS: ReadonlyArray<Scenario> = [
  {
    title:
      "Crear una universidad nueva desde el admin → aislamiento total",
    steps: [
      'Login admin (5173) → Universidades → "Nueva universidad"',
      "Llenar form",
    ],
    successCriterion:
      "la nueva universidad tiene id === tenant_id, banco con 0 ejercicios, 0 facultades. NO heredó NADA de UTN.",
  },
  {
    title: "Cambiar de universidad con el TenantSelector",
    steps: [
      'En admin, abrir el dropdown "Universidad activa" en el header',
      "Cambiar a otra universidad",
    ],
    successCriterion:
      "el dashboard se actualiza, facultades/comisiones/ejercicios cambian. Ningún dato de otra universidad aparece.",
  },
  {
    title: "Hacer un episodio completo como alumno",
    steps: [
      "Login alumno (5175) → Mi materia → Unidad → TP → Ejercicio",
      "Escribir código simple, ejecutar (probar valor inválido + valor válido)",
      "Mandar mensaje al tutor",
      "Cerrar episodio",
    ],
    successCriterion:
      "aparece el diagnóstico N4 con las 5 coherencias. La consola NO tiene errores 500.",
  },
  {
    title: "Auditar la cadena CTR desde el admin",
    steps: [
      "Login admin → Auditoría",
      "Pegar el episode_id del episodio recién cerrado (lo ves en la URL del alumno)",
      'Click "Verificar cadena"',
    ],
    successCriterion:
      'response valid: true, integrity_compromised: false, mensaje "Cadena íntegra"',
  },
  {
    title: "Tampering test (avanzado, opcional)",
    steps: [
      "Conectar a Postgres: docker exec -it platform-postgres psql -U postgres -d ctr_store",
      "Modificar manualmente un self_hash de un evento del medio del episodio:",
      "UPDATE events SET self_hash='deadbeef...' WHERE episode_id='...' AND seq=3;",
      "Volver a auditar",
    ],
    successCriterion:
      "response valid: false, failing_seq: 3. Después restaurar el hash original.",
  },
]

const RED_FLAGS: ReadonlyArray<string> = [
  "Cross-tenant leak: ver datos de otra universidad sin haber cambiado tenant",
  "Episodios que no se cierran (botón Cerrar no responde o tira 500)",
  "Errores 500 en consola del browser",
  "El TenantSelector listando universidades donde NO tenés rol (debería filtrar)",
  "Eventos del CTR perdidos: cerraste un episodio pero verify falla con seq inferior al esperado",
  "BYOK key visible en plaintext en algún response (debe estar siempre cifrada)",
]

type KnownLimitation = {
  what: string
  why: string
}

const KNOWN_LIMITATIONS: ReadonlyArray<KnownLimitation> = [
  {
    what: "comisiones/mis devuelve 0 para alumnos",
    why: "gap B.2, lo arregla F9 con Keycloak (no usar ese endpoint)",
  },
  {
    what: "integrity-attestation-service:8012 responde 503",
    why: "by design en dev local, vive en VPS UNSL",
  },
  {
    what: 'Hashes ceremoniales "c".repeat(64) cuando falla bootstrap',
    why: "fallback documentado, no bloquea",
  },
  {
    what: "Wizard IA del docente devuelve 502 sin BYOK",
    why: "cargá una API key de Mistral en el tenant primero",
  },
  {
    what: 'web-teacher / web-student no tienen TenantSelector "histórico"',
    why: "solo admin lo tiene fully wired",
  },
  {
    what: "κ ≥ 0.70 intercoder NO está validado",
    why: "bloqueante doctoral pero no de software",
  },
]

const BUG_REPORT_TEMPLATE = `TÍTULO: [Severidad] - Componente afectado - Descripción 1-line

SEVERIDAD: critical / high / medium / low
COMPONENTE: web-admin / web-teacher / web-student / api-gateway / etc

REPRODUCIR:
1. ...
2. ...
3. ...

ESPERADO: lo que debería pasar
ACTUAL: lo que pasó
CONSOLA: errores relevantes
PANTALLA: screenshot adjunto

TENANT/USUARIO: en qué tenant + rol estabas`

const INSPECT_COMMANDS = `# Ver health de todos los servicios
bash scripts/check-health.sh

# Resetear estado a "recién clonado" (sin re-correr migraciones)
bash scripts/reset-to-seed.sh

# Inspeccionar Postgres
docker exec -it platform-postgres psql -U postgres -d academic_main
docker exec -it platform-postgres psql -U postgres -d ctr_store

# Inspeccionar Redis (los streams del CTR)
docker exec -it platform-redis redis-cli XLEN ctr.p0

# Ver logs de un servicio específico
tail -f .dev-logs/academic-service.log

# Verificar cadena criptográfica de un episodio (curl directo)
curl -s -X POST "http://127.0.0.1:8000/api/v1/audit/episodes/<UUID>/verify" \\
  -H "X-Tenant-Id: 7a7a143c-31f8-461b-be08-d86ac36b41a3" \\
  -H "X-User-Id: 33333333-3333-3333-3333-333333333333" \\
  -H "X-User-Roles: superadmin"`

// --- Componentes auxiliares ---

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="font-serif text-[28px] leading-tight tracking-tight text-bg">
      {children}
    </h3>
  )
}

function Paragraph({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-5 text-base leading-relaxed text-muted-soft">{children}</p>
  )
}

function CodeBlock({ code }: { code: string }) {
  return (
    <motion.pre
      variants={codeBlockVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
      className="mt-6 overflow-x-auto rounded-xl border border-border/15 bg-ink-soft p-6 font-mono text-[13px] leading-relaxed text-bg"
    >
      <code>{code}</code>
    </motion.pre>
  )
}

function Block({
  index,
  children,
}: {
  index: number
  children: React.ReactNode
}) {
  return (
    <motion.div
      custom={index}
      variants={blockFadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
      className="mt-20 first:mt-0"
    >
      {children}
    </motion.div>
  )
}

// --- Sección principal ---

export function ParaNeyen() {
  return (
    <section
      id="qa"
      className="w-full border-t border-b border-border/10 bg-ink py-40 text-bg"
    >
      <div className="mx-auto max-w-5xl px-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: EXPO_OUT }}
          className="max-w-3xl"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">
            Para Neyen — onboarding del QA
          </p>
          <h2 className="mt-4 font-serif text-[48px] leading-[1.05] tracking-tight text-bg">
            Bienvenido al piloto. Esto vas a probar.
          </h2>
          <p className="mt-6 text-lg text-muted-soft">
            Esta sección es tu mapa. Cinco minutos de lectura y empezás a
            romper.
          </p>
        </motion.div>

        {/* Bloque 1 — Setup */}
        <Block index={0}>
          <Heading>Setup en 5 minutos</Heading>
          <Paragraph>
            Si el stack ya está corriendo, ignorá esto. Si no, abrí una terminal
            y corré los comandos en orden. Toma 8–12 minutos la primera vez
            (descarga de Docker images + uv sync), 60 segundos después.
          </Paragraph>
          <CodeBlock code={SETUP_COMMANDS} />
          <p className="mt-5 text-sm leading-relaxed text-muted-soft">
            Después abrís http://localhost:5172 (esta página) y los 3 frontends
            en :5173/:5174/:5175.
          </p>
        </Block>

        {/* Bloque 2 — Escenarios */}
        <Block index={1}>
          <Heading>Cinco escenarios concretos</Heading>
          <ol className="mt-8 space-y-10">
            {SCENARIOS.map((scenario, idx) => (
              <li key={scenario.title} className="flex gap-5">
                <span className="flex-shrink-0 font-mono text-[12px] uppercase tracking-[0.15em] text-muted">
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <div className="flex-1">
                  <h4 className="text-base font-medium leading-snug text-bg">
                    {scenario.title}
                  </h4>
                  <ul className="mt-3 space-y-1.5 text-sm leading-relaxed text-muted-soft">
                    {scenario.steps.map((step) => (
                      <li key={step} className="flex items-start gap-2">
                        <span
                          aria-hidden="true"
                          className="mt-[0.6em] inline-block h-[3px] w-[3px] flex-shrink-0 rounded-full bg-muted"
                        />
                        <span>{step}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 text-sm leading-relaxed text-muted-soft">
                    <span className="font-mono text-[11px] uppercase tracking-[0.15em] text-accent">
                      Criterio de éxito
                    </span>
                    <span className="mx-2 text-border">·</span>
                    <span>{scenario.successCriterion}</span>
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </Block>

        {/* Bloque 3 — Banderas rojas */}
        <Block index={2}>
          <Heading>Banderas rojas</Heading>
          <Paragraph>
            Estos son bugs que tenés que reportar si los ves:
          </Paragraph>
          <ul className="mt-6 space-y-3">
            {RED_FLAGS.map((flag) => (
              <li
                key={flag}
                className="flex items-start gap-3 text-base leading-relaxed text-muted-soft"
              >
                <span
                  aria-hidden="true"
                  className="mt-[0.65em] inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-red-400"
                />
                <span>{flag}</span>
              </li>
            ))}
          </ul>
        </Block>

        {/* Bloque 4 — Limitaciones conocidas */}
        <Block index={3}>
          <Heading>Lo que ya sabemos</Heading>
          <Paragraph>
            Estas limitaciones están documentadas. NO las reportes.
          </Paragraph>
          <ul className="mt-6 space-y-4">
            {KNOWN_LIMITATIONS.map((item) => (
              <li
                key={item.what}
                className="flex items-start gap-3 text-base leading-relaxed text-muted-soft"
              >
                <span
                  aria-hidden="true"
                  className="mt-[0.65em] inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-400"
                />
                <span>
                  <span className="text-bg">{item.what}</span>
                  <span className="mx-2 text-border">→</span>
                  <span>{item.why}</span>
                </span>
              </li>
            ))}
          </ul>
        </Block>

        {/* Bloque 5 — Cómo reportar bugs */}
        <Block index={4}>
          <Heading>Formato del reporte</Heading>
          <Paragraph>
            Si encontrás algo, abrí issue o mensaje al doctorando con este
            formato:
          </Paragraph>
          <CodeBlock code={BUG_REPORT_TEMPLATE} />
        </Block>

        {/* Bloque 6 — Atajos */}
        <Block index={5}>
          <Heading>Comandos para inspeccionar</Heading>
          <Paragraph>
            Atajos útiles para diagnosticar mientras testeás:
          </Paragraph>
          <CodeBlock code={INSPECT_COMMANDS} />
        </Block>

        {/* Bloque 7 — Contacto */}
        <Block index={6}>
          <Heading>Contacto</Heading>
          <ul className="mt-6 space-y-2 font-mono text-[12px] uppercase tracking-[0.12em] text-muted-soft">
            <li>
              <span className="text-muted">Doctorando</span>
              <span className="mx-2 text-border">·</span>
              <span className="text-bg">
                Alberto Alejandro Cortez · cortez@unsl.edu.ar
              </span>
            </li>
            <li>
              <span className="text-muted">Co-directora</span>
              <span className="mx-2 text-border">·</span>
              <span className="text-bg">
                Daniela Carbonari · carbonari@unsl.edu.ar
              </span>
            </li>
            <li>
              <span className="text-muted">Repositorio</span>
              <span className="mx-2 text-border">·</span>
              <span className="text-bg">github.com/...</span>
            </li>
          </ul>
        </Block>
      </div>
    </section>
  )
}
