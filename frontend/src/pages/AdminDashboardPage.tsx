import { useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import type { DoctorAdmin, DoctorProvisionInput, WorkingHourInput } from "../types/doctor";

const inputClass = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";
const buttonClass = "rounded-lg bg-care-600 px-4 py-2 text-sm font-semibold text-white hover:bg-care-700 disabled:opacity-50";
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const emptyDoctor: DoctorProvisionInput = {
  full_name: "",
  email: "",
  initial_password: "",
  specialisation: "",
  qualifications: "",
  biography: "",
  consultation_mode: "in_person",
  location: "",
  slot_duration_minutes: 30,
  timezone: "Asia/Kolkata",
  is_available_for_booking: true,
};

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "The request could not be completed.";
}

export function AdminDashboardPage() {
  const { accessToken } = useAuth();
  const [doctors, setDoctors] = useState<DoctorAdmin[]>([]);
  const [selected, setSelected] = useState<DoctorAdmin | null>(null);
  const [createForm, setCreateForm] = useState(emptyDoctor);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadDoctors = async (selectId?: string) => {
    if (!accessToken) return;
    const result = await api.adminDoctors(accessToken);
    setDoctors(result.items);
    const id = selectId ?? selected?.id;
    if (id) {
      const match = result.items.find((doctor) => doctor.id === id);
      setSelected(match ? await api.adminGetDoctor(accessToken, id) : null);
    }
  };

  useEffect(() => {
    loadDoctors().catch((caught) => setError(message(caught)));
  }, [accessToken]);

  const createDoctor = async (event: FormEvent) => {
    event.preventDefault();
    if (!accessToken) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.adminCreateDoctor(accessToken, createForm);
      setCreateForm(emptyDoctor);
      setShowCreate(false);
      await loadDoctors(created.id);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  };

  const chooseDoctor = async (doctorId: string) => {
    if (!accessToken) return;
    setError("");
    try {
      setSelected(await api.adminGetDoctor(accessToken, doctorId));
    } catch (caught) {
      setError(message(caught));
    }
  };

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-care-600">Administration</p>
          <h1 className="mt-1 text-3xl font-bold">Doctor management</h1>
          <p className="mt-2 text-slate-600">Provision accounts, profiles, schedules, and full-day leave.</p>
        </div>
        <button className={buttonClass} type="button" onClick={() => setShowCreate((value) => !value)}>
          {showCreate ? "Close form" : "Create doctor"}
        </button>
      </div>

      {error && <p className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}

      {showCreate && (
        <form className="mt-6 grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 sm:grid-cols-2" onSubmit={createDoctor}>
          <h2 className="text-lg font-semibold sm:col-span-2">New doctor account</h2>
          <input className={inputClass} placeholder="Full name" required value={createForm.full_name} onChange={(event) => setCreateForm({ ...createForm, full_name: event.target.value })} />
          <input className={inputClass} placeholder="Email" type="email" required value={createForm.email} onChange={(event) => setCreateForm({ ...createForm, email: event.target.value })} />
          <input className={inputClass} placeholder="Initial password" type="password" required value={createForm.initial_password} onChange={(event) => setCreateForm({ ...createForm, initial_password: event.target.value })} />
          <input className={inputClass} placeholder="Specialisation" required value={createForm.specialisation} onChange={(event) => setCreateForm({ ...createForm, specialisation: event.target.value })} />
          <input className={inputClass} placeholder="Qualifications" value={createForm.qualifications} onChange={(event) => setCreateForm({ ...createForm, qualifications: event.target.value })} />
          <input className={inputClass} placeholder="Location" value={createForm.location ?? ""} onChange={(event) => setCreateForm({ ...createForm, location: event.target.value })} />
          <textarea className={`${inputClass} sm:col-span-2`} placeholder="Biography" value={createForm.biography} onChange={(event) => setCreateForm({ ...createForm, biography: event.target.value })} />
          <p className="text-xs text-slate-500 sm:col-span-2">Password must have at least 10 characters, upper/lowercase letters, and a number.</p>
          <button className={`${buttonClass} sm:col-span-2`} disabled={busy} type="submit">{busy ? "Creating…" : "Create doctor and profile"}</button>
        </form>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-[300px_1fr]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-4">
          <h2 className="px-2 pb-3 font-semibold">All doctors ({doctors.length})</h2>
          <div className="space-y-2">
            {doctors.map((doctor) => (
              <button key={doctor.id} className={`w-full rounded-xl p-3 text-left ${selected?.id === doctor.id ? "bg-care-50 ring-1 ring-care-500" : "hover:bg-slate-50"}`} type="button" onClick={() => chooseDoctor(doctor.id)}>
                <span className="block font-medium">{doctor.full_name}</span>
                <span className="block text-sm text-slate-500">{doctor.specialisation}</span>
                <span className={`mt-1 inline-block text-xs ${doctor.is_active ? "text-care-700" : "text-red-600"}`}>{doctor.is_active ? "Active" : "Inactive"}</span>
              </button>
            ))}
            {!doctors.length && <p className="p-2 text-sm text-slate-500">No doctors have been provisioned.</p>}
          </div>
        </aside>
        {selected ? (
          <DoctorManager doctor={selected} token={accessToken!} onChanged={() => loadDoctors(selected.id)} onError={setError} />
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 p-10 text-center text-slate-500">Select a doctor to manage their profile and schedule.</div>
        )}
      </div>
    </section>
  );
}

function DoctorManager({ doctor, token, onChanged, onError }: { doctor: DoctorAdmin; token: string; onChanged: () => Promise<void>; onError: (value: string) => void }) {
  const [profile, setProfile] = useState(doctor);
  const [hour, setHour] = useState<WorkingHourInput>({ day_of_week: 0, start_time: "09:00", end_time: "17:00" });
  const [editingHour, setEditingHour] = useState<string | null>(null);
  const [leaveDate, setLeaveDate] = useState("");
  const [leaveReason, setLeaveReason] = useState("");

  useEffect(() => setProfile(doctor), [doctor]);

  const run = async (operation: () => Promise<unknown>) => {
    onError("");
    try {
      await operation();
      await onChanged();
    } catch (caught) {
      onError(message(caught));
    }
  };

  const saveProfile = (event: FormEvent) => {
    event.preventDefault();
    return run(() => api.adminUpdateDoctor(token, doctor.id, {
      full_name: profile.full_name,
      specialisation: profile.specialisation,
      qualifications: profile.qualifications,
      biography: profile.biography,
      consultation_mode: profile.consultation_mode,
      location: profile.location,
      slot_duration_minutes: Number(profile.slot_duration_minutes),
      timezone: profile.timezone,
      is_active: profile.is_active,
      is_available_for_booking: profile.is_available_for_booking,
    }));
  };

  const saveHour = (event: FormEvent) => {
    event.preventDefault();
    const operation = editingHour
      ? api.adminUpdateWorkingHour(token, doctor.id, editingHour, hour)
      : api.adminAddWorkingHour(token, doctor.id, hour);
    return run(async () => {
      await operation;
      setEditingHour(null);
    });
  };

  return (
    <div className="space-y-6">
      <form className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 sm:grid-cols-2" onSubmit={saveProfile}>
        <h2 className="text-xl font-semibold sm:col-span-2">Profile</h2>
        <label className="text-sm">Name<input className={`${inputClass} mt-1`} value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} /></label>
        <label className="text-sm">Specialisation<input className={`${inputClass} mt-1`} value={profile.specialisation} onChange={(e) => setProfile({ ...profile, specialisation: e.target.value })} /></label>
        <label className="text-sm">Qualifications<input className={`${inputClass} mt-1`} value={profile.qualifications} onChange={(e) => setProfile({ ...profile, qualifications: e.target.value })} /></label>
        <label className="text-sm">Location<input className={`${inputClass} mt-1`} value={profile.location ?? ""} onChange={(e) => setProfile({ ...profile, location: e.target.value })} /></label>
        <label className="text-sm">Timezone<input className={`${inputClass} mt-1`} value={profile.timezone} onChange={(e) => setProfile({ ...profile, timezone: e.target.value })} /></label>
        <label className="text-sm">Slot minutes<input className={`${inputClass} mt-1`} type="number" min="5" max="180" value={profile.slot_duration_minutes} onChange={(e) => setProfile({ ...profile, slot_duration_minutes: Number(e.target.value) })} /></label>
        <label className="text-sm">Mode<select className={`${inputClass} mt-1`} value={profile.consultation_mode} onChange={(e) => setProfile({ ...profile, consultation_mode: e.target.value })}><option value="in_person">In person</option><option value="video">Video</option><option value="hybrid">Hybrid</option></select></label>
        <div className="flex items-end gap-5 pb-2 text-sm"><label><input type="checkbox" checked={profile.is_active} onChange={(e) => setProfile({ ...profile, is_active: e.target.checked })} /> Account active</label><label><input type="checkbox" checked={profile.is_available_for_booking} onChange={(e) => setProfile({ ...profile, is_available_for_booking: e.target.checked })} /> Discoverable</label></div>
        <label className="text-sm sm:col-span-2">Biography<textarea className={`${inputClass} mt-1`} value={profile.biography} onChange={(e) => setProfile({ ...profile, biography: e.target.value })} /></label>
        <button className={`${buttonClass} sm:col-span-2`} type="submit">Save profile</button>
      </form>

      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-semibold">Working hours</h2>
        <div className="mt-4 space-y-2">{doctor.working_hours.map((item) => <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 p-3 text-sm" key={item.id}><span>{weekdays[item.day_of_week]} · {item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}</span><div className="flex gap-2"><button className="text-care-700" type="button" onClick={() => { setEditingHour(item.id); setHour({ day_of_week: item.day_of_week, start_time: item.start_time.slice(0, 5), end_time: item.end_time.slice(0, 5) }); }}>Edit</button><button className="text-red-600" type="button" onClick={() => run(() => api.adminDeleteWorkingHour(token, doctor.id, item.id))}>Delete</button></div></div>)}</div>
        <form className="mt-4 grid gap-3 sm:grid-cols-4" onSubmit={saveHour}>
          <select className={inputClass} value={hour.day_of_week} onChange={(e) => setHour({ ...hour, day_of_week: Number(e.target.value) })}>{weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}</select>
          <input className={inputClass} type="time" required value={hour.start_time} onChange={(e) => setHour({ ...hour, start_time: e.target.value })} />
          <input className={inputClass} type="time" required value={hour.end_time} onChange={(e) => setHour({ ...hour, end_time: e.target.value })} />
          <button className={buttonClass} type="submit">{editingHour ? "Update" : "Add interval"}</button>
        </form>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-semibold">Full-day leave</h2>
        <div className="mt-4 space-y-2">{doctor.leaves.map((item) => <div className="flex items-center justify-between rounded-lg bg-slate-50 p-3 text-sm" key={item.id}><span>{item.leave_date}{item.reason ? ` · ${item.reason}` : ""}</span><button className="text-red-600" type="button" onClick={() => run(() => api.adminDeleteLeave(token, doctor.id, item.id))}>Remove</button></div>)}</div>
        <form className="mt-4 grid gap-3 sm:grid-cols-[180px_1fr_auto]" onSubmit={(event) => { event.preventDefault(); run(async () => { await api.adminAddLeave(token, doctor.id, leaveDate, leaveReason); setLeaveDate(""); setLeaveReason(""); }); }}>
          <input className={inputClass} type="date" required value={leaveDate} onChange={(e) => setLeaveDate(e.target.value)} />
          <input className={inputClass} placeholder="Optional private reason" value={leaveReason} onChange={(e) => setLeaveReason(e.target.value)} />
          <button className={buttonClass} type="submit">Add leave</button>
        </form>
        <p className="mt-3 text-xs text-slate-500">Appointment-conflict notifications will be added with booking in Phase 2B.</p>
      </div>
    </div>
  );
}

