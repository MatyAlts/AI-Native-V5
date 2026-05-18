/**
 * Panel de notas del estudiante durante un episodio.
 *
 * Permite al alumno escribir anotaciones libres sobre su razonamiento,
 * dudas o decisiones. Cada nota guardada emite un evento CTR
 * `anotacion_creada` (el backend valida 1..5000 chars y responde 422 si
 * no se cumple).
 *
 * El panel mantiene una historia local read-only de las notas guardadas
 * en esta sesión — no las re-fetchea del backend; si el alumno refresca,
 * la recuperación de estado del episodio (G4) las trae desde CTR.
 */
import { useState } from "react"
import { emitAnotacionCreada } from "../lib/api"

interface SavedNote {
  contenido: string
  ts: number
}

const MAX_LEN = 5000

export interface NotesPanelProps {
  episodeId: string
  /** Notas iniciales (opcional) — vienen de la recuperación de estado. */
  initialNotes?: SavedNote[]
}

export function NotesPanel({ episodeId, initialNotes }: NotesPanelProps) {
  const [open, setOpen] = useState(true)
  const [draft, setDraft] = useState("")
  const [notes, setNotes] = useState<SavedNote[]>(initialNotes ?? [])
  const [saving, setSaving] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  const trimmed = draft.trim()
  const tooLong = trimmed.length > MAX_LEN
  const canSave = trimmed.length > 0 && !tooLong && !saving

  async function handleSave() {
    if (!canSave) return
    setSaving(true)
    setValidationError(null)
    try {
      await emitAnotacionCreada(episodeId, { contenido: trimmed })
      setNotes((prev) => [...prev, { contenido: trimmed, ts: Date.now() }])
      setDraft("")
    } catch (e) {
      const status = (e as Error & { status?: number }).status
      if (status === 422) {
        setValidationError("La nota no es válida (vacía, sólo espacios o supera 5000 caracteres).")
      } else {
        setValidationError(`Error guardando la nota: ${String(e)}`)
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="flex flex-col rounded-lg border border-border-soft bg-surface overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-2 flex items-center justify-between text-left border-b border-border-soft hover:bg-surface-alt"
      >
        <span className="text-sm font-medium">
          Mis notas{" "}
          {notes.length > 0 && (
            <span className="text-xs text-muted ml-1">({notes.length})</span>
          )}
        </span>
        <span className="text-xs text-muted">{open ? "Ocultar" : "Mostrar"}</span>
      </button>

      {open && (
        <div className="flex flex-col gap-2 p-3">
          <textarea
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              if (validationError) setValidationError(null)
            }}
            placeholder="Anotá tu razonamiento, dudas, decisiones..."
            rows={4}
            disabled={saving}
            className="w-full px-3 py-2 text-sm rounded border border-border bg-surface-alt resize-none focus:outline-none focus:border-accent-brand"
          />
          <div className="flex items-center justify-between gap-2">
            <span
              className={`text-xs ${tooLong ? "text-[var(--color-danger)]" : "text-muted"}`}
            >
              {trimmed.length}/{MAX_LEN}
            </span>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave}
              className="px-3 py-1 text-sm bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border-strong text-white rounded font-medium"
            >
              {saving ? "Guardando..." : "Guardar nota"}
            </button>
          </div>
          {validationError && (
            <p className="text-xs text-[var(--color-danger)]">{validationError}</p>
          )}

          {notes.length > 0 && (
            <div className="mt-2 pt-2 border-t border-border-soft max-h-48 overflow-y-auto space-y-2">
              {notes.map((n, i) => (
                <div
                  key={`${n.ts}-${i}`}
                  className="text-xs rounded bg-surface-alt border border-border-soft p-2"
                >
                  <div className="text-muted-soft mb-1">{new Date(n.ts).toLocaleTimeString()}</div>
                  <div className="whitespace-pre-wrap text-body">
                    {n.contenido}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
