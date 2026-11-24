Funcion r <- cuadrado(x)
	Definir r Como Real
	r <- x * x
FinFuncion

Funcion r <- maximo(a, b)
	Definir r Como Real
	Si a > b Entonces
		r <- a
	SiNo
		r <- b
	FinSi
FinFuncion

Algoritmo funciones
	Escribir cuadrado(4)
	Escribir maximo(3, 9)
	Escribir cuadrado(maximo(2, 3)) + 1
FinAlgoritmo
