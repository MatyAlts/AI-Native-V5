/**
 * Wizard de generacion de TP con IA (ADR-036).
 *
 * Paso 1 — Prompt: descripcion, cantidad de ejercicios, dificultad, contexto.
 * Paso 2 — Preview + edicion: cada ejercicio es editable inline (enunciado,
 *   codigo, rubrica). El docente ajusta y luego guarda todos los ejercicios
 *   como TPs individuales.
 */
import { MarkdownRenderer, Modal } from "@platform/ui"
import { useCallback, useEffect, useState } from "react"
import {
  type DificultadIA,
  type EjercicioGenerado,
  type GenerateTPResponse,
  type TareaPracticaTemplate,
  generateTPWithAI,
  listMyComisiones,
  tareasPracticasTemplatesApi,
} from "../lib/api"

interface Props {
  isOpen: boolean
  comisionId: string
  getToken: () => Promise<string | null>
  onClose: () => void
  onUseResult: (ejercicios: EjercicioGenerado[], templateId?: string | null) => void
}

type Step = "prompt" | "preview"

export function GenerarConIAWizard({ isOpen, comisionId, getToken, onClose, onUseResult }: Props) {
  const [step, setStep] = useState<Step>("prompt")
  const [materiaId, setMateriaId] = useState<string | null>(null)
  const [periodoId, setPeriodoId] = useState<string | null>(null)

  const [descripcion, setDescripcion] = useState("")
  const [numEjercicios, setNumEjercicios] = useState(3)
  const [dificultad, setDificultad] = useState<DificultadIA | null>(null)
  const [contexto, setContexto] = useState("")

  const [templates, setTemplates] = useState<TareaPracticaTemplate[]>([])
  const [templateId, setTemplateId] = useState<string | null>(null)

  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [result, setResult] = useState<GenerateTPResponse | null>(null)
  const [ejercicios, setEjercicios] = useState<EjercicioGenerado[]>([])

  const selectedTemplate = templates.find((t) => t.id === templateId) ?? null

  const handleClose = useCallback(() => {
    setStep("prompt")
    setDescripcion("")
    setNumEjercicios(3)
    setDificultad(null)
    setContexto("")
    setTemplateId(null)
    setGenerateError(null)
    setResult(null)
    setEjercicios([])
    onClose()
  }, [onClose])

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    listMyComisiones(getToken)
      .then((res) => {
        if (cancelled) return
        const found = res.items.find((c) => c.id === comisionId)
        setMateriaId(found?.materia_id ?? null)
        setPeriodoId(found?.periodo_id ?? null)
      })
      .catch(() => {
        if (!cancelled) {
          setMateriaId(null)
          setPeriodoId(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, comisionId, getToken])

  // Cargar plantillas disponibles para (materia, periodo) — selector opcional.
  useEffect(() => {
    if (!isOpen || !materiaId || !periodoId) return
    let cancelled = false
    tareasPracticasTemplatesApi
      .list({ materia_id: materiaId, periodo_id: periodoId }, getToken)
      .then((res) => {
        if (!cancelled) setTemplates(res.filter((t) => t.estado !== "archived"))
      })
      .catch(() => {
        if (!cancelled) setTemplates([])
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, materiaId, periodoId, getToken])

  const handleSelectTemplate = (id: string | null) => {
    setTemplateId(id)
    if (id) {
      const t = templates.find((x) => x.id === id)
      if (t && !descripcion.trim()) {
        setDescripcion(t.consigna)
      }
    }
  }

  const handleGenerar = async () => {
    if (!materiaId) {
      setGenerateError("No se pudo resolver la materia de esta comision.")
      return
    }
    if (descripcion.trim().length < 10) {
      setGenerateError("La descripcion debe tener al menos 10 caracteres.")
      return
    }
    setGenerateError(null)
    setGenerating(true)
    try {
      const res = await generateTPWithAI(
        {
          materia_id: materiaId,
          descripcion_nl: descripcion.trim(),
          num_ejercicios: numEjercicios,
          ...(dificultad ? { dificultad } : {}),
          ...(contexto.trim() ? { contexto: contexto.trim() } : {}),
          comision_id: comisionId,
          ...(templateId ? { template_id: templateId } : {}),
        },
        getToken,
      )
      setResult(res)
      setEjercicios(res.ejercicios)
      setStep("preview")
    } catch (e) {
      setGenerateError(String(e))
    } finally {
      setGenerating(false)
    }
  }

  const handleUsar = () => {
    if (!ejercicios.length) return
    const tplId = templateId
    handleClose()
    onUseResult(ejercicios, tplId)
  }

  const updateEjercicio = (index: number, updates: Partial<EjercicioGenerado>) => {
    setEjercicios((prev) => prev.map((ej, i) => (i === index ? { ...ej, ...updates } : ej)))
  }

  const removeEjercicio = (index: number) => {
    setEjercicios((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={
        step === "prompt" ? "Generar TP con IA" : `Ejercicios generados (${ejercicios.length})`
      }
      size="xl"
    >
      {step === "prompt" && (
        <PromptStep
          descripcion={descripcion}
          numEjercicios={numEjercicios}
          dificultad={dificultad}
          contexto={contexto}
          generating={generating}
          error={generateError}
          materiaResolved={Boolean(materiaId)}
          templates={templates}
          templateId={templateId}
          selectedTemplate={selectedTemplate}
          onDescripcionChange={setDescripcion}
          onNumEjerciciosChange={setNumEjercicios}
          onDificultadChange={setDificultad}
          onContextoChange={setContexto}
          onTemplateChange={handleSelectTemplate}
          onGenerar={handleGenerar}
          onClose={handleClose}
        />
      )}
      {step === "preview" && result && (
        <PreviewStep
          ejercicios={ejercicios}
          result={result}
          onUpdateEjercicio={updateEjercicio}
          onRemoveEjercicio={removeEjercicio}
          onEditar={() => setStep("prompt")}
          onUsar={handleUsar}
        />
      )}
    </Modal>
  )
}

interface PromptStepProps {
  descripcion: string
  numEjercicios: number
  dificultad: DificultadIA | null
  contexto: string
  generating: boolean
  error: string | null
  materiaResolved: boolean
  templates: TareaPracticaTemplate[]
  templateId: string | null
  selectedTemplate: TareaPracticaTemplate | null
  onDescripcionChange: (v: string) => void
  onNumEjerciciosChange: (v: number) => void
  onDificultadChange: (v: DificultadIA | null) => void
  onContextoChange: (v: string) => void
  onTemplateChange: (id: string | null) => void
  onGenerar: () => void
  onClose: () => void
}

function PromptStep({
  descripcion,
  numEjercicios,
  dificultad,
  contexto,
  generating,
  error,
  materiaResolved,
  templates,
  templateId,
  selectedTemplate,
  onDescripcionChange,
  onNumEjerciciosChange,
  onDificultadChange,
  onContextoChange,
  onTemplateChange,
  onGenerar,
  onClose,
}: PromptStepProps) {
  const DIFICULTADES: { value: DificultadIA; label: string }[] = [
    { value: "basica", label: "Basica" },
    { value: "intermedia", label: "Intermedia" },
    { value: "avanzada", label: "Avanzada" },
  ]

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">
        Describe el trabajo practico. La IA generara los ejercicios con enunciado, codigo inicial,
        rubrica y casos de prueba. Despues podes editar cada uno.
      </p>

      {templates.length > 0 && (
        <div className="rounded-lg border border-border bg-surface-alt/40 p-3 space-y-2">
          <label className="block text-xs font-medium text-ink">
            Usar plantilla de la cátedra
            <span className="text-muted font-normal ml-1">(opcional)</span>
          </label>
          <select
            value={templateId ?? ""}
            onChange={(e) => onTemplateChange(e.target.value || null)}
            className="w-full px-2 py-1.5 text-sm border border-border rounded bg-white"
          >
            <option value="">— Sin plantilla (descripción libre) —</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.codigo} · {t.titulo} (v{t.version}, {t.estado})
              </option>
            ))}
          </select>
          {selectedTemplate && (
            <div className="rounded bg-white border border-border-soft p-2">
              <div className="text-[10px] uppercase tracking-wide text-muted mb-1">
                Consigna pedagógica de la plantilla
              </div>
              <p className="text-xs whitespace-pre-wrap text-body">
                {selectedTemplate.consigna}
              </p>
              <p className="text-[11px] text-muted mt-2">
                Se pasa al LLM como contexto y se asocia el TP resultante a esta plantilla
                via <code>template_id</code> para trazabilidad.
              </p>
            </div>
          )}
        </div>
      )}

      <div>
        <label className="block text-xs font-medium text-ink mb-1.5">
          Descripcion del TP
          <span className="text-muted font-normal ml-1">(obligatorio)</span>
        </label>
        <textarea
          value={descripcion}
          onChange={(e) => onDescripcionChange(e.target.value)}
          rows={5}
          maxLength={2000}
          placeholder="Descri el TP que necesitas. Ej: Un trabajo practico de listas enlazadas con ejercicios de insercion, busqueda y eliminacion..."
          className="w-full px-3 py-2 text-sm text-ink border border-border rounded-lg bg-white resize-none focus:outline-none focus:border-ink transition-colors"
        />
        <div className="flex justify-end mt-1">
          <span className="text-xs text-muted">{descripcion.length}/2000</span>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-ink mb-1.5">Cantidad de ejercicios</label>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={1}
            max={10}
            value={numEjercicios}
            onChange={(e) => onNumEjerciciosChange(Number(e.target.value))}
            className="flex-1 accent-[#111111]"
          />
          <span className="text-sm font-medium text-ink w-6 text-center tabular-nums">
            {numEjercicios}
          </span>
        </div>
      </div>

      <div>
        <span className="block text-xs font-medium text-ink mb-2">
          Dificultad
          <span className="text-muted font-normal ml-1">(opcional)</span>
        </span>
        <div className="flex gap-2">
          {DIFICULTADES.map((d) => (
            <button
              key={d.value}
              type="button"
              onClick={() => onDificultadChange(dificultad === d.value ? null : d.value)}
              className={`px-4 py-1.5 text-xs font-medium rounded-md border transition-colors ${
                dificultad === d.value
                  ? "bg-ink text-white border-ink"
                  : "bg-white text-ink border-border hover:border-ink"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-ink mb-1.5">
          Contexto adicional
          <span className="text-muted font-normal ml-1">(opcional)</span>
        </label>
        <textarea
          value={contexto}
          onChange={(e) => onContextoChange(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="Contexto adicional: temas vistos, restricciones, etc."
          className="w-full px-3 py-2 text-sm text-ink border border-border rounded-lg bg-white resize-none focus:outline-none focus:border-ink transition-colors"
        />
        <div className="flex justify-end mt-1">
          <span className="text-xs text-muted">{contexto.length}/2000</span>
        </div>
      </div>

      {!materiaResolved && (
        <div className="text-xs text-muted bg-canvas border border-border rounded-lg p-3">
          Resolviendo materia de la comision...
        </div>
      )}

      {error && (
        <div className="text-sm text-danger bg-danger-soft border border-danger/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2 border-t border-border">
        <button
          type="button"
          onClick={onClose}
          disabled={generating}
          className="px-4 py-1.5 text-sm border border-border rounded-md hover:bg-canvas transition-colors disabled:opacity-40 text-muted"
        >
          Cancelar
        </button>
        <button
          type="button"
          onClick={onGenerar}
          disabled={generating || !materiaResolved || descripcion.trim().length < 10}
          className={`px-5 py-1.5 text-sm font-medium rounded-md text-white transition-colors ${
            generating
              ? "bg-sidebar-bg-edge animate-pulse cursor-not-allowed"
              : "bg-accent-brand hover:bg-accent-brand-deep disabled:bg-border disabled:text-muted disabled:cursor-not-allowed"
          }`}
        >
          {generating ? "Generando..." : "Generar"}
        </button>
      </div>
    </div>
  )
}

interface PreviewStepProps {
  ejercicios: EjercicioGenerado[]
  result: GenerateTPResponse
  onUpdateEjercicio: (index: number, updates: Partial<EjercicioGenerado>) => void
  onRemoveEjercicio: (index: number) => void
  onEditar: () => void
  onUsar: () => void
}

function PreviewStep({
  ejercicios,
  result,
  onUpdateEjercicio,
  onRemoveEjercicio,
  onEditar,
  onUsar,
}: PreviewStepProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(0)
  const [editingField, setEditingField] = useState<{
    index: number
    field: "enunciado" | "inicial_codigo" | "rubrica" | "titulo"
  } | null>(null)

  return (
    <div className="space-y-4">
      <div className="max-h-[60vh] overflow-y-auto space-y-3 pr-1">
        {ejercicios.map((ej, i) => (
          <EjercicioCard
            key={i}
            index={i}
            ejercicio={ej}
            isExpanded={expandedIndex === i}
            editingField={editingField?.index === i ? editingField.field : null}
            onToggle={() => setExpandedIndex(expandedIndex === i ? null : i)}
            onEdit={(field) => setEditingField({ index: i, field })}
            onStopEdit={() => setEditingField(null)}
            onUpdate={(updates) => onUpdateEjercicio(i, updates)}
            onRemove={ejercicios.length > 1 ? () => onRemoveEjercicio(i) : undefined}
          />
        ))}
      </div>

      <div className="flex items-center gap-3 bg-canvas border border-border rounded-xl px-4 py-3">
        <div className="text-xs text-muted flex flex-wrap gap-x-4 gap-y-1">
          <span>
            <span className="font-medium">Modelo:</span> {result.model_used}
          </span>
          <span>
            <span className="font-medium">Tokens:</span> {result.tokens_input} /{" "}
            {result.tokens_output}
          </span>
          <span>
            <span className="font-medium">RAG:</span>{" "}
            {result.rag_chunks_used > 0 ? `${result.rag_chunks_used} fragmentos` : "sin materiales"}
          </span>
        </div>
      </div>

      <div className="flex justify-between pt-2 border-t border-border">
        <button
          type="button"
          onClick={onEditar}
          className="px-4 py-1.5 text-sm border border-border rounded-md hover:bg-canvas transition-colors text-muted"
        >
          Regenerar
        </button>
        <button
          type="button"
          onClick={onUsar}
          disabled={ejercicios.length === 0}
          className="px-5 py-1.5 text-sm font-medium bg-accent-brand hover:bg-accent-brand-deep text-white rounded-md transition-colors disabled:bg-border disabled:text-muted"
        >
          Crear {ejercicios.length} {ejercicios.length === 1 ? "TP" : "TPs"}
        </button>
      </div>
    </div>
  )
}

interface EjercicioCardProps {
  index: number
  ejercicio: EjercicioGenerado
  isExpanded: boolean
  editingField: "enunciado" | "inicial_codigo" | "rubrica" | "titulo" | null
  onToggle: () => void
  onEdit: (field: "enunciado" | "inicial_codigo" | "rubrica" | "titulo") => void
  onStopEdit: () => void
  onUpdate: (updates: Partial<EjercicioGenerado>) => void
  onRemove?: (() => void) | undefined
}

function EjercicioCard({
  index,
  ejercicio,
  isExpanded,
  editingField,
  onToggle,
  onEdit,
  onStopEdit,
  onUpdate,
  onRemove,
}: EjercicioCardProps) {
  const [rubricaRaw, setRubricaRaw] = useState("")

  const startEditRubrica = () => {
    setRubricaRaw(JSON.stringify(ejercicio.rubrica, null, 2))
    onEdit("rubrica")
  }

  const saveRubrica = () => {
    try {
      onUpdate({ rubrica: JSON.parse(rubricaRaw) })
      onStopEdit()
    } catch {
      // JSON invalido — no guardar
    }
  }

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-canvas hover:bg-surface-alt transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted bg-white border border-border rounded px-1.5 py-0.5">
            {index + 1}
          </span>
          <span className="text-sm font-medium text-ink truncate max-w-md">
            {ejercicio.titulo || `Ejercicio ${index + 1}`}
          </span>
          <span className="text-xs text-muted">{ejercicio.test_cases.length} tests</span>
        </div>
        <div className="flex items-center gap-2">
          {onRemove && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation()
                onRemove()
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation()
                  onRemove()
                }
              }}
              className="text-xs text-danger hover:text-danger px-2 py-0.5"
            >
              Quitar
            </span>
          )}
          <span className="text-muted text-xs">{isExpanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Body */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Titulo */}
          <EditableSection
            label="Titulo"
            isEditing={editingField === "titulo"}
            onStartEdit={() => onEdit("titulo")}
            onStopEdit={onStopEdit}
          >
            {editingField === "titulo" ? (
              <input
                type="text"
                value={ejercicio.titulo}
                onChange={(e) => onUpdate({ titulo: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-surface text-ink focus:border-accent-brand focus:ring-2 focus:ring-accent-brand/20 focus:outline-none"
                autoFocus
              />
            ) : (
              <p className="text-sm text-ink">{ejercicio.titulo}</p>
            )}
          </EditableSection>

          {/* Enunciado */}
          <EditableSection
            label="Enunciado"
            isEditing={editingField === "enunciado"}
            onStartEdit={() => onEdit("enunciado")}
            onStopEdit={onStopEdit}
          >
            {editingField === "enunciado" ? (
              <textarea
                value={ejercicio.enunciado}
                onChange={(e) => onUpdate({ enunciado: e.target.value })}
                rows={8}
                className="w-full px-3 py-2 text-sm font-mono border border-border rounded-lg bg-surface text-ink focus:border-accent-brand focus:ring-2 focus:ring-accent-brand/20 resize-y focus:outline-none"
                autoFocus
              />
            ) : (
              <div className="bg-canvas border border-border rounded-lg p-3 max-h-48 overflow-y-auto">
                <MarkdownRenderer content={ejercicio.enunciado} />
              </div>
            )}
          </EditableSection>

          {/* Codigo inicial */}
          <EditableSection
            label="Codigo inicial"
            isEditing={editingField === "inicial_codigo"}
            onStartEdit={() => onEdit("inicial_codigo")}
            onStopEdit={onStopEdit}
          >
            {editingField === "inicial_codigo" ? (
              <textarea
                value={ejercicio.inicial_codigo}
                onChange={(e) => onUpdate({ inicial_codigo: e.target.value })}
                rows={6}
                className="w-full px-3 py-2 text-sm font-mono border border-border rounded-lg bg-surface text-ink focus:border-accent-brand focus:ring-2 focus:ring-accent-brand/20 resize-y focus:outline-none"
                autoFocus
              />
            ) : (
              <pre className="bg-surface-alt border border-border-soft text-ink rounded-lg px-3 py-2 text-xs font-mono whitespace-pre-wrap max-h-36 overflow-y-auto leading-relaxed">
                {ejercicio.inicial_codigo || (
                  <span className="text-muted-soft italic">(vacío)</span>
                )}
              </pre>
            )}
          </EditableSection>

          {/* Rubrica */}
          <EditableSection
            label="Rubrica"
            isEditing={editingField === "rubrica"}
            onStartEdit={startEditRubrica}
            onStopEdit={saveRubrica}
          >
            {editingField === "rubrica" ? (
              <textarea
                value={rubricaRaw}
                onChange={(e) => setRubricaRaw(e.target.value)}
                rows={6}
                className="w-full px-3 py-2 text-xs font-mono border border-border rounded-lg bg-surface text-ink focus:border-accent-brand focus:ring-2 focus:ring-accent-brand/20 resize-y focus:outline-none"
                autoFocus
              />
            ) : (
              <div className="bg-canvas border border-border rounded-lg p-3 max-h-32 overflow-y-auto">
                {Array.isArray((ejercicio.rubrica as { criterios?: unknown[] })?.criterios) ? (
                  <div className="space-y-1">
                    {(
                      ejercicio.rubrica as {
                        criterios: { nombre: string; peso: number; descripcion: string }[]
                      }
                    ).criterios.map((c, ci) => (
                      <div key={ci} className="flex items-baseline gap-2 text-xs">
                        <span className="font-medium text-ink">{c.nombre}</span>
                        <span className="text-muted">({(c.peso * 100).toFixed(0)}%)</span>
                        <span className="text-muted truncate">{c.descripcion}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <pre className="text-xs font-mono whitespace-pre-wrap">
                    {JSON.stringify(ejercicio.rubrica, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </EditableSection>

          {/* Test cases (read-only preview) */}
          {ejercicio.test_cases.length > 0 && (
            <div>
              <div className="text-xs font-medium text-ink mb-1.5 uppercase tracking-wider">
                Casos de prueba ({ejercicio.test_cases.length})
              </div>
              <div className="space-y-1.5 max-h-32 overflow-y-auto">
                {ejercicio.test_cases.map((tc, ti) => (
                  <div
                    key={ti}
                    className="bg-canvas border border-border rounded-lg px-3 py-1.5 text-xs flex items-center gap-2"
                  >
                    <span className="font-medium text-ink">{tc.name ?? `Caso ${ti + 1}`}</span>
                    {tc.is_public === false && (
                      <span className="text-[10px] bg-surface-alt border border-border-soft text-muted rounded px-1.5 py-0.5">
                        privado
                      </span>
                    )}
                    {tc.expected && (
                      <span className="text-muted font-mono truncate ml-auto">= {tc.expected}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function EditableSection({
  label,
  isEditing,
  onStartEdit,
  onStopEdit,
  children,
}: {
  label: string
  isEditing: boolean
  onStartEdit: () => void
  onStopEdit: () => void
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-ink uppercase tracking-wider">{label}</span>
        <button
          type="button"
          onClick={isEditing ? onStopEdit : onStartEdit}
          className="text-xs text-muted hover:text-ink transition-colors"
        >
          {isEditing ? "Listo" : "Editar"}
        </button>
      </div>
      {children}
    </div>
  )
}
