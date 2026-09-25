import { useEffect, useRef, useState, type ReactNode } from "react";
import { getHealth, onApiEvent } from "../api/client";

interface Props {
  children: ReactNode;
  /** Called when the API answers "ok" after being asleep, so callers can re-read the clock (contract §6 notes). */
  onAwake?: () => void;
  message?: string;
}

/**
 * Blocks the app until GET /health says "ok", polling every 3 s.
 * If /health says "error", start-up failed on the server: show its message instead of waiting forever.
 * Shown again (as an overlay, so screen state survives) whenever a call returns 503 loading
 * or cannot reach the server.
 */
export function WakeUp({ children, onAwake, message = "Starting server (about 1 minute)…" }: Props) {
  const [awake, setAwake] = useState(false);
  const [everAwake, setEverAwake] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);
  const onAwakeRef = useRef(onAwake);
  onAwakeRef.current = onAwake;

  useEffect(() => onApiEvent((e) => e === "waking" && setAwake(false)), []);

  useEffect(() => {
    if (awake) return;
    let cancelled = false;
    const started = Date.now();
    const check = async () => {
      const h = await getHealth();
      if (cancelled) return;
      setSeconds(Math.round((Date.now() - started) / 1000));
      setFailure(h?.status === "error" ? (h.error ?? "unknown error") : null);
      if (h?.status === "ok") {
        setAwake(true);
        setEverAwake(true);
        onAwakeRef.current?.();
      }
    };
    check();
    const id = setInterval(check, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [awake]);

  const screen = failure ? (
    <div className={everAwake ? "wake overlay" : "wake"} role="alert">
      <p className="error">The server failed to start.</p>
      <p className="muted">{failure}</p>
      <p className="muted">Check the API logs on Render, then redeploy or restart the service.</p>
    </div>
  ) : (
    <div className={everAwake ? "wake overlay" : "wake"} role="status" aria-live="polite">
      <div className="spinner" aria-hidden />
      <p>{message}</p>
      <p className="muted">Waiting {seconds}s. The free server sleeps when idle.</p>
    </div>
  );

  if (!everAwake) return screen;
  return (
    <>
      {children}
      {!awake && screen}
    </>
  );
}
