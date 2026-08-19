"""Tests del Epic 3: cuota, gates e idempotencia.

Las dos propiedades que este epic no puede perder:

1. **Un fallo de infraestructura NUNCA es una nota.** Ni un cero. Un cero que
   en realidad significa "el servicio no respondio" termina en el legajo de
   una persona.
2. **La cuota falla CERRADA.** Sin poder leer el contador no se dispara: cada
   corrida cuesta computo y dinero.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.models.entregas import Entrega, EntregaArtefacto
from evaluation_service.services.correccion_cuota import (
    CuotaExcedidaError,
    CuotaIndeterminadaError,
    assert_cuota_disponible,
)
from evaluation_service.services.correccion_ia import (
    CorreccionRechazadaError,
    assert_puede_dispararse,
    es_de_mi_comision,
    mapear_error_activeia,
    marcar_error,
    resolver_rubrica,
)
from evaluation_service.services.correccion_pre_ejecucion import _mapear

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _entrega(*, legacy: bool = False, estado: str = "submitted") -> Entrega:
    e = Entrega(
        id=uuid4(),
        tenant_id=TENANT,
        tarea_practica_id=uuid4(),
        student_pseudonym=uuid4(),
        comision_id=COMISION,
        estado=estado,
        ejercicio_estados=[],
    )
    e.legacy = legacy
    return e


def _db(*resultados: MagicMock) -> MagicMock:
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(side_effect=list(resultados))
    return db


def _scalar(valor: object) -> MagicMock:
    return MagicMock(scalar_one_or_none=MagicMock(return_value=valor))


class TestCuotaFallaCerrada:
    async def test_sin_poder_leer_el_contador_NO_deja_pasar(self) -> None:
        """Es al reves que casi todos los limites del sistema, y es
        deliberado: sin contador no sabemos cuanto se gasto, y el default
        seguro es no gastar."""
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("la base no responde"))

        with pytest.raises(CuotaIndeterminadaError):
            await assert_cuota_disponible(db, TENANT, uuid4())

    async def test_cuota_excedida_y_cuota_indeterminada_son_errores_DISTINTOS(self) -> None:
        """ "Gastaste tu cuota" se resuelve manana; "no se cuanto gastaste" se
        resuelve avisando que algo esta roto. Colapsarlos esconde una falla."""
        assert not issubclass(CuotaExcedidaError, CuotaIndeterminadaError)
        assert not issubclass(CuotaIndeterminadaError, CuotaExcedidaError)

    async def test_excedida_cuando_llego_al_limite(self) -> None:
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=100)))
        with (
            patch("evaluation_service.services.correccion_cuota.settings") as st,
            pytest.raises(CuotaExcedidaError),
        ):
            st.activeia_cuota_diaria_por_docente = 100
            await assert_cuota_disponible(db, TENANT, uuid4())

    async def test_devuelve_cuantas_quedan(self) -> None:
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=3)))
        with patch("evaluation_service.services.correccion_cuota.settings") as st:
            st.activeia_cuota_diaria_por_docente = 10
            assert await assert_cuota_disponible(db, TENANT, uuid4()) == 7


class TestUnFalloNuncaEsNota:
    def test_marcar_error_deja_la_nota_en_none(self) -> None:
        c = CorreccionIA(
            tenant_id=TENANT,
            entrega_id=uuid4(),
            orden=1,
            disparado_por=uuid4(),
            rubrica_id="r1",
            artefacto_sha256="x",
        )
        c.id = uuid4()
        # La nota arranca PUESTA a proposito. La version anterior de este test
        # la seteaba en None antes de llamar, asi que el assert pasaba aunque
        # `marcar_error` no la tocara: probaba el pre-seteo, no la funcion.
        c.nota_100 = Decimal("87.00")
        c.estado = "done"

        marcar_error(c, error_code="GEMINI_OVERLOADED", detalle="saturado", es_infraestructura=True)

        assert c.estado == "error"
        assert c.nota_100 is None, "un fallo de infraestructura quedo con nota"
        assert c.error_code == "GEMINI_OVERLOADED"

    def test_gemini_overloaded_es_infraestructura(self) -> None:
        """El timeout del motor se reporta como error para reintentar, NUNCA
        como una nota."""
        code, infra = mapear_error_activeia("GEMINI_OVERLOADED", "")
        assert infra is True
        assert code == "GEMINI_OVERLOADED"

    def test_un_rechazo_del_servicio_NO_es_infraestructura(self) -> None:
        """Reintentar un rechazo es reintentar el error. La distincion decide
        si la UI dice "probá de nuevo" o "esto no se va a destrabar solo"."""
        _, infra = mapear_error_activeia("RUBRICA_INEXISTENTE", "")
        assert infra is False

    def test_un_timeout_sin_codigo_igual_es_infraestructura(self) -> None:
        code, infra = mapear_error_activeia(None, "Active-IA no respondió: ReadTimeout")
        assert infra is True
        assert code == "TIMEOUT"

    def test_los_fallos_del_sandbox_son_infraestructura(self) -> None:
        for c in ("SANDBOX_TIMEOUT", "SANDBOX_UNREACHABLE", "SANDBOX_QUOTA"):
            assert mapear_error_activeia(c, "")[1] is True


class TestGates:
    async def test_una_entrega_legacy_no_se_corrige(self) -> None:
        """Su codigo no existe: lo unico reconstruible es una lectura del CTR,
        y eso no es lo que el alumno entrego."""
        with pytest.raises(CorreccionRechazadaError) as exc:
            await assert_puede_dispararse(_db(), _entrega(legacy=True), 1)
        assert "anterior" in str(exc.value).lower()

    async def test_una_entrega_en_draft_no_se_corrige(self) -> None:
        with pytest.raises(CorreccionRechazadaError):
            await assert_puede_dispararse(_db(), _entrega(estado="draft"), 1)

    async def test_sin_artefacto_no_se_corrige(self) -> None:
        with pytest.raises(CorreccionRechazadaError) as exc:
            await assert_puede_dispararse(_db(_scalar(None)), _entrega(), 1)
        assert "no hay código guardado" in str(exc.value).lower()

    async def test_con_artefacto_pasa(self) -> None:
        art = EntregaArtefacto(
            tenant_id=TENANT, entrega_id=uuid4(), orden=1, codigo="x", sha256="s"
        )
        assert await assert_puede_dispararse(_db(_scalar(art)), _entrega(), 1) is art

    async def test_sin_rubrica_sincronizada_no_se_corrige(self) -> None:
        """Corregir sin rubrica devolveria un numero sobre nada."""
        with pytest.raises(CorreccionRechazadaError) as exc:
            await resolver_rubrica(_db(_scalar(None)), TENANT, uuid4())
        assert "sincroniz" in str(exc.value).lower()

    async def test_membresia_de_comision(self) -> None:
        """Sin esto un docente gasta la cuota de otro y manda el codigo de un
        alumno ajeno afuera. La RLS no los separa: comparten tenant."""
        con = _db(MagicMock(first=MagicMock(return_value=(1,))))
        sin = _db(MagicMock(first=MagicMock(return_value=None)))
        assert await es_de_mi_comision(con, uuid4(), COMISION) is True
        assert await es_de_mi_comision(sin, uuid4(), COMISION) is False


class TestPreEjecucion:
    def test_un_error_de_compilacion_NO_es_fallo_de_infraestructura(self) -> None:
        """Es informacion sobre el codigo del alumno, y de las mas
        accionables. Por eso vuelve como resultado y no como excepcion."""
        r = _mapear({"compile_error": "Main.java:3: cannot find symbol"})
        assert r.compila is False
        assert r.error_compilacion is not None
        assert r.total == 0

    def test_cuenta_los_casos_que_pasaron(self) -> None:
        r = _mapear({"test_results": [{"passed": True}, {"passed": False}, {"passed": True}]})
        assert (r.total, r.passed, r.failed) == (3, 2, 1)

    def test_no_explota_con_un_resultado_vacio(self) -> None:
        r = _mapear({})
        assert r.compila is True
        assert r.total == 0


class TestEndpoints:
    """Los tres endpoints, con `TestClient` contra la app real."""

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
        self.db = MagicMock()
        self.db.flush = AsyncMock()
        self.db.refresh = AsyncMock()
        self.db.add = MagicMock()

        app.dependency_overrides[get_current_user] = lambda: self.docente
        app.dependency_overrides[_get_db] = lambda: self.db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def test_kill_switch_apagado_da_503(self, client) -> None:
        """Falla CERRADO: apagado, no se dispara nada."""
        with patch("evaluation_service.routes.correccion_ia.settings") as st:
            st.activeia_enabled = False
            r = client.post(
                f"/api/v1/entregas/{uuid4()}/correccion-ia",
                json={"ejercicio_orden": 1, "confirmado": True},
            )
        assert r.status_code == 503

    def test_docente_de_otra_comision_recibe_404(self, client) -> None:
        """404 y NO 403: un 403 confirmaria que la entrega existe, y con eso el
        `entrega_id` de una comision ajena se vuelve un oraculo. Disparar sobre
        una entrega ajena gasta la cuota de otro y manda el codigo de un alumno
        afuera."""
        entrega = _entrega()
        self.db.execute = AsyncMock(
            side_effect=[
                _scalar(entrega),  # la entrega existe
                MagicMock(first=MagicMock(return_value=None)),  # NO es de su comision
            ]
        )
        with patch("evaluation_service.routes.correccion_ia.settings") as st:
            st.activeia_enabled = True
            r = client.post(
                f"/api/v1/entregas/{entrega.id}/correccion-ia",
                json={"ejercicio_orden": 1, "confirmado": True},
            )
        assert r.status_code == 404
        assert "403" not in r.text

    def test_entrega_legacy_da_422(self, client) -> None:
        entrega = _entrega(legacy=True)
        self.db.execute = AsyncMock(
            side_effect=[_scalar(entrega), MagicMock(first=MagicMock(return_value=(1,)))]
        )
        with patch("evaluation_service.routes.correccion_ia.settings") as st:
            st.activeia_enabled = True
            r = client.post(
                f"/api/v1/entregas/{entrega.id}/correccion-ia",
                json={"ejercicio_orden": 1, "confirmado": True},
            )
        assert r.status_code == 422

    def test_cuota_excedida_da_429_solo_al_confirmar(self, client) -> None:
        """Un preview con la cuota agotada NO es un error: el docente tiene que
        poder ver que se quedo sin cuota, no recibir un 429 sobre una operacion
        que no gasta nada."""
        entrega = _entrega()
        art = EntregaArtefacto(
            tenant_id=TENANT,
            entrega_id=entrega.id,
            orden=1,
            codigo="x",
            sha256="s",
            ejercicio_id=uuid4(),
        )
        from evaluation_service.models.activeia import ActiveIARubricaEjercicio

        vinculo = ActiveIARubricaEjercicio(
            tenant_id=TENANT, ejercicio_id=art.ejercicio_id, rubrica_id="r1"
        )

        def _respuestas():
            return [
                _scalar(entrega),
                MagicMock(first=MagicMock(return_value=(1,))),
                _scalar(art),
                _scalar(vinculo),
                _scalar(None),  # no hay correccion existente
            ]

        self.db.execute = AsyncMock(side_effect=_respuestas())
        with (
            patch("evaluation_service.routes.correccion_ia.settings") as st,
            patch(
                "evaluation_service.routes.correccion_ia.assert_cuota_disponible",
                AsyncMock(side_effect=CuotaExcedidaError("sin cuota")),
            ),
        ):
            st.activeia_enabled = True
            r = client.post(
                f"/api/v1/entregas/{entrega.id}/correccion-ia",
                json={"ejercicio_orden": 1, "confirmado": True},
            )
        assert r.status_code == 429

    def test_cuota_indeterminada_da_503_y_no_deja_pasar(self, client) -> None:
        entrega = _entrega()
        art = EntregaArtefacto(
            tenant_id=TENANT,
            entrega_id=entrega.id,
            orden=1,
            codigo="x",
            sha256="s",
            ejercicio_id=uuid4(),
        )
        from evaluation_service.models.activeia import ActiveIARubricaEjercicio

        vinculo = ActiveIARubricaEjercicio(
            tenant_id=TENANT, ejercicio_id=art.ejercicio_id, rubrica_id="r1"
        )
        self.db.execute = AsyncMock(
            side_effect=[
                _scalar(entrega),
                MagicMock(first=MagicMock(return_value=(1,))),
                _scalar(art),
                _scalar(vinculo),
                _scalar(None),
            ]
        )
        with (
            patch("evaluation_service.routes.correccion_ia.settings") as st,
            patch(
                "evaluation_service.routes.correccion_ia.assert_cuota_disponible",
                AsyncMock(side_effect=CuotaIndeterminadaError("no se pudo contar")),
            ),
        ):
            st.activeia_enabled = True
            r = client.post(
                f"/api/v1/entregas/{entrega.id}/correccion-ia",
                json={"ejercicio_orden": 1, "confirmado": True},
            )
        assert r.status_code == 503


class TestElEjecutor:
    """El trabajo en background. Nada de esto puede terminar en una nota."""

    def test_el_zip_nombra_el_archivo_como_el_compilador_espera(self) -> None:
        """Una clase publica Java tiene que vivir en un archivo con su nombre.
        Un zip con `codigo.txt` adentro no compila del otro lado."""
        import zipfile

        from evaluation_service.services.correccion_ejecutor import _zip_del_codigo

        for lang, esperado in (("java", "src/Main.java"), ("python", "src/main.py")):
            z = zipfile.ZipFile(io.BytesIO(_zip_del_codigo("x", lang)))
            assert z.namelist() == [esperado]

    async def test_si_no_compila_SE_MANDA_IGUAL(self) -> None:
        """Cambio del 19/08: antes se cortaba para no pagar una correccion
        sobre codigo roto. Se revirtio — un punto y coma que falta no
        justifica dejar al alumno sin devolucion, y el motor igual puede
        decirle si el diseno va encaminado.

        Lo que NO cambia: el estado de compilacion viaja explicito, para que
        el motor no cierre criterios de "funciona" sobre un archivo que nunca
        corrio."""
        from evaluation_service.services import correccion_ejecutor as mod
        from evaluation_service.services.correccion_pre_ejecucion import ResultadoTests

        correccion = CorreccionIA(
            tenant_id=TENANT,
            entrega_id=uuid4(),
            orden=1,
            disparado_por=uuid4(),
            rubrica_id="r1",
            artefacto_sha256="s",
        )
        correccion.id = uuid4()
        correccion.nota_100 = None

        sesion = MagicMock()
        sesion.get = AsyncMock(return_value=correccion)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=sesion)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "tenant_session", MagicMock(return_value=ctx)),
            patch.object(
                mod,
                "correr_tests",
                AsyncMock(
                    return_value=ResultadoTests(
                        compila=False, error_compilacion="Main.java:3: cannot find symbol"
                    )
                ),
            ),
            patch(
                "evaluation_service.services.activeia_credenciales.cliente_para", AsyncMock()
            ) as fake_cliente,
        ):
            await mod.ejecutar_correccion(
                correccion_id=correccion.id,
                tenant_id=TENANT,
                user_id=uuid4(),
                comision_id=COMISION,
                ejercicio_id=uuid4(),
                codigo="roto",
                language="java",
                alumno_nombre="a",
                activeia_comision_id="1",
                headers_sandbox={},
            )

        fake_cliente.assert_awaited()  # antes: assert_not_awaited()
        assert correccion.error_code != "NO_COMPILA", (
            "volvio a cortar por no compilar: ese gate se saco a proposito"
        )

    async def test_una_excepcion_inesperada_no_deja_la_correccion_en_running(self) -> None:
        """Corre en background: una excepcion que escape se pierde en un log y
        la correccion queda girando en la pantalla del docente para siempre."""
        from evaluation_service.services import correccion_ejecutor as mod

        correccion = CorreccionIA(
            tenant_id=TENANT,
            entrega_id=uuid4(),
            orden=1,
            disparado_por=uuid4(),
            rubrica_id="r1",
            artefacto_sha256="s",
        )
        correccion.id = uuid4()
        correccion.nota_100 = None

        sesion = MagicMock()
        sesion.get = AsyncMock(return_value=correccion)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=sesion)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mod, "tenant_session", MagicMock(return_value=ctx)),
            patch.object(mod, "correr_tests", AsyncMock(side_effect=RuntimeError("boom"))),
        ):
            # NO levanta: eso es parte del contrato de esta funcion.
            await mod.ejecutar_correccion(
                correccion_id=correccion.id,
                tenant_id=TENANT,
                user_id=uuid4(),
                comision_id=COMISION,
                ejercicio_id=uuid4(),
                codigo="x",
                language="java",
                alumno_nombre="a",
                activeia_comision_id="1",
                headers_sandbox={},
            )

        assert correccion.estado == "error"
        assert correccion.nota_100 is None


class TestElOrdenEsObligatorio:
    def test_sin_ejercicio_orden_da_422(self, client=None) -> None:
        """Cada correccion se paga: que ejercicio se corrige tiene que ser una
        decision explicita, no el default de un campo omitido."""
        from evaluation_service.schemas.activeia import CorreccionIABody
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CorreccionIABody(confirmado=True)


class TestElEjecutorNoManda:
    async def test_un_lenguaje_desconocido_corta(self) -> None:
        """Antes caia al `else` y empaquetaba como `main.py`: del otro lado eso
        es un archivo Python con algo que no es Python, y el motor corrige un
        sinsentido en vez de fallar."""
        from evaluation_service.services.correccion_ejecutor import _zip_del_codigo
        from evaluation_service.services.correccion_pre_ejecucion import PreEjecucionError

        with pytest.raises(PreEjecucionError) as exc:
            _zip_del_codigo("x", "cobol")
        assert exc.value.error_code == "LENGUAJE_DESCONOCIDO"

    async def test_el_409_no_se_toma_por_exito_si_no_ubica_la_entrega(self) -> None:
        """Retomar a ciegas subiria la correccion de otro TP del mismo alumno:
        el tutor le adjuntaba la devolucion de otra unidad."""
        from evaluation_service.services.correccion_ejecutor import _subir_y_corregir

        cliente = MagicMock()
        cliente.request = AsyncMock(
            side_effect=[
                MagicMock(status_code=409),  # ya existe
                MagicMock(status_code=200, json=MagicMock(return_value={"items": []})),
            ]
        )
        r = await _subir_y_corregir(
            cliente=cliente,
            codigo="x",
            language="java",
            alumno_nombre="Ana",
            comision_id="1",
            rubrica_id="r1",
            tests={},
        )
        assert r["error_code"] == "CONFLICTO_SIN_SALIDA"
        assert "nota_100" not in r

    async def test_el_409_solo_retoma_la_entrega_de_LA_MISMA_rubrica(self) -> None:
        """El bug documentado de produccion: sin comparar `rubrica_id`
        alcanzaba el nombre del alumno y se retomaba la entrega de OTRO TP."""
        from evaluation_service.services.correccion_ejecutor import _ubicar_entrega

        cliente = MagicMock()
        cliente.request = AsyncMock(
            return_value=MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value={
                        "items": [
                            {"id": "99", "rubrica_id": "OTRA", "alumno_nombre": "Ana"},
                            {"id": "42", "rubrica_id": "r1", "alumno_nombre": "Ana"},
                        ]
                    }
                ),
            )
        )
        assert await _ubicar_entrega(cliente, "1", "r1", "Ana") == "42"
        # Y si la unica del alumno es de otra rubrica, NO se retoma ninguna.
        cliente.request = AsyncMock(
            return_value=MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value={
                        "items": [{"id": "99", "rubrica_id": "OTRA", "alumno_nombre": "Ana"}]
                    }
                ),
            )
        )
        assert await _ubicar_entrega(cliente, "1", "r1", "Ana") is None

    async def test_un_4xx_al_disparar_corta_sin_poletear(self) -> None:
        """Antes solo cortaba con >=500, asi que un rechazo se poleteaba igual
        hasta quemar el presupuesto entero."""
        from evaluation_service.services.correccion_ejecutor import _subir_y_corregir

        cliente = MagicMock()
        cliente.request = AsyncMock(
            side_effect=[
                MagicMock(status_code=201, json=MagicMock(return_value={"id": "7"})),
                MagicMock(status_code=422),  # el disparo lo rechaza
            ]
        )
        r = await _subir_y_corregir(
            cliente=cliente,
            codigo="x",
            language="java",
            alumno_nombre="Ana",
            comision_id="1",
            rubrica_id="r1",
            tests={},
        )
        assert r["error_code"] == "HTTP_422"
        assert "nota_100" not in r
        # No poleteo: sólo dos requests (subir + disparar).
        assert cliente.request.await_count == 2

    async def test_el_poll_no_saca_nota_de_una_respuesta_que_no_es_200(self) -> None:
        from evaluation_service.services.correccion_ejecutor import _poletear

        cliente = MagicMock()
        cliente.request = AsyncMock(
            return_value=MagicMock(status_code=500, json=MagicMock(return_value={"nota": 95}))
        )
        with patch("evaluation_service.services.correccion_ejecutor._POLL_INTERVAL_S", 0.01):
            r = await _poletear(cliente, "7")
        assert "nota_100" not in r
        assert r["error_code"] == "HTTP_500"


class TestLaApiDistingueElTipoDeFallo:
    def test_infraestructura_y_rechazo_se_serializan_distinto(self) -> None:
        """La UI pinta ambar y "reintenta" para uno, rojo para el otro.
        Confundirlos costo dos dias de reintentos sobre algo que nunca se iba
        a destrabar solo."""
        from evaluation_service.routes.correccion_ia import _out

        def _c(code):
            c = CorreccionIA(
                tenant_id=TENANT,
                entrega_id=uuid4(),
                orden=1,
                disparado_por=uuid4(),
                rubrica_id="r1",
                artefacto_sha256="s",
            )
            c.id = uuid4()
            c.estado = "error"
            c.nota_100 = None
            c.error_code = code
            c.error_detail = "x"
            c.desglose = []
            c.tests_snapshot = {}
            c.external_correccion_id = None
            c.created_at = datetime(2026, 8, 18, tzinfo=UTC)
            c.finished_at = None
            return c

        assert _out(_c("GEMINI_OVERLOADED")).es_infraestructura is True
        assert _out(_c("RUBRICA_INEXISTENTE")).es_infraestructura is False
        # Y una que salio bien no es "infraestructura" por descarte.
        ok = _c(None)
        ok.estado = "done"
        ok.nota_100 = Decimal("90.00")
        assert _out(ok).es_infraestructura is False


class TestElPDF:
    """El PDF lleva el nombre del alumno y la devolucion sobre su codigo."""

    def test_la_key_no_es_adivinable(self) -> None:
        """Sin el token random, alguien con el `correccion_id` —que viaja en
        la URL del frontend— construye la ruta del objeto. Si el bucket queda
        mal configurado, eso es un link directo a la devolucion de un
        alumno."""
        from evaluation_service.services.correccion_pdf import make_pdf_key

        t, e, c = uuid4(), uuid4(), uuid4()
        k1 = make_pdf_key(t, e, c)
        k2 = make_pdf_key(t, e, c)
        assert k1 != k2, "la key es deterministica: se puede construir desde los ids"
        assert len(k1.rsplit("/", 1)[-1]) > 20

    def test_la_key_NO_va_al_bucket_de_materiales(self) -> None:
        """En materiales hay objetos que se sirven a la comision entera: un
        permiso pensado para uno alcanzaria al otro."""
        from evaluation_service.services.correccion_pdf import make_pdf_key

        k = make_pdf_key(uuid4(), uuid4(), uuid4())
        assert k.startswith("correcciones/")
        assert "materials/" not in k

    async def test_si_el_pdf_no_baja_la_correccion_NO_falla(self) -> None:
        """La nota ya existe y es lo que importa. Perder la correccion entera
        por un PDF seria tirar el trabajo que ya se pago."""
        from evaluation_service.services.correccion_pdf import bajar_y_guardar

        cliente = MagicMock()
        cliente.request = AsyncMock(side_effect=RuntimeError("se cayo"))
        key = await bajar_y_guardar(
            cliente=cliente,
            tenant_id=uuid4(),
            entrega_id=uuid4(),
            correccion_id=uuid4(),
            external_correccion_id="42",
        )
        assert key is None

    async def test_un_404_del_pdf_tampoco_rompe(self) -> None:
        from evaluation_service.services.correccion_pdf import bajar_y_guardar

        cliente = MagicMock()
        cliente.request = AsyncMock(return_value=MagicMock(status_code=404, content=b""))
        assert (
            await bajar_y_guardar(
                cliente=cliente,
                tenant_id=uuid4(),
                entrega_id=uuid4(),
                correccion_id=uuid4(),
                external_correccion_id="42",
            )
            is None
        )

    async def test_borrar_un_pdf_inexistente_es_exito(self) -> None:
        """El derecho al olvido: si el objeto ya no esta, eso ES el estado que
        se queria, no un error."""
        from evaluation_service.services.correccion_pdf import borrar

        assert await borrar(None) is True

    def test_la_api_no_expone_la_key_del_storage(self) -> None:
        """Publicar la ruta convierte un bucket mal configurado en un link
        directo. Se expone `tiene_pdf`, que es lo que la UI necesita."""
        from evaluation_service.schemas.activeia import CorreccionIAOut

        campos = set(CorreccionIAOut.model_fields)
        assert "pdf_storage_key" not in campos
        assert "tiene_pdf" in campos


class TestElGateDelPDF:
    """El PDF lleva el nombre del alumno y la devolucion sobre su codigo. Su
    autorizacion es lo unico que impide que un docente de otra comision lo
    baje con solo tener el `correccion_id` — que viaja en la URL."""

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
        self.db = MagicMock()
        app.dependency_overrides[get_current_user] = lambda: self.docente
        app.dependency_overrides[_get_db] = lambda: self.db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def test_docente_de_otra_comision_recibe_404(self, client) -> None:
        entrega = _entrega()
        self.db.execute = AsyncMock(
            side_effect=[
                _scalar(entrega),
                MagicMock(first=MagicMock(return_value=None)),  # no es su comision
            ]
        )
        r = client.get(f"/api/v1/entregas/{entrega.id}/correccion-ia/{uuid4()}/pdf")
        assert r.status_code == 404

    def test_sin_pdf_da_404_y_no_204(self, client) -> None:
        """Un 204 con cuerpo vacio se lee como un PDF de cero bytes."""
        entrega = _entrega()
        c = CorreccionIA(
            tenant_id=TENANT,
            entrega_id=entrega.id,
            orden=1,
            disparado_por=uuid4(),
            rubrica_id="r1",
            artefacto_sha256="s",
        )
        c.pdf_storage_key = None
        self.db.execute = AsyncMock(
            side_effect=[
                _scalar(entrega),
                MagicMock(first=MagicMock(return_value=(1,))),
                _scalar(c),
            ]
        )
        r = client.get(f"/api/v1/entregas/{entrega.id}/correccion-ia/{c.id or uuid4()}/pdf")
        assert r.status_code == 404


class TestBorrarPDF:
    async def test_si_el_storage_falla_devuelve_False(self) -> None:
        """De este booleano depende `pdfs_con_error`: el mecanismo entero de
        "un PDF que no se puede borrar queda listado" cuelga de aca."""
        from evaluation_service.services import correccion_pdf as mod

        fake = MagicMock()
        fake.delete = AsyncMock(side_effect=RuntimeError("storage caido"))
        with patch.object(mod, "get_storage", MagicMock(return_value=fake)):
            assert await mod.borrar("k.pdf") is False

    async def test_si_el_storage_anda_devuelve_True(self) -> None:
        from evaluation_service.services import correccion_pdf as mod

        fake = MagicMock()
        fake.delete = AsyncMock()
        with patch.object(mod, "get_storage", MagicMock(return_value=fake)):
            assert await mod.borrar("k.pdf") is True

    async def test_una_respuesta_que_no_es_200_NO_se_guarda_como_pdf(self) -> None:
        """Un 404 o un HTML de error de Active-IA quedaria en el bucket con
        extension .pdf y `tiene_pdf: true`."""
        from evaluation_service.services import correccion_pdf as mod

        cliente = MagicMock()
        cliente.request = AsyncMock(
            return_value=MagicMock(status_code=500, content=b"<html>error</html>")
        )
        fake = MagicMock()
        fake.put = AsyncMock()
        with patch.object(mod, "get_storage", MagicMock(return_value=fake)):
            key = await mod.bajar_y_guardar(
                cliente=cliente,
                tenant_id=uuid4(),
                entrega_id=uuid4(),
                correccion_id=uuid4(),
                external_correccion_id="42",
            )
        assert key is None
        fake.put.assert_not_awaited()


class TestLaClasificacionUsaLosCodigosQueElFlujoEmITE:
    """Los códigos de acá salieron de grepear qué escribe producción, no de
    inventarlos (19/08, hallazgo de la auditoría).

    Por qué importa el detalle: los tests que ya existían probaban el lado
    "rechazo" con `RUBRICA_INEXISTENTE`, un código **que no emite nadie**. Con
    un código inventado, cualquier cosa que no esté en el set da `False` y el
    test pasa — por eso seis códigos de infraestructura real estuvieron
    clasificados como rechazo sin que nada fallara.

    Y no es cosmético: `es_infraestructura` es lo ÚNICO que decide si la UI
    muestra el botón "Reintentar" (`CorreccionIAPanel.tsx`). Clasificar mal un
    fallo de infra le esconde al docente el botón que resolvería el problema.
    """

    @pytest.mark.parametrize(
        "code",
        [
            "GEMINI_OVERLOADED",  # el motor saturado
            "HTTP_500",
            "HTTP_502",
            "HTTP_503",
            "HTTP_504",  # cualquier 5xx de la API
            "PROCESO_INTERRUMPIDO",  # lo escribe el reconciliador
            "ERROR_INTERNO",  # el except general del ejecutor
            "SIN_NOTA",  # respondió sin nota
            "SIN_ENTREGA_ID",  # 201 sin id
            "CONFLICTO_SIN_SALIDA",  # 409 que no se pudo ubicar
            "TIMEOUT",
        ],
    )
    def test_es_infraestructura_y_por_lo_tanto_reintentable(self, code: str) -> None:
        from evaluation_service.services.correccion_ia import mapear_error_activeia

        _, infra = mapear_error_activeia(code, "")
        assert infra is True, (
            f"{code} es infraestructura; clasificado como rechazo, la UI le "
            "esconde el boton de reintentar al docente"
        )

    @pytest.mark.parametrize(
        "code",
        [
            "NO_COMPILA",
            "SIN_RUBRICA",
            "LENGUAJE_DESCONOCIDO",
            "HTTP_422",
            "HTTP_400",
            "HTTP_403",
        ],
    )
    def test_es_rechazo_y_reintentar_no_lo_arregla(self, code: str) -> None:
        """El otro lado: si TODO fuera infraestructura, el botón aparecería
        siempre y el docente reintentaría errores que nunca se destraban."""
        from evaluation_service.services.correccion_ia import mapear_error_activeia

        _, infra = mapear_error_activeia(code, "")
        assert infra is False, f"{code} es un rechazo: reintentar devuelve lo mismo"
