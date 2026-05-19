// Labels para vista pedagógica del docente (no-técnica).
// Marcador anti-reificación implícito: las frases describen el comportamiento
// observado en el episodio, no atribuyen una identidad permanente al estudiante.
// Las categorías describen episodios, no estudiantes — paper Cortez & Garis §4.4
// principio "no-etiquetado individual" del protocolo interpretativo (paper §7.3).
export const APPROPRIATION_DOCENTE: Record<string, string> = {
  delegacion_pasiva: "En este episodio: dependio de la IA",
  apropiacion_superficial: "En este episodio: uso superficial de la IA",
  apropiacion_reflexiva: "En este episodio: trabajo de forma autonoma",
}

// Labels para vista investigador (técnica, comité doctoral).
// IMPORTANTE: la categoría describe el perfil tipológico de apropiación
// observado en UN episodio. NO es un atributo del estudiante. Marcador
// anti-reificación explícito alineado con paper Cortez & Garis §4.4
// ("perfil tipológico de apropiación X") y principio "no-etiquetado individual"
// del protocolo interpretativo §7.3.
export const APPROPRIATION_INVESTIGADOR: Record<string, string> = {
  delegacion_pasiva: "Perfil tipologico: delegacion pasiva",
  apropiacion_superficial: "Perfil tipologico: apropiacion superficial",
  apropiacion_reflexiva: "Perfil tipologico: apropiacion reflexiva",
}

/**
 * Helper canónico para renderizar la categoría de apropiación con disclaimer
 * de scope episódico. Usar SIEMPRE este helper en vistas que muestren
 * apropiación agregada por estudiante (cohorte, longitudinal) para evitar
 * reificación individual.
 *
 * Ej.: "Perfil tipologico: apropiacion reflexiva (este episodio)"
 *
 * Ver paper Cortez & Garis §4.4 + protocolo interpretativo §7.3 principio 4
 * "no-etiquetado individual: las categorías describen episodios, no estudiantes".
 */
export function appropriationWithScope(
  category: string,
  audience: "docente" | "investigador" = "docente",
): string {
  const dict = audience === "investigador" ? APPROPRIATION_INVESTIGADOR : APPROPRIATION_DOCENTE
  const base = dict[category] ?? category
  // En vista investigador el label ya empieza con "Perfil tipologico:";
  // en vista docente ya empieza con "En este episodio:"; el sufijo refuerza
  // el scope cuando el componente lo necesita explícito.
  return `${base} (este episodio)`
}

/**
 * Disclaimer textual canónico para vistas cohortales o longitudinales que
 * agregan categorías de apropiación por estudiante. Insertar como nota al
 * pie / tooltip / leyenda de tabla. Citable contra paper §4.4 + §7.3.
 */
export const APPROPRIATION_REIFICATION_DISCLAIMER =
  "Las categorias describen perfiles tipologicos de apropiacion observados en cada episodio; " +
  "NO son atributos del estudiante. No usar para diagnostico individual sin triangulacion " +
  "con juicio docente y auto-reconstruccion del estudiante (paper Cortez & Garis §4.4 + §7.3 + ADR-053)."

export const PROGRESSION_DOCENTE: Record<string, string> = {
  mejorando: "Mejorando",
  estable: "Estable",
  empeorando: "En riesgo",
  insuficiente: "Sin datos suficientes",
}

export const NLEVEL_DOCENTE: Record<string, string> = {
  N1: "Leyendo el problema",
  N2: "Tomando notas y planificando",
  N3: "Escribiendo y probando codigo",
  N4: "Usando el tutor IA",
  meta: "Abriendo/cerrando la sesion",
}

export const NLEVEL_INVESTIGADOR: Record<string, string> = {
  N1: "N1 - Comprension/planificacion",
  N2: "N2 - Elaboracion estrategica",
  N3: "N3 - Validacion",
  N4: "N4 - Interaccion con IA",
  meta: "meta - Apertura/cierre",
}

export const ADVERSARIAL_DOCENTE: Record<string, string> = {
  jailbreak_indirect: "Intento de manipulacion indirecta",
  jailbreak_substitution: "Intento de manipulacion por sustitucion",
  jailbreak_fiction: "Intento de manipulacion por ficcion",
  persuasion_urgency: "Intento de persuasion por urgencia",
  prompt_injection: "Intento de inyeccion de instrucciones",
}

export const SEVERITY_DOCENTE: Record<string, string> = {
  "1": "Muy bajo",
  "2": "Bajo",
  "3": "Moderado",
  "4": "Alto",
  "5": "Critico",
}

export function slopeToDocente(slope: number | null): {
  label: string
  emoji: string
  color: string
  action: string | null
} {
  if (slope === null) {
    return {
      label: "Sin datos suficientes",
      emoji: "?",
      color: "text-muted",
      action: "Necesita completar mas trabajos para tener una tendencia.",
    }
  }
  if (slope > 0.1) {
    return {
      label: "Mejorando",
      emoji: "↑",
      color: "text-[var(--color-success)]",
      action: null,
    }
  }
  if (slope < -0.1) {
    return {
      label: "En riesgo",
      emoji: "↓",
      color: "text-[var(--color-danger)]",
      action: "Considerá revisar sus ultimos trabajos y hablar con el/ella.",
    }
  }
  return {
    label: "Estable",
    emoji: "→",
    color: "text-muted",
    action: null,
  }
}

export function kappaToDocente(kappa: number): {
  label: string
  description: string
  color: string
} {
  if (kappa >= 0.81) {
    return {
      label: "Excelente acuerdo",
      description:
        "Tu criterio y el del clasificador automatico coinciden casi siempre. La evaluacion es muy consistente.",
      color: "text-green-700 bg-green-50",
    }
  }
  if (kappa >= 0.61) {
    return {
      label: "Buen acuerdo",
      description:
        "Tu criterio y el del clasificador coinciden en la mayoria de los casos. La evaluacion es confiable.",
      color: "text-green-700 bg-green-50",
    }
  }
  if (kappa >= 0.41) {
    return {
      label: "Acuerdo moderado",
      description:
        "Hay diferencias entre tu criterio y el del clasificador. Conviene revisar los casos donde no coinciden.",
      color: "text-warning/85 bg-warning-soft",
    }
  }
  return {
    label: "Acuerdo bajo",
    description:
      "Tu criterio y el del clasificador difieren bastante. Revisá los criterios de evaluacion y re-calibrá.",
    color: "text-danger bg-danger-soft",
  }
}

export function studentShortLabel(pseudonym: string): string {
  // Los pseudonyms del seed tienen patron tipo `c1c1c1c1-0001-...-000000000001`
  // donde los PRIMEROS chars son la marca de la comision (identicos para todos)
  // y la entropia esta en los ULTIMOS chars. Usar los ultimos 6 garantiza
  // unicidad visual en cohortes < 1000 estudiantes tambien para UUIDs aleatorios
  // de produccion.
  const tail = pseudonym.replace(/-/g, "").slice(-6)
  return `Est. ${tail}`
}
