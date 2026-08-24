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
    <div className="min-h-screen bg-mist">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 border-r border-slate-200 bg-white p-5 lg:flex lg:flex-col">
        <div className="flex items-center gap-3"><img className="h-10 w-10" src="/careloop-mark.svg" alt="CareLoop" /><div><p className="font-bold text-ink">CareLoop</p><p className="text-xs text-slate-500">Connected care</p></div></div>
        <nav aria-label="Workspace navigation" className="mt-10 space-y-2"><div className="rounded-xl bg-care-50 px-3 py-3 text-sm font-semibold text-care-900"><span className="block text-[11px] font-medium uppercase tracking-wider text-care-700">Workspace</span><span className="mt-1 block capitalize">{user?.role} dashboard</span></div></nav>
        <div className="mt-auto rounded-2xl bg-slate-50 p-4"><p className="text-sm font-semibold text-ink">Care, coordinated.</p><p className="mt-1 text-xs leading-5 text-slate-500">Your role controls the information and actions available here.</p></div>
      </aside>
      <div className="lg:pl-64"><header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/95 backdrop-blur"><div className="flex min-h-16 items-center justify-between px-4 sm:px-7"><div className="flex items-center gap-3 lg:hidden"><img className="h-9 w-9" src="/careloop-mark.svg" alt="CareLoop" /><span className="font-bold text-ink">CareLoop</span></div><p className="hidden text-sm font-medium capitalize text-slate-500 lg:block">{user?.role} workspace</p><div className="flex items-center gap-3"><div className="hidden text-right sm:block"><p className="text-sm font-semibold text-ink">{user?.full_name}</p><p className="text-xs capitalize text-slate-500">{user?.role}</p></div><span className="grid h-9 w-9 place-items-center rounded-full bg-care-100 text-sm font-bold text-care-900">{user?.full_name?.slice(0, 1).toUpperCase()}</span><button className="ui-button-outline min-h-9 px-3 py-1.5" type="button" onClick={handleLogout}>Log out</button></div></div></header>
      <main className="mx-auto w-full max-w-[1600px] px-4 py-7 sm:px-7 lg:px-10 lg:py-10"><Outlet /></main></div>
    </div>
  );
}
