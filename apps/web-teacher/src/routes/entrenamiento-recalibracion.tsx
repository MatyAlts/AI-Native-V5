import { PageContainer } from "@platform/ui"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { helpContent } from "../utils/helpContent"
import { InterraterTraining } from "../views/InterraterTraining"

export const Route = createFileRoute("/entrenamiento-recalibracion")({
  component: function EntrenamientoRecalibracionRoute() {
    const { getToken } = Route.useRouteContext()
    const navigate = useNavigate()
    return (
      <PageContainer
        title="Entrenamiento / Recalibración"
        description="Aprendé a reconocer los 3 ejes y calibrá tu criterio con 7 episodios reales. Necesitás 6/7 para estar listo. Volvé acá cuando quieras re-calibrar."
        helpContent={helpContent.interraterCoding}
      >
        <div className="max-w-4xl">
          <InterraterTraining getToken={getToken} onPass={() => navigate({ to: "/interrater" })} />
        </div>
      </PageContainer>
    )
  },
})
