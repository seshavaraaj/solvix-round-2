import { useEffect, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { minutesBetween } from "../lib/format";

const CYCLE_EVERY_MIN = 15;

/**
 * POST /cycle?t= on demand, and automatically whenever the replay clock has advanced
 * ≥ 15 simulated minutes since the last run (frontend plan F3.1).
 */
export function useCycle(t: string | undefined) {
  const qc = useQueryClient();
  const lastT = useRef<string | null>(null);

  const mutation = useMutation({
    mutationFn: (at: string) => api.runCycle(at),
    onSuccess: (res) => {
      lastT.current = res.t;
      qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });

  useEffect(() => {
    if (!t || mutation.isPending) return;
    const last = lastT.current;
    // A backwards jump (new scenario) also counts as "advanced": start a fresh cycle.
    const moved = last === null ? Infinity : Math.abs(minutesBetween(last, t));
    if (moved >= CYCLE_EVERY_MIN) {
      lastT.current = t;
      mutation.mutate(t);
    }
  }, [t, mutation]);

  return {
    ready: Boolean(t),
    run: () => {
      if (t) mutation.mutate(t);
    },
    running: mutation.isPending,
    error: mutation.error,
    lastRan: mutation.data,
  };
}

export type Cycle = ReturnType<typeof useCycle>;
