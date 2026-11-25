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
 *
 * Alto (HU-035): el recuadro toma el alto de su contenido. Desde afuera no se
 * puede medir (el origen es opaco), asi que el documento lo avisa: un script
 * despues de la CSP manda `{ tipo: "html-aislado:altura", altura }` con
 * `parent.postMessage` al cargar y cada vez que cambia (ResizeObserver). El
 * componente solo acepta avisos de SU iframe (`event.source`), con ese tipo y
 * una altura numerica, y la acota entre 120 y 4000 px: un script del docente
 * no puede manejar otro recuadro ni hacer la pagina infinita. Hasta que llega
 * el primer aviso el recuadro mide 200 px. El aviso no abre nada: el sandbox
 * sigue siendo solo `allow-scripts`.
 */
import { useEffect, useRef, useState } from "react"
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

const TIPO_ALTURA = "html-aislado:altura"
const ALTO_INICIAL = 200
const ALTO_MIN = 120
const ALTO_MAX = 4000

// Avisa el alto del documento al padre. Va despues de la CSP (que permite
// scripts inline) y antes del HTML del docente. Base: el alto del `<html>`
// (el del contenido, asi el recuadro tambien se achica). Si igual hay scroll
// (un HTML con `html,body{height:100%}` y algo que desborda), se toma el alto
// del scroll para que no quede una barra adentro.
const SCRIPT_ALTURA = [
  "<script>(function(){function avisar(){var d=document.documentElement;",
  "var h=d.getBoundingClientRect().height;",
  "if(d.scrollHeight>innerHeight+1){h=Math.max(h,d.scrollHeight)}",
  `parent.postMessage({tipo:"${TIPO_ALTURA}",altura:Math.ceil(h)},"*")}`,
  'addEventListener("load",avisar);',
  'if(typeof ResizeObserver!=="undefined"){new ResizeObserver(avisar).observe(document.documentElement)}',
  "})()</script>",
].join("")

export function documentoAislado(html: string): string {
  const head = [
    `<meta http-equiv="Content-Security-Policy" content="${CSP}">`,
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<style>${ESTILO_BASE}</style>`,
    SCRIPT_ALTURA,
  ].join("")
  return `<!doctype html><html><head>${head}</head><body>${html}</body></html>`
}

interface HtmlAisladoProps {
  html: string
  /** Titulo accesible del iframe (lo anuncia el lector de pantalla). */
  titulo: string
  className?: string
}

function alturaDelAviso(data: unknown): number | null {
  if (typeof data !== "object" || data === null) return null
  const { tipo, altura } = data as { tipo?: unknown; altura?: unknown }
  if (tipo !== TIPO_ALTURA || typeof altura !== "number" || !Number.isFinite(altura)) return null
  return Math.min(ALTO_MAX, Math.max(ALTO_MIN, Math.round(altura)))
}

export function HtmlAislado({ html, titulo, className }: HtmlAisladoProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [alto, setAlto] = useState(ALTO_INICIAL)

  useEffect(() => {
    function alRecibir(event: MessageEvent) {
      const propia = iframeRef.current?.contentWindow
      if (!propia || event.source !== propia) return
      const altura = alturaDelAviso(event.data)
      if (altura !== null) setAlto(altura)
    }
    window.addEventListener("message", alRecibir)
    return () => window.removeEventListener("message", alRecibir)
  }, [])

  return (
    <iframe
      ref={iframeRef}
      title={titulo}
      srcDoc={documentoAislado(html)}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      // El borde va como ring (no ocupa lugar): con un borde de verdad el
      // documento tendria 2 px menos que el alto avisado y quedaria scrolleando.
      style={{ height: `${alto}px` }}
      className={cn("block w-full rounded-lg border-0 ring-1 ring-border bg-surface", className)}
    />
  )
}
