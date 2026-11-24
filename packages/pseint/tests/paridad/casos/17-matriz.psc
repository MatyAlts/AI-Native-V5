Algoritmo matriz
	Definir m Como Entero
	Dimension m[3, 3]
	Definir f, c Como Entero
	Para f <- 1 Hasta 3 Hacer
		Para c <- 1 Hasta 3 Hacer
			m[f, c] <- f * c
		FinPara
	FinPara
	Para f <- 1 Hasta 3 Hacer
		Para c <- 1 Hasta 3 Hacer
			Escribir Sin Saltar m[f, c], " "
		FinPara
		Escribir ""
	FinPara
FinAlgoritmo
