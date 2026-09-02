"""EL CABLE: que el corrector propio esté de verdad enchufado.

POR QUÉ ESTE ARCHIVO EXISTE APARTE
----------------------------------
`test_correccion_nativa.py` prueba el MOTOR: que la suma sea nuestra, que una
rúbrica mal respetada no produzca nota, que los casos ocultos no viajen. Todo
eso puede estar perfecto y **no correr nunca**.

Es el modo de falla que ya apareció DOS VECES en este repo, en los dos PRs
anteriores: la lógica se extrae a un módulo para poder testearla, queda con
cobertura, y el cable que la conecta al endpoint no lo prueba nadie. En #86 era
`_reabrir_ejercicios`, que existía y andaba pero `return_entrega` no la
llamaba. En #88, `mensajeDeCorrida` y el `CodeEditor`.

Así que acá se prueba lo otro: que apretar el botón con `CORRECCION_MOTOR=nativa`
termine llamando a ESTE corrector, que la nota que se escribe en la fila salga
de NUESTRA suma, y que un fallo del gateway cierre la fila sin nota.

Verificado por reversión degradando el cable —dejando el `if` del selector
apuntando siempre a Active-IA— y no borrándolo.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from evaluation_service.models.correcciones_ia import CorreccionIA
from evaluation_service.services import correccion_nativa
from evaluation_service.services.correccion_ia import mapear_error_activeia
from evaluation_service.services.correccion_pre_ejecucion import ResultadoTests

TENANT = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
COMISION = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

# La rúbrica real de la ficha del alumno (Programación I). Suma 10.
RUBRICA = [
    {"nombre": "Cuatro entradas correctas", "descripcion": "los 4 datos", "puntaje_max": 3},
    {"nombre": "Uso de variables descriptivas", "descripcion": "nombres claros", "puntaje_max": 2},
    {"nombre": "Salida con f-string", "descripcion": "un solo print", "puntaje_max": 3},
    {"nombre": "Formato exacto", "descripcion": "espacios y comas", "puntaje_max": 2},
]

EJERCICIO = correccion_nativa.EjercicioParaCorregir(
    id=uuid4(),
    titulo="Datos personales",
    enunciado_md="Pedí nombre, apellido, edad y ciudad.",
    rubrica=RUBRICA,
    prerequisitos={"sintacticos": ["input()", "print()"], "conceptuales": ["variable"]},
    materia_id=uuid4(),
)

TESTS_OK = ResultadoTests(compila=True, total=2, passed=2, failed=0).as_dict()


def _respuesta_del_modelo(*puntajes: float) -> str:
    import json

    return json.dumps(
        {
            "criterios": [
                {"nombre": c["nombre"], "puntaje": p, "justificacion": "porque si"}
                for c, p in zip(RUBRICA, puntajes, strict=True)
            ]
        },
        ensure_ascii=False,
    )


def _gateway(content: str, *, modelo: str = "google/gemini-2.5-flash-lite") -> MagicMock:
    """Un ai-gateway que devuelve `content`. Guarda con qué lo llamaron."""
    from evaluation_service.services.clients import CompleteResult

    gw = MagicMock()
    gw.complete = AsyncMock(
        return_value=CompleteResult(
            content=content,
            model=modelo,
            provider="openrouter",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0001,
        )
    )
    return gw


def _governance() -> MagicMock:
    from evaluation_service.services.clients import PromptConfig

    gov = MagicMock()
    gov.get_prompt = AsyncMock(
        return_value=PromptConfig(
            name="correccion",
            version="v1.0.0",
            content="Sos un docente corrigiendo.",
            hash="f" * 64,
        )
    )
    return gov


def _fila() -> CorreccionIA:
    c = CorreccionIA(
        tenant_id=TENANT,
        entrega_id=uuid4(),
        orden=1,
        disparado_por=uuid4(),
        rubrica_id="nativa:abc",
        artefacto_sha256="s",
    )
    c.id = uuid4()
    c.nota_100 = None
    c.estado = "pending"
    return c


def _sesion_con(fila: CorreccionIA) -> MagicMock:
    ctx = MagicMock()
    sesion = MagicMock()
    sesion.get = AsyncMock(return_value=fila)
    ctx.__aenter__ = AsyncMock(return_value=sesion)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestElSelectorRuteaDeVerdad:
    """Lo que faltó en los dos PRs anteriores."""

    async def test_con_motor_nativo_NO_se_llama_a_activeia(self) -> None:
        """Si el selector no está cableado, esto pasa igual con la lógica nueva
        escrita y sin usar: el ejecutor sigue yendo a Active-IA."""
        from evaluation_service.services import correccion_ejecutor as mod

        fila = _fila()
        with (
            patch.object(mod, "tenant_session", MagicMock(return_value=_sesion_con(fila))),
            patch.object(mod, "correr_tests", AsyncMock(return_value=ResultadoTests(compila=True))),
            patch.object(mod.settings, "correccion_motor", "nativa"),
            patch.object(
                mod.correccion_nativa, "leer_ejercicio", AsyncMock(return_value=EJERCICIO)
            ),
            patch.object(
                mod.correccion_nativa,
                "corregir_con_ia_nativa",
                AsyncMock(return_value={"nota_100": Decimal("90.00"), "desglose": []}),
            ) as nativo,
            patch(
                "evaluation_service.services.activeia_credenciales.cliente_para", AsyncMock()
            ) as activeia,
        ):
            await mod.ejecutar_correccion(
                correccion_id=fila.id,
                tenant_id=TENANT,
                user_id=uuid4(),
                comision_id=COMISION,
                ejercicio_id=EJERCICIO.id,
                codigo="print('hola')",
                language="python",
                alumno_nombre="pseudo",
                ejercicio_ref="ej-1",
                headers_sandbox={},
            )

        nativo.assert_awaited_once()
        activeia.assert_not_awaited()

    async def test_con_motor_activeia_NO_se_llama_al_nativo(self) -> None:
        """La otra mitad. Sin esto, un cable invertido pasaría el test de arriba."""
        from evaluation_service.services import correccion_ejecutor as mod

        fila = _fila()
        with (
            patch.object(mod, "tenant_session", MagicMock(return_value=_sesion_con(fila))),
            patch.object(mod, "correr_tests", AsyncMock(return_value=ResultadoTests(compila=True))),
            patch.object(mod.settings, "correccion_motor", "activeia"),
            patch.object(mod.correccion_nativa, "corregir_con_ia_nativa", AsyncMock()) as nativo,
            patch(
                "evaluation_service.services.activeia_credenciales.cliente_para", AsyncMock()
            ) as activeia,
        ):
            await mod.ejecutar_correccion(
                correccion_id=fila.id,
                tenant_id=TENANT,
                user_id=uuid4(),
                comision_id=COMISION,
                ejercicio_id=EJERCICIO.id,
                codigo="print('hola')",
                language="python",
                alumno_nombre="pseudo",
                ejercicio_ref="ej-1",
                headers_sandbox={},
            )

        nativo.assert_not_awaited()
        activeia.assert_awaited()


class TestLaNotaQueSeEscribeEsLaNuestra:
    """El circuito entero, con el gateway falso. Lo que termina en la fila."""

    async def _correr(self, content: str) -> CorreccionIA:
        from evaluation_service.services import correccion_ejecutor as mod

        fila = _fila()
        with (
            patch.object(mod, "tenant_session", MagicMock(return_value=_sesion_con(fila))),
            patch.object(
                mod,
                "correr_tests",
                AsyncMock(return_value=ResultadoTests(compila=True, total=2, passed=2)),
            ),
            patch.object(mod.settings, "correccion_motor", "nativa"),
            patch.object(
                mod.correccion_nativa, "leer_ejercicio", AsyncMock(return_value=EJERCICIO)
            ),
            patch("evaluation_service.services.clients.AIGatewayClient", lambda *a, **k: self.gw),
            patch("evaluation_service.services.clients.GovernanceClient", lambda *a, **k: self.gov),
        ):
            await mod.ejecutar_correccion(
                correccion_id=fila.id,
                tenant_id=TENANT,
                user_id=uuid4(),
                comision_id=COMISION,
                ejercicio_id=EJERCICIO.id,
                codigo="nombre = input()",
                language="python",
                alumno_nombre="pseudo",
                ejercicio_ref="",
                headers_sandbox={},
            )
        return fila

    async def test_la_nota_sale_de_la_suma_de_los_criterios(self) -> None:
        """3+1+3+2 = 9 sobre 10 = 90,00. El modelo nunca dijo "90"."""
        self.gw = _gateway(_respuesta_del_modelo(3, 1, 3, 2))
        self.gov = _governance()

        fila = await self._correr("")

        assert fila.estado == "done"
        assert fila.nota_100 == Decimal("90.00")
        assert [d["puntaje"] for d in fila.desglose] == [3, 1, 3, 2]

    async def test_queda_registrado_con_que_se_corrigio(self) -> None:
        """«¿Por qué le puso 6?» tres meses después."""
        self.gw = _gateway(_respuesta_del_modelo(3, 2, 3, 2))
        self.gov = _governance()

        fila = await self._correr("")

        assert fila.motor == "nativa"
        assert fila.prompt_version == "correccion/v1.0.0"
        assert fila.prompt_hash == "f" * 64
        assert fila.modelo == "google/gemini-2.5-flash-lite"

    async def test_el_prompt_del_governance_es_el_system_message(self) -> None:
        """No un string del código: versionado y con hash, como los del tutor."""
        self.gw = _gateway(_respuesta_del_modelo(3, 2, 3, 2))
        self.gov = _governance()

        await self._correr("")

        mensajes = self.gw.complete.await_args.kwargs["messages"]
        assert mensajes[0]["role"] == "system"
        assert mensajes[0]["content"] == "Sos un docente corrigiendo."

    async def test_el_esquema_que_viaja_no_admite_una_nota_total(self) -> None:
        """La defensa más barata contra que la nota la calcule el modelo."""
        self.gw = _gateway(_respuesta_del_modelo(3, 2, 3, 2))
        self.gov = _governance()

        await self._correr("")

        esquema = self.gw.complete.await_args.kwargs["response_format"]
        assert list(esquema["json_schema"]["schema"]["properties"]) == ["criterios"]

    async def test_un_desglose_que_no_respeta_la_rubrica_NO_da_nota(self) -> None:
        """Falta un criterio. Completarlo con 0 sería ponerle número a algo que
        nadie evaluó — y el CHECK de la base ni siquiera lo permitiría junto a
        `estado='error'`."""
        import json

        self.gw = _gateway(
            json.dumps({"criterios": [{"nombre": "Formato exacto", "puntaje": 2, "j": ""}]})
        )
        self.gov = _governance()

        fila = await self._correr("")

        assert fila.estado == "error"
        assert fila.nota_100 is None
        assert fila.error_code == "MODELO_NO_RESPETO_RUBRICA"
        # Y con la procedencia igual: saber con qué modelo pasó es lo que hace
        # falta para arreglarlo.
        assert fila.modelo == "google/gemini-2.5-flash-lite"

    async def test_el_gateway_caido_NO_es_una_nota(self) -> None:
        """La regla de oro del epic, en el motor nuevo."""
        from evaluation_service.services.clients import AIGatewayError

        self.gw = MagicMock()
        self.gw.complete = AsyncMock(side_effect=AIGatewayError("openrouter: 403 key limit"))
        self.gov = _governance()

        fila = await self._correr("")

        assert fila.estado == "error"
        assert fila.nota_100 is None
        assert fila.error_code == "GATEWAY_ERROR"

    async def test_una_respuesta_ilegible_NO_es_una_nota(self) -> None:
        self.gw = _gateway("Le pondría un 7, está bastante bien.")
        self.gov = _governance()

        fila = await self._correr("")

        assert fila.estado == "error"
        assert fila.nota_100 is None


class TestLosTresErroresNuevosOfrecenReintentar:
    """`es_infraestructura` es lo ÚNICO que decide si la UI muestra el botón.

    El flag NO se persiste: la pantalla lo re-deriva del código guardado cada
    vez que pinta una fila. Un código que el flujo emite y que no está en el set
    pinta rojo y esconde el botón — que es exactamente lo que le pasó a
    `PROCESO_INTERRUMPIDO`, cuyo propio mensaje decía "podés volver a
    dispararla" sobre una pantalla sin el botón para hacerlo.
    """

    def test_gateway_caido_prompt_ausente_y_modelo_desobediente(self) -> None:
        for code in ("GATEWAY_ERROR", "SIN_PROMPT", "MODELO_NO_RESPETO_RUBRICA"):
            _, infra = mapear_error_activeia(code, "")
            assert infra, f"{code} esconde el boton de reintentar"

    def test_los_rechazos_del_motor_propio_NO_lo_ofrecen(self) -> None:
        """Sin rúbrica cargada, reintentar devuelve exactamente lo mismo."""
        for code in ("SIN_RUBRICA", "SIN_EJERCICIO"):
            _, infra = mapear_error_activeia(code, "")
            assert not infra, f"{code} ofrece reintentar algo que no se destraba solo"


class TestLaRubricaDelDocenteMandaEnLaIdempotencia:
    def test_editar_la_rubrica_cambia_el_id_de_la_correccion(self) -> None:
        """`rubrica_id` entra en `uq_correccion_ia_idempotencia`. Si fuera una
        constante, la corrección vieja seguiría matcheando y el botón devolvería
        la nota calculada con la rúbrica que ya no existe."""
        otra = [*RUBRICA[:3], {**RUBRICA[3], "puntaje_max": 5}]

        assert correccion_nativa.rubrica_id_nativa(RUBRICA) != (
            correccion_nativa.rubrica_id_nativa(otra)
        )

    def test_la_misma_rubrica_da_el_mismo_id(self) -> None:
        """Y el orden de las claves no lo cambia: la fórmula es canónica."""
        desordenada = [{"puntaje_max": c["puntaje_max"], **c} for c in RUBRICA]

        assert correccion_nativa.rubrica_id_nativa(RUBRICA) == (
            correccion_nativa.rubrica_id_nativa(desordenada)
        )

    def test_entra_en_la_columna(self) -> None:
        """`rubrica_id` es String(100)."""
        assert len(correccion_nativa.rubrica_id_nativa(RUBRICA)) <= 100


class TestLaRutaTambienEstaCableada:
    """El otro extremo del cable: el 202 que dispara todo esto.

    El ejecutor puede rutear perfecto y no llegar nunca, porque la ruta corta
    antes: con `activeia_enabled=False` devolvía 503, y `resolver_rubrica` exigía
    un vínculo sincronizado con Active-IA que en el camino propio no existe.
    """

    async def test_no_exige_el_vinculo_con_activeia(self) -> None:
        """Es LA razón de ser de este motor. `resolver_rubrica` levanta
        `CorreccionRechazadaError` cuando no hay vínculo — y en el camino propio
        no lo hay ni lo tiene que haber: la rúbrica es la local."""
        from evaluation_service.services import correccion_ia as mod

        db = MagicMock()
        with (
            patch.object(mod, "resolver_rubrica", AsyncMock()) as activeia,
            patch(
                "evaluation_service.services.correccion_nativa.leer_ejercicio",
                AsyncMock(return_value=EJERCICIO),
            ),
            patch("evaluation_service.config.settings.correccion_motor", "nativa"),
        ):
            elegida = await mod.resolver_rubrica_del_motor(db, TENANT, EJERCICIO.id)

        activeia.assert_not_awaited()
        assert elegida.rubrica_id == correccion_nativa.rubrica_id_nativa(RUBRICA)
        assert elegida.external_ref == ""

    async def test_con_motor_activeia_SI_lo_exige(self) -> None:
        """La otra mitad: el camino de siempre no cambió."""
        from evaluation_service.services import correccion_ia as mod

        vinculo = MagicMock()
        vinculo.rubrica_id = "RUB-123"
        vinculo.external_ref = "ej-1"
        with (
            patch.object(mod, "resolver_rubrica", AsyncMock(return_value=vinculo)) as activeia,
            patch("evaluation_service.config.settings.correccion_motor", "activeia"),
        ):
            elegida = await mod.resolver_rubrica_del_motor(MagicMock(), TENANT, EJERCICIO.id)

        activeia.assert_awaited_once()
        assert elegida.rubrica_id == "RUB-123"
        assert elegida.external_ref == "ej-1"

    async def test_un_ejercicio_sin_rubrica_se_rechaza_ANTES_de_gastar(self) -> None:
        """Rechazar acá no consume cuota, y el docente se entera cuando todavía
        puede cargar la rúbrica — no después de que la corrección falló."""
        import pytest
        from evaluation_service.services.correccion_ia import (
            CorreccionRechazadaError,
            resolver_rubrica_del_motor,
        )

        sin_rubrica = correccion_nativa.EjercicioParaCorregir(
            id=uuid4(),
            titulo="x",
            enunciado_md="x",
            rubrica=None,
            prerequisitos={},
            materia_id=None,
        )
        with (
            patch(
                "evaluation_service.services.correccion_nativa.leer_ejercicio",
                AsyncMock(return_value=sin_rubrica),
            ),
            patch("evaluation_service.config.settings.correccion_motor", "nativa"),
            pytest.raises(CorreccionRechazadaError),
        ):
            await resolver_rubrica_del_motor(MagicMock(), TENANT, sin_rubrica.id)

    def test_el_503_de_activeia_no_apaga_el_motor_propio(self) -> None:
        """`activeia_enabled` falla cerrado y gobierna el camino de Active-IA.
        Atarle el propio obligaría a prender Active-IA para no usarlo.

        Contra la app real: se pide una entrega que no existe. Lo que importa
        NO es el 404 —es que la respuesta no sea el 503 del kill-switch, o sea
        que el request haya pasado el gate.
        """
        from evaluation_service.auth import get_db as _get_db
        from evaluation_service.auth.dependencies import User, get_current_user
        from evaluation_service.main import app
        from evaluation_service.routes import correccion_ia as ruta
        from fastapi.testclient import TestClient

        docente = User(
            id=uuid4(),
            tenant_id=TENANT,
            email="d@utn.edu.ar",
            roles=frozenset({"docente"}),
            realm="utn",
        )
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
        app.dependency_overrides[get_current_user] = lambda: docente
        app.dependency_overrides[_get_db] = lambda: db
        try:
            with (
                TestClient(app) as c,
                patch.object(ruta.settings, "activeia_enabled", False),
                patch.object(ruta.settings, "correccion_motor", "nativa"),
            ):
                r = c.post(
                    f"/api/v1/entregas/{uuid4()}/correccion-ia",
                    json={"ejercicio_orden": 1, "confirmado": True},
                )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code != 503, (
            "el gate volvio a ser solo `activeia_enabled`: con el motor propio "
            "prendido y Active-IA apagado, el endpoint no deja disparar nada"
        )
