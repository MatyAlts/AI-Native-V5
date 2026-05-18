"""Extractor de archivos de texto plano simple."""

from __future__ import annotations

from content_service.extractors.base import (
    BaseExtractor,
    ExtractedSection,
    ExtractionResult,
)


class TextExtractor(BaseExtractor):
    async def extract(self, content: bytes, filename: str) -> ExtractionResult:
        text = content.decode("utf-8", errors="replace")
        # Dividir por párrafos (doble salto de línea)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        sections = [
            ExtractedSection(
                content=p,
                section_type="prose",
                meta={"source_file": filename, "position": i},
            )
            for i, p in enumerate(paragraphs)
        ]
        return ExtractionResult(
            sections=sections,
            metadata={"format": "text", "total_sections": len(sections)},
        )
