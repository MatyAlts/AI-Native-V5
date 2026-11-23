/**
 * HU-018 C03 (hallazgo F05 de HU-014): un TP de tres ejercicios con el mismo
 * peso mostraba "Peso: 100%" en cada uno, porque se leia `peso_en_tp` como
 * fraccion del total y no lo es. El peso de cada ejercicio es su parte del
 * total de pesos del TP.
 *
 * Devuelve enteros que suman 100, repartidos por el metodo del mayor resto:
 * se toma la parte entera de cada porcentaje y los puntos que faltan van a
 * los de mayor resto (a igual resto, al que aparece primero). Sin pesos
 * positivos (todos en 0, vacios o invalidos) se reparte igual. Lista vacia
 * devuelve lista vacia.
 */
export function porcentajesDePeso(pesos: number[]): number[] {
  const n = pesos.length
  if (n === 0) return []
  const limpios = pesos.map((p) => (Number.isFinite(p) && p > 0 ? p : 0))
  const total = limpios.reduce((a, b) => a + b, 0)
  const base = total > 0 ? limpios : limpios.map(() => 1)
  const suma = total > 0 ? total : n

  const exactos = base.map((p) => (p * 100) / suma)
  const enteros = exactos.map((x) => Math.floor(x))
  let faltan = 100 - enteros.reduce((a, b) => a + b, 0)
  const porResto = exactos
    .map((x, i) => ({ i, resto: x - Math.floor(x) }))
    .sort((a, b) => b.resto - a.resto || a.i - b.i)
  for (const { i } of porResto) {
    if (faltan <= 0) break
    enteros[i] = (enteros[i] ?? 0) + 1
    faltan -= 1
  }
  return enteros
}
