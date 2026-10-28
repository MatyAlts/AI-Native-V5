/**
 * "Mi trabajo corregido" — change `alumno-mis-trabajos-corregidos`.
 *
 * Nota + devolucion (las pinta `GradeDetailView`, sin tocarlo) y, debajo, el
 * codigo que el alumno ENTREGO en cada ejercicio, con boton de descarga.
 *
 * SOLO LECTURA, por construccion y por test: las unicas llamadas son
 *   GET /entregas/{id}/calificacion   (GradeDetailView)
 *   GET /entregas/{id}/artefacto
 *   GET /episodes/{id}                (al apretar "Descargar")
 * No abre/cierra/reanuda episodios, no emite eventos al CTR, no crea
 * entregas y no registra listeners de pestana: no puede alterar la traza
 * cognitiva ni los resultados de la tesis. No usa `CodeEditor` (Monaco emite
 * `edicion_codigo`): el codigo va en un `<pre>`.
 */
import { useEffect, useState } from "react"
import {
  type Entrega,
  type EntregaArtefacto,
  EntregaArtefactoError,
  getEntregaArtefacto,
  getEpisodeState,
} from "../lib/api"
import { archivoDeDescarga, ejerciciosDelTrabajo } from "../utils/trabajoCorregido"
import { GradeDetailView } from "./GradeDetailView"

export interface TrabajoCorregidoViewProps {
  entrega: Entrega
  onBack: () => void
}

type CargaCodigo =
  | { tipo: "cargando" }
  | { tipo: "ok"; datos: EntregaArtefacto }
  | { tipo: "no_disponible" }
  | { tipo: "error" }

export function TrabajoCorregidoView({ entrega, onBack }: TrabajoCorregidoViewProps) {
  const [carga, setCarga] = useState<CargaCodigo>({ tipo: "cargando" })
  const [descargando, setDescargando] = useState<number | null>(null)
  const [avisos, setAvisos] = useState<Record<number, string>>({})

  useEffect(() => {
    let cancelled = false
    setCarga({ tipo: "cargando" })
    getEntregaArtefacto(entrega.id)
      .then((datos) => {
        if (!cancelled) setCarga({ tipo: "ok", datos })
      })
      .catch((e) => {
        if (cancelled) return
        const noDisponible = e instanceof EntregaArtefactoError && e.status === 404
        setCarga({ tipo: noDisponible ? "no_disponible" : "error" })
      })
    return () => {
      cancelled = true
    }
  }, [entrega.id])

  async function descargar(ej: ReturnType<typeof ejerciciosDelTrabajo>[number]) {
    const { artefacto, titulo } = ej
    setDescargando(artefacto.orden)
    setAvisos((a) => ({ ...a, [artefacto.orden]: "" }))
    try {
      // La charla sale del episodio que nombra el ARTEFACTO (cerrado), nunca
      // del de `ejercicio_estados`. Si falla, el codigo se descarga igual.
      let messages = null
      let aviso = ""
      try {
        if (!artefacto.episode_id) throw new Error("sin episodio")
        messages = (await getEpisodeState(artefacto.episode_id)).messages
      } catch {
        aviso = "La charla con el tutor no se pudo incluir."
      }
      const { filename, content } = archivoDeDescarga(artefacto, messages, {
        ejercicioTitulo: `${entrega.tarea_titulo ?? "TP"} - ${titulo}`,
        fecha: new Date().toLocaleString(),
      })
      const blob = new Blob([content], { type: "text/plain;charset=utf-8" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      setAvisos((v) => ({ ...v, [artefacto.orden]: aviso }))
    } catch (e) {
      setAvisos((v) => ({
        ...v,
        [artefacto.orden]: `No se pudo descargar el ${titulo.toLowerCase()}: ${String(e)}`,
      }))
    } finally {
      setDescargando(null)
    }
  }

  const ejercicios = carga.tipo === "ok" ? ejerciciosDelTrabajo(carga.datos.artefactos) : []

  return (
    <div className="flex-1 overflow-y-auto" data-testid="trabajo-corregido-view">
      <GradeDetailView entrega={entrega} onBack={onBack} />

      <section className="max-w-2xl mx-auto px-6 pb-10" aria-label="Codigo que entregaste">
        <h3 className="text-base font-semibold text-ink mb-4">Lo que entregaste</h3>

        {carga.tipo === "cargando" && (
          <div
            data-testid="codigo-cargando"
            className="h-24 rounded-lg bg-surface motion-safe:animate-pulse"
          />
        )}

        {carga.tipo === "error" && (
          <p
            data-testid="codigo-error"
            className="rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger"
          >
            No pudimos traer tu código. Probá de nuevo.
          </p>
        )}

        {carga.tipo === "no_disponible" && (
          <p data-testid="codigo-no-disponible" className="text-sm text-muted">
            Este código no está disponible.
          </p>
        )}

        {carga.tipo === "ok" && ejercicios.length === 0 && (
          <p data-testid="sin-codigo-guardado" className="text-sm text-muted">
            Esta entrega es anterior a que la plataforma guardara el código entregado.
          </p>
        )}

        <div className="space-y-6">
          {ejercicios.map((ej) => {
            const { artefacto, titulo } = ej
            const ext = artefacto.language === "java" ? ".java" : ".py"
            return (
              <article key={artefacto.orden}>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-medium text-body">{titulo}</h4>
                  <button
                    type="button"
                    onClick={() => descargar(ej)}
                    disabled={descargando === artefacto.orden}
                    className="text-xs rounded border border-border-soft px-3 py-1.5 text-body hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60"
                  >
                    {descargando === artefacto.orden ? "Descargando…" : `Descargar (${ext})`}
                  </button>
                </div>
                <pre
                  data-testid="ejercicio-codigo"
                  className="overflow-x-auto rounded-lg border border-border-soft bg-surface p-4 text-xs font-mono"
                >
                  {artefacto.codigo}
                </pre>
                {avisos[artefacto.orden] && (
                  <output className="block mt-2 text-xs text-warning/90">
                    {avisos[artefacto.orden]}
                  </output>
                )}
              </article>
            )
          })}
        </div>
      </section>
    </div>
  )
}
