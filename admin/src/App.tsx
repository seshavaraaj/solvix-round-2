import { useCallback, useEffect } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { onApiEvent, session } from "./api/client";
import { WakeUp } from "./components/WakeUp";
import { Login } from "./pages/Login";
import { RoutesPage } from "./pages/RoutesPage";
import { FleetPage } from "./pages/FleetPage";
import { DecisionsPage } from "./pages/DecisionsPage";

function Shell() {
  const nav = useNavigate();
  const qc = useQueryClient();
  if (!session.token || session.role !== "admin") return <Navigate to="/login" replace />;
  return (
    <div className="shell">
      <header className="topbar">
        <strong>AduthaBus Fleet Admin</strong>
        <nav>
          <NavLink to="/routes">Routes</NavLink>
          <NavLink to="/fleet">Fleet</NavLink>
          <NavLink to="/decisions">Decision log</NavLink>
        </nav>
        <button
          type="button"
          className="link"
          onClick={() => {
            session.clear();
            qc.clear();
            nav("/login", { replace: true });
          }}
        >
          Sign out
        </button>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

export function App() {
  const qc = useQueryClient();
  const nav = useNavigate();

  useEffect(
    () =>
      onApiEvent((e) => {
        if (e === "unauthorized") {
          qc.clear();
          nav("/login", { replace: true });
        }
      }),
    [qc, nav],
  );

  const onAwake = useCallback(() => qc.invalidateQueries(), [qc]);

  return (
    <WakeUp onAwake={onAwake}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Shell />}>
          <Route path="/routes" element={<RoutesPage />} />
          <Route path="/fleet" element={<FleetPage />} />
          <Route path="/decisions" element={<DecisionsPage />} />
          <Route path="*" element={<Navigate to="/routes" replace />} />
        </Route>
      </Routes>
    </WakeUp>
  );
}
