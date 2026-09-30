"""Anclajes del prompt v1.7.0 — las reglas que el tutor NO conoce.

ORIGEN
------
Informe del tester sobre el TP de Listas v3 (ejercicios 1 a 5), 2026-09-30.

El tutor le dijo al alumno que la plataforma no lo penaliza por abrir otra
pestana. El alumno respondio que le salia el cartel de aviso, y el tutor cambio
de postura SIN corregir lo que habia dicho.

La politica real (`tutor-service/config.py:131-138`) es intermedia: NO cierra el
episodio, pero SI registra `pestana_perdida`/`pestana_recuperada` en el CTR, SI
muestra un overlay bloqueante al volver, y el docente lo ve en la auditoria. El
tutor afirmo la mitad tranquilizadora — y nada de eso le llega en el contexto.

Y una CORRECCION de v1.6.0: la prohibicion de derivar afuera chocaba con las
consignas. 13 enunciados del piloto mandan a investigar, uno literal:
`ejercicios-piloto.yaml:1834` — "Nota: investigar el uso del operador de modulo
(%) en Python". Contradecir la consigna pone al tutor en contra del docente.
"""

import pathlib

import pytest

_VERSION = "v1.7.0"
_RUTA = (
    pathlib.Path(__file__).resolve().parents[4]
    / "ai-native-prompts"
    / "prompts"
    / "tutor"
    / _VERSION
    / "system.md"
)


def _prompt() -> str:
    if not _RUTA.exists():
        pytest.fail(f"el prompt {_VERSION} no existe en {_RUTA}")
    return _RUTA.read_text(encoding="utf-8")


def _plano() -> str:
    """Saltos de linea colapsados: las frases del prompt cruzan renglones."""
    return " ".join(_prompt().split()).lower()


class TestC5NoAfirmaReglasDeLaPlataforma:
    def test_declara_que_no_conoce_las_reglas(self) -> None:
        t = _plano()
        assert "reglas de la plataforma" in t
        assert "nada de eso te llega" in t, (
            "falta el POR QUE: el tutor no recibe las reglas en su contexto. "
            "Sin el motivo, la prohibicion se lee como arbitraria"
        )

    def test_recomienda_no_salir_ante_la_duda(self) -> None:
        # La conducta que pidio el tester. Prohibir sin dar la alternativa deja
        # al modelo eligiendo cualquier cosa.
        assert "no salir de la pantalla" in _plano()

    def test_manda_corregirse_cuando_el_alumno_lo_desmiente(self) -> None:
        # Este es el defecto exacto: cambio de postura y no corrigio. El alumno
        # esta VIENDO la pantalla; el tutor la esta adivinando.
        t = _plano()
        assert "el tiene el dato y vos no" in t
        assert "corregilo en voz alta" in t


class TestC3CorregidoLaConsignaManda:
    def test_la_consigna_puede_mandarlo_afuera(self) -> None:
        # Correccion de v1.6.0. Sin esta excepcion el tutor contradice a 13
        # enunciados del piloto que mandan a investigar.
        t = _plano()
        assert "si el enunciado se lo pide, mandalo" in t

    def test_nombra_a_quien_decide(self) -> None:
        # Lo que distingue la regla nueva de la vieja: no es QUE se derive, es
        # QUIEN lo decide.
        assert "la consigna si, vos no" in _plano()

    def test_conserva_la_prohibicion_por_cuenta_propia(self) -> None:
        # Guardian de alcance: corregir C3 no puede convertirse en borrarlo.
        t = _plano()
        assert "google" in t and "stack overflow" in t


class TestVoseoExplicito:
    def test_dice_voseo_y_no_solo_rioplatense(self) -> None:
        # "Rioplatense neutro" ya estaba en v1.6.0 y no alcanzo: el tester
        # reporto tuteo en el ejercicio 3. Un implicito no sostiene un turno 40.
        t = _plano()
        assert "voseo siempre" in t
        assert "nunca tuteo" in t


class TestElPromptSeAutodeclaraConSuVersion:
    def test_el_titulo_dice_v1_7_0(self) -> None:
        # BUG-1 de la auditoria del 2026-09-28: v1.6.0 se autodeclaraba v1.5.0 y
        # la suite quedo verde con el titulo mintiendo. Es el unico literal de
        # version que el MODELO lee.
        primera = _prompt().splitlines()[0]
        assert f"({_VERSION})" in primera, f"el titulo no se autodeclara: {primera!r}"


class TestElMetodoNoSeToco:
    @pytest.mark.parametrize(
        "frase",
        ["ironia", "mayeutica", "elenchos", "aporia", "cerrar el lazo"],
    )
    def test_los_movimientos_siguen_nombrados(self, frase: str) -> None:
        # Red minima. La red REAL son test_prompt_confirmacion_al_acertar.py y
        # test_prompt_notacion_vs_razonamiento.py, que leen la version ACTIVA y
        # siguen el bump: 42 rojos contra un prompt mutilado. Esos son heredados,
        # no de este bump — no me los acredito.
        assert frase in _plano()
