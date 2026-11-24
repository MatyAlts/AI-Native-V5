Algoritmo primos
	Definir n, i, d Como Entero
	Definir esPrimo Como Logico
	Leer n
	Para i <- 2 Hasta n Hacer
		esPrimo <- Verdadero
		d <- 2
		Mientras d * d <= i Y esPrimo Hacer
			Si i MOD d = 0 Entonces
				esPrimo <- Falso
			FinSi
			d <- d + 1
		FinMientras
		Si esPrimo Entonces
			Escribir Sin Saltar i, " "
		FinSi
	FinPara
	Escribir ""
FinAlgoritmo
