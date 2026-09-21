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


def _movimientos(version: str) -> dict[str, str]:
    """Los cuatro movimientos de una version, cada uno como bloque de texto.

    Se parsea por los `###` de la seccion "Movimientos del metodo". Devuelve el
    texto normalizado, igual que `_prompt_activo`, para que un reflow cosmetico
    no cuente como cambio de metodo.
    """
    raiz = Path(__file__).resolve().parents[4]
    ruta = raiz / "ai-native-prompts/prompts/tutor" / version / "system.md"
    if not ruta.exists():
        pytest.fail(f"el prompt {version} no existe en {ruta}")
    seccion, dentro = [], False
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.startswith("## Movimientos del metodo"):
            dentro = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            seccion.append(linea)
    bloques, actual = {}, None
    for linea in seccion:
        if linea.startswith("### "):
            actual = linea[4:].split("—")[0].strip().lower()
            bloques[actual] = []
        elif actual:
            bloques[actual].append(linea)
    return {k: re.sub(r"\s+", " ", "\n".join(v)).strip() for k, v in bloques.items()}


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


class TestElDeltaDelMetodoEsElDeclarado:
    """Lo que el manifest afirma sobre el metodo, verificado contra v1.4.0.

    El manifest de una version es el registro que queda: quien dentro de seis
    meses quiera saber que cambio entre v1.4.0 y v1.5.0 lo lee a el, no al PR.
    Una nota que dice "byte a byte" sobre algo que cambio es peor que no tener
    nota, porque se lee con autoridad y nadie vuelve a chequearla.

    `test_los_cuatro_movimientos_siguen_declarados` no alcanza para esto: busca
    la PALABRA del movimiento, de modo que pasa aunque el bloque entero cambie.
    """

    PADRE = "v1.4.0"

    @pytest.mark.parametrize("movimiento", ["mayeutica", "elenchos", "aporia"])
    def test_los_tres_movimientos_intactos_son_identicos_a_v140(self, movimiento: str) -> None:
        """Verificado por reversion: si alguien edita uno de estos, esto se cae."""
        version = Settings().default_prompt_version
        assert _movimientos(version)[movimiento] == _movimientos(self.PADRE)[movimiento], (
            f"{movimiento} cambio respecto de {self.PADRE}; el manifest declara "
            f"que los tres quedan byte a byte. Actualizar la nota o revertir el cambio."
        )

    def test_la_ironia_si_cambia_y_el_cambio_es_el_declarado(self) -> None:
        """El delta que el manifest SI declara: la ironia acotada al caso sin razon.

        Se afirma en los dos sentidos —que difiere de v1.4.0 y que la diferencia
        es la condicion nueva— para que un cambio distinto en la ironia tampoco
        pase silencioso.
        """
        version = Settings().default_prompt_version
        ironia_nueva = _movimientos(version)["ironia"]
        ironia_vieja = _movimientos(self.PADRE)["ironia"]
        assert ironia_nueva != ironia_vieja, (
            "la ironia quedo igual a v1.4.0: sin el acote al caso sin razon, "
            "le pelea a 'Cerrar el lazo' y la seccion nueva no tiene efecto."
        )
        assert "sin decirte por que le parece que podria estarlo" in ironia_nueva
        assert "negarle la confirmacion a quien ya te dio la razon" in ironia_nueva

    def test_el_manifest_no_afirma_que_los_cuatro_quedan_intactos(self) -> None:
        """La nota que este fix corrige, para que no vuelva por copiar-y-editar."""
        raiz = Path(__file__).resolve().parents[4]
        version = Settings().default_prompt_version
        manifest = raiz / "ai-native-prompts/prompts/tutor" / version / "manifest.yaml"
        texto = re.sub(r"\s+", " ", manifest.read_text(encoding="utf-8")).lower()
        assert "los 4 movimientos socraticos" not in texto or "byte a byte" not in texto, (
            "el manifest vuelve a afirmar que los cuatro movimientos quedan byte a "
            "byte; la ironia cambia y esa nota es lo que queda como trazabilidad."
        )
