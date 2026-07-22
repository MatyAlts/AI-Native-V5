"""Chunker estratificado.

Convierte `ExtractedSection`s en chunks finales listos para embedding.
La estrategia varía por tipo de sección:

- `code_function` / `code_class`: 1 sección = 1 chunk (si cabe en el budget
   de tokens). Código muy largo se divide por bloques lógicos.
- `prose`, `heading`: chunking por ventana con solapamiento de 50 tokens.
  El solapamiento evita perder conceptos que atraviesan el límite de un chunk.
- `table`: 1 chunk por tabla (aunque sea larga), porque la tabla es la
  unidad semántica mínima.
- `video_segment`: 1 chunk por segmento transcrito.

Aproximación de tokens: ~1 token cada 4 caracteres en español. Para el
MVP esto es suficiente; refinar con tiktoken en F3 si hace falta.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from content_service.extractors import ExtractedSection

# Configuración por tipo de sección
DEFAULT_TARGET_TOKENS = 512
DEFAULT_OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 4  # aproximación

MAX_CODE_TOKENS = 1500  # funciones grandes como único chunk hasta este límite


@dataclass
class FinalChunk:
    """Chunk listo para embedding y persistencia."""

    contenido: str
    contenido_hash: str
    position: int
    chunk_type: str
    meta: dict[str, Any]


def chunk_sections(
    sections: list[ExtractedSection],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[FinalChunk]:
    """Convierte secciones extraídas en chunks finales uniformes."""
    chunks: list[FinalChunk] = []
    pos = 0

    for section in sections:
        if section.section_type in ("code_function", "code_class", "code_header", "code_file"):
            chunks.extend(_chunk_code(section, pos))
        elif section.section_type == "table":
            chunks.append(_as_single_chunk(section, pos, "table"))
        else:
            chunks.extend(_chunk_prose(section, target_tokens, overlap_tokens, pos))

        pos = len(chunks)

    return chunks


def _chunk_code(section: ExtractedSection, start_pos: int) -> list[FinalChunk]:
    """Código: 1 chunk por unidad salvo que sea demasiado grande."""
    char_limit = MAX_CODE_TOKENS * CHARS_PER_TOKEN
    if len(section.content) <= char_limit:
        return [_as_single_chunk(section, start_pos, section.section_type)]

    # Función muy grande: dividir por bloques lógicos (doble salto de línea)
    blocks = section.content.split("\n\n")
    chunks: list[FinalChunk] = []
    current: list[str] = []
    current_len = 0
    pos = start_pos

    for block in blocks:
        bl = len(block)
        if current and current_len + bl > char_limit:
            text = "\n\n".join(current)
            chunks.append(
                FinalChunk(
                    contenido=text,
                    contenido_hash=_hash_text(text),
                    position=pos,
                    chunk_type=section.section_type,
                    meta={**section.meta, "subpart": len(chunks)},
                )
            )
            pos += 1
            current = []
            current_len = 0
        current.append(block)
        current_len += bl + 2

    if current:
        text = "\n\n".join(current)
        chunks.append(
            FinalChunk(
                contenido=text,
                contenido_hash=_hash_text(text),
                position=pos,
                chunk_type=section.section_type,
                meta={**section.meta, "subpart": len(chunks)},
            )
        )

    return chunks


def _chunk_prose(
    section: ExtractedSection,
    target_tokens: int,
    overlap_tokens: int,
    start_pos: int,
) -> list[FinalChunk]:
    """Prosa: ventana deslizante respetando límite de párrafos/oraciones."""
    target_chars = target_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    # Si la sección cabe en un chunk, no la dividimos
    if len(section.content) <= target_chars:
        return [_as_single_chunk(section, start_pos, section.section_type)]

    # Dividir en oraciones heurísticamente
    sentences = _split_sentences(section.content)
    chunks: list[FinalChunk] = []
    current: list[str] = []
    current_len = 0
    pos = start_pos

    for sentence in sentences:
        slen = len(sentence)
        if current and current_len + slen > target_chars:
            text = " ".join(current).strip()
            chunks.append(
                FinalChunk(
                    contenido=text,
                    contenido_hash=_hash_text(text),
                    position=pos,
                    chunk_type=section.section_type,
                    meta={**section.meta, "window": len(chunks)},
                )
            )
            pos += 1
            # Solapamiento: conservar las últimas oraciones que acumulen
            # ~overlap_chars caracteres
            if overlap_chars > 0:
                overlap: list[str] = []
                overlap_len = 0
                for s in reversed(current):
                    if overlap_len + len(s) > overlap_chars:
                        break
                    overlap.insert(0, s)
                    overlap_len += len(s) + 1
                current = overlap
                current_len = sum(len(s) + 1 for s in current)
            else:
                current = []
                current_len = 0
        current.append(sentence)
        current_len += slen + 1

    if current:
        text = " ".join(current).strip()
        chunks.append(
            FinalChunk(
                contenido=text,
                contenido_hash=_hash_text(text),
                position=pos,
                chunk_type=section.section_type,
                meta={**section.meta, "window": len(chunks)},
            )
        )

    return chunks


def _as_single_chunk(section: ExtractedSection, position: int, chunk_type: str) -> FinalChunk:
    return FinalChunk(
        contenido=section.content,
        contenido_hash=_hash_text(section.content),
        position=position,
        chunk_type=chunk_type,
        meta=dict(section.meta),
    )


def _split_sentences(text: str) -> list[str]:
    """División heurística de oraciones por puntuación."""
    import re

    # Simple: split por puntos/exclamaciones/preguntas seguidos de espacio+mayúscula
    # Para producción en F3+ usar spaCy o similar.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])", text)
    return [p.strip() for p in parts if p.strip()]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
