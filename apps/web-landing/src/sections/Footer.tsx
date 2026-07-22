import { Wrap } from "../components/primitives"

const COLUMNS = [
  {
    title: "Producto",
    links: [
      { href: "#producto", label: "Qué es" },
      { href: "#alumno", label: "Para alumnos" },
      { href: "#docente", label: "Para docentes" },
      { href: "#institucion", label: "Para instituciones" },
    ],
  },
  {
    title: "Explorar",
    links: [
      { href: "#producto", label: "Cómo funciona" },
      { href: "#beneficios", label: "Por qué elegirla" },
      { href: "#demo", label: "Pedí una demo" },
    ],
  },
]

/** Pie neutro: producto + links de navegacion. */
export function Footer() {
  return (
    <footer className="border-t border-line py-[clamp(44px,6vw,76px)]">
      <Wrap>
        <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
          <div className="max-w-[38ch]">
            <div className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight text-ink">
              <span className="h-2.5 w-2.5 rounded-full bg-celeste" aria-hidden="true" />
              AI-Native
            </div>
            <p className="mt-4 text-[15px] leading-relaxed text-ink-soft">
              La plataforma para enseñar a programar con un tutor de IA que acompaña a cada alumno.
            </p>
          </div>

          <nav
            aria-label="Enlaces del pie"
            className="grid grid-cols-2 gap-x-14 gap-y-8 sm:gap-x-20"
          >
            {COLUMNS.map((col) => (
              <div key={col.title}>
                <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
                  {col.title}
                </p>
                <ul className="mt-4 space-y-3">
                  {col.links.map((l) => (
                    <li key={l.label}>
                      <a
                        href={l.href}
                        className="text-[15px] text-ink-soft transition-colors hover:text-ink"
                      >
                        {l.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t border-line/70 pt-6 text-[13px] text-ink-faint sm:flex-row sm:items-center sm:justify-between">
          <span>© 2026 AI-Native</span>
          <span>Enseñar a programar, acompañando a cada alumno.</span>
        </div>
      </Wrap>
    </footer>
  )
}
