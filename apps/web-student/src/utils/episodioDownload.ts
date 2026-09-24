/**
 * ADE-01 (change `alumno-descarga-episodio`, Lote 1) — arma el archivo de
 * codigo fuente que el alumno descarga de su episodio cerrado: su codigo
 * final + su conversacion con el tutor, comentada al pie para que el
 * archivo siga siendo sintacticamente valido.
 *
 * Pura a proposito: recibe `meta.fecha` ya formateada en vez de llamar
 * `new Date()` adentro, para que sea testeable sin depender del reloj. El
 * llamador (Lote 2, ADE-02) decide el formato de fecha.
 *
 * Privacidad (proposal.md "Gobierno de privacidad"): SOLO usa lo que llega
 * en `messages` (alumno<->tutor, del endpoint `GET /api/v1/episodes/{id}`).
 * El system prompt del tutor nunca esta en `messages` y este helper no lo
 * referencia ni lo infiere.
 */

export interface EpisodioMensaje {
  role: "user" | "assistant"
  content: string
  ts: string
}

export interface EpisodioSourceMeta {
  /** Titulo del ejercicio/TP, para el header y el slug del filename. */
  ejercicioTitulo: string
  /** Fecha ya formateada por el llamador (no se llama `new Date()` aca). */
  fecha: string
}

export interface BuildEpisodioSourceFileInput {
  code: string | null
  messages: EpisodioMensaje[]
  language: "python" | "java" | string | null | undefined
  meta: EpisodioSourceMeta
}

export interface EpisodioSourceFile {
  filename: string
  content: string
}

interface LenguajeConfig {
  extension: string
  comentario: string
}

const LENGUAJES: Record<"python" | "java", LenguajeConfig> = {
  python: { extension: "py", comentario: "#" },
  java: { extension: "java", comentario: "//" },
}

function resolverLenguaje(language: BuildEpisodioSourceFileInput["language"]): LenguajeConfig {
  return language === "java" ? LENGUAJES.java : LENGUAJES.python
}

/** Slug legible y seguro para filename: minusculas, solo [a-z0-9-]. */
function slug(texto: string): string {
  const limpio = texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // saca acentos
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  return limpio || "episodio"
}

function comentarLinea(comentario: string, texto: string): string {
  return texto.length > 0 ? `${comentario} ${texto}` : comentario
}

const ROL_LABEL: Record<EpisodioMensaje["role"], string> = {
  user: "Alumno",
  assistant: "Tutor",
}

/**
 * Comenta la charla alumno<->tutor al pie, linea por linea (cada linea de
 * cada mensaje lleva su propio prefijo de comentario para que el archivo
 * siga siendo sintacticamente valido) y con el rol visible en cada linea
 * para distinguir alumno de tutor al ojo.
 */
function armarCharla(comentario: string, messages: EpisodioMensaje[]): string {
  return messages
    .map((m) => {
      const prefijo = `[${ROL_LABEL[m.role]}] `
      return m.content
        .split("\n")
        .map((linea) => comentarLinea(comentario, `${prefijo}${linea}`))
        .join("\n")
    })
    .join(`\n${comentario}\n`)
}

export function buildEpisodioSourceFile(input: BuildEpisodioSourceFileInput): EpisodioSourceFile {
  const { code, messages, language, meta } = input
  const { extension, comentario } = resolverLenguaje(language)
  const filename = `${slug(meta.ejercicioTitulo)}.${extension}`

  const header = [
    comentarLinea(comentario, meta.ejercicioTitulo),
    comentarLinea(comentario, meta.fecha),
  ].join("\n")

  const cuerpo =
    code && code.length > 0 ? code : comentarLinea(comentario, "(sin codigo entregado)")

  const partes = [header, "", cuerpo]

  if (messages.length > 0) {
    const charlaHeader = comentarLinea(comentario, "--- Charla con el tutor ---")
    partes.push("", charlaHeader, armarCharla(comentario, messages))
  }

  return { filename, content: partes.join("\n") }
}
