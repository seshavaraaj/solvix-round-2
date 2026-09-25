import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { session } from "../api/client";
import { ClockBar } from "../components/ClockBar";
import { FeedBadge } from "../components/FeedBadge";
import { NetworkMap } from "../components/NetworkMap";
import { RecommendationQueue } from "../components/RecommendationQueue";
import { RouteHealthTable } from "../components/RouteHealthTable";
import { useClock } from "../hooks/useClock";
import { useCycle } from "../hooks/useCycle";
import { useRoutes, useStateQuery } from "../hooks/useStateQuery";
import { Results } from "./Results";

type Tab = "routes" | "recommendations" | "results";
const TABS: { id: Tab; label: string }[] = [
  { id: "routes", label: "Routes" },
  { id: "recommendations", label: "Recommendations" },
  { id: "results", label: "Results" },
];

export function Console() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("routes");
  const [focus, setFocus] = useState<string | null>(null);

  const clock = useClock();
  const state = useStateQuery(clock.data?.playing ?? false);
  const routes = useRoutes();
  const t = state.data?.t ?? clock.data?.t;
  const cycle = useCycle(t);

  function logout() {
    session.clear();
    qc.clear();
    nav("/login", { replace: true });
  }

  return (
    <div className="console">
      <header className="topbar">
        <strong className="brand">TransitPulse</strong>
        <ClockBar t={t} />
        <FeedBadge feed={state.data?.feed} />
        <button type="button" className="link" onClick={logout}>
          Sign out
        </button>
      </header>

      <main className="layout">
        <section className="map-area">
          {routes.isError && <div className="banner error">Could not load routes.</div>}
          {state.isError && <div className="banner error">Live state unavailable. Retrying…</div>}
          <NetworkMap routes={routes.data ?? []} buses={state.data?.buses ?? []} focusRouteId={focus} />
        </section>

        <aside className={tab === "results" ? "panel wide" : "panel"}>
          <nav className="tabs" role="tablist">
            {TABS.map((x) => (
              <button
                key={x.id}
                role="tab"
                aria-selected={tab === x.id}
                className={tab === x.id ? "on" : ""}
                onClick={() => setTab(x.id)}
              >
                {x.label}
                {x.id === "recommendations" && cycle.running && " …"}
              </button>
            ))}
          </nav>
          <div className="panel-body">
            {tab === "routes" &&
              (state.isPending ? (
                <p className="muted pad">Loading route health…</p>
              ) : (
                <RouteHealthTable
                  health={state.data?.route_health ?? []}
                  routes={routes.data ?? []}
                  selected={focus}
                  onSelect={setFocus}
                />
              ))}
            {tab === "recommendations" && <RecommendationQueue cycle={cycle} />}
            {tab === "results" && <Results />}
          </div>
        </aside>
      </main>
    </div>
  );
}
