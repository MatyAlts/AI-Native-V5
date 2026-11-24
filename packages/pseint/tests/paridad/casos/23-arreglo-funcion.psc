Funcion s <- sumar(v, n)
	Definir s, i Como Entero
	s <- 0
	Para i <- 1 Hasta n Hacer
		s <- s + v[i]
	FinPara
FinFuncion

Algoritmo arreglofuncion
	Definir v Como Entero
	Dimension v[4]
	v[1] <- 3
	v[2] <- 5
	v[3] <- 7
	v[4] <- 9
	Escribir "Suma: ", sumar(v, 4)
FinAlgoritmo
