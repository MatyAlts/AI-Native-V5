"""Trazas sintéticas de Alberto para los few-shot del juez v2.

Episodios INVENTADOS (no vienen de ningún alumno) en el formato de la traza
ciega `traza_v1` (`traza_ciega.filtrar_traza`). Su clave consensuada es
s-7f3a = pasiva, s-2c9e = superficial y s-b41d = reflexiva. Cambiar este
archivo mueve `HUELLA_PROMPT_V2`: es parte del prompt congelado.
"""

from __future__ import annotations

from typing import Any

SINTETICOS_ALBERTO: dict[str, dict[str, Any]] = {
    "s-7f3a": {
        "enunciado": "Ejercicio 9 – Escala de Richter. Pedí la magnitud de un terremoto y "
        "mostrá su categoría: menos de 3, «Muy leve»; menos de 4, «Leve»; menos "
        "de 5, «Moderado»; menos de 6, «Fuerte»; menos de 7, «Mayor»; 7 o más, "
        "«Gran terremoto». Usá if-elif.",
        "elementos": [
            {"n": 1, "tipo": "inicio", "k": None, "t_seg": 20, "datos": {"language": "python"}},
            {
                "n": 2,
                "tipo": "mensaje_alumno",
                "k": 1,
                "t_seg": 40,
                "datos": {"content": "hacé el ejercicio 9"},
            },
            {
                "n": 3,
                "tipo": "respuesta_tutor",
                "k": 1,
                "t_seg": 60,
                "datos": {
                    "content": "Lo armamos juntos. Para empezar: ¿qué dato "
                    "necesita el programa que le dé el usuario?"
                },
            },
            {
                "n": 4,
                "tipo": "mensaje_alumno",
                "k": 2,
                "t_seg": 80,
                "datos": {"content": "no se pasame el codigo"},
            },
            {
                "n": 5,
                "tipo": "respuesta_tutor",
                "k": 2,
                "t_seg": 100,
                "datos": {
                    "content": "No te voy a dar el código, pero vamos de a un "
                    "paso. ¿Con qué función de Python le pedimos un "
                    "dato al usuario?"
                },
            },
            {"n": 6, "tipo": "mensaje_alumno", "k": 3, "t_seg": 120, "datos": {"content": "cual"}},
            {
                "n": 7,
                "tipo": "respuesta_tutor",
                "k": 3,
                "t_seg": 140,
                "datos": {
                    "content": "Con input(). ¿Cómo guardarías en una variable lo "
                    "que escribe el usuario?"
                },
            },
            {
                "n": 8,
                "tipo": "mensaje_alumno",
                "k": 4,
                "t_seg": 160,
                "datos": {"content": "pasame el codigo completo porfa"},
            },
            {
                "n": 9,
                "tipo": "respuesta_tutor",
                "k": 4,
                "t_seg": 180,
                "datos": {
                    "content": "Entiendo que querés avanzar rápido. Probá "
                    "escribir solo la primera línea y te ayudo con la "
                    "siguiente."
                },
            },
            {
                "n": 10,
                "tipo": "pegado",
                "k": None,
                "t_seg": 200,
                "datos": {"contenido_longitud": 312, "metodo": "teclado"},
            },
            {
                "n": 11,
                "tipo": "codigo",
                "k": 1,
                "t_seg": 220,
                "datos": {
                    "snapshot": 'm = input("Magnitud: ")\nif m < 3:\n    print("Muy leve")',
                    "language": "python",
                },
            },
            {
                "n": 12,
                "tipo": "ejecucion",
                "k": 1,
                "t_seg": 240,
                "datos": {
                    "code": 'm = input("Magnitud: ")\nif m < 3:\n    print("Muy leve")',
                    "stdout": "",
                    "stderr": "TypeError: '<' not supported between instances of 'str' and 'int'",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 13,
                "tipo": "mensaje_alumno",
                "k": 5,
                "t_seg": 260,
                "datos": {
                    "content": "TypeError: '<' not supported between instances of 'str' and 'int'"
                },
            },
            {
                "n": 14,
                "tipo": "respuesta_tutor",
                "k": 5,
                "t_seg": 280,
                "datos": {
                    "content": "El error compara dos tipos distintos. ¿Qué tipo "
                    "de dato crees que devuelve input()?"
                },
            },
            {
                "n": 15,
                "tipo": "mensaje_alumno",
                "k": 6,
                "t_seg": 300,
                "datos": {"content": "no se"},
            },
            {"n": 16, "tipo": "fin_abandonado", "k": None, "t_seg": 320, "datos": {}},
        ],
    },
    "s-2c9e": {
        "enunciado": "Ejercicio 9 – Escala de Richter. Pedí la magnitud de un terremoto y "
        "mostrá su categoría: menos de 3, «Muy leve»; menos de 4, «Leve»; menos "
        "de 5, «Moderado»; menos de 6, «Fuerte»; menos de 7, «Mayor»; 7 o más, "
        "«Gran terremoto». Usá if-elif.",
        "elementos": [
            {"n": 1, "tipo": "inicio", "k": None, "t_seg": 20, "datos": {"language": "python"}},
            {
                "n": 2,
                "tipo": "mensaje_alumno",
                "k": 1,
                "t_seg": 40,
                "datos": {"content": "¿cómo convierto lo que ingresa el usuario a número?"},
            },
            {
                "n": 3,
                "tipo": "respuesta_tutor",
                "k": 1,
                "t_seg": 60,
                "datos": {
                    "content": "¿Qué tipos numéricos conocés en Python? ¿La "
                    "magnitud de un terremoto puede tener decimales?"
                },
            },
            {
                "n": 4,
                "tipo": "mensaje_alumno",
                "k": 2,
                "t_seg": 80,
                "datos": {"content": "sí, float"},
            },
            {
                "n": 5,
                "tipo": "respuesta_tutor",
                "k": 2,
                "t_seg": 100,
                "datos": {"content": "Bien. ¿En qué parte del código lo aplicarías?"},
            },
            {
                "n": 6,
                "tipo": "codigo",
                "k": 1,
                "t_seg": 120,
                "datos": {
                    "snapshot": 'magnitud = float(input("Magnitud: "))\n'
                    "if magnitud < 3:\n"
                    '    print("Muy leve")\n'
                    "if magnitud < 4:\n"
                    '    print("Leve")\n'
                    "if magnitud < 5:\n"
                    '    print("Moderado")\n'
                    "if magnitud < 6:\n"
                    '    print("Fuerte")\n'
                    "if magnitud < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "language": "python",
                },
            },
            {
                "n": 7,
                "tipo": "ejecucion",
                "k": 1,
                "t_seg": 140,
                "datos": {
                    "code": 'magnitud = float(input("Magnitud: "))\n'
                    "if magnitud < 3:\n"
                    '    print("Muy leve")\n'
                    "if magnitud < 4:\n"
                    '    print("Leve")\n'
                    "if magnitud < 5:\n"
                    '    print("Moderado")\n'
                    "if magnitud < 6:\n"
                    '    print("Fuerte")\n'
                    "if magnitud < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "stdout": "Magnitud: 2\nMuy leve\nLeve\nModerado\nFuerte\nMayor",
                    "stderr": "",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 8,
                "tipo": "mensaje_alumno",
                "k": 3,
                "t_seg": 160,
                "datos": {"content": "me imprime todas las categorías, ¿cómo lo arreglo?"},
            },
            {
                "n": 9,
                "tipo": "respuesta_tutor",
                "k": 3,
                "t_seg": 180,
                "datos": {
                    "content": "¿Qué diferencia hay entre escribir varios if "
                    "seguidos y usar if-elif?"
                },
            },
            {
                "n": 10,
                "tipo": "mensaje_alumno",
                "k": 4,
                "t_seg": 200,
                "datos": {"content": "ok, lo cambio por elif"},
            },
            {
                "n": 11,
                "tipo": "codigo",
                "k": 2,
                "t_seg": 220,
                "datos": {
                    "snapshot": 'magnitud = float(input("Magnitud: "))\n'
                    "if magnitud < 3:\n"
                    '    print("Muy leve")\n'
                    "elif magnitud < 4:\n"
                    '    print("Leve")\n'
                    "elif magnitud < 5:\n"
                    '    print("Moderado")\n'
                    "elif magnitud < 6:\n"
                    '    print("Fuerte")\n'
                    "elif magnitud < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "language": "python",
                },
            },
            {
                "n": 12,
                "tipo": "ejecucion",
                "k": 2,
                "t_seg": 240,
                "datos": {
                    "code": 'magnitud = float(input("Magnitud: "))\n'
                    "if magnitud < 3:\n"
                    '    print("Muy leve")\n'
                    "elif magnitud < 4:\n"
                    '    print("Leve")\n'
                    "elif magnitud < 5:\n"
                    '    print("Moderado")\n'
                    "elif magnitud < 6:\n"
                    '    print("Fuerte")\n'
                    "elif magnitud < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "stdout": "Magnitud: 2\nMuy leve",
                    "stderr": "",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 13,
                "tipo": "mensaje_alumno",
                "k": 5,
                "t_seg": 260,
                "datos": {"content": "listo, ¿así está bien?"},
            },
            {
                "n": 14,
                "tipo": "respuesta_tutor",
                "k": 5,
                "t_seg": 280,
                "datos": {
                    "content": "¿Cómo podrías comprobarlo? Por ejemplo, ¿qué debería salir con 7?"
                },
            },
            {
                "n": 15,
                "tipo": "ejecucion",
                "k": 3,
                "t_seg": 300,
                "datos": {
                    "code": 'magnitud = float(input("Magnitud: "))\n'
                    "if magnitud < 3:\n"
                    '    print("Muy leve")\n'
                    "elif magnitud < 4:\n"
                    '    print("Leve")\n'
                    "elif magnitud < 5:\n"
                    '    print("Moderado")\n'
                    "elif magnitud < 6:\n"
                    '    print("Fuerte")\n'
                    "elif magnitud < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "stdout": "Magnitud: 7\nGran terremoto",
                    "stderr": "",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 16,
                "tipo": "mensaje_alumno",
                "k": 6,
                "t_seg": 320,
                "datos": {"content": "sí, anda. gracias"},
            },
            {"n": 17, "tipo": "fin_cerrado", "k": None, "t_seg": 340, "datos": {}},
        ],
    },
    "s-b41d": {
        "enunciado": "Ejercicio 9 – Escala de Richter. Pedí la magnitud de un terremoto y "
        "mostrá su categoría: menos de 3, «Muy leve»; menos de 4, «Leve»; menos "
        "de 5, «Moderado»; menos de 6, «Fuerte»; menos de 7, «Mayor»; 7 o más, "
        "«Gran terremoto». Usá if-elif.",
        "elementos": [
            {"n": 1, "tipo": "inicio", "k": None, "t_seg": 20, "datos": {"language": "python"}},
            {
                "n": 2,
                "tipo": "mensaje_alumno",
                "k": 1,
                "t_seg": 40,
                "datos": {
                    "content": "Pensé usar int(input()) porque las categorías van "
                    "de número entero en número entero. ¿Tiene sentido "
                    "o conviene float?"
                },
            },
            {
                "n": 3,
                "tipo": "respuesta_tutor",
                "k": 1,
                "t_seg": 60,
                "datos": {"content": "¿Qué crees que pasaría si el usuario ingresa 4.7?"},
            },
            {
                "n": 4,
                "tipo": "mensaje_alumno",
                "k": 2,
                "t_seg": 80,
                "datos": {
                    "content": "Supongo que lo trunca a 4 y lo clasifica igual "
                    "como Moderado. Lo pruebo."
                },
            },
            {
                "n": 5,
                "tipo": "codigo",
                "k": 1,
                "t_seg": 100,
                "datos": {"snapshot": 'm = int(input("Magnitud: "))', "language": "python"},
            },
            {
                "n": 6,
                "tipo": "ejecucion",
                "k": 1,
                "t_seg": 120,
                "datos": {
                    "code": 'm = int(input("Magnitud: "))',
                    "stdout": "Magnitud: 4.7",
                    "stderr": "ValueError: invalid literal for int() with base 10: '4.7'",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 7,
                "tipo": "mensaje_alumno",
                "k": 3,
                "t_seg": 140,
                "datos": {
                    "content": "Ah, no llega a truncar: int() no acepta un texto "
                    "con punto decimal y falla antes. Entonces uso "
                    "float, porque la magnitud es un número real."
                },
            },
            {
                "n": 8,
                "tipo": "respuesta_tutor",
                "k": 3,
                "t_seg": 160,
                "datos": {"content": "Buena observación. ¿Cómo vas a ordenar las condiciones?"},
            },
            {
                "n": 9,
                "tipo": "mensaje_alumno",
                "k": 4,
                "t_seg": 180,
                "datos": {
                    "content": "De menor a mayor con elif, así cada condición "
                    "solo necesita el límite de arriba. Si las "
                    "ordenara de mayor a menor tendría que usar >= en "
                    "todas."
                },
            },
            {
                "n": 10,
                "tipo": "codigo",
                "k": 2,
                "t_seg": 200,
                "datos": {
                    "snapshot": 'm = float(input("Magnitud: "))\n'
                    "if m < 3:\n"
                    '    print("Muy leve")\n'
                    "elif m < 4:\n"
                    '    print("Leve")\n'
                    "elif m < 5:\n"
                    '    print("Moderado")\n'
                    "elif m < 6:\n"
                    '    print("Fuerte")\n'
                    "elif m < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "language": "python",
                },
            },
            {
                "n": 11,
                "tipo": "ejecucion",
                "k": 2,
                "t_seg": 220,
                "datos": {
                    "code": 'm = float(input("Magnitud: "))\n'
                    "if m < 3:\n"
                    '    print("Muy leve")\n'
                    "elif m < 4:\n"
                    '    print("Leve")\n'
                    "elif m < 5:\n"
                    '    print("Moderado")\n'
                    "elif m < 6:\n"
                    '    print("Fuerte")\n'
                    "elif m < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "stdout": "Magnitud: 3\nLeve",
                    "stderr": "",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 12,
                "tipo": "mensaje_alumno",
                "k": 5,
                "t_seg": 240,
                "datos": {
                    "content": "Probé el borde: con 3 esperaba «Leve», porque 3 < "
                    "3 es falso y pasa a la siguiente condición. Dio "
                    "bien. ¿Hay algún otro borde que debería "
                    "revisar?"
                },
            },
            {
                "n": 13,
                "tipo": "respuesta_tutor",
                "k": 5,
                "t_seg": 260,
                "datos": {"content": "¿Qué otros valores separan categorías?"},
            },
            {
                "n": 14,
                "tipo": "ejecucion",
                "k": 3,
                "t_seg": 280,
                "datos": {
                    "code": 'm = float(input("Magnitud: "))\n'
                    "if m < 3:\n"
                    '    print("Muy leve")\n'
                    "elif m < 4:\n"
                    '    print("Leve")\n'
                    "elif m < 5:\n"
                    '    print("Moderado")\n'
                    "elif m < 6:\n"
                    '    print("Fuerte")\n'
                    "elif m < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "stdout": "Magnitud: 7\nGran terremoto",
                    "stderr": "",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 15,
                "tipo": "ejecucion",
                "k": 4,
                "t_seg": 300,
                "datos": {
                    "code": 'm = float(input("Magnitud: "))\n'
                    "if m < 3:\n"
                    '    print("Muy leve")\n'
                    "elif m < 4:\n"
                    '    print("Leve")\n'
                    "elif m < 5:\n"
                    '    print("Moderado")\n'
                    "elif m < 6:\n"
                    '    print("Fuerte")\n'
                    "elif m < 7:\n"
                    '    print("Mayor")\n'
                    "else:\n"
                    '    print("Gran terremoto")',
                    "stdout": "Magnitud: -1\nMuy leve",
                    "stderr": "",
                    "passed": None,
                    "failed": None,
                    "total": None,
                    "failed_test_names": None,
                },
            },
            {
                "n": 16,
                "tipo": "mensaje_alumno",
                "k": 6,
                "t_seg": 320,
                "datos": {
                    "content": "Con −1 me dice «Muy leve», pero una magnitud "
                    "negativa no tiene sentido para el ejercicio. "
                    "¿Debería validarla o la consigna no lo pide?"
                },
            },
            {"n": 17, "tipo": "fin_cerrado", "k": None, "t_seg": 340, "datos": {}},
        ],
    },
}
