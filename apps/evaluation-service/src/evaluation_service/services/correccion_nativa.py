"""Corrector propio: la IA lee la consigna, la rúbrica y los tests, y puntúa.

POR QUÉ EXISTE
--------------
Hoy la corrección sale de Active-IA, y eso trae un problema que no es de
proveedor sino de correspondencia: **Active-IA corrige contra SU rúbrica, no
contra la del docente.** El propio panel lo advierte —"los criterios de
Active-IA van SOLOS, no cruzados con tu rúbrica local"— porque emparejarlos por
nombre pondría el puntaje de un criterio en otro. Y quedó registrado el caso de
una rúbrica que declaraba una reducción del 30 % y el motor devolvió la suma
limpia: 87 donde correspondía ~61.

Este corrector puntúa contra `Ejercicio.rubrica`, que es la que el docente
escribió y la que ve en pantalla.

NO REEMPLAZA A ACTIVE-IA. Es un segundo motor detrás del mismo contrato: la
misma forma de resultado, los mismos `error_code`, el mismo panel, el mismo PDF.
F15 no se toca.

LA REGLA QUE SOSTIENE TODO: EL MODELO NO CALCULA LA NOTA
--------------------------------------------------------
El modelo devuelve, por criterio, un puntaje y su porqué. **La suma la hace
`nota_desde_criterios()`, en Python.** Y no es purismo: con Active-IA ya pasó
que los criterios sumaban una cosa y la nota decía otra, y el frontend tuvo que
crecerle un chequeo (`utils/correccionIA.ts`) para avisarle al docente que no
cerraban.

Con la suma de este lado, ese desacuerdo **no puede ocurrir**. Es el mismo
criterio que `regimen_segun_regla()` en el classifier, y por el mismo motivo:
cuando la salida decide algo sobre una persona, la aritmética no se delega.

QUÉ PASA SI EL MODELO NO RESPETA LA RÚBRICA
-------------------------------------------
Falta un criterio, sobra uno, el nombre no coincide, o un puntaje se pasa del
máximo → **no hay nota**. Se cierra con `error_code` y `nota_100 IS NULL`, que
es la regla de oro del epic: un fallo nunca es una nota. Inventar el criterio
faltante en 0 sería peor que no corregir — le pone un número a algo que nadie
evaluó.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

log = structlog.get_logger()

PROMPT_NAME = "correccion"
PROMPT_VERSION = "v1.0.0"

# Cuánto se le permite al modelo. Un desglose de 4-8 criterios con
# justificaciones cortas entra holgado; el techo existe para que una respuesta
# desbocada no se lleve la cuota puesta.
MAX_TOKENS = 2000

# Temperatura cero: la misma corrección sobre el mismo código no debería dar dos
# notas distintas. No garantiza identidad bit-a-bit (el proveedor puede variar),
# pero es la condición mínima.
TEMPERATURE = 0.0


class RubricaInvalidaError(Exception):
    """La rúbrica del ejercicio no sirve para corregir. Es un rechazo, no un fallo."""


@dataclass(frozen=True)
class Criterio:
    nombre: str
    descripcion: str
    puntaje_max: Decimal


def leer_rubrica(rubrica: dict[str, Any] | list[Any] | None) -> list[Criterio]:
    """Los criterios de `Ejercicio.rubrica`, validados.

    Se aceptan las dos formas que el JSONB tiene hoy en la práctica: la lista
    pelada de criterios y el objeto con la clave `criterios`. Cerrarse a una
    sola rompería ejercicios ya cargados, y la forma no la fija ningún esquema.

    `puntaje_max > 0` es la regla del docente, no una validación de tipo: un
    criterio que suma cero no distingue nada y desbalancea la nota sin decirlo.

    Sin criterios NO es un error del sistema: es un ejercicio que no usa
    rúbrica, y ahí este corrector no tiene nada que hacer.
    """
    crudos = rubrica.get("criterios") if isinstance(rubrica, dict) else rubrica
    if not crudos:
        raise RubricaInvalidaError(
            "El ejercicio no tiene criterios cargados, así que no hay contra qué corregir. "
            "Cargá la rúbrica del ejercicio y volvé a disparar."
        )

    criterios: list[Criterio] = []
    for i, c in enumerate(crudos):
        if not isinstance(c, dict):
            raise RubricaInvalidaError(f"El criterio #{i + 1} de la rúbrica no es un objeto.")
        nombre = str(c.get("nombre") or c.get("criterio") or "").strip()
        if not nombre:
            raise RubricaInvalidaError(f"El criterio #{i + 1} de la rúbrica no tiene nombre.")
        try:
            maximo = Decimal(str(c.get("puntaje_max", c.get("puntaje", 0))))
        except Exception as e:  # cualquier basura cae acá igual
            raise RubricaInvalidaError(f"El puntaje máximo de «{nombre}» no es un número.") from e
        if maximo <= 0:
            raise RubricaInvalidaError(
                f"El criterio «{nombre}» tiene puntaje máximo {maximo}. Tiene que ser mayor a 0."
            )
        criterios.append(
            Criterio(
                nombre=nombre,
                descripcion=str(c.get("descripcion") or "").strip(),
                puntaje_max=maximo,
            )
        )

    nombres = [c.nombre for c in criterios]
    if len(set(nombres)) != len(nombres):
        raise RubricaInvalidaError(
            "Hay dos criterios con el mismo nombre. El nombre es lo que empareja el "
            "puntaje del modelo con la rúbrica, así que tienen que ser distintos."
        )
    return criterios


def nota_desde_criterios(
    rubrica: list[Criterio], puntuados: list[dict[str, Any]]
) -> tuple[Decimal, list[dict[str, Any]]]:
    """Suma el desglose y devuelve `(nota_100, desglose)`. La aritmética es NUESTRA.

    Valida que el modelo haya respetado la rúbrica antes de sumar nada:

    - un puntaje por criterio, emparejado por nombre exacto;
    - ninguno de más;
    - ninguno fuera de `[0, puntaje_max]`.

    Levanta `ValueError` ante cualquier desvío. El caller lo traduce a
    `error_code` y cierra sin nota — nunca completa el hueco con un cero.
    """
    por_nombre = {str(p.get("nombre") or "").strip(): p for p in puntuados}

    faltan = [c.nombre for c in rubrica if c.nombre not in por_nombre]
    if faltan:
        raise ValueError(f"El modelo no puntuó estos criterios: {faltan}")

    sobran = [n for n in por_nombre if n not in {c.nombre for c in rubrica}]
    if sobran:
        raise ValueError(f"El modelo inventó criterios que la rúbrica no tiene: {sobran}")

    desglose: list[dict[str, Any]] = []
    obtenido = Decimal(0)
    for c in rubrica:
        crudo = por_nombre[c.nombre].get("puntaje")
        try:
            puntaje = Decimal(str(crudo))
        except Exception as e:
            raise ValueError(f"El puntaje de «{c.nombre}» no es un número: {crudo!r}") from e
        if puntaje < 0 or puntaje > c.puntaje_max:
            raise ValueError(
                f"El puntaje de «{c.nombre}» es {puntaje} y el máximo es {c.puntaje_max}."
            )
        obtenido += puntaje
        desglose.append(
            {
                "nombre": c.nombre,
                "puntaje": float(puntaje),
                "puntaje_max": float(c.puntaje_max),
                "justificacion": str(por_nombre[c.nombre].get("justificacion") or "").strip(),
            }
        )

    total_max = sum((c.puntaje_max for c in rubrica), Decimal(0))
    nota = (obtenido / total_max * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return nota, desglose


def esquema_de_salida(rubrica: list[Criterio]) -> dict[str, Any]:
    """El JSON Schema que se le pasa al gateway como `response_format`.

    Los nombres van como `enum`: así el modelo no puede devolver un criterio con
    el nombre apenas distinto —una tilde, una mayúscula— que despues no
    empareja. Es la clase de error que el emparejado por nombre no perdona.

    Y NO hay campo para la nota final, a propósito: lo que el esquema no admite,
    el modelo no lo manda.
    """
    return {
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
                        "minItems": len(rubrica),
                        "maxItems": len(rubrica),
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["nombre", "puntaje", "justificacion"],
                            "properties": {
                                "nombre": {"enum": [c.nombre for c in rubrica]},
                                "puntaje": {"type": "number", "minimum": 0},
                                "justificacion": {"type": "string"},
                            },
                        },
                    }
                },
            },
        },
    }


def _casos_para_el_prompt(tests: dict[str, Any]) -> list[dict[str, Any]]:
    """Los casos, SIN la salida esperada de los ocultos.

    Lo mismo que ya aplica al enunciado aplica acá: un caso oculto revela la
    solución. El modelo ve que existe, cómo le fue, y nada más.
    """
    limpios = []
    for caso in tests.get("casos") or []:
        if not isinstance(caso, dict):
            continue
        publico = bool(caso.get("is_public"))
        limpios.append(
            {
                "name": caso.get("name"),
                "publico": publico,
                "paso": caso.get("passed"),
                **({"esperado": caso.get("expected")} if publico else {}),
                **({"obtenido": caso.get("got")} if publico else {}),
            }
        )
    return limpios


def armar_mensaje_usuario(
    *,
    enunciado: str,
    rubrica: list[Criterio],
    tests: dict[str, Any],
    codigo: str,
    prerequisitos: dict[str, Any] | None,
) -> str:
    """Todo el contexto en un solo mensaje, rotulado.

    El orden no es casual: primero qué se pidió, después con qué se mide, después
    los hechos, y al final el código. El código va último porque es lo que el
    modelo tiene que juzgar contra todo lo anterior — si va primero, arranca a
    opinar antes de saber contra qué.
    """
    prereq = prerequisitos or {}
    partes = [
        "## Enunciado del ejercicio",
        enunciado.strip() or "(sin enunciado cargado)",
        "",
        "## Rúbrica — puntuá EXACTAMENTE estos criterios",
        json.dumps(
            [
                {
                    "nombre": c.nombre,
                    "descripcion": c.descripcion,
                    "puntaje_max": float(c.puntaje_max),
                }
                for c in rubrica
            ],
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "## Qué se enseñó hasta acá — NO exijas nada fuera de esta lista",
        json.dumps(
            {
                "sintacticos": prereq.get("sintacticos") or [],
                "conceptuales": prereq.get("conceptuales") or [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "## Resultado de correr los tests — esto son HECHOS",
        json.dumps(
            {
                "compila": tests.get("compila"),
                "total": tests.get("total"),
                "pasaron": tests.get("passed"),
                "fallaron": tests.get("failed"),
                "error_compilacion": tests.get("error_compilacion"),
                "casos": _casos_para_el_prompt(tests),
            },
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "## Código que entregó el alumno",
        "```",
        codigo,
        "```",
    ]
    return "\n".join(partes)


def parsear_respuesta(content: str) -> list[dict[str, Any]]:
    """Saca la lista de criterios del texto del modelo.

    Se tolera el envoltorio en backticks porque algunos proveedores lo agregan
    aunque el `response_format` pida JSON puro — el mismo comportamiento que ya
    documenta `regimen_llm.py` del classifier.
    """
    txt = content.strip()
    if txt.startswith("```"):
        txt = txt.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if txt.startswith("json"):
            txt = txt[4:].strip()
    datos = json.loads(txt)
    criterios = datos.get("criterios") if isinstance(datos, dict) else datos
    if not isinstance(criterios, list):
        raise ValueError("La respuesta del modelo no trae una lista de criterios.")
    return criterios
