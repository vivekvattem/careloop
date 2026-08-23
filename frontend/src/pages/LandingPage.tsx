import { Link } from "react-router-dom";

export function LandingPage() {
  return (
    <section className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[34rem] bg-[radial-gradient(circle_at_15%_10%,rgba(204,251,241,0.8),transparent_35%),radial-gradient(circle_at_85%_20%,rgba(219,234,254,0.8),transparent_32%)]" />
      <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-16 sm:px-8 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:py-24">
        <div>
          <span className="ui-status bg-care-100 text-care-700">
            Thoughtful care, better connected
          </span>
          <h1 className="mt-6 max-w-2xl text-4xl font-bold tracking-tight text-ink sm:text-6xl">
            Your care journey, kept in one loop.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600">
            One calm, secure space for appointments, care preparation, follow-up plans, and the people who keep care moving.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="ui-button-primary px-5 py-3" to="/register">
              Join as a patient
            </Link>
            <Link className="ui-button-outline px-5 py-3" to="/login">
              Sign in
            </Link>
          </div>
        </div>
        <div className="ui-card overflow-hidden bg-gradient-to-br from-white via-white to-care-50 p-2 shadow-lift">
          <div className="rounded-[1.35rem] bg-ink p-7 text-white sm:p-9">
            <p className="text-sm font-semibold uppercase tracking-wider text-care-100">Care that stays connected</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Everything important, in context.</h2>
            <div className="mt-7 grid gap-3">
              {["Find a suitable doctor and book with confidence", "Prepare with a focused pre-visit Care Packet", "Keep follow-up plans and medication schedules clear"].map((feature, index) => <div className="flex gap-3 rounded-xl bg-white/10 p-4" key={feature}><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-care-400 text-xs font-bold text-ink">{index + 1}</span><p className="text-sm leading-6 text-slate-100">{feature}</p></div>)}
            </div>
            <p className="mt-6 text-sm leading-6 text-slate-300">CareLoop supports patients, clinicians, and administrators with role-aware workspaces.</p>
          </div>
        </div>
        <div className="lg:col-span-2 grid gap-4 border-t border-slate-200 pt-8 sm:grid-cols-3"><div><p className="font-semibold text-ink">Private by design</p><p className="mt-1 text-sm text-slate-600">Role-aware access keeps care information appropriately scoped.</p></div><div><p className="font-semibold text-ink">Clear next steps</p><p className="mt-1 text-sm text-slate-600">Appointments and follow-up work stay actionable.</p></div><div><p className="font-semibold text-ink">Built for continuity</p><p className="mt-1 text-sm text-slate-600">Care teams can move from preparation to review with less friction.</p></div></div>
      </div>
    </section>
  );
}
