import { Link } from "react-router-dom";

export function LandingPage() {
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto grid max-w-6xl gap-12 px-5 py-20 lg:grid-cols-2 lg:items-center lg:py-28">
        <div>
          <span className="inline-flex rounded-full bg-care-100 px-3 py-1 text-sm font-medium text-care-700">
            Thoughtful care, better connected
          </span>
          <h1 className="mt-6 max-w-xl text-4xl font-bold tracking-tight text-slate-950 sm:text-6xl">
            Your care journey, kept in one loop.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600">
            CareLoop is being built to make appointments and follow-up care easier for patients and care teams.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="rounded-xl bg-care-600 px-5 py-3 font-semibold text-white shadow-sm hover:bg-care-700" to="/register">
              Join as a patient
            </Link>
            <Link className="rounded-xl border border-slate-300 bg-white px-5 py-3 font-semibold text-slate-700 hover:bg-slate-100" to="/login">
              Sign in
            </Link>
          </div>
        </div>
        <div className="rounded-3xl border border-care-100 bg-gradient-to-br from-white to-care-50 p-8 shadow-xl shadow-care-900/5">
          <div className="rounded-2xl bg-white p-6 shadow-sm">
            <p className="text-sm font-semibold uppercase tracking-wider text-care-600">Phase 1</p>
            <h2 className="mt-2 text-2xl font-semibold">A secure foundation</h2>
            <div className="mt-6 space-y-4 text-slate-600">
              <p>✓ Patient account registration</p>
              <p>✓ Secure role-aware sign in</p>
              <p>✓ Dedicated patient, doctor, and admin spaces</p>
            </div>
            <p className="mt-6 rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-500">
              Appointment and follow-up tools will arrive in the next development phases.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

