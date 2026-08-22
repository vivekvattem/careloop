import { useEffect, useState } from "react";

import { ApiError, api } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import type { DoctorLeave, DoctorSchedule, DoctorSelf } from "../types/doctor";

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function DoctorDashboardPage() {
  const { accessToken } = useAuth();
  const [profile, setProfile] = useState<DoctorSelf | null>(null);
  const [schedule, setSchedule] = useState<DoctorSchedule | null>(null);
  const [leaves, setLeaves] = useState<DoctorLeave[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!accessToken) return;
    Promise.all([
      api.doctorProfile(accessToken),
      api.doctorSchedule(accessToken),
      api.doctorLeave(accessToken),
    ])
      .then(([profileResult, scheduleResult, leaveResult]) => {
        setProfile(profileResult);
        setSchedule(scheduleResult);
        setLeaves(leaveResult.leaves);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load your profile."));
  }, [accessToken]);

  return (
    <section>
      <p className="text-sm font-semibold uppercase tracking-wider text-care-600">Doctor workspace</p>
      <h1 className="mt-1 text-3xl font-bold">My profile and schedule</h1>
      <p className="mt-2 text-slate-600">This view is read-only. An administrator manages schedule changes in Phase 2A.</p>
      {error && <p className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}
      {!profile && !error && <p className="mt-8 text-slate-500">Loading profile…</p>}
      {profile && <div className="mt-8 grid gap-6 lg:grid-cols-3"><article className="rounded-2xl border border-slate-200 bg-white p-6"><h2 className="text-xl font-semibold">{profile.full_name}</h2><p className="mt-1 text-care-700">{profile.specialisation}</p><p className="mt-4 text-sm leading-6 text-slate-600">{profile.biography || "No biography provided."}</p><dl className="mt-4 space-y-2 text-sm"><div><dt className="text-slate-500">Qualifications</dt><dd>{profile.qualifications || "Not listed"}</dd></div><div><dt className="text-slate-500">Timezone</dt><dd>{profile.timezone}</dd></div><div><dt className="text-slate-500">Availability</dt><dd>{profile.is_available_for_booking ? "Available for preview" : "Unavailable"}</dd></div></dl></article><article className="rounded-2xl border border-slate-200 bg-white p-6"><h2 className="text-xl font-semibold">Weekly schedule</h2><p className="mt-1 text-xs text-slate-500">{schedule?.slot_duration_minutes}-minute slots · {schedule?.timezone}</p><div className="mt-4 space-y-2">{schedule?.working_hours.map((item) => <div className="rounded-lg bg-slate-50 p-3 text-sm" key={item.id}>{weekdays[item.day_of_week]} · {item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}</div>)}{!schedule?.working_hours.length && <p className="text-sm text-slate-500">No working hours configured.</p>}</div></article><article className="rounded-2xl border border-slate-200 bg-white p-6"><h2 className="text-xl font-semibold">Upcoming leave</h2><div className="mt-4 space-y-2">{leaves.map((item) => <div className="rounded-lg bg-slate-50 p-3 text-sm" key={item.id}><span className="font-medium">{item.leave_date}</span>{item.reason && <span className="mt-1 block text-slate-500">{item.reason}</span>}</div>)}{!leaves.length && <p className="text-sm text-slate-500">No upcoming leave.</p>}</div></article></div>}
    </section>
  );
}

