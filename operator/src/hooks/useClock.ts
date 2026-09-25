import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ClockCommand } from "../api/types";

export function useClock() {
  return useQuery({
    queryKey: ["clock"],
    queryFn: api.getClock,
    refetchInterval: (q) => (q.state.data?.playing ? 5000 : 15000),
  });
}

export function useClockCommand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cmd: ClockCommand) => api.setClock(cmd),
    onSuccess: (clock) => {
      qc.setQueryData(["clock"], clock);
      qc.invalidateQueries({ queryKey: ["state"] });
    },
  });
}
