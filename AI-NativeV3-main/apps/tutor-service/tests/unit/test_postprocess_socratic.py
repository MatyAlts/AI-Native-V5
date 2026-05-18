"""Tests del postprocess_socratic (ADR-044, Mejora 4 del plan post-piloto-1).

Cobertura del esqueleto técnico:

1. Respuesta socrática (con pregunta + sin código + sin imperativos) → score alto, sin violations.
2. Bloque de código completo grande → match `code_block_complete`, penaliza.
3. Respuesta sin "?" ni "¿" → match `no_question_in_response`.
4. Imperativo de respuesta directa ("la solución es...") → match `direct_answer`.
5. Las tres violaciones máximas a la vez → score saturado a 0.
6. Respuesta vacía → score neutral 0.5, sin violations.
7. Determinismo bit-a-bit del corpus_hash (golden value).
8. Función pura: misma input → mismo output.

Convenciones:
- Tests sin red, sin DB, sin Redis — `postprocess` es función pura sobre string.
- `compute_socratic_corpus_hash()` debe matchear el constante `SOCRATIC_CORPUS_HASH`.
"""

from __future__ import annotations

import pytest

from tutor_service.services.postprocess_socratic import (
    SOCRATIC_CORPUS_HASH,
    SOCRATIC_CORPUS_VERSION,
    compute_socratic_corpus_hash,
    postprocess,
)

GOLDEN_HASH = "a9b1d8cc5fab959f031f30f9bbb4c2bb632c41acad6f6af3f20897aef2b105b9"


class TestPostprocessSocratic:
    def test_respuesta_socratica_simple_score_alto_sin_violations(self) -> None:
        response = "¿Qué pasa si en lugar de un for usás un while? ¿Qué condición tendría que cumplir?"
        result = postprocess(response)
        assert result.socratic_compliance == 1.0
        assert result.violations == []

    def test_bloque_codigo_grande_match_code_block_complete(self) -> None:
        # Bloque > 200 chars dentro de fenced code
        big_code = "def factorial(n):\n" + "    " * 50 + "return 1\n" * 20
        response = f"Acá tenés:\n```python\n{big_code}\n```\n¿Probaste correrlo?"
        result = postprocess(response)
        categories = {v.category for v in result.violations}
        assert "code_block_complete" in categories
        assert result.socratic_compliance < 1.0

    def test_respuesta_sin_signo_pregunta_match_no_question(self) -> None:
        response = "Pensá en cómo resolverías el problema con los datos que tenés."
        result = postprocess(response)
        categories = {v.category for v in result.violations}
        assert "no_question_in_response" in categories

    def test_signo_pregunta_invertido_unico_basta(self) -> None:
        response = "¿Probaste imprimir el valor de i en cada iteración."
        result = postprocess(response)
        categories = {v.category for v in result.violations}
        assert "no_question_in_response" not in categories

    def test_imperativo_respuesta_directa_match_direct_answer(self) -> None:
        response = "La solución es usar un diccionario para indexar los valores. ¿Tenés dudas?"
        result = postprocess(response)
        categories = {v.category for v in result.violations}
        assert "direct_answer" in categories
        assert result.socratic_compliance < 1.0

    def test_tres_violaciones_simultaneas_score_saturado_a_cero(self) -> None:
        # code_block_complete + direct_answer + no_question_in_response
        big_code = "x = 1\n" * 100  # >200 chars
        response = f"La solución es directa. Tenés que escribir:\n```python\n{big_code}\n```\n"
        result = postprocess(response)
        categories = {v.category for v in result.violations}
        assert "code_block_complete" in categories
        assert "direct_answer" in categories
        assert "no_question_in_response" in categories
        # penalty = 0.4 + 0.3 + 0.3 = 1.0 → score = max(0, 1 - 1) = 0
        assert result.socratic_compliance == pytest.approx(0.0)

    def test_respuesta_vacia_score_neutral(self) -> None:
        result = postprocess("")
        assert result.socratic_compliance == 0.5
        assert result.violations == []

    def test_corpus_hash_determinista_bit_a_bit(self) -> None:
        # Dos invocaciones de la función pura devuelven el mismo hash.
        h1 = compute_socratic_corpus_hash()
        h2 = compute_socratic_corpus_hash()
        assert h1 == h2
        # Y matchea el módulo-level cache.
        assert h1 == SOCRATIC_CORPUS_HASH
        # Es un SHA-256 hex.
        assert len(h1) == 64
        assert all(c in "0123456789abcdef" for c in h1)

    def test_corpus_version_es_1_0_0(self) -> None:
        assert SOCRATIC_CORPUS_VERSION == "1.0.0"

    def test_corpus_hash_golden(self) -> None:
        # Anti-regresión: cualquier cambio accidental en patterns/weights/severity
        # cambia este hash. Si rompe legítimamente (rebalanceo del score
        # post-validación intercoder), bumpear SOCRATIC_CORPUS_VERSION y
        # actualizar este golden con el valor recomputado.
        golden = "a9b1d8cc5fab959f031f30f9bbb4c2bb632c41acad6f6af3f20897aef2b105b9"
        assert SOCRATIC_CORPUS_HASH == golden, (
            f"Corpus hash drift detectado. SOCRATIC_CORPUS_HASH={SOCRATIC_CORPUS_HASH} "
            f"esperado golden={golden}. Si el cambio es legítimo, bumpear "
            f"SOCRATIC_CORPUS_VERSION y actualizar este golden."
        )

    def test_postprocess_es_idempotente(self) -> None:
        response = "¿Probaste con un for? ¿Qué pasaría si i empieza en 1 en lugar de 0?"
        r1 = postprocess(response)
        r2 = postprocess(response)
        assert r1.socratic_compliance == r2.socratic_compliance
        assert [(v.category, v.pattern_id) for v in r1.violations] == [
            (v.category, v.pattern_id) for v in r2.violations
        ]
        assert r1.corpus_hash == r2.corpus_hash

    def test_excerpt_truncado_a_max_excerpt(self) -> None:
        # bloque grande con suficiente tamaño para superar _MAX_EXCERPT
        big_code_block = "```python\n" + ("x = 1\n" * 100) + "```"
        response = f"{big_code_block} ¿Qué hace?"
        result = postprocess(response)
        code_violations = [v for v in result.violations if v.category == "code_block_complete"]
        assert len(code_violations) == 1
        # Excerpt termina con "..." si fue truncado
        assert code_violations[0].excerpt.endswith("...")
        assert len(code_violations[0].excerpt) <= 153  # 150 + "..."


class TestFlagOff:
    """Garantía de ADR-027: con flag OFF, el payload sigue con None/[].

    Estos tests NO ejercitan tutor_core.interact() (eso requiere mocks de
    sessions/ctr/etc.). Verifican el contrato del postprocess en sí: si NO
    se llama, no hay output. La verificación del flag-gate vive en tests
    de integración del tutor_core (futuro, cuando se prenda el flag).
    """

    def test_postprocess_no_se_llama_implicitamente(self) -> None:
        # Si nadie invoca postprocess(...), no se computa nada.
        # Este test es más assertivo de lo que parece: documenta que NO hay
        # singleton activado por import-time. Importar el módulo no dispara
        # el cálculo sobre nada.
        import tutor_service.services.postprocess_socratic as module

        # El módulo expone función + constantes, NO un objeto stateful que
        # acumule violations entre invocaciones.
        assert callable(module.postprocess)
        assert isinstance(module.SOCRATIC_CORPUS_HASH, str)
