/**
 * Vista ciega de un episodio para el estudio de codificacion (change
 * cibse-codificacion-ciega; design D4, D13, D14).
 *
 * El cegamiento real lo hace classifier-service con la lista blanca `traza_v1`.
 * Esta vista es la SEGUNDA barrera y falla cerrada igual que la primera:
 *   - renderiza solo los tipos que conoce; un tipo nuevo o inesperado se omite;
 *   - de cada tipo lee solo los campos que conoce por nombre; nunca recorre
 *     `datos` ni lo serializa, asi que una clave que el servidor no deberia
 *     mandar tampoco llega al DOM;
 *   - nunca muestra hora absoluta, ids ni JSON crudo: solo tiempo relativo y
 *     localizadores (global `#n` y por tipo: turno k, codigo k, ejecucion k...).
 *
 * Los localizadores son los que el codificador escribe en sus citas ("turno 3;
 * ejecucion 4"): el texto de cada uno tiene que ser exactamente el del codebook.
 */
import { MarkdownRenderer } from "@platform/ui"
import { useEffect, useId, useState } from "react"
import {
  type ElementoTraza,
  type TokenGetter,
  type TrazaCiega as TrazaCiegaData,
  codigoDeError,
  estudioApi,
  statusDeError,
} from "../../lib/estudioApi"
import { diffLineas } from "../../utils/diffLineas"

interface Props {
  clave: string
  itemId: string
  getToken: TokenGetter
}

type Estado =
  | { fase: "cargando" }
  | { fase: "error"; mensaje: string }
  | { fase: "lista"; traza: TrazaCiegaData }

/** Mensaje por motivo. Nunca se reenvia el cuerpo del error del servidor. */
function mensajeDeError(e: unknown): string {
  const codigo = codigoDeError(e)
  if (codigo === "evidencia_alterada") {
    return "La evidencia de este ítem cambió desde que se cargó la muestra y no se muestra. Avisale al investigador del estudio."
  }
  if (codigo === "traza_version_distinta") {
    return "La versión de la vista ciega del sistema no coincide con la del estudio. No se muestra nada hasta que el investigador lo resuelva."
  }
  if (codigo === "enunciado_pendiente") {
    return "La consigna de este ítem todavía no está revisada por el investigador. Volvé a intentar cuando esté lista."
  }
  const status = statusDeError(e)
  if (status === 502 || status === 504) {
    return "El registro de episodios no respondió. Probá de nuevo en unos minutos."
  }
  if (status === 403) return "No tenés acceso a este ítem."
  if (status === 404) return "Este ítem no existe en el estudio."
  return "No se pudo cargar la traza de este ítem."
}

/** `+mm:ss`, o `+h:mm:ss` desde la primera hora. Nunca hora absoluta. */
export function tiempoRelativo(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const dos = (n: number) => String(n).padStart(2, "0")
  return h > 0 ? `+${h}:${dos(m)}:${dos(ss)}` : `+${dos(m)}:${dos(ss)}`
}

const NOMBRE_LOCALIZADOR: Partial<Record<ElementoTraza["tipo"], string>> = {
  mensaje_alumno: "turno",
  respuesta_tutor: "turno",
  codigo: "código",
  ejecucion: "ejecución",
  prueba: "prueba",
  nota: "nota",
  lectura: "lectura",
}

const TIPOS_CONOCIDOS = new Set<string>([
  "inicio",
  "lectura",
  "mensaje_alumno",
  "respuesta_tutor",
  "codigo",
  "ejecucion",
  "prueba",
  "nota",
  "copia",
  "pegado",
  "fin_cerrado",
  "fin_abandonado",
])

function texto(datos: Record<string, unknown>, clave: string): string | null {
  const v = datos[clave]
  return typeof v === "string" ? v : null
}

function numero(datos: Record<string, unknown>, clave: string): number | null {
  const v = datos[clave]
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

function textos(datos: Record<string, unknown>, clave: string): string[] {
  const v = datos[clave]
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
}

export function TrazaCiega({ clave, itemId, getToken }: Props) {
  const [estado, setEstado] = useState<Estado>({ fase: "cargando" })

  useEffect(() => {
    let cancelado = false
    setEstado({ fase: "cargando" })
    estudioApi.traza(clave, itemId, getToken).then(
      (traza) => {
        if (!cancelado) setEstado({ fase: "lista", traza })
      },
      (e: unknown) => {
        if (!cancelado) setEstado({ fase: "error", mensaje: mensajeDeError(e) })
      },
    )
    return () => {
      cancelado = true
    }
  }, [clave, itemId, getToken])

  if (estado.fase === "cargando") {
    return <p className="text-sm text-muted">Cargando la traza del ítem…</p>
  }
  if (estado.fase === "error") {
    return (
      <div
        role="alert"
        className="rounded-lg border border-border bg-danger-soft p-4 text-sm text-danger"
      >
        {estado.mensaje}
      </div>
    )
  }

  const { traza } = estado
  const elementos = traza.elementos.filter((el) => TIPOS_CONOCIDOS.has(el.tipo))

  return (
    <div className="space-y-4">
      <Consigna titulo="Consigna del trabajo práctico" markdown={traza.enunciado.tp_md} />
      {traza.enunciado.ejercicio_md !== null && (
        <Consigna titulo="Consigna del ejercicio" markdown={traza.enunciado.ejercicio_md} />
      )}
      <ol className="divide-y divide-border rounded-lg border border-border bg-white">
        {elementos.map((el, i) => (
          <Elemento key={el.n} elemento={el} anteriorCodigo={codigoAnterior(elementos, i)} />
        ))}
      </ol>
    </div>
  )
}

/** Snapshot del estado de codigo anterior al indice dado, o null si es el primero. */
function codigoAnterior(elementos: ElementoTraza[], indice: number): string | null {
  for (let j = indice - 1; j >= 0; j--) {
    const el = elementos[j]
    if (el?.tipo === "codigo") return texto(el.datos, "snapshot") ?? ""
  }
  return null
}

function Consigna({ titulo, markdown }: { titulo: string; markdown: string }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="rounded-lg border border-border bg-white p-4">
      <h3 id={id} className="text-xs font-semibold uppercase tracking-wider text-muted mb-2">
        {titulo}
      </h3>
      <MarkdownRenderer content={markdown} />
    </section>
  )
}

function Elemento({
  elemento,
  anteriorCodigo,
}: {
  elemento: ElementoTraza
  anteriorCodigo: string | null
}) {
  const nombre = NOMBRE_LOCALIZADOR[elemento.tipo]
  return (
    <li data-testid={`traza-elemento-${elemento.n}`} className="px-4 py-3">
      <div className="flex items-baseline gap-3 text-xs text-muted mb-1">
        <span className="font-mono tabular-nums">#{elemento.n}</span>
        <span className="font-mono tabular-nums">{tiempoRelativo(elemento.t_seg)}</span>
        {nombre && elemento.k !== null && (
          <span className="rounded bg-canvas px-1.5 py-0.5 font-medium text-ink">
            {`${nombre} ${elemento.k}`}
          </span>
        )}
      </div>
      <Cuerpo elemento={elemento} anteriorCodigo={anteriorCodigo} />
    </li>
  )
}

function Cuerpo({
  elemento,
  anteriorCodigo,
}: {
  elemento: ElementoTraza
  anteriorCodigo: string | null
}) {
  const d = elemento.datos
  switch (elemento.tipo) {
    case "inicio": {
      const lenguaje = texto(d, "language")
      return (
        <p className="text-sm text-ink">Inicio del episodio{lenguaje ? ` (${lenguaje})` : ""}</p>
      )
    }
    case "lectura":
      return (
        <p className="text-sm text-ink">
          Lectura de la consigna: {numero(d, "duration_seconds") ?? 0} s
        </p>
      )
    case "mensaje_alumno":
      return <Mensaje autor="Alumno" contenido={texto(d, "content") ?? ""} />
    case "respuesta_tutor":
      return <Mensaje autor="Tutor" contenido={texto(d, "content") ?? ""} />
    case "nota":
      return <Mensaje autor="Nota del alumno" contenido={texto(d, "content") ?? ""} />
    case "codigo":
      return <EstadoCodigo actual={texto(d, "snapshot") ?? ""} anterior={anteriorCodigo} />
    case "ejecucion":
      return <Ejecucion datos={d} />
    case "prueba": {
      const total = numero(d, "test_count_total") ?? 0
      const pasaron = numero(d, "test_count_passed") ?? 0
      const fallaron = numero(d, "test_count_failed") ?? 0
      const publicos = numero(d, "tests_publicos")
      const ocultos = numero(d, "tests_hidden")
      return (
        <p className="text-sm text-ink">
          Corrida de pruebas: {pasaron} de {total} pasaron, {fallaron} fallaron
          {publicos !== null && ocultos !== null
            ? ` (${publicos} públicas, ${ocultos} ocultas)`
            : ""}
        </p>
      )
    }
    case "copia":
      return (
        <p className="text-sm text-ink">
          Intento de copiar: {numero(d, "seleccion_chars") ?? 0} caracteres
          {texto(d, "metodo") ? ` (${texto(d, "metodo")})` : ""}
        </p>
      )
    case "pegado":
      return (
        <p className="text-sm text-ink">
          Intento de pegar: {numero(d, "contenido_longitud") ?? 0} caracteres
          {texto(d, "metodo") ? ` (${texto(d, "metodo")})` : ""}
        </p>
      )
    case "fin_cerrado":
      return <p className="text-sm font-medium text-ink">Fin: cerrado</p>
    case "fin_abandonado":
      return <p className="text-sm font-medium text-ink">Fin: abandonado</p>
    default:
      return null
  }
}

function Mensaje({ autor, contenido }: { autor: string; contenido: string }) {
  return (
    <div>
      <p className="text-xs font-semibold text-muted">{autor}</p>
      <p className="text-sm text-ink whitespace-pre-wrap">{contenido}</p>
    </div>
  )
}

function EstadoCodigo({ actual, anterior }: { actual: string; anterior: string | null }) {
  if (anterior === null) {
    return (
      <div>
        <p className="text-xs font-semibold text-muted mb-1">Estado del código</p>
        <pre className="text-xs bg-slate-950 text-slate-100 p-3 rounded overflow-x-auto max-h-80">
          {actual}
        </pre>
      </div>
    )
  }
  const diff = diffLineas(anterior, actual)
  if (!diff.disponible) {
    return (
      <div>
        <p className="text-xs font-semibold text-muted mb-1">
          Estado del código (demasiado largo para comparar con el anterior)
        </p>
        <pre className="text-xs bg-slate-950 text-slate-100 p-3 rounded overflow-x-auto max-h-80">
          {actual}
        </pre>
      </div>
    )
  }
  return (
    <div>
      <p className="text-xs font-semibold text-muted mb-1">
        Estado del código: +{diff.agregadas} / −{diff.quitadas} líneas respecto del anterior
      </p>
      <pre className="text-xs bg-slate-950 text-slate-100 p-3 rounded overflow-x-auto max-h-80">
        {diff.lineas.map((l, i) => (
          <div
            // biome-ignore lint/suspicious/noArrayIndexKey: lineas de un diff inmutable, sin id propio
            key={i}
            data-diff={l.tipo}
            className={
              l.tipo === "agregada"
                ? "bg-green-900/60"
                : l.tipo === "quitada"
                  ? "bg-red-900/60 line-through"
                  : ""
            }
          >
            <span aria-hidden="true" className="select-none opacity-60 mr-2">
              {l.tipo === "agregada" ? "+" : l.tipo === "quitada" ? "−" : " "}
            </span>
            <span className="sr-only">
              {l.tipo === "agregada" ? "agregada: " : l.tipo === "quitada" ? "quitada: " : ""}
            </span>
            {l.texto}
          </div>
        ))}
      </pre>
    </div>
  )
}

function Ejecucion({ datos }: { datos: Record<string, unknown> }) {
  const stdout = texto(datos, "stdout")
  const stderr = texto(datos, "stderr")
  const code = texto(datos, "code")
  const passed = numero(datos, "passed")
  const total = numero(datos, "total")
  const failed = numero(datos, "failed")
  const fallidas = textos(datos, "failed_test_names")
  return (
    <div className="space-y-2">
      <p className="text-sm text-ink">
        Ejecución
        {passed !== null && total !== null
          ? `: ${passed} de ${total} pruebas pasaron${failed !== null ? `, ${failed} fallaron` : ""}`
          : ""}
      </p>
      {fallidas.length > 0 && <p className="text-xs text-muted">Fallaron: {fallidas.join(", ")}</p>}
      {code !== null && (
        <details>
          <summary className="text-xs text-muted cursor-pointer">Código ejecutado</summary>
          <pre className="text-xs bg-slate-950 text-slate-100 p-3 rounded overflow-x-auto max-h-64">
            {code}
          </pre>
        </details>
      )}
      {stdout && (
        <div>
          <p className="text-xs font-semibold text-muted">Salida</p>
          <pre className="text-xs bg-canvas p-2 rounded overflow-x-auto max-h-48">{stdout}</pre>
        </div>
      )}
      {stderr && (
        <div>
          <p className="text-xs font-semibold text-danger">Salida de error</p>
          <pre className="text-xs bg-danger-soft text-danger p-2 rounded overflow-x-auto max-h-48">
            {stderr}
          </pre>
        </div>
      )}
    </div>
  )
}
