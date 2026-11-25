/**
 * Campus del curso (HU-033): el docente arma lo que ve el alumno al entrar al
 * campus de su comision.
 *
 *  - Bienvenida del curso en HTML.
 *  - Por unidad: introduccion en HTML (puede traer JS), fecha de apertura y
 *    resumen de la tarjeta (`descripcion`).
 *  - Plantillas (HU-036): guardar este campus como plantilla de la materia y
 *    aplicar una plantilla a la comision en un clic (no pisa lo existente; los
 *    TPs llegan en borrador y sin fechas).
 *
 * El HTML se previsualiza SIEMPRE en `HtmlAislado` (iframe sandbox + CSP), el
 * mismo recuadro que usa el campus del alumno. Nunca `dangerouslySetInnerHTML`.
 *
 * Trampa de fechas: `fecha_apertura` es una fecha sin hora ("2027-03-09").
 * `new Date("2027-03-09")` la toma como medianoche UTC y en Argentina sale el
 * dia anterior; por eso se formatea partiendo el string.
 */
import { HtmlAislado, PageContainer, useConfirm } from "@platform/ui"
import { Link } from "@tanstack/react-router"
import { useCallback, useEffect, useState } from "react"
import {
  type AplicacionPlantilla,
  type PlantillaCampus,
  type Unidad,
  aplicarPlantillaCampus,
  getBienvenida,
  guardarPlantillaCampus,
  listPlantillasCampus,
  listUnidades,
  putBienvenida,
  updateUnidad,
} from "../lib/api"
import { helpContent } from "../utils/helpContent"

interface Props {
  comisionId: string
  getToken: () => Promise<string | null>
}

type Estado =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "ok" }
  | { kind: "error"; msg: string }

interface Borrador {
  introduccion: string
  fecha: string
  resumen: string
}

export const ESTRUCTURA_SUGERIDA = [
  "De qué se trata",
  "Al terminar vas a poder",
  "Resumen interactivo",
  "La teoría",
  "Ejemplo resuelto paso a paso",
  "Errores comunes",
  "Antes del TP",
]
  .map((titulo) => `<h2>${titulo}</h2>\n<p></p>`)
  .join("\n\n")

export function textoApertura(fecha: string | null | undefined): string {
  if (!fecha) return "Abierta"
  const [anio, mes, dia] = fecha.split("-")
  return `Abre el ${dia}/${mes}/${anio}`
}

const AREA =
  "block w-full min-h-[400px] rounded-lg border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-ink focus:outline-none focus:ring-2 focus:ring-accent-brand"
const BOTON_PRIMARIO =
  "rounded-lg bg-accent-brand px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-brand-deep disabled:opacity-50 transition-colors"
const BOTON_SECUNDARIO =
  "rounded-lg border border-border bg-surface-alt px-3 py-1.5 text-sm text-ink hover:bg-border-soft transition-colors"

function AvisoEstado({ estado }: { estado: Estado }) {
  if (estado.kind === "ok") return <span className="text-sm text-success">Guardado</span>
  if (estado.kind === "error")
    return (
      <div
        role="alert"
        className="rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger"
      >
        <span className="font-semibold">No se pudo guardar.</span>{" "}
        <span className="font-mono text-xs break-all">{estado.msg}</span>
      </div>
    )
  return null
}

export function resumenAplicacion(r: AplicacionPlantilla): string {
  const unidades = r.unidades_creadas === 1 ? "1 unidad" : `${r.unidades_creadas} unidades`
  const tps = r.tps_creados === 1 ? "1 trabajo práctico" : `${r.tps_creados} trabajos prácticos`
  return `Se crearon ${unidades} y ${tps} en borrador.`
}

/**
 * Mejora #50: aplicar una plantilla sobre la comision de la que salio no crea
 * nada (no pisa lo existente) y el "Se crearon 0" se lee como una falla. La
 * plantilla no guarda la comision de origen (a proposito), asi que se detecta
 * por el resultado: nada creado y nada cargado.
 */
export function aplicacionSinCambios(r: AplicacionPlantilla): boolean {
  return r.unidades_creadas === 0 && r.tps_creados === 0 && !r.bienvenida_aplicada
}

function AvisoError({ titulo, msg }: { titulo: string; msg: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger"
    >
      <span className="font-semibold">{titulo}</span>{" "}
      <span className="font-mono text-xs break-all">{msg}</span>
    </div>
  )
}

function SeccionPlantillas({
  comisionId,
  getToken,
  onAplicada,
}: Props & { onAplicada: () => void }) {
  const [plantillas, setPlantillas] = useState<PlantillaCampus[]>([])
  const [cargando, setCargando] = useState(true)
  const [errorLista, setErrorLista] = useState<string | null>(null)
  const [nombre, setNombre] = useState("")
  const [guardando, setGuardando] = useState(false)
  const [guardada, setGuardada] = useState(false)
  const [errorGuardar, setErrorGuardar] = useState<string | null>(null)
  const [elegida, setElegida] = useState("")
  const [aplicando, setAplicando] = useState(false)
  const [resultado, setResultado] = useState<AplicacionPlantilla | null>(null)
  const [errorAplicar, setErrorAplicar] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true
    setCargando(true)
    setErrorLista(null)
    listPlantillasCampus(comisionId, getToken)
      .then((ps) => {
        if (!vigente) return
        setPlantillas(ps)
        setElegida((actual) => (ps.some((p) => p.id === actual) ? actual : (ps[0]?.id ?? "")))
      })
      .catch((e) => vigente && setErrorLista(String(e)))
      .finally(() => vigente && setCargando(false))
    return () => {
      vigente = false
    }
  }, [comisionId, getToken])

  async function guardar() {
    const limpio = nombre.trim()
    if (limpio === "") return
    setGuardando(true)
    setGuardada(false)
    setErrorGuardar(null)
    try {
      const nueva = await guardarPlantillaCampus(comisionId, limpio, getToken)
      setPlantillas((ps) => [...ps, nueva])
      setElegida((actual) => actual || nueva.id)
      setNombre("")
      setGuardada(true)
    } catch (e) {
      setErrorGuardar(String(e))
    } finally {
      setGuardando(false)
    }
  }

  async function aplicar() {
    if (!elegida) return
    setAplicando(true)
    setResultado(null)
    setErrorAplicar(null)
    try {
      const r = await aplicarPlantillaCampus(elegida, comisionId, getToken)
      setResultado(r)
      onAplicada()
    } catch (e) {
      setErrorAplicar(String(e))
    } finally {
      setAplicando(false)
    }
  }

  return (
    <section className="space-y-4 rounded-lg border border-border bg-surface p-4">
      <div>
        <h2 className="text-base font-semibold text-ink">Plantillas</h2>
        <p className="text-sm text-muted">
          Guarda este campus para reusarlo en otra comision de la materia, o aplica una plantilla
          aca. No se pisa nada que ya exista y los TPs llegan en borrador, sin fechas. Para copiar
          este campus a otra comision, cambia de comision con el selector de arriba y aplica la
          plantilla alla.
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="campus-plantilla-nombre" className="text-xs text-muted">
          Nombre de la plantilla
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <input
            id="campus-plantilla-nombre"
            type="text"
            maxLength={200}
            className="block w-full max-w-sm rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink"
            value={nombre}
            onChange={(e) => {
              setNombre(e.target.value)
              setGuardada(false)
            }}
          />
          <button
            type="button"
            className={BOTON_PRIMARIO}
            disabled={nombre.trim() === "" || guardando}
            onClick={guardar}
          >
            Guardar como plantilla
          </button>
          {guardada && <span className="text-sm text-success">Plantilla guardada</span>}
        </div>
        {errorGuardar && <AvisoError titulo="No se pudo guardar." msg={errorGuardar} />}
      </div>

      <div className="space-y-2">
        {errorLista && (
          <AvisoError titulo="No se pudieron cargar las plantillas." msg={errorLista} />
        )}
        {!cargando && !errorLista && plantillas.length === 0 && (
          <p className="text-sm text-muted">Todavía no hay plantillas de esta materia</p>
        )}
        {plantillas.length > 0 && (
          <>
            <label htmlFor="campus-plantilla-aplicar" className="text-xs text-muted">
              Plantilla para aplicar
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <select
                id="campus-plantilla-aplicar"
                className="block w-full max-w-sm rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink"
                value={elegida}
                onChange={(e) => {
                  setElegida(e.target.value)
                  setResultado(null)
                  setErrorAplicar(null)
                }}
              >
                {plantillas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className={BOTON_PRIMARIO}
                disabled={!elegida || aplicando}
                onClick={aplicar}
              >
                Aplicar plantilla
              </button>
            </div>
          </>
        )}
        {resultado && (
          <div className="space-y-1 rounded-lg border border-border-soft bg-surface-alt px-3 py-2 text-sm text-ink">
            <p>{resumenAplicacion(resultado)}</p>
            {resultado.unidades_omitidas.length > 0 && (
              <p>{`Ya existían y no se tocaron: ${resultado.unidades_omitidas.join(", ")}.`}</p>
            )}
            {resultado.bienvenida_aplicada && <p>También se cargó la bienvenida.</p>}
            {aplicacionSinCambios(resultado) && (
              <p className="font-medium">
                No cambió nada: esta comisión ya tiene todo lo que trae la plantilla. Si la
                guardaste desde esta misma comisión, cambiá a otra comisión de la materia con el
                selector de arriba y aplicala ahí.
              </p>
            )}
          </div>
        )}
        {errorAplicar && <AvisoError titulo="No se pudo aplicar." msg={errorAplicar} />}
      </div>
    </section>
  )
}

export function CampusView({ comisionId, getToken }: Props) {
  const confirm = useConfirm()

  const [bienvenida, setBienvenida] = useState("")
  const [estadoBienvenida, setEstadoBienvenida] = useState<Estado>({ kind: "idle" })
  const [unidades, setUnidades] = useState<Unidad[]>([])
  const [errorCarga, setErrorCarga] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [editando, setEditando] = useState<Unidad | null>(null)
  const [borrador, setBorrador] = useState<Borrador>({ introduccion: "", fecha: "", resumen: "" })
  const [estadoUnidad, setEstadoUnidad] = useState<Estado>({ kind: "idle" })

  const cargar = useCallback(() => {
    setLoading(true)
    setErrorCarga(null)
    Promise.all([getBienvenida(comisionId, getToken), listUnidades(comisionId, getToken)])
      .then(([b, u]) => {
        setBienvenida(b.html ?? "")
        setUnidades([...u].sort((a, z) => a.orden - z.orden))
      })
      .catch((e) => setErrorCarga(String(e)))
      .finally(() => setLoading(false))
  }, [comisionId, getToken])

  useEffect(() => {
    cargar()
  }, [cargar])

  async function guardarBienvenida() {
    setEstadoBienvenida({ kind: "saving" })
    try {
      await putBienvenida(comisionId, bienvenida === "" ? null : bienvenida, getToken)
      setEstadoBienvenida({ kind: "ok" })
    } catch (e) {
      setEstadoBienvenida({ kind: "error", msg: String(e) })
    }
  }

  function abrirEditor(u: Unidad) {
    setEditando(u)
    setEstadoUnidad({ kind: "idle" })
    setBorrador({
      introduccion: u.introduccion_html ?? "",
      fecha: u.fecha_apertura ?? "",
      resumen: u.descripcion ?? "",
    })
  }

  async function usarEstructura() {
    if (borrador.introduccion.trim() !== "") {
      const ok = await confirm({
        title: "Reemplazar la introduccion",
        message: "La introduccion actual se reemplaza por la estructura sugerida.",
        confirmLabel: "Reemplazar",
        tone: "danger",
      })
      if (!ok) return
    }
    setBorrador((b) => ({ ...b, introduccion: ESTRUCTURA_SUGERIDA }))
  }

  async function guardarUnidad() {
    if (!editando) return
    setEstadoUnidad({ kind: "saving" })
    try {
      const actualizada = await updateUnidad(
        editando.id,
        {
          introduccion_html: borrador.introduccion === "" ? null : borrador.introduccion,
          fecha_apertura: borrador.fecha === "" ? null : borrador.fecha,
          descripcion: borrador.resumen === "" ? null : borrador.resumen,
        },
        getToken,
      )
      setUnidades((us) => us.map((u) => (u.id === actualizada.id ? actualizada : u)))
      setEditando(actualizada)
      setEstadoUnidad({ kind: "ok" })
    } catch (e) {
      setEstadoUnidad({ kind: "error", msg: String(e) })
    }
  }

  return (
    <PageContainer
      title="Campus del curso"
      description="La bienvenida y las unidades que ven tus alumnos al entrar al campus."
      helpContent={helpContent.campus}
    >
      <div className="space-y-8">
        {errorCarga && (
          <div
            role="alert"
            className="rounded-xl border border-danger/30 bg-danger-soft p-4 text-sm text-danger"
          >
            <div className="font-semibold">Error al cargar el campus</div>
            <div className="mt-1 font-mono text-xs break-all">{errorCarga}</div>
          </div>
        )}

        <section className="space-y-3 rounded-lg border border-border bg-surface p-4">
          <h2 className="text-base font-semibold text-ink">Bienvenida del curso</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-1">
              <label htmlFor="campus-bienvenida" className="text-xs text-muted">
                HTML de la bienvenida
              </label>
              <textarea
                id="campus-bienvenida"
                className={AREA}
                spellCheck={false}
                value={bienvenida}
                disabled={loading}
                onChange={(e) => {
                  setBienvenida(e.target.value)
                  setEstadoBienvenida({ kind: "idle" })
                }}
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs text-muted">Vista previa</span>
              <HtmlAislado html={bienvenida} titulo="Vista previa de la bienvenida" />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className={BOTON_PRIMARIO}
              disabled={estadoBienvenida.kind === "saving"}
              onClick={guardarBienvenida}
            >
              Guardar bienvenida
            </button>
            <AvisoEstado estado={estadoBienvenida} />
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="text-base font-semibold text-ink">Unidades</h2>
          {loading && <p className="text-sm text-muted">Cargando unidades...</p>}
          {!loading && unidades.length === 0 && !errorCarga && (
            <p className="text-sm text-muted">
              Esta comision todavia no tiene unidades.{" "}
              <Link
                to="/unidades"
                search={{ comisionId }}
                className="font-medium text-ink underline hover:no-underline"
              >
                Crealas en la seccion Unidades
              </Link>{" "}
              y volve aca: con Editar le escribis la introduccion a cada una o le cargas la
              estructura sugerida.
            </p>
          )}
          {!loading && unidades.length > 0 && (
            <p className="text-sm text-muted">
              Toca Editar en una unidad para escribir su introduccion, ponerle fecha de apertura o
              cargarle la estructura sugerida (7 secciones).
            </p>
          )}
          <ul className="divide-y divide-border-soft rounded-lg border border-border bg-surface">
            {unidades.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center justify-between gap-3 p-3">
                <div className="min-w-0">
                  <div className="font-medium text-ink">{u.nombre}</div>
                  <div className="text-xs text-muted">{textoApertura(u.fecha_apertura)}</div>
                  {u.descripcion && (
                    <div className="mt-1 text-sm text-body line-clamp-2">{u.descripcion}</div>
                  )}
                </div>
                <button
                  type="button"
                  aria-label={`Editar ${u.nombre}`}
                  className={BOTON_SECUNDARIO}
                  onClick={() => abrirEditor(u)}
                >
                  Editar
                </button>
              </li>
            ))}
          </ul>

          {editando && (
            <div className="space-y-4 rounded-lg border border-border-strong bg-surface p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold text-ink">{editando.nombre}</h3>
                <button type="button" className={BOTON_SECUNDARIO} onClick={usarEstructura}>
                  Usar estructura sugerida
                </button>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-1">
                  <label htmlFor="campus-introduccion" className="text-xs text-muted">
                    HTML de la introduccion
                  </label>
                  <textarea
                    id="campus-introduccion"
                    className={AREA}
                    spellCheck={false}
                    value={borrador.introduccion}
                    onChange={(e) => {
                      const v = e.target.value
                      setBorrador((b) => ({ ...b, introduccion: v }))
                      setEstadoUnidad({ kind: "idle" })
                    }}
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-xs text-muted">Vista previa</span>
                  <HtmlAislado html={borrador.introduccion} titulo="Vista previa" />
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-[12rem_1fr]">
                <div className="space-y-1">
                  <label htmlFor="campus-fecha" className="text-xs text-muted">
                    Fecha de apertura
                  </label>
                  <input
                    id="campus-fecha"
                    type="date"
                    className="block w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink"
                    value={borrador.fecha}
                    onChange={(e) => {
                      const v = e.target.value
                      setBorrador((b) => ({ ...b, fecha: v }))
                      setEstadoUnidad({ kind: "idle" })
                    }}
                  />
                  <p className="text-xs text-muted">Sin fecha, la unidad queda abierta.</p>
                </div>
                <div className="space-y-1">
                  <label htmlFor="campus-resumen" className="text-xs text-muted">
                    Resumen de la tarjeta
                  </label>
                  <textarea
                    id="campus-resumen"
                    rows={3}
                    className="block w-full rounded-lg border border-border bg-surface p-3 text-sm text-ink"
                    value={borrador.resumen}
                    onChange={(e) => {
                      const v = e.target.value
                      setBorrador((b) => ({ ...b, resumen: v }))
                      setEstadoUnidad({ kind: "idle" })
                    }}
                  />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className={BOTON_PRIMARIO}
                  disabled={estadoUnidad.kind === "saving"}
                  onClick={guardarUnidad}
                >
                  Guardar unidad
                </button>
                <button
                  type="button"
                  className={BOTON_SECUNDARIO}
                  onClick={() => setEditando(null)}
                >
                  Cerrar
                </button>
                <AvisoEstado estado={estadoUnidad} />
              </div>
            </div>
          )}
        </section>

        <SeccionPlantillas comisionId={comisionId} getToken={getToken} onAplicada={cargar} />
      </div>
    </PageContainer>
  )
}
