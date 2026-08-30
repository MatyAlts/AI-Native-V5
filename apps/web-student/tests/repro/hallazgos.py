"""
Reproduccion de los hallazgos del editor de Python (web-student).

Correr:  python3 apps/web-student/tests/repro/hallazgos.py

Cada bloque imprime QUE pasa y con QUE evidencia. Ninguno modifica codigo de
produccion: todo sale de extraer el runtime real de `CodeEditor.tsx` (ver
`arnes.py`) y ejercitarlo con entradas guionadas.
"""

from __future__ import annotations

import time

import arnes

SEP = "=" * 78


def titulo(n: int, texto: str) -> None:
    print(f"\n{SEP}\nH{n}. {texto}\n{SEP}")


# ---------------------------------------------------------------------------
# El ejercicio del video, reducido: validacion en bucle con reintento.
# Es el patron que ensena la catedra: while True + try/except + continue.
# ---------------------------------------------------------------------------
CAJA_KIOSCO = '''
productos = []
cantidad = int(input("Cuantos productos? "))
for i in range(cantidad):
    nombre = input("Nombre del producto: ")
    while True:
        try:
            precio = float(input("Precio: "))
            if precio <= 0:
                print("El precio tiene que ser mayor a 0.")
                continue
            break
        except ValueError:
            print("Eso no es un numero. Proba de nuevo.")
    productos.append((nombre, precio))
print("Total:", sum(p for _, p in productos))
'''


def h1_cancelar_es_bucle_infinito() -> None:
    titulo(1, "Cancelar (Esc / boton Cancelar) = bucle infinito sin salida")
    term = arnes.Terminal(respuestas=["1", "Alfajor"], max_prompts=3000)
    g = arnes.montar_con_print(term)
    t0 = time.monotonic()
    err = arnes.correr(CAJA_KIOSCO, term, globals_py=g)
    dt = time.monotonic() - t0
    print(f"window.prompt() disparados: {len(term.prompts)}")
    print(f"tiempo de pared: {dt:.2f}s")
    print(f"lo que escapo: {type(err).__name__ if err else 'nada'}: {err}")
    print()
    print("Lectura: al 3er prompt el alumno cancela. `window.prompt(...) ?? \"\"`")
    print("convierte el `null` del Cancelar en cadena vacia -> float('') lanza")
    print("ValueError -> el except del alumno imprime y vuelve a preguntar.")
    print("No hay forma de salir: ni Cancelar, ni Esc, ni el watchdog.")
    print(f"El repro corto solo por su tope artificial de {term.max_prompts}.")


def h2_watchdog_nunca_dispara() -> None:
    titulo(2, "El watchdog no puede cortar un bucle que pide input()")
    codigo = 'while True:\n    x = input("dato: ")\n'
    term = arnes.Terminal(cancelar_siempre=True, max_prompts=2000)
    g = arnes.montar_con_print(term)
    t0 = time.monotonic()
    err = arnes.correr(codigo, term, globals_py=g)
    dt = time.monotonic() - t0
    print(f"prompts: {len(term.prompts)} en {dt:.2f}s")
    print(f"escapo: {type(err).__name__ if err else 'nada'}: {err}")
    print()
    print("`__tutor_input` hace pause_deadline() antes y reset_deadline() despues.")
    print(f"El presupuesto vuelve a {arnes.EXECUTION_TIMEOUT_SECONDS}s COMPLETOS en cada")
    print("vuelta, y el tramo de computo entre dos inputs dura microsegundos:")
    print("el deadline nunca se alcanza. TimeoutError nunca se levanta.")
    print()
    print("En el navegador esto es peor: si el alumno tilda la casilla")
    print("'impedir que esta pagina cree mas dialogos' (Chrome/Firefox la ofrecen")
    print("tras varios prompt() seguidos), window.prompt pasa a devolver null al")
    print("instante y el bucle gira a velocidad de maquina, sin dialogos, sin")
    print("watchdog y sin boton de Detener -> la pestana queda muerta.")


def h3_pared_de_texto_en_la_ventanita() -> None:
    titulo(3, "input() sin texto: la ventanita muestra TODA la salida acumulada")
    # Como lo escribe medio curso de primer ano: el print aparte, el input pelado.
    codigo = """
cantidad = int(input())
for i in range(cantidad):
    print("Producto", i + 1)
    print("Ingresa el nombre:")
    nombre = input()
    print("Ingresa el precio:")
    precio = input()
    print("Ingresa el descuento:")
    desc = input()
print("listo")
"""
    term = arnes.Terminal(respuestas=["7"] + ["x"] * 30, max_prompts=200)
    # `montar_con_print` es el espejo del setStdout({batched}) del componente.
    g = arnes.montar_con_print(term)
    arnes.correr(codigo, term, globals_py=g)
    largos = [len(p) for p in term.prompts]
    print(f"prompts disparados: {len(term.prompts)}")
    print(f"largo del mensaje: 1o={largos[0]}  ultimo={largos[-1]}  chars")
    print(f"lineas en el ultimo mensaje: {term.prompts[-1].count(chr(10)) + 1}")
    print()
    print("--- ULTIMO MENSAJE, tal cual lo recibe window.prompt() ---")
    print(term.prompts[-1])
    print("--- fin ---")
    print()
    print("Lectura: `guia = inline || outputBufferRef.current.trim()`. Sin prompt")
    print("inline, la 'guia' es el buffer ENTERO — incluidos los ecos de todo lo")
    print("que el alumno ya tipeo. La pregunta real ('Ingresa el descuento:')")
    print("queda sepultada al final de una pared que ademas crece sola.")
    print("(Si el navegador ademas recorta mensajes largos de prompt(), lo que")
    print("se pierde es el final = la pregunta. No lo verifique en navegador.)")


def h4_buffer_sin_tope() -> None:
    titulo(4, "outputBufferRef / setOutput no tienen tope")
    codigo = "for i in range(200000):\n    print('linea', i)\n"
    term = arnes.Terminal()
    g = arnes.montar_con_print(term)
    err = arnes.correr(codigo, term, globals_py=g)
    mb = len(term.buffer) / 1024 / 1024
    print(f"escapo: {type(err).__name__ if err else 'nada'}")
    print(f"buffer acumulado: {mb:.2f} MB en un solo `for` de 200k prints")
    print()
    print("No hay `slice`, ni tope de chars, ni de lineas: ni en outputBufferRef")
    print("ni en el state `output`, ni en el historial de corridas (que guarda")
    print("hasta 8 salidas COMPLETAS). El mismo string vive 3+ veces en memoria")
    print("y se re-renderiza entero en un <pre>.")


def h5_trace_por_opcode_castiga_bucles_legitimos() -> None:
    titulo(5, "El tracing por opcode multiplica el costo: falso 'bucle infinito'")
    codigo = "s = 0\nfor i in range(N):\n    s += i * i\n"
    N = 50_000  # chico a proposito: tiene que entrar en el presupuesto

    t0 = time.monotonic()
    exec(compile(codigo, "<x>", "exec"), {"N": N})
    libre = time.monotonic() - t0

    term = arnes.Terminal()
    g = arnes.montar(term)
    g["N"] = N
    t0 = time.monotonic()
    err = arnes.correr(codigo, term, globals_py=g)
    trazado = time.monotonic() - t0

    factor = trazado / max(libre, 1e-9)
    print(f"for de {N:,} vueltas, sin watchdog : {libre:.4f}s")
    print(f"el mismo, con _tutor_trace por opcode: {trazado:.4f}s")
    print(f"factor de castigo (CPython)          : x{factor:.0f}")
    print(f"escapo: {type(err).__name__ if err else 'nada'}: {err or ''}")
    print()
    presupuesto = arnes.EXECUTION_TIMEOUT_SECONDS
    techo = int(N * presupuesto / max(trazado, 1e-9))
    sin_watchdog = int(N * presupuesto / max(libre, 1e-9))
    print(f"Techo con {presupuesto}s de presupuesto, EN CPYTHON:")
    print(f"  con el watchdog puesto : ~{techo:,} vueltas de este bucle")
    print(f"  sin el watchdog        : ~{sin_watchdog:,}")
    print("Pyodide-WASM corre bastante mas lento que CPython nativo, asi que el")
    print("techo real en el navegador es MENOR que ese numero. Verificacion:")

    # Y la prueba directa: un bucle que sin watchdog tarda menos de 1s, con el
    # watchdog puesto se come el presupuesto entero y muere como "infinito".
    grande = max(techo * 2, N * 4)
    t0 = time.monotonic()
    exec(compile(codigo, "<x>", "exec"), {"N": grande})
    libre_grande = time.monotonic() - t0
    term2 = arnes.Terminal()
    g2 = arnes.montar(term2)
    g2["N"] = grande
    err2 = arnes.correr(codigo, term2, globals_py=g2)
    print()
    print(f"  `for i in range({grande:,})` tarda {libre_grande:.2f}s en Python normal")
    print(f"  y en el editor termina asi -> {type(err2).__name__ if err2 else 'OK'}: {err2 or ''}")
    print()
    print("O sea: un bucle que en la maquina del alumno corre en menos de un")
    print("segundo, en el editor le dice 'Revisa si tenes un bucle infinito'.")


def h8_estado_que_sobrevive_entre_corridas() -> None:
    titulo(8, "Las variables sobreviven de una corrida a la otra")
    term = arnes.Terminal()
    g = arnes.montar_con_print(term)
    arnes.correr("mi_variable = 42\nprint('corrida 1')", term, globals_py=g)
    err = arnes.correr("print('corrida 2 ve:', mi_variable)", term, globals_py=g)
    print(f"escapo en la 2a corrida: {type(err).__name__ if err else 'nada'}")
    print(f"consola: {term.buffer!r}")
    print()
    print("`__tutor_run_student_code` hace `exec(compile(code, ...), globals())`,")
    print("y el componente reusa la MISMA instancia de Pyodide en toda la sesion.")
    print("Nada se limpia entre corridas: variables, funciones e imports quedan.")
    print("El alumno borra la linea que definia la variable, aprieta Ejecutar, le")
    print("sigue andando — y cuando entrega, el mismo codigo revienta con")
    print("NameError. El comentario del codigo dice que la persistencia es a")
    print("proposito ('preserva que las variables persistan entre corridas'), pero")
    print("no hay ningun boton de 'reiniciar el interprete' en la UI, y el runner")
    print("de tests SI usa namespace fresco: los dos caminos no coinciden.")


def h9_la_salida_entera_viaja_al_CTR() -> None:
    titulo(9, "La salida sin tope viaja al CTR, que es append-only")
    print("Leido (packages/contracts/.../ctr/events.py y EpisodePage.tsx):")
    print()
    print("  onCodeExecuted -> payload { stdout: result.output, ... }")
    print("  CodigoEjecutadoPayload.stdout: str | None = None   <- sin max_length")
    print()
    print("Otros payloads del mismo archivo SI acotan (`max_length=500` en los 3")
    print("campos de la reflexion), asi que el limite faltante aca no es una")
    print("politica del contrato: es un hueco. Y el CTR es append-only: lo que")
    print("entra no se borra ni se trunca despues.")
    print(f"Con el H4 medido, una sola corrida puede meter megabytes en la cadena.")


def h6_print_end_no_llega_a_la_ventanita() -> None:
    titulo(6, "print(..., end='') antes de input(): la guia no lo incluye")
    print("Dos cosas encadenadas, ambas leidas en el codigo (no simuladas aca):")
    print()
    print("a) `setStdout({batched})` hace `outputBufferRef.current += `${text}\\n``")
    print("   — agrega SIEMPRE un salto de linea. Un `print('*', end='')` en un")
    print("   bucle (piramide de asteriscos, clasico de primer ano) sale con la")
    print("   forma cambiada respecto de Python de verdad.")
    print()
    print("b) `__tutor_input` NO hace `sys.stdout.flush()`. El `input()` de CPython")
    print("   si vacia stdout antes de leer; este override no. Entonces con")
    print()
    print("       print('Precio del producto 7: ', end='')")
    print("       precio = input()")
    print()
    print("   la linea parcial sigue en el buffer de Pyodide, NO esta en")
    print("   outputBufferRef, y la ventanita muestra como guia la salida VIEJA:")
    print("   le pregunta al alumno por el producto 6 cuando va por el 7.")


def h7_la_consola_no_se_pinta_durante_la_corrida() -> None:
    titulo(7, "Durante toda la corrida la consola queda en blanco")
    print("Leido, no reproducido aca (es del lado React, ver el test .tsx):")
    print()
    print("`runCode` hace `setOutput('')` y despues llama a `runPythonAsync`. Para")
    print("codigo sincrono, Pyodide ejecuta TODO el programa del alumno en un solo")
    print("bloque sincrono del main thread, y `window.prompt` bloquea sin ceder el")
    print("event loop. React no puede re-renderizar hasta que el programa termina.")
    print()
    print("Consecuencia: los `print()` de los productos 1..6 no se ven mientras el")
    print("alumno esta en el producto 7. Por eso existe el parche de la 'guia'")
    print("(H3) — el parche tapa el sintoma de esto.")


def main() -> None:
    h1_cancelar_es_bucle_infinito()
    h2_watchdog_nunca_dispara()
    h3_pared_de_texto_en_la_ventanita()
    h4_buffer_sin_tope()
    h5_trace_por_opcode_castiga_bucles_legitimos()
    h8_estado_que_sobrevive_entre_corridas()
    h9_la_salida_entera_viaja_al_CTR()
    h6_print_end_no_llega_a_la_ventanita()
    h7_la_consola_no_se_pinta_durante_la_corrida()


if __name__ == "__main__":
    main()
