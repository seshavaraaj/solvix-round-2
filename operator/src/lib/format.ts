// Status palette (fixed): good / warning / critical. Always paired with a text label.
export const LOAD_COLORS = {
  ok: "#0ca30c",
  busy: "#fab219",
  over: "#d03b3b",
  dark: "#898781",
} as const;

export type LoadBand = keyof typeof LOAD_COLORS;

/** < 0.6 green, 0.6–1.0 amber, > 1.0 red (frontend plan F2). */
export function loadBand(loadFactor: number, dark = false): LoadBand {
  if (dark) return "dark";
  if (loadFactor < 0.6) return "ok";
  if (loadFactor <= 1.0) return "busy";
  return "over";
}

export function loadColor(loadFactor: number, dark = false): string {
  return LOAD_COLORS[loadBand(loadFactor, dark)];
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;

/** "17:30" from an ISO time with offset, shown in the time zone of the offset (Asia/Kolkata). */
export function hhmm(iso: string): string {
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : iso;
}

export function minutesBetween(a: string, b: string): number {
  return (Date.parse(b) - Date.parse(a)) / 60000;
}

export const humanize = (s: string) => s.replace(/_/g, " ");
