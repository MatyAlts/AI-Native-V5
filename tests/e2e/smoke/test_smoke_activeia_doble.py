"""Smoke del circuito de corrección con Active-IA reemplazado por un doble HTTP.

**Por qué un doble y no la API real** (tarea 6.1). Cada corrida contra Active-IA
cuesta dinero, tarda decenas de segundos y deja una entrega cargada del otro
lado. Y los caminos que más importan —el motor saturado, la credencial vencida—
no se pueden provocar a demanda contra el servicio real. Con un doble sí, y son
justo los que nunca se prueban hasta que pasan en producción.

**Por qué HTTP de verdad y no un mock del cliente.** Lo que se prueba acá es el
cliente: que re-loguee ante un 401, que distinga un 4xx (rechazo definitivo) de
un 5xx (infraestructura), que no invente una nota cuando no vino. Un `MagicMock`
devuelve lo que se le pida y ninguna de esas cosas se ejercita — misma clase de
test vacuo que ya apareció seis veces en este epic.

**Este archivo es la especificación ejecutable del contrato** (punto 3 del
pedido de Active-IA del 24/08). Lo que el doble acepta y responde es lo que
esperamos de ellos; si algo no coincide, preferimos que aparezca acá.

---

**Reescrito el 2026-08-27 para el endpoint del §3.4.** Hasta esta fecha el doble
hablaba el camino de tres pasos —subir un zip, disparar, poletear cada 5s— y
tenía tres tests dedicados al 409 de entrega duplicada. Ese camino **ya no
existe**: Active-IA construyó el endpoint sincrónico que le pedimos y con él el
zip, el 409 y el polling desaparecen. Los tests que los cubrían se borraron en
vez de adaptarse: probaban ramas que el cliente ya no tiene, y un test verde
sobre código muerto es peor que ninguno.

Lo que se ganó de paso: el cuerpo ahora es **JSON**, así que el doble lo parsea
y verifica el contrato de verdad. Antes era multipart con `Transfer-Encoding:
chunked`, que `BaseHTTPRequestHandler` no sabe leer, y los tres tests de "esto
viaja" tenían que espiar con un cliente falso — o sea, dejaban de probar el
transporte justo donde decían probarlo.

El doble corre en un thread de este proceso; no hace falta stack levantado, así
que **este archivo no depende del gate de health de la suite**.

Correr:
    uv run pytest tests/e2e/smoke/test_smoke_activeia_doble.py -v
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from uuid import uuid4

import pytest
from evaluation_service.services.activeia_client import ActiveIAClient, ActiveIAError
from evaluation_service.services.correccion_ejecutor import (
    _corregir_ejercicio,
    _marcar_sin_ejecucion,
    _resultado_tests_para_activeia,
)

# El guion que cada test le pone al doble antes de arrancar: qué responde y
# cuántas veces. Vive a nivel de módulo porque el handler de http.server se
# instancia por request y no puede llevar estado propio.
# El doble corre en proceso: estos tests no necesitan el stack levantado.
pytestmark = pytest.mark.sin_stack

GUION: dict[str, Any] = {}
LLAMADAS: list[tuple[str, str]] = []
CUERPOS: list[dict[str, Any]] = []

# El cuerpo que el doble contesta es el de ELLOS, no el nuestro. Dos cosas que
# se confundían hasta el 2026-08-28:
#
#   - El campo se llama **`nota`**, no `nota_100`. Active-IA lo confirmó por
#     escrito el 27/08 (§4.2: «no existe `nota_100`, ni `nota_final`, ni
#     `calificacion`») y `1b9ac8b` bajó la cascada de cuatro nombres a uno en
#     `_corregir_ejercicio`. Este archivo se quedó en `nota_100` y nadie se
#     enteró porque nada lo corría: no lleva `@pytest.mark.smoke`, así que
#     `make test-smoke` lo tiraba al montón de `19 deselected`, y el job
#     `Unit tests` sólo mira `apps/*/tests/` y `packages/*/tests/`.
#     Con el nombre viejo el doble devolvía 200 sin nota → `SIN_NOTA`, y los
#     cuatro tests del camino feliz fallaban.
#   - **Viaja como STRING** (`"8.50"`, con comillas): default de Pydantic v2
#     para `Decimal`, deliberado de su lado para que una nota no pase por un
#     float. Ponerlo como número acá dejaría el casteo explícito de
#     `_corregir_ejercicio` sin ejercitar, que es justo lo que ese commit
#     agregó.
#
# `nota_100` sigue siendo el nombre INTERNO de la clave que devuelve
# `_corregir_ejercicio`; por eso los asserts de abajo lo usan y este dict no.
_NOTA_OK = {
    "nota": "8.50",
    "correccion_id": "COR-1",
    "entrega_id": "EXT-1",
    "desglose": [
        {"nombre": "Usa la interfaz", "puntaje": 3, "puntaje_max": 3},
        {"nombre": "Produce la salida esperada", "puntaje": 4, "puntaje_max": 4},
    ],
}


class _DobleActiveIA(BaseHTTPRequestHandler):
    """Habla el dialecto del endpoint del §3.4.

    Una sola ruta de corrección, sincrónica:
      `POST /correcciones/ejercicios/{ejercicio_ref}/corregir` → 200 con la nota.

    Lo que este doble **no** tiene, a propósito, porque el endpoint real
    tampoco: `/entregas/`, el 409 por entrega duplicada, y el poll. Una llamada
    a cualquiera de esos da 404 y el test que la provoque falla — que es lo que
    queremos si alguien reintroduce el camino viejo.
    """

    def log_message(self, *args: Any) -> None:  # silencia el log a stderr
        pass

    def _responder(self, code: int, cuerpo: Any = None) -> None:
        payload = json.dumps(cuerpo if cuerpo is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        LLAMADAS.append(("POST", self.path))
        largo = int(self.headers.get("Content-Length", 0))
        crudo = self.rfile.read(largo) if largo else b""

        if self.path == "/auth/login":
            if GUION.get("login_falla"):
                self._responder(401, {"detail": "credenciales invalidas"})
            else:
                self._responder(200, {"access_token": "token-de-prueba"})
            return

        if self.path.startswith("/correcciones/ejercicios/") and self.path.endswith("/corregir"):
            # El cuerpo es JSON: se guarda para que los tests verifiquen el
            # contrato exacto que viaja, no una aproximación.
            try:
                CUERPOS.append(json.loads(crudo or b"{}"))
            except json.JSONDecodeError:
                CUERPOS.append({"__no_era_json__": crudo.decode("utf-8", "replace")})
            self._responder(GUION.get("corregir_status", 200), GUION.get("corregir_body", _NOTA_OK))
            return

        self._responder(404, {"detail": "ruta no prevista por el doble"})

    def do_GET(self) -> None:
        LLAMADAS.append(("GET", self.path))
        self._responder(404, {"detail": "ruta no prevista por el doble"})


@pytest.fixture
def doble() -> Iterator[str]:
    """Levanta el doble en un puerto libre y devuelve su base url."""
    GUION.clear()
    LLAMADAS.clear()
    CUERPOS.clear()
    servidor = HTTPServer(("127.0.0.1", 0), _DobleActiveIA)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}"
    finally:
        servidor.shutdown()
        servidor.server_close()


def _cliente(base: str) -> ActiveIAClient:
    return ActiveIAClient(base, "docente@test", "secreto", timeout=5.0)


async def _correr(base: str, **kw: Any) -> dict[str, Any]:
    tests = {"compila": True, "passed": 3, "total": 4, "failed": 1, "casos": []}
    tests.update(kw.pop("tests", {}))
    return await _corregir_ejercicio(
        cliente=_cliente(base),
        ejercicio_ref=kw.pop("ejercicio_ref", "EJ-REF-1"),
        alumno_nombre=kw.pop("alumno_nombre", "pseudonimo-abc"),
        codigo=kw.pop("codigo", "public class Main {}"),
        tests=tests,
    )


class TestCaminoFeliz:
    async def test_una_sola_llamada_trae_la_nota(self, doble: str) -> None:
        """El endpoint es sincrónico: la nota vuelve en la respuesta.

        El assert sobre la cantidad de llamadas NO es cosmético: es lo que
        detecta que alguien reintrodujo el poll.
        """
        out = await _correr(doble)

        assert out.get("error_code") is None, out
        assert out["nota_100"] == 8.5
        assert out["external_correccion_id"] == "COR-1"

        corregir = [p for m, p in LLAMADAS if m == "POST" and p.endswith("/corregir")]
        assert len(corregir) == 1, f"se llamó más de una vez: {LLAMADAS}"
        assert not [p for m, p in LLAMADAS if m == "GET"], "volvió el poll"

    async def test_el_ejercicio_viaja_en_la_url_y_no_en_el_cuerpo(self, doble: str) -> None:
        """Es lo que cierra el «comision_id mal cableado».

        Hasta el 2026-08-27 el ejercicio viajaba como `comision_id` en el
        formulario — un id de ejercicio en el campo de una comisión. Ahora va
        en el path, que es su lugar, y no hay campo de comisión que confundir.
        """
        await _correr(doble, ejercicio_ref="EJ-DE-PRUEBA")

        assert ("POST", "/correcciones/ejercicios/EJ-DE-PRUEBA/corregir") in LLAMADAS
        assert "comision_id" not in CUERPOS[0]
        assert "comision_external_ref" not in CUERPOS[0], (
            "se mandó la comisión: el modelo de ellos usa la de integración (§3.3), "
            "y mandarles un id que no conocen es peor que no mandar nada"
        )

    async def test_el_cuerpo_es_el_contrato_que_acordamos(self, doble: str) -> None:
        """`{alumno_ref, codigo, resultado_tests}` — §3.4 del documento.

        Ojo con `pasados`: nuestro dataclass cuenta `passed` y el contrato dice
        `pasados`. Si el remapeo se pierde, ellos reciben el campo en `None` y
        la garantía de `compila: false` se apoya en un dato que no llegó.
        """
        await _correr(doble, tests={"passed": 3, "total": 4})

        cuerpo = CUERPOS[0]
        assert set(cuerpo) == {"alumno_ref", "codigo", "resultado_tests"}
        assert cuerpo["alumno_ref"] == "pseudonimo-abc"
        assert cuerpo["resultado_tests"]["pasados"] == 3
        assert cuerpo["resultado_tests"]["total"] == 4
        assert "passed" not in cuerpo["resultado_tests"]
        assert "failed" not in cuerpo["resultado_tests"], (
            "`failed` es `total - pasados`: mandar un tercer número que puede "
            "contradecir a los otros dos le da al motor a quién creerle mal"
        )


class TestLosCaminosQueNoSePuedenProvocarContraElServicioReal:
    async def test_motor_saturado_es_infraestructura_y_no_una_nota(self, doble: str) -> None:
        """Un 5xx NO puede convertirse en nota: es la invariante central del epic."""
        GUION.update(corregir_status=503)

        out = await _correr(doble)

        assert out["error_code"] == "HTTP_503"
        assert "nota_100" not in out

    async def test_el_5xx_le_dice_al_docente_que_REINTENTE(self, doble: str) -> None:
        """El `error_code` solo no distingue la rama que lo produjo.

        Con `status >= 500` roto (probado: cambiandolo por `status >= 900`), un
        503 cae a la rama de los 4xx y sale con el MISMO
        `error_code == "HTTP_503"` — el assert de arriba pasa igual. Lo que
        cambia es lo unico que el docente lee: el mensaje pasa de "Reintentar
        puede servir" a "Reintentar sin cambiar nada va a devolver lo mismo",
        sobre un motor que estaba saturado y que un minuto despues anda.

        (El flag `es_infraestructura` que decide si la UI ofrece "Reintentar" lo
        resuelve `mapear_error_activeia` por el prefijo `HTTP_5`, asi que ese
        sigue bien; el que miente es el texto.)
        """
        GUION.update(corregir_status=503)

        out = await _correr(doble)

        assert "Reintentar puede servir" in out["error_detail"], out["error_detail"]
        assert "rechaz" not in out["error_detail"].lower(), (
            "un 503 no es un rechazo: el motor no dijo que no, dijo que no pudo"
        )

    async def test_un_4xx_es_un_rechazo_definitivo(self, doble: str) -> None:
        """Un rechazo no se arregla esperando ni reintentando.

        El 422 es el caso concreto que ellos declararon (§3.4 de su documento):
        un caso oculto mal formado se rechaza nombrando el ejercicio y el caso,
        en vez de descartarse en silencio. Ese detalle tiene que sobrevivir
        hasta la pantalla del docente.
        """
        GUION.update(
            corregir_status=422,
            corregir_body={"detail": "caso oculto t3 del ejercicio EJ-1 trae salida esperada"},
        )

        out = await _correr(doble)

        assert out["error_code"] == "HTTP_422"
        assert "caso oculto t3" in out["error_detail"]
        assert "nota_100" not in out

    async def test_credencial_invalida_no_es_infraestructura(self, doble: str) -> None:
        """Un 401 es 'la cuenta está mal', no 'el servicio se cayó'. La
        distinción decide si se reintenta: reintentar una credencial vencida
        no la arregla."""
        GUION.update(login_falla=True)

        with pytest.raises(ActiveIAError) as e:
            await _correr(doble)

        assert e.value.es_infraestructura is False
        assert "contraseña" in e.value.mensaje.lower() or "usuario" in e.value.mensaje.lower()

    async def test_el_401_no_devuelve_el_cuerpo_que_mandamos(self, doble: str) -> None:
        """El body de un login fallido puede traer de vuelta lo que se envió."""
        GUION.update(login_falla=True)

        with pytest.raises(ActiveIAError) as e:
            await _correr(doble)

        assert "secreto" not in str(e.value)

    async def test_un_200_sin_nota_no_se_convierte_en_nota(self, doble: str) -> None:
        """Sin nota, el estado terminal es `error`. Nunca un cero, nunca un
        `None` que la UI pinte como algo."""
        GUION.update(corregir_body={"error_code": "MOTOR_SIN_SALIDA", "error_mensaje": "vacío"})

        out = await _correr(doble)

        assert out["error_code"] == "MOTOR_SIN_SALIDA"
        assert "nota_100" not in out

    async def test_una_respuesta_que_no_es_json_no_inventa_nada(self, doble: str) -> None:
        """Un HTML de proxy con 200 es un 200 sin resultado, no un resultado."""
        GUION.update(corregir_body={})

        out = await _correr(doble)

        assert out["error_code"] == "SIN_NOTA"


class TestReintentarEsLaMismaLlamada:
    async def test_no_hay_rama_de_conflicto(self, doble: str) -> None:
        """§4.2: en el endpoint de ejercicio no hay 409.

        Ellos reusan la entrega y archivan la corrección anterior en su
        historial. Nosotros no ramificamos: la segunda corrida es idéntica a la
        primera. Este test existe para que nadie reintroduzca el manejo del 409
        «por las dudas» — ese código era el que moría en `CONFLICTO_SIN_SALIDA`.
        """
        primera = await _correr(doble)
        segunda = await _correr(doble)

        assert primera["nota_100"] == segunda["nota_100"]
        corregir = [p for m, p in LLAMADAS if m == "POST" and p.endswith("/corregir")]
        assert len(corregir) == 2
        assert corregir[0] == corregir[1], "la segunda llamada no fue idéntica a la primera"
        assert not [p for m, p in LLAMADAS if p == "/entregas/"], "volvió el camino viejo"


class TestElCodigoQueNoCompilaSeMandaIgual:
    """Decisión del 19/08: un punto y coma que falta no justifica dejar al
    alumno sin devolución. El motor puede decirle si el diseño va encaminado,
    que es la parte que un compilador no le da.

    Ahora estos tests leen el cuerpo REAL que llegó al doble. Antes espiaban
    con un cliente falso porque el multipart no se podía parsear — o sea,
    dejaban de probar el transporte justo donde decían probarlo.
    """

    async def test_viaja_que_no_compilo_y_por_que(self, doble: str) -> None:
        await _correr(
            doble,
            tests={
                "compila": False,
                "passed": 0,
                "total": 6,
                "error_compilacion": "error: ';' expected",
            },
        )

        tests = CUERPOS[0]["resultado_tests"]
        assert tests["compila"] is False
        assert "';' expected" in tests["error_compilacion"]

    async def test_cuando_compila_lo_dice_igual(self, doble: str) -> None:
        """Sin el campo, `pasados: 0` no distingue «no compiló» de «compiló y
        falló todo», y son dos devoluciones distintas."""
        await _correr(doble, tests={"compila": True, "passed": 0, "total": 6})

        tests = CUERPOS[0]["resultado_tests"]
        assert tests["compila"] is True
        assert tests["error_compilacion"] is None

    async def test_sin_compilar_igual_se_pide_la_correccion(self, doble: str) -> None:
        """La prueba de que ya no corta: antes ni se enviaba."""
        out = await _correr(doble, tests={"compila": False, "passed": 0, "total": 6})

        assert out.get("error_code") is None, out
        assert CUERPOS, "no llegó a enviar: se cortó antes"

    def test_el_remapeo_no_pierde_el_error_de_compilacion(self) -> None:
        """Directo sobre la función pura: `""` y `None` son lo mismo acá, pero
        un mensaje de compilador NUNCA se puede perder — es lo que hace que la
        garantía de ellos sea aplicable."""
        salida = _resultado_tests_para_activeia(
            {"compila": False, "passed": 0, "total": 3, "error_compilacion": "boom"}
        )

        assert salida["error_compilacion"] == "boom"
        assert salida["compila"] is False
        assert salida["pasados"] == 0


class TestCriteriosQueNoSePudieronVerificar:
    """§3.2 del documento del 24/08.

    «No lo hizo» y «no se pudo verificar porque no compila» son dos cosas
    distintas y merecen leerse distinto. Sólo una de las dos es culpa del
    alumno, y mostrarlas iguales es el mismo modo de falla que le reportamos
    al motor.
    """

    async def test_llegan_marcados_en_el_desglose(self, doble: str) -> None:
        GUION.update(
            corregir_body={
                **_NOTA_OK,
                "criterios_sin_ejecucion": ["Produce la salida esperada"],
            }
        )

        out = await _correr(doble, tests={"compila": False, "passed": 0, "total": 4})

        assert out["criterios_sin_ejecucion"] == ["Produce la salida esperada"]

    def test_el_marcado_estampa_solo_el_criterio_que_corresponde(self) -> None:
        desglose = [
            {"nombre": "Usa la interfaz", "puntaje": 3},
            {"nombre": "Produce la salida esperada", "puntaje": 0},
        ]

        marcado = _marcar_sin_ejecucion(
            desglose, ["Produce la salida esperada"], correccion_id=uuid4()
        )

        assert marcado[0].get("sin_ejecucion") is None
        assert marcado[1]["sin_ejecucion"] is True
        assert desglose[1].get("sin_ejecucion") is None, "mutó la lista de entrada"

    def test_matchea_por_id_cuando_lo_traen(self) -> None:
        """El contrato no fija el nombre del identificador, así que se prueban
        los tres que pueden venir. Emparejar sólo por `nombre` fallaría en
        silencio el día que manden ids."""
        marcado = _marcar_sin_ejecucion(
            [{"id": "C5", "nombre": "El programa funciona"}], ["C5"], correccion_id=uuid4()
        )

        assert marcado[0]["sin_ejecucion"] is True

    def test_un_id_que_no_matchea_no_se_pierde_en_silencio(self) -> None:
        """El docente vería un 0 sin explicación. Se loguea, y el desglose
        vuelve intacto en vez de a medio marcar."""
        marcado = _marcar_sin_ejecucion(
            [{"nombre": "Usa la interfaz"}], ["CRITERIO-FANTASMA"], correccion_id=uuid4()
        )

        assert marcado == [{"nombre": "Usa la interfaz"}]

    def test_sin_criterios_devuelve_el_desglose_tal_cual(self) -> None:
        desglose = [{"nombre": "Usa la interfaz", "puntaje": 3}]

        assert _marcar_sin_ejecucion(desglose, [], correccion_id=uuid4()) == desglose
