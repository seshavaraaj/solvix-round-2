import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/** GET /state every 2 s while the replay clock plays, every 10 s while paused. */
export function useStateQuery(playing: boolean) {
  return useQuery({
    queryKey: ["state"],
    queryFn: () => api.getState(),
    refetchInterval: playing ? 2000 : 10000,
  });
}

export function useRoutes() {
  return useQuery({ queryKey: ["routes"], queryFn: api.getRoutes, staleTime: 5 * 60_000 });
}
