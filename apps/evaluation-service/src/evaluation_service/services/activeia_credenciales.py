"""Alta, baja y lectura de las credenciales de Active-IA de cada docente.

**La regla dura de este módulo**: las tres queries filtran por `user_id`
explícito. La RLS de `activeia_credenciales` es sólo por tenant (design D6), y
en producción todos los docentes comparten tenant — o sea que sin ese filtro
un docente leería la credencial de otro y la RLS no lo frenaría.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from uuid import UUID

import structlog
from platform_ops.crypto import CryptoError, decrypt, encrypt
from sqlalchemy import and_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.config import settings
from evaluation_service.models.activeia import ActiveIACredencial
from evaluation_service.services.activeia_client import (
    ActiveIAClient,
    ActiveIAClientMock,
    ActiveIAError,
)

log = structlog.get_logger()


class CredencialNoConfiguradaError(Exception):
    """El docente no conectó su cuenta de Active-IA."""


def _master_key() -> bytes:
    """La master key, o un error que dice qué falta.

    Sin la key no se cifra ni se descifra nada, y decirlo así es mejor que
    fallar más adentro con un error de criptografía que no orienta a nadie.
    """
    if not settings.activeia_master_key:
        raise ActiveIAError(
            "ACTIVEIA_MASTER_KEY no está configurada en este servicio. "
            "Generar con: openssl rand -base64 32"
        )
    try:
        key = base64.b64decode(settings.activeia_master_key, validate=True)
    except Exception as e:
        raise ActiveIAError(f"ACTIVEIA_MASTER_KEY no es base64 válido: {e}") from e
    # El largo se valida ACÁ y no dentro de `encrypt`: `CryptoError` no hereda
    # de `ActiveIAError`, así que el `except` de la ruta no lo agarraba y una
    # key mal formada salía como 500. Y va antes del login real, para no
    # loguearse contra Active-IA y descubrir recién después que no se va a
    # poder cifrar.
    if len(key) != 32:
        raise ActiveIAError(
            f"ACTIVEIA_MASTER_KEY tiene {len(key)} bytes y tiene que tener 32 bytes. "
            "Generar con: openssl rand -base64 32"
        )
    return key


async def obtener_credencial(
    db: AsyncSession, tenant_id: UUID, user_id: UUID
) -> ActiveIACredencial | None:
    """La credencial VIGENTE de este docente. Filtro por `user_id` explícito."""
    stmt = select(ActiveIACredencial).where(
        and_(
            ActiveIACredencial.tenant_id == tenant_id,
            ActiveIACredencial.user_id == user_id,
            ActiveIACredencial.revoked_at.is_(None),
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def guardar_credencial(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    username: str,
    password: str,
) -> ActiveIACredencial:
    """Valida la cuenta con un login REAL y recién ahí la guarda cifrada.

    Guardar primero y validar después dejaría credenciales rotas en la tabla
    que sólo fallan cuando el docente ya está esperando una corrección.
    """
    key = _master_key()

    cliente = ActiveIAClient(
        base_url=settings.activeia_url,
        username=username,
        password=password,
        timeout=settings.activeia_timeout_seconds,
    )
    await cliente.verificar_credenciales()

    # Revocamos la anterior en vez de pisarla: el UNIQUE parcial es sobre las
    # vigentes, y conservar la revocada deja el rastro de que hubo un cambio.
    anterior = await obtener_credencial(db, tenant_id, user_id)
    ahora = datetime.now(UTC)
    if anterior is not None:
        anterior.revoked_at = ahora
        await db.flush()

    cred = ActiveIACredencial(
        tenant_id=tenant_id,
        user_id=user_id,
        username=username,
        encrypted_password=encrypt(password.encode("utf-8"), key),
        last_login_at=ahora,
        last_login_ok=True,
    )
    try:
        db.add(cred)
        await db.flush()
    except IntegrityError as e:
        # Dos clicks en "Conectar". El UNIQUE parcial sobre las vigentes hace
        # que la segunda quede bloqueada en el índice hasta que la primera
        # commitee, y después levante. Sin este catch salía como el 409
        # genérico "Ya existe un registro con esos datos unicos", que para
        # "conectar mi cuenta" no significa nada — y encima la operación le
        # había salido bien.
        await db.rollback()
        await db.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant_id)},
        )
        existente = await obtener_credencial(db, tenant_id, user_id)
        if existente is not None:
            log.info(
                "activeia_credencial_race_resuelta",
                tenant_id=str(tenant_id),
                user_id=str(user_id),
            )
            return existente
        raise ActiveIAError("No se pudo guardar la credencial. Probá de nuevo.") from e

    # El log NO lleva ni el password ni el username: el username de Active-IA
    # suele ser el mail institucional del docente.
    log.info("activeia_credencial_guardada", tenant_id=str(tenant_id), user_id=str(user_id))
    return cred


async def revocar_credencial(db: AsyncSession, tenant_id: UUID, user_id: UUID) -> bool:
    """Desconecta la cuenta. Devuelve False si no había ninguna vigente."""
    cred = await obtener_credencial(db, tenant_id, user_id)
    if cred is None:
        return False
    cred.revoked_at = datetime.now(UTC)
    await db.flush()
    log.info("activeia_credencial_revocada", tenant_id=str(tenant_id), user_id=str(user_id))
    return True


async def cliente_para(db: AsyncSession, tenant_id: UUID, user_id: UUID) -> ActiveIAClient:
    """Arma un cliente con la credencial guardada de este docente.

    Efímero y por docente a propósito: los `comision_id` y `rubrica_id` que
    devuelve Active-IA salen de la cuenta logueada, así que un cliente
    compartido devolvería ids que para este docente no existen.
    """
    cred = await obtener_credencial(db, tenant_id, user_id)
    if cred is None:
        raise CredencialNoConfiguradaError("Este docente no conectó su cuenta de Active-IA.")
    try:
        password = decrypt(bytes(cred.encrypted_password), _master_key()).decode("utf-8")
    except CryptoError as e:
        # Pasa si rotaron la master key sin re-cifrar. Decirlo así evita que
        # se lea como "la contraseña del docente cambió".
        raise ActiveIAError(
            "No se pudo descifrar la credencial guardada. "
            "Si se rotó ACTIVEIA_MASTER_KEY, el docente tiene que reconectar su cuenta."
        ) from e

    # El mock sólo reemplaza la ESCRITURA de rúbricas (hereda el resto): el
    # login y las lecturas siguen yendo contra Active-IA de verdad, así que
    # conectar la cuenta valida contra la API real aunque el flag esté puesto.
    clase = ActiveIAClientMock if settings.activeia_mock_escritura else ActiveIAClient
    return clase(
        base_url=settings.activeia_url,
        username=cred.username,
        password=password,
        timeout=settings.activeia_timeout_seconds,
    )
