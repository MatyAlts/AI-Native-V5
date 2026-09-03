"""El gateway no puede prohibir una capacidad que el proveedor sí tiene.

`response_format` estaba declarado `dict[str, str]`, así que la salida
estructurada POR ESQUEMA —`{"type": "json_schema", "json_schema": {...}}`, con
un objeto anidado— se rechazaba con un 422 de Pydantic antes de tocar nada:

    "loc": ["body", "response_format", "json_schema"],
    "msg": "Input should be a valid string"

Y el gateway **no interpreta ese campo**: lo pasa tal cual al SDK del proveedor,
que entiende las dos formas. O sea que el tipo estrecho no protegía nada — sólo
prohibía, de este lado, algo que del otro lado ya funcionaba.

Nunca se había notado porque todos los llamadores mandaban `json_object` y nada
más. Lo destapó el corrector propio (2026-09-03), que pide un esquema con los
nombres de los criterios como `enum` para que el modelo no pueda devolver uno
que después no empareje con la rúbrica del docente.

Verificado por reversión volviendo el tipo a `dict[str, str]` y el `in (...)` a
la comparación con `json_object`: cada degradación pone en rojo su test.
"""

from __future__ import annotations

import pytest
from ai_gateway.providers.base import CompletionRequest
from ai_gateway.routes.complete import CompleteRequest
from pydantic import ValidationError

# La forma exacta que manda el corrector: un esquema anidado, con los nombres de
# los criterios como enum y SIN campo para la nota total.
ESQUEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "correccion_por_criterio",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["criterios"],
            "properties": {
                "criterios": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre": {"enum": ["Formato exacto"]},
                            "puntaje": {"type": "number", "minimum": 0},
                        },
                    },
                }
            },
        },
    },
}


class TestElEsquemaAnidadoPasa:
    def test_un_response_format_con_objeto_adentro_se_acepta(self) -> None:
        """El caso que devolvía 422. El anidado tiene que sobrevivir intacto."""
        req = CompleteRequest(
            messages=[{"role": "user", "content": "hola"}],
            model="google/gemini-2.5-flash-lite",
            feature="correccion",
            response_format=ESQUEMA,
        )

        assert req.response_format is not None
        # Intacto: el gateway no lo toca, lo reenvía. Si lo aplanara o le
        # comiera claves, el proveedor recibiría un esquema que no es el que
        # pidió el llamador.
        assert req.response_format == ESQUEMA
        enum = req.response_format["json_schema"]["schema"]["properties"]["criterios"]["items"][
            "properties"
        ]["nombre"]["enum"]
        assert enum == ["Formato exacto"]

    def test_el_json_object_de_siempre_sigue_andando(self) -> None:
        """La otra mitad: ensanchar el tipo no puede romper a los que ya estaban.

        Hoy lo mandan así el generador de TPs, el de ejercicios y el juez del
        eje fino del classifier."""
        req = CompleteRequest(
            messages=[{"role": "user", "content": "hola"}],
            model="gemini-2.5-flash",
            feature="tp_generator",
            response_format={"type": "json_object"},
        )

        assert req.response_format == {"type": "json_object"}

    def test_sin_response_format_sigue_siendo_valido(self) -> None:
        req = CompleteRequest(
            messages=[{"role": "user", "content": "hola"}],
            model="gemini-2.5-flash",
            feature="tutor",
        )

        assert req.response_format is None

    def test_lo_que_NO_es_un_objeto_se_sigue_rechazando(self) -> None:
        """Ensanchar no es abrir del todo: sigue teniendo que ser un dict."""
        with pytest.raises(ValidationError):
            CompleteRequest(
                messages=[{"role": "user", "content": "hola"}],
                model="gemini-2.5-flash",
                feature="tutor",
                response_format="json",  # type: ignore[arg-type]
            )


class TestElProveedorNativoDeGoogleNoLoIgnora:
    """El SDK nativo de Google no toma el esquema de OpenAI tal cual — usa
    `response_schema`, con otro dialecto. Lo que SÍ puede honrar es que la
    salida sea JSON, y antes ni eso: miraba sólo `json_object`, así que un
    `json_schema` se ignoraba **en silencio** y el modelo devolvía prosa.
    """

    @pytest.mark.parametrize("forma", ["json_object", "json_schema"])
    def test_las_dos_formas_piden_JSON(self, forma: str) -> None:
        import inspect

        from ai_gateway.providers import base

        fuente = inspect.getsource(base)
        # La condición tiene que cubrir las dos. Un `== "json_object"` pelado
        # deja la otra afuera sin decir nada.
        assert f'"{forma}",' in fuente or f'== "{forma}"' in fuente

    def test_la_condicion_cubre_las_dos_juntas(self) -> None:
        import inspect

        from ai_gateway.providers import base

        fuente = inspect.getsource(base)
        assert 'request.response_format.get("type") in (' in fuente, (
            "el proveedor nativo de Google volvio a mirar una sola forma: "
            "un json_schema se va a ignorar en silencio"
        )


class TestElContratoInternoAcompana:
    """Si la ruta acepta el anidado y el dataclass interno no, el problema se
    muda de lugar en vez de desaparecer.

    **Se chequea la ANOTACIÓN, no el runtime**, y eso es deliberado:
    `CompletionRequest` es un dataclass pelado, así que construirlo con un dict
    anidado funciona igual con la firma vieja — un test que sólo lo instancie
    pasa siempre y no prueba nada. Acá el que protege es mypy, y lo único
    verificable desde un test es que la firma diga lo que tiene que decir.
    """

    def test_la_firma_del_dataclass_admite_objetos_anidados(self) -> None:
        anotacion = str(CompletionRequest.__annotations__["response_format"])

        assert "dict[str, str]" not in anotacion, (
            "el dataclass del proveedor quedo con la firma estrecha: mypy va a "
            "rechazar el esquema anidado que la ruta ahora si acepta"
        )
        assert "Any" in anotacion

    def test_construirlo_con_el_esquema_anidado_anda(self) -> None:
        """Complemento, no reemplazo: confirma que el valor viaja intacto."""
        req = CompletionRequest(
            messages=[{"role": "user", "content": "hola"}],
            model="google/gemini-2.5-flash-lite",
            response_format=ESQUEMA,
        )

        assert req.response_format == ESQUEMA
