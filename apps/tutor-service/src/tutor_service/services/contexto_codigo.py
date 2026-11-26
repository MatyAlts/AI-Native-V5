"""Código del editor dentro del turno del alumno (HU-042).

Hasta HU-042 el código actual del editor viajaba como un mensaje `system` más.
El ai-gateway junta todos los `system` al final de un `system_instruction` muy
largo y el modelo lo ignoraba: en producción (episodio 2e6315b9, 25/11/2026) el
tutor pidió "¿podrías mostrarme cómo quedaron definidas?" y después dijo "No
tengo acceso directo a tu editor", con el código ya en el contexto.

Ahora el código va dentro del ÚLTIMO mensaje `user` del payload, numerado por
línea, con una indicación explícita de que el tutor lo tiene. Ese texto se arma
SOLO para el payload de ese turno: `prompt_enviado.content` del CTR y
`state.messages` siguen guardando únicamente lo que escribió el alumno, así que
el código no se acumula en el historial ni cambia la traza.

El prompt del tutor (coautoría Ana Garis) no se toca: esto es contexto que arma
el código del tutor-service, igual que el resto de los bloques de `interact`.
"""

from __future__ import annotations


def numerar_codigo(codigo: str) -> str:
    """Cada línea precedida por su número (desde 1), alineado a 3 columnas."""
    return "\n".join(f"{i + 1:3d}  {linea}" for i, linea in enumerate(codigo.splitlines()))


def mensaje_con_codigo(texto_alumno: str, codigo: str | None) -> str:
    """Contenido del último mensaje `user` hacia el modelo.

    Sin código (o sólo espacios) devuelve el texto del alumno tal cual.
    """
    if not codigo or not codigo.strip():
        return texto_alumno
    return (
        "[Código que el alumno tiene ahora en su editor, con número de línea]\n"
        "Tenés este código a la vista en cada turno, y es siempre la versión más "
        "reciente. No le pidas que te lo copie, pegue, muestre o mande, y no "
        "digas que no lo ves ni que no tenés acceso a su editor. Referite a "
        "líneas concretas cuando ayude, sin darle la solución.\n"
        f"```\n{numerar_codigo(codigo)}\n```\n\n"
        "[Mensaje del alumno]\n"
        f"{texto_alumno}"
    )
