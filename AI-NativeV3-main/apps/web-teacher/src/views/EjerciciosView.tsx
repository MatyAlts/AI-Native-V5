/**
 * Vista del banco de Ejercicios reusables (ADR-047 + ADR-048).
 *
 * Biblioteca por tenant. Un Ejercicio es una entidad de primera clase
 * con UUID propio y schema pedagogico PID-UTN. Puede referenciarse desde
 * multiples TPs via la tabla intermedia tp_ejercicios.
 *
 * Permite:
 *  - Listar ejercicios con filtros por unidad_tematica, dificultad, origen IA
 *  - Crear ejercicio manual (form con secciones)
 *  - Crear ejercicio asistido por IA (wizard standalone)
 *  - Editar ejercicio existente
 *  - Borrar (soft delete)
 *
 * Convenciones del repo:
 *  - useCallback para fetchFns que van a deps de useEffect
 *  - Texto en espanol SIN tildes (encoding cp1252 en Windows)
 *  - ModalState discriminated union (mismo patron que TareasPracticasView)
 *  - PageContainer + helpContent (key "ejercicios")
 */
import { Badge, Modal, PageContainer } from "@platform/ui"
import { Pencil, Plus, Sparkles, Trash2 } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import {
  type Dificultad,
  type Ejercicio,
  type EjercicioCreate,
  type EjercicioGenerateRequest,
  type Materia,
  type UnidadTematica,
  createEjercicio,
  deleteEjercicio,
  generateEjercicioWithAI,
  listEjercicios,
  listMaterias,
  updateEjercicio,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  getToken: () => Promise<string | null>
}

type ModalState =
  | { kind: "closed" }
  | { kind: "create"; initial?: EjercicioCreate }
  | { kind: "edit"; ejercicio: Ejercicio }
  | { kind: "view"; ejercicio: Ejercicio }
  | { kind: "ai-wizard" }
  | { kind: "confirm-delete"; ejercicio: Ejercicio }

const UNIDAD_LABEL: Record<UnidadTematica, string> = {
  secuenciales: "Secuenciales",
  condicionales: "Condicionales",
  repetitivas: "Repetitivas",
  mixtos: "Mixtos",
}

const DIFICULTAD_LABEL: Record<Dificultad, string> = {
  basica: "Basica",
  intermedia: "Intermedia",
  avanzada: "Avanzada",
}

const DIFICULTAD_VARIANT: Record<Dificultad, "default" | "success" | "warning"> = {
  basica: "success",
  intermedia: "default",
  avanzada: "warning",
}

function emptyEjercicio(unidad: UnidadTematica = "secuenciales"): EjercicioCreate {
  return {
    titulo: "",
    enunciado_md: "",
    inicial_codigo: null,
    unidad_tematica: unidad,
    dificultad: null,
    prerequisitos: { sintacticos: [], conceptuales: [] },
    test_cases: [],
    rubrica: null,
    tutor_rules: null,
    banco_preguntas: null,
    misconceptions: [],
    respuesta_pista: [],
    heuristica_cierre: null,
    anti_patrones: [],
    created_via_ai: false,
  }
}

export function EjerciciosView({ getToken }: Props) {
  const [ejercicios, setEjercicios] = useState<Ejercicio[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modal, setModal] = useState<ModalState>({ kind: "closed" })
  const [filterUnidad, setFilterUnidad] = useState<UnidadTematica | "">("")
  const [filterDificultad, setFilterDificultad] = useState<Dificultad | "">("")
  const [filterIA, setFilterIA] = useState<"" | "true" | "false">("")

  const fetchList = useCallback(() => {
    setLoading(true)
    setError(null)
    listEjercicios(
      {
        ...(filterUnidad ? { unidad_tematica: filterUnidad } : {}),
        ...(filterDificultad ? { dificultad: filterDificultad } : {}),
        ...(filterIA ? { created_via_ai: filterIA === "true" } : {}),
        limit: 100,
      },
      getToken,
    )
      .then((r) => setEjercicios(r.data))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [filterUnidad, filterDificultad, filterIA, getToken])

  useEffect(() => {
    fetchList()
  }, [fetchList])

  function closeModal() {
    setModal({ kind: "closed" })
  }

  async function handleCreate(body: EjercicioCreate): Promise<void> {
    try {
      await createEjercicio(body, getToken)
      closeModal()
      fetchList()
    } catch (e) {
      alert(`Error al crear ejercicio: ${String(e)}`)
    }
  }

  async function handleUpdate(id: string, body: EjercicioCreate): Promise<void> {
    try {
      await updateEjercicio(id, body, getToken)
      closeModal()
      fetchList()
    } catch (e) {
      alert(`Error al actualizar ejercicio: ${String(e)}`)
    }
  }

  async function handleDelete(ejercicio: Ejercicio): Promise<void> {
    try {
      await deleteEjercicio(ejercicio.id, getToken)
      closeModal()
      fetchList()
    } catch (e) {
      alert(`Error al borrar: ${String(e)}`)
    }
  }

  return (
    <PageContainer
      title="Banco de Ejercicios"
      description="Ejercicios reusables del tenant. Cada uno tiene su contexto pedagogico (banco socratico, misconceptions, anti-patrones)."

      helpContent={helpContent.ejercicios}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={filterUnidad}
            onChange={(e) => setFilterUnidad(e.target.value as UnidadTematica | "")}
            className="border border-border rounded px-2 py-1 text-sm bg-white"
          >
            <option value="">Todas las unidades</option>
            <option value="secuenciales">Secuenciales</option>
            <option value="condicionales">Condicionales</option>
            <option value="repetitivas">Repetitivas</option>
            <option value="mixtos">Mixtos</option>
          </select>
          <select
            value={filterDificultad}
            onChange={(e) => setFilterDificultad(e.target.value as Dificultad | "")}
            className="border border-border rounded px-2 py-1 text-sm bg-white"
          >
            <option value="">Todas las dificultades</option>
            <option value="basica">Basica</option>
            <option value="intermedia">Intermedia</option>
            <option value="avanzada">Avanzada</option>
          </select>
          <select
            value={filterIA}
            onChange={(e) => setFilterIA(e.target.value as "" | "true" | "false")}
            className="border border-border rounded px-2 py-1 text-sm bg-white"
          >
            <option value="">Todos los origenes</option>
            <option value="true">Generados con IA</option>
            <option value="false">Creados manualmente</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setModal({ kind: "ai-wizard" })}
            className="flex items-center gap-1.5 bg-accent-brand text-white rounded px-3 py-1.5 text-sm hover:opacity-90"
          >
            <Sparkles className="w-4 h-4" />
            Crear con IA
          </button>
          <button
            type="button"
            onClick={() => setModal({ kind: "create" })}
            className="flex items-center gap-1.5 border border-border rounded px-3 py-1.5 text-sm hover:bg-canvas"
          >
            <Plus className="w-4 h-4" />
            Crear manual
          </button>
        </div>
      </div>

      {loading && <div className="text-sm text-muted">Cargando ejercicios...</div>}
      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-3 mb-3">
          {error}
        </div>
      )}

      {!loading && ejercicios.length === 0 && !error && (
        <div className="text-sm text-muted bg-canvas border border-border rounded p-6 text-center">
          No hay ejercicios todavia. Crea uno manualmente o usa el wizard de IA.
        </div>
      )}

      {!loading && ejercicios.length > 0 && (
        <div className="border border-border rounded overflow-hidden bg-white">
          <table className="w-full text-sm">
            <thead className="bg-canvas border-b border-border">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Titulo</th>
                <th className="text-left px-3 py-2 font-medium">Unidad</th>
                <th className="text-left px-3 py-2 font-medium">Dificultad</th>
                <th className="text-left px-3 py-2 font-medium">Origen</th>
                <th className="text-left px-3 py-2 font-medium">Creado</th>
                <th className="text-right px-3 py-2 font-medium">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {ejercicios.map((ej) => (
                <tr key={ej.id} className="border-b border-border last:border-0 hover:bg-canvas">
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => setModal({ kind: "view", ejercicio: ej })}
                      className="text-left hover:text-accent-brand"
                    >
                      {ej.titulo}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-muted">{UNIDAD_LABEL[ej.unidad_tematica]}</td>
                  <td className="px-3 py-2">
                    {ej.dificultad ? (
                      <Badge variant={DIFICULTAD_VARIANT[ej.dificultad]}>
                        {DIFICULTAD_LABEL[ej.dificultad]}
                      </Badge>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {ej.created_via_ai ? (
                      <span className="inline-flex items-center gap-1 text-accent-brand text-xs">
                        <Sparkles className="w-3 h-3" />
                        IA
                      </span>
                    ) : (
                      <span className="text-muted text-xs">Manual</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-muted text-xs">
                    {new Date(ej.created_at).toLocaleDateString("es-AR")}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setModal({ kind: "edit", ejercicio: ej })}
                        className="p-1 hover:bg-border rounded"
                        title="Editar"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setModal({ kind: "confirm-delete", ejercicio: ej })}
                        className="p-1 hover:bg-red-50 hover:text-red-600 rounded"
                        title="Eliminar"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(modal.kind === "create" || modal.kind === "edit") && (
        <EjercicioFormModal
          initial={modal.kind === "edit" ? toCreate(modal.ejercicio) : modal.initial}
          title={modal.kind === "create" ? "Crear ejercicio" : "Editar ejercicio"}
          onClose={closeModal}
          onSubmit={(body) =>
            modal.kind === "edit"
              ? handleUpdate(modal.ejercicio.id, body)
              : handleCreate(body)
          }
        />
      )}

      {modal.kind === "view" && (
        <EjercicioViewModal ejercicio={modal.ejercicio} onClose={closeModal} />
      )}

      {modal.kind === "ai-wizard" && (
        <EjercicioAIWizard
          getToken={getToken}
          onClose={closeModal}
          onGenerated={(borrador) => setModal({ kind: "create", initial: borrador })}
        />
      )}

      {modal.kind === "confirm-delete" && (
        <Modal
          isOpen={true}
          onClose={closeModal}
          title="Eliminar ejercicio"
         
          size="sm"
        >
          <p className="text-sm">
            Vas a eliminar el ejercicio <strong>{modal.ejercicio.titulo}</strong>. Los TPs
            que lo referencian seguiran apuntando a esta version (soft delete).
          </p>
          <div className="flex justify-end gap-2 mt-4">
            <button
              type="button"
              onClick={closeModal}
              className="px-3 py-1.5 border border-border rounded text-sm hover:bg-canvas"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => handleDelete(modal.ejercicio)}
              className="px-3 py-1.5 bg-red-600 text-white rounded text-sm hover:opacity-90"
            >
              Eliminar
            </button>
          </div>
        </Modal>
      )}
    </PageContainer>
  )
}

function toCreate(ej: Ejercicio): EjercicioCreate {
  return {
    titulo: ej.titulo,
    enunciado_md: ej.enunciado_md,
    inicial_codigo: ej.inicial_codigo,
    unidad_tematica: ej.unidad_tematica,
    dificultad: ej.dificultad,
    prerequisitos: ej.prerequisitos,
    test_cases: ej.test_cases,
    rubrica: ej.rubrica,
    tutor_rules: ej.tutor_rules,
    banco_preguntas: ej.banco_preguntas,
    misconceptions: ej.misconceptions,
    respuesta_pista: ej.respuesta_pista,
    heuristica_cierre: ej.heuristica_cierre,
    anti_patrones: ej.anti_patrones,
    created_via_ai: ej.created_via_ai,
  }
}

// ── Form modal ──────────────────────────────────────────────────────────

interface FormModalProps {
  initial?: EjercicioCreate
  title: string
  onClose: () => void
  onSubmit: (body: EjercicioCreate) => Promise<void>
}

function EjercicioFormModal({ initial, title, onClose, onSubmit }: FormModalProps) {
  const [draft, setDraft] = useState<EjercicioCreate>(initial ?? emptyEjercicio())
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof EjercicioCreate>(key: K, value: EjercicioCreate[K]) {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  async function handleSubmit() {
    setError(null)
    if (!draft.titulo.trim() || !draft.enunciado_md.trim()) {
      setError("Titulo y enunciado son obligatorios")
      return
    }
    setSubmitting(true)
    try {
      await onSubmit(draft)
    } catch (e) {
      setError(String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal isOpen={true} onClose={onClose} title={title} size="lg">
      <div className="space-y-4">
        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2">
            {error}
          </div>
        )}

        <FormSection title="Datos basicos">
          <label className="block text-xs text-muted mb-1">Titulo</label>
          <input
            type="text"
            value={draft.titulo}
            onChange={(e) => set("titulo", e.target.value)}
            className="w-full border border-border rounded px-2 py-1 text-sm mb-2"
            maxLength={200}
          />
          <label className="block text-xs text-muted mb-1">Enunciado (markdown)</label>
          <textarea
            value={draft.enunciado_md}
            onChange={(e) => set("enunciado_md", e.target.value)}
            className="w-full border border-border rounded px-2 py-1 text-sm font-mono mb-2"
            rows={6}
          />
          <label className="block text-xs text-muted mb-1">
            Codigo inicial (opcional)
          </label>
          <textarea
            value={draft.inicial_codigo ?? ""}
            onChange={(e) => set("inicial_codigo", e.target.value || null)}
            className="w-full border border-border rounded px-2 py-1 text-sm font-mono mb-2"
            rows={4}
            placeholder="# Scaffold opcional"
          />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-muted mb-1">Unidad tematica</label>
              <select
                value={draft.unidad_tematica}
                onChange={(e) => set("unidad_tematica", e.target.value as UnidadTematica)}
                className="w-full border border-border rounded px-2 py-1 text-sm bg-white"
              >
                <option value="secuenciales">Secuenciales</option>
                <option value="condicionales">Condicionales</option>
                <option value="repetitivas">Repetitivas</option>
                <option value="mixtos">Mixtos</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">Dificultad</label>
              <select
                value={draft.dificultad ?? ""}
                onChange={(e) =>
                  set("dificultad", (e.target.value || null) as Dificultad | null)
                }
                className="w-full border border-border rounded px-2 py-1 text-sm bg-white"
              >
                <option value="">Sin especificar</option>
                <option value="basica">Basica</option>
                <option value="intermedia">Intermedia</option>
                <option value="avanzada">Avanzada</option>
              </select>
            </div>
          </div>
        </FormSection>

        <FormSection title="Tests, rubrica y prerequisitos (JSON)">
          <JsonField
            label="test_cases (array)"
            value={draft.test_cases ?? []}
            onChange={(v) => set("test_cases", v)}
          />
          <JsonField
            label="rubrica ({criterios: [...]})"
            value={draft.rubrica ?? null}
            onChange={(v) => set("rubrica", v)}
            allowNull
          />
          <JsonField
            label="prerequisitos ({sintacticos: [], conceptuales: []})"
            value={draft.prerequisitos ?? { sintacticos: [], conceptuales: [] }}
            onChange={(v) => set("prerequisitos", v)}
          />
        </FormSection>

        <FormSection title="Pedagogia PID-UTN (JSON)">
          <JsonField
            label="tutor_rules"
            value={draft.tutor_rules ?? null}
            onChange={(v) => set("tutor_rules", v)}
            allowNull
          />
          <JsonField
            label="banco_preguntas (N1-N4)"
            value={draft.banco_preguntas ?? null}
            onChange={(v) => set("banco_preguntas", v)}
            allowNull
          />
          <JsonField
            label="misconceptions (array)"
            value={draft.misconceptions ?? []}
            onChange={(v) => set("misconceptions", v)}
          />
          <JsonField
            label="respuesta_pista (array por nivel)"
            value={draft.respuesta_pista ?? []}
            onChange={(v) => set("respuesta_pista", v)}
          />
          <JsonField
            label="heuristica_cierre"
            value={draft.heuristica_cierre ?? null}
            onChange={(v) => set("heuristica_cierre", v)}
            allowNull
          />
          <JsonField
            label="anti_patrones (array)"
            value={draft.anti_patrones ?? []}
            onChange={(v) => set("anti_patrones", v)}
          />
        </FormSection>

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 border border-border rounded text-sm hover:bg-canvas"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="px-3 py-1.5 bg-accent-brand text-white rounded text-sm hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Guardando..." : "Guardar"}
          </button>
        </div>
      </div>
    </Modal>
  )
}

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="border border-border rounded" open>
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium bg-canvas border-b border-border">
        {title}
      </summary>
      <div className="p-3 space-y-2">{children}</div>
    </details>
  )
}

interface JsonFieldProps {
  label: string
  value: unknown
  onChange: (v: never) => void
  allowNull?: boolean
}

function JsonField({ label, value, onChange, allowNull = false }: JsonFieldProps) {
  const [text, setText] = useState<string>(() => JSON.stringify(value, null, 2))
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setText(JSON.stringify(value, null, 2))
  }, [value])

  function commit(next: string) {
    setText(next)
    if (allowNull && next.trim() === "null") {
      setErr(null)
      onChange(null as never)
      return
    }
    try {
      const parsed = JSON.parse(next)
      setErr(null)
      onChange(parsed as never)
    } catch (e) {
      setErr(String(e))
    }
  }

  return (
    <div>
      <label className="block text-xs text-muted mb-1">{label}</label>
      <textarea
        value={text}
        onChange={(e) => commit(e.target.value)}
        className={`w-full border rounded px-2 py-1 text-xs font-mono ${
          err ? "border-red-400" : "border-border"
        }`}
        rows={4}
      />
      {err && <div className="text-xs text-red-600 mt-1">{err}</div>}
    </div>
  )
}

// ── View modal (read-only) ─────────────────────────────────────────────

function EjercicioViewModal({
  ejercicio,
  onClose,
}: {
  ejercicio: Ejercicio
  onClose: () => void
}) {
  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={ejercicio.titulo}
     
      size="lg"
    >
      <div className="space-y-3 text-sm">
        <div className="flex gap-2">
          <Badge>{UNIDAD_LABEL[ejercicio.unidad_tematica]}</Badge>
          {ejercicio.dificultad && (
            <Badge variant={DIFICULTAD_VARIANT[ejercicio.dificultad]}>
              {DIFICULTAD_LABEL[ejercicio.dificultad]}
            </Badge>
          )}
          {ejercicio.created_via_ai && (
            <Badge variant="default">
              <Sparkles className="w-3 h-3 inline mr-1" />
              IA
            </Badge>
          )}
        </div>
        <div>
          <div className="text-xs text-muted mb-1">Enunciado</div>
          <pre className="bg-canvas border border-border rounded p-2 text-xs whitespace-pre-wrap font-mono">
            {ejercicio.enunciado_md}
          </pre>
        </div>
        {ejercicio.inicial_codigo && (
          <div>
            <div className="text-xs text-muted mb-1">Codigo inicial</div>
            <pre className="bg-canvas border border-border rounded p-2 text-xs font-mono">
              {ejercicio.inicial_codigo}
            </pre>
          </div>
        )}
        <ReadOnlyJson label="test_cases" value={ejercicio.test_cases} />
        <ReadOnlyJson label="rubrica" value={ejercicio.rubrica} />
        <ReadOnlyJson label="tutor_rules" value={ejercicio.tutor_rules} />
        <ReadOnlyJson label="banco_preguntas" value={ejercicio.banco_preguntas} />
        <ReadOnlyJson label="misconceptions" value={ejercicio.misconceptions} />
        <ReadOnlyJson label="respuesta_pista" value={ejercicio.respuesta_pista} />
        <ReadOnlyJson label="heuristica_cierre" value={ejercicio.heuristica_cierre} />
        <ReadOnlyJson label="anti_patrones" value={ejercicio.anti_patrones} />
      </div>
      <div className="flex justify-end mt-4 pt-3 border-t border-border">
        <button
          type="button"
          onClick={onClose}
          className="px-3 py-1.5 border border-border rounded text-sm hover:bg-canvas"
        >
          Cerrar
        </button>
      </div>
    </Modal>
  )
}

function ReadOnlyJson({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null
  if (Array.isArray(value) && value.length === 0) return null
  return (
    <details className="border border-border rounded">
      <summary className="cursor-pointer px-2 py-1 text-xs font-medium bg-canvas">
        {label}
      </summary>
      <pre className="p-2 text-xs font-mono overflow-x-auto">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  )
}

// ── AI Wizard modal ────────────────────────────────────────────────────

interface AIWizardProps {
  getToken: () => Promise<string | null>
  onClose: () => void
  onGenerated: (borrador: EjercicioCreate) => void
}

function EjercicioAIWizard({ getToken, onClose, onGenerated }: AIWizardProps) {
  const [materias, setMaterias] = useState<Materia[]>([])
  const [materiaId, setMateriaId] = useState<string>("")
  const [descripcionNl, setDescripcionNl] = useState("")
  const [unidad, setUnidad] = useState<UnidadTematica>("secuenciales")
  const [dificultad, setDificultad] = useState<Dificultad | "">("")
  const [contexto, setContexto] = useState("")
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listMaterias("", getToken)
      .then(setMaterias)
      .catch(() => setMaterias([]))
  }, [getToken])

  async function handleGenerate() {
    setError(null)
    if (descripcionNl.trim().length < 10) {
      setError("La descripcion debe tener al menos 10 caracteres")
      return
    }
    setGenerating(true)
    // materia_id es opcional: si esta vacio, el backend resuelve la primera
    // del tenant (modo demo / piloto). Ver ADR-047.
    const req: EjercicioGenerateRequest = {
      ...(materiaId ? { materia_id: materiaId } : {}),
      descripcion_nl: descripcionNl,
      unidad_tematica: unidad,
      ...(dificultad ? { dificultad } : {}),
      ...(contexto ? { contexto } : {}),
    }
    try {
      const resp = await generateEjercicioWithAI(req, getToken)
      onGenerated(resp.borrador)
    } catch (e) {
      setError(String(e))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Modal isOpen={true} onClose={onClose} title="Generar ejercicio con IA" size="md">
      <div className="space-y-3 text-sm">
        {error && (
          <div className="text-red-600 bg-red-50 border border-red-200 rounded p-2">{error}</div>
        )}
        <div>
          <label className="block text-xs text-muted mb-1">Materia (para BYOK + RAG)</label>
          <select
            value={materiaId}
            onChange={(e) => setMateriaId(e.target.value)}
            className="w-full border border-border rounded px-2 py-1 text-sm bg-white"
          >
            <option value="">Sin especificar (usa la primera del tenant)</option>
            {materias.map((m) => (
              <option key={m.id} value={m.id}>
                {m.nombre}
              </option>
            ))}
          </select>
          {materias.length === 0 && (
            <p className="text-xs text-muted mt-1">
              No hay materias cargadas en este tenant. Dejala sin especificar y el backend
              elige la primera disponible.
            </p>
          )}
        </div>
        <div>
          <label className="block text-xs text-muted mb-1">
            Descripcion del ejercicio (en lenguaje natural)
          </label>
          <textarea
            value={descripcionNl}
            onChange={(e) => setDescripcionNl(e.target.value)}
            rows={4}
            className="w-full border border-border rounded px-2 py-1 text-sm"
            placeholder="Ej: Quiero un ejercicio donde el alumno calcule el area de un circulo usando casting a float y la constante pi."
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-xs text-muted mb-1">Unidad tematica</label>
            <select
              value={unidad}
              onChange={(e) => setUnidad(e.target.value as UnidadTematica)}
              className="w-full border border-border rounded px-2 py-1 text-sm bg-white"
            >
              <option value="secuenciales">Secuenciales</option>
              <option value="condicionales">Condicionales</option>
              <option value="repetitivas">Repetitivas</option>
              <option value="mixtos">Mixtos</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-muted mb-1">Dificultad (opcional)</label>
            <select
              value={dificultad}
              onChange={(e) => setDificultad(e.target.value as Dificultad | "")}
              className="w-full border border-border rounded px-2 py-1 text-sm bg-white"
            >
              <option value="">Sin especificar</option>
              <option value="basica">Basica</option>
              <option value="intermedia">Intermedia</option>
              <option value="avanzada">Avanzada</option>
            </select>
          </div>
        </div>
        <div>
          <label className="block text-xs text-muted mb-1">
            Contexto adicional (opcional)
          </label>
          <textarea
            value={contexto}
            onChange={(e) => setContexto(e.target.value)}
            rows={2}
            className="w-full border border-border rounded px-2 py-1 text-sm"
            placeholder="Ej: Es para el TP1 de Programacion I, primer ano TUPAD."
          />
        </div>
        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 border border-border rounded text-sm hover:bg-canvas"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent-brand text-white rounded text-sm hover:opacity-90 disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            {generating ? "Generando..." : "Generar borrador"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
