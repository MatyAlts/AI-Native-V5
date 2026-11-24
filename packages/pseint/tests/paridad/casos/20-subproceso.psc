SubProceso saludar(nombre)
	Escribir "Hola ", nombre
FinSubProceso

SubProceso linea(n)
	Definir i Como Entero
	Para i <- 1 Hasta n Hacer
		Escribir Sin Saltar "-"
	FinPara
	Escribir ""
FinSubProceso

Algoritmo subprocesos
	linea(5)
	saludar("Ana")
	saludar("Luis")
	linea(3)
FinAlgoritmo
