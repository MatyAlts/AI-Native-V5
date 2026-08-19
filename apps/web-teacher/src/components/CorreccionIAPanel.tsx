/**
 * Disparo y resultado de una correccion asistida, para UN ejercicio.
 *
 * Tres reglas de esta UI, y ninguna es cosmetica:
 *
 * 1. **La nota la decide el docente.** Este panel MUESTRA, no califica. No
 *    escribe en `calificaciones` ni rellena nada solo.
 * 2. **Un fallo de infraestructura y un rechazo se ven distinto.** Ambar y
 *    "puede que reintentar sirva" para el primero; rojo para el segundo.
 *    Confundirlos ya costo dos dias de reintentos sobre una entrega que nunca
 *    se iba a destrabar sola.
 * 3. **Preview antes de gastar.** Cuesta plata y tiempo de computo, y el
 *    docente tiene que ver con que rubrica se va a corregir ANTES.
 */
import { AlertTriangle, Sparkles, XCircle } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import {
  type CorreccionIA,
  type CorreccionPreview,
  descargarPdfCorreccion,
  getCorreccionIA,
  listarCorreccionesIA,
  pedirCorreccionIA,
} from "../lib/api"

interface Props {
  entregaId: string
  orden: number
  getToken: () => Promise<string | null>
  /**
   * Avisa al padre que esta correccion cambio de estado.
   *
   * Sin esto la card de resumen se cargaba UNA vez al abrir el form y no se
   * enteraba de nada: el docente disparaba las correcciones, las veia
   * terminar en cada tarjeta, y el promedio ponderado —el entregable central
   * del epic— no aparecia hasta salir y volver a entrar.
   */
  onCambio?: (correccion: CorreccionIA) => void
}

const POLL_MS = 3000

function esCorreccion(x: CorreccionPreview | CorreccionIA): x is CorreccionIA {
  return "estado" in x
}

export function CorreccionIAPanel({ entregaId, orden, getToken, onCambio }: Props) {
  const [correccion, setCorreccion] = useState<CorreccionIA | null>(null)
  const [preview, setPreview] = useState<CorreccionPreview | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // `setTimeout` recursivo y no `setInterval`: con interval, una respuesta
  // lenta se solapa con el tick siguiente y se acumulan requests.
  const timerRef = useRef<number | null>(null)
  // `onCambio` por ref y no en las deps: el padre lo define inline, o sea
  // referencia nueva en cada render. En las deps de un `useEffect` eso es el
  // loop infinito con 429 que el repo ya documenta.
  const onCambioRef = useRef(onCambio)
  onCambioRef.current = onCambio

  const cargar = useCallback(async () => {
    try {
      const todas = await listarCorreccionesIA(entregaId, getToken)
      const mia = todas.find((c) => c.orden === orden) ?? null
      setCorreccion(mia)
      if (mia) onCambioRef.current?.(mia)
    } catch {
      // Silencioso: no tener correccion todavia es lo normal.
    }
  }, [entregaId, orden, getToken])

  useEffect(() => {
    void cargar()
  }, [cargar])

  // Polling mientras esta en vuelo, con limpieza en el unmount. Sin la
  // limpieza el timer sigue vivo despues de cerrar el form y pega contra un
  // componente desmontado.
  useEffect(() => {
    if (!correccion || (correccion.estado !== "pending" && correccion.estado !== "running")) {
      return
    }
    const id = correccion.id
    timerRef.current = window.setTimeout(async () => {
      try {
        const fresca = await getCorreccionIA(entregaId, id, getToken)
        setCorreccion(fresca)
        // El padre se entera en cada tick del poll, no solo al final: asi la
        // card aparece en cuanto la primera correccion termina.
        onCambioRef.current?.(fresca)
      } catch {
        // idem
      }
    }, POLL_MS)
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [correccion, entregaId, getToken])

  async function pedir(confirmado: boolean) {
    setCargando(true)
    setError(null)
    try {
      const r = await pedirCorreccionIA(entregaId, orden, confirmado, getToken)
      if (esCorreccion(r)) {
        setCorreccion(r)
        onCambioRef.current?.(r)
        setPreview(null)
      } else {
        setPreview(r)
      }
    } catch (e) {
      // No se muestra `String(e)` crudo: lleva el status y el cuerpo, que al
      // docente no le dicen nada y pueden traer detalle interno.
      setError(
        e instanceof Error && e.message.includes(":")
          ? e.message.split(":").slice(1).join(":").trim()
          : "No se pudo pedir la correccion.",
      )
    } finally {
      setCargando(false)
    }
  }

  if (correccion?.estado === "error") {
    return <BannerError correccion={correccion} onReintentar={() => void pedir(true)} />
  }

  if (correccion?.estado === "done") {
    return <Resultado correccion={correccion} entregaId={entregaId} getToken={getToken} />
  }

  if (correccion) {
    return (
      <p className="text-xs text-muted" data-testid="correccion-ia-en-curso">
        Corrigiendo... esto puede tardar un par de minutos.
      </p>
    )
  }

  return (
    <div className="space-y-2">
      {error && (
        <p className="text-xs text-danger" data-testid="correccion-ia-error">
          {error}
        </p>
      )}
      {preview ? (
        <PreviewCard
          preview={preview}
          cargando={cargando}
          onConfirmar={() => void pedir(true)}
          onCancelar={() => setPreview(null)}
        />
      ) : (
        <button
          type="button"
          onClick={() => void pedir(false)}
          disabled={cargando}
          data-testid="correccion-ia-pedir"
          className="inline-flex items-center gap-1.5 rounded border border-subtle px-3 py-1.5 text-xs text-secondary hover:bg-surface-hover disabled:opacity-50"
        >
          <Sparkles size={14} aria-hidden="true" />
          Corregir con IA
        </button>
      )}
    </div>
  )
}

function PreviewCard({
  preview,
  cargando,
  onConfirmar,
  onCancelar,
}: {
  preview: CorreccionPreview
  cargando: boolean
  onConfirmar: () => void
  onCancelar: () => void
}) {
  const desactualizada = preview.rubrica_estado === "desactualizado"
  return (
    <div
      className="rounded-lg border border-subtle p-3 text-xs space-y-2"
      data-testid="correccion-ia-preview"
    >
      <p className="text-body">
        Se va a corregir <strong>{preview.ejercicio_titulo}</strong> con la rubrica{" "}
        <span className="font-mono">{preview.rubrica_id}</span>.
      </p>
      {/* Una rubrica desactualizada no da una nota floja: corrige otra cosa. */}
      {desactualizada && (
        <p className="text-warning" data-testid="correccion-ia-rubrica-vieja">
          La rubrica de Active-IA quedo desactualizada respecto de la de aca. Sincronizala antes de
          corregir, o el resultado va a evaluar otra cosa.
        </p>
      )}
      {preview.rubrica_simulada && (
        <p className="text-warning" data-testid="correccion-ia-rubrica-simulada">
          Esta rubrica es SIMULADA: no existe en Active-IA. El resultado no va a servir.
        </p>
      )}
      {preview.ya_corregido && (
        <p className="text-muted">
          Este codigo ya se corrigio con esta rubrica: no se va a volver a cobrar.
        </p>
      )}
      <p className="text-muted">
        {(preview.codigo_bytes / 1024).toFixed(1)} KB de codigo · te quedan {preview.cuota_restante}{" "}
        correcciones hoy
      </p>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onConfirmar}
          disabled={cargando || preview.cuota_restante <= 0}
          data-testid="correccion-ia-confirmar"
          className="rounded px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: "var(--color-accent-brand)" }}
        >
          {cargando ? "Enviando..." : "Corregir"}
        </button>
        <button
          type="button"
          onClick={onCancelar}
          className="rounded border border-subtle px-3 py-1.5 text-xs text-secondary"
        >
          Cancelar
        </button>
      </div>
    </div>
  )
}

/** Ambar para infraestructura, rojo para rechazo. */
function BannerError({
  correccion,
  onReintentar,
}: {
  correccion: CorreccionIA
  onReintentar: () => void
}) {
  const infra = correccion.es_infraestructura
  return (
    <div
      className={`rounded-lg border p-3 text-xs ${
        infra
          ? "border-warning/30 bg-warning-soft text-warning"
          : "border-danger/30 bg-danger-soft text-danger"
      }`}
      data-testid={infra ? "correccion-ia-fallo-infra" : "correccion-ia-rechazo"}
    >
      <div className="flex items-start gap-2">
        {infra ? (
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
        ) : (
          <XCircle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
        )}
        <div className="space-y-1">
          <p>
            {infra
              ? "La correccion no se pudo completar: el servicio no respondio. No hay nota."
              : "El servicio rechazo esta correccion. No hay nota."}
          </p>
          {correccion.error_detail && <p className="text-muted">{correccion.error_detail}</p>}
          {infra ? (
            <button
              type="button"
              onClick={onReintentar}
              className="underline"
              data-testid="correccion-ia-reintentar"
            >
              Reintentar
            </button>
          ) : (
            <p className="text-muted">Reintentar sin cambiar nada va a devolver el mismo error.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function Resultado({
  correccion,
  entregaId,
  getToken,
}: {
  correccion: CorreccionIA
  entregaId: string
  getToken: () => Promise<string | null>
}) {
  const [bajando, setBajando] = useState(false)

  async function bajarPdf() {
    setBajando(true)
    try {
      const blob = await descargarPdfCorreccion(entregaId, correccion.id, getToken)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `devolucion_${correccion.id.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      // El PDF es un extra: la nota esta arriba igual.
    } finally {
      setBajando(false)
    }
  }

  return (
    <div
      className="rounded-lg border border-subtle p-3 text-xs space-y-1"
      data-testid="correccion-ia-resultado"
    >
      <p className="text-body">
        Active-IA sugiere <strong>{correccion.nota_100}/100</strong>
      </p>
      {/* Desde el 19/08 el codigo que no compila se manda igual a corregir: un
          punto y coma que falta no justifica dejar al alumno sin devolucion.
          Pero entonces esta nota se calculo sobre codigo que NUNCA CORRIO, y
          el docente tiene que verlo antes de usarla como base — si no, un
          criterio de "funciona" que el motor haya dado por cumplido pasa a la
          calificacion sin que nada lo respalde. */}
      {correccion.tests_snapshot?.compila === false && (
        <p
          className="rounded border border-warning/30 bg-warning-soft p-2 text-warning"
          data-testid="correccion-ia-no-compila"
        >
          <strong>Ojo: este codigo no compila.</strong> La nota sale de leerlo, no de
          ejecutarlo: ningun test lo respalda.
          {correccion.tests_snapshot?.error_compilacion && (
            <span className="mt-1 block font-mono text-[11px] opacity-80">
              {correccion.tests_snapshot.error_compilacion}
            </span>
          )}
        </p>
      )}
      {correccion.tiene_pdf && (
        <button
          type="button"
          onClick={() => void bajarPdf()}
          disabled={bajando}
          data-testid="correccion-ia-pdf"
          className="underline text-secondary disabled:opacity-50"
        >
          {bajando ? "Bajando..." : "Bajar el PDF de devolucion"}
        </button>
      )}
      {/* La nota la decide el docente, siempre. */}
      <p className="text-muted">
        Es una sugerencia: no se guarda ni rellena la calificacion. Sumá los criterios y comparalos
        con el total antes de darla por buena.
      </p>
    </div>
  )
}
