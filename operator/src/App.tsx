import { useCallback, useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { onApiEvent, session } from "./api/client";
import { WakeUp } from "./components/WakeUp";
import { Login } from "./pages/Login";
import { Console } from "./pages/Console";

function RequireOperator({ children }: { children: JSX.Element }) {
  if (!session.token || session.role !== "operator") return <Navigate to="/login" replace />;
  return children;
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

  // After a cold start or reconnect the replay clock may have reset: refetch everything.
  const onAwake = useCallback(() => qc.invalidateQueries(), [qc]);

  return (
    <WakeUp onAwake={onAwake}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/*"
          element={
            <RequireOperator>
              <Console />
            </RequireOperator>
          }
        />
      </Routes>
    </WakeUp>
  );
}
