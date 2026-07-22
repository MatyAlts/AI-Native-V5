"""Tests del extractor de Markdown."""

from __future__ import annotations

import pytest
from content_service.extractors.markdown import MarkdownExtractor


@pytest.fixture
def extractor() -> MarkdownExtractor:
    return MarkdownExtractor()


async def test_extrae_secciones_por_headings(extractor: MarkdownExtractor) -> None:
    md = """# Introducción a Python

Python es un lenguaje interpretado.

## Variables

Las variables guardan valores.

## Funciones

Las funciones se definen con `def`.
""".encode()

    result = await extractor.extract(md, "intro.md")

    assert len(result.sections) == 3
    assert "Introducción a Python" in result.sections[0].content
    assert "Variables" in result.sections[1].content
    assert "Funciones" in result.sections[2].content


async def test_acumula_heading_path(extractor: MarkdownExtractor) -> None:
    """El heading_path refleja la jerarquía."""
    md = """# Capítulo 1

## Sección A

Texto A.

## Sección B

Texto B.

# Capítulo 2

Texto del capítulo 2.
""".encode()

    result = await extractor.extract(md, "libro.md")

    paths = [s.meta["heading_path"] for s in result.sections]
    # Capítulo 1, Capítulo 1 > Sección A, Capítulo 1 > Sección B, Capítulo 2
    assert "Capítulo 1" in paths[0]
    assert "Capítulo 1 > Sección A" in paths[1]
    assert "Capítulo 1 > Sección B" in paths[2]
    assert paths[3] == "Capítulo 2"


async def test_maneja_documento_sin_headings(extractor: MarkdownExtractor) -> None:
    md = b"Esto es solo prosa sin ningun heading.\n\nOtro parrafo."
    result = await extractor.extract(md, "plano.md")
    assert len(result.sections) == 1  # todo colapsa en una sección prose
    assert result.sections[0].section_type == "prose"


async def test_preserva_utf8(extractor: MarkdownExtractor) -> None:
    md = "# Título con acentos\n\nMatemática: ∀x ∃y P(x,y).".encode()
    result = await extractor.extract(md, "ut8.md")
    assert "∀x" in result.sections[0].content
    assert "Matemática" in result.sections[0].content
