/**
 * Recuadro aislado para HTML escrito por usuarios (HU-033).
 *
 * El HTML del campus (bienvenida e introduccion de unidad) lo escribe el
 * docente y puede traer JS. Nunca se inyecta en la pagina
 * (`dangerouslySetInnerHTML` queda prohibido para esto): se muestra dentro de
 * un `<iframe srcDoc>` con dos barreras independientes:
 *
 * - `sandbox="allow-scripts"` sin `allow-same-origin`: el documento corre en
 *   un origen opaco, asi que su JS no lee cookies, storage ni la sesion de la
 *   plataforma, no navega la pagina de arriba y no envia formularios.
 * - Una CSP en el propio documento con `connect-src 'none'`: el JS no puede
 *   mandar datos a ningun lado con fetch/XHR/WebSocket. Va antes del HTML del
 *   usuario para que rija desde el primer script.
 *
 * Lo usan la vista previa del docente y el campus del alumno: el mismo
 * recuadro, asi lo que se previsualiza es lo que se ve.
 */
import { cn } from "../utils/cn"

const CSP =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
  "img-src https: data:; font-src https: data:; media-src https:; frame-src https:; " +
  "connect-src 'none'"

// Estilo base minimo para que un HTML sin estilos propios se lea bien; el
// docente lo puede pisar con su propio <style>.
const ESTILO_BASE =
  "body{margin:0;padding:16px;font-family:system-ui,sans-serif;line-height:1.5;" +
  "color:#2a2a2a;background:#ffffff}img,video{max-width:100%;height:auto}"

export function documentoAislado(html: string): string {
  const head = [
    `<meta http-equiv="Content-Security-Policy" content="${CSP}">`,
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<style>${ESTILO_BASE}</style>`,
  ].join("")
  return `<!doctype html><html><head>${head}</head><body>${html}</body></html>`
}

interface HtmlAisladoProps {
  html: string
  /** Titulo accesible del iframe (lo anuncia el lector de pantalla). */
  titulo: string
  className?: string
}

export function HtmlAislado({ html, titulo, className }: HtmlAisladoProps) {
  return (
    <iframe
      title={titulo}
      srcDoc={documentoAislado(html)}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      className={cn(
        "block w-full min-h-[400px] rounded-lg border border-border bg-surface",
        className,
      )}
    />
  )
}
