"""Sincronización de rúbricas hacia Active-IA (tareas 2.11 y 2.12).

La corrección es POR EJERCICIO (design D1), así que del otro lado hace falta
una rúbrica por ejercicio. Se empuja **el TP entero con sus ejercicios
anidados**, no N rúbricas sueltas: es el contrato de
`docs/research/activeia-cambios-pedidos.md` 3.3, y sin el TP que los agrupe
los ejercicios quedarían huérfanos del otro lado.

`rubrica_hash` guarda el hash de **todo lo que se envió** de ese ejercicio —
rúbrica, enunciado, test cases y peso—, no sólo de la rúbrica. Los cuatro
cambian lo que el motor corrige: si el hash cubriera sólo la rúbrica, editar
la consigna dejaría el ejercicio en verde "Sincronizado" para siempre mientras
Active-IA sigue con el enunciado viejo.

Y **una rúbrica equivocada no da una nota floja: corrige otra cosa**. Un TP de
listas corregido con la rúbrica de condicionales produce un número plausible y
sin sentido, y ese número termina en el legajo de una persona.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from evaluation_service.config import settings
from evaluation_service.models.activeia import ActiveIARubricaEjercicio
from evaluation_service.services.activeia_client import ActiveIAClient, ActiveIAError

log = structlog.get_logger()


class EstadoSync(StrEnum):
    """Qué tan confiable es la rúbrica de allá para corregir ESTE ejercicio."""

    SINCRONIZADO = "sincronizado"
    DESACTUALIZADO = "desactualizado"
    SIN_SINCRONIZAR = "sin_sincronizar"
    # El ejercicio no tiene rúbrica local. No es un problema de sync: no hay
    # nada contra qué corregir, y decirlo así evita que se lea como un fallo.
    SIN_RUBRICA = "sin_rubrica"


@dataclass(frozen=True)
class EstadoEjercicio:
    ejercicio_id: UUID
    titulo: str
    estado: EstadoSync
    rubrica_id: str | None = None
    sincronizado_at: datetime | None = None
    simulado: bool = False


def rubrica_hash(rubrica: Any) -> str:
    """Hash canónico de una rúbrica local.

    Misma fórmula que el resto del repo (`chunks_used_hash`, `self_hash` del
    CTR): `sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`.
    `ensure_ascii=False` no es cosmético — sin eso el hash cambia según si la
    rúbrica tiene tildes o ñ, y las nuestras están en castellano.
    """
    canonical = json.dumps(rubrica, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _ejercicios_de_tp(db: AsyncSession, tarea_practica_id: UUID) -> list[dict[str, Any]]:
    """Los ejercicios del TP con su rúbrica, sus test cases y su peso.

    Lectura por SQL y no importando el modelo de `academic-service`: las
    tablas viven en la misma DB pero son de otro servicio, mismo criterio que
    la consulta a `usuarios_comision`.
    """
    rows = await db.execute(
        text(
            "SELECT e.id, e.titulo, e.enunciado_md, e.rubrica, e.test_cases, "
            "       tp.peso_en_tp, tp.orden "
            "FROM tp_ejercicios tp "
            "JOIN ejercicios e ON e.id = tp.ejercicio_id "
            "WHERE tp.tarea_practica_id = :tp ORDER BY tp.orden"
        ),
        {"tp": str(tarea_practica_id)},
    )
    return [
        {
            "ejercicio_id": r[0],
            "titulo": r[1],
            "enunciado_md": r[2],
            "rubrica": r[3],
            "test_cases": r[4],
            "peso_en_tp": float(r[5]) if r[5] is not None else None,
            "orden": r[6],
        }
        for r in rows.all()
    ]


async def _tarea_practica(db: AsyncSession, tarea_practica_id: UUID) -> dict[str, Any] | None:
    """La TP con su materia, para poder anidar los ejercicios debajo.

    La materia sale de la comisión: `tareas_practicas` no la lleva, y sin ella
    el TP no tiene dónde aterrizar del otro lado (el modelo de Active-IA está
    enraizado en materia).
    """
    row = await db.execute(
        text(
            "SELECT t.id, t.titulo, c.materia_id "
            "FROM tareas_practicas t JOIN comisiones c ON c.id = t.comision_id "
            "WHERE t.id = :tp"
        ),
        {"tp": str(tarea_practica_id)},
    )
    r = row.first()
    return {"id": r[0], "titulo": r[1], "materia_id": r[2]} if r else None


async def _vinculos(
    db: AsyncSession, tenant_id: UUID, ejercicio_ids: list[UUID]
) -> dict[UUID, ActiveIARubricaEjercicio]:
    if not ejercicio_ids:
        return {}
    rows = await db.execute(
        select(ActiveIARubricaEjercicio).where(
            and_(
                ActiveIARubricaEjercicio.tenant_id == tenant_id,
                ActiveIARubricaEjercicio.ejercicio_id.in_(ejercicio_ids),
            )
        )
    )
    return {v.ejercicio_id: v for v in rows.scalars().all()}


async def estado_de_sincronizacion(
    db: AsyncSession, tenant_id: UUID, tarea_practica_id: UUID
) -> list[EstadoEjercicio]:
    """Estado por ejercicio, SIN contactar a Active-IA.

    Se compara el hash guardado contra el de la rúbrica de hoy. No se lee la
    rúbrica remota: hoy no se puede (403 con rol tutor), y aunque se pudiera,
    lo que interesa es si LO NUESTRO cambió desde el último push.
    """
    tp = await _tarea_practica(db, tarea_practica_id)
    ejercicios = await _ejercicios_de_tp(db, tarea_practica_id)
    vinculos = await _vinculos(db, tenant_id, [e["ejercicio_id"] for e in ejercicios])

    out: list[EstadoEjercicio] = []
    for ej in ejercicios:
        vinculo = vinculos.get(ej["ejercicio_id"])
        if not ej["rubrica"]:
            estado = EstadoSync.SIN_RUBRICA
        elif vinculo is None:
            estado = EstadoSync.SIN_SINCRONIZAR
        elif vinculo.rubrica_hash != hash_de_lo_enviado(ej, tp):
            estado = EstadoSync.DESACTUALIZADO
        else:
            estado = EstadoSync.SINCRONIZADO

        out.append(
            EstadoEjercicio(
                ejercicio_id=ej["ejercicio_id"],
                titulo=ej["titulo"],
                estado=estado,
                rubrica_id=vinculo.rubrica_id if vinculo else None,
                sincronizado_at=vinculo.sincronizado_at if vinculo else None,
                # Un `rubrica_id` con prefijo MOCK- salió del simulador y no
                # existe del otro lado. Se propaga para que la UI lo diga.
                simulado=bool(vinculo and vinculo.rubrica_id.startswith("MOCK-")),
            )
        )
    return out


def _test_cases_para_activeia(test_cases: Any) -> list[dict[str, Any]]:
    """Traduce los test cases al vocabulario del contrato pedido.

    Tres cosas que no son cosméticas:

    1. **Las claves.** Las nuestras son `name/expected/is_public`; las pedidas,
       `nombre/salida_esperada/es_publico`. Mandando las nuestras, el otro lado
       lee `es_publico` como ausente y **trata un caso oculto como público**.

    2. **El `tipo` viaja.** El banco tiene tres (`stdin_stdout`,
       `pytest_assert`, `junit_assert`) y en los dos de assert `code` es una
       ASERCIÓN, no una entrada, y `expected` es `null`. Aplanarlos todos a
       entrada/salida hacía que el motor leyera *"entrada:
       `assert suma(2,3)==5` / salida esperada: (vacía)"* y evaluara "el
       programa funciona" contra eso — produciendo un número plausible y sin
       sentido, que es el modo de fallo medido de este motor.

    3. **A los ocultos se les saca la salida esperada.** El motor sigue
       sabiendo que existen, cuántos son y cómo se llaman, que es lo que
       aportan al enunciado. Lo que no puede citar en el PDF del alumno es lo
       que nunca recibió. Pedir por documento que no los cite es depender de
       que un tercero cumpla un párrafo — y de ese motor ya está medido que no
       honra las reglas declaradas en su propia rúbrica (aplicó 0% donde la
       rúbrica pedía una penalización del 30%).
    """
    if not isinstance(test_cases, list):
        return []
    out: list[dict[str, Any]] = []
    for tc in test_cases:
        if not isinstance(tc, dict):
            continue
        # `is not False` y no `or True`: un caso SIN la clave se trata como
        # público (el default del banco), pero uno con `False` explícito nunca
        # se vuelve público por un `or`.
        es_publico = tc.get("is_public", tc.get("es_publico", True)) is not False
        tipo = tc.get("type") or tc.get("tipo") or "stdin_stdout"
        caso: dict[str, Any] = {
            "id": tc.get("id"),
            "nombre": tc.get("name") or tc.get("nombre"),
            "tipo": tipo,
            "es_publico": es_publico,
        }
        if tipo == "stdin_stdout":
            # La ENTRADA tampoco viaja si el caso es oculto (2026-08-20).
            # Antes iba siempre, y era más de lo que declaramos en el documento
            # de integración: ahí dice que de un caso oculto mandamos "el id, el
            # nombre y el tipo", nada más.
            #
            # No es formalismo. El PDF de devolución se le entrega al alumno, y
            # con la entrada a la vista —"probamos con 3 estudiantes y cupo
            # 2"— la regla que el caso oculto codifica queda dicha. Un caso
            # oculto citado deja de estar oculto para toda la cohorte, no sólo
            # para quien lo leyó.
            if es_publico:
                caso["entrada"] = tc.get("code") or tc.get("entrada") or ""
                caso["salida_esperada"] = tc.get("expected") or tc.get("salida_esperada") or ""
        # En los de assert el código ES el criterio: no hay entrada ni
        # salida que mandar, y meterlo en `entrada` sería mentir sobre qué
        # es. Sólo va si el caso es público.
        elif es_publico:
            caso["asercion"] = tc.get("code") or tc.get("asercion") or ""
        out.append(caso)
    return out


def _payload_ejercicio(ej: dict[str, Any]) -> dict[str, Any]:
    """Un ejercicio dentro del TP, con las claves del contrato pedido.

    Va el enunciado además de la rúbrica: sin la consigna, el motor evalúa
    los criterios contra un código que no sabe qué tenía que hacer.
    """
    return {
        "external_ref": str(ej["ejercicio_id"]),
        "orden": ej["orden"],
        "titulo": ej["titulo"],
        "enunciado_md": ej["enunciado_md"],
        # `peso` y no `peso_en_tp`: así lo pide el contrato.
        "peso": ej["peso_en_tp"],
        # `ej["rubrica"]` YA es `{"criterios": [...]}` — así están las 54
        # rúbricas cargadas del banco, sin excepción. Envolverla otra vez
        # producía `{"criterios": {"criterios": [...]}}`, y del otro lado el
        # parser encontraría un dict donde espera la lista de criterios: en el
        # mejor caso un 422, en el peor un TP sincronizado con CERO criterios
        # — y una rúbrica vacía corrige contra nada y devuelve un número igual.
        "rubrica": ej["rubrica"],
        "test_cases": _test_cases_para_activeia(ej["test_cases"]),
    }


def _payload_tp(tp: dict[str, Any], ejercicios: list[dict[str, Any]]) -> dict[str, Any]:
    """El TP entero con sus ejercicios ANIDADOS.

    Uno solo y no N sueltos, como pide `activeia-cambios-pedidos.md` 3.3. Un
    push por ejercicio dejaría los ejercicios sin TP que los agrupe, y del
    otro lado la corrección no sabría que son partes de una misma entrega.

    La materia viaja por `external_ref` y no por su id numérico: la sección
    3.2 del mismo documento pone el `external_ref` como el punto por donde
    cruza toda la integración, y pedir un `materia_id` de Active-IA obligaría
    a mantener acá un mapeo de ids ajenos que vencen sin avisar — el problema
    que ese documento viene a resolver.
    """
    return {
        "external_ref": str(tp["id"]),
        "materia_external_ref": str(tp["materia_id"]) if tp["materia_id"] else None,
        "titulo": tp["titulo"],
        "ejercicios": [_payload_ejercicio(e) for e in ejercicios if e["rubrica"]],
    }


def hash_de_lo_enviado(ej: dict[str, Any], tp: dict[str, Any] | None = None) -> str:
    """Hash de TODO lo que se le manda a Active-IA de este ejercicio.

    No sólo de la rúbrica. El push lleva también el enunciado, los test cases
    y el peso, y los tres cambian lo que el motor corrige: si el hash sólo
    cubriera la rúbrica, editar la consigna dejaría el ejercicio en verde
    "Sincronizado" para siempre mientras Active-IA sigue con el enunciado
    viejo. Se hashea el payload, que es exactamente lo que viajó.
    """
    payload: dict[str, Any] = {"ejercicio": _payload_ejercicio(ej)}
    if tp is not None:
        # El header del TP también entra: mover el TP de materia cambia dónde
        # aterriza la corrección, y sin esto la vista seguiría en verde.
        payload["tp"] = {
            "titulo": tp["titulo"],
            "materia_external_ref": str(tp["materia_id"]) if tp["materia_id"] else None,
        }
    return rubrica_hash(payload)


async def sincronizar_tp(
    db: AsyncSession,
    cliente: ActiveIAClient,
    tenant_id: UUID,
    tarea_practica_id: UUID,
) -> list[EstadoEjercicio]:
    """Empuja el TP con sus ejercicios anidados y guarda el vínculo de cada uno.

    Los ejercicios SIN rúbrica local no se mandan: una rúbrica vacía del otro
    lado corregiría contra nada y devolvería un número igual.
    """
    if not settings.activeia_sync_rubricas_enabled:
        raise ActiveIAError("La sincronización de rúbricas está desactivada en este entorno.")

    tp = await _tarea_practica(db, tarea_practica_id)
    if tp is None:
        raise ActiveIAError("La tarea práctica no existe.")

    ejercicios = await _ejercicios_de_tp(db, tarea_practica_id)
    con_rubrica = [e for e in ejercicios if e["rubrica"]]
    if not con_rubrica:
        raise ActiveIAError(
            "Ningún ejercicio de este trabajo práctico tiene rúbrica cargada. "
            "Sin rúbrica no hay contra qué corregir."
        )

    resp = await cliente.crear_o_actualizar_tp(
        external_ref=str(tarea_practica_id), payload=_payload_tp(tp, ejercicios)
    )

    # La respuesta trae el id de cada ejercicio, indexado por SU `external_ref`
    # (nuestro UUID). Es la única forma de saber con qué rúbrica se corrige
    # cada uno: emparejar por orden o por título sería adivinar, y una rúbrica
    # equivocada no da una nota floja — corrige otra cosa.
    por_ref = {
        str(e.get("external_ref")): e for e in resp.get("ejercicios", []) if isinstance(e, dict)
    }

    vinculos = await _vinculos(db, tenant_id, [e["ejercicio_id"] for e in con_rubrica])
    ahora = datetime.now(UTC)

    for ej in con_rubrica:
        ref = str(ej["ejercicio_id"])
        devuelto = por_ref.get(ref)
        rid = str(devuelto.get("rubrica_id") or devuelto.get("id") or "") if devuelto else ""
        if not rid:
            # Sin id no se puede corregir ese ejercicio, y marcarlo
            # sincronizado sería mentir. Queda como estaba.
            log.warning("activeia_sync_ejercicio_sin_id", ejercicio_id=ref)
            continue

        # El hash se guarda DESPUÉS del push. Guardarlo antes marcaría como
        # sincronizado un ejercicio cuya rúbrica no llegó.
        vinculo = vinculos.get(ej["ejercicio_id"])
        if vinculo is None:
            vinculo = ActiveIARubricaEjercicio(
                tenant_id=tenant_id, ejercicio_id=ej["ejercicio_id"], external_ref=ref
            )
            db.add(vinculo)
        vinculo.rubrica_id = rid
        vinculo.rubrica_hash = hash_de_lo_enviado(ej, tp)
        vinculo.sincronizado_at = ahora

    await db.flush()
    return await estado_de_sincronizacion(db, tenant_id, tarea_practica_id)
