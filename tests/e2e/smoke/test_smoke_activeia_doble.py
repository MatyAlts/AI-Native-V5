"""Smoke del circuito de corrección con Active-IA reemplazado por un doble HTTP.

**Por qué un doble y no la API real** (tarea 6.1). Cada corrida contra Active-IA
cuesta dinero, tarda decenas de segundos y deja una entrega cargada del otro
lado. Y los caminos que más importan —el motor saturado, la credencial vencida—
no se pueden provocar a demanda contra el servicio real. Con un doble sí, y son
justo los que nunca se prueban hasta que pasan en producción.

**Por qué HTTP de verdad y no un mock del cliente.** Lo que se prueba acá es el
cliente: que siga el redirect de `/entregas` a `/entregas/`, que re-loguee ante
un 401, que distinga un 4xx (rechazo definitivo) de un 5xx (infraestructura),
que retome ante el 409 en vez de volver a subir. Un `MagicMock` devuelve lo que
se le pida y ninguna de esas cosas se ejercita — misma clase de test vacuo que
ya apareció seis veces en este epic.

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

import pytest
from evaluation_service.services.activeia_client import ActiveIAClient, ActiveIAError
from evaluation_service.services.correccion_ejecutor import _subir_y_corregir

# El guion que cada test le pone al doble antes de arrancar: qué responde y
# cuántas veces. Vive a nivel de módulo porque el handler de http.server se
# instancia por request y no puede llevar estado propio.
# El doble corre en proceso: estos tests no necesitan el stack levantado.
pytestmark = pytest.mark.sin_stack

GUION: dict[str, Any] = {}
LLAMADAS: list[tuple[str, str]] = []


class _DobleActiveIA(BaseHTTPRequestHandler):
    """Habla el mismo dialecto que Active-IA, con las rarezas que tiene.

    Las tres que importan y que el cliente ya aprendió a mano:
      - `/entregas` redirige a `/entregas/` (por eso el cliente sigue redirects)
      - el poll es `GET /correcciones/entregas/{id}`: 200 corregida, 404 todavía no
      - el 409 keyea por `(comision_id, rubrica_id, alumno_nombre)`
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
        if largo:
            self.rfile.read(largo)

        if self.path == "/auth/login":
            if GUION.get("login_falla"):
                self._responder(401, {"detail": "credenciales invalidas"})
            else:
                self._responder(200, {"access_token": "token-de-prueba"})
            return

        if self.path == "/entregas/":
            self._responder(
                GUION.get("upload_status", 201), GUION.get("upload_body", {"id": "EXT-1"})
            )
            return

        if self.path.endswith("/corregir"):
            self._responder(GUION.get("corregir_status", 200), {})
            return

        self._responder(404, {"detail": "ruta no prevista por el doble"})

    def do_GET(self) -> None:
        LLAMADAS.append(("GET", self.path))

        if self.path.startswith("/correcciones/entregas/"):
            restantes = GUION.get("poll_404_restantes", 0)
            if restantes > 0:
                GUION["poll_404_restantes"] = restantes - 1
                self._responder(404, {"detail": "todavia no"})
                return
            self._responder(200, GUION.get("poll_body", {"nota_final": 8.5, "id": "COR-1"}))
            return

        if self.path.startswith("/entregas/"):
            # Listado que usa `_ubicar_entrega` para retomar tras el 409.
            self._responder(200, GUION.get("listado", {"items": []}))
            return

        self._responder(404, {"detail": "ruta no prevista por el doble"})


@pytest.fixture
def doble() -> Iterator[str]:
    """Levanta el doble en un puerto libre y devuelve su base url."""
    GUION.clear()
    LLAMADAS.clear()
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


async def _correr(base: str) -> dict[str, Any]:
    return await _subir_y_corregir(
        cliente=_cliente(base),
        codigo="public class Main {}",
        language="java",
        alumno_nombre="Alumno Prueba",
        comision_id="COM-1",
        rubrica_id="RUB-1",
        tests={"passed": 3, "total": 4},
    )


class TestCaminoFeliz:
    async def test_sube_dispara_poletea_y_trae_la_nota(self, doble: str) -> None:
        GUION.update(poll_404_restantes=0, poll_body={"nota_final": 8.5, "id": "COR-1"})

        out = await _correr(doble)

        assert out.get("error_code") is None, out
        assert out["external_entrega_id"] == "EXT-1"

    async def test_el_poll_espera_al_404_y_no_lo_toma_como_fallo(self, doble: str) -> None:
        """404 en el poll es 'todavía no', no 'salió mal'. Si se leyera como
        error, toda corrección que tarde más que el primer intento fallaría."""
        GUION.update(poll_404_restantes=1)

        out = await _correr(doble)

        assert out.get("error_code") is None, out
        polls = [p for m, p in LLAMADAS if m == "GET" and "/correcciones/" in p]
        assert len(polls) >= 2, "no reintentó tras el 404"


class TestLosCaminosQueNoSePuedenProvocarContraElServicioReal:
    async def test_gemini_saturado_es_infraestructura_y_no_una_nota(self, doble: str) -> None:
        """Un 5xx al disparar NO puede convertirse en nota: es la invariante
        central del epic."""
        GUION.update(corregir_status=503)

        out = await _correr(doble)

        assert out["error_code"] == "GEMINI_OVERLOADED"
        assert "nota_final" not in out

    async def test_un_4xx_al_disparar_corta_en_vez_de_poletear(self, doble: str) -> None:
        """Un rechazo no se arregla esperando. Antes sólo se cortaba con >=500,
        así que un 4xx se poleteaba hasta quemar el presupuesto entero."""
        GUION.update(corregir_status=422)

        out = await _correr(doble)

        assert out["error_code"] == "HTTP_422"
        assert not [p for m, p in LLAMADAS if m == "GET" and "/correcciones/" in p]

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


class TestEl409SeRetomaEnVezDeCobrarDosVeces:
    async def test_retoma_la_entrega_que_ya_estaba_arriba(self, doble: str) -> None:
        GUION.update(
            upload_status=409,
            listado={
                "items": [
                    {
                        "id": "EXT-YA-EXISTIA",
                        "comision_id": "COM-1",
                        "rubrica_id": "RUB-1",
                        "alumno_nombre": "Alumno Prueba",
                    }
                ]
            },
        )

        out = await _correr(doble)

        assert out.get("external_entrega_id") == "EXT-YA-EXISTIA"
        subidas = [p for m, p in LLAMADAS if m == "POST" and p == "/entregas/"]
        assert len(subidas) == 1, "volvió a subir: eso se cobra de nuevo"

    async def test_el_409_sin_entrega_ubicable_no_inventa_una(self, doble: str) -> None:
        """Si dice que existe y no aparece, se corta con un motivo legible en
        vez de seguir con un id vacío."""
        GUION.update(upload_status=409, listado={"items": []})

        out = await _correr(doble)

        assert out["error_code"] == "CONFLICTO_SIN_SALIDA"

    async def test_no_retoma_la_entrega_de_otro_tp_del_mismo_alumno(self, doble: str) -> None:
        """El match tiene que incluir `rubrica_id`. Sin él se retomaba la
        entrega de OTRA unidad del mismo alumno y se le adjuntaba la
        devolución equivocada."""
        GUION.update(
            upload_status=409,
            listado={
                "items": [
                    {
                        "id": "EXT-DE-OTRO-TP",
                        "comision_id": "COM-1",
                        "rubrica_id": "RUB-DISTINTA",
                        "alumno_nombre": "Alumno Prueba",
                    }
                ]
            },
        )

        out = await _correr(doble)

        assert out.get("external_entrega_id") != "EXT-DE-OTRO-TP"
        assert out.get("error_code") == "CONFLICTO_SIN_SALIDA"


class TestFallosDeSubida:
    async def test_un_5xx_al_subir_no_sigue_adelante(self, doble: str) -> None:
        GUION.update(upload_status=502)

        out = await _correr(doble)

        assert out["error_code"] == "HTTP_502"
        assert not [p for m, p in LLAMADAS if p.endswith("/corregir")]

    async def test_sin_id_en_la_respuesta_se_corta(self, doble: str) -> None:
        """Un 201 sin `id` deja el circuito sin a qué apuntar."""
        GUION.update(upload_status=201, upload_body={})

        out = await _correr(doble)

        assert out["error_code"] == "SIN_ENTREGA_ID"
