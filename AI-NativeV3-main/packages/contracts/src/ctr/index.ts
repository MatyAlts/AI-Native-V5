/**
 * Schemas de eventos del CTR — lado TypeScript.
 *
 * Los contratos deben mantenerse alineados con los de Python.
 * Cambios coordinados entre ambas fuentes.
 *
 * Convención de naming (F1, alineada con runtime):
 * - Las constantes/types Zod conservan PascalCase (idioma TS).
 * - El campo `event_type` viaja en snake_case porque es lo que ya emite
 *   el tutor-service. Cambiar el string en runtime obliga a migrar
 *   seeds, tests, dashboards y CTRs persistidos.
 */
import { z } from "zod"

const Sha256 = z.string().regex(/^[a-f0-9]{64}$/)
const Uuid = z.string().uuid()

export const PromptKind = z.enum([
  "solicitud_directa",
  "comparativa",
  "epistemologica",
  "validacion",
  "aclaracion_enunciado",
])
export type PromptKind = z.infer<typeof PromptKind>

// Base de todo evento del CTR
const CTRBase = z.object({
  event_uuid: Uuid,
  episode_id: Uuid,
  tenant_id: Uuid,
  seq: z.number().int().nonnegative(),
  ts: z.string().datetime(),
  prompt_system_hash: Sha256,
  prompt_system_version: z.string(),
  classifier_config_hash: Sha256,
})

export const EpisodioAbierto = CTRBase.extend({
  event_type: z.literal("episodio_abierto"),
  payload: z.object({
    student_pseudonym: Uuid,
    problema_id: Uuid,
    comision_id: Uuid,
    curso_config_hash: Sha256,
  }),
})
export type EpisodioAbierto = z.infer<typeof EpisodioAbierto>

export const EpisodioCerrado = CTRBase.extend({
  event_type: z.literal("episodio_cerrado"),
  payload: z.object({
    final_chain_hash: Sha256,
    total_events: z.number().int().positive(),
    duration_seconds: z.number().nonnegative(),
  }),
})
export type EpisodioCerrado = z.infer<typeof EpisodioCerrado>

// Declarado en el contract Pydantic desde la primera iteración de fixes
// pero ningún servicio lo emite todavía en runtime — la decisión de
// dispararlo al expirar el SessionState del tutor (TTL 6h) es scope de G10.
export const EpisodioAbandonado = CTRBase.extend({
  event_type: z.literal("episodio_abandonado"),
  payload: z.object({
    reason: z.string(), // "timeout" | "beforeunload" | "explicit" en runtime
    last_activity_seconds_ago: z.number().nonnegative(),
  }),
})
export type EpisodioAbandonado = z.infer<typeof EpisodioAbandonado>

export const PromptEnviado = CTRBase.extend({
  event_type: z.literal("prompt_enviado"),
  payload: z.object({
    content: z.string(),
    prompt_kind: PromptKind,
    chunks_used_hash: Sha256.nullable(),
  }),
})
export type PromptEnviado = z.infer<typeof PromptEnviado>

// F2 + F8: renombrado RespuestaRecibida -> TutorRespondio.
// `socratic_compliance`/`violations` son opcionales hasta que se
// implemente el postprocesamiento real.
export const TutorRespondio = CTRBase.extend({
  event_type: z.literal("tutor_respondio"),
  payload: z.object({
    content: z.string(),
    model_used: z.string(),
    chunks_used_hash: Sha256.nullable().optional(),
    socratic_compliance: z.number().min(0).max(1).nullable().optional(),
    violations: z.array(z.string()).default([]),
  }),
})
export type TutorRespondio = z.infer<typeof TutorRespondio>

// ADR-019 (G3 Fase A): el tutor emite este side-channel POR CADA match del
// corpus regex de guardrails, ANTES de pegarle al LLM. NO bloquea el flow.
// `guardrails_corpus_hash` permite reproducibilidad bit-a-bit cuando el
// corpus de patrones evolucione.
export const IntentoAdversoCategory = z.enum([
  "jailbreak_indirect",
  "jailbreak_substitution",
  "jailbreak_fiction",
  "persuasion_urgency",
  "prompt_injection",
])
export type IntentoAdversoCategory = z.infer<typeof IntentoAdversoCategory>

export const IntentoAdversoDetectado = CTRBase.extend({
  event_type: z.literal("intento_adverso_detectado"),
  payload: z.object({
    pattern_id: z.string(),
    category: IntentoAdversoCategory,
    severity: z.number().int().min(1).max(5),
    matched_text: z.string(),
    guardrails_corpus_hash: Sha256,
  }),
})
export type IntentoAdversoDetectado = z.infer<typeof IntentoAdversoDetectado>

// F6: campo `origin` opcional para distinguir tipeo / copia / paste.
//
// Estado de cobertura v1.0.0 (F22):
//   - `student_typed`     → emitido por web-student (tipeo normal en el editor).
//   - `pasted_external`   → emitido por web-student (paste detectado).
//   - `copied_from_tutor` → DECLARADO en el contract pero NO emitido todavía:
//       requiere una afordancia de UI ("Insertar código del tutor") que no está
//       en `apps/web-student/src/components/CodeEditor.tsx`. Tracked como G11.
//
// El event_labeler (ADR-020) reconoce los tres valores y aplica override a N4
// para los dos no-typed.
export const EdicionCodigoOrigin = z.enum(["student_typed", "copied_from_tutor", "pasted_external"])
export type EdicionCodigoOrigin = z.infer<typeof EdicionCodigoOrigin>

export const EdicionCodigo = CTRBase.extend({
  event_type: z.literal("edicion_codigo"),
  payload: z.object({
    snapshot: z.string(),
    diff_chars: z.number().int().nonnegative(),
    language: z.string(),
    origin: EdicionCodigoOrigin.nullable().optional(),
  }),
})
export type EdicionCodigo = z.infer<typeof EdicionCodigo>

// F4: renombrado TestsEjecutados -> CodigoEjecutado, payload flexible.
export const CodigoEjecutado = CTRBase.extend({
  event_type: z.literal("codigo_ejecutado"),
  payload: z.object({
    code: z.string(),
    stdout: z.string().nullable().optional(),
    stderr: z.string().nullable().optional(),
    duration_ms: z.number().int().nonnegative(),
    runtime: z.string(),
    passed: z.number().int().nonnegative().nullable().optional(),
    failed: z.number().int().nonnegative().nullable().optional(),
    total: z.number().int().nonnegative().nullable().optional(),
    failed_test_names: z.array(z.string()).default([]),
  }),
})
export type CodigoEjecutado = z.infer<typeof CodigoEjecutado>

export const LecturaEnunciado = CTRBase.extend({
  event_type: z.literal("lectura_enunciado"),
  payload: z.object({
    duration_seconds: z.number().nonnegative(),
  }),
})
export type LecturaEnunciado = z.infer<typeof LecturaEnunciado>

// F3: renombrado NotaPersonal -> AnotacionCreada (alinea con runtime).
export const AnotacionCreada = CTRBase.extend({
  event_type: z.literal("anotacion_creada"),
  payload: z.object({
    content: z.string(),
    words: z.number().int().nonnegative(),
  }),
})
export type AnotacionCreada = z.infer<typeof AnotacionCreada>

// Union de todos los eventos CTR
export const CTREvent = z.discriminatedUnion("event_type", [
  EpisodioAbierto,
  EpisodioCerrado,
  EpisodioAbandonado,
  PromptEnviado,
  TutorRespondio,
  IntentoAdversoDetectado,
  EdicionCodigo,
  CodigoEjecutado,
  LecturaEnunciado,
  AnotacionCreada,
])
export type CTREvent = z.infer<typeof CTREvent>
