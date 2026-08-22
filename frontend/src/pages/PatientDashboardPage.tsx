import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import type { AppointmentListItem, HoldResponse, SymptomInput } from "../types/appointment";
import type { DoctorPublic, SlotPreview } from "../types/doctor";

const inputClass = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";
const buttonClass = "rounded-lg bg-care-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50";
const emptySymptoms: SymptomInput = {
  chief_complaint: "",
  symptom_description: "",
  duration: "",
  severity: 5,
  existing_conditions: null,
  current_medications: null,
};

export function PatientDashboardPage() {
  const { user, accessToken } = useAuth();
  const [doctors, setDoctors] = useState<DoctorPublic[]>([]);
  const [appointments, setAppointments] = useState<AppointmentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<DoctorPublic | null>(null);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [preview, setPreview] = useState<SlotPreview | null>(null);
  const [hold, setHold] = useState<HoldResponse | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [symptoms, setSymptoms] = useState(emptySymptoms);
  const [reschedulingId, setReschedulingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadAppointments = async () => {
    if (!accessToken) return;
    const result = await api.patientAppointments(accessToken);
    setAppointments(result.items);
  };

  const loadDoctors = async (requestedPage = page, term = search) => {
    if (!accessToken) return;
    try {
      const result = await api.publicDoctors(accessToken, term, requestedPage);
      setDoctors(result.items);
      setTotal(result.total);
      setPage(result.page);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load doctors.");
    }
  };

  useEffect(() => {
    if (!accessToken) return;
    Promise.all([loadDoctors(1, ""), loadAppointments()])
      .catch(() => setError("Could not load your dashboard."))
      .finally(() => setLoading(false));
  }, [accessToken]);

  useEffect(() => {
    if (!hold) return;
    const update = () => {
      const seconds = Math.max(0, Math.floor((new Date(hold.expires_at).getTime() - Date.now()) / 1000));
      setRemaining(seconds);
      if (!seconds) setHold(null);
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [hold]);

  const upcoming = useMemo(() => appointments.filter((item) => new Date(item.slot_end) >= new Date() && item.status !== "cancelled"), [appointments]);
  const past = useMemo(() => appointments.filter((item) => new Date(item.slot_end) < new Date() || item.status === "cancelled"), [appointments]);

  const showSlots = async () => {
    if (!accessToken || !selected) return;
    try {
      setError("");
      setPreview(await api.previewSlots(accessToken, selected.id, date));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not generate slots.");
    }
  };

  const holdSlot = async (slotStart: string) => {
    if (!accessToken || !selected) return;
    try {
      setError("");
      setNotice("");
      const created = await api.holdSlot(accessToken, selected.id, slotStart);
      setHold(created);
      setRemaining(created.remaining_seconds);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The slot could not be held.");
      await showSlots();
    }
  };

  const completeBooking = async (event: FormEvent) => {
    event.preventDefault();
    if (!accessToken || !hold) return;
    try {
      if (reschedulingId) {
        await api.rescheduleAppointment(accessToken, reschedulingId, hold.hold_token);
        setNotice("Appointment rescheduled successfully.");
      } else {
        await api.confirmAppointment(accessToken, hold.hold_token, symptoms);
        setNotice("Appointment confirmed successfully.");
      }
      setHold(null);
      setSymptoms(emptySymptoms);
      setReschedulingId(null);
      setPreview(null);
      await loadAppointments();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The appointment could not be confirmed.");
    }
  };

  const cancel = async (appointmentId: string) => {
    if (!accessToken || !window.confirm("Cancel this appointment?")) return;
    try {
      await api.cancelAppointment(accessToken, appointmentId, "Cancelled by patient");
      setNotice("Appointment cancelled. The slot is available again.");
      await loadAppointments();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Cancellation failed.");
    }
  };

  return (
    <section className="space-y-10">
      <div><p className="text-sm font-semibold uppercase tracking-wider text-care-600">Patient workspace</p><h1 className="mt-1 text-3xl font-bold">Hello, {user?.full_name}</h1><p className="mt-2 text-slate-600">Preview, briefly hold, and confirm an appointment.</p></div>
      {loading && <p className="rounded-xl bg-slate-100 p-3 text-sm text-slate-600">Loading your doctors and appointments…</p>}
      {error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}
      {notice && <p className="rounded-xl bg-care-50 p-3 text-sm text-care-800">{notice}</p>}

      <section><h2 className="text-2xl font-semibold">My appointments</h2><div className="mt-4 grid gap-4 lg:grid-cols-2"><AppointmentGroup title="Upcoming" items={upcoming} onCancel={cancel} onReschedule={(id) => { setReschedulingId(id); setNotice("Choose and hold a replacement slot below."); window.scrollTo({ top: 500, behavior: "smooth" }); }} /><AppointmentGroup title="Past and cancelled" items={past} /></div></section>

      <section><h2 className="text-2xl font-semibold">Find a doctor</h2><form className="mt-4 flex max-w-xl gap-2" onSubmit={(event) => { event.preventDefault(); loadDoctors(1, search); }}><input className={`${inputClass} min-w-0 flex-1`} placeholder="Search specialisation" value={search} onChange={(e) => setSearch(e.target.value)} /><button className={buttonClass}>Search</button></form><div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1.2fr]"><div><p className="mb-3 text-sm text-slate-500">{total} doctors found</p><div className="space-y-3">{doctors.map((doctor) => <button className={`w-full rounded-2xl border bg-white p-5 text-left ${selected?.id === doctor.id ? "border-care-500" : "border-slate-200"}`} key={doctor.id} onClick={() => { setSelected(doctor); setPreview(null); setHold(null); }}><span className="block font-semibold">{doctor.full_name}</span><span className="text-sm text-care-700">{doctor.specialisation}</span></button>)}</div><div className="mt-4 flex gap-2"><button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={page <= 1} onClick={() => loadDoctors(page - 1)}>Previous</button><button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={page * 10 >= total} onClick={() => loadDoctors(page + 1)}>Next</button></div></div>
      {selected ? <div className="rounded-2xl border border-slate-200 bg-white p-6"><h3 className="text-xl font-semibold">{selected.full_name}</h3><p className="text-care-700">{selected.specialisation}</p><p className="mt-3 text-sm text-slate-600">{selected.biography}</p><div className="mt-5 flex gap-2"><input className={inputClass} type="date" value={date} onChange={(e) => setDate(e.target.value)} /><button className={buttonClass} onClick={showSlots}>Preview slots</button></div>{preview && <div className="mt-5"><p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">{preview.disclaimer}</p><div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">{preview.slots.map((slot) => <button className="rounded-lg border border-care-200 bg-care-50 p-2 text-sm text-care-900 hover:bg-care-100" key={slot.start} onClick={() => holdSlot(slot.start)}>{new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit", timeZone: preview.timezone }).format(new Date(slot.start))}</button>)}</div>{!preview.slots.length && <p className="mt-3 text-sm text-slate-500">No available slots.</p>}</div>}</div> : <div className="rounded-2xl border border-dashed p-10 text-center text-slate-500">Select a doctor.</div>}</div></section>

      {hold && <form className="rounded-2xl border-2 border-care-500 bg-white p-6" onSubmit={completeBooking}><div className="flex items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">{reschedulingId ? "Confirm replacement slot" : "Complete symptom form"}</h2><p className="mt-1 text-sm text-slate-500">Server hold expires at {new Date(hold.expires_at).toLocaleTimeString()}.</p></div><span className="rounded-full bg-care-100 px-3 py-1 font-mono text-care-900">{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}</span></div>{!reschedulingId && <div className="mt-5 grid gap-3 sm:grid-cols-2"><input className={inputClass} required placeholder="Chief complaint" value={symptoms.chief_complaint} onChange={(e) => setSymptoms({ ...symptoms, chief_complaint: e.target.value })} /><input className={inputClass} required placeholder="Duration" value={symptoms.duration} onChange={(e) => setSymptoms({ ...symptoms, duration: e.target.value })} /><textarea className={`${inputClass} sm:col-span-2`} required placeholder="Describe your symptoms" value={symptoms.symptom_description} onChange={(e) => setSymptoms({ ...symptoms, symptom_description: e.target.value })} /><label className="text-sm">Severity: {symptoms.severity}<input className="block w-full" type="range" min="1" max="10" value={symptoms.severity} onChange={(e) => setSymptoms({ ...symptoms, severity: Number(e.target.value) })} /></label><input className={inputClass} placeholder="Existing conditions (optional)" value={symptoms.existing_conditions ?? ""} onChange={(e) => setSymptoms({ ...symptoms, existing_conditions: e.target.value || null })} /><input className={inputClass} placeholder="Current medications (optional)" value={symptoms.current_medications ?? ""} onChange={(e) => setSymptoms({ ...symptoms, current_medications: e.target.value || null })} /></div>}<button className={`${buttonClass} mt-5`} disabled={!remaining}>{reschedulingId ? "Confirm reschedule" : "Confirm appointment"}</button><p className="mt-2 text-xs text-slate-500">The countdown is informational; the server is authoritative.</p></form>}
    </section>
  );
}

function AppointmentGroup({ title, items, onCancel, onReschedule }: { title: string; items: AppointmentListItem[]; onCancel?: (id: string) => void; onReschedule?: (id: string) => void }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-5"><h3 className="font-semibold">{title}</h3><div className="mt-3 space-y-3">{items.map((item) => <div className="rounded-xl bg-slate-50 p-3 text-sm" key={item.id}><div className="flex justify-between gap-2"><span className="font-medium">{item.doctor_name}</span><StatusBadge status={item.status} /></div><p className="mt-1 text-slate-500">{new Date(item.slot_start).toLocaleString()}</p>{onCancel && item.status !== "cancelled" && <div className="mt-2 flex gap-3"><button className="text-red-600" onClick={() => onCancel(item.id)}>Cancel</button><button className="text-care-700" onClick={() => onReschedule?.(item.id)}>Reschedule</button></div>}</div>)}{!items.length && <p className="text-sm text-slate-500">Nothing here yet.</p>}</div></div>;
}

export function StatusBadge({ status }: { status: string }) {
  return <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs capitalize">{status.replaceAll("_", " ")}</span>;
}
