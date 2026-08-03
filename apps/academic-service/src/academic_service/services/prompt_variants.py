"""Resolucion de la variante de prompt segun el lenguaje del ejercicio.

Los generadores por IA (`ejercicio_generator`, `tp_generator`) tienen un
documento propio por lenguaje, no un prompt unico con secciones condicionales
(decision D6 de la change `java-authoring-experience`). El motivo es que la
progresion de dificultad de cada lenguaje es distinta *en contenido*, no en
redaccion: la de Python va por estructuras de control (sin `if` en basica, sin
`for` hasta avanzada) y la de Java por construcciones del lenguaje (primitivos,
despues metodos y arreglos, despues clases y excepciones), porque en Java la
ceremonia de clase + `main` existe desde el primer ejercicio.

Convencion de nombres de familia:

    python (default) -> "ejercicio_generator"        <- NO cambia
    java             -> "ejercicio_generator_java"

El lenguaje por omision conserva el nombre historico a proposito: un docente que
genera en el lenguaje preexistente tiene que obtener exactamente el mismo prompt
que antes de esta change, sin migracion de archivos ni de manifest.

El `PromptLoader` del governance-service es generico en el nombre de familia y
no tiene whitelist, asi que agregar una variante es agregar un directorio y una
linea al manifest global — sin cambios de codigo en governance.
"""

from __future__ import annotations

from platform_contracts.academic.ejercicio import DEFAULT_LANGUAGE, Language


def resolve_prompt_name(base_name: str, language: str | None) -> str:
    """Devuelve el nombre de familia de prompt para `base_name` en `language`.

    Args:
        base_name: familia base, ej. `"ejercicio_generator"` o `"tp_generator"`.
        language: lenguaje pedido. `None` o vacio se trata como el default.

    Returns:
        `base_name` tal cual para el lenguaje por omision; `f"{base_name}_{language}"`
        para cualquier otro.

    El lenguaje NO se valida acá: el gate es el `Literal` de `Language` en los
    schemas de la API, que rechaza cualquier valor fuera del conjunto admitido
    antes de que la request llegue hasta este punto.
    """
    effective: Language | str = language or DEFAULT_LANGUAGE
    if effective == DEFAULT_LANGUAGE:
        return base_name
    return f"{base_name}_{effective}"
