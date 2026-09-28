"""Anclajes de contenido para el prompt del tutor v1.6.0 — contexto real.

EL DEFECTO (verificado contra el codigo el 2026-09-28)
--------------------------------------------------------
El prompt v1.5.0 le dice al modelo que no conoce el enunciado del TP ("Vos no
conoces el enunciado completo — el estudiante te lo va a compartir si es
relevante", seccion "Contexto del TP"), cuando el propio tutor-service SI se
lo inyecta al abrir el episodio (`tutor_core.py`, bloque 3 de `open_episode`,
best-effort — degrada sin enunciado si el academic-service falla). Y el
codigo que el alumno tiene en el editor le llega numerado por linea en cada
turno (`tutor_core.py:825-828`, gateado por `if state.current_code and
state.current_code.strip()`), pero el prompt nunca lo menciona.

Consecuencia medida en produccion el 2026-09-28: el tutor le pide tres veces
al alumno que pegue su codigo, en una plataforma que bloquea copiar y pegar
— un callejon sin salida que le ordena el propio sistema. Y deriva al alumno
a Google: comportamiento emergente, el prompt no menciona buscadores
externos en ninguna linea (verificado por `rg`, cero coincidencias).

POR QUE ESTOS TESTS VAN ANTES DEL CONTENIDO
---------------------------------------------
Anclar por frase, no por numero de linea: el numero se mueve con cualquier
edicion futura del archivo. Y el orden importa — estos tests tienen que
fallar HOY, antes de que `v1.6.0/system.md` exista, para que el ciclo TDD
tenga un rojo real que ver y no una descripcion post-hoc de lo que ya se
escribio.

Se lee el archivo por ruta fija (`v1.6.0` hardcodeado), no via
`Settings().default_prompt_version` — ese literal todavia apunta a v1.5.0
en esta etapa (tarea 3.2 lo mueve despues).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_VERSION = "v1.6.0"


def _v1_6_0_path() -> Path:
    raiz = Path(__file__).resolve().parents[4]
    return raiz / "ai-native-prompts" / "prompts" / "tutor" / _VERSION / "system.md"


def _v1_6_0_prompt() -> str:
    """Texto del prompt v1.6.0, con saltos de linea colapsados a un espacio.

    El archivo esta wrappeado a ~79 columnas y las frases que se anclan acá
    cruzan el corte (mismo patron que `test_prompt_confirmacion_al_acertar.py`
    y `test_prompt_notacion_vs_razonamiento.py`): sin colapsar, un reflow
    cosmetico rompe el test aunque el contenido no haya cambiado.
    """
    ruta = _v1_6_0_path()
    if not ruta.exists():
        pytest.fail(f"el prompt {_VERSION} no existe en {ruta}")
    return re.sub(r"\s+", " ", ruta.read_text(encoding="utf-8"))


class TestElArchivoExiste:
    def test_existe_el_archivo_system_md_de_v1_6_0(self) -> None:
        """1.1 — existencia. NOTA: ya no puede ponerse rojo por su cuenta;
        el helper _v1_6_0_prompt() hace pytest.fail si el archivo falta, asi
        que los 7 tests del modulo mueren juntos por esa misma linea. Ese
        "RED 7/7" prueba que el archivo no estaba, NO que los anclajes
        discriminen (auditoria 2026-09-28, hallazgo 2)."""
        ruta = _v1_6_0_path()
        assert ruta.exists(), f"falta {ruta}"


class TestC1ElTutorSiConoceElEnunciado:
    def test_no_contiene_la_afirmacion_falsa_sobre_el_enunciado(self) -> None:
        """1.2 — el tutor SI recibe el enunciado (best-effort); esta frase miente."""
        texto = _v1_6_0_prompt().lower()
        assert "no conoces el enunciado" not in texto, (
            "el prompt todavia afirma que el tutor no conoce el enunciado del "
            "TP, pero tutor_core.py lo inyecta al abrir el episodio "
            "(open_episode, bloque 3, best-effort)"
        )
        assert "el estudiante te lo va a compartir si es relevante" not in texto, (
            "sigue la variante de la frase falsa sobre el enunciado"
        )

    def test_conserva_no_supongas_requisitos_que_el_enunciado_no_establecio(
        self,
    ) -> None:
        """1.5 — afirma que UNA oracion sigue presente. NO es un guardian de
        alcance: QA redujo system.md de 529 lineas a 11 conservando solo las
        frases ancladas y los 7 tests pasaron (auditoria 2026-09-28, BUG-3).
        El alcance lo cubren test_prompt_confirmacion_al_acertar.py y
        test_prompt_notacion_vs_razonamiento.py, que leen la version ACTIVA y
        siguieron el bump — 30 fallas sobre el documento mutilado. Esos son
        heredados, no de este change."""
        texto = _v1_6_0_prompt()
        assert "NO supongas requisitos que el enunciado no establecio" in texto, (
            "la instruccion valida de v1.5.0 desaparecio — C1 corrige el hecho "
            "falso sobre el enunciado, no reescribe el resto de la seccion"
        )

    def test_afirma_que_el_tutor_si_recibe_el_enunciado(self) -> None:
        """Ancla POSITIVA de C1 — sin esto, borrar la seccion corregida entera
        deja los tests en verde: la negativa de 1.2 queda satisfecha por la
        ausencia. QA lo demostro el 2026-09-28 (BUG-2) borrando el parrafo y
        obteniendo 7 passed."""
        texto = _v1_6_0_prompt().lower()
        assert "recibis el enunciado" in texto, (
            "desaparecio la afirmacion verdadera de C1. El tutor SI recibe el "
            "enunciado al abrir el episodio; decirlo es la correccion, no solo "
            "callar la frase falsa"
        )
        assert "no hace falta que te lo pegue" in texto, (
            "desaparecio la consecuencia operativa de C1 — es la frase que "
            "evita que el tutor pida el enunciado pegado"
        )

    def test_declara_que_el_enunciado_es_best_effort(self) -> None:
        """El enunciado NO se inyecta incondicionalmente: contexto_data sale de
        un try/except que degrada a None si el academic-service falla
        (tutor_core.py:1289-1305). El prompt tiene que decir que hacer en ese
        caso, o reintroduce una afirmacion falsa distinta."""
        texto = _v1_6_0_prompt().lower()
        assert "best-effort" in texto, (
            "C1 afirma que el enunciado llega, sin declarar que puede no llegar"
        )
        assert "no le pidas que te pegue el enunciado" in texto, (
            "falta la conducta para el camino degradado: sin enunciado, "
            "preguntar por el problema — nunca pedir un pegado"
        )

    def test_prohibe_mandarlo_a_un_entorno_que_no_existe(self) -> None:
        """C4 — reportado por el tester el 2026-09-28: el tutor sugirio "probar
        en la consola de Python". La plataforma no tiene consola interactiva —
        son tres paneles (consigna, editor, tutor) y ejecucion con Pyodide.
        Verificado en apps/web-student/src/pages/EpisodePage.tsx (aria-labels)."""
        texto = _v1_6_0_prompt().lower()
        assert "consola" in texto and "no existe" in texto, (
            "falta la prohibicion de mandar al estudiante a una consola "
            "interactiva que la plataforma no tiene"
        )
        assert "agregue un print" in texto or "ejecutar su propio codigo" in texto, (
            "la prohibicion tiene que ofrecer la alternativa real: el "
            "estudiante SI puede ejecutar su codigo y ver la salida"
        )


class TestElPromptSeAutodeclaraConSuVersion:
    def test_el_titulo_declara_v1_6_0_y_no_la_version_anterior(self) -> None:
        """BUG-1 de QA (2026-09-28): v1.6.0/system.md:1 decia "(v1.5.0)". Es el
        unico literal de version que el MODELO lee, y rompia la convencion de
        las 7 versiones anteriores. La suite estaba verde en 527 con el titulo
        mintiendo, porque ningun test lo miraba."""
        primera = _v1_6_0_path().read_text(encoding="utf-8").splitlines()[0]
        assert f"({_VERSION})" in primera, (
            f"el titulo del prompt no se autodeclara {_VERSION}: {primera!r}. "
            "Corregirlo cambia el sha256 y obliga a re-firmar el hash en "
            "v1.6.0/manifest.yaml, que el governance-service verifica fail-loud"
        )


class TestC2ElTutorVeElCodigoDelAlumno:
    def test_prohibe_pedir_que_el_alumno_pegue_su_codigo(self) -> None:
        """1.3 — debe fallar de verdad si alguien revierte C2."""
        texto = _v1_6_0_prompt().lower()
        assert "nunca le pidas al estudiante que te pegue" in texto, (
            "falta la prohibicion de pedir codigo pegado — el codigo ya le "
            "llega numerado por linea (tutor_core.py:825-828) y la plataforma "
            "bloquea copiar y pegar, asi que pedirlo es un callejon sin salida"
        )

    def test_indica_que_el_codigo_llega_numerado_por_linea(self) -> None:
        """Anclaje del resto de C2: sin esto, la prohibicion queda sin contexto."""
        texto = _v1_6_0_prompt().lower()
        assert "numerado por linea" in texto

    def test_indica_que_hacer_cuando_todavia_no_hay_codigo(self) -> None:
        """C2 tambien cubre el camino sin codigo: invitar a escribir, no a pegar."""
        texto = _v1_6_0_prompt().lower()
        assert "todavia no hay codigo" in texto
        assert "invitalo a escribir" in texto


class TestC3NoDerivaAHerramientasExternas:
    def test_prohibe_derivar_a_google_chatgpt_y_stack_overflow(self) -> None:
        """1.4."""
        texto = _v1_6_0_prompt().lower()
        assert "no recomiendes buscar la respuesta en google" in texto, (
            "falta la prohibicion de derivar a buscadores externos — "
            "comportamiento emergente medido en produccion el 2026-09-28"
        )
        assert "chatgpt" in texto
        assert "stack overflow" in texto
