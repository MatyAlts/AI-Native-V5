/**
 * Fechas de apertura del campus (HU-035).
 *
 * `fecha_apertura` viaja como "YYYY-MM-DD" (un `date` de Python, sin hora).
 * Nunca pasa por `new Date("2027-03-16")`: eso la lee como medianoche UTC y en
 * Argentina (UTC-3) se muestra el dia anterior. Se compara y se formatea como
 * texto.
 */

const ZONA_CAMPUS = "America/Argentina/Buenos_Aires"

/** "Hoy" en Argentina como "YYYY-MM-DD" (sv-SE formatea en ISO). */
export function hoyCampus(ahora: Date = new Date()): string {
  return ahora.toLocaleDateString("sv-SE", { timeZone: ZONA_CAMPUS })
}

/** Una unidad sin fecha esta abierta; con fecha, abre ese mismo dia. */
export function unidadAbierta(fecha: string | null | undefined, hoy: string): boolean {
  if (!fecha) return true
  // Comparar "YYYY-MM-DD" como texto respeta el orden cronologico.
  return fecha.slice(0, 10) <= hoy
}

/** "2027-03-09" -> "09/03/2027". */
export function formatearFecha(fecha: string): string {
  const [anio, mes, dia] = fecha.slice(0, 10).split("-")
  return `${dia}/${mes}/${anio}`
}

/**
 * Un instante ISO (`fecha_fin`, `submitted_at`: datetime con zona) pasado al
 * dia de Argentina, "YYYY-MM-DD". A diferencia de `fecha_apertura`, aca si
 * corresponde convertir de zona. null si no hay fecha o no se puede leer.
 */
export function diaDeInstante(instante: string | null | undefined): string | null {
  if (!instante) return null
  const d = new Date(instante)
  if (Number.isNaN(d.getTime())) return null
  return hoyCampus(d)
}
