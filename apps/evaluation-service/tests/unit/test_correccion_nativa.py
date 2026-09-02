"""El corrector propio: la aritmética es nuestra y la rúbrica es la del docente.

QUÉ CUIDA ESTE ARCHIVO
----------------------
Una nota es una decisión sobre una persona. Las propiedades de acá no son
preferencias de diseño: son lo que hace que esa decisión sea revisable.

1. **El modelo no suma.** Devuelve puntajes por criterio; el total lo calcula
   Python. Con Active-IA ya pasó lo contrario —criterios que sumaban 61 y una
   nota que decía 87— y el frontend tuvo que crecerle un chequeo para avisarlo.
2. **Si el modelo no respeta la rúbrica, no hay nota.** Falta un criterio, sobra
   uno, o un puntaje se pasa del máximo → error, `nota_100 IS NULL`. Completar
   el hueco con un cero sería ponerle número a algo que nadie evaluó.
3. **Los casos ocultos no viajan al prompt.** Su `expected` es la solución.

Cada test se verificó por reversión DEGRADANDO la función —dejándola con la
misma firma pero sin la propiedad— y no borrándola. Un `ImportError` sólo prueba
que el archivo no compila; lo que hay que probar es que el test ve el
comportamiento malo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from evaluation_service.services.correccion_nativa import (
    RubricaInvalidaError,
    _casos_para_el_prompt,
    armar_mensaje_usuario,
    esquema_de_salida,
    leer_rubrica,
    nota_desde_criterios,
    parsear_respuesta,
)

# La rúbrica del ejemplo real (ficha del alumno, Programación I). Suma 10.
RUBRICA_CRUDA = [
    {
        "nombre": "Cuatro entradas correctas",
        "descripcion": "Pide los 4 datos en el orden indicado",
        "puntaje_max": 3,
    },
    {
        "nombre": "Uso de variables descriptivas",
        "descripcion": "Cada dato en una variable con nombre claro",
        "puntaje_max": 2,
    },
    {
        "nombre": "Salida con f-string",
        "descripcion": "Usa f-string para combinar las 4 en un print()",
        "puntaje_max": 3,
    },
    {
        "nombre": "Formato exacto",
        "descripcion": "Respeta espacios, comas y punto final",
        "puntaje_max": 2,
    },
]


def _puntajes(*valores: float) -> list[dict]:
    return [
        {"nombre": c["nombre"], "puntaje": v, "justificacion": "porque si"}
        for c, v in zip(RUBRICA_CRUDA, valores, strict=True)
    ]


class TestLaRubricaDelDocente:
    def test_lee_la_lista_pelada(self) -> None:
        criterios = leer_rubrica(RUBRICA_CRUDA)

        assert [c.nombre for c in criterios] == [c["nombre"] for c in RUBRICA_CRUDA]
        assert sum(c.puntaje_max for c in criterios) == Decimal(10)

    def test_lee_tambien_el_objeto_con_criterios(self) -> None:
        """Las dos formas existen en el JSONB. Cerrarse a una rompe ejercicios ya cargados."""
        criterios = leer_rubrica({"criterios": RUBRICA_CRUDA})

        assert len(criterios) == 4

    def test_sin_criterios_NO_corrige(self) -> None:
        """No es un fallo del sistema: es un ejercicio que no usa rúbrica."""
        for vacia in ([], None, {"criterios": []}):
            with pytest.raises(RubricaInvalidaError):
                leer_rubrica(vacia)

    def test_un_criterio_que_vale_cero_se_rechaza(self) -> None:
        """Un criterio en 0 no distingue nada y desbalancea la nota en silencio."""
        with pytest.raises(RubricaInvalidaError, match="mayor a 0"):
            leer_rubrica([{"nombre": "Decorativo", "puntaje_max": 0}])

    def test_dos_criterios_con_el_mismo_nombre_se_rechazan(self) -> None:
        """El nombre es lo que empareja el puntaje del modelo con la rúbrica."""
        with pytest.raises(RubricaInvalidaError, match="mismo nombre"):
            leer_rubrica(
                [
                    {"nombre": "Formato", "puntaje_max": 2},
                    {"nombre": "Formato", "puntaje_max": 3},
                ]
            )


class TestLaSumaEsNuestra:
    def test_la_nota_sale_de_los_criterios(self) -> None:
        rubrica = leer_rubrica(RUBRICA_CRUDA)

        nota, desglose = nota_desde_criterios(rubrica, _puntajes(3, 1, 3, 2))

        # 9 sobre 10 → 90,00. No hay lugar donde el modelo pueda decir otra cosa.
        assert nota == Decimal("90.00")
        assert [d["puntaje"] for d in desglose] == [3, 1, 3, 2]

    def test_todo_bien_da_cien(self) -> None:
        rubrica = leer_rubrica(RUBRICA_CRUDA)

        nota, _ = nota_desde_criterios(rubrica, _puntajes(3, 2, 3, 2))

        assert nota == Decimal("100.00")

    def test_el_cero_es_una_nota_legitima(self) -> None:
        """El template vacío, o el código que no compila. Cero NO es "sin nota":
        esa confusión ya causó un bucle de reintentos pagos con Active-IA."""
        rubrica = leer_rubrica(RUBRICA_CRUDA)

        nota, _ = nota_desde_criterios(rubrica, _puntajes(0, 0, 0, 0))

        assert nota == Decimal("0.00")

    def test_el_desglose_lleva_el_maximo_de_cada_criterio(self) -> None:
        """Sin el máximo al lado, un "1" en pantalla no dice si estuvo bien o mal."""
        rubrica = leer_rubrica(RUBRICA_CRUDA)

        _, desglose = nota_desde_criterios(rubrica, _puntajes(3, 1, 3, 2))

        assert [d["puntaje_max"] for d in desglose] == [3, 2, 3, 2]


class TestSiNoRespetaLaRubricaNoHayNota:
    def test_un_criterio_que_falta_NO_se_completa_con_cero(self) -> None:
        """Ponerle 0 a algo que nadie evaluó es peor que no corregir."""
        rubrica = leer_rubrica(RUBRICA_CRUDA)
        incompleto = _puntajes(3, 1, 3, 2)[:3]

        with pytest.raises(ValueError, match="no puntuó"):
            nota_desde_criterios(rubrica, incompleto)

    def test_un_criterio_inventado_se_rechaza(self) -> None:
        rubrica = leer_rubrica(RUBRICA_CRUDA)
        de_mas = [
            *_puntajes(3, 1, 3, 2),
            {"nombre": "Prolijidad general", "puntaje": 5, "justificacion": "..."},
        ]

        with pytest.raises(ValueError, match="inventó"):
            nota_desde_criterios(rubrica, de_mas)

    def test_un_puntaje_por_encima_del_maximo_se_rechaza(self) -> None:
        """Sin esto, un modelo generoso sube la nota por arriba de 100."""
        rubrica = leer_rubrica(RUBRICA_CRUDA)

        with pytest.raises(ValueError, match="máximo"):
            nota_desde_criterios(rubrica, _puntajes(3, 99, 3, 2))

    def test_un_puntaje_negativo_se_rechaza(self) -> None:
        rubrica = leer_rubrica(RUBRICA_CRUDA)

        with pytest.raises(ValueError):
            nota_desde_criterios(rubrica, _puntajes(3, -1, 3, 2))

    def test_un_puntaje_ilegible_se_rechaza(self) -> None:
        """Una nota que no se puede leer no es una nota."""
        rubrica = leer_rubrica(RUBRICA_CRUDA)
        roto = _puntajes(3, 1, 3, 2)
        roto[1]["puntaje"] = "muy bien"

        with pytest.raises(ValueError, match="no es un número"):
            nota_desde_criterios(rubrica, roto)


class TestElEsquemaNoDejaMandarLaNota:
    def test_el_esquema_no_admite_un_total(self) -> None:
        """Lo que el esquema no admite, el modelo no lo manda. Es la defensa
        de más barata que hay contra que la nota la calcule el modelo."""
        esquema = esquema_de_salida(leer_rubrica(RUBRICA_CRUDA))

        props = esquema["json_schema"]["schema"]["properties"]
        assert list(props) == ["criterios"]
        assert esquema["json_schema"]["schema"]["additionalProperties"] is False

    def test_los_nombres_van_como_enum(self) -> None:
        """Así el modelo no puede devolver «Formato Exacto» —una mayúscula de
        más— y quedar sin emparejar."""
        esquema = esquema_de_salida(leer_rubrica(RUBRICA_CRUDA))

        item = esquema["json_schema"]["schema"]["properties"]["criterios"]["items"]
        assert item["properties"]["nombre"]["enum"] == [c["nombre"] for c in RUBRICA_CRUDA]

    def test_exige_exactamente_los_criterios_de_la_rubrica(self) -> None:
        esquema = esquema_de_salida(leer_rubrica(RUBRICA_CRUDA))

        arr = esquema["json_schema"]["schema"]["properties"]["criterios"]
        assert arr["minItems"] == arr["maxItems"] == 4


class TestElPromptNoFiltraLaSolucion:
    """El fixture usa la forma que `_mapear` produce DE VERDAD.

    Antes usaba `name` / `is_public` / `passed` / `expected` / `got`, que son
    las claves del SANDBOX. Entre el sandbox y este módulo está `_mapear`, que
    las traduce a `nombre` / `es_publico` / `paso` / `salida_obtenida` — y lo
    que llega acá, vía `ResultadoTests.as_dict()`, es la forma traducida.

    Con las claves del sandbox, `_casos_para_el_prompt` devolvía `None` en
    todo y el test seguía verde: probaba que los ocultos no filtran sobre una
    forma que el sistema nunca produce.

    Las cadenas del fixture son deliberadamente ajenas al código y al enunciado
    (`SALIDA-PUBLICA-42`, `SOLUCION-SECRETA-99`). La versión anterior buscaba
    `"HOLA"`, que también estaba en `codigo="print('HOLA')"`: el assert pasaba
    por el bloque de código, no por el caso, así que la aserción positiva no
    probaba nada.
    """

    TESTS = {
        "compila": True,
        "total": 3,
        "passed": 2,
        "failed": 1,
        "error_compilacion": None,
        "casos": [
            {
                "id": "c1",
                "nombre": "CASO-PUBLICO-UNO",
                "paso": True,
                "salida_obtenida": "SALIDA-PUBLICA-42",
                "es_publico": True,
            },
            {
                "id": "c2",
                "nombre": "CASO-OCULTO-DOS",
                "paso": False,
                "salida_obtenida": "SALIDA-DEL-OCULTO-7",
                "es_publico": False,
                # `_mapear` NO emite esta clave: se pone acá a propósito, para
                # que el guard del oculto se ejercite contra un dato que existe
                # y no contra una ausencia. Sin esto, el test verifica que no
                # se filtre algo que nunca estuvo.
                "salida_esperada": "SOLUCION-SECRETA-99",
            },
        ],
    }

    def _mensaje(self) -> str:
        return armar_mensaje_usuario(
            enunciado="Pedí nombre y apellido.",
            rubrica=leer_rubrica(RUBRICA_CRUDA),
            tests=self.TESTS,
            codigo="print('HOLA')",
            prerequisitos={"sintacticos": ["input()"], "conceptuales": ["variable"]},
        )

    def test_el_esperado_de_un_caso_OCULTO_no_viaja(self) -> None:
        """Es la solución. Lo mismo que ya aplica al enunciado aplica acá."""
        assert "SOLUCION-SECRETA-99" not in self._mensaje()

    def test_el_nombre_de_cada_caso_SI_viaja(self) -> None:
        """Sin el nombre, el modelo no puede citar QUÉ caso falló al justificar
        un descuento — y la justificación es el producto de este corrector."""
        mensaje = self._mensaje()

        assert "CASO-PUBLICO-UNO" in mensaje
        assert "CASO-OCULTO-DOS" in mensaje

    def test_si_cada_caso_paso_o_no_SI_viaja(self) -> None:
        """La regla 4 del prompt le dice al modelo que los tests son HECHOS que
        mandan sobre su lectura del código. Si llegan vacíos, le estamos
        ordenando confiar en una evidencia que no está."""
        vistos = _casos_para_el_prompt(self.TESTS)

        assert [c["paso"] for c in vistos] == [True, False]

    def test_la_salida_REAL_del_alumno_viaja_en_los_dos(self) -> None:
        """Es su código, no el enunciado — mismo criterio explícito que
        `_mapear`, que la incluye para todos los casos. Es lo que el modelo
        necesita para justificar un descuento sobre un caso que falló."""
        mensaje = self._mensaje()

        assert "SALIDA-PUBLICA-42" in mensaje
        assert "SALIDA-DEL-OCULTO-7" in mensaje

    def test_van_los_prerequisitos(self) -> None:
        """Sin esta lista el modelo penaliza por lo que todavía no se enseñó."""
        mensaje = self._mensaje()

        assert "input()" in mensaje
        assert "NO exijas nada fuera de esta lista" in mensaje

    def test_van_los_resultados_de_los_tests(self) -> None:
        """Son hechos, y el prompt los rotula como tales."""
        mensaje = self._mensaje()

        assert "HECHOS" in mensaje
        assert '"fallaron": 1' in mensaje

    def test_el_codigo_va_al_final(self) -> None:
        """Primero qué se pidió y contra qué se mide; el código al final. Si va
        primero, el modelo arranca a opinar antes de saber contra qué."""
        mensaje = self._mensaje()

        assert mensaje.index("## Rúbrica") < mensaje.index("## Código que entregó")


class TestParseoTolerante:
    def test_json_pelado(self) -> None:
        crudo = '{"criterios": [{"nombre": "A", "puntaje": 1, "justificacion": "ok"}]}'

        assert parsear_respuesta(crudo)[0]["nombre"] == "A"

    def test_envuelto_en_backticks(self) -> None:
        """Algunos proveedores lo agregan aunque el response_format pida JSON puro
        — el mismo comportamiento que documenta `regimen_llm.py`."""
        crudo = (
            '```json\n{"criterios": [{"nombre": "A", "puntaje": 1, "justificacion": "ok"}]}\n```'
        )

        assert parsear_respuesta(crudo)[0]["puntaje"] == 1

    def test_una_respuesta_que_no_es_json_revienta(self) -> None:
        """Y revienta a propósito: el caller la traduce a error, sin nota."""
        with pytest.raises(Exception):  # JSONDecodeError o ValueError
            parsear_respuesta("Le pondría un 7 porque está bastante bien.")
