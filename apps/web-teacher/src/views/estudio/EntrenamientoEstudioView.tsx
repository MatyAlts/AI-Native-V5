/**
 * Entrenamiento-Recalibracion del estudio de codificacion ciega (change
 * cibse-codificacion-ciega; design D8, D11, D13).
 *
 * Muestra el codebook VIGENTE tal como lo cargo el investigador (borrador o
 * congelado, con marca visible), los ejemplos (anclas `ejemplo`: traza, respuesta
 * esperada y explicacion) y la practica (anclas `practica`: a ciegas; la respuesta
 * esperada llega recien con la devolucion de cada envio).
 *
 * El entrenamiento NO es requisito para codificar (decision del 04/11/2026): no
 * hay umbral de aciertos ni bloqueo. Nada del entrenamiento del piloto vive aca:
 * todo el contenido sale del codebook y de las anclas persistidas.
 */
import { MarkdownRenderer, PageContainer } from "@platform/ui"
import { useCallback, useEffect, useState } from "react"
import {
  type DevolucionPractica,
  type EjemploEntrenamiento,
  type Entrenamiento,
  type EsquemaFormulario,
  type Membresia,
  type RespuestaFormulario,
  type TokenGetter,
  estudioApi,
} from "../../lib/estudioApi"
import { helpContent } from "../../utils/helpContent"
import { FormularioEsquema } from "./FormularioEsquema"
import { SeccionEstudio } from "./SeccionEstudio"
import { TrazaCiega } from "./TrazaCiega"
import { mensajeDeErrorEstudio } from "./mensajesError"

export function EntrenamientoEstudioView({ getToken }: { getToken: TokenGetter }) {
  return (
    <PageContainer
      title="Entrenamiento-Recalibración"
      description="Codebook vigente del estudio, ejemplos resueltos y práctica con devolución."
      helpContent={helpContent.estudioEntrenamiento}
    >
      <div className="max-w-5xl">
        <SeccionEstudio getToken={getToken}>
          {(m) => <PanelEntrenamiento key={m.clave} membresia={m} getToken={getToken} />}
        </SeccionEstudio>
      </div>
    </PageContainer>
  )
}

type Carga =
  | { fase: "cargando" }
  | { fase: "error"; mensaje: string }
  | { fase: "lista"; datos: Entrenamiento }

function PanelEntrenamiento({
  membresia,
  getToken,
}: {
  membresia: Membresia
  getToken: TokenGetter
}) {
  const clave = membresia.clave
  const [carga, setCarga] = useState<Carga>({ fase: "cargando" })

  useEffect(() => {
    let cancelado = false
    estudioApi.entrenamiento(clave, getToken).then(
      (datos) => {
        if (!cancelado) setCarga({ fase: "lista", datos })
      },
      (e: unknown) => {
        if (!cancelado) setCarga({ fase: "error", mensaje: mensajeDeErrorEstudio(e) })
      },
    )
    return () => {
      cancelado = true
    }
  }, [clave, getToken])

  if (carga.fase === "cargando") return <p className="text-sm text-muted">Cargando…</p>
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

  const { codebook, ejemplos, practicas } = carga.datos
  const esquema = codebook?.esquema ?? null
  const ordenados = <T extends { orden: number }>(xs: T[]) =>
    [...xs].sort((a, b) => a.orden - b.orden)

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">
        El entrenamiento no es obligatorio para codificar: sirve para leer el codebook y calibrar el
        criterio con casos ya consensuados.
      </p>

      {codebook === null ? (
        <p className="rounded-lg border border-border bg-white p-4 text-sm text-ink">
          Todavía no hay codebook cargado en el estudio.
        </p>
      ) : (
        <section className="rounded-lg border border-border bg-white p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="font-medium text-ink">Codebook {codebook.etiqueta}</span>
            {codebook.estado === "borrador" ? (
              <span className="rounded bg-warning-soft px-2 py-0.5 font-medium text-ink">
                Borrador: puede cambiar antes de congelarse
              </span>
            ) : (
              <span className="font-mono" title={codebook.contenido_sha256 ?? ""}>
                congelado · sha256 {codebook.contenido_sha256}
              </span>
            )}
          </div>
          <MarkdownRenderer content={codebook.contenido_md} />
        </section>
      )}

      {ejemplos.length === 0 && practicas.length === 0 ? (
        <p className="rounded-lg border border-border bg-white p-4 text-sm text-ink">
          Todavía no hay ejemplos ni práctica cargados en la versión vigente.
        </p>
      ) : (
        <>
          {ejemplos.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-base font-semibold text-ink">Ejemplos</h2>
              {ordenados(ejemplos).map((ej) => (
                <Ejemplo
                  key={ej.item_id}
                  clave={clave}
                  ejemplo={ej}
                  esquema={esquema}
                  getToken={getToken}
                />
              ))}
            </section>
          )}
          {practicas.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-base font-semibold text-ink">Práctica</h2>
              {ordenados(practicas).map((pr) => (
                <Practica
                  key={pr.item_id}
                  clave={clave}
                  itemId={pr.item_id}
                  orden={pr.orden}
                  esquema={esquema}
                  getToken={getToken}
                />
              ))}
            </section>
          )}
        </>
      )}
    </div>
  )
}

function nombreRegimen(esquema: EsquemaFormulario | null, clave: string | null): string {
  if (clave === null) return "sin régimen"
  return esquema?.regimenes.find((r) => r.clave === clave)?.nombre ?? clave
}

function RespuestaEsperada({
  esperada,
  esquema,
}: {
  esperada: RespuestaFormulario
  esquema: EsquemaFormulario | null
}) {
  const dimensiones = esquema?.dimensiones ?? []
  return (
    <div className="text-sm text-ink space-y-1">
      <p>
        <span className="font-medium">Régimen esperado:</span>{" "}
        {nombreRegimen(esquema, esperada.regimen)}
      </p>
      <ul className="list-disc ml-5">
        {dimensiones.map((d) => {
          const r = esperada.respuestas[d.clave]
          return (
            <li key={d.clave}>
              {`${d.nombre}: ${r?.valor ?? "sin valor"}${r?.cita ? ` (${r.cita})` : ""}`}
            </li>
          )
        })}
      </ul>
      {(esperada.notas ?? "").trim() !== "" && (
        <p className="text-muted">Notas: {esperada.notas}</p>
      )}
    </div>
  )
}

function Ejemplo({
  clave,
  ejemplo,
  esquema,
  getToken,
}: {
  clave: string
  ejemplo: EjemploEntrenamiento
  esquema: EsquemaFormulario | null
  getToken: TokenGetter
}) {
  return (
    <article
      data-testid={`ejemplo-${ejemplo.item_id}`}
      className="rounded-lg border border-border bg-white p-4 space-y-3"
    >
      <h3 className="text-sm font-semibold text-ink">Ejemplo {ejemplo.orden}</h3>
      <TrazaCiega clave={clave} itemId={ejemplo.item_id} getToken={getToken} />
      <RespuestaEsperada esperada={ejemplo.respuesta_esperada} esquema={esquema} />
      <MarkdownRenderer content={ejemplo.explicacion_md} />
    </article>
  )
}

function Practica({
  clave,
  itemId,
  orden,
  esquema,
  getToken,
}: {
  clave: string
  itemId: string
  orden: number
  esquema: EsquemaFormulario | null
  getToken: TokenGetter
}) {
  const [devolucion, setDevolucion] = useState<DevolucionPractica | null>(null)

  const responder = useCallback(
    async (r: RespuestaFormulario) => {
      const dev = await estudioApi.responderPractica(clave, itemId, r, getToken)
      setDevolucion(dev)
      return {
        ...r,
        regimen: dev.regimen,
        regimen_regla: dev.regimen_regla,
        regimen_propuesto: dev.regimen_propuesto,
        updated_at: null,
      }
    },
    [clave, itemId, getToken],
  )

  return (
    <article
      data-testid={`practica-${itemId}`}
      className="rounded-lg border border-border bg-white p-4 space-y-3"
    >
      <h3 className="text-sm font-semibold text-ink">Práctica {orden}</h3>
      <TrazaCiega clave={clave} itemId={itemId} getToken={getToken} />
      {esquema === null ? (
        <p className="text-sm text-muted">
          La versión vigente todavía no tiene esquema de formulario: se puede leer la traza pero no
          responder.
        </p>
      ) : (
        <FormularioEsquema esquema={esquema} inicial={null} onGuardar={responder} />
      )}
      {devolucion && (
        <div
          data-testid={`devolucion-${itemId}`}
          className="rounded border border-border bg-canvas p-3 space-y-2"
        >
          <p className="text-sm text-ink">
            {`Tu régimen (según la regla): ${nombreRegimen(esquema, devolucion.regimen)} · Esperado: ${nombreRegimen(esquema, devolucion.esperada.regimen)} · ${
              devolucion.coincide ? "coincide" : "no coincide"
            }`}
          </p>
          <RespuestaEsperada esperada={devolucion.esperada} esquema={esquema} />
          <MarkdownRenderer content={devolucion.explicacion_md} />
        </div>
      )}
    </article>
  )
}
