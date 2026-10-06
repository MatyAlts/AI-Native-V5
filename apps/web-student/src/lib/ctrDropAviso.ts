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
 * Por eso el aviso se muestra SOLO ante "exhausted" (nunca ante "rejected"), y
 * su TEXTO no afirma la causa. Las dos cosas que el texto NO puede decir, y no
 * dice:
 *
 *  - "Se vencio tu sesion" seria inventar el motivo con una autoridad que este
 *    modulo no tiene: como dice el parrafo de arriba, una caida de red o un 5xx
 *    persistente producen el mismo "exhausted". Mandar a reloguear a quien solo
 *    perdio el wifi es un dato falso y encima un consejo inutil.
 *  - "Volve a entrar PARA QUE SE REGISTRE" seria prometer algo que no pasa: al
 *    agotar reintentos el CTRClient hace `queue.shift()` ANTES de invocar
 *    `onDrop` (ver `drain()` en `@platform/ctr-client`), asi que ese evento ya
 *    no existe y ninguna reconexion lo trae de vuelta.
 *
 * Lo que SI es cierto es lo que se le dice: el codigo esta a salvo en este
 * dispositivo (`saveArtefactoDraft` es sincronico y corre en el mismo tick del
 * debounce — ver `cascadaCodigo.ts`), y lo que efectivamente vuelve a registrar
 * el trabajo es la PROXIMA edicion, que emite un snapshot nuevo y completo.
 */
import type { DropReason } from "@platform/ctr-client"

export function mensajeAvisoDescartado(reason: DropReason): string | null {
  if (reason !== "exhausted") return null
  return (
    "No pudimos registrar tus últimos cambios en el servidor. " +
    "Tu código está a salvo en este dispositivo: revisá tu conexión y, si el " +
    "problema sigue, volvé a entrar — al seguir escribiendo se registra de nuevo."
  )
}
