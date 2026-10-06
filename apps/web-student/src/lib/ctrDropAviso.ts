/**
 * Mensaje visible para el alumno cuando el CTRClient descarta un evento
 * (dead-letter) — ver `@platform/ctr-client`.
 *
 * El modulo del CTRClient ya documenta el dead-letter como "nunca en
 * silencio" (`onDrop` siempre se invoca), pero hasta ahora el callback
 * cableado en `EpisodePage.tsx` solo logueaba a consola — nada que el alumno
 * pudiera ver. Esta funcion decide QUE mostrarle, si corresponde mostrarle
 * algo.
 *
 * LA LIMITACION QUE ESTO DECLARA (no se inventa un `DropReason` nuevo sin
 * autorizacion — cambiar ese tipo cambia el contrato de la libreria)
 * --------------------------------------------------------------------------
 * `DropReason` es `"rejected" | "exhausted"` y no alcanza para distinguir
 * "se vencio la sesion" de "el evento era invalido":
 *
 *  - "rejected" = rechazo de NEGOCIO inmediato (403 sin permiso, 409 episodio
 *    cerrado, 422 payload invalido). Ninguno de estos es sobre la sesion —
 *    decirle al alumno "volve a entrar" ahi seria un dato falso.
 *  - "exhausted" = se agotaron los reintentos (`maxAttempts`, default 8).
 *    Tras el fix de 401 (sesion vencida es reintentable, ver `index.ts`),
 *    la causa MAS PROBABLE de un agotamiento es una sesion que nunca se
 *    renovo durante la ventana de reintentos (~2 minutos de backoff). Pero
 *    no es la UNICA: una caida de red o un 5xx persistente por el mismo
 *    lapso tambien terminan en "exhausted", y el CTRClient no guarda que
 *    status HTTP vio en el ultimo intento. El aviso de abajo es por lo tanto
 *    una aproximacion declarada, no una certeza — reportado al orquestador.
 *
 * Por eso el aviso se muestra SOLO ante "exhausted" (nunca ante "rejected"),
 * con un texto que no asegura la causa exacta pero tampoco miente: no le dice
 * al alumno que perdio su codigo (el borrador local lo cubre — ver
 * `cascadaCodigo.ts`), le dice que no se pudo REGISTRAR el cambio.
 */
import type { DropReason } from "@platform/ctr-client"

export function mensajeAvisoDescartado(reason: DropReason): string | null {
  if (reason !== "exhausted") return null
  return (
    "Se venció tu sesión y no pudimos registrar tus últimos cambios. " +
    "Tu código está a salvo en este dispositivo — volvé a entrar para que se registre."
  )
}
