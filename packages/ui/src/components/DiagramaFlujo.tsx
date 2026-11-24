/**
 * Diagrama de flujo de un algoritmo PSeInt (HU-031). ESQUELETO DE
 * ACEPTACIÓN: fija el contrato; el constructor lo reemplaza.
 *
 * Contrato del DOM (lo usan las pruebas y los lectores de pantalla):
 * - un `<svg role="img">` por diagrama (principal, funciones y subprocesos),
 *   con `aria-label` que nombra el algoritmo;
 * - cada forma es un `<g data-tipo="<TipoNodo>">` con su texto visible;
 * - una lista ordenada (`<ol>`) con los pasos en texto, para quien no ve el
 *   dibujo (puede estar oculta visualmente, no con `display:none`);
 * - con un error de sintaxis no hay `<svg>`: se muestra un aviso con la línea.
 */
export interface DiagramaFlujoProps {
  /** Pseudocódigo PSeInt a dibujar. */
  fuente: string
  className?: string
}

export function DiagramaFlujo(_props: DiagramaFlujoProps) {
  return null
}
