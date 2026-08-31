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

import pytest
from content_service.embedding.embedder import (
    GeminiEmbedder,
    MockEmbedder,
    _exigir_sentence_transformers,
    get_embedder,
)


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


class TestElCorpusDeOtroEspacio:
    """La consulta SQL tiene que excluir los chunks de otro embedder.

    Es un test sobre el texto del SQL y no sobre una base real: los tests de
    integracion contra Postgres necesitan `CONTENT_DB_URL` y hoy no corren en
    CI. La leccion de agosto en este repo es que un test que no corre no prueba
    nada — asi que la propiedad se fija tambien acá, donde corre siempre.
    """

    def _fuente(self) -> str:
        from pathlib import Path

        import content_service.services.retrieval as mod

        return Path(mod.__file__).read_text(encoding="utf-8")

    def test_el_where_filtra_por_embedding_model(self) -> None:
        """Verificado por reversion: sin esta linea, pgvector ordena por una
        distancia entre dos espacios distintos y devuelve 200 con basura."""
        assert "c.embedding_model IS NULL OR c.embedding_model = :modelo" in self._fuente()

    def test_los_chunks_sin_embedding_model_SI_entran(self) -> None:
        """Son de antes de que existiera la columna. Excluirlos romperia
        corpus historicos por una sospecha que no podemos confirmar."""
        assert "c.embedding_model IS NULL OR" in self._fuente()

    def test_avisa_fuerte_cuando_encuentra_corpus_de_otro_embedder(self) -> None:
        """El filtro convierte el fallo en "no hay material", que es legible.
        Este log es la explicacion de por que no lo hay — sin el, la causa
        real (la config del embedder) queda invisible."""
        fuente = self._fuente()
        assert "rag_corpus_de_otro_embedder" in fuente
        assert "logger.error" in fuente


class TestElMockSigueSiendoDetectable:
    def test_el_mock_no_es_semantico(self) -> None:
        """Regresion posible de estos cambios: si el mock pasara como
        semantico, el guard de BUG-4 dejaria de abortar en produccion y se
        indexaria con vectores de hash creyendo que son reales."""
        assert MockEmbedder.is_semantic is False
