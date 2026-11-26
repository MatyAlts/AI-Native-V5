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
# 1.1.0 (25/11/2026, HU-042): suma la referencia breve de cómo se comporta el
#   intérprete de la plataforma (Escribir, Leer, `/`, `+` con textos), tomada
#   de `packages/pseint/PERFIL.md`. En producción el tutor afirmó que las comas
#   de `Escribir` separan con espacio, y es falso.
CONTEXTO_PSEINT_VERSION = "1.1.0"

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

# HU-042 C02: hechos del intérprete de la plataforma (perfil 20250314, ver
# `packages/pseint/PERFIL.md`). Cada hecho va en su propia línea.
REFERENCIA_LENGUAJE_PSEINT = (
    "\n\n[Cómo se comporta PSeInt en esta plataforma]\n"
    "Si tenés dudas de cómo se comporta algo, guiate por esto y no por otro "
    "lenguaje:\n"
    "- `Escribir a, b` escribe los valores pegados, sin espacios ni separador "
    "entre ellos: para separarlos hay que escribir el espacio a mano "
    '(`Escribir a, " ", b`). Al final salta de línea, salvo con `Sin Saltar`.\n'
    "- `Leer` toma un valor por línea; `Leer a, b` pide dos datos.\n"
    "- `/` siempre divide con decimales (`7/2` da 3.5); para la división entera "
    "se usa `trunc(a/b)` y el resto es `MOD`.\n"
    '- `+` también concatena textos, pero mezclar texto y número (`"a" + 1`) '
    "es un error."
)


def contexto_pseint(language: object) -> str:
    """Devuelve la guía si el lenguaje es PSeInt; si no, cadena vacía."""
    if language != LENGUAJE_PSEINT:
        return ""
    return CONTEXTO_PSEINT + REFERENCIA_LENGUAJE_PSEINT
