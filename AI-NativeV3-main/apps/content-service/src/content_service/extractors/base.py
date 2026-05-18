"""Extractores que convierten un archivo de entrada en secciones semánticas.

Cada formato tiene un extractor con la misma interfaz. El pipeline de
ingesta elige el extractor por magic bytes + extensión del archivo.

Los extractores NO hacen chunking final — solo extraen secciones
semánticas. El chunking se hace después con estrategia uniforme.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedSection:
    """Sección semántica extraída del material fuente.

    Una sección es la unidad "natural" del documento: un párrafo, una
    función de código, un segmento de video, una celda de tabla.
    """

    content: str
    section_type: str  # "prose" | "heading" | "code_function" | ...
    meta: dict[str, Any] = field(default_factory=dict)
    # {page, start_line, end_line, heading_level, source_file, timestamp_seconds}


@dataclass
class ExtractionResult:
    sections: list[ExtractedSection]
    metadata: dict[str, Any] = field(default_factory=dict)
    # Metadata del material completo: total_pages, language, etc.


class BaseExtractor(ABC):
    """Interfaz común de todos los extractores."""

    @abstractmethod
    async def extract(self, content: bytes, filename: str) -> ExtractionResult:
        """Extrae secciones semánticas del archivo binario."""
        raise NotImplementedError


def detect_format(filename: str, content: bytes) -> str:
    """Detecta el formato por magic bytes + extensión.

    Returns:
        "pdf" | "markdown" | "code_archive" | "text" | "unknown"
    """
    name = filename.lower()

    # Magic bytes primero (más confiable)
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"PK\x03\x04") and name.endswith((".zip",)):
        return "code_archive"

    # Por extensión
    if name.endswith((".md", ".markdown")):
        return "markdown"
    if name.endswith((".txt",)):
        return "text"

    return "unknown"
