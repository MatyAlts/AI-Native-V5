"""Tests del extractor de archivos de código."""

from __future__ import annotations

import io
import zipfile

import pytest
from content_service.extractors.code import CodeArchiveExtractor


@pytest.fixture
def extractor() -> CodeArchiveExtractor:
    return CodeArchiveExtractor()


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


async def test_extrae_funciones_python(extractor: CodeArchiveExtractor) -> None:
    py_code = '''"""Módulo de ejemplo."""
import math


def area_circulo(r: float) -> float:
    """Calcula el área de un círculo."""
    return math.pi * r ** 2


def perimetro_circulo(r: float) -> float:
    return 2 * math.pi * r


class Circulo:
    def __init__(self, r: float):
        self.r = r
'''
    zip_bytes = _make_zip({"geometria.py": py_code})

    result = await extractor.extract(zip_bytes, "ejercicios.zip")

    # Esperamos: header (imports) + 2 funciones + 1 clase = 4 secciones
    assert len(result.sections) == 4
    types = [s.section_type for s in result.sections]
    assert "code_header" in types
    assert types.count("code_function") == 3  # 2 funciones top-level + clase


async def test_detecta_lenguaje_por_extension(extractor: CodeArchiveExtractor) -> None:
    zip_bytes = _make_zip(
        {
            "main.py": "def foo():\n    return 1\n",
            "app.js": "function bar() { return 2; }\n",
            "Cli.java": "public class Cli { }\n",
        }
    )

    result = await extractor.extract(zip_bytes, "multi.zip")

    langs = {s.meta.get("lang") for s in result.sections}
    assert "python" in langs
    assert "javascript" in langs
    assert "java" in langs


async def test_ignora_archivos_no_codigo(extractor: CodeArchiveExtractor) -> None:
    zip_bytes = _make_zip(
        {
            "README.md": "# no soy codigo\n",
            "main.py": "def run():\n    pass\n",
            ".gitignore": "*.pyc\n",
        }
    )

    result = await extractor.extract(zip_bytes, "proj.zip")

    # Solo main.py debe estar
    source_files = {s.meta.get("source_file") for s in result.sections}
    assert "main.py" in source_files
    assert "README.md" not in source_files
    assert ".gitignore" not in source_files


async def test_archivo_sin_funciones_detectadas(extractor: CodeArchiveExtractor) -> None:
    """Código plano sin def/class se mantiene como un único chunk."""
    script = """# Script de configuración
PORT = 8080
DEBUG = True

print("Hola mundo")
"""
    zip_bytes = _make_zip({"config.py": script})

    result = await extractor.extract(zip_bytes, "c.zip")

    # No hay def/class → un solo code_file
    assert len(result.sections) == 1
    assert result.sections[0].section_type == "code_file"
