"""Anclajes de contenido para el prompt del tutor v1.9.0 — copiar/pegar interno.

ORIGEN
------
Change `copiar-pegar-interno-en-el-episodio`. v1.8.0 le dice al modelo, dos
veces, que "en esta plataforma copiar y pegar esta bloqueado" / "la
plataforma no permite copiar y pegar en el editor". Con el portapapeles
interno (`CodeEditor.tsx`) eso deja de ser cierto EN GENERAL: dentro del
episodio (consigna -> editor, editor -> editor) el pegado SI funciona. Lo
que sigue bloqueado es **hacia afuera**: pegar algo que no se copio adentro
de esta misma pagina.

Si este change entra sin corregir el prompt, el tutor le miente al alumno
sobre una regla de la plataforma — exactamente el defecto C5 que v1.7.0 ya
cerro para OTRA regla (pestana perdida). No repetirlo para esta.

Se lee el archivo por ruta fija (`v1.9.0` hardcodeado), no via
`Settings().default_prompt_version` — ese literal sigue apuntando a v1.8.0:
la activacion de v1.9.0 espera revision de Ana Garis (gobernanza MEDIO-ALTA
del proposal), igual que las tres versiones anteriores.

Anclar por frase, no por numero de linea: el numero se mueve con cualquier
edicion futura del archivo.
"""

from __future__ import annotations

import pathlib

import pytest

_VERSION = "v1.9.0"
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


class TestElPromptSeAutodeclaraConSuVersion:
    def test_el_titulo_dice_v1_9_0(self) -> None:
        # Mismo guardian que BUG-1 de la auditoria del 2026-09-28: el titulo
        # es el unico literal de version que el MODELO lee.
        primera = _prompt().splitlines()[0]
        assert f"({_VERSION})" in primera, f"el titulo no se autodeclara: {primera!r}"


class TestLaAfirmacionDeBloqueoTotalYaNoEsta:
    """v1.8.0 decia, textual, dos veces, que copiar/pegar esta bloqueado EN
    GENERAL. Las dos son falsas desde este change."""

    def test_no_afirma_que_copiar_y_pegar_este_bloqueado_sin_calificar(self) -> None:
        t = _plano()
        # La frase textual de v1.8.0 no puede sobrevivir intacta: afirmaria
        # una regla que ya no rige.
        assert "copiar y pegar esta bloqueado" not in t
        assert "la plataforma no permite copiar y pegar en el editor" not in t

    def test_dice_que_el_bloqueo_es_hacia_afuera(self) -> None:
        t = _plano()
        assert "hacia afuera" in t
        assert "pegar" in t

    def test_dice_que_dentro_del_episodio_se_puede_pegar(self) -> None:
        # El hecho nuevo, no solo la ausencia del viejo: sin esto el modelo
        # se queda sin saber la regla actual, solo que la vieja ya no vale.
        t = _plano()
        assert "dentro del episodio" in t and "se puede" in t


class TestElConsejoDeVsCodeSigueProhibidoPeroPorOtraRazon:
    """Tarea 4.3: 'llevatelo a VS Code' sigue prohibido, ahora por el
    argumento pedagogico y no por imposibilidad tecnica — copiar codigo
    AFUERA del editor si funciona hoy (Ctrl+C real); lo que sigue bloqueado
    es pegar algo de afuera de vuelta adentro."""

    def test_ya_no_justifica_la_prohibicion_con_que_no_se_puede_ejecutar(self) -> None:
        # Guardian negativo: la vieja razon (imposibilidad tecnica) no puede
        # quedar como la razon vigente.
        t = _plano()
        assert "no se puede ejecutar" not in t

    def test_sigue_recomendando_no_llevarselo_a_vs_code(self) -> None:
        t = _plano()
        assert "vs code" in t

    def test_dice_que_la_plataforma_ya_guarda_el_progreso_sola(self) -> None:
        # El argumento pedagogico concreto: un respaldo manual es innecesario
        # porque el guardado automatico ya existe (onEditDebounced ->
        # saveArtefactoDraft). Sin este dato el "no lo hagas" queda huerfano
        # de motivo, que es el MISMO defecto que C4 le encontro a v1.6.0.
        t = _plano()
        assert "se guarda" in t or "guardado automat" in t


class TestNoLePidasQueComparaElCodigo:
    """La seccion 'El codigo que el estudiante esta escribiendo' tambien
    justificaba el pedido-imposible con el bloqueo total. Se corrige sin
    tocar la instruccion de fondo (seguis sin pedirle que te pegue nada)."""

    def test_sigue_prohibiendo_pedir_que_pegue_el_codigo(self) -> None:
        t = _plano()
        assert "nunca le pidas al estudiante que te pegue" in t

    def test_ya_no_justifica_eso_con_bloqueo_total_del_editor(self) -> None:
        t = _plano()
        assert "la plataforma no permite copiar y pegar en el editor" not in t


class TestElMetodoNoSeToco:
    @pytest.mark.parametrize(
        "frase",
        ["ironia", "mayeutica", "elenchos", "aporia", "cerrar el lazo"],
    )
    def test_los_movimientos_siguen_nombrados(self, frase: str) -> None:
        # Red minima, mismo patron que test_prompt_reglas_plataforma.py: este
        # bump NO toca el metodo, solo la seccion de reglas de la plataforma.
        assert frase in _plano()


class TestElRestoDeC5NoSeRompio:
    """Guardian de regresion: v1.8.0 ya tenia la correccion de C5 (pestana
    perdida) y C3/C4 (derivar afuera). Este bump no las toca."""

    def test_c5_pestana_perdida_sigue(self) -> None:
        t = _plano()
        assert "nada de eso te llega" in t

    def test_c3_la_consigna_puede_mandarlo_afuera_sigue(self) -> None:
        t = _plano()
        assert "la consigna si, vos no" in t
