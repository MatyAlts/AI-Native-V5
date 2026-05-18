"""Tests del event_labeler_lexical (ADR-045, Mejora 3 / G8b del plan post-piloto-1).

Cubren el esqueleto tecnico:

1. Anotacion N1 ("estoy leyendo el enunciado") -> "N1".
2. Anotacion N4 ("ahora entiendo lo que el tutor explico") -> "N4".
3. Precedencia: contenido con marker N1 Y N4 -> gana N4.
4. Anotacion neutral sin markers -> None (fallback al override temporal v1.1.0).
5. Anotacion vacia -> None.
6. Determinismo bit-a-bit del corpus_hash (golden value).
7. Funcion pura: misma input -> mismo output.
8. Variantes con/sin tildes en mayusculas y minusculas.

Convenciones:
- Tests sin red, sin DB, sin Redis — `lexical_label` es funcion pura sobre string.
- Documentan que el modulo NO se invoca desde label_event() mientras el flag
  `lexical_anotacion_override_enabled=False` (default del config).
"""

from __future__ import annotations

import pytest

from classifier_service.services.event_labeler_lexical import (
    LEXICAL_CORPUS_HASH,
    LEXICAL_CORPUS_VERSION,
    compute_lexical_corpus_hash,
    lexical_label,
)


class TestLexicalLabel:
    def test_n1_estoy_leyendo(self) -> None:
        assert lexical_label("Estoy leyendo el enunciado del problema") == "N1"

    def test_n1_enunciado_pide(self) -> None:
        assert lexical_label("El enunciado pide calcular el factorial") == "N1"
        assert lexical_label("La consigna dice usar recursion") == "N1"

    def test_n1_no_entiendo_todavia(self) -> None:
        assert lexical_label("Todavia no me queda claro como hacerlo") == "N1"
        assert lexical_label("No entiendo todavia que hay que retornar") == "N1"

    def test_n1_me_piden(self) -> None:
        assert lexical_label("Me piden que calcule la suma") == "N1"
        assert lexical_label("Tengo que entender la consigna primero") == "N1"

    def test_n4_ahora_entiendo(self) -> None:
        assert lexical_label("Ahora entiendo lo que querias decir") == "N4"
        assert lexical_label("Ahora veo el patron") == "N4"
        assert lexical_label("Ahora me doy cuenta del bug") == "N4"

    def test_n4_tras_la_respuesta(self) -> None:
        assert lexical_label("Tras la respuesta del tutor pude resolverlo") == "N4"
        assert lexical_label("Despues de la respuesta lo arregle") == "N4"

    def test_n4_siguiendo_consejo(self) -> None:
        assert lexical_label("Siguiendo el consejo del tutor probe esto") == "N4"
        assert lexical_label("Siguiendo lo que me dijo lo intente") == "N4"

    def test_n4_el_tutor(self) -> None:
        assert lexical_label("El tutor me dijo que probara con un while") == "N4"
        assert lexical_label("El tutor sugirio usar recursion") == "N4"
        assert lexical_label("El tutor me ayudo a entender el problema") == "N4"

    def test_precedencia_n4_gana_sobre_n1(self) -> None:
        # Contenido con marker N1 Y N4 -> N4 por precedencia (mismo criterio
        # que el override temporal v1.1.0 cuando ambas ventanas matchean).
        content = "Estoy leyendo el enunciado y ahora entiendo lo que pide"
        assert lexical_label(content) == "N4"

    def test_anotacion_neutral_sin_markers_devuelve_none(self) -> None:
        assert lexical_label("voy a probar con un for loop") is None
        assert lexical_label("intentemos con array.length") is None

    def test_anotacion_vacia_devuelve_none(self) -> None:
        assert lexical_label("") is None

    def test_corpus_hash_determinista_bit_a_bit(self) -> None:
        h1 = compute_lexical_corpus_hash()
        h2 = compute_lexical_corpus_hash()
        assert h1 == h2
        assert h1 == LEXICAL_CORPUS_HASH
        assert len(h1) == 64
        assert all(c in "0123456789abcdef" for c in h1)

    def test_corpus_version_es_1_0_0(self) -> None:
        assert LEXICAL_CORPUS_VERSION == "1.0.0"

    def test_corpus_hash_golden(self) -> None:
        # Anti-regresion: cualquier cambio accidental en patterns cambia el hash.
        # Si rompe legitimamente (rebalanceo del corpus post-validacion intercoder),
        # bumpear LEXICAL_CORPUS_VERSION y actualizar este golden con el valor
        # recomputado.
        golden = "40db6b9047b3c8fee3665c95f5b86d6ea790afd558564349cb009c0f2ca3fe95"
        assert LEXICAL_CORPUS_HASH == golden, (
            f"Corpus hash drift detectado. LEXICAL_CORPUS_HASH={LEXICAL_CORPUS_HASH} "
            f"esperado golden={golden}. Si el cambio es legitimo, bumpear "
            f"LEXICAL_CORPUS_VERSION y actualizar este golden."
        )

    def test_lexical_label_es_idempotente(self) -> None:
        content = "Ahora entiendo siguiendo el consejo del tutor"
        r1 = lexical_label(content)
        r2 = lexical_label(content)
        assert r1 == r2 == "N4"

    def test_case_insensitive(self) -> None:
        assert lexical_label("AHORA ENTIENDO el problema") == "N4"
        assert lexical_label("estoy LEYENDO el enunciado") == "N1"


class TestFlagOff:
    """Garantia de ADR-027/ADR-045: con flag OFF, label_event sigue produciendo
    las mismas etiquetas que la heuristica temporal v1.1.0.

    Estos tests NO ejercitan label_event() con flag ON (eso requiere settings
    mock). Verifican el contrato del modulo lexical en si: si NO se invoca,
    no hay efecto secundario.
    """

    def test_modulo_es_puro_no_tiene_estado(self) -> None:
        # Multiples invocaciones no acumulan estado — la funcion es pura.
        for _ in range(5):
            assert lexical_label("Ahora entiendo todo") == "N4"
            assert lexical_label("Estoy leyendo el problema") == "N1"
            assert lexical_label("voy con un for") is None
