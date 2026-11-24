# Perfil de PSeInt del intérprete (HU-030)

El intérprete de `@platform/pseint` sigue el perfil **por defecto de PSeInt
oficial 20250314** (el que usa `pseint` sin `--profile`). La decisión y su
porqué están en `docs/adr/064-pseint-interprete-propio.md`.

## Árbitro

Ante una duda, manda PSeInt oficial 20250314 (Linux 64 bits,
`pseint-l64-20250314.tgz` de SourceForge). El corpus de paridad
(`tests/paridad/casos/`) se corre contra el binario oficial con
`tests/paridad/generar_esperados.py`, y `tests/paridad.test.ts` exige que
nuestra salida sea idéntica byte a byte. Para averiguar un comportamiento:

```bash
pseint archivo.psc --nouser --fortest --rawerrors < entrada.txt
```

Los `.psc` se le pasan en latin-1. Cada `Leer` escribe el indicador `> `, que
no es salida del algoritmo y no se compara.

## Reglas del perfil

- **Estructura**: `Algoritmo nombre … FinAlgoritmo` (o `Proceso … FinProceso`).
  Las funciones (`Funcion r <- nombre(params) … FinFuncion`, `SubProceso`,
  `SubAlgoritmo`) van fuera del algoritmo, antes o después. Solo un algoritmo.
- **Mayúsculas y tildes**: las palabras clave y los nombres no distinguen
  mayúsculas ni tildes (`Según` = `SEGUN`, `total` = `TOTAL`). La `ñ` cuenta.
- **Variables**: `Definir` no es obligatorio. Una variable definida empieza en
  `0`, `""` o `Falso` según su tipo. Una sin definir toma el tipo del primer
  valor que recibe, y después no puede cambiarlo. Tipos: `Entero` (32 bits),
  `Real` (`Numero`, `Numerico`), `Caracter` (`Texto`, `Cadena`), `Logico`.
  A un `Entero` no se le puede asignar un valor con decimales.
- **Nombres**: una variable no puede llamarse como el algoritmo ni como una
  función, ni como una palabra reservada. `y`, `o`, `no` y `mod` son
  reservadas: `Definir x, y` es error de sintaxis.
- **Asignación**: `<-` (o `:=`). **`=` no asigna**: `x = 3` es error de
  sintaxis; `=` solo compara.
- **Arreglos**: `Dimension v[n]` o `Dimension m[f, c]`. **Los arreglos empiezan
  en 1**: `v[0]` y `v[n+1]` son errores de ejecución. Se pasan a las funciones
  por referencia salvo que el parámetro diga `Por Valor`.
- **Parámetros**: por valor salvo `Por Referencia`. Las funciones no ven las
  variables del algoritmo.
- **Operadores**: `+ - * / ^ MOD` (`%`), `= <> < > <= >=`, `Y O NO`
  (`& | ~`). `/` siempre divide con decimales. `^` asocia a izquierda
  (`2^3^2` = 64) y liga más que el menos unario (`-2^2` = -4). `NO` liga menos
  que las comparaciones (`NO n = 5` es `NO (n = 5)`). `Y` liga más que `O`.
  `Y` y `O` cortan apenas saben el resultado. `+` también concatena textos.
- **Comparaciones**: dos números son iguales si difieren en menos de 1e-11
  (`0.1 + 0.2 = 0.3` es Verdadero). Los textos se comparan distinguiendo
  mayúsculas. Comparar valores de distinto tipo es error.
- **Tipos en expresiones de literales**: si el choque de tipos se ve sin
  ejecutar (`"a" + 1`, `3 Y Verdadero`, `7.5 MOD 2`), es error de sintaxis.
- **Escribir**: `Escribir a, b` escribe los valores **pegados, sin
  separador**, y salta de línea al final salvo `Sin Saltar` (o `Sin Bajar`).
  Los lógicos salen `VERDADERO`/`FALSO`.
- **Números**: se escriben como `printf("%.10f")` sin los ceros del final:
  `7/2` → `3.5`, `1/3` → `0.3333333333`, `10/5` → `2`, `2^60` sale entero.
- **Para**: sin `Con Paso`, si el inicio es mayor que el final **cuenta hacia
  atrás** (`Para i <- 1 Hasta 0` corre con 1 y con 0). Con paso explícito
  positivo y el inicio mayor, no corre. La variable de control no se puede
  modificar dentro del ciclo, y al terminar queda en 0.
- **Leer**: un valor por línea; `Leer a, b` pide dos. A un `Entero` hay que
  darle un entero (`2.5` o `abc` son error de ejecución en la línea del
  `Leer`); a un `Real`, un número sin espacios; a un `Logico`, `Verdadero`,
  `Falso`, `V`, `F`, `1` o `0`. Un dato vacío es 0 para los números. A una
  variable sin definir le queda número si lo que se ingresó es un número, y
  texto si no.
- **Segun**: `Segun x Hacer`, opciones `valor[, valor]:` y
  `De Otro Modo:`, `FinSegun`.
- **Repetir**: termina con `Hasta Que cond` o `Mientras Que cond`.
- `Hacer` (en `Para`, `Mientras`, `Segun`) y `Entonces` se pueden omitir.
- **Errores de sintaxis**: se detectan antes de ejecutar y no se ejecuta nada.
  Si falta cerrar una estructura (`Si` sin `FinSi`), la línea del error es la
  de la estructura abierta; un cierre que sobra se informa en su línea.
- **Funciones predefinidas**: `trunc`, `redon` (redondea .5 alejándose del
  cero), `raiz`/`rc`, `abs`, `ln`, `exp`, `sen`, `cos`, `tan`, `asen`,
  `acos`, `atan`, `azar(n)` (entero de 0 a n-1), `aleatorio(a, b)`,
  `Longitud`, `Subcadena(s, desde, hasta)` (desde 1, ambos inclusive),
  `Mayusculas`, `Minusculas`, `Concatenar`, `ConvertirANumero`,
  `ConvertirATexto`, y la constante `PI`.
- `Limpiar Pantalla`, `Esperar Tecla` y `Esperar n Segundos` no hacen nada (como
  `--fortest`).

## Divergencias deliberadas con PSeInt oficial

1. **`Leer` sin datos de entrada.** Con la entrada por adelantado
   (`ejecutarConEntrada`: casos de prueba, Probar y servidor), si `Leer` pide un
   valor y la entrada se terminó, es un **error de ejecución** en la línea del
   `Leer`. PSeInt oficial lee vacío y sigue. Un caso de prueba con menos datos
   de los que pide el algoritmo es un error del algoritmo o del caso, y no se
   deja pasar en silencio.
2. **Variables sin valor.** Usar una variable que nunca recibió valor (ni
   `Definir`, ni `<-`, ni `Leer`), o un elemento de un arreglo sin tipo que
   nunca se asignó, es un error de ejecución con un mensaje claro. PSeInt
   oficial lo trata como vacío o 0 sin avisar.
3. **Tipos de variables en la sintaxis.** PSeInt oficial infiere el tipo de
   las variables antes de ejecutar y marca algunos choques como error de
   sintaxis (`Definir s Como Caracter` y después `s <- 3`). Acá esos choques
   son errores de ejecución en la misma línea; solo las expresiones hechas de
   literales se revisan antes de ejecutar.
4. **Mensajes de error.** Los textos son propios, en castellano y pensados para
   el alumno; la paridad exige la misma **línea**, no el mismo texto ni el
   número de error de PSeInt.
5. **Límite de pasos.** Una ejecución corta a los `MAX_PASOS_POR_DEFECTO`
   (2.000.000) pasos con estado `limite_excedido`, para que un ciclo infinito
   no congele el navegador ni ocupe el sandbox.
6. **Recursión.** Más de 1.000 llamadas anidadas es error de ejecución.
