import { createFileRoute } from "@tanstack/react-router"
import { KappaRatingView } from "../views/KappaRatingView"

const DEMO_EPISODES = [
  {
    episode_id: "ep_demo_1",
    classifier_label: "apropiacion_reflexiva" as const,
    summary:
      "Estudiante pregunta por qué su solución tiene complejidad O(n²) y propone alternativas con hash map antes de pedir código.",
  },
  {
    episode_id: "ep_demo_2",
    classifier_label: "delegacion_pasiva" as const,
    summary:
      '"Dame la solución del ejercicio 3 del TP" (tres prompts consecutivos pidiendo código directo, copia-pega sin preguntar).',
  },
  {
    episode_id: "ep_demo_3",
    classifier_label: "apropiacion_superficial" as const,
    summary:
      'Pregunta conceptos sueltos ("¿qué es recursión?"), recibe respuestas, ejecuta código sin probar alternativas ni validar edge cases.',
  },
]

export const Route = createFileRoute("/kappa")({
  component: function KappaRoute() {
    const { getToken } = Route.useRouteContext()
    return <KappaRatingView getToken={getToken} episodes={DEMO_EPISODES} />
  },
})
