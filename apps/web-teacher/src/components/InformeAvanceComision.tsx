/**
 * Informe de avance de comisión (imprimible, para el docente) — Lote 2,
 * IAC-03. Componente de presentación pura: recibe el view-model ya armado
 * por los helpers del Lote 1 (`buildResumenComision`,
 * `buildDetallePorAlumno`) y renderiza portada + detalle por alumno. NO
 * fetchea nada (eso lo hace `ExportView`, IAC-04).
 *
 * Print CSS: este componente lleva la clase `informe-avance-print`, que
 * `index.css` usa como scope de un bloque `@media print` que oculta el resto
 * de la app (header/sidebar/nav) y deja SOLO este árbol visible al imprimir.
 * Se eligió un contenedor print-only en vez de una ruta dedicada porque el
 * informe se dispara desde `ExportView` con datos ya compuestos en memoria
 * (sin fetch propio ni navegación) — una ruta aparte hubiera obligado a
 * re-fetchear o a pasar el view-model por routing state.
 */
import { PROGRESSION_DOCENTE, studentShortLabel } from "../utils/docenteLabels"
import type { DetalleAlumnoRow, ResumenComisionPortada } from "../utils/informeComision"

export interface InformeAvanceComisionProps {
  /** Label ya resuelto de la comisión (ej. "Prog 1 · A-Mañana"), sin UUID. */
  comisionLabel: string
  resumen: ResumenComisionPortada
  detalle: DetalleAlumnoRow[]
}

function fmtRatio(n: number): string {
  return n.toFixed(2)
}

export function InformeAvanceComision({
  comisionLabel,
  resumen,
  detalle,
}: InformeAvanceComisionProps) {
  const { progresion, cuartilesCII, alertas } = resumen

  return (
    <div className="informe-avance-print bg-white text-ink p-8 space-y-8 max-w-3xl mx-auto">
      <header className="space-y-1 border-b border-border pb-4">
        <p className="text-[11px] uppercase tracking-[0.12em] font-semibold text-muted">
          Informe de avance de comisión
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">{comisionLabel}</h1>
        <p className="text-sm text-muted">
          Generado el {new Date().toLocaleDateString("es-AR")} · {progresion.nEstudiantes} alumno
          {progresion.nEstudiantes !== 1 ? "s" : ""}
        </p>
      </header>

      <section data-testid="informe-avance-portada" className="space-y-6">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2">
            Progresión de la cohorte
          </h2>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <dt className="text-muted text-xs">Alumnos</dt>
              <dd className="font-mono text-lg">{progresion.nEstudiantes}</dd>
            </div>
            <div>
              <dt className="text-muted text-xs">Mejorando</dt>
              <dd className="font-mono text-lg">{progresion.mejorando}</dd>
            </div>
            <div>
              <dt className="text-muted text-xs">Estable</dt>
              <dd className="font-mono text-lg">{progresion.estable}</dd>
            </div>
            <div>
              <dt className="text-muted text-xs">En riesgo</dt>
              <dd className="font-mono text-lg">{progresion.empeorando}</dd>
            </div>
          </dl>
          <p className="text-xs text-muted mt-2">
            Net progression ratio:{" "}
            <span className="font-mono">{fmtRatio(progresion.netProgressionRatio)}</span>
          </p>
        </div>

        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2">
            Cuartiles CII de la cohorte
          </h2>
          {cuartilesCII.disponible ? (
            <dl className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <dt className="text-muted text-xs">Q1</dt>
                <dd className="font-mono text-lg">{fmtRatio(cuartilesCII.q1 as number)}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Mediana</dt>
                <dd className="font-mono text-lg">{fmtRatio(cuartilesCII.median as number)}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Q3</dt>
                <dd className="font-mono text-lg">{fmtRatio(cuartilesCII.q3 as number)}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted italic">
              Datos insuficientes por privacidad (menos de 5 alumnos evaluados).
            </p>
          )}
        </div>

        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2">
            Resumen de alertas
          </h2>
          {alertas.disponible ? (
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <dt className="text-muted text-xs">Con alguna alerta</dt>
                <dd className="font-mono text-lg">{alertas.estudiantesConAlerta}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Regresión vs. cohorte</dt>
                <dd className="font-mono text-lg">{alertas.counts?.regresion_vs_cohorte}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Quartil inferior</dt>
                <dd className="font-mono text-lg">{alertas.counts?.bottom_quartile}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs">Pendiente negativa</dt>
                <dd className="font-mono text-lg">
                  {alertas.counts?.slope_negativo_significativo}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted italic">
              Datos insuficientes por privacidad (menos de 5 alumnos evaluados).
            </p>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Detalle por alumno
        </h2>
        <p
          data-testid="informe-avance-privacidad"
          className="text-xs font-medium text-danger bg-danger-soft border border-danger/30 rounded px-3 py-2"
        >
          Uso interno de la cátedra — contiene datos personales, no publicar ni compartir fuera de
          la cátedra.
        </p>
        {detalle.length === 0 ? (
          <p className="text-sm text-muted italic">No hay alumnos con datos en esta comisión.</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted border-b border-border">
                <th className="py-2 pr-4">Alumno</th>
                <th className="py-2 pr-4">Estado</th>
                <th className="py-2 pr-4">Episodios</th>
                <th className="py-2 pr-4">Último estado observado</th>
              </tr>
            </thead>
            <tbody>
              {detalle.map((row) => (
                <tr key={row.pseudonym} className="border-b border-border-soft">
                  <td className="py-2 pr-4 font-medium">
                    {row.label || studentShortLabel(row.pseudonym)}
                  </td>
                  <td className="py-2 pr-4">
                    {PROGRESSION_DOCENTE[row.progressionLabel] ?? row.progressionLabel}
                  </td>
                  <td className="py-2 pr-4 font-mono">{row.nEpisodes}</td>
                  <td className="py-2 pr-4">{row.lastClassification ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
