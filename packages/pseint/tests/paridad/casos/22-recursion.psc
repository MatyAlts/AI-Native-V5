Funcion r <- factorial(n)
	Definir r Como Entero
	Si n <= 1 Entonces
		r <- 1
	SiNo
		r <- n * factorial(n - 1)
	FinSi
FinFuncion

Algoritmo recursion
	Definir i Como Entero
	Para i <- 0 Hasta 6 Hacer
		Escribir i, "! = ", factorial(i)
	FinPara
FinAlgoritmo
