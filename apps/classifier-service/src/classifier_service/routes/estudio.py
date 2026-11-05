"""Estudio de codificación ciega (change cibse-codificacion-ciega).

Acceso por MEMBRESÍA asignada por email y atada al `user_id` firmado por el
gateway en el primer uso (design D3). Ningún rol genérico alcanza: con Clerk,
toda cuenta trae `estudiante,docente`. Los roles `superadmin`/`docente_admin`
solo sirven para dar de alta estudios y gestionar membresías.

Tablas del estudio: solo las leen endpoints de este router.

Endpoints (prefijo `/api/v1/interrater/estudios`):
  - POST   ""                               alta de estudio (admin)
  - GET    "/mis-membresias"                membresías activas del caller
  - POST   "/{clave}/membresias"            alta de membresía (investigador o admin)
  - DELETE "/{clave}/membresias/{id}"       revocación (investigador o admin)
  - POST   "/{clave}/codebook"              versión nueva, vacía o clonada (investigador)
  - PUT    "/{clave}/codebook/{etiqueta}"   texto y esquema de un borrador (investigador)
  - POST   "/{clave}/codebook/{etiqueta}/congelar"   congela con sha256 (investigador)
  - PUT    "/{clave}/codebook-vigente"      fija la versión vigente (investigador)
  - GET    "/{clave}/codebook/vigente"      lee la vigente (cualquier miembro)
  - GET    "/{clave}/membresias"            lista membresías (investigador o admin)
  - GET    "/{clave}/codebook/versiones[/{etiqueta}]"  versiones (cualquier miembro;
           anclas completas solo para el investigador)
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classifier_service.auth import User, get_current_user, require_gateway_auth
from classifier_service.db import tenant_session
from classifier_service.models import (
    CodebookVersion,
    EstudioAncla,
    EstudioCodificacion,
    EstudioEtiqueta,
    EstudioMembresia,
)
from classifier_service.services.estudio_codebook import CAMPOS_ANCLA, sha256_codebook
from classifier_service.services.estudio_esquema import (
    motivos_ancla_para_congelar,
    validar_esquema,
)
from classifier_service.services.traza_ciega import TRAZA_VERSION

router = APIRouter(
    prefix="/api/v1/interrater/estudios",
    tags=["estudio"],
    dependencies=[Depends(require_gateway_auth)],
)
logger = logging.getLogger(__name__)

ADMIN_ROLES = frozenset({"superadmin", "docente_admin"})
INVESTIGADOR = "investigador"
CODIFICADOR = "codificador"
ROLES_ESTUDIO = (INVESTIGADOR, CODIFICADOR)

_CLAVE_ESTUDIO = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")
# Segmentos literales de las rutas del router: una clave igual haría ambigua
# la URL (`/estudios/mis-membresias`) o la confundiría con un sub-recurso.
CLAVES_RESERVADAS = frozenset(
    {
        "mis-membresias",
        "membresias",
        "codebook",
        "codebook-vigente",
        "vigente",
        "congelar",
        "muestra",
        "items",
        "traza",
        "mi-etiqueta",
        "mi-codificacion",
        "cerrar",
        "enunciados",
        "revision",
        "anclas",
        "entrenamiento",
        "respuesta",
        "progreso",
        "exportacion",
    }
)
_PREFIJO_ALIAS = {INVESTIGADOR: "I", CODIFICADOR: "C"}

_SIN_ACCESO = "Sin acceso a este estudio"
# Literal: `HTTP_422_UNPROCESSABLE_ENTITY` está deprecado en la Starlette instalada
# y `HTTP_422_UNPROCESSABLE_CONTENT` no existe en versiones anteriores.
HTTP_422 = 422


# ── Esquemas HTTP ─────────────────────────────────────────────────────────


class EstudioIn(BaseModel):
    clave: str = Field(min_length=1, max_length=64)
    titulo: str = Field(min_length=1, max_length=300)


class EstudioOut(BaseModel):
    clave: str
    titulo: str
    traza_version: str


class MembresiaIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    rol: Literal["investigador", "codificador"]


class MembresiaOut(BaseModel):
    membresia_id: str
    alias: str
    rol: str


class RevocacionOut(BaseModel):
    membresia_id: str
    revocada_at: datetime


class MiMembresiaOut(BaseModel):
    clave: str
    titulo: str
    rol: str
    cerrada: bool


# ── Resolución de identidad ───────────────────────────────────────────────


def _email(user: User) -> str:
    return user.email.strip().lower()


def _es_admin(user: User) -> bool:
    return bool(user.roles & ADMIN_ROLES)


def _prohibido() -> HTTPException:
    # Mismo cuerpo exista o no el estudio: no se revela su existencia.
    return HTTPException(status.HTTP_403_FORBIDDEN, detail=_SIN_ACCESO)


Bloqueo = Literal["share", "update"]


async def _buscar_estudio(
    session: AsyncSession, clave: str, *, bloquear: bool | Bloqueo = False
) -> EstudioCodificacion | None:
    """`bloquear`: `"update"` (o True) toma la fila `FOR UPDATE`; `"share"`,
    `FOR SHARE`."""
    consulta = select(EstudioCodificacion).where(EstudioCodificacion.clave == clave)
    if bloquear:
        consulta = consulta.with_for_update(read=bloquear == "share").execution_options(
            populate_existing=True
        )
    return (await session.execute(consulta)).scalar_one_or_none()


async def _atar_o_verificar(session: AsyncSession, membresia: EstudioMembresia, user: User) -> bool:
    """Ata la membresía al `user_id` del primer uso o verifica que coincida.

    Devuelve False (y registra `estudio_membresia_user_id_distinto`, sin email)
    si ya estaba atada a otro usuario. La atadura es condicional
    (`WHERE user_id IS NULL`) para que dos primeros usos simultáneos no se
    pisen: el que pierde relee y queda rechazado."""
    if membresia.user_id is None:
        await session.execute(
            update(EstudioMembresia)
            .where(EstudioMembresia.id == membresia.id, EstudioMembresia.user_id.is_(None))
            .values(user_id=user.id)
        )
        await session.refresh(membresia)
    if membresia.user_id != user.id:
        logger.warning(
            "estudio_membresia_user_id_distinto",
            extra={"membresia_id": str(membresia.id), "user_id": str(user.id)},
        )
        return False
    return True


async def require_membresia(
    session: AsyncSession,
    user: User,
    clave: str,
    roles: tuple[str, ...],
    *,
    bloquear_estudio: Bloqueo | None = None,
) -> tuple[EstudioCodificacion, EstudioMembresia]:
    """Estudio y membresía ACTIVA del caller con uno de `roles`, o 403.

    El email solo localiza la membresía (minúsculas); la identidad la da el
    `user_id` atado. Se llama dentro de la sesión del handler (no como
    `Depends`) para que la atadura comparta la transacción del pedido.

    `bloquear_estudio`: los caminos que bloquean la fila del estudio la toman
    ACÁ, antes de leer y atar la membresía (D10b: estudio, luego membresía). Si
    la tomaran después de la atadura (un UPDATE de la membresía), chocarían con
    una revocación, que toma el estudio y después la membresía: deadlock
    (verify-2, N1)."""
    estudio = await _buscar_estudio(session, clave, bloquear=bloquear_estudio or False)
    if estudio is None:
        raise _prohibido()
    membresia = (
        await session.execute(
            select(EstudioMembresia).where(
                EstudioMembresia.estudio_id == estudio.id,
                func.lower(EstudioMembresia.email) == _email(user),
                EstudioMembresia.revocada_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if membresia is None or membresia.rol not in roles:
        raise _prohibido()
    if not await _atar_o_verificar(session, membresia, user):
        raise _prohibido()
    return estudio, membresia


async def _estudio_para_gestionar(
    session: AsyncSession, user: User, clave: str
) -> EstudioCodificacion:
    """Estudio cuyas membresías puede gestionar el caller: administrador o
    investigador del estudio. Bloquea la fila (alta y revocación serializadas)."""
    if _es_admin(user):
        estudio = await _buscar_estudio(session, clave, bloquear=True)
        if estudio is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Estudio inexistente")
        return estudio
    bloqueado, _ = await require_membresia(
        session, user, clave, (INVESTIGADOR,), bloquear_estudio="update"
    )
    return bloqueado


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("", response_model=EstudioOut, status_code=status.HTTP_201_CREATED)
async def crear_estudio(body: EstudioIn, user: User = Depends(get_current_user)) -> EstudioOut:
    if not _es_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Requiere rol administrativo")
    if not _CLAVE_ESTUDIO.match(body.clave) or body.clave in CLAVES_RESERVADAS:
        raise HTTPException(
            HTTP_422,
            detail="Clave inválida: minúsculas, dígitos y guiones (3 a 41), no reservada",
        )
    try:
        async with tenant_session(user.tenant_id) as session:
            session.add(
                EstudioCodificacion(
                    tenant_id=user.tenant_id,
                    clave=body.clave,
                    titulo=body.titulo,
                    traza_version=TRAZA_VERSION,
                    created_by=user.id,
                )
            )
            await session.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="La clave ya existe")
    logger.info(
        "estudio_alta",
        extra={
            "estudio": body.clave,
            "autor_user_id": str(user.id),
            "traza_version": TRAZA_VERSION,
        },
    )
    return EstudioOut(clave=body.clave, titulo=body.titulo, traza_version=TRAZA_VERSION)


@router.get("/mis-membresias", response_model=list[MiMembresiaOut])
async def mis_membresias(user: User = Depends(get_current_user)) -> list[MiMembresiaOut]:
    """Membresías activas del caller. Cuenta como primer uso: ata el `user_id`.
    Una membresía atada a otro usuario no se lista (y queda registrada)."""
    async with tenant_session(user.tenant_id) as session:
        filas = (
            await session.execute(
                select(EstudioMembresia, EstudioCodificacion)
                .join(EstudioCodificacion, EstudioCodificacion.id == EstudioMembresia.estudio_id)
                .where(
                    func.lower(EstudioMembresia.email) == _email(user),
                    EstudioMembresia.revocada_at.is_(None),
                )
                .order_by(EstudioCodificacion.clave)
            )
        ).all()
        salida = []
        for membresia, estudio in filas:
            if not await _atar_o_verificar(session, membresia, user):
                continue
            salida.append(
                MiMembresiaOut(
                    clave=estudio.clave,
                    titulo=estudio.titulo,
                    rol=membresia.rol,
                    cerrada=membresia.cerrada_at is not None,
                )
            )
    return salida


async def _siguiente_alias(session: AsyncSession, estudio_id: UUID, rol: str) -> str:
    previas = (
        await session.execute(
            select(func.count())
            .select_from(EstudioMembresia)
            .where(EstudioMembresia.estudio_id == estudio_id, EstudioMembresia.rol == rol)
        )
    ).scalar_one()
    return f"{_PREFIJO_ALIAS[rol]}{previas + 1}"


async def _semilla_libre(session: AsyncSession, estudio_id: UUID) -> int:
    usadas = set(
        (
            await session.execute(
                select(EstudioMembresia.semilla).where(EstudioMembresia.estudio_id == estudio_id)
            )
        ).scalars()
    )
    while True:
        semilla = secrets.randbits(63)
        if semilla not in usadas:
            return semilla


@router.post(
    "/{clave}/membresias", response_model=MembresiaOut, status_code=status.HTTP_201_CREATED
)
async def alta_membresia(
    clave: str, body: MembresiaIn, user: User = Depends(get_current_user)
) -> MembresiaOut:
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(HTTP_422, detail="Email inválido")
    try:
        async with tenant_session(user.tenant_id) as session:
            estudio = await _estudio_para_gestionar(session, user, clave)
            membresia = EstudioMembresia(
                tenant_id=user.tenant_id,
                estudio_id=estudio.id,
                email=email,
                rol=body.rol,
                alias=await _siguiente_alias(session, estudio.id, body.rol),
                semilla=await _semilla_libre(session, estudio.id),
                created_by=user.id,
            )
            session.add(membresia)
            await session.flush()
            salida = MembresiaOut(
                membresia_id=str(membresia.id), alias=membresia.alias, rol=body.rol
            )
    except IntegrityError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Ese email ya tiene una membresía activa en el estudio"
        )
    logger.info(
        "estudio_membresia_alta",
        extra={
            "estudio": clave,
            "rol": body.rol,
            "membresia_id": salida.membresia_id,
            "alias": salida.alias,
            "autor_user_id": str(user.id),
            "momento": datetime.now(UTC).isoformat(),
        },
    )
    return salida


@router.delete("/{clave}/membresias/{membresia_id}", response_model=RevocacionOut)
async def revocar_membresia(
    clave: str, membresia_id: UUID, user: User = Depends(get_current_user)
) -> RevocacionOut:
    async with tenant_session(user.tenant_id) as session:
        estudio = await _estudio_para_gestionar(session, user, clave)
        ahora = datetime.now(UTC)
        fila = (
            await session.execute(
                update(EstudioMembresia)
                .where(
                    EstudioMembresia.id == membresia_id,
                    EstudioMembresia.estudio_id == estudio.id,
                    EstudioMembresia.revocada_at.is_(None),
                )
                .values(revocada_at=ahora)
                .returning(EstudioMembresia.rol, EstudioMembresia.alias)
            )
        ).one_or_none()
        if fila is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Membresía activa inexistente")
    logger.info(
        "estudio_membresia_revocada",
        extra={
            "estudio": clave,
            "rol": fila.rol,
            "membresia_id": str(membresia_id),
            "alias": fila.alias,
            "autor_user_id": str(user.id),
            "momento": ahora.isoformat(),
        },
    )
    return RevocacionOut(membresia_id=str(membresia_id), revocada_at=ahora)


# ── Codebook versionado (design D8, D9) ──────────────────────────────────────

_ETIQUETA_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
# `vigente` y `versiones` son segmentos literales de rutas `.../codebook/...`.
_ETIQUETAS_RESERVADAS = frozenset({"vigente", "versiones"})
# Columnas del ancla que se copian al clonar: todo salvo ids y fechas.
_COLUMNAS_ANCLA_CLONADAS = (
    "episode_id",
    "seq_tope",
    "chain_hash_tope",
    "events_count_carga",
    "last_chain_hash_carga",
    "estado_carga",
    "problema_id",
    "ejercicio_id",
    "uso",
    "orden",
    "respuesta_esperada",
    "explicacion_md",
    "consensuado_por",
)


class VersionIn(BaseModel):
    etiqueta: str = Field(max_length=64)
    clonar_de: str | None = None


class VersionEdicion(BaseModel):
    contenido_md: str | None = None
    esquema: dict[str, Any] | None = None


class VersionOut(BaseModel):
    etiqueta: str
    estado: str
    contenido_md: str
    esquema: dict[str, Any] | None
    contenido_sha256: str | None


class AnclaInvalidaOut(BaseModel):
    item_id: UUID
    uso: str
    orden: int
    motivos: list[str]


class VersionEditadaOut(VersionOut):
    """Respuesta del PUT del borrador: avisa qué anclas dejaron de valer contra
    el esquema guardado. No rechaza (renombrar una dimensión dejaría al ancla
    sin forma de corregirse: tampoco vale contra el esquema viejo); congelar sí
    rechaza mientras haya alguna (verify-1, F1)."""

    anclas_invalidas: list[AnclaInvalidaOut]


class VigenteIn(BaseModel):
    etiqueta: str = Field(max_length=64)


def version_out(version: CodebookVersion) -> VersionOut:
    return VersionOut(
        etiqueta=version.etiqueta,
        estado=version.estado,
        contenido_md=version.contenido_md,
        esquema=version.esquema_formulario,
        contenido_sha256=version.contenido_sha256,
    )


async def _version(
    session: AsyncSession, estudio_id: UUID, etiqueta: str, *, bloquear: bool = False
) -> CodebookVersion:
    consulta = select(CodebookVersion).where(
        CodebookVersion.estudio_id == estudio_id, CodebookVersion.etiqueta == etiqueta
    )
    if bloquear:
        consulta = consulta.with_for_update()
    version = (await session.execute(consulta)).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Versión inexistente")
    return version


async def investigador_con_estudio_bloqueado(
    session: AsyncSession, user: User, clave: str
) -> EstudioCodificacion:
    """Investigador del estudio; bloquea la fila del estudio (D10b: cambio de
    vigente, congelado y alta/baja de anclas quedan serializados)."""
    estudio, _ = await require_membresia(
        session, user, clave, (INVESTIGADOR,), bloquear_estudio="update"
    )
    return estudio


@router.post("/{clave}/codebook", response_model=VersionOut, status_code=status.HTTP_201_CREATED)
async def crear_version(
    clave: str, body: VersionIn, user: User = Depends(get_current_user)
) -> VersionOut:
    if not _ETIQUETA_VERSION.match(body.etiqueta) or body.etiqueta in _ETIQUETAS_RESERVADAS:
        raise HTTPException(HTTP_422, detail="Etiqueta inválida")
    try:
        async with tenant_session(user.tenant_id) as session:
            estudio = await investigador_con_estudio_bloqueado(session, user, clave)
            origen = await _version(session, estudio.id, body.clonar_de) if body.clonar_de else None
            version = CodebookVersion(
                tenant_id=user.tenant_id,
                estudio_id=estudio.id,
                etiqueta=body.etiqueta,
                estado="borrador",
                contenido_md=origen.contenido_md if origen else "",
                esquema_formulario=origen.esquema_formulario if origen else None,
                created_by=user.id,
            )
            session.add(version)
            await session.flush()
            if origen is not None:
                anclas = (
                    await session.execute(
                        select(EstudioAncla).where(EstudioAncla.codebook_version_id == origen.id)
                    )
                ).scalars()
                for ancla in anclas:
                    session.add(
                        EstudioAncla(
                            tenant_id=user.tenant_id,
                            estudio_id=estudio.id,
                            codebook_version_id=version.id,
                            **{c: getattr(ancla, c) for c in _COLUMNAS_ANCLA_CLONADAS},
                        )
                    )
                await session.flush()
            salida = version_out(version)
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="La etiqueta ya existe en el estudio")
    logger.info(
        "estudio_codebook_version_alta",
        extra={
            "estudio": clave,
            "etiqueta": body.etiqueta,
            "clonada_de": body.clonar_de,
            "autor_user_id": str(user.id),
        },
    )
    return salida


@router.put("/{clave}/codebook/{etiqueta}", response_model=VersionEditadaOut)
async def editar_version(
    clave: str, etiqueta: str, body: VersionEdicion, user: User = Depends(get_current_user)
) -> VersionEditadaOut:
    if "esquema" in body.model_fields_set and body.esquema is not None:
        errores = validar_esquema(body.esquema)
        if errores:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail={"mensaje": "Esquema inválido", "errores": errores},
            )
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        version = await _version(session, estudio.id, etiqueta, bloquear=True)
        if version.estado != "borrador":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Versión congelada")
        if "contenido_md" in body.model_fields_set and body.contenido_md is not None:
            version.contenido_md = body.contenido_md
        if "esquema" in body.model_fields_set:
            version.esquema_formulario = body.esquema
        await session.flush()
        invalidas = (
            await _anclas_invalidas(session, version.id, version.esquema_formulario)
            if version.esquema_formulario is not None
            else []
        )
        return VersionEditadaOut(**version_out(version).model_dump(), anclas_invalidas=invalidas)


async def _anclas_de(session: AsyncSession, version_id: UUID) -> list[EstudioAncla]:
    return list(
        (
            await session.execute(
                select(EstudioAncla)
                .where(EstudioAncla.codebook_version_id == version_id)
                .order_by(EstudioAncla.uso, EstudioAncla.orden, EstudioAncla.episode_id)
            )
        ).scalars()
    )


async def _anclas_invalidas(
    session: AsyncSession, version_id: UUID, esquema: dict[str, Any]
) -> list[AnclaInvalidaOut]:
    """Anclas de la versión que impiden congelar contra `esquema`: respuesta
    esperada que no vale (misma semántica que el etiquetado; exentos explícitos
    permitidos) o que no está completa como un cierre de codificación (O1)."""
    salida = []
    for ancla in await _anclas_de(session, version_id):
        motivos = motivos_ancla_para_congelar(esquema, ancla.respuesta_esperada)
        if motivos:
            salida.append(
                AnclaInvalidaOut(
                    item_id=ancla.item_id, uso=ancla.uso, orden=ancla.orden, motivos=motivos
                )
            )
    return salida


async def _anclas_para_sha(session: AsyncSession, version_id: UUID) -> list[dict[str, Any]]:
    return [
        {campo: getattr(ancla, campo) for campo in CAMPOS_ANCLA}
        for ancla in await _anclas_de(session, version_id)
    ]


@router.post("/{clave}/codebook/{etiqueta}/congelar", response_model=VersionOut)
async def congelar_version(
    clave: str, etiqueta: str, user: User = Depends(get_current_user)
) -> VersionOut:
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        version = await _version(session, estudio.id, etiqueta, bloquear=True)
        if version.estado != "borrador":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="La versión ya está congelada")
        if not version.contenido_md.strip():
            raise HTTPException(HTTP_422, detail="El texto del codebook está vacío")
        if version.esquema_formulario is None or validar_esquema(version.esquema_formulario):
            raise HTTPException(HTTP_422, detail="Falta un esquema válido")
        invalidas = await _anclas_invalidas(session, version.id, version.esquema_formulario)
        if invalidas:
            raise HTTPException(
                HTTP_422,
                detail={
                    "codigo": "anclas_invalidas",
                    "anclas": [a.model_dump(mode="json") for a in invalidas],
                    "errores": [
                        f"ancla {a.uso} {a.orden}: {'; '.join(a.motivos)}" for a in invalidas
                    ],
                },
            )
        sha = sha256_codebook(
            version.contenido_md,
            version.esquema_formulario,
            await _anclas_para_sha(session, version.id),
        )
        version.estado = "congelada"
        version.contenido_sha256 = sha
        version.congelada_at = datetime.now(UTC)
        version.congelada_por = user.id
        await session.flush()
        salida = version_out(version)
    logger.info(
        "estudio_codebook_congelado",
        extra={
            "estudio": clave,
            "etiqueta": etiqueta,
            "contenido_sha256": sha,
            "autor_user_id": str(user.id),
        },
    )
    return salida


@router.put("/{clave}/codebook-vigente", response_model=VersionOut)
async def fijar_vigente(
    clave: str, body: VigenteIn, user: User = Depends(get_current_user)
) -> VersionOut:
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        version = await _version(session, estudio.id, body.etiqueta)
        if estudio.codebook_vigente_id != version.id:
            etiquetas = (
                await session.execute(
                    select(func.count())
                    .select_from(EstudioEtiqueta)
                    .join(EstudioMembresia, EstudioMembresia.id == EstudioEtiqueta.membresia_id)
                    .where(EstudioMembresia.estudio_id == estudio.id)
                )
            ).scalar_one()
            if etiquetas:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Hay etiquetas del estudio: la versión vigente no se cambia",
                )
            estudio.codebook_vigente_id = version.id
            await session.flush()
        salida = version_out(version)
    logger.info(
        "estudio_codebook_vigente",
        extra={"estudio": clave, "etiqueta": body.etiqueta, "autor_user_id": str(user.id)},
    )
    return salida


@router.get("/{clave}/codebook/vigente", response_model=VersionOut)
async def leer_vigente(clave: str, user: User = Depends(get_current_user)) -> VersionOut:
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, ROLES_ESTUDIO)
        if estudio.codebook_vigente_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="sin_codebook")
        version = (
            await session.execute(
                select(CodebookVersion).where(CodebookVersion.id == estudio.codebook_vigente_id)
            )
        ).scalar_one()
        return version_out(version)


# ── Lecturas para el panel del investigador (tareas 5.2 y 5.3) ───────────────


def _estado_membresia(m: EstudioMembresia) -> str:
    if m.revocada_at is not None:
        return "revocada"
    if m.cerrada_at is not None:
        return "cerrada"
    return "activa"


@router.get("/{clave}/membresias")
async def listar_membresias(
    clave: str, user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    """Investigador del estudio o administrador. Nunca etiquetas ni progreso."""
    async with tenant_session(user.tenant_id) as session:
        if _es_admin(user):
            estudio = await _buscar_estudio(session, clave)
            if estudio is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Estudio inexistente")
        else:
            estudio, _ = await require_membresia(session, user, clave, (INVESTIGADOR,))
        membresias = (
            await session.execute(
                select(EstudioMembresia)
                .where(EstudioMembresia.estudio_id == estudio.id)
                .order_by(EstudioMembresia.created_at)
            )
        ).scalars()
        return [
            {
                "membresia_id": str(m.id),
                "email": m.email,
                "rol": m.rol,
                "alias": m.alias,
                "estado": _estado_membresia(m),
                "atada": m.user_id is not None,
                "created_at": m.created_at.isoformat(),
                "cerrada_at": m.cerrada_at.isoformat() if m.cerrada_at else None,
                "revocada_at": m.revocada_at.isoformat() if m.revocada_at else None,
            }
            for m in membresias
        ]


@router.get("/{clave}/codebook/versiones")
async def listar_versiones(
    clave: str, user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, ROLES_ESTUDIO)
        versiones = (
            await session.execute(
                select(CodebookVersion)
                .where(CodebookVersion.estudio_id == estudio.id)
                .order_by(CodebookVersion.created_at)
            )
        ).scalars()
        return [
            {
                "etiqueta": v.etiqueta,
                "estado": v.estado,
                "contenido_sha256": v.contenido_sha256,
                "congelada_at": v.congelada_at.isoformat() if v.congelada_at else None,
                "vigente": v.id == estudio.codebook_vigente_id,
            }
            for v in versiones
        ]


@router.get("/{clave}/codebook/versiones/{etiqueta}")
async def leer_version(
    clave: str, etiqueta: str, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """Texto, esquema, estado y sha256 para todo miembro. Anclas: el
    investigador las ve completas; el resto solo `item_id`, uso y orden (sin
    respuesta esperada, explicación ni `episode_id`, D5 y D11)."""
    async with tenant_session(user.tenant_id) as session:
        estudio, membresia = await require_membresia(session, user, clave, ROLES_ESTUDIO)
        version = await _version(session, estudio.id, etiqueta)
        anclas = (
            await session.execute(
                select(EstudioAncla)
                .where(EstudioAncla.codebook_version_id == version.id)
                .order_by(EstudioAncla.uso, EstudioAncla.orden)
            )
        ).scalars()
        if membresia.rol == INVESTIGADOR:
            anclas_out = [
                {
                    "item_id": str(a.item_id),
                    "episode_id": str(a.episode_id),
                    "uso": a.uso,
                    "orden": a.orden,
                    "respuesta_esperada": a.respuesta_esperada,
                    "explicacion_md": a.explicacion_md,
                    "consensuado_por": a.consensuado_por,
                }
                for a in anclas
            ]
        else:
            anclas_out = [
                {"item_id": str(a.item_id), "uso": a.uso, "orden": a.orden} for a in anclas
            ]
        return {
            **version_out(version).model_dump(),
            "congelada_at": version.congelada_at.isoformat() if version.congelada_at else None,
            "vigente": version.id == estudio.codebook_vigente_id,
            "anclas": anclas_out,
        }
