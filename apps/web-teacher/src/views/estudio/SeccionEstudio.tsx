/**
 * Marco comun de las dos secciones del estudio (Codificacion y Entrenamiento):
 * resuelve las membresias del usuario y decide que se muestra (design D13).
 *
 *   - cargando / error del servicio: el error queda DENTRO de la seccion; el
 *     resto del panel sigue funcionando (spec estudio-codificacion-acceso,
 *     "Disponibilidad del panel ante fallas del servicio del estudio");
 *   - sin membresia: aviso de que la seccion se usa para el estudio y enlace a
 *     la vista historica del acuerdo del piloto (`/interrater-admin`). No se pide
 *     ningun otro dato del estudio;
 *   - con una o mas membresias: el contenido de la seccion para la elegida.
 */
import { Link } from "@tanstack/react-router"
import { type ReactNode, useEffect, useState } from "react"
import { type Membresia, type TokenGetter, estudioApi } from "../../lib/estudioApi"
import { mensajeDeErrorEstudio } from "./mensajesError"

type Estado =
  | { fase: "cargando" }
  | { fase: "error"; mensaje: string }
  | { fase: "lista"; membresias: Membresia[] }

export function SeccionEstudio({
  getToken,
  children,
}: {
  getToken: TokenGetter
  children: (membresia: Membresia) => ReactNode
}) {
  const [estado, setEstado] = useState<Estado>({ fase: "cargando" })
  const [elegida, setElegida] = useState<string | null>(null)

  useEffect(() => {
    let cancelado = false
    estudioApi.misMembresias(getToken).then(
      (membresias) => {
        if (!cancelado) setEstado({ fase: "lista", membresias })
      },
      (e: unknown) => {
        if (!cancelado) setEstado({ fase: "error", mensaje: mensajeDeErrorEstudio(e) })
      },
    )
    return () => {
      cancelado = true
    }
  }, [getToken])

  if (estado.fase === "cargando") {
    return <p className="text-sm text-muted">Consultando tus estudios de codificación…</p>
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
  if (estado.membresias.length === 0) return <AvisoSinMembresia />

  const membresia =
    estado.membresias.find((m) => m.clave === elegida) ?? (estado.membresias[0] as Membresia)
  return (
    <div className="space-y-4">
      {estado.membresias.length > 1 && (
        <label className="flex items-center gap-2 text-sm">
          Estudio
          <select
            className="rounded border border-border p-1.5 text-sm"
            value={membresia.clave}
            onChange={(ev) => setElegida(ev.target.value)}
          >
            {estado.membresias.map((m) => (
              <option key={m.clave} value={m.clave}>
                {m.titulo}
              </option>
            ))}
          </select>
        </label>
      )}
      {children(membresia)}
    </div>
  )
}

function AvisoSinMembresia() {
  return (
    <div className="rounded-lg border border-border bg-white p-5 text-sm text-ink space-y-2">
      <p>
        Esta sección se usa para un estudio de codificación a ciegas con codificadores asignados. Tu
        cuenta no participa del estudio, así que acá no hay nada para hacer.
      </p>
      <p className="text-muted">
        Los resultados de la codificación del piloto siguen disponibles en{" "}
        <Link to="/interrater-admin" className="underline font-medium hover:opacity-80">
          el acuerdo del piloto
        </Link>
        .
      </p>
    </div>
  )
}
