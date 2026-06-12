#!/usr/bin/env python3
"""Seed del banco de ejercicios — Practico 6: Funciones en Python (UTN Prog I).

Crea 10 ejercicios reusables en el banco (tabla `ejercicios`) via la API del
api-gateway. Idempotente: si ya existe un ejercicio con el mismo titulo en la
materia, lo saltea. Pensado para correr contra prod con los headers X-* del
docente (mientras dev_trust_headers siga activo en el gateway).

Requiere que el enum `unidad_tematica` acepte 'funciones' (migracion
20260604_0001 + contrato). Si el primer POST falla con 422/500, aborta y avisa
que falta aplicar la migracion (redeploy del academic-service).

Uso:
    python3 scripts/seed_ejercicios_p6_funciones.py

Config por env vars (con defaults de prod):
    API_BASE, TENANT_ID, USER_ID, USER_EMAIL, MATERIA_ID
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_BASE = os.environ.get(
    "API_BASE",
    "https://api.ai-native-tutor-socratico-api-gateway.3xzl86.easypanel.host",
)
TENANT_ID = os.environ.get("TENANT_ID", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ID = os.environ.get("USER_ID", "11111111-1111-1111-1111-111111111111")
USER_EMAIL = os.environ.get("USER_EMAIL", "docente01@demo-uni.edu")
MATERIA_ID = os.environ.get("MATERIA_ID", "461e7bcc-79a4-4f12-96dd-c9a2834a0548")

HEADERS = {
    "Content-Type": "application/json",
    "X-Tenant-Id": TENANT_ID,
    "X-User-Id": USER_ID,
    "X-User-Email": USER_EMAIL,
    "X-User-Roles": "docente",
}

# ── Los 10 ejercicios del Practico 6 (contenido aprobado E1-E10) ──────────────
EJERCICIOS: list[dict] = [
    {
        "titulo": "E1 - Hola Mundo con función",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `imprimir_hola_mundo()` que imprima por "
            "pantalla el mensaje `Hola Mundo!`. Después, desde el **programa "
            "principal**, llamá a la función para que el mensaje aparezca.\n\n"
            "### La función\n"
            "- **Nombre:** `imprimir_hola_mundo`\n"
            "- **Parámetros:** ninguno\n"
            "- **Qué hace:** imprime `Hola Mundo!` por pantalla (no devuelve nada, usa `print`)\n\n"
            "### Requisitos\n"
            "- Definí la función con `def`.\n"
            "- La función no recibe parámetros ni usa `return`: solo imprime.\n"
            "- Llamá a la función desde el programa principal (si no la llamás, no se ejecuta nada).\n"
            "- El mensaje tiene que ser exactamente `Hola Mundo!` (con `H` y `M` mayúsculas y el signo `!`).\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nHola Mundo!\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 1 - Hola Mundo con función\n\n"
            "# 1) Definí la función imprimir_hola_mundo() con def (sin parámetros)\n"
            "# 2) Adentro (indentado), usá print() para mostrar el mensaje exacto\n"
            "def imprimir_hola_mundo():\n"
            "    pass  # reemplazá esta línea por el print\n\n"
            "# 3) Llamá a la función desde el programa principal\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "basica",
        "test_cases": [
            {"id": "tc1", "name": "Imprime el mensaje exacto", "type": "stdin_stdout", "code": "", "expected": "Hola Mundo!", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Sin texto extra ni lineas de mas", "type": "stdin_stdout", "code": "", "expected": "Hola Mundo!", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Capitalizacion y signo exactos", "type": "stdin_stdout", "code": "", "expected": "Hola Mundo!", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con def", "descripcion": "Define la funcion con def y el nombre exacto imprimir_hola_mundo", "puntaje_max": "2"},
            {"nombre": "Indentacion del cuerpo", "descripcion": "El cuerpo de la funcion esta correctamente indentado dentro del def", "puntaje_max": "1"},
            {"nombre": "Mensaje exacto con print", "descripcion": "Usa print con el texto exacto 'Hola Mundo!' (mayusculas y signo incluidos)", "puntaje_max": "3"},
            {"nombre": "Llamado desde el principal", "descripcion": "Invoca la funcion desde el programa principal para que se ejecute", "puntaje_max": "3"},
            {"nombre": "Uso correcto de print vs return", "descripcion": "Usa print para mostrar en pantalla y no return", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def", "print()", "dos puntos (:) al definir", "indentacion", "llamado a funcion nombre()"],
            "conceptuales": ["definicion vs. llamada de funcion", "funcion sin parametros", "diferencia entre imprimir y devolver", "modularidad", "indentacion como bloque"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno define la funcion pero no ve ninguna salida, NO le digas 'te falta llamarla': preguntale que pasa cuando definis una funcion pero nunca la usas en el programa. Si escribe el print suelto o todo el codigo sin def, guialo a distinguir entre DEFINIR una funcion y EJECUTARLA. Si el mensaje sale distinto (minusculas o sin el signo), pedile que lo compare caracter por caracter con lo pedido. Ante IndentationError o SyntaxError por faltar los dos puntos, preguntale que dice exactamente el mensaje de error y a que linea apunta.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Que tiene que hacer este programa, y que diferencia hay entre escribir el mensaje suelto y meterlo dentro de una funcion?", "senal_comprension": "Entiende que debe definir una funcion que imprima, no solo imprimir suelto", "senal_alerta": "Cree que alcanza con un print sin definir ninguna funcion"},
                {"texto": "Esta funcion necesita que el usuario le pase algun dato para funcionar?", "senal_comprension": "Reconoce que no recibe parametros ni usa input", "senal_alerta": "Intenta pedir datos con input que el ejercicio no requiere"},
            ],
            "n2": [
                {"texto": "Con que palabra clave se define una funcion en Python, y que va justo despues del nombre y los parentesis?", "senal_comprension": "Sabe que es def y que van los dos puntos", "senal_alerta": "Olvida los parentesis o los dos puntos"},
                {"texto": "Para mostrar el mensaje en pantalla, usas print o return? Que diferencia hay entre los dos?", "senal_comprension": "Sabe que print muestra en pantalla y return devuelve un valor", "senal_alerta": "Cree que return tambien imprime en pantalla"},
            ],
            "n3": [
                {"texto": "Corres el programa y no aparece nada en pantalla, aunque la funcion parece bien definida. Que puede estar pasando?", "senal_comprension": "Sospecha que definio la funcion pero no la llamo", "senal_alerta": "No relaciona la falta de salida con la falta de llamada"},
                {"texto": "Aparece 'IndentationError'. Que te esta diciendo Python sobre donde pusiste el print?", "senal_comprension": "Entiende que el print debe estar indentado dentro del cuerpo de la funcion", "senal_alerta": "No asocia el error con la indentacion"},
            ],
            "n4": [
                {"texto": "Si ahora quisieras que la funcion salude usando un nombre, que le tendrias que agregar a la definicion?", "senal_comprension": "Piensa en agregar un parametro entre los parentesis", "senal_alerta": "No ve como parametrizar la funcion"},
                {"texto": "Como harias para que el mensaje se imprima tres veces, sin reescribir el print tres veces adentro?", "senal_comprension": "Piensa en llamar la funcion varias veces o usar un bucle", "senal_alerta": "Cree que hay que duplicar el codigo de la funcion"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Define la funcion pero nunca la llama, entonces el programa corre sin errores pero no muestra nada.", "probabilidad_estimada": 0.7, "pregunta_diagnostica": "Que pasa cuando definis una funcion pero no la usas en ninguna parte del programa?"},
            {"descripcion": "Cree que return imprime en pantalla y usa return en vez de print.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "Que ves en la pantalla cuando una funcion hace return en lugar de print?"},
            {"descripcion": "Olvida los dos puntos despues de def y obtiene SyntaxError.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Que dice exactamente el mensaje de error y en que linea apunta?"},
            {"descripcion": "Escribe el print afuera de la funcion (sin indentar) y la funcion queda vacia.", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "El print esta adentro o afuera del cuerpo de la funcion?"},
            {"descripcion": "Escribe el mensaje distinto (minusculas o sin el signo !) y los tests fallan.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Coincide tu mensaje caracter por caracter con el pedido?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Pensa el programa en dos partes separadas: primero DEFINIR la funcion (decir que hace) y despues LLAMARLA (hacer que se ejecute). Anota cada parte antes de escribir codigo."},
            {"nivel": 2, "pista": "Necesitas: (1) definir con def imprimir_hola_mundo(): , (2) adentro, indentado, un print con el mensaje exacto, (3) en el programa principal, una linea que llame a la funcion escribiendo su nombre con parentesis."},
            {"nivel": 3, "pista": "Estructura guia:\ndef imprimir_hola_mundo():\n    print(\"Hola Mundo!\")\n\n# programa principal\nimprimir_hola_mundo()"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Ya tenes tu primera funcion andando. Como la modificarias para que reciba un nombre y salude a una persona en particular? Que cambia en la definicion y que en la llamada?"},
        "anti_patrones": [
            {"patron": "Definir la funcion pero no llamarla", "descripcion": "El programa corre sin errores pero no muestra nada.", "mensaje_orientacion": "Agrega en el programa principal una linea que llame a la funcion por su nombre."},
            {"patron": "Usar return en lugar de print", "descripcion": "La funcion devuelve el texto pero no se ve en pantalla.", "mensaje_orientacion": "Para mostrar en pantalla, usa print dentro de la funcion."},
            {"patron": "Olvidar los dos puntos despues de def", "descripcion": "Genera SyntaxError.", "mensaje_orientacion": "Revisa que despues de los parentesis vayan los dos puntos."},
            {"patron": "Print afuera del cuerpo de la funcion", "descripcion": "La funcion queda vacia y el mensaje no depende de ella.", "mensaje_orientacion": "Indenta el print para que quede dentro de la funcion."},
            {"patron": "Escribir el mensaje con distinto texto o capitalizacion", "descripcion": "Los tests fallan por no coincidir caracter por caracter.", "mensaje_orientacion": "Compara tu mensaje con el pedido: 'Hola Mundo!', con mayusculas y signo de exclamacion."},
        ],
    },
    {
        "titulo": "E2 - Saludo personalizado con función",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `saludar_usuario(nombre)` que reciba un nombre "
            "como parámetro y **devuelva** (con `return`) un saludo personalizado. Por "
            "ejemplo, `saludar_usuario(\"Marcos\")` tiene que devolver `Hola Marcos!`. En "
            "el programa principal, pedí el nombre con `input()`, llamá a la función con "
            "ese valor e imprimí lo que devuelve.\n\n"
            "### La función\n"
            "- **Nombre:** `saludar_usuario`\n"
            "- **Parámetros:** `nombre` (un texto)\n"
            "- **Qué hace:** devuelve (`return`) el texto `Hola <nombre>!` (no imprime adentro)\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y un parámetro `nombre`.\n"
            "- La función arma el saludo y lo **devuelve** con `return` (no usa `print` adentro).\n"
            "- En el programa principal: pedí el nombre con `input()`, llamá a la función y mostrá con `print()` lo que devuelve.\n"
            "- El saludo tiene que ser exactamente `Hola <nombre>!` (un espacio después de \"Hola\", el nombre tal cual, y el signo `!`).\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese su nombre: Marcos\nHola Marcos!\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 2 - Saludo personalizado\n\n"
            "# 1) Definí la función saludar_usuario(nombre) con un parámetro\n"
            "# 2) Adentro, armá el saludo \"Hola <nombre>!\" y devolvelo con return\n"
            "def saludar_usuario(nombre):\n"
            "    pass  # reemplazá esta línea: armá el saludo y devolvelo con return\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí el nombre con input()\n"
            "#    - llamá a la función con ese nombre\n"
            "#    - imprimí con print() lo que la función devuelve\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "basica",
        "test_cases": [
            {"id": "tc1", "name": "Nombre comun", "type": "stdin_stdout", "code": "Marcos", "expected": "Hola Marcos!", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Otro nombre", "type": "stdin_stdout", "code": "Lucia", "expected": "Hola Lucia!", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Nombre en mayusculas", "type": "stdin_stdout", "code": "ANA", "expected": "Hola ANA!", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con parametro", "descripcion": "Define saludar_usuario con un parametro nombre", "puntaje_max": "2"},
            {"nombre": "Uso de return", "descripcion": "La funcion devuelve el saludo con return y no lo imprime adentro", "puntaje_max": "3"},
            {"nombre": "Formato del saludo", "descripcion": "Arma exactamente 'Hola <nombre>!' con el espacio y el signo", "puntaje_max": "2"},
            {"nombre": "Input y llamada en el principal", "descripcion": "Pide el nombre con input y llama a la funcion con ese valor", "puntaje_max": "2"},
            {"nombre": "Muestra el valor devuelto", "descripcion": "Imprime en el principal lo que la funcion devuelve", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con parametro", "return", "input()", "f-string o concatenacion con +", "print()"],
            "conceptuales": ["parametro de funcion", "valor de retorno (return)", "diferencia return vs print", "pasaje de argumento", "uso del valor devuelto en el principal"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno usa print dentro de la funcion en vez de return, no le digas 'usa return': preguntale que diferencia hay entre mostrar algo y devolverlo, y que pasaria si despues quisiera reutilizar ese saludo. Si hace return pero en el principal no imprime el resultado, preguntale donde se ve lo que una funcion devuelve. Si el saludo sale pegado ('HolaMarcos!') o sin signo, pedile que compare el formato caracter por caracter. Si pide el input adentro de la funcion en lugar del principal, preguntale de quien es la responsabilidad de pedir datos segun la consigna.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Que recibe esta funcion desde afuera y que tiene que devolver?", "senal_comprension": "Recibe un nombre y devuelve un saludo armado con ese nombre", "senal_alerta": "Cree que la funcion tambien tiene que pedir el nombre con input"},
                {"texto": "El saludo cambia segun el nombre. Que parte del texto es fija y cual varia?", "senal_comprension": "Ve que 'Hola' y '!' son fijos y el nombre es lo que varia", "senal_alerta": "No distingue la parte fija de la variable"},
            ],
            "n2": [
                {"texto": "Como se le indica a una funcion que reciba un dato desde afuera?", "senal_comprension": "Sabe que se declara un parametro entre los parentesis", "senal_alerta": "No sabe como declarar el parametro"},
                {"texto": "Para que el programa principal pueda usar el saludo, la funcion lo tiene que imprimir o devolver? Por que?", "senal_comprension": "Entiende que return deja el valor disponible para reutilizar", "senal_alerta": "Cree que print y return son intercambiables"},
            ],
            "n3": [
                {"texto": "Pusiste print adentro de la funcion y el saludo se ve, pero la consigna pide return. Que diferencia practica hay?", "senal_comprension": "Entiende que con return el valor queda disponible para el principal", "senal_alerta": "No ve la diferencia porque en pantalla parece igual"},
                {"texto": "El saludo sale como 'HolaMarcos!' sin espacio. Donde esta el problema?", "senal_comprension": "Detecta que falta el espacio en la concatenacion o el f-string", "senal_alerta": "No revisa como armo el texto"},
            ],
            "n4": [
                {"texto": "Como cambiarias la funcion para que pueda saludar distinto, por ejemplo 'Buenos dias, Marcos'?", "senal_comprension": "Piensa en modificar el texto o agregar otro parametro", "senal_alerta": "No ve como variar el saludo"},
                {"texto": "Si tuvieras una lista de varios nombres, como reutilizarias esta misma funcion para saludarlos a todos?", "senal_comprension": "Piensa en llamarla varias veces o dentro de un bucle", "senal_alerta": "Cree que hay que reescribir la funcion por cada nombre"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Usa print dentro de la funcion en vez de return: funciona visualmente pero no devuelve el valor.", "probabilidad_estimada": 0.6, "pregunta_diagnostica": "Que diferencia hay entre mostrar el saludo y devolverlo?"},
            {"descripcion": "Hace return del saludo pero en el principal no lo imprime, entonces no se ve nada.", "probabilidad_estimada": 0.55, "pregunta_diagnostica": "Donde se muestra lo que una funcion devuelve con return?"},
            {"descripcion": "Arma el saludo sin el espacio o sin el signo (HolaMarcos / Hola Marcos).", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Coincide el formato de tu saludo caracter por caracter con el pedido?"},
            {"descripcion": "Pide el input adentro de la funcion en lugar del programa principal.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "Segun la consigna, quien pide el nombre: la funcion o el principal?"},
            {"descripcion": "Hardcodea un nombre fijo en el saludo y no usa el parametro recibido.", "probabilidad_estimada": 0.3, "pregunta_diagnostica": "De donde tiene que salir el nombre que aparece en el saludo?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Separa el problema: la FUNCION solo arma y devuelve el saludo a partir de un nombre; el PROGRAMA PRINCIPAL pide el nombre y muestra el resultado. Anota que hace cada parte antes de codear."},
            {"nivel": 2, "pista": "Necesitas: (1) def saludar_usuario(nombre): que arme 'Hola ' + nombre + '!' (o un f-string) y lo devuelva con return; (2) en el principal, nombre = input(...); (3) llamar a la funcion e imprimir lo que devuelve."},
            {"nivel": 3, "pista": "Estructura guia:\ndef saludar_usuario(nombre):\n    return f\"Hola {nombre}!\"\n\n# programa principal\nnombre = input(\"Ingrese su nombre: \")\nprint(saludar_usuario(nombre))"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Tu funcion devuelve un saludo. Como la modificarias para que reciba tambien un momento del dia y salude distinto (buenos dias / buenas tardes)? Que agregarias a la definicion y que a la llamada?"},
        "anti_patrones": [
            {"patron": "Usar print en lugar de return", "descripcion": "La funcion muestra el saludo pero no lo devuelve, no se puede reutilizar.", "mensaje_orientacion": "Para devolver un valor usable, usa return; el principal se encarga de imprimirlo."},
            {"patron": "return sin imprimir en el principal", "descripcion": "La funcion devuelve el saludo pero nada lo muestra en pantalla.", "mensaje_orientacion": "En el principal, envolve la llamada con print() o guarda el resultado y luego imprimilo."},
            {"patron": "Saludo sin espacio o sin signo", "descripcion": "El formato no coincide y los tests fallan.", "mensaje_orientacion": "Revisa el armado: 'Hola ' con espacio, el nombre, y el signo '!'."},
            {"patron": "Pedir input dentro de la funcion", "descripcion": "Mezcla responsabilidades: la funcion deberia solo armar el saludo.", "mensaje_orientacion": "Move el input() al programa principal y pasale el nombre como argumento."},
            {"patron": "Hardcodear el nombre en la funcion", "descripcion": "El saludo no depende del parametro recibido.", "mensaje_orientacion": "Usa el parametro 'nombre' dentro del saludo, no un texto fijo."},
        ],
    },
    {
        "titulo": "E3 - Ficha personal con función",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `informacion_personal(nombre, apellido, edad, residencia)` "
            "que reciba esos **cuatro parámetros** e **imprima** el mensaje:\n\n"
            "`Soy <nombre> <apellido>, tengo <edad> años y vivo en <residencia>.`\n\n"
            "En el programa principal, pedí los cuatro datos al usuario con `input()` y llamá a la "
            "función con esos valores.\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y los cuatro parámetros, en ese orden.\n"
            "- La función arma e **imprime** el mensaje (usa `print`, no `return`).\n"
            "- En el programa principal: pedí los cuatro datos con `input()` y llamá a la función pasándolos **en el mismo orden**.\n"
            "- El mensaje tiene que coincidir exactamente, incluyendo la palabra `años` (con ñ), la coma y el punto final.\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nNombre: Marcos\nApellido: Pérez\nEdad: 25\nLugar de residencia: San Rafael\nSoy Marcos Pérez, tengo 25 años y vivo en San Rafael.\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 3 - Ficha personal\n\n"
            "# 1) Definí la función con los 4 parámetros, en este orden:\n"
            "#    nombre, apellido, edad, residencia\n"
            "# 2) Adentro, imprimí el mensaje usando los 4 datos\n"
            "def informacion_personal(nombre, apellido, edad, residencia):\n"
            "    pass  # reemplazá esta línea por el print del mensaje\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí los 4 datos con input()\n"
            "#    - llamá a la función pasándolos en el mismo orden\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "intermedia",
        "test_cases": [
            {"id": "tc1", "name": "Datos completos", "type": "stdin_stdout", "code": "Marcos\nPérez\n25\nSan Rafael", "expected": "Soy Marcos Pérez, tengo 25 años y vivo en San Rafael.", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Otra persona", "type": "stdin_stdout", "code": "Lucia\nGomez\n31\nMendoza", "expected": "Soy Lucia Gomez, tengo 31 años y vivo en Mendoza.", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Residencia compuesta", "type": "stdin_stdout", "code": "Juan\nLopez\n19\nVilla Mercedes", "expected": "Soy Juan Lopez, tengo 19 años y vivo en Villa Mercedes.", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con 4 parametros", "descripcion": "Define la funcion con los cuatro parametros en el orden pedido", "puntaje_max": "2"},
            {"nombre": "Uso de print", "descripcion": "La funcion imprime el mensaje (usa print, no return)", "puntaje_max": "2"},
            {"nombre": "Formato exacto del mensaje", "descripcion": "Arma el texto exacto, incluida la palabra años con ñ, la coma y el punto final", "puntaje_max": "3"},
            {"nombre": "Input de los 4 datos", "descripcion": "Pide los cuatro datos con input en el programa principal", "puntaje_max": "2"},
            {"nombre": "Orden de los argumentos", "descripcion": "Llama a la funcion pasando los argumentos en el mismo orden que los parametros", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con varios parametros", "input()", "f-string o concatenacion", "print()", "coma para separar parametros"],
            "conceptuales": ["multiples parametros", "orden posicional de los argumentos", "correspondencia argumento-parametro", "interpolacion de variables en un texto", "funcion que imprime vs funcion que devuelve"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno mezcla el orden de los argumentos (por ejemplo pasa el apellido donde va el nombre), no le digas cual esta mal: preguntale en que orden definio los parametros y en que orden los esta pasando. Si el mensaje sale mal armado (falta 'años', la coma o el 'y'), pedile que compare su salida caracter por caracter con el ejemplo. Si usa return en vez de print, recordale que la consigna pide imprimir. Si pide los 4 datos adentro de la funcion, preguntale donde dice la consigna que se piden los datos. Cuidado con la 'ñ' de 'años': si escribe 'anos' o 'anios', orientalo a revisar el texto exacto sin darselo escrito.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Cuantos datos distintos necesita la funcion para armar el mensaje, y cuales son?", "senal_comprension": "Identifica los cuatro: nombre, apellido, edad y residencia", "senal_alerta": "Cree que con menos parametros alcanza"},
                {"texto": "La funcion imprime el mensaje o lo devuelve? Que palabra de la consigna te lo indica?", "senal_comprension": "Ve que la consigna dice 'imprime' y por eso usa print", "senal_alerta": "Asume return sin leer la consigna"},
            ],
            "n2": [
                {"texto": "Como se declaran varios parametros en una misma funcion?", "senal_comprension": "Sabe que se separan con comas dentro de los parentesis", "senal_alerta": "No sabe como poner mas de un parametro"},
                {"texto": "Cuando llamas a la funcion, en que orden tenes que pasar los valores?", "senal_comprension": "Entiende que el orden de los argumentos sigue el de los parametros", "senal_alerta": "Cree que el orden de los argumentos no importa"},
            ],
            "n3": [
                {"texto": "El mensaje muestra el apellido en el lugar del nombre. Que tenes que revisar?", "senal_comprension": "Revisa el orden en que paso los argumentos al llamar", "senal_alerta": "No relaciona el problema con el orden posicional"},
                {"texto": "En tu salida falta la palabra 'años' o una coma. Donde se arma ese texto?", "senal_comprension": "Revisa el f-string o la concatenacion del mensaje", "senal_alerta": "No revisa la parte fija del mensaje"},
            ],
            "n4": [
                {"texto": "Como agregarias un quinto dato, por ejemplo la profesion, al mensaje?", "senal_comprension": "Piensa en sumar otro parametro y usarlo en el texto", "senal_alerta": "No sabe como extender la funcion"},
                {"texto": "Si quisieras que la funcion DEVUELVA el mensaje en vez de imprimirlo, que cambiarias?", "senal_comprension": "Cambia print por return y lo imprime en el principal", "senal_alerta": "No distingue imprimir de devolver"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Pasa los argumentos en orden equivocado (apellido por nombre, etc.).", "probabilidad_estimada": 0.6, "pregunta_diagnostica": "En que orden definiste los parametros y en que orden los estas pasando?"},
            {"descripcion": "Usa return en vez de print aunque la consigna pide imprimir.", "probabilidad_estimada": 0.35, "pregunta_diagnostica": "Que palabra usa la consigna: imprimir o devolver?"},
            {"descripcion": "Escribe 'años' sin la ñ (anos / anios) y el texto no coincide.", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "Como se escribe exactamente la palabra años en el mensaje?"},
            {"descripcion": "Olvida la coma, el 'y' o el punto final, y el formato difiere.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Coincide tu salida palabra por palabra y signo por signo con el ejemplo?"},
            {"descripcion": "Pide los cuatro inputs adentro de la funcion en lugar del principal.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "Donde dice la consigna que se piden los datos al usuario?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Pensa primero que datos necesita el mensaje (son cuatro) y de donde salen. La FUNCION recibe esos cuatro datos y arma el mensaje; el PRINCIPAL los pide con input y llama a la funcion."},
            {"nivel": 2, "pista": "Necesitas: (1) def informacion_personal(nombre, apellido, edad, residencia): con un print que arme el mensaje usando los cuatro; (2) en el principal, un input() por cada dato; (3) llamar a la funcion pasando los cuatro en el mismo orden."},
            {"nivel": 3, "pista": "Estructura guia:\ndef informacion_personal(nombre, apellido, edad, residencia):\n    print(f\"Soy {nombre} {apellido}, tengo {edad} años y vivo en {residencia}.\")\n\n# programa principal\nnombre = input(\"Nombre: \")\napellido = input(\"Apellido: \")\nedad = input(\"Edad: \")\nresidencia = input(\"Lugar de residencia: \")\ninformacion_personal(nombre, apellido, edad, residencia)"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Tu funcion arma una ficha personal con cuatro datos. Como la adaptarias para que la profesion sea un dato opcional, sin romper las llamadas que ya funcionan? Que sabes de los valores por defecto en los parametros?"},
        "anti_patrones": [
            {"patron": "Argumentos en orden equivocado", "descripcion": "El mensaje mezcla los datos (por ejemplo apellido donde va nombre).", "mensaje_orientacion": "Pasa los argumentos en el mismo orden en que definiste los parametros."},
            {"patron": "Usar return en vez de print", "descripcion": "La consigna pide imprimir y la funcion no muestra nada.", "mensaje_orientacion": "La funcion tiene que imprimir el mensaje con print."},
            {"patron": "Escribir 'años' sin la ñ", "descripcion": "El texto no coincide caracter por caracter.", "mensaje_orientacion": "Revisa que la palabra sea exactamente 'años', con ñ."},
            {"patron": "Olvidar la coma, el 'y' o el punto", "descripcion": "El formato del mensaje difiere del esperado.", "mensaje_orientacion": "Compara con el ejemplo: coma despues del apellido, 'y' antes de 'vivo', y punto final."},
            {"patron": "Pedir los inputs dentro de la funcion", "descripcion": "Mezcla la responsabilidad de pedir datos con la de armar el mensaje.", "mensaje_orientacion": "Pedi los cuatro datos en el principal y pasalos como argumentos."},
        ],
    },
    {
        "titulo": "E4 - Área y perímetro con dos funciones",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí **dos funciones**: `calcular_area_circulo(radio)`, que **devuelve** el área de un "
            "círculo, y `calcular_perimetro_circulo(radio)`, que **devuelve** el perímetro. Ambas reciben "
            "el radio como parámetro. En el programa principal, pedí el radio al usuario, llamá a las dos "
            "funciones y mostrá los resultados redondeados a 2 decimales.\n\n"
            "### Fórmulas\n"
            "- Área = π × radio²\n"
            "- Perímetro = 2 × π × radio\n\n"
            "### Requisitos\n"
            "- Importá `math` para usar `math.pi`.\n"
            "- Cada cálculo va en **su propia función**, y cada una **devuelve** el valor con `return`.\n"
            "- En el programa principal: convertí el radio a `float`, llamá a ambas funciones y mostrá los resultados redondeados a 2 decimales.\n"
            "- La salida tiene que ser exactamente `Área:` y `Perímetro:` (con tilde en Área).\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese el radio del círculo: 5\nÁrea: 78.54\nPerímetro: 31.42\n```"
        ),
        "inicial_codigo": (
            "import math\n"
            "# Ejercicio 4 - Área y perímetro con dos funciones\n\n"
            "# 1) Definí calcular_area_circulo(radio) que DEVUELVA el área (math.pi * radio**2)\n"
            "def calcular_area_circulo(radio):\n"
            "    pass  # reemplazá por el return del área\n\n"
            "# 2) Definí calcular_perimetro_circulo(radio) que DEVUELVA el perímetro (2 * math.pi * radio)\n"
            "def calcular_perimetro_circulo(radio):\n"
            "    pass  # reemplazá por el return del perímetro\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí el radio y convertilo a float\n"
            "#    - llamá a ambas funciones\n"
            "#    - mostrá los resultados redondeados a 2 decimales\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "intermedia",
        "test_cases": [
            {"id": "tc1", "name": "Radio entero", "type": "stdin_stdout", "code": "5", "expected": "Área: 78.54\nPerímetro: 31.42", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Radio decimal", "type": "stdin_stdout", "code": "2.5", "expected": "Área: 19.63\nPerímetro: 15.71", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Radio igual a 1", "type": "stdin_stdout", "code": "1", "expected": "Área: 3.14\nPerímetro: 6.28", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Importacion de math", "descripcion": "Importa el modulo math antes de usar math.pi", "puntaje_max": "1"},
            {"nombre": "Dos funciones separadas", "descripcion": "Define una funcion para el area y otra para el perimetro, cada una con su return", "puntaje_max": "3"},
            {"nombre": "Formulas correctas", "descripcion": "Aplica area = pi*r**2 y perimetro = 2*pi*r en la funcion que corresponde", "puntaje_max": "3"},
            {"nombre": "Conversion y redondeo", "descripcion": "Convierte el radio a float y muestra los resultados con 2 decimales", "puntaje_max": "2"},
            {"nombre": "Llamada a ambas funciones", "descripcion": "El programa principal llama a las dos funciones con el radio ingresado", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["import math", "math.pi", "def con parametro", "return", "** (potencia)", "float()", "round() o :.2f", "print()"],
            "conceptuales": ["una funcion por cada calculo", "valor de retorno", "modulo math", "conversion de tipos", "redondeo", "reutilizacion del mismo parametro en dos funciones"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno mete area y perimetro en una sola funcion, preguntale cuantos calculos distintos pide la consigna y cuantas funciones sugiere eso. Si olvida import math, no le digas que falta: preguntale que dice exactamente el mensaje de error. Si usa el radio sin convertir y obtiene TypeError, guialo a pensar que tipo devuelve input(). Si confunde las formulas (usa 2*pi*r para el area), pedile que vuelva a leer las formulas de la consigna. Si usa print dentro de las funciones en vez de return, preguntale como haria el principal para mostrar ambos resultados si las funciones no devuelven nada.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Cuantos calculos distintos pide la consigna, y como se relaciona eso con la cantidad de funciones?", "senal_comprension": "Ve que son dos calculos y por eso dos funciones", "senal_alerta": "Intenta resolver todo en una sola funcion"},
                {"texto": "Que dato necesitan las dos funciones para poder trabajar?", "senal_comprension": "Reconoce que ambas reciben el radio", "senal_alerta": "Cree que cada funcion necesita datos distintos"},
            ],
            "n2": [
                {"texto": "Como hacen las funciones para entregarle el resultado al programa principal?", "senal_comprension": "Devuelven el valor con return", "senal_alerta": "Imprimen adentro en lugar de devolver"},
                {"texto": "Que es math.pi y por que conviene usarlo en vez de escribir 3.14?", "senal_comprension": "Entiende que es π con mucha precision", "senal_alerta": "Cree que 3.14 es igual de preciso"},
            ],
            "n3": [
                {"texto": "Aparece 'NameError: name math is not defined'. Que esta faltando?", "senal_comprension": "Falta import math al inicio", "senal_alerta": "No relaciona el error con la falta del import"},
                {"texto": "El area te da un numero con muchos decimales. Donde conviene aplicar el redondeo?", "senal_comprension": "Redondea al mostrar en el principal con round o :.2f", "senal_alerta": "No sabe en que punto redondear"},
            ],
            "n4": [
                {"texto": "Como agregarias una tercera funcion que calcule el diametro (2*radio)?", "senal_comprension": "Define otra funcion analoga con el mismo parametro radio", "senal_alerta": "No ve como sumar otra funcion del mismo estilo"},
                {"texto": "Si quisieras que una sola funcion devuelva el area y el perimetro juntos, que tipo de dato te permite devolver dos valores?", "senal_comprension": "Piensa en una tupla", "senal_alerta": "Cree que una funcion solo puede devolver un valor"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Usa math.pi sin import math y obtiene NameError.", "probabilidad_estimada": 0.6, "pregunta_diagnostica": "Que dice exactamente el mensaje de error?"},
            {"descripcion": "No convierte el radio a float y obtiene TypeError al multiplicar.", "probabilidad_estimada": 0.7, "pregunta_diagnostica": "Que tipo de dato devuelve input()?"},
            {"descripcion": "Confunde las formulas: usa la del perimetro para el area o viceversa.", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "Cual es la formula del area y cual la del perimetro segun la consigna?"},
            {"descripcion": "Mete los dos calculos en una sola funcion en vez de dos.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "Cuantas funciones sugiere una consigna que pide dos calculos separados?"},
            {"descripcion": "Olvida redondear y muestra muchos decimales.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Cuantos decimales muestra tu salida y cuantos pide la consigna?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Son DOS calculos independientes (area y perimetro), asi que pensa DOS funciones, cada una recibiendo el radio. El programa principal pide el radio una sola vez y llama a las dos."},
            {"nivel": 2, "pista": "Necesitas: (1) import math; (2) def calcular_area_circulo(radio): que devuelva math.pi*radio**2; (3) def calcular_perimetro_circulo(radio): que devuelva 2*math.pi*radio; (4) en el principal, convertir el radio a float, llamar a ambas y mostrar redondeado a 2 decimales."},
            {"nivel": 3, "pista": "Estructura guia:\nimport math\n\ndef calcular_area_circulo(radio):\n    return math.pi * radio**2\n\ndef calcular_perimetro_circulo(radio):\n    return 2 * math.pi * radio\n\n# programa principal\nradio = float(input(\"Ingrese el radio del círculo: \"))\nprint(f\"Área: {round(calcular_area_circulo(radio), 2)}\")\nprint(f\"Perímetro: {round(calcular_perimetro_circulo(radio), 2)}\")"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Ya tenes dos funciones que comparten el mismo radio. Como armarias una unica funcion que devuelva el area y el perimetro juntos en una tupla? Que ventaja tendria llamar a una sola funcion en vez de dos?"},
        "anti_patrones": [
            {"patron": "Usar math.pi sin import math", "descripcion": "Genera NameError.", "mensaje_orientacion": "Agrega import math al inicio del archivo."},
            {"patron": "Radio sin convertir a float", "descripcion": "Genera TypeError al multiplicar.", "mensaje_orientacion": "Envolve el input() con float()."},
            {"patron": "Confundir las formulas de area y perimetro", "descripcion": "Los resultados salen cruzados.", "mensaje_orientacion": "Revisa: area = pi*r**2, perimetro = 2*pi*r."},
            {"patron": "Resolver con una sola funcion", "descripcion": "La consigna pide dos funciones separadas.", "mensaje_orientacion": "Defini una funcion para el area y otra para el perimetro."},
            {"patron": "Resultado sin redondear", "descripcion": "Muestra demasiados decimales.", "mensaje_orientacion": "Redondea al mostrar con round(valor, 2) o el formato :.2f."},
        ],
    },
    {
        "titulo": "E5 - Conversión de segundos a horas",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `segundos_a_horas(segundos)` que reciba una cantidad de segundos "
            "y **devuelva** (con `return`) la cantidad de horas correspondientes. En el programa principal, "
            "pedí los segundos al usuario y mostrá el resultado usando la función.\n\n"
            "### Pista de conversión\n"
            "- 1 hora = 3600 segundos.\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y el parámetro `segundos`.\n"
            "- La función **devuelve** las horas con `return`, usando la **división real** (`/`) para no perder los decimales.\n"
            "- En el programa principal: convertí el dato ingresado a número, llamá a la función e imprimí lo que devuelve.\n"
            "- La salida tiene que ser exactamente `Horas: <valor>`.\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese la cantidad de segundos: 7200\nHoras: 2.0\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 5 - Segundos a horas\n\n"
            "# 1) Definí la función segundos_a_horas(segundos)\n"
            "# 2) Adentro, devolvé las horas: segundos dividido la cantidad de segundos que tiene una hora\n"
            "def segundos_a_horas(segundos):\n"
            "    pass  # reemplazá por el return de la conversión\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí los segundos y convertilos a número\n"
            "#    - llamá a la función e imprimí lo que devuelve\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "intermedia",
        "test_cases": [
            {"id": "tc1", "name": "Dos horas exactas", "type": "stdin_stdout", "code": "7200", "expected": "Horas: 2.0", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Hora y media", "type": "stdin_stdout", "code": "5400", "expected": "Horas: 1.5", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Media hora", "type": "stdin_stdout", "code": "1800", "expected": "Horas: 0.5", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con parametro", "descripcion": "Define segundos_a_horas con el parametro segundos", "puntaje_max": "2"},
            {"nombre": "Conversion del input a numero", "descripcion": "Convierte el dato ingresado a int o float antes de operar", "puntaje_max": "2"},
            {"nombre": "Formula y division correctas", "descripcion": "Divide por 3600 usando division real (/) para conservar decimales", "puntaje_max": "3"},
            {"nombre": "Uso de return", "descripcion": "La funcion devuelve el resultado con return en lugar de imprimirlo", "puntaje_max": "2"},
            {"nombre": "Muestra en el principal", "descripcion": "Llama a la funcion e imprime el valor devuelto con el formato pedido", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con parametro", "return", "input()", "int() o float()", "operador / (division real)", "print()"],
            "conceptuales": ["valor de retorno", "conversion de tipos", "division real vs division entera (/ vs //)", "equivalencia 1 hora = 3600 segundos", "uso del valor devuelto"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno usa // (division entera) y pierde los decimales (5400 le da 1 en vez de 1.5), no le digas que cambie el operador: preguntale que diferencia hay entre / y // y que pasa con la parte decimal. Si no convierte el input y obtiene TypeError, guialo a pensar que tipo devuelve input(). Si usa un divisor incorrecto (60 en vez de 3600), preguntale cuantos segundos tiene una hora. Si imprime adentro de la funcion en vez de devolver, recordale que la consigna dice 'devuelve'.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Cuantos segundos hay en una hora, y como se relaciona eso con la conversion que pide el ejercicio?", "senal_comprension": "Sabe que una hora tiene 3600 segundos", "senal_alerta": "No conoce la equivalencia o usa 60"},
                {"texto": "La funcion devuelve las horas o las imprime? Que palabra de la consigna lo aclara?", "senal_comprension": "Ve que dice 'devuelve' y usa return", "senal_alerta": "Asume print sin leer la consigna"},
            ],
            "n2": [
                {"texto": "Para pasar de segundos a horas, dividis o multiplicas, y por cuanto?", "senal_comprension": "Divide por 3600", "senal_alerta": "Multiplica o usa un divisor equivocado"},
                {"texto": "El input llega como texto. Que tenes que hacer antes de poder dividirlo?", "senal_comprension": "Lo convierte a int o float", "senal_alerta": "Intenta dividir el string directamente"},
            ],
            "n3": [
                {"texto": "Pusiste 5400 y te dio 1 en vez de 1.5. Que operador de division usaste?", "senal_comprension": "Detecta que uso // en lugar de /", "senal_alerta": "No distingue / de //"},
                {"texto": "Aparece 'TypeError: unsupported operand type(s) for /'. Que tipo sigue siendo segundos?", "senal_comprension": "El input sigue siendo string", "senal_alerta": "No relaciona el error con el tipo del input"},
            ],
            "n4": [
                {"texto": "Como ampliarias la funcion para que tambien devuelva los minutos restantes?", "senal_comprension": "Piensa en el modulo (%) y otra division", "senal_alerta": "No ve como obtener el resto"},
                {"texto": "Si quisieras la funcion inversa (de horas a segundos), que operacion usarias?", "senal_comprension": "Multiplicaria por 3600", "senal_alerta": "No ve la operacion inversa"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Usa division entera // y pierde los decimales de las horas.", "probabilidad_estimada": 0.55, "pregunta_diagnostica": "Que diferencia hay entre / y // cuando dividis?"},
            {"descripcion": "No convierte el input a numero y obtiene TypeError al dividir.", "probabilidad_estimada": 0.65, "pregunta_diagnostica": "Que tipo de dato devuelve input()?"},
            {"descripcion": "Usa un divisor incorrecto (60 en vez de 3600).", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "Cuantos segundos tiene una hora completa?"},
            {"descripcion": "Imprime adentro de la funcion en vez de devolver con return.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "La consigna pide imprimir o devolver las horas?"},
            {"descripcion": "Multiplica por 3600 en lugar de dividir.", "probabilidad_estimada": 0.3, "pregunta_diagnostica": "Si tenes muchos segundos, las horas deberian dar un numero mas grande o mas chico?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Pensa primero la equivalencia: cuantos segundos hay en una hora. La FUNCION recibe los segundos y devuelve las horas; el PRINCIPAL pide el numero y muestra el resultado."},
            {"nivel": 2, "pista": "Necesitas: (1) def segundos_a_horas(segundos): que devuelva segundos / 3600 (division real, con /); (2) en el principal, convertir el input a numero (int o float); (3) llamar a la funcion e imprimir lo que devuelve."},
            {"nivel": 3, "pista": "Estructura guia:\ndef segundos_a_horas(segundos):\n    return segundos / 3600\n\n# programa principal\nsegundos = int(input(\"Ingrese la cantidad de segundos: \"))\nprint(f\"Horas: {segundos_a_horas(segundos)}\")"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Tu funcion convierte segundos a horas. Como la extenderias para que devuelva horas, minutos y segundos por separado (formato reloj)? Que operaciones necesitarias ademas de la division?"},
        "anti_patrones": [
            {"patron": "Usar // en vez de /", "descripcion": "Pierde la parte decimal de las horas.", "mensaje_orientacion": "Para conservar los decimales, usa la division real con /."},
            {"patron": "No convertir el input a numero", "descripcion": "Genera TypeError al dividir un string.", "mensaje_orientacion": "Convertí el input a int o float antes de dividir."},
            {"patron": "Dividir por un valor incorrecto", "descripcion": "El resultado no representa las horas reales.", "mensaje_orientacion": "Una hora tiene 3600 segundos: dividi por 3600."},
            {"patron": "Imprimir en vez de devolver", "descripcion": "La funcion no devuelve el valor que el principal necesita.", "mensaje_orientacion": "Usa return; el programa principal se encarga de imprimir."},
            {"patron": "Multiplicar en lugar de dividir", "descripcion": "Mas segundos darian mas horas, lo cual es incorrecto.", "mensaje_orientacion": "Para pasar a una unidad mayor (horas), dividis."},
        ],
    },
    {
        "titulo": "E6 - Tabla de multiplicar con función",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `tabla_multiplicar(numero)` que reciba un número e **imprima** su "
            "tabla de multiplicar del 1 al 10. En el programa principal, pedí el número al usuario y llamá "
            "a la función.\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y el parámetro `numero`.\n"
            "- Usá un bucle `for` con `range` para recorrer del 1 al 10.\n"
            "- Cada línea tiene el formato exacto `<numero> x <i> = <resultado>`.\n"
            "- En el programa principal: pedí el número, convertilo a entero y llamá a la función.\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese un número: 5\n5 x 1 = 5\n5 x 2 = 10\n5 x 3 = 15\n5 x 4 = 20\n5 x 5 = 25\n5 x 6 = 30\n5 x 7 = 35\n5 x 8 = 40\n5 x 9 = 45\n5 x 10 = 50\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 6 - Tabla de multiplicar\n\n"
            "# 1) Definí la función tabla_multiplicar(numero)\n"
            "# 2) Adentro, usá un for con range para ir del 1 al 10\n"
            "#    y en cada vuelta imprimí \"numero x i = resultado\"\n"
            "def tabla_multiplicar(numero):\n"
            "    pass  # reemplazá por el bucle que imprime la tabla\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí el número y convertilo a entero\n"
            "#    - llamá a la función\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "intermedia",
        "test_cases": [
            {"id": "tc1", "name": "Tabla del 5", "type": "stdin_stdout", "code": "5", "expected": "5 x 1 = 5\n5 x 2 = 10\n5 x 3 = 15\n5 x 4 = 20\n5 x 5 = 25\n5 x 6 = 30\n5 x 7 = 35\n5 x 8 = 40\n5 x 9 = 45\n5 x 10 = 50", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Tabla del 3", "type": "stdin_stdout", "code": "3", "expected": "3 x 1 = 3\n3 x 2 = 6\n3 x 3 = 9\n3 x 4 = 12\n3 x 5 = 15\n3 x 6 = 18\n3 x 7 = 21\n3 x 8 = 24\n3 x 9 = 27\n3 x 10 = 30", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Tabla del 10", "type": "stdin_stdout", "code": "10", "expected": "10 x 1 = 10\n10 x 2 = 20\n10 x 3 = 30\n10 x 4 = 40\n10 x 5 = 50\n10 x 6 = 60\n10 x 7 = 70\n10 x 8 = 80\n10 x 9 = 90\n10 x 10 = 100", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con parametro", "descripcion": "Define tabla_multiplicar con el parametro numero", "puntaje_max": "2"},
            {"nombre": "Bucle del 1 al 10", "descripcion": "Usa for con range para recorrer exactamente del 1 al 10 inclusive", "puntaje_max": "3"},
            {"nombre": "Formato de cada linea", "descripcion": "Cada linea respeta el formato 'numero x i = resultado'", "puntaje_max": "3"},
            {"nombre": "Conversion del input", "descripcion": "Convierte el numero ingresado a entero antes de usarlo", "puntaje_max": "1"},
            {"nombre": "Llamada desde el principal", "descripcion": "El programa principal pide el numero y llama a la funcion", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con parametro", "for", "range(1, 11)", "int()", "f-string", "print()"],
            "conceptuales": ["bucle for", "rango y limites de range", "iteracion del 1 al 10 inclusive", "funcion que imprime", "interpolacion de variables del bucle"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si la tabla llega solo hasta el 9, no le digas que cambie el range: preguntale hasta que numero llega range(1, 10) y donde se corta. Si la tabla arranca en 0, preguntale en que valor empieza range cuando le pasas un solo argumento. Si el print esta fuera del bucle y solo aparece una linea, preguntale donde tiene que estar el print para que se repita. Si no convierte el numero y el formato sale raro o falla, guialo a revisar el tipo del input.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Cuantas lineas tiene que imprimir la funcion, y que va cambiando en cada una?", "senal_comprension": "Reconoce que son 10 lineas y que cambia el multiplicador del 1 al 10", "senal_alerta": "No identifica que es una repeticion"},
                {"texto": "La funcion imprime la tabla o la devuelve? Que palabra de la consigna lo indica?", "senal_comprension": "Ve que dice 'imprima' y usa print", "senal_alerta": "Intenta devolver la tabla con return"},
            ],
            "n2": [
                {"texto": "Que estructura te permite repetir una accion del 1 al 10 sin escribir 10 prints?", "senal_comprension": "Sabe que es un bucle for con range", "senal_alerta": "Escribe 10 prints separados"},
                {"texto": "Para que el for vaya del 1 al 10 inclusive, que valores le pasas a range?", "senal_comprension": "Sabe que es range(1, 11)", "senal_alerta": "Usa range(1, 10) o range(10)"},
            ],
            "n3": [
                {"texto": "Tu tabla llega hasta el 9 y no muestra el 10. Que valor le pusiste como limite al range?", "senal_comprension": "Detecta que range(1, 10) no incluye el 10", "senal_alerta": "No entiende que el limite superior de range es exclusivo"},
                {"texto": "Solo aparece una linea de la tabla. Donde esta ubicado tu print, adentro o afuera del for?", "senal_comprension": "Detecta que el print quedo fuera del bucle", "senal_alerta": "No relaciona la indentacion del print con la repeticion"},
            ],
            "n4": [
                {"texto": "Como modificarias la funcion para imprimir la tabla hasta un limite que reciba como segundo parametro?", "senal_comprension": "Piensa en agregar un parametro y usarlo en el range", "senal_alerta": "No ve como parametrizar el limite"},
                {"texto": "Como harias para que la funcion DEVUELVA la tabla como un texto en vez de imprimirla?", "senal_comprension": "Piensa en acumular en un string y devolverlo", "senal_alerta": "No distingue imprimir de devolver"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Usa range(1, 10) y la tabla llega solo hasta el 9.", "probabilidad_estimada": 0.6, "pregunta_diagnostica": "Hasta que numero llega range(1, 10)?"},
            {"descripcion": "Usa range(10) y la tabla arranca en 0 o llega solo al 9.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "En que valor empieza range cuando le pasas un solo argumento?"},
            {"descripcion": "Pone el print fuera del bucle y solo imprime una linea.", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "El print esta adentro o afuera del for?"},
            {"descripcion": "No convierte el numero a entero y el formato sale mal.", "probabilidad_estimada": 0.35, "pregunta_diagnostica": "Que tipo devuelve input() y como afecta a la multiplicacion?"},
            {"descripcion": "Arma el formato de la linea distinto (sin espacios o con otro signo).", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "Coincide cada linea caracter por caracter con el ejemplo?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Pensa que la funcion tiene que repetir una misma accion 10 veces, cambiando solo el multiplicador del 1 al 10. Eso es un bucle. La funcion imprime cada linea; el principal pide el numero."},
            {"nivel": 2, "pista": "Necesitas: (1) def tabla_multiplicar(numero): con un for i in range(1, 11): adentro; (2) en cada vuelta, un print con el formato 'numero x i = resultado'; (3) en el principal, convertir el input a entero y llamar a la funcion."},
            {"nivel": 3, "pista": "Estructura guia:\ndef tabla_multiplicar(numero):\n    for i in range(1, 11):\n        print(f\"{numero} x {i} = {numero * i}\")\n\n# programa principal\nnumero = int(input(\"Ingrese un número: \"))\ntabla_multiplicar(numero)"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Tu funcion imprime la tabla del 1 al 10. Como la modificarias para que el limite sea un segundo parametro (por ejemplo hasta 12)? Que parte del codigo cambia y que parte se mantiene?"},
        "anti_patrones": [
            {"patron": "Usar range(1, 10)", "descripcion": "La tabla no incluye el 10 porque el limite superior es exclusivo.", "mensaje_orientacion": "Para llegar al 10 inclusive, el range tiene que terminar en 11."},
            {"patron": "Print fuera del bucle", "descripcion": "Solo se imprime una linea en vez de las diez.", "mensaje_orientacion": "Indenta el print para que quede adentro del for."},
            {"patron": "Escribir 10 prints a mano", "descripcion": "Repite codigo en vez de usar un bucle.", "mensaje_orientacion": "Usa un for con range para no repetir el print diez veces."},
            {"patron": "No convertir el numero a entero", "descripcion": "El producto o el formato salen mal.", "mensaje_orientacion": "Convertí el input a entero con int() antes de usarlo."},
            {"patron": "Formato de linea distinto", "descripcion": "Las lineas no coinciden con lo esperado.", "mensaje_orientacion": "Respeta el formato 'numero x i = resultado', con los espacios y el signo igual."},
        ],
    },
    {
        "titulo": "E7 - Operaciones básicas devolviendo una tupla",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `operaciones_basicas(a, b)` que reciba dos números y **devuelva** "
            "(con `return`) una **tupla** con cuatro resultados, en este orden: la suma, la resta, la "
            "multiplicación y la división. En el programa principal, pedí los dos números al usuario, llamá "
            "a la función y mostrá los cuatro resultados de forma clara.\n\n"
            "### La función\n"
            "- **Nombre:** `operaciones_basicas`\n"
            "- **Parámetros:** `a`, `b` (dos números)\n"
            "- **Qué hace:** devuelve una tupla `(suma, resta, multiplicacion, division)`\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y los parámetros `a` y `b`.\n"
            "- La función **devuelve** los cuatro resultados en una tupla, en el orden indicado.\n"
            "- En el programa principal: pedí los dos números, convertilos a número, llamá a la función y mostrá cada resultado etiquetado.\n"
            "- La salida tiene el formato exacto `Suma:`, `Resta:`, `Multiplicación:`, `División:` (con tilde donde corresponde).\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese el primer número: 10\nIngrese el segundo número: 2\nSuma: 12\nResta: 8\nMultiplicación: 20\nDivisión: 5.0\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 7 - Operaciones básicas\n\n"
            "# 1) Definí la función operaciones_basicas(a, b)\n"
            "# 2) Adentro, calculá las 4 operaciones y devolvelas en una tupla\n"
            "#    en el orden: suma, resta, multiplicación, división\n"
            "def operaciones_basicas(a, b):\n"
            "    pass  # reemplazá por el return de la tupla con los 4 resultados\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí los dos números y convertilos a número\n"
            "#    - llamá a la función y mostrá cada resultado etiquetado\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "avanzada",
        "test_cases": [
            {"id": "tc1", "name": "Division exacta", "type": "stdin_stdout", "code": "10\n2", "expected": "Suma: 12\nResta: 8\nMultiplicación: 20\nDivisión: 5.0", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Numeros mayores", "type": "stdin_stdout", "code": "20\n5", "expected": "Suma: 25\nResta: 15\nMultiplicación: 100\nDivisión: 4.0", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Otro par", "type": "stdin_stdout", "code": "9\n3", "expected": "Suma: 12\nResta: 6\nMultiplicación: 27\nDivisión: 3.0", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con dos parametros", "descripcion": "Define operaciones_basicas con los parametros a y b", "puntaje_max": "1"},
            {"nombre": "Calculo de las cuatro operaciones", "descripcion": "Calcula suma, resta, multiplicacion y division correctamente", "puntaje_max": "3"},
            {"nombre": "Devolucion en tupla ordenada", "descripcion": "Devuelve los cuatro resultados en una tupla en el orden pedido", "puntaje_max": "3"},
            {"nombre": "Conversion y llamada en el principal", "descripcion": "Pide y convierte los dos numeros y llama a la funcion", "puntaje_max": "2"},
            {"nombre": "Salida etiquetada", "descripcion": "Muestra cada resultado con su etiqueta en el formato pedido", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con dos parametros", "return de una tupla", "operadores + - * /", "int() o float()", "input()", "desempaquetado de tupla", "print()"],
            "conceptuales": ["devolver varios valores con una tupla", "orden de los elementos de la tupla", "division real", "division por cero", "uso del valor devuelto"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno intenta devolver cuatro return separados, preguntale cuantas veces puede ejecutarse un return en una funcion y como agruparia varios valores en uno solo. Si el segundo numero es 0 y aparece 'ZeroDivisionError', no le des la solucion: preguntale que pasa matematicamente al dividir por cero y como podria anticipar ese caso. Si desordena la tupla (devuelve la resta donde va la suma), pedile que compare el orden con el que pide la consigna. Si no convierte los inputs, guialo a pensar el tipo que devuelve input().",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Cuantos resultados tiene que devolver la funcion y en que orden?", "senal_comprension": "Reconoce que son cuatro: suma, resta, multiplicacion y division", "senal_alerta": "Cree que tiene que devolver de a uno"},
                {"texto": "Una funcion puede devolver mas de un valor a la vez? Como agruparias varios resultados en uno solo?", "senal_comprension": "Piensa en una tupla", "senal_alerta": "Cree que solo se puede devolver un valor suelto"},
            ],
            "n2": [
                {"texto": "Como se escribe una tupla con cuatro valores en un return?", "senal_comprension": "Sabe que van entre parentesis separados por comas", "senal_alerta": "No sabe la sintaxis de la tupla"},
                {"texto": "Una vez que la funcion devuelve la tupla, como accedes a cada resultado en el principal?", "senal_comprension": "Piensa en desempaquetar o indexar la tupla", "senal_alerta": "No sabe como leer los valores devueltos"},
            ],
            "n3": [
                {"texto": "Pusiste cuatro return seguidos y solo te devuelve la suma. Por que se corta la funcion en el primer return?", "senal_comprension": "Entiende que return termina la funcion", "senal_alerta": "Cree que puede haber varios return ejecutandose"},
                {"texto": "Si el segundo numero es 0 aparece 'ZeroDivisionError'. Que esta pasando con la division?", "senal_comprension": "Reconoce que no se puede dividir por cero", "senal_alerta": "No relaciona el error con el divisor en cero"},
            ],
            "n4": [
                {"texto": "Como modificarias la funcion para que devuelva tambien el resto de la division entera?", "senal_comprension": "Piensa en agregar el operador % a la tupla", "senal_alerta": "No conoce el operador modulo"},
                {"texto": "Como evitarias el error cuando b es 0, devolviendo algo razonable en su lugar?", "senal_comprension": "Piensa en un condicional antes de dividir", "senal_alerta": "No ve como anticipar el caso"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Usa cuatro return separados y la funcion termina en el primero.", "probabilidad_estimada": 0.55, "pregunta_diagnostica": "Que hace return apenas se ejecuta dentro de una funcion?"},
            {"descripcion": "Desordena la tupla (devuelve la resta donde va la suma, etc.).", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "En que orden pide la consigna los cuatro resultados?"},
            {"descripcion": "No contempla la division por cero y obtiene ZeroDivisionError.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Que pasa matematicamente cuando dividis por cero?"},
            {"descripcion": "No convierte los inputs a numero y concatena strings en vez de sumar.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Que hace el operador + cuando a y b son strings?"},
            {"descripcion": "Imprime los resultados adentro de la funcion en vez de devolverlos.", "probabilidad_estimada": 0.35, "pregunta_diagnostica": "La consigna pide imprimir o devolver los resultados?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "La funcion tiene que entregar CUATRO resultados juntos. Pensa que estructura de Python te permite agrupar varios valores en uno solo para devolverlos de una. La FUNCION calcula y devuelve; el PRINCIPAL pide los numeros y muestra."},
            {"nivel": 2, "pista": "Necesitas: (1) def operaciones_basicas(a, b): que calcule las cuatro operaciones y haga return (a+b, a-b, a*b, a/b); (2) en el principal, convertir los dos inputs a numero; (3) recibir la tupla y mostrar cada valor etiquetado."},
            {"nivel": 3, "pista": "Estructura guia:\ndef operaciones_basicas(a, b):\n    return (a + b, a - b, a * b, a / b)\n\n# programa principal\na = int(input(\"Ingrese el primer número: \"))\nb = int(input(\"Ingrese el segundo número: \"))\nsuma, resta, multiplicacion, division = operaciones_basicas(a, b)\nprint(f\"Suma: {suma}\")\nprint(f\"Resta: {resta}\")\nprint(f\"Multiplicación: {multiplicacion}\")\nprint(f\"División: {division}\")"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Tu funcion devuelve cuatro operaciones en una tupla. Como la harias mas robusta para que no se rompa cuando el segundo numero es 0? Que estructura de control te permite decidir antes de dividir?"},
        "anti_patrones": [
            {"patron": "Varios return separados", "descripcion": "La funcion termina en el primer return y solo devuelve un valor.", "mensaje_orientacion": "Agrupa los cuatro resultados en una sola tupla y devolvela con un unico return."},
            {"patron": "Tupla desordenada", "descripcion": "Los resultados salen en un orden distinto al pedido.", "mensaje_orientacion": "Respeta el orden: suma, resta, multiplicacion, division."},
            {"patron": "No contemplar division por cero", "descripcion": "Con b = 0 el programa se corta con ZeroDivisionError.", "mensaje_orientacion": "Pensa que deberia pasar cuando b es 0 y como anticiparlo con un condicional."},
            {"patron": "No convertir los inputs", "descripcion": "Con strings, el + concatena y el resto falla.", "mensaje_orientacion": "Convertí los dos inputs a numero antes de operar."},
            {"patron": "Imprimir dentro de la funcion", "descripcion": "La consigna pide devolver una tupla, no imprimir.", "mensaje_orientacion": "La funcion devuelve la tupla; el principal se encarga de mostrar."},
        ],
    },
    {
        "titulo": "E8 - Cálculo del IMC con función",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `calcular_imc(peso, altura)` que reciba el peso (en kg) y la altura "
            "(en metros) y **devuelva** (con `return`) el Índice de Masa Corporal (IMC). En el programa "
            "principal, pedí los datos al usuario y mostrá el resultado con **dos decimales**.\n\n"
            "### Fórmula\n"
            "- IMC = peso / altura²\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y los parámetros `peso` y `altura`.\n"
            "- La función **devuelve** el IMC con `return`, usando la potencia para `altura²`.\n"
            "- En el programa principal: convertí peso y altura a `float`, llamá a la función y mostrá el resultado con exactamente dos decimales.\n"
            "- La salida tiene el formato exacto `IMC: <valor>`.\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese su peso en kg: 70\nIngrese su altura en m: 1.75\nIMC: 22.86\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 8 - Cálculo del IMC\n\n"
            "# 1) Definí la función calcular_imc(peso, altura)\n"
            "# 2) Adentro, devolvé el IMC con la fórmula: peso / altura al cuadrado\n"
            "def calcular_imc(peso, altura):\n"
            "    pass  # reemplazá por el return del IMC\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí peso y altura, convertilos a float\n"
            "#    - llamá a la función y mostrá el resultado con 2 decimales\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "avanzada",
        "test_cases": [
            {"id": "tc1", "name": "Caso tipico", "type": "stdin_stdout", "code": "70\n1.75", "expected": "IMC: 22.86", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Otra persona", "type": "stdin_stdout", "code": "80\n1.80", "expected": "IMC: 24.69", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Altura mas baja", "type": "stdin_stdout", "code": "60\n1.60", "expected": "IMC: 23.44", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con dos parametros", "descripcion": "Define calcular_imc con los parametros peso y altura", "puntaje_max": "2"},
            {"nombre": "Formula correcta", "descripcion": "Aplica peso / altura**2 para calcular el IMC", "puntaje_max": "3"},
            {"nombre": "Uso de return", "descripcion": "Devuelve el IMC con return en lugar de imprimirlo", "puntaje_max": "2"},
            {"nombre": "Conversion a float", "descripcion": "Convierte peso y altura a float para permitir decimales", "puntaje_max": "2"},
            {"nombre": "Salida con dos decimales", "descripcion": "Muestra el IMC con exactamente dos decimales y el formato pedido", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con dos parametros", "return", "** (potencia)", "float()", "input()", ":.2f o round()", "print()"],
            "conceptuales": ["valor de retorno", "potencia para elevar al cuadrado", "conversion de tipos", "formato con dos decimales", "uso del valor devuelto"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno calcula peso / altura sin elevar al cuadrado, no le digas que eleve: preguntale que parte de la formula es altura al cuadrado y como se escribe en Python. Si escribe altura^2, recordale con una pregunta cual es el operador de potencia en Python. Si no convierte a float y la altura con coma falla, guialo a pensar el tipo del input. Si el resultado sale con muchos decimales, preguntale cuantos decimales pide la consigna y como los limitaria.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Que dos datos necesita la funcion y que devuelve a partir de ellos?", "senal_comprension": "Reconoce que recibe peso y altura y devuelve el IMC", "senal_alerta": "Confunde que dato va en cada parametro"},
                {"texto": "Que parte de la formula del IMC es la que mas suele olvidarse?", "senal_comprension": "Identifica que es elevar la altura al cuadrado", "senal_alerta": "Cree que es solo peso dividido altura"},
            ],
            "n2": [
                {"texto": "Como se escribe 'altura al cuadrado' en Python?", "senal_comprension": "Sabe que es altura**2", "senal_alerta": "Escribe altura^2"},
                {"texto": "Por que conviene convertir peso y altura a float y no a int?", "senal_comprension": "Entiende que la altura tiene decimales", "senal_alerta": "Usa int y pierde la parte decimal de la altura"},
            ],
            "n3": [
                {"texto": "Tu IMC da el doble de lo esperado. Estas elevando la altura al cuadrado?", "senal_comprension": "Detecta que falto el **2", "senal_alerta": "No relaciona el resultado con la falta del cuadrado"},
                {"texto": "Aparece 'ValueError: could not convert string to float' con 1.75. Que tecla usaste, coma o punto?", "senal_comprension": "Entiende que float usa punto decimal", "senal_alerta": "No asocia el error con el separador decimal"},
            ],
            "n4": [
                {"texto": "Como extenderias el programa para que ademas indique la categoria del IMC (bajo, normal, alto)?", "senal_comprension": "Piensa en condicionales sobre el valor devuelto", "senal_alerta": "No ve como clasificar el resultado"},
                {"texto": "Si tuvieras la altura en centimetros, que cambio harias antes de aplicar la formula?", "senal_comprension": "Piensa en convertir cm a metros", "senal_alerta": "No ve la necesidad de unificar unidades"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Calcula peso / altura sin elevar la altura al cuadrado.", "probabilidad_estimada": 0.6, "pregunta_diagnostica": "Que parte de la formula del IMC es altura al cuadrado?"},
            {"descripcion": "Escribe altura^2 creyendo que es la potencia.", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "Cual es el operador de potencia en Python?"},
            {"descripcion": "Convierte a int y pierde los decimales de la altura.", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "La altura 1.75 se puede representar con int?"},
            {"descripcion": "Usa coma en vez de punto al ingresar la altura y obtiene ValueError.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "Que separador decimal espera float, coma o punto?"},
            {"descripcion": "No limita a dos decimales y muestra el IMC con muchos digitos.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Cuantos decimales pide la consigna y como los limitarias?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Pensa la formula del IMC y en que orden van los datos. La FUNCION recibe peso y altura y devuelve el IMC; el PRINCIPAL pide los datos y muestra el resultado con dos decimales."},
            {"nivel": 2, "pista": "Necesitas: (1) def calcular_imc(peso, altura): que devuelva peso / altura**2; (2) en el principal, convertir peso y altura a float; (3) llamar a la funcion y mostrar el resultado formateado a dos decimales."},
            {"nivel": 3, "pista": "Estructura guia:\ndef calcular_imc(peso, altura):\n    return peso / altura**2\n\n# programa principal\npeso = float(input(\"Ingrese su peso en kg: \"))\naltura = float(input(\"Ingrese su altura en m: \"))\nprint(f\"IMC: {calcular_imc(peso, altura):.2f}\")"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Ya calculas el IMC. Como extenderias el programa para que ademas te diga la categoria (bajo peso, normal, sobrepeso)? Que estructura de control necesitarias sobre el valor que devuelve la funcion?"},
        "anti_patrones": [
            {"patron": "No elevar la altura al cuadrado", "descripcion": "El IMC da un valor incorrecto (mucho mas grande).", "mensaje_orientacion": "La formula divide por la altura al cuadrado: usa altura**2."},
            {"patron": "Usar el operador ^ para la potencia", "descripcion": "^ no es potencia en Python, da un resultado raro.", "mensaje_orientacion": "El operador de potencia en Python es **."},
            {"patron": "Convertir la altura a int", "descripcion": "Pierde los decimales y la altura queda mal.", "mensaje_orientacion": "Convertí peso y altura a float, no a int."},
            {"patron": "Resultado sin limitar decimales", "descripcion": "Muestra el IMC con demasiados digitos.", "mensaje_orientacion": "Mostralo con dos decimales usando :.2f o round(valor, 2)."},
            {"patron": "Imprimir dentro de la funcion", "descripcion": "La consigna pide devolver el IMC, no imprimirlo.", "mensaje_orientacion": "La funcion devuelve el IMC; el principal lo muestra."},
        ],
    },
    {
        "titulo": "E9 - Conversión de Celsius a Fahrenheit",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `celsius_a_fahrenheit(celsius)` que reciba una temperatura en grados "
            "Celsius y **devuelva** (con `return`) su equivalente en grados Fahrenheit. En el programa "
            "principal, pedí la temperatura al usuario y mostrá el resultado.\n\n"
            "### Fórmula\n"
            "- F = C × 9 / 5 + 32\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y el parámetro `celsius`.\n"
            "- La función **devuelve** el resultado con `return`, aplicando la fórmula con división real (`/`).\n"
            "- En el programa principal: convertí la temperatura a `float`, llamá a la función e imprimí el resultado.\n"
            "- La salida tiene el formato exacto `Fahrenheit: <valor>`.\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese la temperatura en grados Celsius: 25\nFahrenheit: 77.0\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 9 - Celsius a Fahrenheit\n\n"
            "# 1) Definí la función celsius_a_fahrenheit(celsius)\n"
            "# 2) Adentro, devolvé el resultado aplicando: C * 9 / 5 + 32\n"
            "def celsius_a_fahrenheit(celsius):\n"
            "    pass  # reemplazá por el return de la conversión\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí la temperatura y convertila a float\n"
            "#    - llamá a la función e imprimí lo que devuelve\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "intermedia",
        "test_cases": [
            {"id": "tc1", "name": "Temperatura ambiente", "type": "stdin_stdout", "code": "25", "expected": "Fahrenheit: 77.0", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Punto de congelacion", "type": "stdin_stdout", "code": "0", "expected": "Fahrenheit: 32.0", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Punto de ebullicion", "type": "stdin_stdout", "code": "100", "expected": "Fahrenheit: 212.0", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con parametro", "descripcion": "Define celsius_a_fahrenheit con el parametro celsius", "puntaje_max": "2"},
            {"nombre": "Formula correcta", "descripcion": "Aplica C * 9 / 5 + 32 con division real", "puntaje_max": "3"},
            {"nombre": "Uso de return", "descripcion": "Devuelve el resultado con return en lugar de imprimirlo", "puntaje_max": "2"},
            {"nombre": "Conversion a float", "descripcion": "Convierte la temperatura ingresada a float", "puntaje_max": "2"},
            {"nombre": "Salida con el formato pedido", "descripcion": "Imprime el resultado en el formato Fahrenheit: valor", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con parametro", "return", "operadores * / +", "float()", "input()", "print()"],
            "conceptuales": ["valor de retorno", "orden de las operaciones (precedencia)", "division real vs entera", "conversion de tipos", "uso del valor devuelto"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "Si el alumno usa 9//5 (division entera) y el resultado da mal, no le digas que cambie el operador: preguntale cuanto da 9//5 y cuanto deberia dar 9/5. Si arma la formula con parentesis equivocados (por ejemplo 9/(5+32)), pedile que revise el orden de las operaciones. Si no convierte a float y falla con decimales, guialo a pensar el tipo del input. Si imprime adentro en vez de devolver, recordale que la consigna pide devolver.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Que recibe la funcion y que tiene que devolver?", "senal_comprension": "Recibe grados Celsius y devuelve grados Fahrenheit", "senal_alerta": "Confunde el sentido de la conversion"},
                {"texto": "La funcion devuelve el resultado o lo imprime? Que palabra de la consigna lo aclara?", "senal_comprension": "Ve que dice 'devuelve' y usa return", "senal_alerta": "Asume print sin leer la consigna"},
            ],
            "n2": [
                {"texto": "En la formula C * 9 / 5 + 32, en que orden se resuelven las operaciones?", "senal_comprension": "Sabe que primero multiplica y divide, despues suma", "senal_alerta": "Cree que se resuelve de izquierda a derecha sin jerarquia"},
                {"texto": "Para que la division conserve los decimales, usas / o //?", "senal_comprension": "Usa / (division real)", "senal_alerta": "Usa // y pierde decimales"},
            ],
            "n3": [
                {"texto": "Con 25 esperabas 77.0 pero te dio otro numero. Revisaste si usaste / o //?", "senal_comprension": "Detecta que 9//5 da 1 y descuadra la formula", "senal_alerta": "No distingue / de //"},
                {"texto": "Tu resultado da raro. Donde pusiste los parentesis en la formula?", "senal_comprension": "Revisa la precedencia y el orden de operaciones", "senal_alerta": "Agrupa mal con parentesis"},
            ],
            "n4": [
                {"texto": "Como escribirias la funcion inversa, de Fahrenheit a Celsius?", "senal_comprension": "Despeja C de la formula", "senal_alerta": "No sabe invertir la formula"},
                {"texto": "Como mostrarias el resultado redondeado a un decimal, manteniendo la funcion intacta?", "senal_comprension": "Aplica el formato en el principal", "senal_alerta": "Mete el formato dentro de la funcion innecesariamente"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Usa 9//5 (division entera, da 1) y la conversion sale mal.", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Cuanto da 9//5 y cuanto deberia dar 9/5?"},
            {"descripcion": "Arma la formula con parentesis equivocados y altera el orden de operaciones.", "probabilidad_estimada": 0.4, "pregunta_diagnostica": "En que orden se resuelven multiplicacion, division y suma?"},
            {"descripcion": "Confunde el sentido de la conversion (aplica la formula inversa).", "probabilidad_estimada": 0.35, "pregunta_diagnostica": "La funcion va de Celsius a Fahrenheit o al reves?"},
            {"descripcion": "No convierte el input a float y falla con temperaturas decimales.", "probabilidad_estimada": 0.45, "pregunta_diagnostica": "Que tipo devuelve input() y como lo convertis?"},
            {"descripcion": "Imprime adentro de la funcion en vez de devolver.", "probabilidad_estimada": 0.35, "pregunta_diagnostica": "La consigna pide imprimir o devolver el resultado?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Tene a mano la formula de conversion y pensa el orden de las operaciones. La FUNCION recibe los grados Celsius y devuelve los Fahrenheit; el PRINCIPAL pide la temperatura y la muestra."},
            {"nivel": 2, "pista": "Necesitas: (1) def celsius_a_fahrenheit(celsius): que devuelva celsius * 9 / 5 + 32 (con division real); (2) en el principal, convertir el input a float; (3) llamar a la funcion e imprimir lo que devuelve."},
            {"nivel": 3, "pista": "Estructura guia:\ndef celsius_a_fahrenheit(celsius):\n    return celsius * 9 / 5 + 32\n\n# programa principal\ncelsius = float(input(\"Ingrese la temperatura en grados Celsius: \"))\nprint(f\"Fahrenheit: {celsius_a_fahrenheit(celsius)}\")"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Tu funcion pasa de Celsius a Fahrenheit. Como escribirias la funcion inversa (de Fahrenheit a Celsius) despejando la formula? Que operaciones cambian de lugar?"},
        "anti_patrones": [
            {"patron": "Usar 9//5 en la formula", "descripcion": "La division entera da 1 y descuadra la conversion.", "mensaje_orientacion": "Usa division real con / para conservar el 1.8."},
            {"patron": "Parentesis mal ubicados", "descripcion": "Altera el orden de las operaciones y da un resultado incorrecto.", "mensaje_orientacion": "Respeta la formula C * 9 / 5 + 32 sin agrupar de mas."},
            {"patron": "Invertir el sentido de la conversion", "descripcion": "Aplica la formula de Fahrenheit a Celsius por error.", "mensaje_orientacion": "Verifica que vas de Celsius a Fahrenheit segun la consigna."},
            {"patron": "No convertir a float", "descripcion": "Falla o trunca con temperaturas decimales.", "mensaje_orientacion": "Convertí la temperatura con float() antes de operar."},
            {"patron": "Imprimir dentro de la funcion", "descripcion": "La consigna pide devolver, no imprimir.", "mensaje_orientacion": "La funcion devuelve el resultado; el principal lo imprime."},
        ],
    },
    {
        "titulo": "E10 - Promedio de tres números con función",
        "enunciado_md": (
            "## Consigna\n"
            "Escribí una función llamada `calcular_promedio(a, b, c)` que reciba tres números y **devuelva** "
            "(con `return`) el promedio de los tres. En el programa principal, pedí los tres números al "
            "usuario y mostrá el resultado usando la función.\n\n"
            "### Fórmula\n"
            "- Promedio = (a + b + c) / 3\n\n"
            "### Requisitos\n"
            "- Definí la función con `def` y los tres parámetros.\n"
            "- La función **devuelve** el promedio con `return`. Cuidado con los **paréntesis**: hay que sumar los tres antes de dividir.\n"
            "- En el programa principal: convertí los tres números, llamá a la función e imprimí el resultado.\n"
            "- La salida tiene el formato exacto `Promedio: <valor>`.\n\n"
            "### Ejemplo de ejecución\n"
            "```text\nIngrese el primer número: 8\nIngrese el segundo número: 6\nIngrese el tercer número: 10\nPromedio: 8.0\n```"
        ),
        "inicial_codigo": (
            "# Ejercicio 10 - Promedio de tres números\n\n"
            "# 1) Definí la función calcular_promedio(a, b, c)\n"
            "# 2) Adentro, devolvé el promedio: la SUMA de los tres dividida 3\n"
            "#    (ojo con los paréntesis: primero se suman, después se divide)\n"
            "def calcular_promedio(a, b, c):\n"
            "    pass  # reemplazá por el return del promedio\n\n"
            "# 3) En el programa principal:\n"
            "#    - pedí los tres números y convertilos a número\n"
            "#    - llamá a la función e imprimí lo que devuelve\n"
        ),
        "unidad_tematica": "funciones",
        "dificultad": "intermedia",
        "test_cases": [
            {"id": "tc1", "name": "Tres numeros", "type": "stdin_stdout", "code": "8\n6\n10", "expected": "Promedio: 8.0", "is_public": True, "weight": 1},
            {"id": "tc2", "name": "Consecutivos", "type": "stdin_stdout", "code": "4\n5\n6", "expected": "Promedio: 5.0", "is_public": True, "weight": 1},
            {"id": "tc3", "name": "Multiplos de diez", "type": "stdin_stdout", "code": "10\n20\n30", "expected": "Promedio: 20.0", "is_public": False, "weight": 1},
        ],
        "rubrica": {"criterios": [
            {"nombre": "Definicion con tres parametros", "descripcion": "Define calcular_promedio con los parametros a, b y c", "puntaje_max": "2"},
            {"nombre": "Formula con parentesis correctos", "descripcion": "Suma los tres numeros antes de dividir por 3", "puntaje_max": "3"},
            {"nombre": "Uso de return", "descripcion": "Devuelve el promedio con return en lugar de imprimirlo", "puntaje_max": "2"},
            {"nombre": "Conversion de los inputs", "descripcion": "Convierte los tres numeros a int o float antes de operar", "puntaje_max": "2"},
            {"nombre": "Salida con el formato pedido", "descripcion": "Imprime el resultado en el formato Promedio: valor", "puntaje_max": "1"},
        ]},
        "prerequisitos": {
            "sintacticos": ["def con tres parametros", "return", "parentesis para agrupar", "operador / (division real)", "int() o float()", "input()", "print()"],
            "conceptuales": ["valor de retorno", "precedencia de operadores", "uso de parentesis para forzar el orden", "conversion de tipos", "uso del valor devuelto"],
        },
        "tutor_rules": {
            "prohibido_dar_solucion": True,
            "forzar_pregunta_antes_de_hint": True,
            "nivel_socratico_minimo": 2,
            "instrucciones_adicionales": "El error mas comun es escribir a + b + c / 3 sin parentesis. Si el promedio sale demasiado grande, no le digas que ponga parentesis: preguntale, segun la precedencia, que se calcula primero en a + b + c / 3 y sobre que numero se aplica la division. Si no convierte los inputs y concatena strings, guialo a pensar que hace el + con texto. Si imprime adentro en vez de devolver, recordale que la consigna pide devolver.",
        },
        "banco_preguntas": {
            "n1": [
                {"texto": "Que tiene que recibir la funcion y que devuelve a partir de esos datos?", "senal_comprension": "Recibe tres numeros y devuelve su promedio", "senal_alerta": "No tiene claro como se calcula un promedio"},
                {"texto": "Como se calcula el promedio de tres numeros, en palabras?", "senal_comprension": "Suma los tres y divide por 3", "senal_alerta": "Divide solo uno o no suma todos"},
            ],
            "n2": [
                {"texto": "En la expresion a + b + c / 3, sobre que numero se aplica la division segun la precedencia?", "senal_comprension": "Entiende que la division se aplica solo a c", "senal_alerta": "Cree que primero se suma todo y despues se divide"},
                {"texto": "Que tenes que agregar para asegurarte de que primero se sumen los tres y despues se divida?", "senal_comprension": "Sabe que van parentesis alrededor de la suma", "senal_alerta": "No ve la necesidad de los parentesis"},
            ],
            "n3": [
                {"texto": "Tu promedio da mucho mas grande de lo esperado. Pusiste parentesis alrededor de la suma?", "senal_comprension": "Detecta que sin parentesis solo se divide c", "senal_alerta": "No relaciona el error con la precedencia"},
                {"texto": "El programa concatena los numeros en vez de sumarlos (8610). Que tipo siguen siendo a, b y c?", "senal_comprension": "Reconoce que son strings sin convertir", "senal_alerta": "No relaciona la concatenacion con el tipo del input"},
            ],
            "n4": [
                {"texto": "Como adaptarias la funcion para que calcule el promedio de una cantidad variable de numeros?", "senal_comprension": "Piensa en una lista y en sum()/len()", "senal_alerta": "No ve como generalizar a N numeros"},
                {"texto": "Como mostrarias el promedio redondeado a dos decimales sin tocar la funcion?", "senal_comprension": "Aplica el formato en el principal", "senal_alerta": "Mete el redondeo dentro de la funcion"},
            ],
        },
        "misconceptions": [
            {"descripcion": "Escribe a + b + c / 3 sin parentesis y solo divide el ultimo numero.", "probabilidad_estimada": 0.65, "pregunta_diagnostica": "Segun la precedencia, sobre que numero se aplica la division en a + b + c / 3?"},
            {"descripcion": "No convierte los inputs y el + concatena los strings (8610 en vez de sumar).", "probabilidad_estimada": 0.5, "pregunta_diagnostica": "Que hace el operador + cuando los datos son texto?"},
            {"descripcion": "Divide por una cantidad equivocada (por 2 o por otro numero).", "probabilidad_estimada": 0.3, "pregunta_diagnostica": "Cuantos numeros estas promediando y por cuanto deberias dividir?"},
            {"descripcion": "Imprime el promedio adentro de la funcion en vez de devolverlo.", "probabilidad_estimada": 0.35, "pregunta_diagnostica": "La consigna pide imprimir o devolver el promedio?"},
            {"descripcion": "Suma solo dos de los tres numeros.", "probabilidad_estimada": 0.25, "pregunta_diagnostica": "Estas incluyendo los tres numeros en la suma?"},
        ],
        "respuesta_pista": [
            {"nivel": 1, "pista": "Pensa como se calcula un promedio: primero se suman TODOS los numeros y despues se divide por la cantidad. La FUNCION recibe los tres y devuelve el promedio; el PRINCIPAL pide los numeros y muestra el resultado."},
            {"nivel": 2, "pista": "Necesitas: (1) def calcular_promedio(a, b, c): que devuelva (a + b + c) / 3, con los parentesis alrededor de la suma; (2) en el principal, convertir los tres inputs a numero; (3) llamar a la funcion e imprimir lo que devuelve."},
            {"nivel": 3, "pista": "Estructura guia:\ndef calcular_promedio(a, b, c):\n    return (a + b + c) / 3\n\n# programa principal\na = float(input(\"Ingrese el primer número: \"))\nb = float(input(\"Ingrese el segundo número: \"))\nc = float(input(\"Ingrese el tercer número: \"))\nprint(f\"Promedio: {calcular_promedio(a, b, c)}\")"},
        ],
        "heuristica_cierre": {"tests_min_pasados": 2, "heuristica": "Tu funcion promedia tres numeros fijos. Como la generalizarias para promediar una cantidad cualquiera de numeros usando una lista? Que funciones de Python te ayudarian a sumar y contar?"},
        "anti_patrones": [
            {"patron": "Olvidar los parentesis de la suma", "descripcion": "Con a + b + c / 3 solo se divide el ultimo numero y el promedio sale mal.", "mensaje_orientacion": "Agrupa la suma entre parentesis: (a + b + c) / 3."},
            {"patron": "No convertir los inputs", "descripcion": "Con strings el + concatena en vez de sumar.", "mensaje_orientacion": "Convertí los tres inputs a numero antes de operar."},
            {"patron": "Dividir por un numero equivocado", "descripcion": "El promedio no representa a los tres numeros.", "mensaje_orientacion": "Dividi por la cantidad de numeros: en este caso, 3."},
            {"patron": "Imprimir dentro de la funcion", "descripcion": "La consigna pide devolver el promedio, no imprimirlo.", "mensaje_orientacion": "La funcion devuelve el promedio; el principal lo imprime."},
            {"patron": "Sumar solo dos numeros", "descripcion": "Queda afuera uno de los tres valores.", "mensaje_orientacion": "Asegurate de incluir a, b y c en la suma."},
        ],
    },
]


def _req(method: str, path: str, body: dict | None = None):
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read() or b"{}")


def existing_titles() -> set[str]:
    try:
        _, data = _req("GET", f"/api/v1/ejercicios?materia_id={MATERIA_ID}&limit=200")
    except Exception as e:  # noqa: BLE001
        print(f"WARN: no se pudo leer el banco existente ({e}); sigo sin dedupe.")
        return set()
    items = data.get("data", data if isinstance(data, list) else [])
    return {e.get("titulo") for e in items}


def main() -> int:
    print(f"API_BASE={API_BASE}\nMATERIA_ID={MATERIA_ID}  created_by={USER_ID}\n")
    have = existing_titles()
    creados = 0
    total = len(EJERCICIOS)
    for i, base in enumerate(EJERCICIOS, 1):
        ej = {**base, "materia_id": MATERIA_ID, "created_via_ai": False}
        titulo = ej["titulo"]
        if titulo in have:
            print(f"[{i}/{total}] SKIP (ya existe): {titulo}")
            continue
        try:
            status, res = _req("POST", "/api/v1/ejercicios", ej)
            creados += 1
            print(f"[{i}/{total}] OK {status}: {titulo} -> id={res.get('id')}")
        except urllib.error.HTTPError as e:  # noqa: PERF203
            detalle = e.read().decode()[:500]
            print(f"[{i}/{total}] FALLO {e.code}: {titulo}\n  {detalle}")
            if i == 1 and e.code in (422, 500):
                print("\nABORTO: el primer ejercicio fallo. Probablemente el enum "
                      "'funciones' aun no esta aplicado (falta el redeploy del "
                      "academic-service con la migracion 20260604_0001). Reintentar "
                      "cuando el deploy termine.")
                return 1
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{total}] ERROR: {titulo}: {e}")
    print(f"\nListo: {creados} creados, {total - creados} saltados/fallidos de {total}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
