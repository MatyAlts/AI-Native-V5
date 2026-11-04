/**
 * Codificacion (inter-jueces) del estudio de codificacion ciega (change
 * cibse-codificacion-ciega; design D7, D9, D10, D13).
 *
 * Codificador: lista de items en SU orden (posicion por semilla, D7), traza
 * ciega + formulario del esquema por item, guardado incremental y cierre con
 * confirmacion. El investigador ve la administracion del estudio en su lugar.
 *
 * El codificador nunca ve el `episode_id` ni el `item_id` como texto: el item se
 * nombra por su posicion en su propio orden.
 */
import { PageContainer, useConfirm } from "@platform/ui"
import { useCallback, useEffect, useState } from "react"
import {
  type CodebookVersion,
  type EsquemaFormulario,
  type EtiquetaGuardada,
  type ItemCodificador,
  type Membresia,
  type RespuestaFormulario,
  type TokenGetter,
  codigoDeError,
  estudioApi,
  statusDeError,
} from "../../lib/estudioApi"
import { helpContent } from "../../utils/helpContent"
import { AdministracionEstudioView } from "./AdministracionEstudioView"
import { FormularioEsquema } from "./FormularioEsquema"
import { SeccionEstudio } from "./SeccionEstudio"
import { TrazaCiega } from "./TrazaCiega"
import { mensajeDeErrorEstudio } from "./mensajesError"

export function CodificacionEstudioView({ getToken }: { getToken: TokenGetter }) {
  return (
    <PageContainer
      title="Codificación (inter-jueces)"
      description="Codificación a ciegas de la muestra del estudio, con el formulario del codebook vigente."
      helpContent={helpContent.interraterCoding}
    >
      <div className="max-w-5xl">
        <SeccionEstudio getToken={getToken}>
          {(m) =>
            m.rol === "investigador" ? (
              <AdministracionEstudioView clave={m.clave} rol={m.rol} getToken={getToken} />
            ) : (
              <PanelCodificador key={m.clave} membresia={m} getToken={getToken} />
            )
          }
        </SeccionEstudio>
      </div>
    </PageContainer>
  )
}

interface Faltante {
  item_id: string
  posicion: number
  motivos: string[]
}

/**
 * Los motivos del 422 de cierre llegan como codigos estables del backend
 * (`services/estudio_esquema.py::faltantes_cierre`): `regimen`, `dimension:<clave>`,
 * `cita:<clave>`, `notas`, `confianza`, y `sin_etiqueta` para un item sin guardar.
 * Se muestran con el nombre de la dimension del esquema; un codigo desconocido se
 * muestra tal cual antes que perderlo.
 */
export function describirMotivo(motivo: string, esquema: EsquemaFormulario): string {
  const nombre = (clave: string) =>
    esquema.dimensiones.find((d) => d.clave === clave)?.nombre ?? clave
  if (motivo === "regimen") return "régimen"
  if (motivo === "notas") return "notas"
  if (motivo === "confianza") return "confianza"
  if (motivo === "sin_etiqueta") return "sin etiqueta"
  if (motivo.startsWith("dimension:")) return `valor de ${nombre(motivo.slice(10))}`
  if (motivo.startsWith("cita:")) return `cita de ${nombre(motivo.slice(5))}`
  return motivo
}

function faltantesDe(e: unknown): Faltante[] | null {
  if (statusDeError(e) !== 422 || !e || typeof e !== "object") return null
  const detail = (e as { detail?: unknown }).detail
  if (!detail || typeof detail !== "object") return null
  const lista = (detail as { faltantes?: unknown }).faltantes
  // Una lista vacia no es "faltan 0": se muestra como error comun (verify-1, F4).
  if (!Array.isArray(lista) || lista.length === 0) return null
  return lista.filter(
    (f): f is Faltante =>
      !!f &&
      typeof f === "object" &&
      typeof (f as Faltante).item_id === "string" &&
      typeof (f as Faltante).posicion === "number",
  )
}

const ETIQUETA_ESTADO: Record<ItemCodificador["estado"], string> = {
  sin_empezar: "sin empezar",
  parcial: "parcial",
  completa: "completa",
}

type Carga =
  | { fase: "cargando" }
  | { fase: "error"; mensaje: string }
  | { fase: "sin_codebook" }
  | { fase: "lista"; codebook: CodebookVersion; items: ItemCodificador[] }

function PanelCodificador({
  membresia,
  getToken,
}: {
  membresia: Membresia
  getToken: TokenGetter
}) {
  const clave = membresia.clave
  const confirm = useConfirm()
  const [carga, setCarga] = useState<Carga>({ fase: "cargando" })
  const [abierto, setAbierto] = useState<string | null>(null)
  const [cerrada, setCerrada] = useState(membresia.cerrada)
  const [faltantes, setFaltantes] = useState<Faltante[] | null>(null)
  const [errorCierre, setErrorCierre] = useState<string | null>(null)

  useEffect(() => {
    let cancelado = false
    Promise.all([estudioApi.codebookVigente(clave, getToken), estudioApi.misItems(clave, getToken)])
      .then(([codebook, items]) => {
        if (!cancelado) setCarga({ fase: "lista", codebook, items })
      })
      .catch((e: unknown) => {
        if (cancelado) return
        if (statusDeError(e) === 404 && codigoDeError(e) === "sin_codebook") {
          setCarga({ fase: "sin_codebook" })
        } else {
          setCarga({ fase: "error", mensaje: mensajeDeErrorEstudio(e) })
        }
      })
    return () => {
      cancelado = true
    }
  }, [clave, getToken])

  const refrescarItems = useCallback(async () => {
    const items = await estudioApi.misItems(clave, getToken)
    setCarga((prev) => (prev.fase === "lista" ? { ...prev, items } : prev))
  }, [clave, getToken])

  const cerrar = async () => {
    setErrorCierre(null)
    setFaltantes(null)
    const ok = await confirm({
      title: "Cerrar tu codificación",
      message:
        "Al cerrar, tu codificación queda registrada y ya no vas a poder modificar ninguna etiqueta. Se rechaza si algún ítem está incompleto.",
    })
    if (!ok) return
    try {
      await estudioApi.cerrarMiCodificacion(clave, getToken)
      setCerrada(true)
    } catch (e) {
      const f = faltantesDe(e)
      if (f) setFaltantes(f)
      else setErrorCierre(mensajeDeErrorEstudio(e))
    }
  }

  if (carga.fase === "cargando") return <p className="text-sm text-muted">Cargando la muestra…</p>
  if (carga.fase === "error") {
    return (
      <div
        role="alert"
        className="rounded-lg border border-border bg-danger-soft p-4 text-sm text-danger"
      >
        {carga.mensaje}
      </div>
    )
  }
  if (carga.fase === "sin_codebook") {
    return (
      <p className="rounded-lg border border-border bg-white p-4 text-sm text-ink">
        Todavía no hay un codebook vigente en el estudio. La codificación se habilita cuando el
        investigador lo cargue y lo congele.
      </p>
    )
  }
  if (carga.codebook.estado !== "congelada" || carga.codebook.esquema === null) {
    return (
      <p className="rounded-lg border border-border bg-white p-4 text-sm text-ink">
        El codebook vigente todavía es un borrador ({carga.codebook.etiqueta}). Se puede leer y
        practicar en Entrenamiento-Recalibración; la codificación se habilita cuando el investigador
        lo congele.
      </p>
    )
  }

  if (carga.items.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-white p-4 text-sm text-ink">
        La muestra del estudio todavía no se cargó: no hay ítems para codificar. Cuando el
        investigador la cargue, aparecen acá en tu orden.
      </p>
    )
  }

  const esquema = carga.codebook.esquema
  const items = [...carga.items].sort((a, b) => a.posicion - b.posicion)
  const completos = items.filter((i) => i.estado === "completa").length
  const itemAbierto = items.find((i) => i.item_id === abierto) ?? null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-white px-4 py-3">
        <p className="text-sm text-ink">
          <span className="font-medium tabular-nums">
            {completos} de {items.length} completos
          </span>
          <span className="text-muted"> · codebook {carga.codebook.etiqueta} (congelado)</span>
        </p>
        {cerrada ? (
          <p className="text-sm font-medium text-ink">
            Tu codificación está cerrada: ya no se pueden guardar cambios.
          </p>
        ) : (
          <button
            type="button"
            onClick={() => void cerrar()}
            className="rounded border border-border px-3 py-1.5 text-sm hover:bg-canvas"
          >
            Cerrar mi codificación
          </button>
        )}
      </div>

      {faltantes && (
        <div role="alert" className="rounded-lg border border-border bg-warning-soft p-4 text-sm">
          <p className="font-medium text-ink">Faltan {faltantes.length} ítems para poder cerrar:</p>
          <ul className="list-disc ml-5">
            {faltantes.map((f) => (
              <li key={f.item_id}>
                {`Ítem ${f.posicion}: ${f.motivos.map((m) => describirMotivo(m, esquema)).join(", ")}`}
              </li>
            ))}
          </ul>
        </div>
      )}
      {errorCierre && (
        <div
          role="alert"
          className="rounded-lg border border-border bg-danger-soft p-4 text-sm text-danger"
        >
          {errorCierre}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[14rem_1fr]">
        <ul aria-label="Ítems en tu orden" className="space-y-1">
          {items.map((it) => (
            <li key={it.item_id}>
              <button
                type="button"
                onClick={() => setAbierto(it.item_id)}
                aria-current={it.item_id === abierto ? "true" : undefined}
                className={`w-full rounded border px-3 py-1.5 text-left text-sm ${
                  it.item_id === abierto ? "border-blue-600 bg-white" : "border-border bg-white"
                }`}
              >
                <span className="font-medium tabular-nums">Ítem {it.posicion}</span>
                <span className="text-muted"> · {ETIQUETA_ESTADO[it.estado]}</span>
              </button>
            </li>
          ))}
        </ul>

        <div className="min-w-0 space-y-4">
          {itemAbierto === null ? (
            <p className="text-sm text-muted">Elegí un ítem de la lista para ver su traza.</p>
          ) : (
            <>
              <h2 className="text-base font-semibold text-ink">Ítem {itemAbierto.posicion}</h2>
              <TrazaCiega clave={clave} itemId={itemAbierto.item_id} getToken={getToken} />
              <EditorEtiqueta
                key={itemAbierto.item_id}
                clave={clave}
                itemId={itemAbierto.item_id}
                esquema={esquema}
                getToken={getToken}
                deshabilitado={cerrada}
                faltantes={(
                  faltantes?.find((f) => f.item_id === itemAbierto.item_id)?.motivos ?? []
                ).map((m) => describirMotivo(m, esquema))}
                onGuardado={refrescarItems}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function EditorEtiqueta({
  clave,
  itemId,
  esquema,
  getToken,
  deshabilitado,
  faltantes,
  onGuardado,
}: {
  clave: string
  itemId: string
  esquema: NonNullable<CodebookVersion["esquema"]>
  getToken: TokenGetter
  deshabilitado: boolean
  faltantes: string[]
  onGuardado: () => Promise<void>
}) {
  const [inicial, setInicial] = useState<EtiquetaGuardada | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelado = false
    estudioApi.miEtiqueta(clave, itemId, getToken).then(
      (et) => {
        if (!cancelado) setInicial(et)
      },
      (e: unknown) => {
        if (cancelado) return
        // Un item nunca guardado llega como 200 con la etiqueta vacia: un 404 es
        // un item que no es de la muestra, y no se ofrece formulario.
        setError(mensajeDeErrorEstudio(e))
      },
    )
    return () => {
      cancelado = true
    }
  }, [clave, itemId, getToken])

  const guardar = useCallback(
    async (r: RespuestaFormulario) => {
      const guardada = await estudioApi.guardarMiEtiqueta(clave, itemId, r, getToken)
      await onGuardado().catch(() => undefined)
      return guardada
    },
    [clave, itemId, getToken, onGuardado],
  )

  if (error) {
    return (
      <div
        role="alert"
        className="rounded-lg border border-border bg-danger-soft p-4 text-sm text-danger"
      >
        {error}
      </div>
    )
  }
  if (inicial === undefined) return <p className="text-sm text-muted">Cargando tu etiqueta…</p>
  return (
    <FormularioEsquema
      esquema={esquema}
      inicial={inicial}
      onGuardar={guardar}
      deshabilitado={deshabilitado}
      faltantes={faltantes}
    />
  )
}
