import { useAuth } from "../contexts/AuthContext";
import type { UserRole } from "../types/auth";

const descriptions: Record<UserRole, string> = {
  patient: "Appointment booking, visit preparation, and follow-up tools will be added in later phases.",
  doctor: "Availability, appointment review, and clinical summary tools will be added in later phases.",
  admin: "User oversight and operational management tools will be added in later phases.",
};

export function DashboardPage({ role }: { role: UserRole }) {
  const { user } = useAuth();
  return (
    <section>
      <p className="text-sm font-semibold uppercase tracking-wider text-care-600">{role} dashboard</p>
      <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Hello, {user?.full_name}</h1>
      <div className="mt-8 max-w-2xl rounded-2xl border border-slate-200 bg-white p-7 shadow-sm">
        <h2 className="text-xl font-semibold">Your workspace is ready</h2>
        <p className="mt-3 leading-7 text-slate-600">{descriptions[role]}</p>
        <div className="mt-6 rounded-xl bg-care-50 p-4 text-sm text-care-900">
          Phase 1 includes account security and role-aware routing only.
        </div>
      </div>
    </section>
  );
}

