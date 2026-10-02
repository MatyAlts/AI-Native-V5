"""Código, título de la TP y nota en la respuesta de entregas.

Change `alumno-ve-su-nota-sin-depender-del-listado`: el alumno pierde el
acceso a su nota cuando el docente archiva la TP, porque la única puerta a la
nota es `TareaSelector`, que itera sobre TPs `published`. El dato (la nota) y
el permiso (el endpoint no mira el estado de la TP) ya estaban — lo que
faltaba era con qué mostrarla: `EntregaOut` no traía ni el código ni el
título de la TP, y pedirlos a `GET /tareas-practicas/{id}` da 404 para una TP
archivada.

`nota_final` se sumó en una segunda vuelta (correctivo de spec, no mío): el
shape confirmado del frontend muestra la nota EN LA LISTA, no sólo al abrir
el detalle — sin ella el componente necesitaba pedir `getCalificacion` por
cada fila (hasta 50 requests en paralelo por carga de pantalla, un costo real
reportado en netbooks). Se la agrega al mismo batch.

`graded_at` se sumó en una tercera vuelta, por el mismo motivo: el shape
confirmado muestra "entregado {fecha} · corregido {fecha}", y la segunda
vuelta sólo había resuelto la nota. Mismo batch, una columna más del mismo
`select` — `_notas_metadata` ya consultaba `calificaciones`.

**Sobre `TestGetEntregaConNotaFinal::test_trae_la_nota_de_su_calificacion`**:
el `isinstance(..., float)` de ese test no es estilo, es la lección de esta
change. `Decimal("8.50") == 8.5` da `True` en Python — comparan por VALOR
matemático, no por tipo — así que un `==` contra un literal no distingue un
`Decimal` crudo (el cast a `float` olvidado) de un `float` real. Es una clase
de aserción vacía DISTINTA de la de la change anterior (una subcadena corta
que casi siempre está en un documento largo, por otra razón): acá el valor es
correcto y el tipo está mal, y `==` no lo ve. Cualquier campo que salga de un
`Numeric`/`Decimal` de Postgres y se compare contra un literal numérico en un
test tiene el mismo riesgo — usar `isinstance` primero, `==` después.

Mismo estilo que `test_entrega_artefactos.py`: sesión mockeada, sin DB real.
La integración contra Postgres (que el join sea válido en SQL real) queda
para `tests/integration/`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from evaluation_service.auth.dependencies import User
from evaluation_service.models.entregas import Entrega
from evaluation_service.routes.entregas import _notas_metadata, get_entrega, list_entregas

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
GRADED_AT = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def _entrega(
    student_id: UUID,
    tarea_practica_id: UUID | None = None,
    estado: str = "graded",
) -> Entrega:
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=tarea_practica_id or uuid4(),
        student_pseudonym=student_id,
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[],
    )
    e.artefactos = []
    e.legacy = False
    e.artefacto_sha256 = None
    e.deleted_at = None
    e.submitted_at = None
    e.created_at = datetime(2026, 9, 19, tzinfo=UTC)
    return e


def _student(sid: UUID) -> User:
    return User(
        id=sid, tenant_id=TENANT, email="a@utn.edu.ar", roles=frozenset({"estudiante"}), realm="utn"
    )


def _docente_oversight(did: UUID) -> User:
    """Rol oversight (`superadmin`) — salta la consulta previa de
    `usuarios_comision` (gate `if not is_oversight:`), así que `list_entregas`
    hace UNA sola llamada a `db.execute`: la del `select(Entrega)` principal.
    Eso es lo que permite capturarlo por índice fijo (`call_args_list[0]`)
    sin tener que mockear también la consulta cruda de comisiones."""
    return User(
        id=did,
        tenant_id=TENANT,
        email="d@utn.edu.ar",
        roles=frozenset({"superadmin"}),
        realm="utn",
    )


def _res_entrega(entrega: Entrega) -> MagicMock:
    return MagicMock(scalar_one_or_none=MagicMock(return_value=entrega))


def _res_list(entregas: list[Entrega]) -> MagicMock:
    return MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=entregas)))
    )


def _res_tp_meta(rows: list[tuple]) -> MagicMock:
    """Respuesta cruda de `_tp_metadata`: filas (id, codigo, titulo)."""
    return MagicMock(all=MagicMock(return_value=rows))


def _res_notas(rows: list[tuple]) -> MagicMock:
    """Respuesta cruda de `_notas_metadata`: filas (entrega_id, nota_final,
    graded_at)."""
    return MagicMock(all=MagicMock(return_value=rows))


def _mock_db(*responses: MagicMock) -> MagicMock:
    """Misma idea que `test_entrega_artefactos.py::_mock_db`: una respuesta
    por `db.execute`, en el orden exacto que el endpoint debería pedirlas."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(side_effect=list(responses))
    return db


class TestGetEntregaConTpMetadata:
    async def test_trae_codigo_y_titulo_de_su_tp(self) -> None:
        sid = uuid4()
        tp_id = uuid4()
        entrega = _entrega(sid, tarea_practica_id=tp_id)
        db = _mock_db(
            _res_entrega(entrega),
            _res_tp_meta([(str(tp_id), "TP2", "Agenda de turnos")]),
            _res_notas([(str(entrega.id), Decimal("8.50"), GRADED_AT)]),
        )

        out = await get_entrega(entrega.id, _student(sid), db)

        assert out.tarea_codigo == "TP2"
        assert out.tarea_titulo == "Agenda de turnos"

    async def test_tp_no_resoluble_devuelve_campos_none_y_200(self) -> None:
        """TRIANGULA: la TP de esta entrega está borrada (o no existe) — el
        `IN` de `_tp_metadata` no trae ninguna fila. La entrega se ve igual
        (200), sin título ni código: un campo obligatorio hubiera tumbado el
        endpoint con un 500 acá."""
        sid = uuid4()
        entrega = _entrega(sid)
        db = _mock_db(
            _res_entrega(entrega),
            _res_tp_meta([]),
            _res_notas([]),
        )

        out = await get_entrega(entrega.id, _student(sid), db)

        assert out.tarea_codigo is None
        assert out.tarea_titulo is None
        assert out.id == entrega.id


class TestGetEntregaConNotaFinal:
    """`nota_final` sumado en la segunda vuelta: la lista del frontend
    necesita la nota SIN pedir `getCalificacion` por fila."""

    async def test_trae_la_nota_de_su_calificacion(self) -> None:
        sid = uuid4()
        entrega = _entrega(sid, estado="graded")
        db = _mock_db(
            _res_entrega(entrega),
            _res_tp_meta([]),
            _res_notas([(str(entrega.id), Decimal("8.50"), GRADED_AT)]),
        )

        out = await get_entrega(entrega.id, _student(sid), db)

        # `isinstance`, no `==`: `Decimal("8.50") == 8.5` da `True` en Python
        # (comparan por valor), así que un `==` por sí solo no distingue un
        # `Decimal` crudo —que olvidó el cast— de un `float` real. Ya pasó:
        # ver REFACTOR en el informe final sobre la mutación que esto atrapa.
        assert isinstance(out.nota_final, float)
        assert out.nota_final == 8.5

    def test_nota_final_viaja_como_number_no_como_string_decimal(self) -> None:
        """Mismo bug que `CalificacionOut` ya tuvo (CLAUDE.md, backlog QA
        2026-05-07): `Numeric(5,2)` sin cast explícito serializa `"8.50"`
        (string), y el frontend tipa `nota_final` como `number`."""
        from evaluation_service.schemas.entrega import EntregaOut

        out = EntregaOut(
            id=uuid4(),
            tenant_id=TENANT,
            tarea_practica_id=uuid4(),
            student_pseudonym=uuid4(),
            comision_id=COMISION,
            estado="graded",
            ejercicio_estados=[],
            submitted_at=None,
            created_at=datetime(2026, 9, 19, tzinfo=UTC),
            deleted_at=None,
            nota_final=Decimal("8.50"),  # type: ignore[arg-type]
        )
        json_str = out.model_dump_json()
        assert '"nota_final":8.5' in json_str, json_str
        assert '"nota_final":"8.50"' not in json_str

    async def test_sin_calificar_nota_final_es_none(self) -> None:
        """TRIANGULA: una entrega `submitted` no tiene fila en
        `calificaciones` — `nota_final` queda en `None`, 200 igual."""
        sid = uuid4()
        entrega = _entrega(sid, estado="submitted")
        db = _mock_db(
            _res_entrega(entrega),
            _res_tp_meta([]),
            _res_notas([]),
        )

        out = await get_entrega(entrega.id, _student(sid), db)

        assert out.nota_final is None


class TestGetEntregaConGradedAt:
    """`graded_at` sumado en la tercera vuelta: mismo `select` de
    `_notas_metadata`, una columna más — el shape confirmado dice
    "entregado {fecha} · corregido {fecha}", no sólo la nota."""

    async def test_trae_la_fecha_de_correccion(self) -> None:
        sid = uuid4()
        entrega = _entrega(sid, estado="graded")
        db = _mock_db(
            _res_entrega(entrega),
            _res_tp_meta([]),
            _res_notas([(str(entrega.id), Decimal("8.50"), GRADED_AT)]),
        )

        out = await get_entrega(entrega.id, _student(sid), db)

        assert out.graded_at == GRADED_AT

    async def test_sin_calificar_graded_at_es_none(self) -> None:
        """TRIANGULA: sin fila en `calificaciones`, `graded_at` es `None` —
        mismo caso que `nota_final`, misma fuente."""
        sid = uuid4()
        entrega = _entrega(sid, estado="submitted")
        db = _mock_db(
            _res_entrega(entrega),
            _res_tp_meta([]),
            _res_notas([]),
        )

        out = await get_entrega(entrega.id, _student(sid), db)

        assert out.graded_at is None


class TestListEntregasConTpMetadataSinNMas1:
    async def test_dos_entregas_de_tps_distintas_traen_su_codigo_y_titulo(self) -> None:
        sid = uuid4()
        tp1, tp2 = uuid4(), uuid4()
        e1 = _entrega(sid, tarea_practica_id=tp1, estado="graded")
        e2 = _entrega(sid, tarea_practica_id=tp2, estado="submitted")
        db = _mock_db(
            _res_list([e1, e2]),
            _res_tp_meta(
                [
                    (str(tp1), "TP1", "Primeros programas"),
                    (str(tp2), "TP2", "Agenda de turnos"),
                ]
            ),
            _res_notas([(str(e1.id), Decimal("7.00"), GRADED_AT)]),
        )

        out = await list_entregas(
            tarea_practica_id=None,
            comision_id=None,
            estado=None,
            student_pseudonym=None,
            cursor=None,
            limit=50,
            user=_student(sid),
            db=db,
        )

        by_id = {str(d.id): d for d in out.data}
        assert by_id[str(e1.id)].tarea_codigo == "TP1"
        assert by_id[str(e1.id)].tarea_titulo == "Primeros programas"
        assert by_id[str(e2.id)].tarea_codigo == "TP2"
        assert by_id[str(e2.id)].tarea_titulo == "Agenda de turnos"

    async def test_no_hace_una_consulta_de_tp_por_fila(self) -> None:
        """El N+1: `_mock_db` sólo tiene TRES respuestas armadas — la lista de
        entregas, UN batch de metadata de TP y UN batch de notas. Si
        `list_entregas` consultara la TP o la nota fila por fila, una llamada
        extra a `db.execute` se queda sin respuesta y explota con
        `StopIteration`, no con un assert cómodo."""
        sid = uuid4()
        tp1, tp2, tp3 = uuid4(), uuid4(), uuid4()
        entregas = [
            _entrega(sid, tarea_practica_id=tp1),
            _entrega(sid, tarea_practica_id=tp2),
            _entrega(sid, tarea_practica_id=tp3),
        ]
        db = _mock_db(
            _res_list(entregas),
            _res_tp_meta([]),
            _res_notas([]),
        )

        await list_entregas(
            tarea_practica_id=None,
            comision_id=None,
            estado=None,
            student_pseudonym=None,
            cursor=None,
            limit=50,
            user=_student(sid),
            db=db,
        )

        assert db.execute.call_count == 3


class TestListEntregasConNotaFinal:
    async def test_cada_entrega_trae_su_propia_nota_y_fecha_de_correccion(self) -> None:
        sid = uuid4()
        e1 = _entrega(sid, estado="graded")
        e2 = _entrega(sid, estado="returned")
        graded_at_e1 = datetime(2026, 9, 3, tzinfo=UTC)
        graded_at_e2 = datetime(2026, 9, 19, tzinfo=UTC)
        db = _mock_db(
            _res_list([e1, e2]),
            _res_tp_meta([]),
            _res_notas(
                [
                    (str(e1.id), Decimal("7.00"), graded_at_e1),
                    (str(e2.id), Decimal("9.25"), graded_at_e2),
                ]
            ),
        )

        out = await list_entregas(
            tarea_practica_id=None,
            comision_id=None,
            estado=None,
            student_pseudonym=None,
            cursor=None,
            limit=50,
            user=_student(sid),
            db=db,
        )

        by_id = {str(d.id): d for d in out.data}
        assert by_id[str(e1.id)].nota_final == 7.0
        assert by_id[str(e2.id)].nota_final == 9.25
        # TRIANGULA sobre graded_at: cada fila trae SU PROPIA fecha, no la de
        # la otra — distinto del caso anterior (distintas notas), acá lo que
        # podría confundirse es la fecha si el mapeo por id fallara.
        assert by_id[str(e1.id)].graded_at == graded_at_e1
        assert by_id[str(e2.id)].graded_at == graded_at_e2


class TestListEntregasAislamientoPorAlumno:
    """Hallazgo de la auditoría: el filtro `Entrega.student_pseudonym ==
    user.id` que impide que un alumno vea las entregas de OTRO alumno no
    estaba fijado por ningún test. Los `_mock_db(...)` de esta clase devuelven
    filas pre-armadas sin que `db.execute` mire qué `WHERE` compiló
    `list_entregas` — así que los tests existentes (incluido
    `test_cada_entrega_trae_su_propia_nota_y_fecha_de_correccion`, que prueba
    que dos entregas del MISMO alumno no se crucen entre sí, algo distinto)
    pasarían igual aunque el filtro por alumno desapareciera entero.

    Estos dos capturan el `Select` real que `list_entregas` arma (lo único NO
    mockeado — compilarlo no toca una DB) y leen el SQL compilado con
    `literal_binds=True`.

    LÍMITE DECLARADO, con las palabras del auditor: esto prueba que el código
    ARMA la condición correcta. NO prueba que Postgres la APLIQUE — eso
    necesita una base real contra la cual ejecutar, y no hay una levantada en
    esta suite (es sesión mockeada, como el resto del archivo). Una RLS mal
    configurada, un índice que ignora la condición o un bug del driver async
    quedan fuera del alcance de este test.

    GOTCHA verificado al escribir esto: el literal UUID que compila
    SQLAlchemy con el tipo `PgUUID` NO lleva guiones (`sid.hex`, no
    `str(sid)`) — comparar contra `str(uuid)` da un falso negativo silencioso
    (el `in` nunca es `True`, pero tampoco explota).
    """

    async def test_alumno_no_docente_ignora_el_parametro_student_pseudonym_y_usa_su_propio_id(
        self,
    ) -> None:
        """El vector de ataque concreto: un alumno pide
        `?student_pseudonym=<otro-alumno>`. La rama no-docente de
        `list_entregas` NUNCA lee ese parámetro — siempre arma la condición
        con `user.id`. Si alguien cambia `user.id` por el parámetro en esa
        rama (o lo agrega a la condición), el valor que compila cambia y esto
        se pone rojo."""
        sid = uuid4()
        otro_alumno = uuid4()
        db = _mock_db(_res_list([]))  # lote vacío: UNA sola llamada a db.execute

        await list_entregas(
            tarea_practica_id=None,
            comision_id=None,
            estado=None,
            student_pseudonym=otro_alumno,  # el alumno pide el id de OTRO
            cursor=None,
            limit=50,
            user=_student(sid),
            db=db,
        )

        stmt = db.execute.call_args_list[0].args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert sid.hex in compiled, compiled
        assert otro_alumno.hex not in compiled, compiled

    async def test_rol_docente_no_agrega_filtro_por_student_pseudonym_del_propio_user(
        self,
    ) -> None:
        """Lo opuesto: para un rol docente (oversight, para que `list_entregas`
        haga UNA sola llamada a `db.execute` — ver `_docente_oversight`), el
        código NO debe agregar `Entrega.student_pseudonym == user.id` — esa
        restricción es sólo para no-docentes. Si alguien la agrega sin querer
        a la rama docente, el id del docente aparecería en el WHERE
        compilado donde no corresponde."""
        did = uuid4()
        db = _mock_db(_res_list([]))

        await list_entregas(
            tarea_practica_id=None,
            comision_id=None,
            estado=None,
            student_pseudonym=None,
            cursor=None,
            limit=50,
            user=_docente_oversight(did),
            db=db,
        )

        stmt = db.execute.call_args_list[0].args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert did.hex not in compiled, compiled


class TestNotasMetadataExcluyeCalificacionesBorradas:
    """`_notas_metadata` filtra `deleted_at IS NULL`, igual que sus hermanas.

    POR QUE ESTE TEST EXISTE
    --------------------------
    Lo senalo la revision de DBA. Las otras DOS lecturas de `Calificacion` en
    `routes/entregas.py` si filtran por `deleted_at` —`get_calificacion` y
    `recalificar_entrega`— y `_notas_metadata` era la unica que no.

    Hoy el filtro es inerte: nada en el repo escribe `Calificacion.deleted_at`,
    asi que no hay soft-delete de calificaciones implementado. Pero la columna
    existe (viene de `TimestampMixin`) y la migracion le crea su propio indice.
    El dia que exista el soft-delete, sin este filtro la LISTA le muestra al
    alumno una nota que el DETALLE trata como inexistente.

    QUE PRUEBA Y QUE NO
    ---------------------
    Prueba que el codigo ARMA la condicion, afirmando sobre el SQL compilado.
    NO prueba que Postgres la aplique: eso necesita una base real, y con una
    sesion mockeada un test asi pasaria con el filtro puesto Y sacado. Es el
    mismo limite que declara `TestListEntregasAislamientoPorAlumno` mas arriba.
    """

    async def test_el_where_compilado_excluye_las_borradas(self) -> None:
        capturado: list[object] = []

        class _Db:
            async def execute(self, stmt: object) -> object:
                capturado.append(stmt)

                class _R:
                    @staticmethod
                    def all() -> list[object]:
                        return []

                return _R()

        await _notas_metadata(_Db(), {uuid4()})  # type: ignore[arg-type]

        assert capturado, "no se capturo ningun statement: el test quedo vacuo"
        compilado = str(capturado[0].compile())  # type: ignore[attr-defined]
        # El `IS NULL` sobre deleted_at tiene que estar en el WHERE. Se busca la
        # columna Y el IS NULL juntos: buscar solo "deleted_at" pasaria si la
        # columna apareciera en el SELECT por cualquier otro motivo.
        assert "deleted_at IS NULL" in compilado, (
            f"el filtro de borradas no esta en el WHERE: {compilado}"
        )

    async def test_sin_ids_no_consulta_nada(self) -> None:
        # Guarda del guard: con el set vacio devuelve {} sin tocar la base, asi
        # que el `IN ()` degenerado nunca llega a Postgres.
        class _DbQueExplota:
            async def execute(self, stmt: object) -> object:
                raise AssertionError("no deberia consultar con ids vacios")

        assert await _notas_metadata(_DbQueExplota(), set()) == {}  # type: ignore[arg-type]
