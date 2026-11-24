"""Guía del tutor para ejercicios en PSeInt (HU-034).

El prompt del tutor no se toca (coautoría Ana Garis, intacto byte a byte): esta
guía se suma al CONTEXTO del ejercicio que arma
`TutorCore._build_ejercicio_context`, igual que `tutor_rules` o el banco
socrático (ADR-048), y sólo cuando el ejercicio o la TP declaran
`language == "pseint"`. Para cualquier otro lenguaje el contexto queda idéntico.

Versión de la guía: `CONTEXTO_PSEINT_VERSION`. Cualquier cambio del texto sube
la versión (semver) para que quede trazable; el LLM no la ve.
"""

from __future__ import annotations

# 1.0.0 (24/11/2026, HU-034): primera versión de la guía.
CONTEXTO_PSEINT_VERSION = "1.0.0"

LENGUAJE_PSEINT = "pseint"

CONTEXTO_PSEINT = (
    "\n\n[Lenguaje del ejercicio: PSeInt]\n"
    "El estudiante escribe pseudocódigo en PSeInt (perfil oficial 20250314) y "
    "muchas veces es su primer contacto con la programación. Explicá con "
    "palabras simples y con el vocabulario de PSeInt: Algoritmo, "
    "Definir … Como, Leer, Escribir, Si … Entonces / SiNo, Segun, "
    "Mientras … Hacer, Repetir … Hasta Que, Para … Hasta … Con Paso, "
    "Funcion, SubProceso.\n"
    "- Cuando muestres sintaxis o un ejemplo mínimo que no resuelva el "
    "ejercicio, usá siempre sintaxis de PSeInt; nunca la de Python ni la de "
    "otro lenguaje.\n"
    "- Reglas del perfil que más confunden: la asignación es con `<-` "
    "(`=` compara); los arreglos se crean con `Dimension` y empiezan en 1; "
    "`Y`, `O` y `NO` son operadores y no pueden ser nombres de variable; el "
    "nombre del Algoritmo no puede repetirse en una variable; un `Para` con "
    "inicio mayor que el fin cuenta hacia atrás.\n"
    "- Herramientas que el estudiante tiene en la plataforma: el botón "
    '"Paso a paso" hace la prueba de escritorio (muestra el valor de cada '
    'variable en cada paso), la pestaña "Diagrama" dibuja el diagrama de flujo '
    "de su código y los mensajes de error dicen la línea. Invitalo a usarlas "
    "antes de darle pistas.\n"
    "- Seguís siendo socrático: preguntas antes que respuestas."
)


def contexto_pseint(language: object) -> str:
    """Devuelve la guía si el lenguaje es PSeInt; si no, cadena vacía."""
    return CONTEXTO_PSEINT if language == LENGUAJE_PSEINT else ""
