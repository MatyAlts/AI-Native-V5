// Mapping de event_type del CTR a metadata visual para el timeline docente.
// El n_level "base" acá NO contempla overrides condicionales (anotacion_creada
// v1.1.0 ventana posicional, edicion_codigo con origin=copied_from_tutor,
// tests_ejecutados v1.2.0 con delta tutor). Los overrides se derivan en
// `apps/classifier-service/.../event_labeler.py` y se reflejan correctamente
// en `/api/v1/analytics/episode/{id}/n-level-distribution`. Acá mostramos el
// nivel base como referencia rápida.

import type { NLevel } from "../lib/api"

export type EventCategory = "meta" | "lectura" | "anotacion" | "codigo" | "tutor" | "integridad"

export interface EventMeta {
  icon: string
  label: string
  category: EventCategory
  nLevelBase: NLevel
  /** Resumen 1-línea derivado del payload. Receive `payload` no tipado porque varía por event_type. */
  summary: (payload: Record<string, unknown>) => string
}

const fmtPreview = (s: unknown, max = 80): string => {
  if (typeof s !== "string") return ""
  const trimmed = s.trim().replace(/\s+/g, " ")
  return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed
}

export const EVENT_META: Record<string, EventMeta> = {
  episodio_abierto: {
    icon: "🚪",
    label: "Episodio abierto",
    category: "meta",
    nLevelBase: "meta",
    summary: (p) => `model=${p.model ?? "?"}`,
  },
  episodio_cerrado: {
    icon: "✅",
    label: "Episodio cerrado",
    category: "meta",
    nLevelBase: "meta",
    summary: (p) => `reason=${p.reason ?? "?"}`,
  },
  episodio_abandonado: {
    icon: "🚫",
    label: "Episodio abandonado",
    category: "meta",
    nLevelBase: "meta",
    summary: (p) => `reason=${p.reason ?? "?"}`,
  },
  lectura_enunciado: {
    icon: "📖",
    label: "Lectura de enunciado",
    category: "lectura",
    nLevelBase: "N1",
    summary: (p) => `${Number(p.duration_seconds ?? 0).toFixed(1)}s leyendo`,
  },
  anotacion_creada: {
    icon: "📝",
    label: "Anotación",
    category: "anotacion",
    nLevelBase: "N2",
    summary: (p) => fmtPreview(p.content),
  },
  edicion_codigo: {
    icon: "⌨️",
    label: "Edición de código",
    category: "codigo",
    nLevelBase: "N2",
    summary: (p) => {
      const origin = p.origin === "copied_from_tutor" ? "[copiado del tutor] " : ""
      const snap = fmtPreview(p.snapshot, 70)
      return `${origin}${snap}`
    },
  },
  codigo_ejecutado: {
    icon: "▶️",
    label: "Código ejecutado",
    category: "codigo",
    nLevelBase: "N3",
    summary: (p) => {
      const ok = p.success === true ? "OK" : "ERROR"
      return `[${ok}] ${fmtPreview(p.output ?? p.error, 60)}`
    },
  },
  tests_ejecutados: {
    icon: "🧪",
    label: "Tests ejecutados",
    category: "codigo",
    nLevelBase: "N3",
    summary: (p) => {
      const passed = Number(p.test_count_passed ?? 0)
      const failed = Number(p.test_count_failed ?? 0)
      return `${passed} pasados · ${failed} fallidos`
    },
  },
  prompt_enviado: {
    icon: "💬",
    label: "Prompt al tutor",
    category: "tutor",
    nLevelBase: "N4",
    summary: (p) => fmtPreview(p.content),
  },
  tutor_respondio: {
    icon: "🤖",
    label: "Respuesta del tutor",
    category: "tutor",
    nLevelBase: "N4",
    summary: (p) => fmtPreview(p.content),
  },
  intento_adverso_detectado: {
    icon: "⚠️",
    label: "Intento adverso",
    category: "integridad",
    nLevelBase: "N4",
    summary: (p) => `categoria=${p.category ?? "?"} · severidad=${p.severity ?? "?"}`,
  },
  pestana_perdida: {
    icon: "🪟",
    label: "Pestaña perdida",
    category: "integridad",
    nLevelBase: "meta",
    summary: (p) => `trigger=${p.trigger ?? "?"}`,
  },
  pestana_recuperada: {
    icon: "🔙",
    label: "Pestaña recuperada",
    category: "integridad",
    nLevelBase: "meta",
    summary: (p) => `fuera ${Number(p.tiempo_fuera_segundos ?? 0).toFixed(1)}s`,
  },
  copia_intentada: {
    icon: "📋",
    label: "Intento de copia",
    category: "integridad",
    nLevelBase: "meta",
    summary: (p) => `metodo=${p.metodo ?? "?"}`,
  },
  pega_intentada: {
    icon: "📥",
    label: "Intento de pega",
    category: "integridad",
    nLevelBase: "meta",
    summary: (p) => {
      const preview = fmtPreview(p.contenido_preview, 50)
      return `metodo=${p.metodo ?? "?"}${preview ? ` · "${preview}"` : ""}`
    },
  },
  reflexion_completada: {
    icon: "💭",
    label: "Reflexión metacognitiva",
    category: "anotacion",
    nLevelBase: "meta",
    summary: (p) => fmtPreview(p.content, 100),
  },
}

const FALLBACK_META: EventMeta = {
  icon: "❓",
  label: "Evento desconocido",
  category: "meta",
  nLevelBase: "meta",
  summary: () => "(sin metadata declarada)",
}

export function getEventMeta(eventType: string): EventMeta {
  return EVENT_META[eventType] ?? FALLBACK_META
}

export const CATEGORY_LABEL: Record<EventCategory, string> = {
  meta: "Meta",
  lectura: "Lectura",
  anotacion: "Anotaciones",
  codigo: "Código",
  tutor: "Tutor",
  integridad: "Integridad",
}

export const ALL_CATEGORIES: EventCategory[] = [
  "meta",
  "lectura",
  "anotacion",
  "codigo",
  "tutor",
  "integridad",
]

export function relativeTs(ts: string, openedAtMs: number): string {
  const eventMs = Date.parse(ts)
  if (Number.isNaN(eventMs)) return "?"
  const delta = Math.max(0, Math.floor((eventMs - openedAtMs) / 1000))
  if (delta < 60) return `+0:${delta.toString().padStart(2, "0")}`
  const m = Math.floor(delta / 60)
  const s = delta - m * 60
  return `+${m}:${s.toString().padStart(2, "0")}`
}
