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

// Subgrupos en lenguaje docente (selector de protocolo del inter-rater).
// Coinciden con classifier-service/services/subgrupo.py.
export const SUBGRUPO_DOCENTE: Record<string, string> = {
  autonomo_competente: "Autonomo: resolvio bien solo",
  autonomo_trabado: "Autonomo: se trabo sin pedir ayuda",
  escribe_sin_validar: "Escribio codigo sin probarlo",
  desenganchado: "Poco enganchado con la tarea",
  colaborador_reflexivo: "Colaboro con la IA reflexionando",
  colaborador_funcional: "Uso la IA de forma funcional",
  dependiente: "Dependio de la IA",
  indeterminado: "Sesion muy corta / sin señal",
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

// IMPORTANTE: estos labels DEBEN reflejar la semántica del event_labeler
// (apps/classifier-service/.../event_labeler.py:DEFAULT_EVENT_LEVELS).
//   - `edicion_codigo` (escribir código) → N2
//   - `codigo_ejecutado` (botón Ejecutar) → N3
//   - `tests_ejecutados` → N3 (o N4 si todos pasan + tutor reciente)
// Por eso N2 incluye "escribiendo código" y N3 dice "probando" (ejecutando),
// no "escribiendo". Cambiar la semántica del labeler requiere bumpear
// LABELER_VERSION + re-clasificar — pero los labels del UI pueden y deben
// alinearse con lo que ya se mide.
export const NLEVEL_DOCENTE: Record<string, string> = {
  N1: "Leyendo el problema",
  N2: "Planificando y escribiendo codigo",
  N3: "Probando codigo (ejecutando)",
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

export function studentShortLabel(
  pseudonym: string,
  profilesMap?: Map<string, string>,
): string {
  // Si el alumno ya se logueo con Clerk y auto-completo su perfil, mostramos
  // el nombre real (full_name). Caso contrario, fallback al pseudonym corto.
  const realName = profilesMap?.get(pseudonym)
  if (realName) return realName
  // Los pseudonyms del seed tienen patron tipo `c1c1c1c1-0001-...-000000000001`
  // donde los PRIMEROS chars son la marca de la comision (identicos para todos)
  // y la entropia esta en los ULTIMOS chars. Usar los ultimos 6 garantiza
  // unicidad visual en cohortes < 1000 estudiantes tambien para UUIDs aleatorios
  // de produccion.
  const tail = pseudonym.replace(/-/g, "").slice(-6)
  return `Est. ${tail}`
}

// ─── Explicación del estado del alumno en lenguaje docente ───────────────
//
// Traduce las métricas de coherencia (ritmo temporal, código-discurso,
// enfoque inter-iteración) a una explicación SIN números ni jerga, que
// cambia según el valor de cada dimensión. Reemplaza el `appropriation_reason`
// técnico del backend en la UI del docente. NO altera la clasificación —
// es solo presentación (mismo espíritu que el feedback al alumno en
// web-student/EpisodePage.tsx). El reason técnico sigue persistido en el CTR
// para auditoría/investigador (paper §4.4 + ADR-053).
export interface EstadoDocenteExplicado {
  resumen: string
  factores: string[]
  sinActividad?: boolean
}

export function explicarEstadoDocente(
  c: {
    appropriation: string
    ct_summary: number | null
    ccd_mean: number | null
    ccd_orphan_ratio: number | null
    cii_stability: number | null
  },
  eventosCognitivos?: number | null,
): EstadoDocenteExplicado {
  // Episodio vacío: solo abrió/cerró, sin actividad cognitiva (niveles N1-N4).
  // Las métricas de coherencia caen a defaults neutros (~0.5) que NO
  // representan trabajo real — afirmar "trabajo ordenado" seria falso.
  // Decimos la verdad en lugar de inventar señales.
  if (eventosCognitivos === 0) {
    return {
      sinActividad: true,
      resumen:
        "La sesion fue demasiado corta para evaluar: el alumno practicamente solo abrio y cerro el episodio, sin trabajar en el problema.",
      factores: [
        "No se registro lectura del enunciado, escritura de codigo, ejecucion ni dialogo con el tutor.",
      ],
    }
  }

  const factores: string[] = []

  // Ritmo de trabajo (coherencia temporal)
  if (c.ct_summary !== null) {
    if (c.ct_summary >= 0.65)
      factores.push("Trabajo de forma ordenada y sostenida en el tiempo.")
    else if (c.ct_summary >= 0.35)
      factores.push("Tuvo un ritmo de trabajo irregular, con idas y vueltas.")
    else factores.push("Trabajo de forma muy fragmentada, con muchas interrupciones.")
  }

  // Código vs. diálogo (coherencia código-discurso)
  if (c.ccd_orphan_ratio !== null && c.ccd_orphan_ratio >= 0.5) {
    factores.push(
      "Ejecuto o edito codigo sin explicar que buscaba ni consultarlo con el tutor.",
    )
  } else if (c.ccd_mean !== null && c.ccd_mean >= 0.65) {
    factores.push(
      "Acompano lo que programaba con lo que conversaba: codigo y razonamiento fueron de la mano.",
    )
  } else if (c.ccd_mean !== null && c.ccd_mean < 0.35) {
    factores.push("Casi no verbalizo su razonamiento mientras programaba.")
  } else if (c.ccd_mean !== null) {
    factores.push("En parte explico lo que hacia, en parte trabajo sin verbalizar.")
  }

  // Profundización (estabilidad inter-iteración)
  if (c.cii_stability !== null) {
    if (c.cii_stability > 0.2)
      factores.push(
        "Se mantuvo enfocado en el mismo problema, profundizando en lugar de saltar de tema.",
      )
    else
      factores.push(
        "No llego a profundizar: toco varias cosas sin sostener una sola linea de trabajo.",
      )
  }

  let resumen: string
  switch (c.appropriation) {
    case "apropiacion_reflexiva":
      resumen =
        "En conjunto, fue un trabajo reflexivo y autonomo: las tres dimensiones se acompanaron."
      break
    case "delegacion_pasiva":
      resumen =
        "El patron sugiere que se apoyo en el tutor sin construir comprension propia. Conviene conversarlo con el alumno."
      break
    default:
      resumen =
        "Hubo intento y actividad, pero sin evidencia suficiente de comprension profunda. Vale la pena preguntarle como llego a su solucion."
  }

  return { resumen, factores }
}
