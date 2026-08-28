"""Endpoints de la cuenta de Active-IA del docente.

    POST   /api/v1/activeia/credenciales   conectar (valida con login real)
    GET    /api/v1/activeia/credenciales   estado de la cuenta conectada
    DELETE /api/v1/activeia/credenciales   desconectar

Ninguna respuesta de este módulo devuelve el password, ni cifrado ni en claro,
ni un fingerprint suyo. Lo único observable es el username, la fecha y si el
último login anduvo.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.auth import User, get_db
from evaluation_service.auth.dependencies import require_correccion_ia
from evaluation_service.config import settings
from evaluation_service.schemas.activeia import (
    CredencialCreate,
    CredencialEstado,
    EjercicioSyncOut,
    SincronizacionOut,
)
from evaluation_service.services.activeia_client import ActiveIAError
from evaluation_service.services.activeia_credenciales import (
    CredencialNoConfiguradaError,
    cliente_para,
    guardar_credencial,
    obtener_credencial,
    revocar_credencial,
)
from evaluation_service.services.activeia_sync import (
    estado_de_sincronizacion,
    sincronizar_tp,
)

# Mismo conjunto que `correccion_ia.py`: coordinacion opera cross-comision a
# proposito, igual que ve toda la cola en `list_entregas`.
_OVERSIGHT = frozenset({"superadmin", "docente_admin"})

router = APIRouter(prefix="/api/v1/activeia", tags=["activeia"])


def _hay_simulacion(estados: list) -> bool:
    """Si hay que mostrar el aviso grande de simulación.

    Mira el FLAG **y** el DATO. Sólo el flag no alcanza: un vínculo `MOCK-`
    persiste en la base a que se apague el simulador, así que apagarlo hacía
    desaparecer el banner y dejaba sólo el "(simulada)" chiquito de la
    columna — sobre rúbricas que siguen sin existir del otro lado.
    """
    return settings.activeia_mock_escritura or any(e.simulado for e in estados)


def _assert_habilitado() -> None:
    """Kill switch. Falla CERRADO: apagado, no se conecta ninguna cuenta."""
    if not settings.activeia_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La corrección asistida está desactivada en este entorno.",
        )


@router.post("/credenciales", response_model=CredencialEstado, status_code=status.HTTP_201_CREATED)
async def conectar_cuenta(
    data: CredencialCreate,
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> CredencialEstado:
    """Conecta la cuenta de Active-IA de ESTE docente.

    Valida con un login real contra Active-IA antes de guardar. Si el login
    falla, el error dice que las credenciales no andan — nunca "no tenés
    rúbricas", que es lo que devolvería validar listando rúbricas y ya
    confundió a un tutor en producción.
    """
    _assert_habilitado()
    try:
        cred = await guardar_credencial(
            db, user.tenant_id, user.id, data.username, data.password.get_secret_value()
        )
    except ActiveIAError as e:
        # 400 y no 500: el caso normal es que el docente se haya equivocado de
        # contraseña. `e.mensaje` está redactado para no repetir lo que mandó.
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if e.es_infraestructura
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=e.mensaje,
        ) from e

    return CredencialEstado(
        conectada=True,
        modo_simulado=settings.activeia_mock_escritura,
        username=cred.username,
        created_at=cred.created_at,
        last_login_at=cred.last_login_at,
        last_login_ok=cred.last_login_ok,
    )


@router.get("/credenciales", response_model=CredencialEstado)
async def estado_cuenta(
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> CredencialEstado:
    """Estado de la cuenta de ESTE docente. 200 con `conectada=false` si no hay.

    No es 404: "no conectaste tu cuenta" es una respuesta legítima que la UI
    necesita para ofrecer el formulario, no un error.
    """
    cred = await obtener_credencial(db, user.tenant_id, user.id)
    if cred is None:
        return CredencialEstado(conectada=False, modo_simulado=settings.activeia_mock_escritura)
    return CredencialEstado(
        conectada=True,
        modo_simulado=settings.activeia_mock_escritura,
        username=cred.username,
        created_at=cred.created_at,
        last_login_at=cred.last_login_at,
        last_login_ok=cred.last_login_ok,
    )


async def _assert_tp_de_mi_comision(db: AsyncSession, tarea_practica_id: UUID, user: User) -> None:
    """El docente sólo opera sobre TPs de SUS comisiones. 404 y no 403.

    Todo el epic se construye sobre que en producción los docentes comparten
    tenant, así que la RLS aísla tenants pero NO comisiones. El resto de los
    endpoints cerró ese agujero (`es_de_mi_comision` en `correccion_ia.py`,
    `_assert_comision_visible` en `entregas.py`); estos dos quedaron con
    chequeo de ROL solamente.

    Con el `tarea_practica_id` de otra comisión en la mano, un docente ajeno
    podía leer los títulos de sus ejercicios y sus `rubrica_id`, y —peor—
    empujar ese TP **con su propia cuenta de Active-IA**, pisando las filas de
    `activeia_rubrica_ejercicio`, que son únicas por `(tenant_id, ejercicio_id)`
    y no llevan comisión ni docente. El docente legítimo quedaba con un vínculo
    apuntando a la rúbrica de una cuenta ajena, y como `rubrica_id` entra en la
    clave de idempotencia, la corrección previa dejaba de encontrarse y se
    pagaba otra corrida sobre el mismo código.

    404 y no 403, mismo criterio que el resto: un 403 confirmaría que la TP
    existe, y ahí el id de una comisión ajena se vuelve un oráculo.
    """
    if user.roles & _OVERSIGHT:
        return
    fila = (
        await db.execute(
            text(
                "SELECT 1 FROM tareas_practicas tp "
                "JOIN usuarios_comision uc ON uc.comision_id = tp.comision_id "
                "WHERE tp.id = :tp AND uc.user_id = :u AND uc.deleted_at IS NULL "
                "LIMIT 1"
            ),
            {"tp": str(tarea_practica_id), "u": str(user.id)},
        )
    ).first()
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trabajo practico no existe"
        )


@router.get("/tp/{tarea_practica_id}/sincronizacion", response_model=SincronizacionOut)
async def estado_sincronizacion(
    tarea_practica_id: UUID,
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> SincronizacionOut:
    """Estado por ejercicio, sin contactar a Active-IA.

    Es una lectura barata: compara el hash guardado contra el de la rúbrica de
    hoy. No hace falta cuenta conectada ni el kill switch prendido — saber que
    algo quedó desactualizado tiene que poder verse aunque la integración esté
    apagada.
    """
    await _assert_tp_de_mi_comision(db, tarea_practica_id, user)
    estados = await estado_de_sincronizacion(db, user.tenant_id, tarea_practica_id)
    return SincronizacionOut(
        ejercicios=[
            EjercicioSyncOut(
                ejercicio_id=e.ejercicio_id,
                titulo=e.titulo,
                estado=e.estado.value,
                rubrica_id=e.rubrica_id,
                sincronizado_at=e.sincronizado_at,
                simulado=e.simulado,
            )
            for e in estados
        ],
        modo_simulado=_hay_simulacion(estados),
    )


@router.post("/tp/{tarea_practica_id}/sincronizar", response_model=SincronizacionOut)
async def sincronizar(
    tarea_practica_id: UUID,
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> SincronizacionOut:
    """Empuja la rúbrica de cada ejercicio del TP a Active-IA.

    Un ejercicio que falla NO aborta el resto: el docente prefiere tener tres
    de cuatro y saber cuál falló, antes que nada. El resultado devuelve el
    estado de todos, así que el que no se sincronizó se ve.
    """
    _assert_habilitado()
    await _assert_tp_de_mi_comision(db, tarea_practica_id, user)
    try:
        cliente = await cliente_para(db, user.tenant_id, user.id)
        estados = await sincronizar_tp(db, cliente, user.tenant_id, tarea_practica_id)
    except CredencialNoConfiguradaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ActiveIAError as e:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if e.es_infraestructura
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=e.mensaje,
        ) from e

    return SincronizacionOut(
        ejercicios=[
            EjercicioSyncOut(
                ejercicio_id=e.ejercicio_id,
                titulo=e.titulo,
                estado=e.estado.value,
                rubrica_id=e.rubrica_id,
                sincronizado_at=e.sincronizado_at,
                simulado=e.simulado,
            )
            for e in estados
        ],
        modo_simulado=_hay_simulacion(estados),
    )


@router.delete("/credenciales", status_code=status.HTTP_204_NO_CONTENT)
async def desconectar_cuenta(
    user: User = Depends(require_correccion_ia),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Desconecta la cuenta. Idempotente: sin cuenta conectada también da 204.

    No borra la fila, la marca revocada: saber que un docente tuvo una cuenta
    conectada es parte de la trazabilidad de quién mandó código afuera.
    """
    revocada = await revocar_credencial(db, user.tenant_id, user.id)
    log = structlog.get_logger()
    log.info(
        "activeia_desconectar",
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        habia_credencial=revocada,
    )
