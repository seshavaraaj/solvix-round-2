// Chart tokens: validated default categorical palette (slots 1–3) and chart chrome.
// Series colour follows the entity: slot order is fixed, never cycled.
export const CHART = {
  series: ["#2a78d6", "#eb6834", "#1baf7a"],
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  muted: "#898781",
} as const;

/** Fixed colour per strategy so filtering never repaints survivors. */
export const STRATEGY_COLOR: Record<string, string> = {
  baseline: CHART.series[0],
  holding: CHART.series[1],
  aduthabus: CHART.series[2],
};
