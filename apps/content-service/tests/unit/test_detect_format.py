"""Tests del detector de formato."""

from __future__ import annotations

from content_service.extractors.base import detect_format


def test_detecta_pdf_por_magic_bytes() -> None:
    pdf_bytes = b"%PDF-1.4\nfake content"
    assert detect_format("documento.pdf", pdf_bytes) == "pdf"
    # También funciona aun si la extensión está mal
    assert detect_format("docum.xyz", pdf_bytes) == "pdf"


def test_detecta_markdown_por_extension() -> None:
    assert detect_format("notas.md", b"# Hola\n") == "markdown"
    assert detect_format("guia.markdown", b"# Hola\n") == "markdown"


def test_detecta_zip_de_codigo() -> None:
    # Magic bytes de ZIP + extensión
    zip_bytes = b"PK\x03\x04\x0a\x00\x00\x00fake_zip"
    assert detect_format("proyecto.zip", zip_bytes) == "code_archive"


def test_detecta_texto_plano() -> None:
    assert detect_format("apuntes.txt", b"hola") == "text"


def test_formato_desconocido() -> None:
    assert detect_format("imagen.jpg", b"fake") == "unknown"
    assert detect_format("sin_extension", b"random bytes") == "unknown"
