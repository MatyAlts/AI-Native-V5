/**
 * Borrador local del código de cada ejercicio, para poder mandarlo en el submit.
 *
 * El problema que resuelve: cuando el alumno aprieta "Entregar TP" desde
 * `ExerciseListView`, el código de los ejercicios NO está en memoria — cada uno
 * se escribió en un episodio del que el alumno ya salió. Y el snapshot del CTR
 * no sirve como fuente: se ingesta asíncrono y el editor emite fire-and-forget,
 * así que leerlo certifica "esto es lo que leí", no "esto es lo que entregó".
 *
 * Entonces guardamos el snapshot acá a medida que el alumno escribe, y el
 * submit lo lee. Es best-effort por naturaleza: `localStorage` es por navegador
 * y por dispositivo, no sobrevive un cambio de máquina ni el modo privado con
 * cuota llena. Un ejercicio sin borrador se manda igual, vacío no — se omite, y
 * el backend queda con un artefacto incompleto que la vista del docente marca.
 * Es un piso mucho más alto que "no hay código en ningún lado".
 */

const PREFIX = "entrega_artefacto"

export interface ArtefactoDraft {
  orden: number
  ejercicio_id: string | null
  episode_id: string | null
  codigo: string
  language: string
  /** Epoch ms del guardado. Lo usa el barrido por antigüedad, no el submit. */
  saved_at?: number
}

/**
 * El scope es la entrega cuando el alumno la conoce mientras escribe (TP con
 * ejercicios), y el episodio cuando no (TP monolítica: ahí la entrega recién
 * se crea al salir, así que al momento de editar todavía no existe).
 */
function key(scopeId: string, orden: number): string {
  return `${PREFIX}_${scopeId}_${orden}`
}

/** Orden único de la TP monolítica: un solo "ejercicio", el TP entero. */
export const MONOLITHIC_ORDEN = 1

/** Días tras los cuales un borrador se considera basura y se barre. */
const TTL_DIAS = 30

/**
 * Borra los borradores más viejos que `TTL_DIAS`.
 *
 * `clearArtefactoDrafts` sólo corre en el camino feliz del submit, así que
 * todo lo que quedó de un submit fallido, de un episodio abandonado o de una
 * TP que el alumno nunca terminó se acumulaba para siempre. Y `localStorage`
 * tiene cuota: llenarla haría fallar el guardado de los borradores nuevos,
 * que es justo lo que no puede fallar.
 */
function pruneViejos(ahora: number): void {
  try {
    const limite = ahora - TTL_DIAS * 24 * 60 * 60 * 1000
    const aBorrar: string[] = []
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i)
      if (!k?.startsWith(PREFIX)) continue
      const raw = window.localStorage.getItem(k)
      if (!raw) continue
      try {
        const parsed = JSON.parse(raw) as ArtefactoDraft
        // Sin `saved_at` es de una versión previa: se barre igual.
        if (!parsed.saved_at || parsed.saved_at < limite) aBorrar.push(k)
      } catch {
        aBorrar.push(k) // corrupto: no sirve para nada
      }
    }
    for (const k of aBorrar) window.localStorage.removeItem(k)
  } catch {
    // idem
  }
}

/** Guarda (pisando) el código del ejercicio. Best-effort: nunca tira. */
export function saveArtefactoDraft(scopeId: string, draft: ArtefactoDraft): void {
  const saved_at = Date.now()
  try {
    window.localStorage.setItem(key(scopeId, draft.orden), JSON.stringify({ ...draft, saved_at }))
  } catch {
    // Cuota llena: barremos lo viejo y reintentamos UNA vez. Si igual falla,
    // seguimos sin borrador (modo privado) — el submit tiene su fallback.
    pruneViejos(saved_at)
    try {
      window.localStorage.setItem(key(scopeId, draft.orden), JSON.stringify({ ...draft, saved_at }))
    } catch {
      // No bloqueamos al alumno por esto.
    }
  }
}

/**
 * Junta los borradores de los ejercicios pedidos, en orden.
 *
 * Omite los que no tienen borrador o cuyo código está vacío: mandar una
 * cadena vacía sería registrar "entregó nada" con la misma autoridad que
 * "entregó esto", y son cosas distintas.
 */
export function collectArtefactoDrafts(scopeId: string, ordenes: number[]): ArtefactoDraft[] {
  const out: ArtefactoDraft[] = []
  for (const orden of [...ordenes].sort((a, b) => a - b)) {
    try {
      const raw = window.localStorage.getItem(key(scopeId, orden))
      if (!raw) continue
      const parsed = JSON.parse(raw) as ArtefactoDraft
      if (typeof parsed?.codigo !== "string" || parsed.codigo.trim() === "") continue
      out.push(parsed)
    } catch {
      // Entrada corrupta: la salteamos en vez de romper la entrega entera.
    }
  }
  return out
}

/**
 * Limpia los borradores de una entrega ya enviada, y de paso barre lo viejo.
 *
 * El barrido va acá y NO en `collect`: en `collect` estaríamos borrando
 * justo lo que estamos por leer, y un borrador sin `saved_at` (guardado por
 * una versión anterior) se perdería en el mismo submit que lo necesita.
 */
export function clearArtefactoDrafts(scopeId: string, ordenes: number[]): void {
  for (const orden of ordenes) {
    try {
      window.localStorage.removeItem(key(scopeId, orden))
    } catch {
      // idem
    }
  }
  pruneViejos(Date.now())
}
