"""Extractor de PDF.

En producción usa unstructured.io con strategy=auto (detecta si el PDF
es escaneado y aplica OCR con tesseract automáticamente).

Para el entorno de tests o entornos sin unstructured (que es una
dependencia pesada), incluimos un fallback con pypdf que extrae texto
plano página por página.
"""

from __future__ import annotations

import io

from content_service.extractors.base import (
    BaseExtractor,
    ExtractedSection,
    ExtractionResult,
)


class PDFExtractor(BaseExtractor):
    """Extractor de PDF con fallback si unstructured no está disponible."""

    async def extract(self, content: bytes, filename: str) -> ExtractionResult:
        # Preferir unstructured si está disponible (mejor detección de tablas,
        # listas, OCR automático para escaneados)
        try:
            from unstructured.partition.pdf import partition_pdf

            return await self._extract_with_unstructured(content, filename, partition_pdf)
        except ImportError:
            return await self._extract_with_pypdf(content, filename)

    async def _extract_with_unstructured(
        self, content: bytes, filename: str, partition_pdf
    ) -> ExtractionResult:
        with io.BytesIO(content) as buf:
            elements = partition_pdf(
                file=buf,
                strategy="auto",
                infer_table_structure=True,
                extract_images_in_pdf=False,
            )

        sections: list[ExtractedSection] = []
        for i, el in enumerate(elements):
            text = str(el).strip()
            if not text:
                continue
            category = el.category.lower() if hasattr(el, "category") else "prose"
            page = getattr(el.metadata, "page_number", None) if hasattr(el, "metadata") else None
            sections.append(
                ExtractedSection(
                    content=text,
                    section_type=_map_section_type(category),
                    meta={
                        "source_file": filename,
                        "page": page,
                        "position": i,
                    },
                )
            )

        return ExtractionResult(
            sections=sections,
            metadata={
                "format": "pdf",
                "total_sections": len(sections),
                "extractor": "unstructured",
            },
        )

    async def _extract_with_pypdf(self, content: bytes, filename: str) -> ExtractionResult:
        """Fallback: extracción simple por página."""
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError(
                "Ni 'unstructured' ni 'pypdf' disponibles. "
                "Instalar uno: pip install unstructured[pdf] o pip install pypdf"
            ) from e

        reader = PdfReader(io.BytesIO(content))
        sections: list[ExtractedSection] = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            # Dividir cada página en párrafos
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for p_idx, para in enumerate(paragraphs):
                sections.append(
                    ExtractedSection(
                        content=para,
                        section_type="prose",
                        meta={
                            "source_file": filename,
                            "page": page_num,
                            "position": len(sections),
                            "paragraph_in_page": p_idx,
                        },
                    )
                )

        return ExtractionResult(
            sections=sections,
            metadata={
                "format": "pdf",
                "total_pages": len(reader.pages),
                "total_sections": len(sections),
                "extractor": "pypdf",
            },
        )


def _map_section_type(category: str) -> str:
    """Mapea la categoría de unstructured a nuestra taxonomía."""
    mapping = {
        "title": "heading",
        "narrativetext": "prose",
        "listitem": "prose",
        "table": "table",
        "formula": "prose",
    }
    return mapping.get(category, "prose")
