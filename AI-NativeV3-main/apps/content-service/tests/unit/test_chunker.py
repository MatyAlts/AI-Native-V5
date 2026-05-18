"""Tests del chunker estratificado."""

from __future__ import annotations

from content_service.extractors.base import ExtractedSection
from content_service.services.chunker import (
    CHARS_PER_TOKEN,
    MAX_CODE_TOKENS,
    chunk_sections,
)


def test_codigo_corto_es_un_chunk() -> None:
    """Una función chica cabe en un solo chunk."""
    sections = [
        ExtractedSection(
            content="def foo():\n    return 1",
            section_type="code_function",
            meta={"source_file": "x.py"},
        )
    ]
    chunks = chunk_sections(sections)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "code_function"
    assert chunks[0].position == 0


def test_codigo_muy_grande_se_subdivide() -> None:
    """Código que excede MAX_CODE_TOKENS se divide por bloques lógicos."""
    # Generar código extenso: 50 bloques separados por doble salto de línea
    huge = "\n\n".join([f"x_{i} = {i}" for i in range(500)])
    assert len(huge) > MAX_CODE_TOKENS * CHARS_PER_TOKEN

    sections = [
        ExtractedSection(
            content=huge,
            section_type="code_function",
            meta={"source_file": "big.py"},
        )
    ]
    chunks = chunk_sections(sections)
    assert len(chunks) > 1


def test_prosa_usa_ventana_deslizante() -> None:
    """Prosa larga se divide en ventanas con solapamiento."""
    # Generar un texto con varias oraciones
    sentences = [f"Esta es la oración número {i} del texto de prueba." for i in range(200)]
    long_text = " ".join(sentences)

    sections = [
        ExtractedSection(
            content=long_text,
            section_type="prose",
            meta={"source_file": "largo.md"},
        )
    ]
    chunks = chunk_sections(sections)
    assert len(chunks) > 1
    # Posiciones consecutivas
    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_tabla_es_un_unico_chunk() -> None:
    sections = [
        ExtractedSection(
            content="| a | b |\n| 1 | 2 |\n| 3 | 4 |",
            section_type="table",
            meta={"source_file": "datos.pdf", "page": 3},
        )
    ]
    chunks = chunk_sections(sections)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "table"


def test_hash_es_determinista() -> None:
    """Mismo contenido → mismo hash."""
    section = ExtractedSection(
        content="texto reproducible",
        section_type="prose",
        meta={},
    )
    chunks1 = chunk_sections([section])
    chunks2 = chunk_sections([section])
    assert chunks1[0].contenido_hash == chunks2[0].contenido_hash
    assert len(chunks1[0].contenido_hash) == 64  # SHA-256 hex


def test_posiciones_incrementales_entre_secciones() -> None:
    """Las posiciones son globales al documento, no por sección."""
    sections = [
        ExtractedSection(content="Primera sección.", section_type="prose", meta={}),
        ExtractedSection(content="Segunda sección.", section_type="prose", meta={}),
        ExtractedSection(
            content="def f():\n    pass",
            section_type="code_function",
            meta={},
        ),
    ]
    chunks = chunk_sections(sections)
    positions = [c.position for c in chunks]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)  # sin duplicados
