"""El tutor CIERRA el lazo cuando el estudiante acierta.

EL REPORTE (la critica mas comun del piloto, 2026-09-21)
--------------------------------------------------------
    "El socratico no les ayuda, se la pasa haciendo preguntas. Si vos le decis
     la respuesta necesitas que te diga 'si, lo que pensaste es correcto' o algo
     parecido, no que te diga 300 preguntas mas."

EL DEFECTO
----------
No es que el tutor sea "demasiado socratico". Es que el metodo, como estaba
escrito en v1.4.0, **no tenia salida**: los cuatro movimientos son todos de
apertura —ironia suspende, mayeutica pregunta, elenchos contradice, aporia
sostiene el bloqueo— y ninguno cierra. En los dialogos tempranos de Platon eso
es deliberado. En una cursada con un TP que entregar, no.

Tres lineas concretas de v1.4.0 lo producian:

  - La ironia mandaba devolver la pregunta ante "esto esta bien?" SIN condicion,
    sin distinguir el "¿esta bien?" a secas del "creo que es X porque Y".
  - El Principio 5 ("Reconocer avances") era prioridad 5, decia "reforzalo"
    sin decir cuando, y terminaba mandando otra pregunta.
  - `Responder con "si, perfecto" cuando hay errores por corregir` estaba en
    "Lo que NO hace": un condicional que el modelo generalizaba a un absoluto.

Y el dato que lo vuelve indefendible: el cierre YA estaba modelado en los datos
—cada ejercicio trae `heuristica_cierre` y cada pregunta del banco socratico
trae `senal_comprension` (ADR-048)— y el prompt no tenia ninguna accion asociada
a detectarlo. Detectores sin accion.

POR QUE ESTE TEST NO ES DECORATIVO
----------------------------------
El hash del manifest detecta que el prompt CAMBIO; no detecta que siga siendo
correcto. Un bump futuro puede reescribir la seccion y perder el cierre sin que
nada avise, porque el hash nuevo va a coincidir con el manifest nuevo.

Y las dos mitades importan por igual: este archivo prueba que la confirmacion
EXISTE **y** que el metodo socratico sigue intacto. Un test que solo probara lo
primero dejaria pasar un prompt que confirma cualquier cosa — que es el fracaso
opuesto y peor, porque destruye el constructo que el marco mide.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tutor_service.config import Settings


def _prompt_activo() -> str:
    """El texto del prompt que el tutor-service usa DE VERDAD.

    Se resuelve desde `Settings`, no con la version escrita a mano: si alguien
    bumpea el config y no la seccion, este archivo lee el prompt nuevo y las
    aserciones se caen — que es justo lo que queremos.

    Los saltos de linea se colapsan a un espacio: el prompt esta wrappeado a 79
    columnas y las frases que buscamos cruzan el corte. Un reflow cosmetico no
    tiene que romper este archivo — lo que se verifica es que la INSTRUCCION
    este, no donde cae el margen derecho.
    """
    raiz = Path(__file__).resolve().parents[4]
    version = Settings().default_prompt_version
    ruta = raiz / "ai-native-prompts/prompts/tutor" / version / "system.md"
    if not ruta.exists():
        pytest.fail(f"el prompt activo ({version}) no existe en {ruta}")
    return re.sub(r"\s+", " ", ruta.read_text(encoding="utf-8"))


class TestElMetodoTieneSalida:
    def test_declara_el_cierre_como_movimiento(self) -> None:
        """El corazon del fix.

        Verificado por reversion: sobre v1.4.0 esto falla — no hay ninguna
        seccion sobre cerrar, y la palabra "confirmacion" no aparece.
        """
        texto = _prompt_activo().lower()

        assert "cerrar el lazo" in texto, (
            "el metodo sigue siendo de apertura pura: ironia, mayeutica, "
            "elenchos y aporia abren y ninguno cierra, asi que el estudiante "
            "que ya razono bien recibe otra pregunta en vez de una confirmacion"
        )

    def test_manda_confirmar_y_dice_donde(self) -> None:
        """No alcanza con nombrar el cierre: hay que decir que hacer.

        "En la primera oracion" no es cosmetico — una confirmacion enterrada
        despues de dos preguntas el estudiante no la lee como confirmacion.
        """
        texto = _prompt_activo().lower()

        assert "confirmalo en la primera oracion" in texto

    def test_prohibe_retener_la_confirmacion(self) -> None:
        """La conducta exacta que el estudiante reporta como "no me ayuda"."""
        texto = _prompt_activo().lower()

        assert "no retengas la confirmacion" in texto

    def test_declara_que_la_mayeutica_termina(self) -> None:
        """Sin condicion de terminacion, la secuencia de 4 pasos se reinicia
        sobre el mismo punto y salen las "300 preguntas"."""
        texto = _prompt_activo().lower()

        assert "la mayeutica es una secuencia, no un bucle" in texto


class TestLaLineaEstaTrazadaEnLosDosSentidos:
    def test_da_un_ejemplo_de_lo_que_SI_se_confirma(self) -> None:
        """Sin ejemplo concreto el modelo traza la linea donde quiere."""
        texto = _prompt_activo().lower()

        assert "el bucle termina cuando i llega a n" in texto

    def test_la_conclusion_SIN_razon_sigue_recibiendo_la_pregunta(self) -> None:
        """La otra mitad. Confirmar un "me parece que esta bien" pelado seria
        exactamente el fracaso opuesto: un tutor que valida cualquier cosa."""
        texto = _prompt_activo().lower()

        assert "una conclusion sin razon" in texto

    def test_con_errores_se_confirma_la_parte_y_se_marca_lo_que_falta(self) -> None:
        """El condicional de v1.4.0 (`"si, perfecto" cuando hay errores`) estaba
        escrito como prohibicion y el modelo lo leia como absoluto. Ahora dice
        que hacer en su lugar."""
        texto = _prompt_activo().lower()

        assert "confirma lo que esta bien y marca lo que falta" in texto

    def test_declara_la_regla_de_desempate(self) -> None:
        """Ante la duda, confirmar.

        Los dos errores no cuestan lo mismo: confirmar de mas cuesta una
        oracion; no confirmar cuando correspondia le enseña al estudiante que
        con este tutor no se termina nunca de pensar.
        """
        texto = _prompt_activo().lower()

        assert "si el camino es valido, confirmalo" in texto


class TestNoLePeleaAlContextoPorEjercicio:
    def test_aclara_que_confirmar_no_es_dar_una_pista(self) -> None:
        """10 de los 25 ejercicios del piloto tienen
        `tutor_rules.forzar_pregunta_antes_de_hint = true`, que inyecta al
        system message "antes de dar cualquier pista, hace al menos una pregunta
        socratica". Sin esta aclaracion ese bloque por ejercicio le pelea al fix
        global y la confirmacion vuelve a llegar detras de una pregunta.
        """
        texto = _prompt_activo().lower()

        assert "confirmar no es dar una pista" in texto


class TestLosTresAjustesQueLoHacenEfectivo:
    def test_la_ironia_quedo_acotada_al_caso_sin_razon(self) -> None:
        """Era la linea que producia la queja, textual y sin condicion."""
        texto = _prompt_activo().lower()

        assert "sin decirte por que le parece que podria estarlo" in texto

    def test_el_principio_5_ahora_dice_cuando(self) -> None:
        texto = _prompt_activo().lower()

        assert "confirmar cuando acierta" in texto

    def test_retener_la_confirmacion_es_algo_que_el_tutor_NO_hace(self) -> None:
        texto = _prompt_activo().lower()

        assert "retener la confirmacion cuando el estudiante ya acerto" in texto


class TestElMetodoSocraticoSigueIntacto:
    """La regresion que este cambio podia introducir: aflojar de mas.

    Un prompt que confirma cualquier cosa es el fracaso opuesto al reportado, y
    seria peor: destruye el constructo que el marco mide.
    """

    @pytest.mark.parametrize("movimiento", ["ironia", "mayeutica", "elenchos", "aporia"])
    def test_los_cuatro_movimientos_siguen_declarados(self, movimiento: str) -> None:
        assert movimiento in _prompt_activo().lower()

    def test_GP1_sigue_en_pie(self) -> None:
        """No dar la solucion directa es el principio 1 y no se toca."""
        assert "NO des la solucion directa" in _prompt_activo()

    def test_sigue_sin_generar_codigo_completo(self) -> None:
        assert "Generar codigo completo por el estudiante" in _prompt_activo()

    def test_sigue_sin_dar_el_resultado_sin_razonarlo(self) -> None:
        assert "Dar el resultado de un ejercicio sin que el estudiante lo razone" in (
            _prompt_activo()
        )


class TestElFixDeV140NoSePierde:
    """v1.5.0 se deriva de v1.4.0. La seccion de notacion tiene que sobrevivir.

    Copiar un prompt y editarlo a mano es exactamente como se pierde un fix
    anterior sin que nada avise.
    """

    def test_la_notacion_se_sigue_respondiendo_directo(self) -> None:
        texto = _prompt_activo().lower()

        assert "notacion" in texto
        assert "respondele directo" in texto
        assert "respondela como factual" in texto

    def test_la_consulta_de_sintaxis_sigue_sin_ser_un_salteo(self) -> None:
        assert "Una consulta de sintaxis NO es un intento de salteo" in _prompt_activo()
