"""sha256 canónico de una versión del codebook (tarea 5.1, design D8).

El literal se calculó FUERA de la implementación: la serialización canónica de
D8 escrita a mano (claves ordenadas, sin espacios, sin escapar no-ASCII,
anclas ordenadas por `(uso, orden, episode_id)` con exactamente sus 8 campos)
pasada por `sha256sum`. Si este test falla, el sha de los codebooks congelados
dejó de ser reproducible: no se "actualiza el literal" sin decidirlo.
"""

from __future__ import annotations

import copy
from uuid import UUID

from classifier_service.services.estudio_codebook import sha256_codebook

SHA_LITERAL = "51c3389612d2e87b72a2bab32177a2d3b23d2ec53dcb1b096b5fd7ced75e775f"

CONTENIDO = "# Codebook de prueba\nPáramo ñandú"
ESQUEMA = {
    "dimensiones": [
        {"clave": "d1", "nombre": "D1", "valores": ["si", "no"], "cita_requerida_si": ["si"]}
    ],
    "regimenes": [{"clave": "a", "nombre": "A"}, {"clave": "ei", "nombre": "EI"}],
    "regimen_evidencia_insuficiente": "ei",
}


def anclas_de_prueba() -> list[dict]:
    """Con campos de más (`item_id`, `codebook_version_id`, `estado_carga`...)
    que el sha NO cubre, y desordenadas respecto del orden canónico."""
    return [
        {
            "item_id": UUID("11111111-1111-4111-8111-111111111111"),
            "codebook_version_id": UUID("22222222-2222-4222-8222-222222222222"),
            "uso": "practica",
            "orden": 1,
            "episode_id": UUID("00000000-0000-4000-8000-000000000002"),
            "respuesta_esperada": {"regimen": "ei", "respuestas": {}},
            "explicacion_md": "Porque sí",
            "consensuado_por": "C1 y C2",
            "seq_tope": 5,
            "chain_hash_tope": "a" * 64,
            "estado_carga": "closed",
        },
        {
            "item_id": UUID("33333333-3333-4333-8333-333333333333"),
            "codebook_version_id": UUID("22222222-2222-4222-8222-222222222222"),
            "uso": "ejemplo",
            "orden": 2,
            "episode_id": UUID("00000000-0000-4000-8000-000000000001"),
            "respuesta_esperada": {
                "respuestas": {"d1": {"valor": "si", "cita": "turno 2"}},
                "regimen": "a",
            },
            "explicacion_md": "Ejemplo claro",
            "consensuado_por": "C1 y C2",
            "seq_tope": 3,
            "chain_hash_tope": "b" * 64,
            "estado_carga": "paused",
        },
    ]


def test_sha_fijo_de_un_contenido_con_anclas() -> None:
    assert sha256_codebook(CONTENIDO, ESQUEMA, anclas_de_prueba()) == SHA_LITERAL


def test_el_orden_de_entrada_de_las_anclas_no_cambia_el_sha() -> None:
    assert sha256_codebook(CONTENIDO, ESQUEMA, list(reversed(anclas_de_prueba()))) == SHA_LITERAL


def test_ids_internos_de_las_anclas_no_entran_al_sha() -> None:
    anclas = anclas_de_prueba()
    for ancla in anclas:
        ancla["item_id"] = UUID("99999999-9999-4999-8999-999999999999")
        ancla["estado_carga"] = "otro"
    assert sha256_codebook(CONTENIDO, ESQUEMA, anclas) == SHA_LITERAL


def test_cambiar_una_explicacion_de_ancla_cambia_el_sha() -> None:
    original = sha256_codebook(CONTENIDO, ESQUEMA, anclas_de_prueba())
    anclas = anclas_de_prueba()
    anclas[0]["explicacion_md"] = "Porque no"
    assert sha256_codebook(CONTENIDO, ESQUEMA, anclas) != original


def test_sin_anclas_el_sha_es_otro() -> None:
    sin_anclas = "11d0d2cd342bbca9eab0ae173f052536d34b0ff58b01216a0e5da6fa8c99b94b"
    assert sha256_codebook(CONTENIDO, ESQUEMA, []) == sin_anclas


def test_no_modifica_las_anclas_recibidas() -> None:
    anclas = anclas_de_prueba()
    copia = copy.deepcopy(anclas)
    sha256_codebook(CONTENIDO, ESQUEMA, anclas)
    assert anclas == copia
