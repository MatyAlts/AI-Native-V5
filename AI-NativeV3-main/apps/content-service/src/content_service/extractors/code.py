"""Extractor de archivos de código.

Para un ZIP con código fuente, extrae cada archivo soportado y divide
por funciones/clases detectadas heurísticamente (prefijo de regex para
lenguajes populares; en F3+ se puede migrar a tree-sitter para parseo
sintáctico real).

Para F2, el approach de regex es suficiente — la mayoría de
materiales de cátedra son archivos Python cortos con funciones bien
delimitadas.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePath

from content_service.extractors.base import (
    BaseExtractor,
    ExtractedSection,
    ExtractionResult,
)

LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
}

# Heurísticas de delimitación de funciones/clases por lenguaje.
# Simple, no perfecto — suficiente para la mayoría de archivos docentes.
FUNCTION_START_PATTERNS: dict[str, re.Pattern] = {
    "python": re.compile(r"^(def |class |async def )", re.MULTILINE),
    "javascript": re.compile(
        r"^(function |class |export |const \w+ = (?:async )?\()", re.MULTILINE
    ),
    "typescript": re.compile(
        r"^(function |class |export |const \w+ = (?:async )?\()", re.MULTILINE
    ),
    "java": re.compile(r"^\s*(public|private|protected|class |interface )", re.MULTILINE),
    "go": re.compile(r"^(func |type )", re.MULTILINE),
    "rust": re.compile(r"^(fn |pub fn |struct |impl |trait )", re.MULTILINE),
}


class CodeArchiveExtractor(BaseExtractor):
    async def extract(self, content: bytes, filename: str) -> ExtractionResult:
        sections: list[ExtractedSection] = []
        file_count = 0

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for entry in zf.namelist():
                # Ignorar entradas basura
                if entry.endswith("/") or "__MACOSX" in entry or entry.startswith("."):
                    continue
                ext = PurePath(entry).suffix.lower()
                lang = LANG_BY_EXT.get(ext)
                if not lang:
                    continue

                try:
                    raw = zf.read(entry)
                    code = raw.decode("utf-8", errors="replace")
                except Exception:
                    continue

                file_count += 1
                file_sections = self._split_code_file(code, entry, lang)
                sections.extend(file_sections)

        return ExtractionResult(
            sections=sections,
            metadata={
                "format": "code_archive",
                "total_sections": len(sections),
                "total_files": file_count,
                "archive_name": filename,
            },
        )

    def _split_code_file(self, code: str, filepath: str, lang: str) -> list[ExtractedSection]:
        """Divide un archivo en secciones por función/clase si se puede."""
        pattern = FUNCTION_START_PATTERNS.get(lang)
        if pattern is None:
            # Sin pattern conocido: un solo chunk con todo el archivo
            return [
                ExtractedSection(
                    content=code,
                    section_type="code_file",
                    meta={
                        "source_file": filepath,
                        "lang": lang,
                        "position": 0,
                    },
                )
            ]

        # Encontrar boundaries de definiciones
        matches = list(pattern.finditer(code))
        if not matches:
            # No hay funciones/clases detectadas: todo el archivo como uno
            return [
                ExtractedSection(
                    content=code,
                    section_type="code_file",
                    meta={
                        "source_file": filepath,
                        "lang": lang,
                        "position": 0,
                    },
                )
            ]

        sections: list[ExtractedSection] = []

        # Header (imports, constantes) antes de la primera definición
        if matches[0].start() > 0:
            header = code[: matches[0].start()].strip()
            if header:
                sections.append(
                    ExtractedSection(
                        content=header,
                        section_type="code_header",
                        meta={
                            "source_file": filepath,
                            "lang": lang,
                            "position": 0,
                            "start_line": 1,
                        },
                    )
                )

        # Cada definición es una sección
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(code)
            chunk = code[start:end].strip()
            if not chunk:
                continue
            # Extraer nombre de la definición de la primera línea
            first_line = chunk.split("\n", 1)[0]
            start_line = code[:start].count("\n") + 1
            sections.append(
                ExtractedSection(
                    content=chunk,
                    section_type="code_function",
                    meta={
                        "source_file": filepath,
                        "lang": lang,
                        "position": i + 1,
                        "start_line": start_line,
                        "definition_line": first_line,
                    },
                )
            )

        return sections
