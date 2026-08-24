import { Link } from "react-router-dom";
import { CarePathArtwork } from "../components/CarePathArtwork";

export function LandingPage() {
  return (
    <section className="relative overflow-hidden"><CarePathArtwork />
      <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-16 sm:px-8 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:py-24">
        <div>
          <span className="ui-status bg-care-100 text-care-700">
            Care that stays connected
          </span>
          <h1 className="mt-6 max-w-2xl text-4xl font-bold tracking-tight text-ink sm:text-6xl">
            Every care moment, thoughtfully connected.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600">
            Book with confidence, arrive prepared, and keep clinician-approved next steps clear—before and after every visit.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="ui-button-primary px-5 py-3" to="/register">
              Book an appointment
            </Link>
            <Link className="ui-button-outline px-5 py-3" to="/login">
              Sign in
            </Link>
          </div>
        </div>
        <div className="ui-card relative overflow-hidden bg-white p-2 shadow-lift"><div className="rounded-[1.35rem] bg-ink p-6 text-white sm:p-8"><div className="flex items-start justify-between"><div><p className="text-xs font-semibold uppercase tracking-wider text-care-100">Upcoming appointment</p><h2 className="mt-2 text-xl font-semibold text-white">Dr. Ananya Mehta</h2><p className="text-sm text-slate-300">Neurology · 24 August 2026</p></div><span className="ui-status bg-care-400 text-ink">Confirmed</span></div><p className="mt-5 text-lg font-medium">10:30 AM – 11:00 AM</p><div className="mt-6 grid gap-3"><div className="rounded-xl bg-white/10 p-4"><p className="text-sm font-semibold">Pre-visit packet ready</p><p className="mt-1 text-xs text-slate-300">Your symptoms and visit context are organised for review.</p></div><div className="flex items-center justify-between rounded-xl bg-white/10 p-4 text-sm"><span>Medication reminder</span><span className="text-care-100">Follow-up scheduled</span></div><div className="flex items-center justify-between text-xs text-slate-300"><span>Calendar sync</span><span className="text-care-100">Up to date</span></div></div></div></div>
        <p className="lg:col-span-2 text-sm font-medium text-slate-600">Clinician-reviewed summaries. Reliable care even when AI services are unavailable.</p>
      </div>
      <div className="relative mx-auto max-w-7xl px-5 pb-20 sm:px-8"><div className="grid gap-4 border-y border-slate-200 py-8 sm:grid-cols-2 lg:grid-cols-4">{["Role-based access","Clinician-reviewed AI summaries","Reliable provider fallback","Private and secure care records"].map((item)=><p className="text-sm font-semibold text-ink" key={item}>{item}</p>)}</div><div id="how-it-works" className="py-20"><p className="text-sm font-semibold text-care-700">HOW CARELOOP WORKS</p><h2 className="mt-3 text-3xl font-bold">A clearer path through care.</h2><div className="mt-9 grid gap-6 md:grid-cols-4">{["Discover a doctor","Book securely","Prepare with a pre-visit packet","Receive clinician-approved care instructions"].map((item,index)=><div key={item}><span className="text-care-600">0{index+1}</span><p className="mt-3 font-semibold">{item}</p></div>)}</div></div><div id="features" className="grid gap-4 md:grid-cols-3"><div className="ui-card p-6 md:col-span-2"><h2 className="text-2xl font-bold">Scheduling that respects the real world.</h2><p className="mt-3 text-slate-600">Smart availability, care preparation, post-visit summaries, and medication reminders remain connected.</p></div><div className="ui-card-muted p-6"><p className="font-semibold">Google Calendar synchronization</p><p className="mt-2 text-sm text-slate-600">Keep appointments aligned without putting clinical details in calendar events.</p></div><div className="ui-card-muted p-6"><p className="font-semibold">Controlled history retrieval</p><p className="mt-2 text-sm text-slate-600">Relevant context remains patient-scoped and reviewable.</p></div><div className="ui-card p-6 md:col-span-2"><p className="font-semibold">Graceful deterministic AI fallback</p><p className="mt-2 text-slate-600">Appointments and summaries remain usable when external AI services are unavailable.</p></div></div><div id="safety" className="mt-20 rounded-3xl bg-care-50 p-8"><h2 className="text-2xl font-bold">Safety and reliability, built into the workflow.</h2><p className="mt-4 max-w-3xl text-slate-700">AI does not replace the clinician. Appropriate summaries are reviewed, private notes remain private, records are role-scoped, and care continues even when external services fail.</p></div><div className="mt-16 text-center"><h2 className="text-3xl font-bold">Start your CareLoop journey</h2><div className="mt-6 flex justify-center gap-3"><Link className="ui-button-primary" to="/register">Register as patient</Link><Link className="ui-button-outline" to="/login">Sign in</Link></div></div></div>
    </section>
  );
}
