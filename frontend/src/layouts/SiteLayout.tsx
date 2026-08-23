import { Link, Outlet } from "react-router-dom";

import { useAuth } from "../contexts/AuthContext";
import { dashboardPath } from "../routes/ProtectedRoute";

export function SiteLayout() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-mist">
      <header className="border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <Link className="flex items-center gap-2 font-bold text-ink" to="/">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-care-600 text-lg text-white shadow-sm">C</span>
            CareLoop
          </Link>
          <div className="flex items-center gap-3 text-sm font-medium">
            {user ? (
                <Link className="ui-button-secondary min-h-9 px-3 py-1.5" to={dashboardPath(user.role)}>
                Dashboard
              </Link>
            ) : (
              <>
                <Link className="ui-button-ghost min-h-9 px-3 py-1.5" to="/login">Log in</Link>
                <Link className="ui-button-primary min-h-9 px-3 py-1.5" to="/register">Create account</Link>
              </>
            )}
          </div>
        </nav>
      </header>
      <main><Outlet /></main>
    </div>
  );
}
