/**
 * Cómo escribe PSeInt los valores (HU-030, perfil por defecto 20250314).
 *
 * Los números se escriben como `printf("%.10f")` sin los ceros del final:
 * `7/2` → `3.5`, `1/3` → `0.3333333333`, `0.1+0.2` → `0.3`, `2^60` sale entero
 * y exacto. `toFixed(10)` redondea igual que `printf` (con el valor binario
 * exacto); por encima de 1e21 `toFixed` pasa a notación científica, y ahí el
 * número ya es entero, así que se escribe con `BigInt`.
 */

export type Valor = number | string | boolean

export function formatearNumero(x: number): string {
  if (Number.isNaN(x)) return "nan"
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf"
  if (Math.abs(x) >= 1e21) return BigInt(x).toString()
  let s = x.toFixed(10)
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "")
  return s === "-0" ? "0" : s
}

export function formatear(v: Valor): string {
  if (typeof v === "number") return formatearNumero(v)
  if (typeof v === "boolean") return v ? "VERDADERO" : "FALSO"
  return v
}
