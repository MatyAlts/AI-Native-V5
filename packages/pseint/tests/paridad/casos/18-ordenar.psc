Algoritmo burbuja
	Definir v Como Real
	Dimension v[6]
	Definir i, j Como Entero
	Definir aux Como Real
	Para i <- 1 Hasta 6 Hacer
		Leer v[i]
	FinPara
	Para i <- 1 Hasta 5 Hacer
		Para j <- 1 Hasta 6 - i Hacer
			Si v[j] > v[j + 1] Entonces
				aux <- v[j]
				v[j] <- v[j + 1]
				v[j + 1] <- aux
			FinSi
		FinPara
	FinPara
	Para i <- 1 Hasta 6 Hacer
		Escribir v[i]
	FinPara
FinAlgoritmo
