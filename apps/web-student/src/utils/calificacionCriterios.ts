/**
 * BUG-19 (QA 2026-09-23) — "Ver calificacion" del alumno mostraba
 * "CRITERIOS DE EVALUACION -> 0 / NaN".
 *
 * El shape real que persiste evaluation-service (`CriterioCalificacion`,
 * `apps/evaluation-service/src/evaluation_service/schemas/entrega.py`) es
 * `{criterio, puntaje, max_puntaje, comentario}`. El tipo de este frontend
 * (`CalificacionCriterio`) estaba desalineado y usaba `nombre`/`peso`, que no
 * existen en el payload — `criterio.peso` daba `undefined`, y
 * `Math.round(undefined * 10)` da `NaN`. Ese `NaN` se mostraba tal cual, con
 * la autoridad de un numero real.
 *
 * `puntaje`/`max_puntaje` viajan como STRING cuando el modelo Pydantic
 * serializa el `Numeric` de Postgres (mismo gotcha que `nota_100` y
 * `peso_en_tp` en el resto del epic), por eso se aceptan laxos y se
 * normalizan aca.
 */
function normalizarNumero(valor: number | string | null | undefined): number | null {
  if (typeof valor === "number") return Number.isFinite(valor) ? valor : null
  const parsed = Number.parseFloat(String(valor ?? ""))
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Formatea "puntaje / max_puntaje" para un criterio de la devolucion. Un
 * valor ausente o no numerico se muestra como "—", nunca como "NaN".
 */
export function formatoCriterioPuntaje(
  puntaje: number | string | null | undefined,
  maxPuntaje: number | string | null | undefined,
): string {
  const p = normalizarNumero(puntaje)
  const m = normalizarNumero(maxPuntaje)
  return `${p ?? "—"} / ${m ?? "—"}`
}
