import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { EpisodeNLevelView } from "../views/EpisodeNLevelView"

const searchSchema = z.object({
  episodeId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/episode-n-level")({
  validateSearch: searchSchema,
  component: function EpisodeNLevelRoute() {
    const { getToken } = Route.useRouteContext()
    const { episodeId } = Route.useSearch()
    return (
      <div className="p-6">
        <EpisodeNLevelView
          getToken={getToken}
          {...(episodeId ? { initialEpisodeId: episodeId } : {})}
        />
      </div>
    )
  },
})
