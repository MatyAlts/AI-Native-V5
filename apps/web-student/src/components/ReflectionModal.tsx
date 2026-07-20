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

  useEffect(() => {
    if (isOpen) {
      openedAtRef.current = Date.now()
      setQueAprendiste("")
      setDificultad("")
      setQueDistinto("")
      setError(null)
      setSubmitting(false)
    } else {
      openedAtRef.current = null
    }
  }, [isOpen])

  async function handleSubmit() {
    if (!episodeId || submitting) return
    if (openedAtRef.current === null) {
      // Defensa: si el ref no se hidrato, no enviamos un valor invalido.
      return
    }
    setSubmitting(true)
    setError(null)
    const tiempoMs = Date.now() - openedAtRef.current
    try {
      await submitReflection(episodeId, {
        que_aprendiste: queAprendiste,
        dificultad_encontrada: dificultad,
        que_haria_distinto: queDistinto,
        prompt_version: PROMPT_VERSION,
        tiempo_completado_ms: Math.max(0, tiempoMs),
      })
      onClose(true)
    } catch (e) {
      setError(`Error enviando reflexion: ${e}`)
      setSubmitting(false)
    }
  }

  function handleSkip() {
    if (submitting) return
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
          Tomate un minuto para pensar sobre el episodio que acabas de cerrar.
          Esto es para vos — no es una entrega, no se califica, y nadie te va
          a responder. Pensar sobre lo que hiciste mientras todavia esta fresco
          es parte del proceso.
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

        {error && (
          <div className="bg-danger-soft text-danger px-3 py-2 text-sm rounded">
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
      <p
        className={`text-xs mt-1 text-right ${
          overLimit ? "text-danger" : "text-muted"
        }`}
      >
        {remaining} chars restantes
      </p>
    </div>
  )
}
