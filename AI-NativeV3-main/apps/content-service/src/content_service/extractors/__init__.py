"""Extractores por formato."""

from content_service.extractors.base import (
    BaseExtractor,
    ExtractedSection,
    ExtractionResult,
    detect_format,
)
from content_service.extractors.code import CodeArchiveExtractor
from content_service.extractors.markdown import MarkdownExtractor
from content_service.extractors.pdf import PDFExtractor
from content_service.extractors.text import TextExtractor


def get_extractor(format_name: str) -> BaseExtractor:
    """Factory: devuelve el extractor correcto según formato detectado."""
    extractors: dict[str, BaseExtractor] = {
        "pdf": PDFExtractor(),
        "markdown": MarkdownExtractor(),
        "code_archive": CodeArchiveExtractor(),
        "text": TextExtractor(),
    }
    if format_name not in extractors:
        raise ValueError(f"Formato no soportado: {format_name}")
    return extractors[format_name]


__all__ = [
    "BaseExtractor",
    "CodeArchiveExtractor",
    "ExtractedSection",
    "ExtractionResult",
    "MarkdownExtractor",
    "PDFExtractor",
    "TextExtractor",
    "detect_format",
    "get_extractor",
]
