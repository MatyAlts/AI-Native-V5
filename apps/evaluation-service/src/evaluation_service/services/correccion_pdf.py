"""El PDF de devolución de Active-IA (tareas 5.2 y 5.3).

Se baja al cerrar la corrección y se guarda en storage propio. Tres reglas:

1. **Key no adivinable.** Lleva un token random además de los ids. Sin eso,
   alguien con el `correccion_id` construye la key — y si el bucket queda mal
   configurado, eso es un link directo a la devolución de un alumno.
2. **Prefijo y bucket propios.** NUNCA el de materiales, donde hay objetos que
   se sirven a la comisión entera: un permiso pensado para uno alcanzaría al
   otro.
3. **Se sirve por el endpoint, con el gate de comisión.** Sin link público ni
   URL firmada de larga vida: una URL que sobrevive a que el docente cierre la
   sesión es una URL que puede circular.

Si el PDF no se puede bajar, la corrección NO falla: la nota ya existe y es lo
que importa. Queda sin PDF y el endpoint lo dice.
"""

from __future__ import annotations

import secrets
from typing import Any
from uuid import UUID

import structlog
from platform_ops.storage import BaseStorage, build_storage

log = structlog.get_logger()

_storage: BaseStorage | None = None


def get_storage() -> BaseStorage:
    """El storage de PDF de correcciones, con SU bucket.

    Se cachea acá y no en `platform_ops`: un cache compartido devolvería el
    storage del primer servicio que llame, con el bucket del otro.
    """
    global _storage
    if _storage is None:
        _storage = build_storage("S3_BUCKET_CORRECCIONES", "correcciones")
    return _storage


def make_pdf_key(tenant_id: UUID, entrega_id: UUID, correccion_id: UUID) -> str:
    """La key donde va el PDF.

    El sufijo random es lo que la vuelve no adivinable. Los ids solos harían
    que cualquiera que vio un `correccion_id` —que viaja en la URL del
    frontend— pueda construir la ruta del objeto.
    """
    token = secrets.token_urlsafe(16)
    return f"correcciones/{tenant_id}/{entrega_id}/{correccion_id}/{token}.pdf"


async def bajar_y_guardar(
    *,
    cliente: Any,
    tenant_id: UUID,
    entrega_id: UUID,
    correccion_id: UUID,
    external_correccion_id: str,
) -> str | None:
    """Baja el PDF de Active-IA y lo guarda. Devuelve la key, o `None`.

    **Devuelve `None` en vez de levantar**: la nota ya existe y es lo que
    importa. Perder la corrección entera porque no se pudo bajar un PDF sería
    tirar el trabajo que ya se pagó.
    """
    try:
        resp = await cliente.request(
            "GET", f"/documentos/correcciones/{external_correccion_id}/pdf"
        )
    except Exception as e:
        log.warning(
            "activeia_pdf_no_descargado",
            correccion_id=str(correccion_id),
            detalle=f"{type(e).__name__}",
        )
        return None

    if resp.status_code != 200 or not resp.content:
        log.warning(
            "activeia_pdf_no_descargado",
            correccion_id=str(correccion_id),
            status=resp.status_code,
        )
        return None

    key = make_pdf_key(tenant_id, entrega_id, correccion_id)
    try:
        await get_storage().put(key, resp.content, "application/pdf")
    except Exception:
        log.exception("activeia_pdf_no_guardado", correccion_id=str(correccion_id))
        return None

    log.info("activeia_pdf_guardado", correccion_id=str(correccion_id), bytes=len(resp.content))
    return key


async def borrar(pdf_storage_key: str | None) -> bool:
    """Borra el PDF del storage. Idempotente.

    Lo usa el derecho al olvido: si el objeto ya no está, eso es exactamente
    el estado que se quería, no un error.
    """
    if not pdf_storage_key:
        return True
    try:
        await get_storage().delete(pdf_storage_key)
    except Exception:
        log.exception("activeia_pdf_no_borrado", key=pdf_storage_key)
        return False
    return True
