/**
 * Ruta /progreso del web-student (F9).
 *
 * Vista de solo lectura de la progresion pedagogica longitudinal del alumno:
 * trayectoria de apropiacion en tareas analogas (CII), episodios y señales
 * pedagogicas vs cohorte. Sin search params: el pseudonimo lo resuelve la
 * pagina (getCurrentUserUuid con fallback al /student/me/episodes).
 */
import { createFileRoute } from "@tanstack/react-router"
import { MiProgresoPage } from "../pages/MiProgresoPage"

export const Route = createFileRoute("/progreso")({
  component: MiProgresoPage,
})
