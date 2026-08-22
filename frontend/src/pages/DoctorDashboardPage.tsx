import { useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import type { AppointmentDetail, AppointmentListItem } from "../types/appointment";
import type { DoctorLeave, DoctorSchedule, DoctorSelf } from "../types/doctor";
import { StatusBadge } from "./PatientDashboardPage";

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function DoctorDashboardPage() {
  const { accessToken } = useAuth();
  const [profile, setProfile] = useState<DoctorSelf | null>(null);
  const [schedule, setSchedule] = useState<DoctorSchedule | null>(null);
  const [leaves, setLeaves] = useState<DoctorLeave[]>([]);
  const [appointments, setAppointments] = useState<AppointmentListItem[]>([]);
  const [selected, setSelected] = useState<AppointmentDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!accessToken) return;
    Promise.all([
      api.doctorProfile(accessToken),
      api.doctorSchedule(accessToken),
      api.doctorLeave(accessToken),
      api.doctorAppointments(accessToken),
    ])
      .then(([profileResult, scheduleResult, leaveResult, appointmentResult]) => {
        setProfile(profileResult);
        setSchedule(scheduleResult);
        setLeaves(leaveResult.leaves);
        setAppointments(appointmentResult.items);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load your workspace."));
  }, [accessToken]);

  const todayKey = new Date().toDateString();
  const today = useMemo(() => appointments.filter((item) => new Date(item.slot_start).toDateString() === todayKey), [appointments, todayKey]);
  const upcoming = useMemo(() => appointments.filter((item) => new Date(item.slot_start) > new Date() && new Date(item.slot_start).toDateString() !== todayKey), [appointments, todayKey]);

  const inspect = async (id: string) => {
    if (!accessToken) return;
    try {
      setSelected(await api.doctorAppointment(accessToken, id));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load appointment details.");
    }
  };

  return <section className="space-y-8"><div><p className="text-sm font-semibold uppercase tracking-wider text-care-600">Doctor workspace</p><h1 className="mt-1 text-3xl font-bold">My practice</h1><p className="mt-2 text-slate-600">Schedule data is read-only; appointment symptoms are available only for your patients.</p></div>{error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}{profile && <div className="grid gap-6 lg:grid-cols-3"><article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">{profile.full_name}</h2><p className="text-care-700">{profile.specialisation}</p><p className="mt-3 text-sm text-slate-600">{profile.biography}</p></article><article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">Weekly schedule</h2><p className="text-xs text-slate-500">{schedule?.slot_duration_minutes}-minute slots · {schedule?.timezone}</p><div className="mt-3 space-y-2">{schedule?.working_hours.map((item) => <div className="rounded-lg bg-slate-50 p-2 text-sm" key={item.id}>{weekdays[item.day_of_week]} · {item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}</div>)}</div></article><article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">Upcoming leave</h2><div className="mt-3 space-y-2">{leaves.map((item) => <div className="rounded-lg bg-slate-50 p-2 text-sm" key={item.id}>{item.leave_date}</div>)}{!leaves.length && <p className="text-sm text-slate-500">No upcoming leave.</p>}</div></article></div>}
  <div className="grid gap-6 lg:grid-cols-2"><AppointmentList title="Today’s appointments" items={today} onSelect={inspect} /><AppointmentList title="Upcoming appointments" items={upcoming} onSelect={inspect} /></div>
  {selected && <article className="rounded-2xl border border-care-200 bg-white p-6"><div className="flex justify-between"><div><h2 className="text-xl font-semibold">{selected.patient_name}</h2><p className="text-sm text-slate-500">{new Date(selected.slot_start).toLocaleString()}</p></div><StatusBadge status={selected.status} /></div>{selected.symptoms ? <dl className="mt-5 grid gap-4 sm:grid-cols-2"><div><dt className="text-xs uppercase text-slate-500">Chief complaint</dt><dd>{selected.symptoms.chief_complaint}</dd></div><div><dt className="text-xs uppercase text-slate-500">Duration / severity</dt><dd>{selected.symptoms.duration} · {selected.symptoms.severity}/10</dd></div><div className="sm:col-span-2"><dt className="text-xs uppercase text-slate-500">Original description</dt><dd>{selected.symptoms.symptom_description}</dd></div><div><dt className="text-xs uppercase text-slate-500">Conditions</dt><dd>{selected.symptoms.existing_conditions || "None reported"}</dd></div><div><dt className="text-xs uppercase text-slate-500">Medications</dt><dd>{selected.symptoms.current_medications || "None reported"}</dd></div></dl> : <p className="mt-4 text-slate-500">No symptom submission.</p>}</article>}</section>;
}

function AppointmentList({ title, items, onSelect }: { title: string; items: AppointmentListItem[]; onSelect: (id: string) => void }) {
  return <article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">{title}</h2><div className="mt-4 space-y-2">{items.map((item) => <button className="flex w-full items-center justify-between rounded-lg bg-slate-50 p-3 text-left text-sm hover:bg-care-50" key={item.id} onClick={() => onSelect(item.id)}><span><span className="block font-medium">{item.patient_name}</span><span className="text-slate-500">{new Date(item.slot_start).toLocaleTimeString()}</span></span><StatusBadge status={item.status} /></button>)}{!items.length && <p className="text-sm text-slate-500">No appointments.</p>}</div></article>;
}
