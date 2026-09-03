"""La fila tiene que estar COMMITEADA antes de pasarle su id a otro proceso.

EL BUG QUE ESTE ARCHIVO IMPIDE QUE VUELVA
-----------------------------------------
La ruta creaba la corrección con `db.add()` + `flush()` y **sin commitear**, y
acto seguido le pasaba su `id` a un `BackgroundTask`. Esa tarea abre **su
propia sesión** —otra transacción, otra conexión— y lo primero que hace es
`db.get(CorreccionIA, correccion_id)`.

Un `flush()` manda el INSERT pero no lo hace durable: la fila existe dentro de
ESA transacción y en ningún otro lado. Así que la tarea preguntaba por una fila
que todavía no era visible para nadie más, no la encontraba, y se iba.

Producción, 2026-09-03:

    13:13:54.262  activeia_correccion_disparada     (la ruta)
    13:13:54.351  activeia_correccion_desaparecida  (la tarea, 89 ms después)

La fila quedaba en `pending` para siempre. El panel del docente giraba, y seis
minutos más tarde el reconciliador la cerraba con «quedó a medias, probablemente
por un reinicio del servicio» — un mensaje que mandaba a buscar el problema
exactamente al lugar equivocado.

**Toda corrección NUEVA moría acá**, antes del sandbox y antes del motor. Los
reintentos no, porque su fila estaba commiteada desde hacía rato: dos síntomas
idénticos en pantalla, con causas distintas.

No se notó durante meses porque este camino nunca corrió en producción —
Active-IA estuvo siempre apagado y sin una sola rúbrica sincronizada. Se destapó
al encender el corrector propio.

QUÉ SE PRUEBA, Y POR QUÉ ASÍ
----------------------------
Se prueba el ORDEN: que el commit ocurra **antes** de que el trabajo se
registre. No alcanza con "se commitea en algún momento" — el bug es exactamente
que se commiteaba después.

Verificado por reversión sacando el `await db.commit()` de la ruta: los dos
tests de la primera clase caen en rojo por assert.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from evaluation_service.models.entregas import Entrega, EntregaArtefacto
from evaluation_service.services.correccion_ia import RubricaElegida
from starlette.background import BackgroundTasks

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _entrega() -> Entrega:
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=uuid4(),
        student_pseudonym=uuid4(),
        comision_id=COMISION,
        estado="submitted",
        ejercicio_estados=[],
    )
    e.legacy = False
    return e


def _scalar(v):
    return MagicMock(scalar_one_or_none=MagicMock(return_value=v))


def _como_la_base(c) -> None:
    """Lo que Postgres completa al INSERT y el mock no: id y server_defaults.

    Sin esto el `refresh` mockeado deja el objeto a medio construir y el schema
    de salida revienta — un fallo de andamiaje que no dice nada sobre el orden
    de las operaciones, que es lo único que este archivo mide.
    """
    c.id = c.id or uuid4()
    c.created_at = c.created_at or datetime.now(UTC)
    c.desglose = c.desglose if c.desglose is not None else []
    c.tests_snapshot = c.tests_snapshot if c.tests_snapshot is not None else {}


class TestElOrdenDeLasOperaciones:
    """Commit primero, entrega del id después. En ese orden y no en el otro."""

    @pytest.fixture
    def client(self):
        from evaluation_service.auth import get_db as _get_db
        from evaluation_service.auth.dependencies import User, get_current_user
        from evaluation_service.main import app
        from fastapi.testclient import TestClient

        self.docente = User(
            id=uuid4(),
            tenant_id=TENANT,
            email="d@utn.edu.ar",
            roles=frozenset({"docente"}),
            realm="utn",
        )
        # `orden` registra QUÉ pasó y CUÁNDO, que es lo único que este archivo mide.
        self.orden: list[str] = []
        self.db = MagicMock()
        self.db.add = MagicMock()
        self.db.flush = AsyncMock(side_effect=lambda: self.orden.append("flush"))
        self.db.refresh = AsyncMock(side_effect=_como_la_base)
        self.db.commit = AsyncMock(side_effect=lambda: self.orden.append("commit"))

        app.dependency_overrides[get_current_user] = lambda: self.docente
        app.dependency_overrides[_get_db] = lambda: self.db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def _disparar(self, client):
        entrega = _entrega()
        art = EntregaArtefacto(
            tenant_id=TENANT,
            entrega_id=entrega.id,
            orden=1,
            codigo="print('hola')",
            sha256="sha-del-codigo",
            ejercicio_id=uuid4(),
        )
        art.language = "python"
        self.db.execute = AsyncMock(
            side_effect=[
                _scalar(entrega),  # la entrega existe
                MagicMock(first=MagicMock(return_value=(1,))),  # es de su comision
                _scalar(art),  # el artefacto
                _scalar(None),  # no hay correccion previa
            ]
        )

        def _anotar_add_task(_self, *a, **k):
            self.orden.append("add_task")

        with (
            patch("evaluation_service.routes.correccion_ia.settings") as st,
            patch(
                "evaluation_service.routes.correccion_ia.resolver_rubrica_del_motor",
                AsyncMock(
                    return_value=RubricaElegida(
                        rubrica_id="nativa:abc", external_ref="", estado="local", simulada=False
                    )
                ),
            ),
            patch(
                "evaluation_service.routes.correccion_ia.assert_cuota_disponible",
                AsyncMock(return_value=99),
            ),
            patch.object(BackgroundTasks, "add_task", autospec=True, side_effect=_anotar_add_task),
        ):
            st.correccion_motor = "nativa"
            st.activeia_enabled = False
            return client.post(
                f"/api/v1/entregas/{entrega.id}/correccion-ia",
                json={"ejercicio_orden": 1, "confirmado": True},
            )

    def test_se_commitea_ANTES_de_registrar_el_trabajo(self, client) -> None:
        """El corazón del arreglo.

        Sin el commit, la tarea de fondo recibe el id de una fila que sólo
        existe dentro de la transacción del request. Abre su propia sesión, no
        la encuentra, y se va dejándola en `pending` para siempre.
        """
        r = self._disparar(client)

        assert r.status_code == 202, r.text
        assert "commit" in self.orden, (
            "la fila se entrega sin commitear: la tarea de fondo va a abrir otra "
            "sesion y no va a encontrarla (activeia_correccion_desaparecida)"
        )
        assert self.orden.index("commit") < self.orden.index("add_task"), (
            f"el commit ocurre DESPUES de entregar el id. Orden real: {self.orden}"
        )

    def test_el_insert_va_antes_del_commit(self, client) -> None:
        """Obvio, pero fija el orden completo: flush → commit → add_task.

        Sin esto, un commit puesto antes del `flush` pasaría el test de arriba
        sin hacer durable nada.
        """
        self._disparar(client)

        assert self.orden == ["flush", "commit", "add_task"], self.orden


class TestLaRamaDeReintentoTambien:
    """El commit tiene que cubrir las DOS ramas, y por motivos distintos.

    La rama de INSERT lo necesita para que la fila exista. La de **reintento**
    lo necesita todavía más: `reabrir_para_reintento` hace un `UPDATE ... SET
    estado='pending'` que sin commit deja la fila **lockeada por la transacción
    del request**. El `estado='running'` de la tarea de fondo es otro UPDATE
    sobre esa misma fila: espera el lock. Y el request no commitea hasta que la
    tarea termine. Espera circular, sin `lock_timeout` en ningún lado.

    Si alguien mueve el `await db.commit()` adentro del `else`, los tests de la
    clase de arriba siguen todos en verde y esta rama vuelve a colgarse.
    """

    @pytest.fixture
    def client(self):
        from evaluation_service.auth import get_db as _get_db
        from evaluation_service.auth.dependencies import User, get_current_user
        from evaluation_service.main import app
        from fastapi.testclient import TestClient

        self.docente = User(
            id=uuid4(),
            tenant_id=TENANT,
            email="d@utn.edu.ar",
            roles=frozenset({"docente"}),
            realm="utn",
        )
        self.orden: list[str] = []
        self.db = MagicMock()
        self.db.add = MagicMock()
        self.db.flush = AsyncMock()
        self.db.refresh = AsyncMock(side_effect=_como_la_base)
        self.db.commit = AsyncMock(side_effect=lambda: self.orden.append("commit"))

        app.dependency_overrides[get_current_user] = lambda: self.docente
        app.dependency_overrides[_get_db] = lambda: self.db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def test_un_reintento_tambien_commitea_antes_de_entregar_el_id(self, client) -> None:
        from evaluation_service.models.correcciones_ia import CorreccionIA

        entrega = _entrega()
        art = EntregaArtefacto(
            tenant_id=TENANT,
            entrega_id=entrega.id,
            orden=1,
            codigo="print('hola')",
            sha256="sha-del-codigo",
            ejercicio_id=uuid4(),
        )
        art.language = "python"
        # Una corrección que ya falló: es lo que habilita el reintento.
        vieja = CorreccionIA(
            tenant_id=TENANT,
            entrega_id=entrega.id,
            orden=1,
            disparado_por=self.docente.id,
            rubrica_id="nativa:abc",
            artefacto_sha256="sha-del-codigo",
        )
        vieja.id = uuid4()
        vieja.estado = "error"
        _como_la_base(vieja)

        self.db.execute = AsyncMock(
            side_effect=[
                _scalar(entrega),
                MagicMock(first=MagicMock(return_value=(1,))),
                _scalar(art),
                _scalar(vieja),  # buscar_existente la encuentra
                MagicMock(rowcount=1),  # el UPDATE de reabrir_para_reintento
            ]
        )

        def _anotar_add_task(_self, *a, **k):
            self.orden.append("add_task")

        with (
            patch("evaluation_service.routes.correccion_ia.settings") as st,
            patch(
                "evaluation_service.routes.correccion_ia.resolver_rubrica_del_motor",
                AsyncMock(
                    return_value=RubricaElegida(
                        rubrica_id="nativa:abc", external_ref="", estado="local", simulada=False
                    )
                ),
            ),
            patch(
                "evaluation_service.routes.correccion_ia.assert_cuota_disponible",
                AsyncMock(return_value=99),
            ),
            patch.object(BackgroundTasks, "add_task", autospec=True, side_effect=_anotar_add_task),
        ):
            st.correccion_motor = "nativa"
            st.activeia_enabled = False
            r = client.post(
                f"/api/v1/entregas/{entrega.id}/correccion-ia",
                json={"ejercicio_orden": 1, "confirmado": True},
            )

        assert r.status_code == 202, r.text
        assert self.orden == ["commit", "add_task"], (
            f"el UPDATE del reintento se entrega sin commitear: la tarea de fondo "
            f"va a esperar un lock que nadie suelta. Orden real: {self.orden}"
        )


class TestLaRegla:
    """La regla general, escrita donde se lee.

    No es una propiedad de esta ruta: vale para cualquier `BackgroundTask` del
    repo que reciba el id de una fila recién creada.
    """

    def test_esta_documentada_en_la_ruta(self) -> None:
        """Un test sobre un comentario es raro, y acá se justifica: el arreglo
        es UNA línea (`await db.commit()`) que parece redundante —FastAPI
        commitea al cerrar la dependencia— y sin el porqué al lado, el próximo
        que pase la borra por prolijidad y reintroduce el bug entero.
        """
        import inspect

        from evaluation_service.routes import correccion_ia as ruta

        fuente = inspect.getsource(ruta.disparar_correccion)

        assert "await db.commit()" in fuente
        # Se ancla en el nombre del evento que lo delató en producción: es lo
        # que hace que el comentario sea *encontrable* el día que alguien vea
        # ese log y busque de dónde sale.
        assert "activeia_correccion_desaparecida" in fuente, (
            "el commit quedo sin el porque al lado. El proximo que pase lo borra "
            "por prolijidad —FastAPI ya commitea al cerrar la dependencia— y "
            "reintroduce el bug entero."
        )
