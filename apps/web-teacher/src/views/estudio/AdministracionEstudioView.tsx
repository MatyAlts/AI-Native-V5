/**
 * Administracion del estudio de codificacion, solo para el investigador (change
 * cibse-codificacion-ciega; design D3, D6, D8, D11, D12, D14).
 *
 * El control de acceso real lo hace classifier-service (membresia con rol
 * investigador). Esta vista igual no se renderiza para otro rol: a un codificador
 * no se le muestra ni se le pide nada.
 *
 * Archivos (muestra, enunciados): se suben CRUDOS, el `File` tal cual. El servidor
 * calcula el sha256 sobre esos bytes; decodificar en el navegador podria quitar un
 * BOM o cambiar saltos de linea y romper la comparacion con el hash esperado.
 *
 * Los enunciados se revisan uno por uno viendo el texto ORIGINAL y sus alertas:
 * el sistema no puede saber si un texto nombra docentes, comisiones o fechas, y
 * mientras falte o quede sin revisar alguno de la muestra la codificacion de todo
 * el estudio queda bloqueada (D14).
 */
import { useConfirm } from "@platform/ui"
import { type ReactNode, useCallback, useEffect, useId, useState } from "react"
import {
  type Ancla,
  type AnclaInvalida,
  type ContenidoExportacion,
  type Enunciado,
  type EstadoEnunciados,
  type FormatoExportacion,
  type MembresiaGestion,
  type ProgresoCodificador,
  type ResultadoCargaEnunciados,
  type RolEstudio,
  type TokenGetter,
  type UsoAncla,
  type VersionResumen,
  estudioApi,
} from "../../lib/estudioApi"
import { mensajeDeErrorEstudio } from "./mensajesError"

interface Props {
  clave: string
  rol: RolEstudio | string
  getToken: TokenGetter
}

export function AdministracionEstudioView({ clave, rol, getToken }: Props) {
  if (rol !== "investigador") return null
  return <Administracion clave={clave} getToken={getToken} />
}

function leerTexto(archivo: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const lector = new FileReader()
    lector.onload = () => resolve(String(lector.result ?? ""))
    lector.onerror = () => reject(lector.error)
    lector.readAsText(archivo)
  })
}

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  const id = useId()
  return (
    <section
      aria-labelledby={id}
      className="rounded-lg border border-border bg-white p-4 space-y-3"
    >
      <h3 id={id} className="text-sm font-semibold text-ink">
        {titulo}
      </h3>
      {children}
    </section>
  )
}

function Alerta({ mensaje }: { mensaje: string | null }) {
  if (!mensaje) return null
  return (
    <p role="alert" className="text-sm text-danger">
      {mensaje}
    </p>
  )
}

const BOTON = "rounded border border-border px-3 py-1.5 text-sm hover:bg-canvas disabled:opacity-50"
const BOTON_PRIMARIO =
  "rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
const CAMPO = "rounded border border-border p-1.5 text-sm"

function Administracion({ clave, getToken }: { clave: string; getToken: TokenGetter }) {
  const [versiones, setVersiones] = useState<VersionResumen[] | null>(null)
  const [errorVersiones, setErrorVersiones] = useState<string | null>(null)

  const cargarVersiones = useCallback(async () => {
    try {
      setVersiones(await estudioApi.listarVersiones(clave, getToken))
      setErrorVersiones(null)
    } catch (e) {
      setErrorVersiones(mensajeDeErrorEstudio(e))
    }
  }, [clave, getToken])

  useEffect(() => {
    void cargarVersiones()
  }, [cargarVersiones])

  const vigente = versiones?.find((v) => v.vigente) ?? null

  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold text-ink">Administración del estudio</h2>
      <p className="text-sm text-muted">
        Estudio <span className="font-mono">{clave}</span>. Vos cargás la muestra, los enunciados,
        el codebook y las anclas, y exportás los resultados. No podés codificar en este estudio.
      </p>
      <Progreso clave={clave} getToken={getToken} />
      <Membresias clave={clave} getToken={getToken} />
      <Codebook
        clave={clave}
        getToken={getToken}
        versiones={versiones}
        error={errorVersiones}
        onCambio={cargarVersiones}
      />
      {vigente && <Anclas clave={clave} version={vigente} getToken={getToken} />}
      <Muestra clave={clave} getToken={getToken} />
      <Enunciados clave={clave} getToken={getToken} />
      <Exportacion clave={clave} getToken={getToken} />
    </div>
  )
}

// ── Progreso ──────────────────────────────────────────────────────────

function Progreso({ clave, getToken }: { clave: string; getToken: TokenGetter }) {
  const [filas, setFilas] = useState<ProgresoCodificador[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelado = false
    estudioApi.progreso(clave, getToken).then(
      (p) => {
        if (!cancelado) setFilas(p)
      },
      (e: unknown) => {
        if (!cancelado) setError(mensajeDeErrorEstudio(e))
      },
    )
    return () => {
      cancelado = true
    }
  }, [clave, getToken])
  return (
    <Seccion titulo="Progreso">
      <Alerta mensaje={error} />
      {filas && filas.length === 0 && (
        <p className="text-sm text-muted">Todavía no hay codificadores asignados.</p>
      )}
      {filas && filas.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-xs text-muted">
            <tr>
              <th className="text-left font-medium py-1">Codificador</th>
              <th className="text-right font-medium">Completos</th>
              <th className="text-right font-medium">Parciales</th>
              <th className="text-right font-medium">Con régimen propuesto</th>
              <th className="text-left font-medium pl-4">Estado</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr
                key={f.alias}
                data-testid={`progreso-${f.alias}`}
                className="border-t border-border"
              >
                <td className="py-1 font-mono">{f.alias}</td>
                <td className="text-right tabular-nums">{f.completos}</td>
                <td className="text-right tabular-nums">{f.parciales}</td>
                <td className="text-right tabular-nums">{f.con_regimen_propuesto}</td>
                <td className="pl-4">
                  {f.revocada ? "revocada" : f.cerrada ? "cerrada" : "en curso"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Seccion>
  )
}

// ── Membresias ────────────────────────────────────────────────────────

function Membresias({ clave, getToken }: { clave: string; getToken: TokenGetter }) {
  const confirm = useConfirm()
  const [membresias, setMembresias] = useState<MembresiaGestion[] | null>(null)
  const [email, setEmail] = useState("")
  const [rol, setRol] = useState<RolEstudio>("codificador")
  const [mensaje, setMensaje] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const idEmail = useId()
  const idRol = useId()

  const cargar = useCallback(async () => {
    try {
      setMembresias(await estudioApi.listarMembresias(clave, getToken))
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }, [clave, getToken])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const asignar = async () => {
    setError(null)
    setMensaje(null)
    try {
      await estudioApi.asignarMembresia(clave, { email: email.trim(), rol }, getToken)
      setMensaje("Membresía asignada.")
      setEmail("")
      await cargar()
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }

  // Por id (contrato del backend): el email no viaja en la URL ni en el cuerpo.
  const revocar = async (m: MembresiaGestion) => {
    setError(null)
    setMensaje(null)
    const ok = await confirm({
      title: `Revocar ${m.alias}`,
      message:
        "La persona deja de tener acceso al estudio. Sus etiquetas se conservan y se exportan con la fecha de revocación.",
      tone: "danger",
    })
    if (!ok) return
    try {
      await estudioApi.revocarMembresia(clave, m.membresia_id, getToken)
      setMensaje(`Membresía ${m.alias} revocada.`)
      await cargar()
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }

  return (
    <Seccion titulo="Membresías">
      {membresias && membresias.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-xs text-muted">
            <tr>
              <th className="text-left font-medium py-1">Email</th>
              <th className="text-left font-medium">Rol</th>
              <th className="text-left font-medium">Alias</th>
              <th className="text-left font-medium">Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {membresias.map((m) => (
              <tr
                key={m.membresia_id}
                data-testid={`membresia-${m.membresia_id}`}
                className="border-t border-border"
              >
                <td className="py-1">{m.email}</td>
                <td>{m.rol}</td>
                <td className="font-mono">{m.alias}</td>
                <td>{m.estado}</td>
                <td className="text-right">
                  {m.estado !== "revocada" && (
                    <button type="button" className={BOTON} onClick={() => void revocar(m)}>
                      {`Revocar ${m.alias}`}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor={idEmail} className="block text-xs text-muted">
            Email
          </label>
          <input
            id={idEmail}
            type="email"
            className={CAMPO}
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
          />
        </div>
        <div>
          <label htmlFor={idRol} className="block text-xs text-muted">
            Rol
          </label>
          <select
            id={idRol}
            className={CAMPO}
            value={rol}
            onChange={(ev) => setRol(ev.target.value as RolEstudio)}
          >
            <option value="codificador">codificador</option>
            <option value="investigador">investigador</option>
          </select>
        </div>
        <button
          type="button"
          className={BOTON_PRIMARIO}
          disabled={email.trim() === ""}
          onClick={() => void asignar()}
        >
          Asignar
        </button>
      </div>
      {mensaje && <p className="text-sm text-ink">{mensaje}</p>}
      <Alerta mensaje={error} />
    </Seccion>
  )
}

// ── Codebook ──────────────────────────────────────────────────────────

function Codebook({
  clave,
  getToken,
  versiones,
  error,
  onCambio,
}: {
  clave: string
  getToken: TokenGetter
  versiones: VersionResumen[] | null
  error: string | null
  onCambio: () => Promise<void>
}) {
  const confirm = useConfirm()
  const [md, setMd] = useState<File | null>(null)
  const [esquema, setEsquema] = useState<File | null>(null)
  const [nueva, setNueva] = useState("")
  const [clonarDe, setClonarDe] = useState("")
  const [errorAccion, setErrorAccion] = useState<string | null>(null)
  const [mensaje, setMensaje] = useState<string | null>(null)
  const [avisoAnclas, setAvisoAnclas] = useState<string | null>(null)
  const idMd = useId()
  const idEsquema = useId()
  const idNueva = useId()
  const idClonar = useId()

  const borrador =
    versiones?.find((v) => v.estado === "borrador" && v.vigente) ??
    versiones?.find((v) => v.estado === "borrador") ??
    null

  const accion = async (fn: () => Promise<unknown>, ok: string) => {
    setErrorAccion(null)
    setMensaje(null)
    try {
      await fn()
      setMensaje(ok)
      await onCambio()
    } catch (e) {
      setErrorAccion(mensajeDeErrorEstudio(e))
    }
  }

  const guardarBorrador = async (etiqueta: string) => {
    setErrorAccion(null)
    setMensaje(null)
    setAvisoAnclas(null)
    if (!md || !esquema) {
      setErrorAccion("Elegí el archivo del codebook y el del esquema.")
      return
    }
    const [texto, crudoEsquema] = await Promise.all([leerTexto(md), leerTexto(esquema)])
    let esquemaJson: unknown
    try {
      esquemaJson = JSON.parse(crudoEsquema)
    } catch {
      setErrorAccion("El archivo del esquema no es JSON válido.")
      return
    }
    await accion(async () => {
      const v = await estudioApi.editarVersion(
        clave,
        etiqueta,
        { contenido_md: texto, esquema: esquemaJson },
        getToken,
      )
      setAvisoAnclas(avisoDeAnclas(v.anclas_invalidas ?? []))
    }, `Borrador ${etiqueta} guardado.`)
  }

  const congelar = async (etiqueta: string) => {
    const ok = await confirm({
      title: `Congelar ${etiqueta}`,
      message:
        "Una versión congelada no se puede editar ni borrar, ni tampoco sus anclas. Se registra su sha256. Para cambiar algo después hay que crear otra versión.",
    })
    if (!ok) return
    await accion(
      () => estudioApi.congelarVersion(clave, etiqueta, getToken),
      `${etiqueta} congelada.`,
    )
  }

  return (
    <Seccion titulo="Codebook">
      <Alerta mensaje={error} />
      {versiones && versiones.length === 0 && (
        <p className="text-sm text-muted">Todavía no hay versiones del codebook.</p>
      )}
      {versiones && versiones.length > 0 && (
        <ul className="space-y-1 text-sm">
          {versiones.map((v) => (
            <li key={v.etiqueta} className="flex flex-wrap items-center gap-2">
              <span className="text-ink">
                {`${v.etiqueta} · ${v.estado}${v.vigente ? " · vigente" : ""}`}
              </span>
              {v.contenido_sha256 && (
                <span className="font-mono text-xs text-muted" title={v.contenido_sha256}>
                  {`${v.contenido_sha256.slice(0, 12)}…`}
                </span>
              )}
              {!v.vigente && (
                <button
                  type="button"
                  className={BOTON}
                  onClick={() =>
                    void accion(
                      () => estudioApi.fijarVigente(clave, v.etiqueta, getToken),
                      `${v.etiqueta} es la vigente.`,
                    )
                  }
                >
                  {`Fijar ${v.etiqueta} como vigente`}
                </button>
              )}
              {v.estado === "borrador" && (
                <button type="button" className={BOTON} onClick={() => void congelar(v.etiqueta)}>
                  {`Congelar ${v.etiqueta}`}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor={idNueva} className="block text-xs text-muted">
            Nueva versión
          </label>
          <input
            id={idNueva}
            className={CAMPO}
            value={nueva}
            placeholder="v1"
            onChange={(ev) => setNueva(ev.target.value)}
          />
        </div>
        <div>
          <label htmlFor={idClonar} className="block text-xs text-muted">
            Clonar de
          </label>
          <select
            id={idClonar}
            className={CAMPO}
            value={clonarDe}
            onChange={(ev) => setClonarDe(ev.target.value)}
          >
            <option value="">Vacía</option>
            {versiones?.map((v) => (
              <option key={v.etiqueta} value={v.etiqueta}>
                {v.etiqueta}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className={BOTON}
          disabled={nueva.trim() === ""}
          onClick={() =>
            void accion(
              () =>
                estudioApi.crearVersion(
                  clave,
                  { etiqueta: nueva.trim(), clonar_de: clonarDe === "" ? null : clonarDe },
                  getToken,
                ),
              `Versión ${nueva.trim()} creada en borrador.`,
            )
          }
        >
          Crear versión
        </button>
      </div>

      {borrador && (
        <div className="space-y-2 border-t border-border pt-3">
          <p className="text-xs text-muted">
            {`Cargar texto y esquema en el borrador ${borrador.etiqueta}. El esquema se valida contra el meta-esquema al guardar.`}
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor={idMd} className="block text-xs text-muted">
                Texto del codebook (.md)
              </label>
              <input
                id={idMd}
                type="file"
                accept=".md,text/markdown"
                className="text-sm"
                onChange={(ev) => setMd(ev.target.files?.[0] ?? null)}
              />
            </div>
            <div>
              <label htmlFor={idEsquema} className="block text-xs text-muted">
                Esquema del formulario (.json)
              </label>
              <input
                id={idEsquema}
                type="file"
                accept=".json,application/json"
                className="text-sm"
                onChange={(ev) => setEsquema(ev.target.files?.[0] ?? null)}
              />
            </div>
            <button
              type="button"
              className={BOTON_PRIMARIO}
              onClick={() => void guardarBorrador(borrador.etiqueta)}
            >
              {`Guardar borrador ${borrador.etiqueta}`}
            </button>
          </div>
        </div>
      )}
      {mensaje && <p className="text-sm text-ink">{mensaje}</p>}
      {avisoAnclas && (
        <p className="rounded border border-border bg-warning-soft p-2 text-sm text-ink">
          {avisoAnclas}
        </p>
      )}
      <Alerta mensaje={errorAccion} />
    </Seccion>
  )
}

/**
 * Aviso del PUT del borrador (verify-1, F1): el esquema se guardo, pero estas
 * anclas ya no valen contra el y congelar las va a rechazar con 422.
 */
function avisoDeAnclas(invalidas: AnclaInvalida[]): string | null {
  if (invalidas.length === 0) return null
  const cuantas =
    invalidas.length === 1
      ? "1 ancla no vale contra el esquema nuevo"
      : `${invalidas.length} anclas no valen contra el esquema nuevo`
  const detalle = invalidas
    .map((a) => `${USO[a.uso] ?? a.uso} ${a.orden}: ${a.motivos.join("; ")}`)
    .join(" · ")
  return `Atención: ${cuantas}; mientras no se corrija, la versión no se puede congelar. ${detalle}`
}

// ── Anclas ────────────────────────────────────────────────────────────

const USO: Record<UsoAncla, string> = { ejemplo: "ejemplo", practica: "práctica" }

function Anclas({
  clave,
  version,
  getToken,
}: {
  clave: string
  version: VersionResumen
  getToken: TokenGetter
}) {
  const [anclas, setAnclas] = useState<Ancla[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [avisoIncompleta, setAvisoIncompleta] = useState<string | null>(null)
  const [form, setForm] = useState({
    episode_id: "",
    uso: "practica" as UsoAncla,
    orden: "1",
    respuesta: "",
    explicacion: "",
    consensuado: "",
  })
  const editable = version.estado === "borrador"
  const ids = {
    episodio: useId(),
    uso: useId(),
    orden: useId(),
    respuesta: useId(),
    explicacion: useId(),
    consensuado: useId(),
  }

  const cargar = useCallback(async () => {
    try {
      setAnclas(await estudioApi.anclas(clave, version.etiqueta, getToken))
      setError(null)
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }, [clave, version.etiqueta, getToken])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const crear = async () => {
    setError(null)
    setAvisoIncompleta(null)
    let respuesta: unknown
    try {
      respuesta = JSON.parse(form.respuesta)
    } catch {
      setError("La respuesta esperada no es JSON válido.")
      return
    }
    try {
      const creada = await estudioApi.crearAncla(
        clave,
        version.etiqueta,
        {
          episode_id: form.episode_id.trim(),
          uso: form.uso,
          orden: Number(form.orden),
          respuesta_esperada: respuesta as Ancla["respuesta_esperada"],
          explicacion_md: form.explicacion,
          consensuado_por: form.consensuado,
        },
        getToken,
      )
      const faltan = creada.faltantes ?? []
      if (faltan.length > 0) {
        setAvisoIncompleta(
          `El ancla se guardó, pero quedó incompleta (falta: ${faltan.join(", ")}). Completala antes de congelar la versión: congelar la rechaza.`,
        )
      }
      await cargar()
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }

  const borrar = async (itemId: string) => {
    setError(null)
    try {
      await estudioApi.borrarAncla(clave, version.etiqueta, itemId, getToken)
      await cargar()
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }

  return (
    <Seccion titulo="Anclas">
      <p className="text-xs text-muted">
        {`Anclas de la versión vigente ${version.etiqueta} (${version.estado}). Un ancla se ve en el entrenamiento solo con sus enunciados cargados y revisados.`}
      </p>
      {anclas && anclas.length === 0 && <p className="text-sm text-muted">Sin anclas.</p>}
      {anclas && anclas.length > 0 && (
        <ul className="space-y-1 text-sm">
          {anclas.map((a) => (
            <li key={a.item_id} data-testid={`ancla-${a.item_id}`} className="flex flex-wrap gap-2">
              <span className="tabular-nums">{a.orden}.</span>
              <span>{USO[a.uso]}</span>
              <span className="font-mono text-xs text-muted">{a.episode_id}</span>
              <span className={a.enunciados_listos ? "text-muted" : "text-danger"}>
                {a.enunciados_listos ? "enunciados revisados" : "enunciado pendiente"}
              </span>
              {editable && (
                <button type="button" className={BOTON} onClick={() => void borrar(a.item_id)}>
                  Borrar
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && (
        <div className="grid grid-cols-1 gap-2 border-t border-border pt-3 md:grid-cols-3">
          <div>
            <label htmlFor={ids.episodio} className="block text-xs text-muted">
              episode_id
            </label>
            <input
              id={ids.episodio}
              className={`${CAMPO} w-full font-mono`}
              value={form.episode_id}
              onChange={(ev) => setForm({ ...form, episode_id: ev.target.value })}
            />
          </div>
          <div>
            <label htmlFor={ids.uso} className="block text-xs text-muted">
              Uso
            </label>
            <select
              id={ids.uso}
              className={CAMPO}
              value={form.uso}
              onChange={(ev) => setForm({ ...form, uso: ev.target.value as UsoAncla })}
            >
              <option value="ejemplo">ejemplo</option>
              <option value="practica">práctica</option>
            </select>
          </div>
          <div>
            <label htmlFor={ids.orden} className="block text-xs text-muted">
              Orden
            </label>
            <input
              id={ids.orden}
              type="number"
              className={CAMPO}
              value={form.orden}
              onChange={(ev) => setForm({ ...form, orden: ev.target.value })}
            />
          </div>
          <div className="md:col-span-3">
            <label htmlFor={ids.respuesta} className="block text-xs text-muted">
              Respuesta esperada (JSON con el formato del formulario: respuestas, regimen, notas…)
            </label>
            <textarea
              id={ids.respuesta}
              rows={4}
              className={`${CAMPO} w-full font-mono`}
              value={form.respuesta}
              onChange={(ev) => setForm({ ...form, respuesta: ev.target.value })}
            />
          </div>
          <div className="md:col-span-2">
            <label htmlFor={ids.explicacion} className="block text-xs text-muted">
              Explicación (Markdown)
            </label>
            <textarea
              id={ids.explicacion}
              rows={2}
              className={`${CAMPO} w-full`}
              value={form.explicacion}
              onChange={(ev) => setForm({ ...form, explicacion: ev.target.value })}
            />
          </div>
          <div>
            <label htmlFor={ids.consensuado} className="block text-xs text-muted">
              Consensuada por
            </label>
            <input
              id={ids.consensuado}
              className={`${CAMPO} w-full`}
              value={form.consensuado}
              onChange={(ev) => setForm({ ...form, consensuado: ev.target.value })}
            />
          </div>
          <div>
            <button type="button" className={BOTON_PRIMARIO} onClick={() => void crear()}>
              Agregar ancla
            </button>
          </div>
        </div>
      )}
      {avisoIncompleta && (
        <p className="rounded border border-border bg-warning-soft p-2 text-sm text-ink">
          {avisoIncompleta}
        </p>
      )}
      <Alerta mensaje={error} />
    </Seccion>
  )
}

// ── Muestra ───────────────────────────────────────────────────────────

function Muestra({ clave, getToken }: { clave: string; getToken: TokenGetter }) {
  const [archivo, setArchivo] = useState<File | null>(null)
  const [sha, setSha] = useState("")
  const [resultado, setResultado] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const idArchivo = useId()
  const idSha = useId()

  const cargar = async () => {
    if (!archivo) return
    setError(null)
    setResultado(null)
    setEnviando(true)
    try {
      const r = await estudioApi.cargarMuestra(
        clave,
        archivo,
        sha.trim() === "" ? null : sha.trim(),
        getToken,
      )
      setResultado(`Muestra cargada: ${r.items} ítems. sha256 ${r.sha256}`)
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Seccion titulo="Muestra">
      <p className="text-xs text-muted">
        Se sube el CSV de origen tal cual. El servidor guarda solo la columna episode_id y el sha256
        del archivo; descarta el resto. Todo o nada. Se puede reemplazar solo mientras no haya
        etiquetas.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor={idArchivo} className="block text-xs text-muted">
            Archivo CSV de la muestra
          </label>
          <input
            id={idArchivo}
            type="file"
            accept=".csv,text/csv"
            className="text-sm"
            onChange={(ev) => setArchivo(ev.target.files?.[0] ?? null)}
          />
        </div>
        <div>
          <label htmlFor={idSha} className="block text-xs text-muted">
            sha256 esperado (opcional)
          </label>
          <input
            id={idSha}
            className={`${CAMPO} w-[34rem] max-w-full font-mono`}
            value={sha}
            onChange={(ev) => setSha(ev.target.value)}
          />
        </div>
        <button
          type="button"
          className={BOTON_PRIMARIO}
          disabled={!archivo || enviando}
          onClick={() => void cargar()}
        >
          Cargar muestra
        </button>
      </div>
      {resultado && <p className="text-sm text-ink break-all">{resultado}</p>}
      <Alerta mensaje={error} />
    </Seccion>
  )
}

// ── Enunciados ────────────────────────────────────────────────────────

function Enunciados({ clave, getToken }: { clave: string; getToken: TokenGetter }) {
  const [estado, setEstado] = useState<EstadoEnunciados | null>(null)
  const [ignoradas, setIgnoradas] = useState<ResultadoCargaEnunciados["ignoradas"]>([])
  const [archivo, setArchivo] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const idArchivo = useId()

  const cargarEstado = useCallback(async () => {
    try {
      setEstado(await estudioApi.enunciados(clave, getToken))
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }, [clave, getToken])

  useEffect(() => {
    void cargarEstado()
  }, [cargarEstado])

  const subir = async () => {
    if (!archivo) return
    setError(null)
    try {
      const r = await estudioApi.cargarEnunciados(clave, archivo, getToken)
      setIgnoradas(r.ignoradas ?? [])
      await cargarEstado()
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }

  const c = estado?.cobertura
  return (
    <Seccion titulo="Enunciados">
      <p className="text-sm text-ink">
        La codificación queda bloqueada para todo el estudio mientras falte o esté sin revisar algún
        enunciado de la muestra. Revisá cada uno viendo el texto: si nombra docentes, comisiones,
        fechas u horarios, guardá una versión editada.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor={idArchivo} className="block text-xs text-muted">
            Archivo CSV de enunciados
          </label>
          <input
            id={idArchivo}
            type="file"
            accept=".csv,text/csv"
            className="text-sm"
            onChange={(ev) => setArchivo(ev.target.files?.[0] ?? null)}
          />
        </div>
        <button
          type="button"
          className={BOTON_PRIMARIO}
          disabled={!archivo}
          onClick={() => void subir()}
        >
          Cargar enunciados
        </button>
      </div>
      <Alerta mensaje={error} />
      {c && (
        <div className="text-sm text-ink space-y-1">
          <p className="tabular-nums">
            {`${c.cargados} de ${c.requeridos} cargados · ${c.revisados} revisados`}
          </p>
          {(c.faltantes.length > 0 || c.sin_revisar.length > 0) && (
            <ul className="list-disc ml-5">
              {c.faltantes.map((f) => (
                <li key={`falta-${f.tipo}-${f.id}`}>
                  {`Falta ${f.tipo} ${f.id} · ${f.items_afectados} ítems afectados`}
                </li>
              ))}
              {c.sin_revisar.map((f) => (
                <li key={`sin-revisar-${f.tipo}-${f.id}`}>
                  {`Sin revisar ${f.tipo} ${f.id} · ${f.items_afectados} ítems afectados`}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {ignoradas.length > 0 && (
        <div className="text-sm text-muted">
          <p>Filas ignoradas (no corresponden a ningún ítem ni ancla):</p>
          <ul className="list-disc ml-5">
            {ignoradas.map((f) => (
              <li key={`${f.tipo}-${f.id}`}>{`${f.tipo} ${f.id}`}</li>
            ))}
          </ul>
        </div>
      )}
      {estado && estado.enunciados.length > 0 && (
        <ul className="space-y-3">
          {estado.enunciados.map((en) => (
            <RevisionEnunciado
              key={en.id}
              clave={clave}
              enunciado={en}
              getToken={getToken}
              onRevisado={cargarEstado}
            />
          ))}
        </ul>
      )}
    </Seccion>
  )
}

function RevisionEnunciado({
  clave,
  enunciado,
  getToken,
  onRevisado,
}: {
  clave: string
  enunciado: Enunciado
  getToken: TokenGetter
  onRevisado: () => Promise<void>
}) {
  const [editado, setEditado] = useState(
    enunciado.contenido_mostrado_md ?? enunciado.contenido_original_md,
  )
  const [error, setError] = useState<string | null>(null)
  const idEditado = useId()

  const revisar = async (contenido: string | null) => {
    setError(null)
    try {
      await estudioApi.revisarEnunciado(
        clave,
        enunciado.id,
        { contenido_mostrado_md: contenido },
        getToken,
      )
      await onRevisado()
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }

  return (
    <li
      data-testid={`enunciado-${enunciado.id}`}
      className="rounded border border-border p-3 space-y-2"
    >
      <p className="text-xs text-muted">
        <span className="font-medium text-ink">{enunciado.tipo === "tp" ? "TP" : "Ejercicio"}</span>{" "}
        <span className="font-mono">{enunciado.fuente_id}</span>
        {" · "}
        {enunciado.revisado ? "Revisado" : "Sin revisar"}
      </p>
      {enunciado.alertas.length > 0 && (
        <p className="text-xs text-danger">Alertas: {enunciado.alertas.join(", ")}</p>
      )}
      <div>
        <p className="text-xs text-muted">Texto original</p>
        <pre className="text-xs bg-canvas p-2 rounded whitespace-pre-wrap">
          {enunciado.contenido_original_md}
        </pre>
      </div>
      {enunciado.revisado ? (
        enunciado.contenido_mostrado_md !== null &&
        enunciado.contenido_mostrado_md !== enunciado.contenido_original_md && (
          <div>
            <p className="text-xs text-muted">Versión mostrada</p>
            <pre className="text-xs bg-canvas p-2 rounded whitespace-pre-wrap">
              {enunciado.contenido_mostrado_md}
            </pre>
          </div>
        )
      ) : (
        <>
          <div>
            <label htmlFor={idEditado} className="block text-xs text-muted">
              Versión a mostrar
            </label>
            <textarea
              id={idEditado}
              rows={4}
              className={`${CAMPO} w-full`}
              value={editado}
              onChange={(ev) => setEditado(ev.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button type="button" className={BOTON} onClick={() => void revisar(null)}>
              Aprobar tal cual
            </button>
            <button
              type="button"
              className={BOTON_PRIMARIO}
              disabled={editado.trim() === ""}
              onClick={() => void revisar(editado)}
            >
              Guardar versión editada
            </button>
          </div>
        </>
      )}
      <Alerta mensaje={error} />
    </li>
  )
}

// ── Exportacion ───────────────────────────────────────────────────────

function Exportacion({ clave, getToken }: { clave: string; getToken: TokenGetter }) {
  const [contenido, setContenido] = useState<ContenidoExportacion>("etiquetas")
  const [formato, setFormato] = useState<FormatoExportacion>("csv")
  const [error, setError] = useState<string | null>(null)
  const idContenido = useId()
  const idFormato = useId()

  const exportar = async () => {
    setError(null)
    try {
      const texto = await estudioApi.exportar(clave, contenido, formato, getToken)
      const tipo = formato === "csv" ? "text/csv" : "application/json"
      const url = URL.createObjectURL(new Blob([texto], { type: `${tipo};charset=utf-8` }))
      const a = document.createElement("a")
      a.href = url
      a.download = `${clave}-${contenido}.${formato}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(mensajeDeErrorEstudio(e))
    }
  }

  return (
    <Seccion titulo="Exportación">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor={idContenido} className="block text-xs text-muted">
            Contenido
          </label>
          <select
            id={idContenido}
            className={CAMPO}
            value={contenido}
            onChange={(ev) => setContenido(ev.target.value as ContenidoExportacion)}
          >
            <option value="etiquetas">etiquetas</option>
            <option value="entrenamiento">entrenamiento</option>
            <option value="historial">historial</option>
          </select>
        </div>
        <div>
          <label htmlFor={idFormato} className="block text-xs text-muted">
            Formato
          </label>
          <select
            id={idFormato}
            className={CAMPO}
            value={formato}
            onChange={(ev) => setFormato(ev.target.value as FormatoExportacion)}
          >
            <option value="csv">CSV</option>
            <option value="json">JSON</option>
          </select>
        </div>
        <button type="button" className={BOTON_PRIMARIO} onClick={() => void exportar()}>
          Exportar
        </button>
      </div>
      <Alerta mensaje={error} />
    </Seccion>
  )
}
