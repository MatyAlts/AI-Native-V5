"""El payload de Active-IA, armado con datos REALES del banco.

Este archivo existe porque el mismo mecanismo produjo un hallazgo en tres
revisiones seguidas: **el fixture no coincidia con el dato real**.

- Vuelta 2: la sesion mockeada no veia que el UPDATE no se emitia.
- Vuelta 3: `entrega.artefactos = []` explicito tapaba un `MissingGreenlet`.
- Vuelta 4: `RUBRICA = [{...}]` (una lista) tapaba un doble anidado, cuando
  las 54 rubricas del banco son objetos `{"criterios": [...]}`.

Un test unitario no puede atrapar esa clase de bug: el fixture lo escribe el
mismo que escribio el codigo, con la misma idea equivocada de la forma del
dato. Estos tests leen del banco de verdad.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration -v

Sin esa env var se SKIPEAN. Son de solo lectura: no escriben nada.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from evaluation_service.services.activeia_sync import (
    _payload_ejercicio,
    _test_cases_para_activeia,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real"
)


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _ejercicios_reales(db: AsyncSession, limite: int = 20) -> list[dict[str, Any]]:
    rows = await db.execute(
        text(
            "SELECT id, titulo, enunciado_md, rubrica, test_cases FROM ejercicios "
            "WHERE rubrica IS NOT NULL LIMIT :n"
        ),
        {"n": limite},
    )
    return [
        {
            "ejercicio_id": r[0],
            "titulo": r[1],
            "enunciado_md": r[2],
            "rubrica": r[3],
            "test_cases": r[4],
            "peso_en_tp": 1.0,
            "orden": 1,
        }
        for r in rows.all()
    ]


class TestLaRubricaViajaConLaFormaQuePideElContrato:
    async def test_criterios_es_una_lista_y_no_un_dict(self, db: AsyncSession) -> None:
        """El bug: `ejercicios.rubrica` YA es `{"criterios": [...]}`, y el
        codigo la envolvia otra vez produciendo `{"criterios": {"criterios":
        [...]}}`. Del otro lado el parser encuentra un dict donde espera la
        lista: 422 en el mejor caso, un TP con CERO criterios en el peor — y
        una rubrica vacia corrige contra nada y devuelve un numero igual.
        """
        ejercicios = await _ejercicios_reales(db)
        if not ejercicios:
            pytest.skip("la base no tiene ejercicios con rubrica")

        for ej in ejercicios:
            p = _payload_ejercicio(ej)
            criterios = p["rubrica"].get("criterios")
            assert isinstance(criterios, list), (
                f"ejercicio {ej['ejercicio_id']}: `criterios` es "
                f"{type(criterios).__name__}, el contrato pide una lista"
            )

    async def test_cada_criterio_tiene_las_claves_del_contrato(self, db: AsyncSession) -> None:
        ejercicios = await _ejercicios_reales(db)
        if not ejercicios:
            pytest.skip("la base no tiene ejercicios con rubrica")

        for ej in ejercicios:
            for c in _payload_ejercicio(ej)["rubrica"]["criterios"]:
                assert "nombre" in c, f"criterio sin `nombre`: {c}"
                assert "puntaje_max" in c, f"criterio sin `puntaje_max`: {c}"


class TestLosTestCasesRealesViajanBien:
    async def test_ningun_caso_oculto_manda_su_salida_esperada(self, db: AsyncSession) -> None:
        """El PDF de Active-IA se le entrega al alumno. Un caso oculto cuya
        salida esperada viajo puede terminar citado ahi, y deja de estar
        oculto para toda la cohorte."""
        rows = await db.execute(text("SELECT test_cases FROM ejercicios WHERE test_cases != '[]'"))
        vistos_ocultos = 0
        for (tcs,) in rows.all():
            for caso in _test_cases_para_activeia(tcs):
                if caso["es_publico"] is False:
                    vistos_ocultos += 1
                    assert "salida_esperada" not in caso, f"salio la salida de {caso['id']}"
                    assert "asercion" not in caso
        assert vistos_ocultos > 0, "la base no tiene casos ocultos: el test no probo nada"

    async def test_los_tres_tipos_del_banco_viajan_con_su_tipo(self, db: AsyncSession) -> None:
        """El banco tiene `stdin_stdout`, `pytest_assert` y `junit_assert`.
        Aplanarlos a entrada/salida hacia que un assert viajara como si fuera
        una entrada, con salida vacia."""
        rows = await db.execute(
            text("SELECT DISTINCT tc->>'type' FROM ejercicios, jsonb_array_elements(test_cases) tc")
        )
        tipos_en_banco = {r[0] for r in rows.all() if r[0]}
        assert tipos_en_banco, "la base no tiene test cases tipados"

        for tipo in tipos_en_banco:
            caso = _test_cases_para_activeia(
                [{"id": "x", "name": "n", "type": tipo, "code": "c", "is_public": True}]
            )[0]
            assert caso["tipo"] == tipo
            if tipo == "stdin_stdout":
                assert "entrada" in caso
            else:
                assert "entrada" not in caso, f"un {tipo} viajo como entrada/salida"
                assert caso["asercion"] == "c"

    async def test_el_payload_entero_es_json_serializable(self, db: AsyncSession) -> None:
        """Lo que no serializa no viaja. `Decimal` y `datetime` del banco son
        los sospechosos habituales."""
        import json

        ejercicios = await _ejercicios_reales(db)
        if not ejercicios:
            pytest.skip("la base no tiene ejercicios con rubrica")
        for ej in ejercicios:
            json.dumps(_payload_ejercicio(ej))
