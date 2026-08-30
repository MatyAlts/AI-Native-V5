/**
 * `?raw` de Vite sobre archivos `.py`.
 *
 * Vite ya sabe servir cualquier archivo como texto con el sufijo `?raw`; lo que
 * falta es que TypeScript lo sepa. Sin esta declaracion, `import arnes from
 * "./arnes.py?raw"` no compila y la unica salida seria volver a pegar el Python
 * adentro de un `.ts` — que es exactamente de lo que veniamos.
 */
declare module "*.py?raw" {
  const contenido: string
  export default contenido
}
