"""Que SOBREVIVE despues del olvido, contra Postgres real.

La direccion de la pregunta es lo que hace este archivo distinto de los 7 de
`packages/platform-ops`. Esos preguntan *"se borro lo que dije que iba a
borrar?"* y pasan todos, porque lo que se borra se borra bien. La pregunta que
no hacia nadie es la inversa, y es la unica que importa en un feature de
cumplimiento: **despues del olvido, que queda?**

Con esa pregunta aparecieron cuatro campos de `correcciones_ia` que un informe
de olvido exitoso dejaba intactos: el mismo `artefacto_sha256` que se acababa
de borrar de `entregas`, la salida real del programa del alumno en
`tests_snapshot`, la devolucion criterio por criterio en `desglose`, y una
`pdf_storage_key` apuntando a un objeto borrado que hacia que la API siguiera
diciendo `tiene_pdf: true`.

Correr:
    EVAL_TEST_DB_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/academic_main \
        uv run pytest apps/evaluation-service/tests/integration/test_olvido_db.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from evaluation_service.config import settings
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.models.entregas import Entrega, EntregaArtefacto
from evaluation_service.services.olvido import OlvidoCorreccionAdapter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DSN = os.environ.get("EVAL_TEST_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="Sin EVAL_TEST_DB_URL: estos tests necesitan Postgres real"
)

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

# Lo que el programa del alumno imprimio. Lleva datos personales a proposito:
# es el escenario que importa.
SALIDA_DEL_ALUMNO = "Hola, me llamo Juan Perez y mi DNI es 30111222"
DEVOLUCION = "La clase Alumno de Juan expone el DNI"


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    settings.academic_db_url = _DSN or ""
    engine = create_async_engine(_DSN or "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(TENANT)}
        )
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _sembrar(db: AsyncSession, alumno: UUID) -> tuple[UUID, UUID]:
    """Una entrega con artefacto y una correccion con TODO lo derivado."""
    tp = (await db.execute(text("SELECT id FROM tareas_practicas LIMIT 1"))).scalar_one_or_none()
    com = (await db.execute(text("SELECT id FROM comisiones LIMIT 1"))).scalar_one_or_none()
    if tp is None or com is None:
        pytest.skip("la base no tiene TPs/comisiones")

    entrega = Entrega(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=tp,
        student_pseudonym=alumno,
        comision_id=com,
        estado="submitted",
        ejercicio_estados=[],
    )
    entrega.artefacto_sha256 = "f" * 64
    db.add(entrega)
    await db.flush()

    db.add(
        EntregaArtefacto(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            entrega_id=entrega.id,
            orden=1,
            codigo="class Main { /* el codigo del alumno */ }",
            language="java",
            sha256="f" * 64,
        )
    )
    correccion = CorreccionIA(
        tenant_id=TENANT,
        entrega_id=entrega.id,
        orden=1,
        disparado_por=uuid.uuid4(),
        rubrica_id="r1",
        estado="done",
        nota_100=Decimal("87.00"),
        artefacto_sha256="f" * 64,
        tests_snapshot={"casos": [{"nombre": "t1", "salida_obtenida": SALIDA_DEL_ALUMNO}]},
        desglose=[{"nombre": "Encapsulamiento", "puntaje": 8, "comentario": DEVOLUCION}],
    )
    correccion.pdf_storage_key = "correcciones/k/abc.pdf"
    db.add(correccion)
    await db.flush()
    return entrega.id, correccion.id


class TestQueSobrevive:
    async def test_no_queda_NADA_que_describa_el_codigo_del_alumno(self, db: AsyncSession) -> None:
        """La pregunta invertida. Es la que produjo el hallazgo."""
        alumno = uuid.uuid4()
        entrega_id, correccion_id = await _sembrar(db, alumno)
        adapter = OlvidoCorreccionAdapter(db, TENANT)

        await adapter.delete_artefactos_by_student(alumno)
        await adapter.update_correcciones_pseudonym(alumno, uuid.uuid4())
        await db.flush()

        fila = (
            await db.execute(
                text(
                    "SELECT artefacto_sha256, tests_snapshot::text, desglose::text, "
                    "       pdf_storage_key "
                    "FROM correcciones_ia WHERE id = :i"
                ),
                {"i": str(correccion_id)},
            )
        ).one()

        assert fila[0] == "", f"sobrevivio el hash del artefacto: {fila[0]}"
        assert SALIDA_DEL_ALUMNO not in fila[1], "sobrevivio la salida del programa del alumno"
        assert DEVOLUCION not in fila[2], "sobrevivio la devolucion sobre su trabajo"
        assert fila[3] is None, "la key del PDF quedo apuntando a un objeto borrado"

        # Y el artefacto y su hash en `entregas`, que ya estaban cubiertos.
        n = (
            await db.execute(
                text("SELECT count(*) FROM entrega_artefactos WHERE entrega_id = :i"),
                {"i": str(entrega_id)},
            )
        ).scalar_one()
        assert n == 0

    async def test_la_fila_de_la_correccion_SE_CONSERVA(self, db: AsyncSession) -> None:
        """Que hubo una correccion, cuando y con que rubrica es trazabilidad
        del piloto. Quien fue, no. Borrar la fila entera perderia lo primero
        para proteger lo segundo."""
        alumno = uuid.uuid4()
        _, correccion_id = await _sembrar(db, alumno)
        adapter = OlvidoCorreccionAdapter(db, TENANT)
        await adapter.update_correcciones_pseudonym(alumno, uuid.uuid4())
        await db.flush()

        fila = (
            await db.execute(
                text("SELECT estado, rubrica_id, nota_100 FROM correcciones_ia WHERE id = :i"),
                {"i": str(correccion_id)},
            )
        ).one()
        assert fila[0] == "done"
        assert fila[1] == "r1"
        assert fila[2] == Decimal("87.00")

    async def test_el_pseudonimo_de_la_entrega_se_rota(self, db: AsyncSession) -> None:
        alumno = uuid.uuid4()
        entrega_id, _ = await _sembrar(db, alumno)
        adapter = OlvidoCorreccionAdapter(db, TENANT)
        nuevo = uuid.uuid4()
        assert await adapter.update_correcciones_pseudonym(alumno, nuevo) == 1
        await db.flush()

        actual = (
            await db.execute(
                text("SELECT student_pseudonym FROM entregas WHERE id = :i"),
                {"i": str(entrega_id)},
            )
        ).scalar_one()
        assert actual == nuevo

    async def test_el_hash_del_conjunto_en_entregas_queda_en_NULL(self, db: AsyncSession) -> None:
        alumno = uuid.uuid4()
        entrega_id, _ = await _sembrar(db, alumno)
        adapter = OlvidoCorreccionAdapter(db, TENANT)
        await adapter.delete_artefactos_by_student(alumno)
        await db.flush()

        v = (
            await db.execute(
                text("SELECT artefacto_sha256 FROM entregas WHERE id = :i"),
                {"i": str(entrega_id)},
            )
        ).scalar_one()
        assert v is None


class TestElBorradoManualEsAccionable:
    async def test_el_listado_trae_el_id_externo(self, db: AsyncSession) -> None:
        """Mientras Active-IA no exponga borrado por API, ESTE id es lo unico
        con lo que alguien puede encontrar esa copia en su panel. Sin el, "hay
        que borrarlo a mano" no es accionable."""
        alumno = uuid.uuid4()
        _, correccion_id = await _sembrar(db, alumno)
        await db.execute(
            text("UPDATE correcciones_ia SET external_entrega_id = '9911' WHERE id = :i"),
            {"i": str(correccion_id)},
        )
        await db.flush()

        cs = await OlvidoCorreccionAdapter(db, TENANT).list_correcciones_by_student(alumno)
        assert cs[0]["external_entrega_id"] == "9911"

    async def test_borrar_en_activeia_LEVANTA_en_vez_de_mentir(self, db: AsyncSession) -> None:
        """Devolver `True` seria decir que se borro algo que sigue afuera.
        Levantar hace que el informe quede en `None` = "no se intento"."""
        with pytest.raises(NotImplementedError):
            await OlvidoCorreccionAdapter(db, TENANT).borrar_en_activeia(uuid.uuid4())
