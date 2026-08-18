/**
 * Resumen de las correcciones asistidas de una entrega.
 *
 * **Este componente MUESTRA. No decide.** No escribe en `calificaciones`, no
 * guarda nada, y el boton "Usar como base" rellena el campo de nota y deja el
 * foco ahi — el docente tiene que apretar Calificar como siempre.
 *
 * Tres cosas que la pantalla hace y que parecen detalles:
 *
 * 1. **Muestra el calculo, no solo el resultado.** El docente tiene que poder
 *    ver de donde sale el numero que va a usar como base.
 * 2. **Si falta una correccion, no promedia.** Nombra los que faltan en vez
 *    de dar un numero que se lee como la nota del TP y no lo es.
 * 3. **Los criterios de Active-IA van SOLOS, sin cruzarlos con la rubrica
 *    local.** Emparejar por nombre pone el puntaje de un criterio en otro que
 *    se llama parecido, y eso no se ve.
 */
import { HelpButton } from "@platform/ui"
import { AlertTriangle, Calculator } from "lucide-react"
import type { CorreccionIA } from "../lib/api"
import { type EjercicioDelTP, chequearAritmetica, resumirCorrecciones } from "../utils/correccionIA"
import { helpContent } from "../utils/helpContent"

interface Props {
  ejercicios: EjercicioDelTP[]
  correcciones: CorreccionIA[]
  /** Rellena el campo de nota. NO guarda: eso lo hace el form de siempre. */
  onUsarComoBase: (nota10: number) => void
}

export function ResumenCorreccionIA({ ejercicios, correcciones, onUsarComoBase }: Props) {
  const r = resumirCorrecciones(ejercicios, correcciones)

  // Sin ninguna correccion terminada no hay nada que resumir, y una card
  // vacia que dice "faltan 4" antes de que el docente pida la primera seria
  // ruido.
  if (r.terminos.length === 0) return null

  return (
    <section
      className="rounded-xl border border-border bg-surface p-4 space-y-3"
      data-testid="resumen-correccion-ia"
    >
      <div className="flex items-center gap-2">
        <Calculator size={14} className="text-muted" aria-hidden="true" />
        <p className="text-xs font-mono uppercase tracking-wider text-muted">
          Sugerencia de Active-IA
        </p>
        <span className="ml-auto">
          <HelpButton
            title="La sugerencia de Active-IA"
            content={helpContent.correccionSugerida}
            size="sm"
          />
        </span>
      </div>

      <ul className="space-y-1 text-xs" data-testid="resumen-terminos">
        {r.terminos.map((t) => (
          <li key={t.orden} className="flex items-baseline justify-between gap-3">
            <span className="text-body">{t.titulo}</span>
            <span className="font-mono text-muted">
              {t.nota100}/100 x {(t.pesoNormalizado * 100).toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>

      {r.promedio100 === null ? (
        <div
          className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-xs text-warning"
          data-testid="resumen-sin-promedio"
        >
          No se puede promediar: falta la correccion de <strong>{r.faltantes.join(", ")}</strong>.
          Un promedio sobre los que estan se lee como la nota del TP, y no lo es.
        </div>
      ) : (
        <div className="space-y-2">
          {/* El calculo a la vista, no el resultado pelado. */}
          <p className="font-mono text-xs text-muted" data-testid="resumen-calculo">
            {r.terminos.map((t) => `${t.nota100} x ${t.pesoNormalizado.toFixed(2)}`).join("  +  ")}{" "}
            = <strong className="text-body">{r.promedio100.toFixed(2)}/100</strong>
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-body">
              Equivale a <strong data-testid="resumen-propuesta">{r.propuesta10}</strong>/10
            </p>
            <button
              type="button"
              onClick={() => r.propuesta10 !== null && onUsarComoBase(r.propuesta10)}
              data-testid="resumen-usar-como-base"
              className="rounded border border-subtle px-3 py-1.5 text-xs text-secondary hover:bg-surface-hover"
            >
              Usar como base
            </button>
            <span className="text-xs text-muted">Rellena el campo. No guarda nada.</span>
          </div>
        </div>
      )}

      <Desgloses correcciones={correcciones} />

      {/* Los modos de fallo MEDIDOS de este motor. No es un disclaimer
          generico: cada uno tiene un caso control detras. */}
      <details className="text-xs text-muted">
        <summary className="cursor-pointer">Que hace bien y que no este motor</summary>
        <ul className="mt-2 list-disc list-inside space-y-1">
          <li>
            <strong>Cuenta presencia, no vinculo.</strong> Le dio 100/100 a una entrega con "3
            categorias OK" y "10 productos OK" donde ningun producto quedaba vinculado a ninguna
            categoria.
          </li>
          <li>
            <strong>Elogia lo hardcodeado.</strong> Puntaje completo a una "busqueda" que era{" "}
            <code>if puntajes[i] == 990</code>.
          </li>
          <li>
            <strong>Puede recomendar lo que la catedra prohibe.</strong> Sugirio try/except en
            Programacion 1, donde la consigna lo veda.
          </li>
          <li>
            Gana donde tiene la rubrica cargada y el humano no la leyo. Pierde donde hay que
            entender si el programa <em>responde la pregunta</em>.
          </li>
        </ul>
      </details>
    </section>
  )
}

/**
 * El desglose de cada correccion, tal como lo devolvio Active-IA.
 *
 * Deliberadamente NO se cruza con la rubrica local. `mapSavedToInputs`
 * empareja criterios por string, y dos criterios que se llaman parecido
 * terminarian con el puntaje cambiado sin que nadie lo note. Lado a lado.
 */
function Desgloses({ correcciones }: { correcciones: CorreccionIA[] }) {
  const conDesglose = correcciones.filter(
    (c) => c.estado === "done" && c.desglose && c.desglose.length > 0,
  )
  if (conDesglose.length === 0) return null

  return (
    <div className="space-y-2" data-testid="resumen-desgloses">
      {conDesglose.map((c) => {
        const chequeo = chequearAritmetica(c.desglose, c.nota_100)
        return (
          <div key={c.id} className="rounded-lg border border-border-soft p-2">
            <p className="mb-1 text-[10px] font-mono uppercase tracking-wider text-muted-soft">
              Ejercicio {c.orden} · rubrica {c.rubrica_id}
            </p>
            <ul className="space-y-0.5 text-xs">
              {c.desglose.map((criterio, i) => (
                <li key={`${c.id}-${i}`} className="flex items-baseline justify-between gap-3">
                  <span className="text-body">
                    {String(criterio.nombre ?? criterio.criterio ?? `Criterio ${i + 1}`)}
                  </span>
                  <span className="font-mono text-muted">
                    {String(criterio.puntaje ?? criterio.puntos ?? criterio.score ?? "—")}
                  </span>
                </li>
              ))}
            </ul>
            {chequeo?.difiere && (
              <p
                className="mt-2 flex items-start gap-1.5 text-xs text-warning"
                data-testid={`resumen-no-cierra-${c.orden}`}
              >
                <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
                <span>
                  Los criterios suman <strong>{chequeo.suma}</strong> pero la nota dice{" "}
                  <strong>{chequeo.total}</strong>. Ya paso: una rubrica declaraba una reduccion del
                  30% y el motor devolvio la suma limpia. Revisa el desglose antes de usar este
                  numero.
                </span>
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
