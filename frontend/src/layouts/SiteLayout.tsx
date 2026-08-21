import { Link, Outlet } from "react-router-dom";

import { useAuth } from "../contexts/AuthContext";
import { dashboardPath } from "../routes/ProtectedRoute";

export function SiteLayout() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <Link className="flex items-center gap-2 font-semibold text-care-900" to="/">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-care-600 text-lg text-white">C</span>
            CareLoop
          </Link>
          <div className="flex items-center gap-3 text-sm font-medium">
            {user ? (
              <Link className="rounded-lg px-3 py-2 text-care-700 hover:bg-care-50" to={dashboardPath(user.role)}>
                Dashboard
              </Link>
            ) : (
              <>
                <Link className="rounded-lg px-3 py-2 text-slate-600 hover:bg-slate-100" to="/login">Log in</Link>
                <Link className="rounded-lg bg-care-600 px-4 py-2 text-white hover:bg-care-700" to="/register">Create account</Link>
              </>
            )}
          </div>
        </nav>
      </header>
      <main><Outlet /></main>
    </div>
  );
}

