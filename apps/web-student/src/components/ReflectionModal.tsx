import { Modal } from "@platform/ui"
import { useEffect, useRef, useState } from "react"
import { submitReflection } from "../lib/api"

/**
 * Modal de reflexion metacognitiva post-cierre del episodio (ADR-035).
 *
 * NO bloqueante: el cierre del episodio ya emitio `EpisodioCerrado` al CTR
 * antes de que este modal se muestre. El alumno puede saltarlo (boton
 * "Saltar") sin emitir `reflexion_completada`. La cadena criptografica
 * sigue intacta.
 *
 * Privacy: el contenido textual viaja al backend como string libre. El
 * export academico redacta los 3 campos por default (`include_reflections`
 * = false). Investigador con consentimiento usa el flag explicito.
 *
 * Reproducibilidad: el classifier IGNORA `reflexion_completada` (filtrado
 * en `pipeline.py::_EXCLUDED_FROM_FEATURES`) — la presencia o ausencia de
 * reflexion NO afecta el resultado de la clasificacion N4 ni el
 * `classifier_config_hash`.
 */

// NOTE (R6 del informeSoc.md, 2026-05-16): textos de las 3 preguntas
// reescritos para ser metacognitivamente situados en vez de genericos. Las
// keys del payload (que_aprendiste, dificultad_encontrada, que_haria_distinto)
// se preservan para no romper el contrato CTR ni los tests del tutor-service
// (test_reflexion_completada.py linea 168/182/206/239). Si en algun momento
// se decide bumpear a "reflection/v1.1.0" por la divergencia semantica de
// las preguntas, hay que coordinar:
//   1. Actualizar prompt_version aca.
//   2. Actualizar tests_reflexion_completada.py con el nuevo valor esperado.
//   3. Agregar entrada al manifest si corresponde (hoy reflection no esta
//      versionado en manifest.yaml, vive solo en este string).
// Por ahora v1.0.0 sigue siendo el version label canonico — el cambio de
// copy NO bumpea por si solo, igual que un bump de comentarios HTML en
// system.md no cambia el comportamiento del modelo.
const PROMPT_VERSION = "reflection/v1.0.0"
const MAX_CHARS = 500

interface ReflectionModalProps {
  isOpen: boolean
  episodeId: string | null
  // `submitted=true` → el alumno completo las 3 preguntas y se emitio
  // reflexion_completada al CTR. `submitted=false` → cerro sin reflexionar
  // (boton "No quiero reflexionar ahora" o escape/click-outside). La
  // pantalla post-cierre lo usa para diferenciar el tono pedagogico
  // (QA round 2 bug ROUND2-BUG / Etapa 1.1).
  onClose: (submitted: boolean) => void
}

/** Esperas entre reintentos ante un 409, en milisegundos.
 *
 * El 409 de este endpoint significa "el episodio todavia no figura cerrado", y
 * eso se resuelve solo cuando el `partition_worker` drena el evento de cierre.
 * Tres intentos cubren ~5s de retraso del worker, que es holgado para el caso
 * normal; si tarda mas que eso hay algo roto de verdad y el alumno tiene que
 * enterarse, no quedarse mirando un boton que gira.
 *
 * Exportada para que el test no tenga que esperar 5 segundos de reloj real. */
export const ESPERAS_409_MS = [600, 1500, 3000] as const

export function ReflectionModal({ isOpen, episodeId, onClose }: ReflectionModalProps) {
  const [queAprendiste, setQueAprendiste] = useState("")
  const [dificultad, setDificultad] = useState("")
  const [queDistinto, setQueDistinto] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Marca temporal de apertura para calcular `tiempo_completado_ms`. Se
  // resetea cada vez que el modal se abre — usamos useRef para que el reset
  // ocurra dentro del effect, no en cada render.
  const openedAtRef = useRef<number | null>(null)

  // Clave de idempotencia estable por apertura del modal. El reintento tras un
  // error de red reusa el MISMO valor y el backend devuelve el seq ya asignado
  // en vez de emitir un segundo `reflexion_completada` — que post-cierre
  // colisionaria en seq (sin sesion Redis el seq sale de `events_count`) y
  // mandaria a la DLQ un episodio ya cerrado, marcandolo integrity_compromised.
  const idempotencyKeyRef = useRef<string | null>(null)

  /** Guard doble-submit SINCRONICO (NB-11).
   *
   * El state `submitting` se actualiza de forma asincronica: entre el primer
   * click y el re-render que lo pone en `true` entran mas clicks, y el guard
   * `if (submitting) return` los deja pasar. `EpisodePage.handleClose` ya usa
   * una ref por este motivo; este modal habia quedado afuera del patron.
   *
   * Hoy el backend absorbe el doble envio por la `Idempotency-Key` compartida
   * —los dos requests devuelven el mismo seq—, asi que el guard no evita un
   * evento duplicado. Evita dos POST y, sobre todo, dos cadenas de reintento
   * corriendo en paralelo sobre el mismo modal. */
  const enviandoRef = useRef(false)
  /** Mostrado mientras se reintenta por un 409: el alumno tiene que saber que
      la demora es del sistema terminando de cerrar, no de su conexion. */
  const [esperandoCierre, setEsperandoCierre] = useState(false)

  useEffect(() => {
    if (isOpen) {
      openedAtRef.current = Date.now()
      idempotencyKeyRef.current = crypto.randomUUID()
      setQueAprendiste("")
      setDificultad("")
      setQueDistinto("")
      setError(null)
      setSubmitting(false)
    } else {
      openedAtRef.current = null
      idempotencyKeyRef.current = null
    }
  }, [isOpen])

  async function handleSubmit() {
    if (!episodeId || enviandoRef.current) return
    if (openedAtRef.current === null) {
      // Defensa: si el ref no se hidrato, no enviamos un valor invalido.
      return
    }
    enviandoRef.current = true
    setSubmitting(true)
    setError(null)
    setEsperandoCierre(false)
    const tiempoMs = Date.now() - openedAtRef.current

    try {
      for (let intento = 0; ; intento++) {
        try {
          await submitReflection(
            episodeId,
            {
              que_aprendiste: queAprendiste,
              dificultad_encontrada: dificultad,
              que_haria_distinto: queDistinto,
              prompt_version: PROMPT_VERSION,
              tiempo_completado_ms: Math.max(0, tiempoMs),
            },
            idempotencyKeyRef.current ?? undefined,
          )
          onClose(true)
          return
        } catch (e) {
          const status = (e as Error & { status?: number }).status
          if (status !== 409 || intento >= ESPERAS_409_MS.length) throw e

          // 409 ACA SIGNIFICA "TODAVIA NO", NO "NO".
          //
          // El unico camino de 409 del endpoint es que el episodio no figure
          // todavia como `closed`. Y eso es una carrera, no un error del
          // alumno: cerrar el episodio publica `episodio_cerrado` al CTR, que
          // responde 202 apenas hace el XADD a Redis —la persistencia es
          // asincronica—, y el `partition_worker` recien pone
          // `estado = "closed"` cuando drena ese evento. Este modal se abre
          // sobre el 202, asi que un alumno que escribe rapido llega antes que
          // el worker.
          //
          // Reintentar es SEGURO porque la `Idempotency-Key` es la misma en
          // todos los intentos: si alguno llegara a persistir, el siguiente
          // recibe el seq ya asignado en vez de emitir un segundo evento.
          //
          // Y era necesario: sin esto, el 409 PIERDE la reflexion. El chequeo
          // de estado corta antes de publicar al CTR, asi que no es un "se
          // guardo pero el ACK se perdio" — no se escribe nada, y para la
          // tesis queda un `reflexion_completada` que no existe.
          setEsperandoCierre(true)
          await new Promise((r) => setTimeout(r, ESPERAS_409_MS[intento]))
        }
      }
    } catch (e) {
      const status = (e as Error & { status?: number }).status
      setError(
        status === 409
          ? "Todavia estamos terminando de cerrar tu episodio. Esperá unos segundos y volvé a enviar — lo que escribiste no se pierde."
          : `No pudimos enviar tu reflexion. Probá de nuevo; lo que escribiste no se pierde. (detalle: ${e})`,
      )
      setSubmitting(false)
      setEsperandoCierre(false)
    } finally {
      enviandoRef.current = false
    }
  }

  function handleSkip() {
    if (enviandoRef.current) return
    onClose(false)
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleSkip}
      title="Antes de cerrar — un minuto para pensar"
      size="lg"
    >
      <div className="space-y-4 text-sm text-body">
        <p className="text-muted">
          Tomate un minuto para pensar sobre el episodio que acabas de cerrar. Esto es para vos — no
          es una entrega, no se califica, y nadie te va a responder. Pensar sobre lo que hiciste
          mientras todavia esta fresco es parte del proceso.
        </p>

        <ReflectionTextarea
          id="que-aprendiste"
          label="¿En que momento del episodio sentiste que algo hizo click?"
          hint="Un instante concreto — cuando entendiste algo, cuando viste como encajaba, cuando te diste cuenta de un error. Si no hubo, contanos en que momento estuviste mas perdido."
          value={queAprendiste}
          onChange={setQueAprendiste}
        />

        <ReflectionTextarea
          id="dificultad-encontrada"
          label="Si alguien viniera a hacer el mismo ejercicio manana, ¿que le contarias sobre como encararlo?"
          hint="No la solucion — el enfoque. Como pensarias el problema, por donde empezarias, que cosas tendrias en mente."
          value={dificultad}
          onChange={setDificultad}
        />

        <ReflectionTextarea
          id="que-haria-distinto"
          label="¿Te quedaste con alguna pregunta sin responder?"
          hint="Algo que no te quedo del todo claro, una duda que no llegaste a resolver, una curiosidad que te quedo. Aunque no la respondas, identificarla te ayuda."
          value={queDistinto}
          onChange={setQueDistinto}
        />

        {/* Mientras se reintenta por un 409. Sin esto el alumno ve el boton
            girando hasta cinco segundos sin saber por que, y el silencio se
            lee como "se colgo". */}
        {esperandoCierre && !error && (
          // `<output>` y no un `div` con role: trae `role="status"` implicito y
          // es el elemento semantico para un estado en vivo — el lector de
          // pantalla lo anuncia sin interrumpir lo que el alumno este leyendo.
          <output
            className="block bg-surface-soft text-muted px-3 py-2 text-sm rounded"
            data-testid="reflexion-esperando-cierre"
          >
            Estamos terminando de cerrar tu episodio. Tu reflexion se envia en cuanto termine — no
            cierres esta ventana.
          </output>
        )}

        {error && (
          <div
            role="alert"
            className="bg-danger-soft text-danger px-3 py-2 text-sm rounded"
            data-testid="reflexion-error"
          >
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={handleSkip}
            disabled={submitting}
            className="px-4 py-2 text-sm border border-border rounded hover:bg-surface-alt disabled:opacity-50"
          >
            No quiero reflexionar ahora
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 text-sm bg-accent-brand hover:bg-accent-brand-deep text-white rounded disabled:opacity-50"
          >
            {submitting ? "Enviando..." : "Enviar"}
          </button>
        </div>
      </div>
    </Modal>
  )
}

interface ReflectionTextareaProps {
  id: string
  label: string
  hint: string
  value: string
  onChange: (v: string) => void
}

function ReflectionTextarea({ id, label, hint, value, onChange }: ReflectionTextareaProps) {
  const remaining = MAX_CHARS - value.length
  const overLimit = remaining < 0

  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium mb-1">
        {label}
      </label>
      <p className="text-xs text-muted mb-2">{hint}</p>
      <textarea
        id={id}
        value={value}
        onChange={(e) => {
          // Cap en el cliente para evitar que el backend rechace con 422.
          // El backend igual valida defensivamente.
          if (e.target.value.length <= MAX_CHARS) onChange(e.target.value)
        }}
        rows={3}
        className="w-full px-3 py-2 text-sm border border-border bg-surface rounded resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <p className={`text-xs mt-1 text-right ${overLimit ? "text-danger" : "text-muted"}`}>
        {remaining} chars restantes
      </p>
    </div>
  )
}
