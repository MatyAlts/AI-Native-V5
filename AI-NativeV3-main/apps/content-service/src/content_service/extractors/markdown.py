"""Extractor de Markdown.

Divide el documento respetando la estructura de headings: cada sección
bajo un heading H1/H2/H3 es una sección independiente. Preserva el
"heading_path" completo para dar contexto al chunk posterior.
"""

from __future__ import annotations

import re

from content_service.extractors.base import (
    BaseExtractor,
    ExtractedSection,
    ExtractionResult,
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)$", re.MULTILINE)


class MarkdownExtractor(BaseExtractor):
    async def extract(self, content: bytes, filename: str) -> ExtractionResult:
        text = content.decode("utf-8", errors="replace")
        sections: list[ExtractedSection] = []

        # Estrategia: dividir por headings, cada bloque es una sección.
        # Acumular heading_path para trazabilidad.
        lines = text.split("\n")
        current_section: list[str] = []
        heading_stack: list[str] = []  # [h1_title, h2_title, h3_title, ...]
        current_heading: str | None = None
        position = 0

        def flush_section() -> None:
            nonlocal position
            if not current_section:
                return
            content_text = "\n".join(current_section).strip()
            if not content_text:
                return
            sections.append(
                ExtractedSection(
                    content=content_text,
                    section_type="heading" if current_heading else "prose",
                    meta={
                        "source_file": filename,
                        "heading": current_heading,
                        "heading_path": " > ".join(heading_stack),
                        "position": position,
                    },
                )
            )
            position += 1

        for line in lines:
            m = HEADING_RE.match(line)
            if m:
                # Al encontrar un heading, flushear la sección previa
                flush_section()
                current_section = []
                level = len(m.group(1))
                title = m.group(2).strip()
                # Ajustar stack
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                current_heading = title
                # El heading forma parte del contenido de la sección
                current_section.append(line)
            else:
                current_section.append(line)

        flush_section()

        return ExtractionResult(
            sections=sections,
            metadata={
                "format": "markdown",
                "total_sections": len(sections),
                "lines": len(lines),
            },
        )
