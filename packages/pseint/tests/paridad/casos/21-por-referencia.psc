SubProceso intercambiar(a Por Referencia, b Por Referencia)
	Definir t Como Entero
	t <- a
	a <- b
	b <- t
FinSubProceso

SubProceso noCambia(a Por Valor)
	a <- 100
FinSubProceso

Algoritmo referencia
	Definir x, z Como Entero
	x <- 1
	z <- 2
	intercambiar(x, z)
	Escribir x, " ", z
	noCambia(x)
	Escribir x
FinAlgoritmo
