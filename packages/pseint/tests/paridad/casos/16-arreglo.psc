Algoritmo arreglo
	Definir v Como Entero
	Dimension v[5]
	Definir i, mayor Como Entero
	Para i <- 1 Hasta 5 Hacer
		Leer v[i]
	FinPara
	mayor <- v[1]
	Para i <- 2 Hasta 5 Hacer
		Si v[i] > mayor Entonces
			mayor <- v[i]
		FinSi
	FinPara
	Escribir "Mayor: ", mayor
	Para i <- 5 Hasta 1 Con Paso -1 Hacer
		Escribir Sin Saltar v[i], " "
	FinPara
	Escribir ""
FinAlgoritmo
