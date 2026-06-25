import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useParams } from "react-router";

import { AppShell } from "./components/common/AppShell";
import { PublicShell } from "./components/common/PublicShell";
import { Spinner } from "./components/common/Spinner";
import { IS_PUBLIC_MODE } from "./config/runtime";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Search } from "./pages/Search";
import { useAuthStore } from "./stores/auth";

const EntityAnalysis = lazy(() => import("./pages/EntityAnalysis").then((m) => ({ default: m.EntityAnalysis })));

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const restored = useAuthStore((s) => s.restored);
  if (!restored) return <Spinner />;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RedirectIfAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const restored = useAuthStore((s) => s.restored);
  if (!restored) return <Spinner />;
  if (token) return <Navigate to="/app" replace />;
  return <>{children}</>;
}

function GraphRedirect() {
  const { entityId } = useParams();
  return <Navigate to={`/app/analysis/${entityId}`} replace />;
}

export function App() {
  const restore = useAuthStore((s) => s.restore);

  useEffect(() => {
    restore();
  }, [restore]);

  return (
    <Routes>
      {/* Public shell — landing, login, register */}
      <Route
        element={IS_PUBLIC_MODE ? <PublicShell /> : (
          <RedirectIfAuth>
            <PublicShell />
          </RedirectIfAuth>
        )}
      >
        <Route index element={<Landing />} />
        {!IS_PUBLIC_MODE && <Route path="login" element={<Login />} />}
        {!IS_PUBLIC_MODE && <Route path="register" element={<Register />} />}
      </Route>

      {/* Authenticated shell — the intelligence workspace */}
      <Route
        path="app"
        element={IS_PUBLIC_MODE ? <AppShell /> : (
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        )}
      >
        <Route index element={<Navigate to="/app/search" replace />} />
        <Route path="search" element={<Search />} />
        <Route path="analysis/:entityId" element={<Suspense fallback={<Spinner />}><EntityAnalysis /></Suspense>} />
        <Route path="graph/:entityId" element={<GraphRedirect />} />
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
