import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../contexts/AuthContext";

export function DashboardLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <div>
            <p className="font-semibold text-care-900">CareLoop</p>
            <p className="text-xs capitalize text-slate-500">{user?.role} workspace</p>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden text-sm text-slate-600 sm:inline">{user?.full_name}</span>
            <button className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-100" type="button" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-10"><Outlet /></main>
    </div>
  );
}

