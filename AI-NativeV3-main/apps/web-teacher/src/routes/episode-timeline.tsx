import { createFileRoute } from "@tanstack/react-router"
import { z } from "zod"
import { EpisodeTimelineView } from "../views/EpisodeTimelineView"

const searchSchema = z.object({
  episodeId: z.string().uuid().optional(),
})

export const Route = createFileRoute("/episode-timeline")({
  validateSearch: searchSchema,
  component: function EpisodeTimelineRoute() {
    const { getToken } = Route.useRouteContext()
    const { episodeId } = Route.useSearch()
    return (
      <div className="p-6">
        <EpisodeTimelineView
          getToken={getToken}
          {...(episodeId ? { initialEpisodeId: episodeId } : {})}
        />
      </div>
    )
  },
})
