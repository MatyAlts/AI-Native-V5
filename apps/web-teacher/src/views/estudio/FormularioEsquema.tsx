/**
 * Formulario de etiquetado definido por el esquema de una version del codebook
 * (change cibse-codificacion-ciega, design D9).
 *
 * Nada del codebook vive aca: dimensiones, valores, regimenes, regla, frontera y
 * confianza salen del esquema que recibe. La regla de regimen tampoco se evalua
 * en el panel:
 *   - con regla, el regimen viaja en null y lo DERIVA el servidor; el panel muestra
 *     lo que volvio, rotulado como resultado de la regla. Solo se puede marcar un
 *     regimen exento (evidencia insuficiente);
 *   - sin regla (`reglas_regimen` vacia), el codificador elige el regimen;
 *   - el desacuerdo con la regla va en `regimen_propuesto`, con nota obligatoria.
 *     No cambia el regimen: queda registrado al lado.
 */
import { useId, useState } from "react"
import type { EsquemaFormulario, EtiquetaGuardada, RespuestaFormulario } from "../../lib/estudioApi"
import { mensajeDeErrorEstudio } from "./mensajesError"

interface Props {
  esquema: EsquemaFormulario
  /** Etiqueta propia ya guardada, o null si el item no se empezo. */
  inicial: EtiquetaGuardada | null
  onGuardar: (respuesta: RespuestaFormulario) => Promise<EtiquetaGuardada>
  /** Motivos que devolvio el cierre (422) para este item. */
  faltantes?: string[]
  /** Codificacion cerrada o codebook no congelado. */
  deshabilitado?: boolean
}

interface ValorDimension {
  valor: string | null
  cita: string
}

function valoresIniciales(
  esquema: EsquemaFormulario,
  inicial: EtiquetaGuardada | null,
): Record<string, ValorDimension> {
  const r: Record<string, ValorDimension> = {}
  for (const d of esquema.dimensiones) {
    const previo = inicial?.respuestas[d.clave]
    r[d.clave] = { valor: previo?.valor ?? null, cita: previo?.cita ?? "" }
  }
  return r
}

export function FormularioEsquema({
  esquema,
  inicial,
  onGuardar,
  faltantes = [],
  deshabilitado = false,
}: Props) {
  const conRegla = esquema.reglas_regimen.length > 0
  const exentos = new Set(esquema.regimenes_exentos)
  const nombreRegimen = (clave: string | null) =>
    clave === null ? null : (esquema.regimenes.find((r) => r.clave === clave)?.nombre ?? clave)

  const [valores, setValores] = useState(() => valoresIniciales(esquema, inicial))
  // Con regla: solo un exento puede elegirse. Sin regla: cualquier regimen.
  const [regimenElegido, setRegimenElegido] = useState<string | null>(() => {
    const previo = inicial?.regimen ?? null
    if (previo === null) return null
    return conRegla ? (exentos.has(previo) ? previo : null) : previo
  })
  const [propuesto, setPropuesto] = useState<string | null>(inicial?.regimen_propuesto ?? null)
  const [frontera, setFrontera] = useState(inicial?.es_frontera ?? false)
  const [confianza, setConfianza] = useState<string | null>(inicial?.confianza ?? null)
  const [notas, setNotas] = useState(inicial?.notas ?? "")
  const [resultado, setResultado] = useState<EtiquetaGuardada | null>(inicial)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const idNotas = useId()
  const idPropuesto = useId()
  const idConfianza = useId()
  const idFaltantes = useId()

  const cambiarValor = (clave: string, cambio: Partial<ValorDimension>) =>
    setValores((prev) => ({
      ...prev,
      [clave]: { ...(prev[clave] ?? { valor: null, cita: "" }), ...cambio },
    }))

  const guardar = async () => {
    setError(null)
    if (propuesto !== null && notas.trim() === "") {
      setError("La nota es obligatoria para proponer otro régimen.")
      return
    }
    const respuestas: RespuestaFormulario["respuestas"] = {}
    for (const d of esquema.dimensiones) {
      const v = valores[d.clave] ?? { valor: null, cita: "" }
      respuestas[d.clave] = { valor: v.valor, cita: v.cita.trim() === "" ? null : v.cita }
    }
    setGuardando(true)
    try {
      const guardado = await onGuardar({
        respuestas,
        regimen: regimenElegido,
        regimen_propuesto: propuesto,
        es_frontera: frontera,
        confianza,
        notas,
      })
      setResultado(guardado)
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(ev) => {
        ev.preventDefault()
        void guardar()
      }}
    >
      {esquema.dimensiones.map((d) => {
        const v = valores[d.clave] ?? { valor: null, cita: "" }
        return (
          <fieldset key={d.clave} className="rounded-lg border border-border bg-white p-3">
            <legend className="px-1 text-sm font-semibold text-ink">{d.nombre}</legend>
            <div className="flex flex-wrap gap-3 mb-2">
              {d.valores.map((valor) => (
                <label key={valor} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="radio"
                    name={`dim-${d.clave}`}
                    value={valor}
                    checked={v.valor === valor}
                    disabled={deshabilitado}
                    onChange={() => cambiarValor(d.clave, { valor })}
                  />
                  {valor}
                </label>
              ))}
            </div>
            <label className="block text-xs text-muted">
              Cita
              <textarea
                className="mt-1 block w-full rounded border border-border p-2 text-sm text-ink"
                rows={2}
                value={v.cita}
                disabled={deshabilitado}
                placeholder="Localizadores de la traza: turno 3; ejecución 4"
                onChange={(ev) => cambiarValor(d.clave, { cita: ev.target.value })}
              />
            </label>
          </fieldset>
        )
      })}

      <fieldset className="rounded-lg border border-border bg-white p-3 space-y-2">
        <legend className="px-1 text-sm font-semibold text-ink">Régimen</legend>
        {conRegla ? (
          <>
            <p data-testid="regimen-regla" className="text-sm text-ink">
              {textoRegimen(resultado, exentos, nombreRegimen)}
            </p>
            {esquema.regimenes_exentos.map((clave) => (
              <label key={clave} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={regimenElegido === clave}
                  disabled={deshabilitado}
                  onChange={(ev) => setRegimenElegido(ev.target.checked ? clave : null)}
                />
                {`Marcar como ${nombreRegimen(clave)}`}
              </label>
            ))}
            <div>
              <label htmlFor={idPropuesto} className="block text-xs text-muted">
                Régimen propuesto
              </label>
              <select
                id={idPropuesto}
                className="mt-1 rounded border border-border bg-surface p-1.5 text-sm text-ink"
                value={propuesto ?? ""}
                disabled={deshabilitado}
                onChange={(ev) => setPropuesto(ev.target.value === "" ? null : ev.target.value)}
              >
                <option value="">Sin desacuerdo con la regla</option>
                {esquema.regimenes.map((r) => (
                  <option key={r.clave} value={r.clave}>
                    {r.nombre}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-muted">
                Si creés que la regla da un resultado injusto en este caso, proponé otro régimen y
                explicá por qué en las notas. El régimen registrado sigue siendo el de la regla.
              </p>
            </div>
          </>
        ) : (
          <div className="flex flex-wrap gap-3">
            {esquema.regimenes.map((r) => (
              <label key={r.clave} className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="regimen"
                  value={r.clave}
                  checked={regimenElegido === r.clave}
                  disabled={deshabilitado}
                  onChange={() => setRegimenElegido(r.clave)}
                />
                {r.nombre}
              </label>
            ))}
          </div>
        )}
      </fieldset>

      {esquema.marca_frontera && (
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={frontera}
            disabled={deshabilitado}
            onChange={(ev) => setFrontera(ev.target.checked)}
          />
          Caso de frontera
        </label>
      )}

      {esquema.confianza !== null && (
        <div>
          <label htmlFor={idConfianza} className="block text-xs text-muted">
            Confianza
          </label>
          <select
            id={idConfianza}
            className="mt-1 rounded border border-border bg-surface p-1.5 text-sm text-ink"
            value={confianza ?? ""}
            disabled={deshabilitado}
            onChange={(ev) => setConfianza(ev.target.value === "" ? null : ev.target.value)}
          >
            <option value="">Sin indicar</option>
            {esquema.confianza.valores.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      )}

      <div>
        <label htmlFor={idNotas} className="block text-xs text-muted">
          Notas
        </label>
        <textarea
          id={idNotas}
          className="mt-1 block w-full rounded border border-border p-2 text-sm text-ink"
          rows={3}
          value={notas}
          disabled={deshabilitado}
          onChange={(ev) => setNotas(ev.target.value)}
        />
      </div>

      {faltantes.length > 0 && (
        <div className="rounded-lg border border-border bg-warning-soft p-3 text-sm">
          <p id={idFaltantes} className="font-medium text-ink">
            Falta para cerrar
          </p>
          <ul aria-labelledby={idFaltantes} className="list-disc ml-5">
            {faltantes.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={deshabilitado || guardando}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Guardar
        </button>
        {guardando && <span className="text-xs text-muted">Guardando…</span>}
        {resultado?.updated_at && !guardando && (
          <span className="text-xs text-muted">Guardado</span>
        )}
      </div>
    </form>
  )
}

function textoRegimen(
  resultado: EtiquetaGuardada | null,
  exentos: Set<string>,
  nombre: (clave: string | null) => string | null,
): string {
  if (resultado === null || (resultado.regimen === null && resultado.regimen_regla === null)) {
    return "Todavía no hay régimen: se calcula al guardar, cuando estén completas las dimensiones que usa la regla."
  }
  if (resultado.regimen !== null && exentos.has(resultado.regimen)) {
    const regla = nombre(resultado.regimen_regla)
    return `Marcado como ${nombre(resultado.regimen)}. Con estas dimensiones, según la regla correspondería: ${regla ?? "no calculable todavía"}.`
  }
  return `Régimen según la regla: ${nombre(resultado.regimen ?? resultado.regimen_regla)}`
}
