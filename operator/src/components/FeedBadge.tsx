import type { FeedHealth } from "../api/types";
import { pct } from "../lib/format";

export function FeedBadge({ feed }: { feed?: FeedHealth }) {
  if (!feed) return <span className="badge muted">Feed: –</span>;
  const healthy = feed.fresh && feed.share_reporting >= 0.8;
  return (
    <span
      className={`badge ${healthy ? "good" : "warn"}`}
      title={`${pct(feed.share_reporting)} of expected buses reporting${feed.fresh ? "" : " · feed is stale"}`}
    >
      {healthy ? "●" : "▲"} {feed.buses_reporting}/{feed.buses_expected} reporting · {feed.mode}
      {!feed.fresh && " · stale"}
    </span>
  );
}
