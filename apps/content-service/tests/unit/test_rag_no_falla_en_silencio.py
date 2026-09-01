"""Los dos modos en que el RAG fallaba SIN avisar (QA 2026-08-31).

Los dos salieron del mismo sintoma —`POST /api/v1/retrieve` devolviendo 500—
pero son problemas distintos, y el segundo es peor porque NO devuelve 500.

1. `EMBEDDER=local` SIN LA LIBRERIA
-----------------------------------
El import de `sentence_transformers` es perezoso (vive en `_ensure_model()`),
asi que el servicio arrancaba verde, pasaba el health check, y moria recien
cuando un alumno preguntaba algo. Y la libreria faltaba de verdad: es un extra
opcional (`local-models`) y el Dockerfile corre `uv sync --all-packages
--no-dev`, sin `--extra`.

Lo curioso: el camino por DEFAULT (sin `EMBEDDER` seteado) si chequeaba, y caia
a mock. El camino EXPLICITO no chequeaba nada. El descuidado era el que alguien
elige a proposito.

2. EL CORPUS INDEXADO CON OTRO EMBEDDER
---------------------------------------
Cambiar `EMBEDDER` de `local` a `gemini` no da error. Los dos producen vectores
de 1024 dims —Gemini rellena con ceros hasta llegar— asi que el `<=>` de
pgvector compara dos espacios que no tienen nada que ver y devuelve **200 OK
con resultados sin sentido**.

Eso es PEOR que el 500. El 500 se ve. Un retrieval silenciosamente malo se ve
como un tutor que contesta cualquier cosa, y eso se le atribuye al modelo, no a
la configuracion.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import pytest
from content_service.embedding.embedder import (
    GeminiEmbedder,
    MockEmbedder,
    _exigir_sentence_transformers,
    get_embedder,
)
from content_service.schemas import RetrievalRequest
from content_service.services.retrieval import RetrievalService


class TestEmbedderLocalSinLaLibreria:
    def test_falla_al_arrancar_y_no_en_la_primera_consulta(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El corazon del fix.

        Verificado por reversion: sin `_exigir_sentence_transformers()`,
        `get_embedder()` devuelve un `SentenceTransformerEmbedder` feliz y el
        fallo se muda a la primera pregunta de un alumno.
        """
        monkeypatch.setattr("importlib.util.find_spec", lambda nombre: None)
        monkeypatch.setenv("EMBEDDER", "local")
        get_embedder.cache_clear()

        with pytest.raises(RuntimeError) as exc:
            get_embedder()

        get_embedder.cache_clear()
        assert "local-models" in str(exc.value), "el error no dice como arreglarlo"

    def test_el_mensaje_nombra_lo_que_falta_y_la_salida(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un error de despliegue tiene que ser accionable sin leer el codigo."""
        monkeypatch.setattr("importlib.util.find_spec", lambda nombre: None)

        with pytest.raises(RuntimeError) as exc:
            _exigir_sentence_transformers()

        texto = str(exc.value)
        assert "sentence_transformers" in texto
        assert "uv sync --extra local-models" in texto
        assert "EMBEDDER=gemini" in texto

    def test_con_la_libreria_presente_no_molesta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """El chequeo no puede romper el caso en que todo esta bien."""
        monkeypatch.setattr("importlib.util.find_spec", lambda nombre: object())

        _exigir_sentence_transformers()  # no tira

    def test_gemini_no_pasa_por_el_chequeo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`EMBEDDER=gemini` no necesita sentence-transformers para nada."""
        monkeypatch.setattr("importlib.util.find_spec", lambda nombre: None)
        monkeypatch.setenv("EMBEDDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaFalsa")
        get_embedder.cache_clear()

        emb = get_embedder()
        get_embedder.cache_clear()

        assert isinstance(emb, GeminiEmbedder)


class _ResultadoFalso:
    """Lo minimo que `retrieve` le pide a un resultado de SQLAlchemy."""

    def __init__(self, filas: list[Any], primera: Any = None) -> None:
        self._filas = filas
        self._primera = primera

    def mappings(self) -> _ResultadoFalso:
        return self

    def all(self) -> list[Any]:
        return self._filas

    def first(self) -> Any:
        return self._primera


class _SesionFalsa:
    """Registra lo que se ejecuto de verdad, con su SQL y sus parametros.

    No simula Postgres: simula el CONTRATO. Alcanza para preguntar "¿la consulta
    que salio lleva el filtro y el modelo?" — que es la propiedad — sin depender
    de `CONTENT_DB_URL`, que hoy no existe en CI.
    """

    def __init__(self, *, otro_embedder: tuple[str, int] | None = None) -> None:
        self.ejecutadas: list[tuple[str, dict[str, Any]]] = []
        self._otro = otro_embedder

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _ResultadoFalso:
        sql = str(stmt)
        self.ejecutadas.append((sql, dict(params or {})))
        if "GROUP BY c.embedding_model" in sql:
            return _ResultadoFalso([], primera=self._otro)
        return _ResultadoFalso([])


class TestElCorpusDeOtroEspacio:
    """Que el filtro por embedder este puesto Y que se ejecute.

    ESTE ARCHIVO YA TUVO LA ENFERMEDAD QUE VIENE A CURAR
    ----------------------------------------------------
    La version anterior de esta clase leia `retrieval.py` como TEXTO con
    `Path(...).read_text()` y buscaba substrings. Era un `grep` disfrazado de
    test, y una auditoria adversarial del PR #86 lo probo: desconectando la
    llamada real a `_avisar_si_hay_corpus_de_otro_embedder` dentro de
    `retrieve()` —dejando el metodo intacto, solo sin invocarlo— los tres tests
    seguian en VERDE.

    O sea: el test de "la mitigacion existe" no distinguia una mitigacion viva
    de una muerta. Que es EXACTAMENTE el defecto que este PR arregla seis veces
    —el endpoint que sabe des-marcar y nadie llama, el boton que cambia un
    estado y nada mas, el `||` que descartaba el buffer—. El patron se colo en
    los tests escritos para arreglarlo.

    Estos ejercitan `RetrievalService.retrieve()` contra una sesion que registra
    lo que salio. Si alguien desconecta el aviso, se ponen rojos.
    """

    @pytest.fixture(autouse=True)
    def _embedder_de_test(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMBEDDER", "mock")
        monkeypatch.setenv("RERANKER", "identity")
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_embedder.cache_clear()

    def _pedido(self) -> RetrievalRequest:
        return RetrievalRequest(query="que es un bucle", materia_id=uuid.uuid4())

    async def test_la_consulta_que_SALE_filtra_por_el_modelo_que_consulta(self) -> None:
        """No que el filtro este escrito: que la consulta ejecutada lo lleve,
        con el modelo del embedder vigente atado como parametro."""
        sesion = _SesionFalsa()

        await RetrievalService(sesion).retrieve(self._pedido())  # type: ignore[arg-type]

        sql, params = sesion.ejecutadas[0]
        assert "c.embedding_model IS NULL OR c.embedding_model = :modelo" in sql
        assert params["modelo"] == MockEmbedder.model_name

    async def test_los_chunks_sin_embedding_model_SI_entran(self) -> None:
        """Son de antes de que existiera la columna. Excluirlos romperia
        corpus historicos por una sospecha que no podemos confirmar."""
        sesion = _SesionFalsa()

        await RetrievalService(sesion).retrieve(self._pedido())  # type: ignore[arg-type]

        sql, _ = sesion.ejecutadas[0]
        assert "c.embedding_model IS NULL OR" in sql

    async def test_avisa_fuerte_cuando_encuentra_corpus_de_otro_embedder(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """El caso que el test viejo daba por bueno sin ejercitarlo.

        El filtro convierte el fallo en "no hay material", que es legible. Este
        log es la explicacion de POR QUE no lo hay — sin el, la causa real (la
        config del embedder) queda invisible.
        """
        sesion = _SesionFalsa(otro_embedder=("intfloat/multilingual-e5-large", 412))

        with caplog.at_level(logging.ERROR):
            await RetrievalService(sesion).retrieve(self._pedido())  # type: ignore[arg-type]

        assert "rag_corpus_de_otro_embedder" in caplog.text
        assert "intfloat/multilingual-e5-large" in caplog.text
        assert "412" in caplog.text

    async def test_con_el_corpus_sano_NO_grita(self, caplog: pytest.LogCaptureFixture) -> None:
        """La contracara: un aviso que suena siempre no lo lee nadie."""
        sesion = _SesionFalsa(otro_embedder=None)

        with caplog.at_level(logging.ERROR):
            await RetrievalService(sesion).retrieve(self._pedido())  # type: ignore[arg-type]

        assert "rag_corpus_de_otro_embedder" not in caplog.text


class TestElMockSigueSiendoDetectable:
    def test_el_mock_no_es_semantico(self) -> None:
        """Regresion posible de estos cambios: si el mock pasara como
        semantico, el guard de BUG-4 dejaria de abortar en produccion y se
        indexaria con vectores de hash creyendo que son reales."""
        assert MockEmbedder.is_semantic is False
