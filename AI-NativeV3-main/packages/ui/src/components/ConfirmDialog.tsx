import { type ReactNode, createContext, useCallback, useContext, useState } from "react"
import { Button } from "./Button"
import { Modal } from "./Modal"

/*
 * Confirmacion destructiva consistente para todo el DS (FR-9).
 * Reemplaza la mezcla de `window.confirm` nativo + modales ad-hoc por un
 * unico dialogo basado en el `Modal` del DS. API imperativa basada en promesa:
 *
 *   const confirm = useConfirm()
 *   const handleDelete = async (x) => {
 *     if (!(await confirm({ message: "...", tone: "danger" }))) return
 *     deleteMutation.mutate(x.id)
 *   }
 *
 * El provider (`ConfirmProvider`) se monta una sola vez en la raiz de la app
 * y renderiza un unico Modal reutilizado por todos los call-sites.
 */

export interface ConfirmOptions {
  /** Titulo del dialogo. Default: "Confirmar accion". */
  title?: string
  /** Cuerpo del dialogo. Acepta texto (con saltos de linea) o JSX. */
  message: ReactNode
  /** Texto del boton de confirmacion. Default: "Confirmar". */
  confirmLabel?: string
  /** Texto del boton de cancelacion. Default: "Cancelar". */
  cancelLabel?: string
  /** `danger` pinta el boton de confirmacion como accion destructiva. Default: "default". */
  tone?: "danger" | "default"
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<ConfirmFn | null>(null)

interface PendingConfirm {
  options: ConfirmOptions
  resolve: (value: boolean) => void
}

export function ConfirmProvider({ children }: { children: ReactNode }): ReactNode {
  const [pending, setPending] = useState<PendingConfirm | null>(null)

  const confirm = useCallback<ConfirmFn>(
    (options) =>
      new Promise<boolean>((resolve) => {
        setPending({ options, resolve })
      }),
    [],
  )

  const settle = useCallback((result: boolean) => {
    setPending((current) => {
      current?.resolve(result)
      return null
    })
  }, [])

  const options = pending?.options
  const tone = options?.tone ?? "default"

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        isOpen={pending !== null}
        onClose={() => settle(false)}
        title={options?.title ?? "Confirmar accion"}
        size="sm"
      >
        <div className="space-y-6">
          <div className="text-sm text-body whitespace-pre-line">{options?.message}</div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => settle(false)}>
              {options?.cancelLabel ?? "Cancelar"}
            </Button>
            {/* autoFocus mueve el foco al CTA al abrir; Escape/backdrop cancelan. */}
            <Button
              variant={tone === "danger" ? "danger" : "primary"}
              onClick={() => settle(true)}
              autoFocus
            >
              {options?.confirmLabel ?? "Confirmar"}
            </Button>
          </div>
        </div>
      </Modal>
    </ConfirmContext.Provider>
  )
}

/**
 * Devuelve una funcion `confirm(options) => Promise<boolean>`.
 * Debe usarse dentro de un `<ConfirmProvider>`.
 */
export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error("useConfirm debe usarse dentro de <ConfirmProvider>")
  return ctx
}
