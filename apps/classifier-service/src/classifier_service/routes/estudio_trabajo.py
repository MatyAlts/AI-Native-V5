"""Estudio de codificación ciega: trabajo sobre la muestra (grupos 6 a 10 del change).

Mismo prefijo y mismo gate de procedencia que `routes/estudio.py`, del que
reusa la resolución de membresía. Acá viven la traza ciega, la muestra y su
orden, los enunciados, las anclas, el etiquetado, el entrenamiento, el
progreso y la exportación.

La cuenta de servicio del CTR (`services/ctr_lectura.py`) lee cualquier
episodio del tenant: ningún endpoint de este módulo le pasa un `episode_id`
que venga del pedido de un codificador. La traza resuelve SIEMPRE un
`item_id` opaco de la muestra o de las anclas del estudio del caller.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classifier_service.auth import User, get_current_user, require_gateway_auth
from classifier_service.db import tenant_session
from classifier_service.models import (
    CodebookVersion,
    EntrenamientoRespuesta,
    EstudioAncla,
    EstudioCodificacion,
    EstudioEnunciado,
    EstudioEtiqueta,
    EstudioEtiquetaHistorial,
    EstudioMembresia,
    EstudioMuestra,
)
from classifier_service.routes.estudio import (
    CODIFICADOR,
    HTTP_422,
    INVESTIGADOR,
    ROLES_ESTUDIO,
    VersionOut,
    investigador_con_estudio_bloqueado,
    require_membresia,
    version_out,
)
from classifier_service.services.ctr_lectura import (
    CTRLector,
    CTRNoDisponibleError,
    EpisodioInexistenteError,
    get_ctr_lector,
)
from classifier_service.services.estudio_enunciados import (
    alertas_enunciado,
    cobertura,
    parsear_enunciados_csv,
    sha256_texto,
)
from classifier_service.services.estudio_esquema import (
    Evaluacion,
    PedidoInvalidoError,
    evaluar_pedido,
    faltantes_cierre,
    motivos_ancla_para_congelar,
)
from classifier_service.services.estudio_export import (
    a_csv,
    aplanar_respuesta,
    columnas_respuesta,
)
from classifier_service.services.estudio_muestra import (
    evidencia_fija,
    motivo_rechazo,
    parsear_muestra_csv,
)
from classifier_service.services.estudio_orden import orden_codificador
from classifier_service.services.traza_ciega import TRAZA_VERSION, filtrar_traza

router = APIRouter(
    prefix="/api/v1/interrater/estudios",
    tags=["estudio"],
    dependencies=[Depends(require_gateway_auth)],
)
logger = logging.getLogger("classifier_service.routes.estudio")

_ERROR_CTR = "El registro de episodios no está disponible"


def _conflicto(codigo: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail=codigo)


async def _item_del_estudio(
    session: AsyncSession, estudio: EstudioCodificacion, item_id: UUID
) -> EstudioMuestra | EstudioAncla:
    """Ítem de la muestra o ancla de ESTE estudio, o 404. Nunca un `episode_id`."""
    item: EstudioMuestra | EstudioAncla | None = (
        await session.execute(
            select(EstudioMuestra).where(
                EstudioMuestra.item_id == item_id, EstudioMuestra.estudio_id == estudio.id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        item = (
            await session.execute(
                select(EstudioAncla).where(
                    EstudioAncla.item_id == item_id, EstudioAncla.estudio_id == estudio.id
                )
            )
        ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ítem inexistente")
    return item


async def _enunciados_revisados(
    session: AsyncSession, estudio_id: UUID
) -> dict[tuple[str, UUID], EstudioEnunciado]:
    filas = (
        await session.execute(
            select(EstudioEnunciado).where(
                EstudioEnunciado.estudio_id == estudio_id,
                EstudioEnunciado.revisado_at.is_not(None),
            )
        )
    ).scalars()
    return {(e.fuente, e.fuente_id): e for e in filas}


def _enunciado_del_item(
    item: EstudioMuestra | EstudioAncla, revisados: dict[tuple[str, UUID], EstudioEnunciado]
) -> dict[str, str | None] | None:
    """Texto mostrado de TP y ejercicio; None si falta alguno o no está revisado."""
    tp = revisados.get(("tp", item.problema_id))
    if tp is None:
        return None
    ejercicio = None
    if item.ejercicio_id is not None:
        ejercicio = revisados.get(("ejercicio", item.ejercicio_id))
        if ejercicio is None:
            return None
    return {
        "tp_md": tp.contenido_mostrado_md,
        "ejercicio_md": ejercicio.contenido_mostrado_md if ejercicio else None,
    }


@router.get("/{clave}/items/{item_id}/traza")
async def traza_ciega(
    clave: str,
    item_id: UUID,
    user: User = Depends(get_current_user),
    lector: CTRLector = Depends(get_ctr_lector),
) -> dict[str, Any]:
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, ROLES_ESTUDIO)
        item = await _item_del_estudio(session, estudio, item_id)
        if estudio.traza_version != TRAZA_VERSION:
            raise _conflicto("traza_version_distinta")
        enunciado = _enunciado_del_item(item, await _enunciados_revisados(session, estudio.id))
        if enunciado is None:
            raise _conflicto("enunciado_pendiente")
        episode_id, seq_tope, chain_tope = item.episode_id, item.seq_tope, item.chain_hash_tope

    try:
        episodio = await lector.episodio(user.tenant_id, episode_id)
    except EpisodioInexistenteError:
        episodio = {"events": []}
    except CTRNoDisponibleError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=_ERROR_CTR)

    eventos = episodio.get("events") or []
    tope = next((e for e in eventos if e.get("seq") == seq_tope), None)
    if tope is None or tope.get("chain_hash") != chain_tope:
        logger.warning(
            "estudio_evidencia_alterada", extra={"estudio": clave, "item_id": str(item_id)}
        )
        raise _conflicto("evidencia_alterada")

    return {
        "traza_version": TRAZA_VERSION,
        "enunciado": enunciado,
        "elementos": filtrar_traza(eventos, seq_tope),
    }


# ── Muestra (design D6, D4b) ─────────────────────────────────────────────────

CONCURRENCIA_CTR = 8


async def leer_episodios(
    lector: CTRLector, tenant_id: UUID, episodios: list[UUID]
) -> dict[UUID, dict[str, Any] | None]:
    """Lee del CTR con concurrencia acotada. Inexistente -> None.
    `CTRNoDisponibleError` se propaga: el llamador responde 502 sin cargar nada."""
    semaforo = asyncio.Semaphore(CONCURRENCIA_CTR)

    async def uno(episodio: UUID) -> tuple[UUID, dict[str, Any] | None]:
        async with semaforo:
            try:
                return episodio, await lector.episodio(tenant_id, episodio)
            except EpisodioInexistenteError:
                return episodio, None

    return dict(await asyncio.gather(*(uno(e) for e in episodios)))


def _error_ctr() -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=_ERROR_CTR)


async def hay_etiquetas(session: AsyncSession, estudio_id: UUID) -> bool:
    cantidad = (
        await session.execute(
            select(func.count())
            .select_from(EstudioEtiqueta)
            .join(EstudioMembresia, EstudioMembresia.id == EstudioEtiqueta.membresia_id)
            .where(EstudioMembresia.estudio_id == estudio_id)
        )
    ).scalar_one()
    return bool(cantidad)


@router.post("/{clave}/muestra")
async def cargar_muestra(
    clave: str,
    request: Request,
    sha256_esperado: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    lector: CTRLector = Depends(get_ctr_lector),
) -> dict[str, Any]:
    """CSV crudo en el cuerpo; se guarda solo `episode_id` y la evidencia fija.
    Todo o nada, bajo el lock del estudio (D10b)."""
    crudo = await request.body()
    sha = hashlib.sha256(crudo).hexdigest()
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        if sha256_esperado and sha256_esperado.strip().lower() != sha:
            raise HTTPException(HTTP_422, detail={"codigo": "sha256_distinto"})
        try:
            texto = crudo.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                HTTP_422, detail={"codigo": "csv_invalido", "errores": ["no es UTF-8"]}
            )
        episodios, errores = parsear_muestra_csv(texto)
        if errores:
            raise HTTPException(HTTP_422, detail={"codigo": "csv_invalido", "errores": errores})
        if await hay_etiquetas(session, estudio.id):
            raise _conflicto("muestra_con_etiquetas")
        anclas = (
            await session.execute(
                select(func.count())
                .select_from(EstudioAncla)
                .where(
                    EstudioAncla.estudio_id == estudio.id, EstudioAncla.episode_id.in_(episodios)
                )
            )
        ).scalar_one()
        if anclas:
            raise _conflicto("episodio_es_ancla")
        try:
            leidos = await leer_episodios(lector, user.tenant_id, episodios)
        except CTRNoDisponibleError:
            raise _error_ctr()
        errores = []
        for fila, episodio in enumerate(episodios, start=2):
            datos = leidos[episodio]
            motivo = "episodio inexistente" if datos is None else motivo_rechazo(datos)
            if motivo:
                errores.append(f"fila {fila}: {motivo}")
        if errores:
            raise HTTPException(
                HTTP_422, detail={"codigo": "episodios_invalidos", "errores": errores}
            )

        await session.execute(delete(EstudioMuestra).where(EstudioMuestra.estudio_id == estudio.id))
        for episodio in episodios:
            datos = leidos[episodio]
            assert datos is not None
            session.add(
                EstudioMuestra(
                    tenant_id=user.tenant_id,
                    estudio_id=estudio.id,
                    episode_id=episodio,
                    **evidencia_fija(datos),
                )
            )
        estudio.muestra_sha256 = sha
        estudio.muestra_cargada_at = datetime.now(UTC)
        await session.flush()
    logger.info(
        "estudio_muestra_cargada",
        extra={
            "estudio": clave,
            "items": len(episodios),
            "sha256": sha,
            "autor_user_id": str(user.id),
        },
    )
    return {"items": len(episodios), "sha256": sha}


# ── Orden e ítems del codificador (design D7) ────────────────────────────────


def evaluacion_de(etiqueta: EstudioEtiqueta) -> Evaluacion:
    return Evaluacion(
        respuestas=etiqueta.respuestas or {},
        regimen=etiqueta.regimen,
        regimen_regla=etiqueta.regimen_regla,
        regimen_propuesto=etiqueta.regimen_propuesto,
        es_frontera=etiqueta.es_frontera,
        confianza=etiqueta.confianza,
        notas=etiqueta.notas,
    )


async def esquema_vigente(
    session: AsyncSession, estudio: EstudioCodificacion
) -> CodebookVersion | None:
    if estudio.codebook_vigente_id is None:
        return None
    return (
        await session.execute(
            select(CodebookVersion).where(CodebookVersion.id == estudio.codebook_vigente_id)
        )
    ).scalar_one()


def estado_etiqueta(etiqueta: EstudioEtiqueta | None, esquema: dict[str, Any] | None) -> str:
    if etiqueta is None:
        return "sin_empezar"
    if esquema is not None and not faltantes_cierre(esquema, evaluacion_de(etiqueta)):
        return "completa"
    return "parcial"


@router.get("/{clave}/items")
async def mis_items(clave: str, user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Solo identificador opaco, posición y estado de la etiqueta propia."""
    async with tenant_session(user.tenant_id) as session:
        estudio, membresia = await require_membresia(session, user, clave, (CODIFICADOR,))
        item_ids = list(
            (
                await session.execute(
                    select(EstudioMuestra.item_id).where(EstudioMuestra.estudio_id == estudio.id)
                )
            ).scalars()
        )
        propias = {
            e.muestra_item_id: e
            for e in (
                await session.execute(
                    select(EstudioEtiqueta).where(EstudioEtiqueta.membresia_id == membresia.id)
                )
            ).scalars()
        }
        version = await esquema_vigente(session, estudio)
        esquema = version.esquema_formulario if version else None
        return [
            {
                "item_id": item_id,
                "posicion": posicion,
                "estado": estado_etiqueta(propias.get(UUID(item_id)), esquema),
            }
            for item_id, posicion in orden_codificador(membresia.semilla, item_ids)
        ]


# ── Enunciados (design D14) ──────────────────────────────────────────────────

Clave = tuple[str, UUID]


def _claves_de(item: EstudioMuestra | EstudioAncla) -> list[Clave]:
    claves: list[Clave] = [("tp", item.problema_id)]
    if item.ejercicio_id is not None:
        claves.append(("ejercicio", item.ejercicio_id))
    return claves


async def requeridos(
    session: AsyncSession, estudio_id: UUID, *, con_anclas: bool = True
) -> dict[Clave, list[str]]:
    """`(fuente, id) -> item_ids` de la muestra (y de las anclas, salvo `con_anclas=False`)."""
    items: list[EstudioMuestra | EstudioAncla] = list(
        (
            await session.execute(
                select(EstudioMuestra).where(EstudioMuestra.estudio_id == estudio_id)
            )
        ).scalars()
    )
    if con_anclas:
        items += list(
            (
                await session.execute(
                    select(EstudioAncla).where(EstudioAncla.estudio_id == estudio_id)
                )
            ).scalars()
        )
    salida: dict[Clave, list[str]] = {}
    for item in items:
        for clave in _claves_de(item):
            salida.setdefault(clave, []).append(str(item.item_id))
    return salida


async def _enunciados(session: AsyncSession, estudio_id: UUID) -> dict[Clave, EstudioEnunciado]:
    filas = (
        await session.execute(
            select(EstudioEnunciado).where(EstudioEnunciado.estudio_id == estudio_id)
        )
    ).scalars()
    return {(e.fuente, e.fuente_id): e for e in filas}


async def enunciados_pendientes(session: AsyncSession, estudio_id: UUID) -> bool:
    """True si falta o no está revisado ALGÚN enunciado requerido por la MUESTRA.
    Bloquea la codificación de todo el estudio, no del ítem (D14)."""
    necesarios = await requeridos(session, estudio_id, con_anclas=False)
    revisados = await _enunciados_revisados(session, estudio_id)
    return any(clave not in revisados for clave in necesarios)


def _enunciado_out(e: EstudioEnunciado) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "tipo": e.fuente,
        "fuente_id": str(e.fuente_id),
        "contenido_original_md": e.contenido_original_md,
        "sha256_original": e.sha256_original,
        "contenido_mostrado_md": e.contenido_mostrado_md,
        "sha256_mostrado": e.sha256_mostrado,
        "alertas": e.alertas,
        "revisado": e.revisado_at is not None,
    }


async def _cobertura(session: AsyncSession, estudio_id: UUID) -> dict[str, Any]:
    cargados = await _enunciados(session, estudio_id)
    return cobertura(
        await requeridos(session, estudio_id),
        cargados=set(cargados),
        revisados={c for c, e in cargados.items() if e.revisado_at is not None},
    )


@router.post("/{clave}/enunciados")
async def cargar_enunciados(
    clave: str, request: Request, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """CSV crudo. Todo o nada por archivo: 422 si no valida, 409 si cambia un
    revisado. Filas sin uso en la muestra ni en las anclas no se guardan."""
    crudo = await request.body()
    archivo_sha = hashlib.sha256(crudo).hexdigest()
    reemplazos: list[dict[str, str]] = []
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        try:
            texto = crudo.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                HTTP_422, detail={"codigo": "csv_invalido", "errores": ["no es UTF-8"]}
            )
        filas, errores = parsear_enunciados_csv(texto)
        if errores:
            raise HTTPException(HTTP_422, detail={"codigo": "csv_invalido", "errores": errores})
        necesarios = await requeridos(session, estudio.id)
        existentes = await _enunciados(session, estudio.id)
        ignoradas = []
        for fila in filas:
            clave_fila = (fila.fuente, fila.fuente_id)
            if clave_fila not in necesarios:
                ignoradas.append({"tipo": fila.fuente, "id": str(fila.fuente_id)})
                continue
            sha = sha256_texto(fila.texto)
            previo = existentes.get(clave_fila)
            if previo is None:
                session.add(
                    EstudioEnunciado(
                        tenant_id=user.tenant_id,
                        estudio_id=estudio.id,
                        fuente=fila.fuente,
                        fuente_id=fila.fuente_id,
                        archivo_sha256=archivo_sha,
                        cargado_por=user.id,
                        contenido_original_md=fila.texto,
                        sha256_original=sha,
                        alertas=alertas_enunciado(fila.texto),
                    )
                )
            elif previo.sha256_original == sha:
                continue
            elif previo.revisado_at is not None:
                raise _conflicto("enunciado_revisado")
            else:
                reemplazos.append(
                    {
                        "tipo": fila.fuente,
                        "id": str(fila.fuente_id),
                        "sha256_anterior": previo.sha256_original,
                        "sha256_nuevo": sha,
                    }
                )
                previo.contenido_original_md = fila.texto
                previo.sha256_original = sha
                previo.archivo_sha256 = archivo_sha
                previo.alertas = alertas_enunciado(fila.texto)
                previo.cargado_por = user.id
                previo.cargado_at = datetime.now(UTC)
        await session.flush()
        resultado = {"cobertura": await _cobertura(session, estudio.id), "ignoradas": ignoradas}
    for reemplazo in reemplazos:
        logger.info("estudio_enunciado_reemplazado", extra={"estudio": clave, **reemplazo})
    logger.info(
        "estudio_enunciados_cargados",
        extra={"estudio": clave, "archivo_sha256": archivo_sha, "ignoradas": len(ignoradas)},
    )
    return resultado


@router.get("/{clave}/enunciados")
async def estado_enunciados(clave: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, (INVESTIGADOR,))
        cargados = await _enunciados(session, estudio.id)
        return {
            "cobertura": await _cobertura(session, estudio.id),
            "enunciados": [
                _enunciado_out(e)
                for _, e in sorted(cargados.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))
            ],
        }


@router.post("/{clave}/enunciados/{enunciado_id}/revision")
async def revisar_enunciado(
    clave: str,
    enunciado_id: UUID,
    contenido_mostrado_md: str | None = Body(default=None, embed=True),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Aprueba el original (`null`) o guarda una versión editada. Una sola vez."""
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        enunciado = (
            await session.execute(
                select(EstudioEnunciado)
                .where(
                    EstudioEnunciado.id == enunciado_id, EstudioEnunciado.estudio_id == estudio.id
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if enunciado is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Enunciado inexistente")
        if enunciado.revisado_at is not None:
            raise _conflicto("enunciado_revisado")
        mostrado = (
            enunciado.contenido_original_md
            if contenido_mostrado_md is None
            else contenido_mostrado_md
        )
        if not mostrado.strip():
            raise HTTPException(HTTP_422, detail="El texto mostrado no puede quedar vacío")
        enunciado.contenido_mostrado_md = mostrado
        enunciado.sha256_mostrado = sha256_texto(mostrado)
        enunciado.revisado_por = user.id
        enunciado.revisado_at = datetime.now(UTC)
        await session.flush()
        salida = _enunciado_out(enunciado)
    logger.info(
        "estudio_enunciado_revisado",
        extra={
            "estudio": clave,
            "enunciado_id": str(enunciado_id),
            "editado": contenido_mostrado_md is not None,
            "autor_user_id": str(user.id),
        },
    )
    return salida


# ── Etiquetado, cierre y progreso (design D9, D10, D10b) ─────────────────────


async def bloquear_para_codificar(
    session: AsyncSession, user: User, clave: str
) -> tuple[EstudioCodificacion, EstudioMembresia]:
    """Orden de locks de D10b: estudio `FOR SHARE`, después la membresía
    `FOR UPDATE`; relee `cerrada_at` y la vigente bajo lock."""
    estudio, membresia = await require_membresia(
        session, user, clave, (CODIFICADOR,), bloquear_estudio="share"
    )
    membresia = (
        await session.execute(
            select(EstudioMembresia)
            .where(EstudioMembresia.id == membresia.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if membresia.cerrada_at is not None:
        raise _conflicto("codificacion_cerrada")
    return estudio, membresia


async def vigente_congelada(session: AsyncSession, estudio: EstudioCodificacion) -> CodebookVersion:
    version = await esquema_vigente(session, estudio)
    if version is None or version.estado != "congelada" or version.esquema_formulario is None:
        raise _conflicto("codebook_borrador")
    return version


async def _item_de_muestra(
    session: AsyncSession, estudio_id: UUID, item_id: UUID
) -> EstudioMuestra:
    item = (
        await session.execute(
            select(EstudioMuestra).where(
                EstudioMuestra.item_id == item_id, EstudioMuestra.estudio_id == estudio_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ítem inexistente")
    return item


async def _etiqueta_propia(
    session: AsyncSession, membresia_id: UUID, item_id: UUID
) -> EstudioEtiqueta | None:
    return (
        await session.execute(
            select(EstudioEtiqueta).where(
                EstudioEtiqueta.membresia_id == membresia_id,
                EstudioEtiqueta.muestra_item_id == item_id,
            )
        )
    ).scalar_one_or_none()


def etiqueta_out(ev: Evaluacion | None, updated_at: datetime | None) -> dict[str, Any]:
    if ev is None:
        ev = Evaluacion({}, None, None, None, False, None, None)
    return {
        "respuestas": ev.respuestas,
        "regimen": ev.regimen,
        "regimen_regla": ev.regimen_regla,
        "regimen_propuesto": ev.regimen_propuesto,
        "disiente_de_regla": ev.disiente_de_regla,
        "es_frontera": ev.es_frontera,
        "confianza": ev.confianza,
        "notas": ev.notas,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def evaluar_o_rechazar(esquema: dict[str, Any], pedido: Any) -> Evaluacion:
    try:
        return evaluar_pedido(esquema, pedido)
    except PedidoInvalidoError as exc:
        raise HTTPException(
            exc.status, detail={"codigo": "pedido_invalido", "errores": exc.errores}
        )


@router.get("/{clave}/items/{item_id}/mi-etiqueta")
async def mi_etiqueta(
    clave: str, item_id: UUID, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """La etiqueta PROPIA del caller; vacía si todavía no guardó (nunca la de otro)."""
    async with tenant_session(user.tenant_id) as session:
        estudio, membresia = await require_membresia(session, user, clave, (CODIFICADOR,))
        await _item_de_muestra(session, estudio.id, item_id)
        etiqueta = await _etiqueta_propia(session, membresia.id, item_id)
        if etiqueta is None:
            return etiqueta_out(None, None)
        return etiqueta_out(evaluacion_de(etiqueta), etiqueta.updated_at)


@router.put("/{clave}/items/{item_id}/mi-etiqueta")
async def guardar_mi_etiqueta(
    clave: str,
    item_id: UUID,
    pedido: dict[str, Any] = Body(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with tenant_session(user.tenant_id) as session:
        estudio, membresia = await bloquear_para_codificar(session, user, clave)
        version = await vigente_congelada(session, estudio)
        await _item_de_muestra(session, estudio.id, item_id)
        if await enunciados_pendientes(session, estudio.id):
            raise _conflicto("enunciados_pendientes")
        esquema = version.esquema_formulario
        assert esquema is not None
        ev = evaluar_o_rechazar(esquema, pedido)
        ahora = datetime.now(UTC)
        etiqueta = await _etiqueta_propia(session, membresia.id, item_id)
        if etiqueta is None:
            etiqueta = EstudioEtiqueta(
                tenant_id=user.tenant_id,
                membresia_id=membresia.id,
                muestra_item_id=item_id,
                created_at=ahora,
            )
            session.add(etiqueta)
        etiqueta.codebook_version_id = version.id
        etiqueta.traza_version = estudio.traza_version
        etiqueta.respuestas = ev.respuestas
        etiqueta.regimen = ev.regimen
        etiqueta.regimen_regla = ev.regimen_regla
        etiqueta.regimen_propuesto = ev.regimen_propuesto
        etiqueta.es_frontera = ev.es_frontera
        etiqueta.confianza = ev.confianza
        etiqueta.notas = ev.notas
        etiqueta.updated_at = ahora
        await session.flush()
        session.add(
            EstudioEtiquetaHistorial(
                tenant_id=user.tenant_id,
                etiqueta_id=etiqueta.id,
                membresia_id=membresia.id,
                muestra_item_id=item_id,
                snapshot={
                    **etiqueta_out(ev, ahora),
                    "codebook_version_id": str(version.id),
                    "traza_version": estudio.traza_version,
                },
                guardado_at=ahora,
            )
        )
        await session.flush()
        return etiqueta_out(ev, ahora)


@router.post("/{clave}/mi-codificacion/cerrar")
async def cerrar_mi_codificacion(
    clave: str, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    async with tenant_session(user.tenant_id) as session:
        estudio, membresia = await bloquear_para_codificar(session, user, clave)
        version = await vigente_congelada(session, estudio)
        esquema = version.esquema_formulario
        assert esquema is not None
        item_ids = list(
            (
                await session.execute(
                    select(EstudioMuestra.item_id).where(EstudioMuestra.estudio_id == estudio.id)
                )
            ).scalars()
        )
        if not item_ids:
            # Sin muestra no hay nada que cerrar: código propio, no "faltan 0".
            raise _conflicto("sin_muestra")
        propias = {
            e.muestra_item_id: e
            for e in (
                await session.execute(
                    select(EstudioEtiqueta).where(EstudioEtiqueta.membresia_id == membresia.id)
                )
            ).scalars()
        }
        faltantes = []
        for item_id, posicion in orden_codificador(membresia.semilla, item_ids):
            etiqueta = propias.get(UUID(item_id))
            motivos = (
                ["sin_etiqueta"]
                if etiqueta is None
                else faltantes_cierre(esquema, evaluacion_de(etiqueta))
            )
            if motivos:
                faltantes.append({"item_id": item_id, "posicion": posicion, "motivos": motivos})
        if faltantes:
            raise HTTPException(
                HTTP_422,
                detail={"codigo": "incompleta", "faltan": len(faltantes), "faltantes": faltantes},
            )
        membresia.cerrada_at = datetime.now(UTC)
        await session.flush()
        cerrada = membresia.cerrada_at
    logger.info(
        "estudio_codificacion_cerrada",
        extra={"estudio": clave, "membresia_id": str(membresia.id), "alias": membresia.alias},
    )
    return {"cerrada_at": cerrada.isoformat()}


@router.get("/{clave}/progreso")
async def progreso(clave: str, user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Solo cantidades por codificador; nunca valores de etiquetas."""
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, (INVESTIGADOR,))
        version = await esquema_vigente(session, estudio)
        esquema = version.esquema_formulario if version else None
        codificadores = (
            await session.execute(
                select(EstudioMembresia)
                .where(
                    EstudioMembresia.estudio_id == estudio.id, EstudioMembresia.rol == CODIFICADOR
                )
                .order_by(EstudioMembresia.created_at)
            )
        ).scalars()
        salida = []
        for m in codificadores:
            etiquetas = list(
                (
                    await session.execute(
                        select(EstudioEtiqueta).where(EstudioEtiqueta.membresia_id == m.id)
                    )
                ).scalars()
            )
            estados = [estado_etiqueta(e, esquema) for e in etiquetas]
            salida.append(
                {
                    "alias": m.alias,
                    "completos": estados.count("completa"),
                    "parciales": estados.count("parcial"),
                    "con_regimen_propuesto": sum(
                        1 for e in etiquetas if e.regimen_propuesto is not None
                    ),
                    "cerrada": m.cerrada_at is not None,
                    "revocada": m.revocada_at is not None,
                }
            )
        return salida


# ── Anclas (design D11, D4b, D14) ────────────────────────────────────────────


class AnclaIn(BaseModel):
    episode_id: UUID
    uso: Literal["ejemplo", "practica"]
    orden: int = Field(ge=0)
    respuesta_esperada: dict[str, Any]
    explicacion_md: str = ""
    consensuado_por: str = ""


class AnclaEdicion(BaseModel):
    uso: Literal["ejemplo", "practica"] | None = None
    orden: int | None = Field(default=None, ge=0)
    respuesta_esperada: dict[str, Any] | None = None
    explicacion_md: str | None = None
    consensuado_por: str | None = None


def respuesta_guardable(ev: Evaluacion) -> dict[str, Any]:
    """Respuesta esperada tal como se guarda y entra al sha del codebook."""
    return {
        "respuestas": ev.respuestas,
        "regimen": ev.regimen,
        "regimen_propuesto": ev.regimen_propuesto,
        "es_frontera": ev.es_frontera,
        "confianza": ev.confianza,
        "notas": ev.notas,
    }


def ancla_out(
    ancla: EstudioAncla, revisados: dict[tuple[str, UUID], EstudioEnunciado]
) -> dict[str, Any]:
    return {
        "item_id": str(ancla.item_id),
        "episode_id": str(ancla.episode_id),
        "uso": ancla.uso,
        "orden": ancla.orden,
        "respuesta_esperada": ancla.respuesta_esperada,
        "explicacion_md": ancla.explicacion_md,
        "consensuado_por": ancla.consensuado_por,
        "enunciados_listos": _enunciado_del_item(ancla, revisados) is not None,
    }


async def _version_borrador(
    session: AsyncSession, estudio_id: UUID, etiqueta: str
) -> CodebookVersion:
    version = (
        await session.execute(
            select(CodebookVersion)
            .where(CodebookVersion.estudio_id == estudio_id, CodebookVersion.etiqueta == etiqueta)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Versión inexistente")
    if version.estado != "borrador":
        raise _conflicto("version_congelada")
    return version


def _esquema_de(version: CodebookVersion) -> dict[str, Any]:
    if version.esquema_formulario is None:
        raise HTTPException(
            HTTP_422, detail="La versión no tiene esquema: cargarlo antes de las anclas"
        )
    return version.esquema_formulario


async def _ancla_de(session: AsyncSession, version: CodebookVersion, item_id: UUID) -> EstudioAncla:
    ancla = (
        await session.execute(
            select(EstudioAncla).where(
                EstudioAncla.item_id == item_id, EstudioAncla.codebook_version_id == version.id
            )
        )
    ).scalar_one_or_none()
    if ancla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ancla inexistente")
    return ancla


@router.get("/{clave}/codebook/{etiqueta}/anclas")
async def listar_anclas(
    clave: str, etiqueta: str, user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, (INVESTIGADOR,))
        version = (
            await session.execute(
                select(CodebookVersion).where(
                    CodebookVersion.estudio_id == estudio.id, CodebookVersion.etiqueta == etiqueta
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Versión inexistente")
        anclas = (
            await session.execute(
                select(EstudioAncla)
                .where(EstudioAncla.codebook_version_id == version.id)
                .order_by(EstudioAncla.uso, EstudioAncla.orden)
            )
        ).scalars()
        revisados = await _enunciados_revisados(session, estudio.id)
        return [ancla_out(a, revisados) for a in anclas]


@router.post("/{clave}/codebook/{etiqueta}/anclas", status_code=status.HTTP_201_CREATED)
async def crear_ancla(
    clave: str,
    etiqueta: str,
    body: AnclaIn,
    user: User = Depends(get_current_user),
    lector: CTRLector = Depends(get_ctr_lector),
) -> dict[str, Any]:
    """Bajo el lock del estudio: la exclusión con la muestra no se puede violar
    con una carga de muestra concurrente (spec entrenamiento-calibracion)."""
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        version = await _version_borrador(session, estudio.id, etiqueta)
        esquema = _esquema_de(version)
        ev = evaluar_o_rechazar(esquema, body.respuesta_esperada)
        en_muestra = (
            await session.execute(
                select(func.count())
                .select_from(EstudioMuestra)
                .where(
                    EstudioMuestra.estudio_id == estudio.id,
                    EstudioMuestra.episode_id == body.episode_id,
                )
            )
        ).scalar_one()
        if en_muestra:
            raise _conflicto("episodio_en_muestra")
        try:
            episodio = await lector.episodio(user.tenant_id, body.episode_id)
        except EpisodioInexistenteError:
            raise HTTPException(HTTP_422, detail={"codigo": "episodio_inexistente"})
        except CTRNoDisponibleError:
            raise _error_ctr()
        motivo = motivo_rechazo(episodio)
        if motivo:
            raise HTTPException(
                HTTP_422, detail={"codigo": "episodio_no_terminado", "motivo": motivo}
            )
        ancla = EstudioAncla(
            tenant_id=user.tenant_id,
            estudio_id=estudio.id,
            codebook_version_id=version.id,
            episode_id=body.episode_id,
            uso=body.uso,
            orden=body.orden,
            respuesta_esperada=respuesta_guardable(ev),
            explicacion_md=body.explicacion_md,
            consensuado_por=body.consensuado_por,
            **evidencia_fija(episodio),
        )
        session.add(ancla)
        await session.flush()
        salida = {
            **ancla_out(ancla, await _enunciados_revisados(session, estudio.id)),
            "faltantes": faltantes_cierre(esquema, ev),
        }
    logger.info(
        "estudio_ancla_alta",
        extra={"estudio": clave, "etiqueta": etiqueta, "item_id": salida["item_id"]},
    )
    return salida


@router.put("/{clave}/codebook/{etiqueta}/anclas/{item_id}")
async def editar_ancla(
    clave: str,
    etiqueta: str,
    item_id: UUID,
    body: AnclaEdicion,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        version = await _version_borrador(session, estudio.id, etiqueta)
        ancla = await _ancla_de(session, version, item_id)
        esquema = _esquema_de(version)
        if body.respuesta_esperada is not None:
            ancla.respuesta_esperada = respuesta_guardable(
                evaluar_o_rechazar(esquema, body.respuesta_esperada)
            )
        for campo in ("uso", "orden", "explicacion_md", "consensuado_por"):
            valor = getattr(body, campo)
            if valor is not None:
                setattr(ancla, campo, valor)
        await session.flush()
        # Aviso, no rechazo: en borrador se admite incompleta; congelar no (O1).
        # El ancla guardada vale contra este esquema (se acaba de validar o ya
        # estaba); si no vale, el aviso de validez lo da el PUT del esquema.
        motivos = motivos_ancla_para_congelar(esquema, ancla.respuesta_esperada)
        return {
            **ancla_out(ancla, await _enunciados_revisados(session, estudio.id)),
            "faltantes": [m.removeprefix("incompleta: ") for m in motivos],
        }


@router.delete("/{clave}/codebook/{etiqueta}/anclas/{item_id}")
async def borrar_ancla(
    clave: str, etiqueta: str, item_id: UUID, user: User = Depends(get_current_user)
) -> dict[str, str]:
    async with tenant_session(user.tenant_id) as session:
        estudio = await investigador_con_estudio_bloqueado(session, user, clave)
        version = await _version_borrador(session, estudio.id, etiqueta)
        ancla = await _ancla_de(session, version, item_id)
        respuestas = (
            await session.execute(
                select(func.count())
                .select_from(EntrenamientoRespuesta)
                .where(EntrenamientoRespuesta.ancla_id == ancla.item_id)
            )
        ).scalar_one()
        if respuestas:
            raise _conflicto("ancla_con_respuestas")
        await session.delete(ancla)
        await session.flush()
    logger.info(
        "estudio_ancla_baja",
        extra={"estudio": clave, "etiqueta": etiqueta, "item_id": str(item_id)},
    )
    return {"item_id": str(item_id)}


# ── Entrenamiento (design D11) ───────────────────────────────────────────────


async def _anclas_listas(
    session: AsyncSession, estudio: EstudioCodificacion, version: CodebookVersion
) -> list[EstudioAncla]:
    """Anclas de la vigente con sus enunciados cargados y revisados (D14: el
    bloqueo es por ancla, no del entrenamiento entero)."""
    revisados = await _enunciados_revisados(session, estudio.id)
    anclas = (
        await session.execute(
            select(EstudioAncla)
            .where(EstudioAncla.codebook_version_id == version.id)
            .order_by(EstudioAncla.orden, EstudioAncla.item_id)
        )
    ).scalars()
    return [a for a in anclas if _enunciado_del_item(a, revisados) is not None]


@router.get("/{clave}/entrenamiento")
async def entrenamiento(clave: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Codebook vigente (aunque sea borrador), ejemplos con respuesta y
    explicación, y prácticas SIN respuesta ni explicación."""
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, ROLES_ESTUDIO)
        version = await esquema_vigente(session, estudio)
        if version is None:
            return {"codebook": None, "ejemplos": [], "practicas": []}
        anclas = await _anclas_listas(session, estudio, version)
        codebook: VersionOut = version_out(version)
        return {
            "codebook": codebook.model_dump(),
            "ejemplos": [
                {
                    "item_id": str(a.item_id),
                    "orden": a.orden,
                    "respuesta_esperada": a.respuesta_esperada,
                    "explicacion_md": a.explicacion_md,
                }
                for a in anclas
                if a.uso == "ejemplo"
            ],
            "practicas": [
                {"item_id": str(a.item_id), "orden": a.orden} for a in anclas if a.uso == "practica"
            ],
        }


@router.post("/{clave}/entrenamiento/{item_id}/respuesta")
async def responder_practica(
    clave: str,
    item_id: UUID,
    pedido: dict[str, Any] = Body(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Append-only. Registra la vigente (aunque sea borrador) y la versión de la
    traza; recién acá se devuelven la respuesta esperada y la explicación de
    ESTA ancla."""
    async with tenant_session(user.tenant_id) as session:
        estudio, membresia = await require_membresia(session, user, clave, ROLES_ESTUDIO)
        version = await esquema_vigente(session, estudio)
        if version is None or version.esquema_formulario is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="sin_codebook")
        ancla = next(
            (
                a
                for a in await _anclas_listas(session, estudio, version)
                if a.item_id == item_id and a.uso == "practica"
            ),
            None,
        )
        if ancla is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Práctica inexistente")
        ev = evaluar_o_rechazar(version.esquema_formulario, pedido)
        session.add(
            EntrenamientoRespuesta(
                tenant_id=user.tenant_id,
                membresia_id=membresia.id,
                ancla_id=ancla.item_id,
                codebook_version_id=version.id,
                traza_version=estudio.traza_version,
                respuestas=ev.respuestas,
                regimen=ev.regimen,
                regimen_regla=ev.regimen_regla,
                regimen_propuesto=ev.regimen_propuesto,
                es_frontera=ev.es_frontera,
                confianza=ev.confianza,
                notas=ev.notas,
            )
        )
        await session.flush()
        esperada = ancla.respuesta_esperada
        return {
            "regimen": ev.regimen,
            "regimen_regla": ev.regimen_regla,
            "regimen_propuesto": ev.regimen_propuesto,
            "esperada": esperada,
            "explicacion_md": ancla.explicacion_md,
            "coincide": ev.regimen is not None and ev.regimen == esperada.get("regimen"),
        }


# ── Exportación (design D12) ─────────────────────────────────────────────────

_EXTRA_ETIQUETAS = [
    "episode_id",
    "item_id",
    "alias",
    "membresia_id",
    "semilla",
    "posicion",
    "codebook_etiqueta",
    "codebook_sha256",
    "traza_version",
]
_DESPUES_ETIQUETAS = [
    "enunciado_tp_sha256_original",
    "enunciado_tp_sha256_mostrado",
    "enunciado_tp_archivo_sha256",
    "enunciado_ejercicio_sha256_original",
    "enunciado_ejercicio_sha256_mostrado",
    "enunciado_ejercicio_archivo_sha256",
    "created_at",
    "updated_at",
    "cerrada_at",
    "revocada_at",
]
_EXTRA_ENTRENAMIENTO = [
    "membresia_id",
    "alias",
    "ancla_id",
    "episode_id",
    "uso",
    "codebook_etiqueta",
    "codebook_sha256",
    "traza_version",
]
_DESPUES_ENTRENAMIENTO = ["respondida_at", "revocada_at"]
_COLUMNAS_HISTORIAL = [
    "historial_id",
    "etiqueta_id",
    "membresia_id",
    "alias",
    "item_id",
    "episode_id",
    "guardado_at",
    "snapshot",
]


def _iso(valor: datetime | None) -> str | None:
    return valor.isoformat() if valor else None


def _dims(esquema: dict[str, Any] | None) -> list[str]:
    return [d["clave"] for d in (esquema or {}).get("dimensiones", [])]


def _shas_enunciado(prefijo: str, enunciado: EstudioEnunciado | None) -> dict[str, str | None]:
    return {
        f"enunciado_{prefijo}_sha256_original": enunciado.sha256_original if enunciado else None,
        f"enunciado_{prefijo}_sha256_mostrado": enunciado.sha256_mostrado if enunciado else None,
        f"enunciado_{prefijo}_archivo_sha256": enunciado.archivo_sha256 if enunciado else None,
    }


async def _versiones(session: AsyncSession, estudio_id: UUID) -> dict[UUID, CodebookVersion]:
    filas = (
        await session.execute(
            select(CodebookVersion).where(CodebookVersion.estudio_id == estudio_id)
        )
    ).scalars()
    return {v.id: v for v in filas}


async def _membresias(session: AsyncSession, estudio_id: UUID) -> dict[UUID, EstudioMembresia]:
    filas = (
        await session.execute(
            select(EstudioMembresia).where(EstudioMembresia.estudio_id == estudio_id)
        )
    ).scalars()
    return {m.id: m for m in filas}


async def _filas_etiquetas(
    session: AsyncSession, estudio: EstudioCodificacion
) -> tuple[list[str], list[dict[str, Any]]]:
    versiones = await _versiones(session, estudio.id)
    membresias = await _membresias(session, estudio.id)
    muestra = {
        m.item_id: m
        for m in (
            await session.execute(
                select(EstudioMuestra).where(EstudioMuestra.estudio_id == estudio.id)
            )
        ).scalars()
    }
    enunciados = await _enunciados(session, estudio.id)
    vigente = versiones.get(estudio.codebook_vigente_id) if estudio.codebook_vigente_id else None
    dims = _dims(vigente.esquema_formulario if vigente else None)
    posiciones = {
        mid: dict(orden_codificador(m.semilla, list(muestra))) for mid, m in membresias.items()
    }
    etiquetas = (
        await session.execute(
            select(EstudioEtiqueta)
            .where(EstudioEtiqueta.membresia_id.in_(list(membresias)))
            .order_by(EstudioEtiqueta.membresia_id, EstudioEtiqueta.id)
        )
    ).scalars()
    filas = []
    for e in etiquetas:
        m = membresias[e.membresia_id]
        item = muestra[e.muestra_item_id]
        version = versiones[e.codebook_version_id]
        registro = {
            "episode_id": str(item.episode_id),
            "item_id": str(item.item_id),
            "alias": m.alias,
            "membresia_id": str(m.id),
            "semilla": m.semilla,
            "posicion": posiciones[m.id].get(str(item.item_id)),
            "codebook_etiqueta": version.etiqueta,
            "codebook_sha256": version.contenido_sha256,
            "traza_version": e.traza_version,
            "respuestas": e.respuestas,
            "regimen": e.regimen,
            "regimen_regla": e.regimen_regla,
            "regimen_propuesto": e.regimen_propuesto,
            "es_frontera": e.es_frontera,
            "confianza": e.confianza,
            "notas": e.notas,
            **_shas_enunciado("tp", enunciados.get(("tp", item.problema_id))),
            **_shas_enunciado(
                "ejercicio",
                enunciados.get(("ejercicio", item.ejercicio_id)) if item.ejercicio_id else None,
            ),
            "created_at": _iso(e.created_at),
            "updated_at": _iso(e.updated_at),
            "cerrada_at": _iso(m.cerrada_at),
            "revocada_at": _iso(m.revocada_at),
        }
        filas.append(aplanar_respuesta(_EXTRA_ETIQUETAS, dims, registro, _DESPUES_ETIQUETAS))
    return columnas_respuesta(_EXTRA_ETIQUETAS, dims, _DESPUES_ETIQUETAS), filas


async def _filas_entrenamiento(
    session: AsyncSession, estudio: EstudioCodificacion
) -> tuple[list[str], list[dict[str, Any]]]:
    versiones = await _versiones(session, estudio.id)
    membresias = await _membresias(session, estudio.id)
    anclas = {
        a.item_id: a
        for a in (
            await session.execute(select(EstudioAncla).where(EstudioAncla.estudio_id == estudio.id))
        ).scalars()
    }
    respuestas = list(
        (
            await session.execute(
                select(EntrenamientoRespuesta)
                .where(EntrenamientoRespuesta.membresia_id.in_(list(membresias)))
                .order_by(EntrenamientoRespuesta.id)
            )
        ).scalars()
    )
    dims: list[str] = []
    for r in respuestas:
        for d in _dims(versiones[r.codebook_version_id].esquema_formulario):
            if d not in dims:
                dims.append(d)
    filas = []
    for r in respuestas:
        m = membresias[r.membresia_id]
        ancla = anclas[r.ancla_id]
        version = versiones[r.codebook_version_id]
        registro = {
            "membresia_id": str(m.id),
            "alias": m.alias,
            "ancla_id": str(ancla.item_id),
            "episode_id": str(ancla.episode_id),
            "uso": ancla.uso,
            "codebook_etiqueta": version.etiqueta,
            "codebook_sha256": version.contenido_sha256,
            "traza_version": r.traza_version,
            "respuestas": r.respuestas,
            "regimen": r.regimen,
            "regimen_regla": r.regimen_regla,
            "regimen_propuesto": r.regimen_propuesto,
            "es_frontera": r.es_frontera,
            "confianza": r.confianza,
            "notas": r.notas,
            "respondida_at": _iso(r.respondida_at),
            "revocada_at": _iso(m.revocada_at),
        }
        filas.append(
            aplanar_respuesta(_EXTRA_ENTRENAMIENTO, dims, registro, _DESPUES_ENTRENAMIENTO)
        )
    return columnas_respuesta(_EXTRA_ENTRENAMIENTO, dims, _DESPUES_ENTRENAMIENTO), filas


async def _filas_historial(
    session: AsyncSession, estudio: EstudioCodificacion
) -> tuple[list[str], list[dict[str, Any]]]:
    membresias = await _membresias(session, estudio.id)
    muestra = {
        m.item_id: m
        for m in (
            await session.execute(
                select(EstudioMuestra).where(EstudioMuestra.estudio_id == estudio.id)
            )
        ).scalars()
    }
    historial = (
        await session.execute(
            select(EstudioEtiquetaHistorial)
            .where(EstudioEtiquetaHistorial.membresia_id.in_(list(membresias)))
            .order_by(EstudioEtiquetaHistorial.id)
        )
    ).scalars()
    filas = []
    for h in historial:
        item = muestra.get(h.muestra_item_id)
        filas.append(
            {
                "historial_id": h.id,
                "etiqueta_id": h.etiqueta_id,
                "membresia_id": str(h.membresia_id),
                "alias": membresias[h.membresia_id].alias,
                "item_id": str(h.muestra_item_id),
                "episode_id": str(item.episode_id) if item else None,
                "guardado_at": _iso(h.guardado_at),
                "snapshot": json.dumps(h.snapshot, sort_keys=True, ensure_ascii=False),
            }
        )
    return list(_COLUMNAS_HISTORIAL), filas


@router.get("/{clave}/exportacion")
async def exportar(
    clave: str,
    contenido: Literal["etiquetas", "entrenamiento", "historial"] = Query(...),
    formato: Literal["csv", "json"] = Query(...),
    user: User = Depends(get_current_user),
) -> Response:
    """Solo investigador del estudio. Sin emails ni contenido de episodios."""
    async with tenant_session(user.tenant_id) as session:
        estudio, _ = await require_membresia(session, user, clave, (INVESTIGADOR,))
        armar = {
            "etiquetas": _filas_etiquetas,
            "entrenamiento": _filas_entrenamiento,
            "historial": _filas_historial,
        }[contenido]
        columnas, filas = await armar(session, estudio)
    logger.info(
        "estudio_exportacion",
        extra={
            "estudio": clave,
            "contenido": contenido,
            "formato": formato,
            "autor_user_id": str(user.id),
            "filas": len(filas),
            "momento": datetime.now(UTC).isoformat(),
        },
    )
    if formato == "json":
        return JSONResponse(filas)
    return PlainTextResponse(a_csv(columnas, filas), media_type="text/csv")
