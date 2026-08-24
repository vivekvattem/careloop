import { Link, Outlet } from "react-router-dom";
import { useState } from "react";

import { useAuth } from "../contexts/AuthContext";
import { dashboardPath } from "../routes/ProtectedRoute";

export function SiteLayout() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-mist">
      <header className="border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-4">
          <Link className="flex items-center" to="/" aria-label="CareLoop home">
            <img className="h-9 w-auto" src="/careloop-logo.svg" alt="CareLoop" />
          </Link>
          <button className="ui-button-ghost md:hidden" aria-expanded={open} onClick={() => setOpen(!open)}>Menu</button><div className={`${open ? "flex" : "hidden"} w-full flex-col gap-2 text-sm font-medium md:flex md:w-auto md:flex-row md:items-center`}>
            {!user && <><a className="ui-button-ghost" href="/#how-it-works" onClick={() => setOpen(false)}>How it works</a><a className="ui-button-ghost" href="/#features" onClick={() => setOpen(false)}>Features</a><a className="ui-button-ghost" href="/#safety" onClick={() => setOpen(false)}>Safety</a></>}
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
      <footer className="border-t border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-bold text-ink">CareLoop</p><p className="mt-1">Connected care journeys for this assessment demo.</p></div><div className="flex gap-4"><Link className="hover:text-care-700 hover:underline" to="/login">Sign in</Link><Link className="hover:text-care-700 hover:underline" to="/register">Create patient account</Link></div></div></footer>
    </div>
  );
}
