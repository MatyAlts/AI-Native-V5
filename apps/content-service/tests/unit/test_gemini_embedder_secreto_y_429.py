"""La API key de Gemini no puede viajar en la URL, y un 429 no puede ser un 500.

Los dos hallazgos salieron de la misma sesion de QA del 31/08/2026 y viven en
la misma clase, asi que van juntos.

EL SECRETO
----------
`_embed_one` mandaba la key con `params={"key": self._api_key}`. Google acepta
esa forma, pero mete el secreto DENTRO de la URL — y una URL no es un lugar
privado: httpx la imprime entera al construir el texto de `HTTPStatusError`,
asi que cada error contra Google escribia la `GEMINI_API_KEY` en texto plano
en los logs de produccion. Se encontro leyendo los logs, no el codigo.

Lo importante: nadie tomo la decision de loguear el secreto. Se logueaba solo,
como efecto de haberlo puesto en un lugar que se imprime. Por eso el test no
mira los logs —eso seria perseguir el sintoma— sino la URL, que es la causa.

EL 429
------
`_embed_one` no reintentaba. Un limite de tasa —temporal por definicion, y con
un `Retry-After` que dice cuanto esperar— salia por `POST /retrieve` como un
500 al alumno: el tutor sin material, por algo que se arreglaba esperando un
segundo.
"""

from __future__ import annotations

import httpx
import pytest
from content_service.embedding.embedder import GeminiEmbedder, _retry_after_segundos

KEY = "AIzaSyTOTALMENTE-FALSA-PERO-RECONOCIBLE"


async def _no_dormir(segundos: float) -> None:
    return None


def _embedder(monkeypatch: pytest.MonkeyPatch) -> GeminiEmbedder:
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    return GeminiEmbedder()


def _respuesta_ok() -> dict:
    return {"embedding": {"values": [0.1] * 1024}}


class TestLaKeyNoViajaEnLaURL:
    async def test_la_url_del_request_no_contiene_la_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El corazon del fix.

        Verificado por reversion: con `params={"key": ...}` la URL termina en
        `?key=AIza...` y este assert falla nombrando el secreto entero.
        """
        emb = _embedder(monkeypatch)
        vistas: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            vistas.append(str(request.url))
            return httpx.Response(200, json=_respuesta_ok())

        emb._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers={"x-goog-api-key": KEY}
        )
        await emb.embed_query("hola")

        assert vistas, "no se llego a hacer el request"
        assert KEY not in vistas[0], f"la key quedo en la URL: {vistas[0]}"
        assert "key=" not in vistas[0]

    async def test_la_key_viaja_en_el_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Y tiene que seguir autenticando.

        Sacarla de la URL sin ponerla en el header seria 'arreglar' el leak
        rompiendo el servicio.
        """
        emb = _embedder(monkeypatch)
        vistos: list[httpx.Headers] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            vistos.append(request.headers)
            return httpx.Response(200, json=_respuesta_ok())

        emb._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers={"x-goog-api-key": KEY}
        )
        await emb.embed_query("hola")

        assert vistos[0].get("x-goog-api-key") == KEY

    def test_el_cliente_nace_con_el_header_puesto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """La key se configura UNA vez, en el cliente.

        Ponerla en cada `post()` deja tantos lugares donde puede volver a
        colarse en la URL como call-sites haya.
        """
        emb = _embedder(monkeypatch)
        assert emb._http.headers.get("x-goog-api-key") == KEY
        assert KEY not in emb._url

    async def test_el_texto_del_error_no_delata_la_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El sintoma exacto que se vio en los logs.

        `HTTPStatusError.__str__` imprime la URL. Si la key esta ahi, cada
        error de Google la publica — que es como se descubrio esto.
        """
        emb = _embedder(monkeypatch)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "lo que sea"})

        emb._http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers={"x-goog-api-key": KEY}
        )

        with pytest.raises(httpx.HTTPStatusError) as exc:
            await emb.embed_query("hola")
        assert KEY not in str(exc.value), "el error de httpx imprime la key"


class TestEl429SeReintenta:
    async def test_un_429_seguido_de_un_200_devuelve_el_vector(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verificado por reversion: sin reintento esto tira `HTTPStatusError`
        y el alumno recibe un 500 por un limite que ya se habia liberado."""
        emb = _embedder(monkeypatch)
        monkeypatch.setattr("content_service.embedding.embedder.asyncio.sleep", _no_dormir)
        llamadas = {"n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"}, json={})
            return httpx.Response(200, json=_respuesta_ok())

        emb._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        vec = await emb.embed_query("hola")

        assert len(vec) == 1024
        assert llamadas["n"] == 2, "no reintento"

    async def test_respeta_el_retry_after_de_google_por_sobre_el_backoff(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El que sabe cuando se libera la cuota es Google, no nuestro backoff."""
        emb = _embedder(monkeypatch)
        dormidas: list[float] = []

        async def espiar(segundos: float) -> None:
            dormidas.append(segundos)

        monkeypatch.setattr("content_service.embedding.embedder.asyncio.sleep", espiar)
        llamadas = {"n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "3"}, json={})
            return httpx.Response(200, json=_respuesta_ok())

        emb._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await emb.embed_query("hola")

        assert dormidas == [3.0], f"no uso el Retry-After: {dormidas}"

    async def test_un_retry_after_absurdo_queda_acotado(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Con la cuota DIARIA agotada Google manda minutos.

        Dormir eso adentro de un request deja al alumno mirando una pantalla
        colgada hasta que el proxy lo corte. Mejor fallar rapido.
        """
        emb = _embedder(monkeypatch)
        dormidas: list[float] = []

        async def espiar(segundos: float) -> None:
            dormidas.append(segundos)

        monkeypatch.setattr("content_service.embedding.embedder.asyncio.sleep", espiar)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "600"}, json={})

        emb._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(httpx.HTTPStatusError):
            await emb.embed_query("hola")

        assert max(dormidas) <= 8.0, f"durmio de mas: {dormidas}"

    async def test_se_rinde_y_propaga_si_el_429_no_afloja(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reintentar no es insistir para siempre."""
        emb = _embedder(monkeypatch)
        monkeypatch.setattr("content_service.embedding.embedder.asyncio.sleep", _no_dormir)
        llamadas = {"n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            llamadas["n"] += 1
            return httpx.Response(429, json={})

        emb._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with pytest.raises(httpx.HTTPStatusError):
            await emb.embed_query("hola")
        assert llamadas["n"] == 3, "el numero de intentos no es el declarado"

    async def test_el_ultimo_intento_no_duerme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dormir despues del ultimo reintento es espera que no compra nada."""
        emb = _embedder(monkeypatch)
        dormidas: list[float] = []

        async def espiar(segundos: float) -> None:
            dormidas.append(segundos)

        monkeypatch.setattr("content_service.embedding.embedder.asyncio.sleep", espiar)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={})

        emb._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(httpx.HTTPStatusError):
            await emb.embed_query("hola")

        assert len(dormidas) == 2, f"3 intentos tienen que dormir 2 veces: {dormidas}"

    async def test_un_400_NO_se_reintenta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un request mal armado no mejora reintentandolo: solo tarda mas en
        darnos la misma mala noticia."""
        emb = _embedder(monkeypatch)
        llamadas = {"n": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            llamadas["n"] += 1
            return httpx.Response(400, json={})

        emb._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(httpx.HTTPStatusError):
            await emb.embed_query("hola")

        assert llamadas["n"] == 1


class TestRetryAfter:
    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [
            ("5", 5.0),
            (" 2.5 ", 2.5),
            ("0", 0.0),
            (None, None),
            ("", None),
            ("-1", None),
            # Formato de fecha HTTP: el RFC lo permite y Google no lo manda,
            # pero un header raro no puede hacer estallar el reintento.
            ("Wed, 21 Oct 2026 07:28:00 GMT", None),
        ],
    )
    def test_parseo(self, valor: str | None, esperado: float | None) -> None:
        assert _retry_after_segundos(valor) == esperado
