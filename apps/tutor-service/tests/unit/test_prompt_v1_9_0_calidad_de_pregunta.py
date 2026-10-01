"""El prompt v1.9.0 del tutor sube la CALIDAD de la pregunta.

EL REPORTE (cuatro alumnos del piloto, dos canales, 2026-09-30/10-01)
-----------------------------------------------------------------------
    "le consulto de que manera puedo realizar una validacion, y el tutor me
     responde: como empezarias? que cambiarias? por que creés que deberias
     validarlo?"

    "nunca me ha dicho una funcion o porcion de codigo, estaria bueno que te
     ensene (no que te resuelva el codigo)"

    "preguntas alguna duda y responde con otra pregunta, en vez de mostrar
     ejemplo como ayuda"

EL DIAGNOSTICO
---------------
Los cuatro movimientos del metodo son todos de APERTURA y presuponen que el
estudiante ya tiene algo adentro para que se lo saquen. Un alumno de primer
ano que nunca escucho hablar del concepto no tiene de donde agarrarse, y es
el caso mas comun, no el raro.

LOS CINCO CAMBIOS, NINGUNO SOBRE GUARDRAILS
---------------------------------------------
1. Una sola pregunta por turno (antes: "una o dos").
2. Nombrar una herramienta que el alumno no conoce no es resolver.
3. Seccion nueva "Abrir el lazo" — la entrada del metodo.
4. Seccion nueva "Usar el material del ejercicio" — el banco socratico y las
   misconceptions pasan de media oracion a seccion propia.
5. Credito parcial en "Cerrar el lazo", que hoy es binario.

POR QUE ESTE TEST NO ES DECORATIVO
------------------------------------
El hash del manifest detecta que el prompt CAMBIO; no detecta que cambio BIEN.
Por eso este archivo prueba las dos mitades: que los cinco cambios estan, y
que lo que el manifest dice que queda intacto (los cuatro movimientos, los
nueve principios, y "Cerrar el lazo" salvo el agregado) sigue siendo byte a
byte identico a v1.8.0. Es el mismo patron de
`test_prompt_confirmacion_al_acertar.py`, que comparo los tres movimientos
intactos contra v1.4.0.

v1.9.0 viaja DESACTIVADO: `config.py` y el manifest raiz siguen en v1.8.0
hasta que cierre la revision coautoral de Ana Garis (ver
`test_header_del_prompt_no_miente.py`). Por eso estos tests leen el archivo
de v1.9.0 por ruta directa, no via `Settings().default_prompt_version`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VERSION = "v1.9.0"
PADRE = "v1.8.0"


def _ruta(version: str) -> Path:
    raiz = Path(__file__).resolve().parents[4]
    return raiz / "ai-native-prompts/prompts/tutor" / version / "system.md"


def _prompt(version: str) -> str:
    ruta = _ruta(version)
    if not ruta.exists():
        pytest.fail(f"el prompt {version} no existe en {ruta}")
    return ruta.read_text(encoding="utf-8")


def _normalizado(version: str) -> str:
    """Colapsa saltos de linea a un espacio — ver docstring de la funcion
    equivalente en test_prompt_confirmacion_al_acertar.py: un reflow cosmetico
    no tiene que romper este archivo."""
    return re.sub(r"\s+", " ", _prompt(version))


def _seccion(version: str, encabezado: str) -> str:
    """Texto de una seccion `## encabezado...`, sin la linea del encabezado.

    Matchea por prefijo: "Cerrar el lazo" encuentra
    "## Cerrar el lazo: cuando el estudiante acierta".
    """
    dentro = False
    bloque: list[str] = []
    encontrada = False
    for linea in _prompt(version).splitlines():
        if linea.startswith(f"## {encabezado}"):
            dentro = True
            encontrada = True
            continue
        if dentro and linea.startswith("## "):
            break
        if dentro:
            bloque.append(linea)
    if not encontrada:
        pytest.fail(f"la seccion '## {encabezado}' no existe en {version}")
    return "\n".join(bloque)


def _indice_encabezado(version: str, encabezado: str) -> int:
    """Numero de linea (0-based) donde arranca `## encabezado...`, o -1.

    Ancla por `startswith` linea por linea — a diferencia de un `in` sobre el
    texto plano, "## Abrir el lazo" NO matchea dentro de "### Abrir el lazo":
    un substring plano si lo hace, porque "## " cae contenido en "### ".
    """
    for i, linea in enumerate(_prompt(version).splitlines()):
        if linea.startswith(f"## {encabezado}"):
            return i
    return -1


def _movimientos(version: str) -> dict[str, str]:
    """Los cuatro movimientos, cada uno como bloque de texto normalizado."""
    seccion = _seccion(version, "Movimientos del metodo")
    bloques: dict[str, list[str]] = {}
    actual = None
    for linea in seccion.splitlines():
        if linea.startswith("### "):
            actual = linea[4:].split("—")[0].strip().lower()
            bloques[actual] = []
        elif actual:
            bloques[actual].append(linea)
    return {k: re.sub(r"\s+", " ", "\n".join(v)).strip() for k, v in bloques.items()}


class TestLosCincoCambiosEstan:
    def test_una_sola_pregunta_por_turno(self) -> None:
        """Reemplaza 'una o dos preguntas o sugerencias por turno' de v1.8.0."""
        texto = _normalizado(VERSION).lower()
        assert "una sola pregunta por turno" in texto
        assert "una o dos preguntas o sugerencias por turno" not in texto

    def test_tres_preguntas_juntas_son_una_pared(self) -> None:
        texto = _normalizado(VERSION).lower()
        assert "tres preguntas juntas no son tres oportunidades de pensar" in texto

    def test_nombrar_la_herramienta_no_es_resolver(self) -> None:
        seccion = _seccion(VERSION, "Lo que SI se responde directo").lower()
        assert "nombrar una herramienta que el estudiante todavia no" in seccion
        assert "nombrar la herramienta y seguir preguntando" in seccion
        assert "no cuenta como dar una pista" in seccion

    def test_seccion_abrir_el_lazo_existe(self) -> None:
        assert _indice_encabezado(VERSION, "Abrir el lazo") >= 0

    def test_abrir_el_lazo_pide_ejemplo_de_otro_dominio(self) -> None:
        seccion = _seccion(VERSION, "Abrir el lazo").lower()
        assert "un ejemplo de otra cosa" in seccion
        assert "nunca del ejercicio que esta resolviendo" in seccion

    def test_abrir_el_lazo_esta_antes_de_cerrar_el_lazo(self) -> None:
        idx_abrir = _indice_encabezado(VERSION, "Abrir el lazo")
        idx_cerrar = _indice_encabezado(VERSION, "Cerrar el lazo")
        assert idx_abrir >= 0 and idx_cerrar >= 0
        assert idx_abrir < idx_cerrar

    def test_seccion_usar_el_material_del_ejercicio_existe(self) -> None:
        assert _indice_encabezado(VERSION, "Usar el material del ejercicio") >= 0

    def test_usar_el_material_tiene_el_test_de_la_pregunta_generica(self) -> None:
        seccion = _seccion(VERSION, "Usar el material del ejercicio").lower()
        assert "cambiale el tema y fijate si" in seccion
        assert "es una plantilla" in seccion

    def test_usar_el_material_esta_antes_del_contexto_rag(self) -> None:
        idx_usar = _indice_encabezado(VERSION, "Usar el material del ejercicio")
        idx_rag = _indice_encabezado(VERSION, "Uso del material de catedra")
        assert idx_usar >= 0 and idx_rag >= 0
        assert idx_usar < idx_rag

    def test_contexto_del_tp_ya_no_relega_el_material_a_media_oracion(self) -> None:
        seccion = re.sub(r"\s+", " ", _seccion(VERSION, "Contexto del TP")).lower()
        assert "mapa privado para orientar tus preguntas" not in seccion
        assert "no es decorativo y no es opcional" in seccion

    def test_cerrar_el_lazo_tiene_credito_parcial(self) -> None:
        seccion = _seccion(VERSION, "Cerrar el lazo").lower()
        assert "acierta en parte" in seccion
        assert "nombra primero" in seccion


class TestLoQueNoCambioNoCambio:
    """El manifest va a afirmar que esto queda intacto. Este archivo lo prueba."""

    @pytest.mark.parametrize("movimiento", ["ironia", "mayeutica", "elenchos", "aporia"])
    def test_los_cuatro_movimientos_son_identicos_a_v180(self, movimiento: str) -> None:
        assert _movimientos(VERSION)[movimiento] == _movimientos(PADRE)[movimiento], (
            f"{movimiento} cambio respecto de {PADRE}; esta change no toca el metodo."
        )

    def test_los_principios_son_identicos_a_v180(self) -> None:
        assert _seccion(VERSION, "Principios") == _seccion(PADRE, "Principios")

    def test_cerrar_el_lazo_conserva_integro_el_texto_de_v180(self) -> None:
        """El credito parcial se AGREGA; nada de lo que ya estaba se reescribe.

        Se verifica que el texto completo de 'Cerrar el lazo' en v1.8.0 sigue
        apareciendo, sin alterar, dentro de la seccion de v1.9.0.
        """
        seccion_v190 = _seccion(VERSION, "Cerrar el lazo")
        seccion_v180 = _seccion(PADRE, "Cerrar el lazo")
        assert seccion_v180.strip() in seccion_v190, (
            "el texto de 'Cerrar el lazo' en v1.8.0 no aparece intacto dentro de "
            "v1.9.0 — el credito parcial se tiene que AGREGAR, no reescribir lo "
            "que ya estaba."
        )

    def test_lo_que_no_hace_el_tutor_cambia_SOLO_en_el_dato_del_portapapeles(
        self,
    ) -> None:
        """Esta change no toca guardrails. La unica edicion en esta seccion es
        el DATO sobre copiar y pegar (sexto cambio), que quedo falso cuando
        `main` habilito el pegado interno.

        El test no se borro al agregar ese cambio: se acoto. Borrarlo habria
        dejado la seccion de guardrails sin ninguna red, que es exactamente lo
        que este archivo existe para evitar. Lo que se afirma ahora es que el
        delta esta CONTENIDO en el parrafo del portapapeles y que el resto de la
        seccion sigue byte a byte.
        """

        # Se normaliza antes de recortar: los marcadores de corte cruzan saltos
        # de linea en el archivo real, y un reflow cosmetico no tiene que romper
        # este test (mismo criterio que `_normalizado`).
        def _plano(s: str) -> str:
            return re.sub(r"\s+", " ", s).strip()

        nueva = _plano(_seccion(VERSION, "Lo que NO hace el tutor"))
        vieja = _plano(_seccion(PADRE, "Lo que NO hace el tutor"))

        INICIO = "**Y decile el dato"
        FIN_NUEVO = "Lo que esta bloqueado es la salida, no el reuso."
        FIN_VIEJO = "lo recomendaste."

        # Se recorta el parrafo del dato en cada version y se compara el
        # remanente: si cambio algo MAS, el remanente difiere y esto falla.
        cn, cv = nueva.index(INICIO), vieja.index(INICIO)
        fn = nueva.index(FIN_NUEVO) + len(FIN_NUEVO)
        fv = vieja.index(FIN_VIEJO) + len(FIN_VIEJO)

        resto_nuevo = nueva[:cn] + nueva[fn:]
        resto_viejo = vieja[:cv] + vieja[fv:]

        assert resto_nuevo == resto_viejo, (
            "la seccion de guardrails cambio en algo mas que el dato del portapapeles"
        )


class TestElManifestDeclaraElHashReal:
    def test_manifest_existe_y_declara_el_sha256_de_system_md(self) -> None:
        import hashlib

        version_dir = _ruta(VERSION).parent
        manifest = version_dir / "manifest.yaml"
        assert manifest.exists(), f"falta {manifest}"

        declared = re.search(r"system\.md:\s*([0-9a-f]{64})", manifest.read_text(encoding="utf-8"))
        assert declared is not None, "manifest.yaml no declara el sha256 de system.md"

        actual = hashlib.sha256(_ruta(VERSION).read_bytes()).hexdigest()
        assert actual == declared.group(1), (
            f"el contenido de {VERSION}/system.md no coincide con el hash "
            f"declarado.\n  declarado: {declared.group(1)}\n  actual:    {actual}\n"
            "Calcular el sha256 DESPUES del ultimo cambio al archivo."
        )


class TestElSextoCambioLaReglaDelPortapapeles:
    """El prompt deja de afirmar que copiar y pegar esta bloqueado, sin calificar.

    POR QUE ESTE CAMBIO EXISTE
    ----------------------------
    `main` habilito el pegado interno (commit 9a7206a, "copiar y pegar el propio
    codigo adentro del editor"). v1.8.0 decia DOS cosas sobre eso, y con ese
    cambio una queda falsa:

      1. "en esta plataforma copiar y pegar esta bloqueado" — la PREMISA quedo
         falsa (adentro del editor si se puede), aunque la conclusion que sacaba
         sigue siendo cierta: "copiatelo a VS Code" es inejecutable, porque el
         Ctrl+C del editor NO escribe en el portapapeles del sistema.
      2. "la plataforma no permite copiar y pegar en el editor" — esta es
         directamente falsa. El titulo del propio commit que la invalido dice
         "adentro del editor".

    Quien mergeo el cambio argumento que v1.8.0 seguia siendo verdadero, y tenia
    razon sobre la frase que cito (la 1, por la conclusion). Su argumento no
    cubre la frase 2.

    POR QUE NO ES PROLIJIDAD
    --------------------------
    Es el defecto que la v1.7.0 cerro con C5: el tutor afirmo una regla de la
    plataforma que estaba mal, el alumno lo contradijo, y el tutor cambio de
    postura sin corregirse. La regla que quedo fue "el tiene el dato y vos no".
    Un estudiante descubre que esta frase es falsa la primera vez que aprieta
    Ctrl+C adentro del editor, y desde ahi deja de creerle al resto.

    LO QUE SIGUE SIENDO VERDAD, Y NO SE DEBE DEBILITAR
    ----------------------------------------------------
    El codigo NO sale del editor: `portapapelesInternoRef` es una variable en
    memoria y el codigo de `CodeEditor.tsx` declara que no escribe al clipboard
    del SO. Asi que el consejo "llevatelo afuera" sigue siendo inejecutable, y
    pedirle al estudiante que pegue su codigo en el chat sigue siendo un
    callejon sin salida. Lo que cambia es el MOTIVO, no la conclusion.
    """

    def test_no_afirma_el_bloqueo_sin_calificar(self) -> None:
        texto = _normalizado("v1.9.0")

        # La forma ASERTIVA es la que quedo falsa, y es la que no puede volver.
        # No alcanza con buscar la cadena pelada: el prompt la menciona a
        # proposito, en una prohibicion ("No digas que copiar y pegar esta
        # bloqueado, sin calificar"), y un `not in` sobre la cadena suelta
        # prohibiria la instruccion que arregla el problema.
        assert "en esta plataforma **copiar y pegar esta bloqueado**" not in texto
        assert "no permite copiar y pegar en el editor" not in texto

    # Formas en las que la frase puede aparecer SIN afirmar la regla. No es una
    # lista para ir agrandando ante cada rojo: cada entrada es un verbo que
    # NIEGA o DESCRIBE la afirmacion en vez de hacerla. Si aparece una forma
    # nueva que no niega nada, el test tiene que ponerse rojo, no crecer.
    _NEGADORES = ("No digas", "Deja de afirmar", "no es que")

    def test_donde_menciona_el_bloqueo_es_para_negarlo(self) -> None:
        """Complemento del test anterior: la cadena SI aparece en el prompt, y
        cada aparicion tiene que estar NEGANDO la regla, nunca afirmandola.

        Sin esta mitad, el test de arriba pasaria con una redaccion afirmativa
        apenas distinta de la original — por ejemplo "aca copiar y pegar esta
        bloqueado", que esquiva el literal exacto y dice lo mismo.

        Este test ya se puso rojo una vez de verdad: al agregar el sexto cambio
        al changelog del header apareció "Deja de afirmar que copiar y pegar
        esta bloqueado", que es una descripcion del cambio y no la regla. Se
        agrego ese negador en vez de aflojar el test.
        """
        texto = _normalizado("v1.9.0")
        apariciones = list(re.finditer(r"copiar y pegar esta bloqueado", texto))
        assert apariciones, (
            "la frase no aparece en ninguna parte: este test quedo vacuo y el "
            "de arriba tambien pasaria sin medir nada"
        )
        for m in apariciones:
            contexto = texto[max(0, m.start() - 60) : m.start()]
            assert any(neg in contexto for neg in self._NEGADORES), (
                f"aparece afirmando la regla, en: ...{contexto}"
            )

    def test_dice_que_adentro_del_editor_SI_se_puede(self) -> None:
        texto = _normalizado("v1.9.0")
        # Anclado a la afirmacion COMPLETA, no a la frase suelta. "adentro del
        # editor" aparece en tres lugares distintos del prompt, asi que un
        # `in texto` sobre esa frase pasa aunque se borre justo el lugar donde
        # se afirma el permiso. Encontrado por mutacion: borrando "adentro" de
        # esta oracion, la version suelta de este test seguia en verde.
        assert "**SI puede copiar y pegar su propio codigo adentro del editor**" in texto

    def test_conserva_que_el_codigo_no_sale_del_editor(self) -> None:
        # El guardrail de v1.8.0 (C4: no mandarlo afuera) no se debilita: lo que
        # se corrige es el dato, no la politica.
        texto = _normalizado("v1.9.0")
        assert "no sale del editor" in texto
        assert "que no se puede ejecutar" in texto

    def test_v180_SI_tenia_las_dos_frases_falsas(self) -> None:
        # Guarda contra el modo de falla mas tonto de los tres tests de arriba:
        # si la normalizacion o la lectura se rompen y devuelven "", los
        # `not in` pasan sin haber mirado nada. Este test afirma que en v1.8.0
        # las frases SI estaban, asi que los `not in` de arriba miden un delta
        # real y no un archivo vacio.
        viejo = _normalizado("v1.8.0")
        assert "copiar y pegar esta bloqueado" in viejo
        assert "no permite copiar y pegar en el editor" in viejo
