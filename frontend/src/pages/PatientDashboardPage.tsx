import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import type { AppointmentListItem, HoldResponse, PatientPostVisitSummary, PreVisitSummary, SymptomInput } from "../types/appointment";
import type { DoctorPublic, SlotPreview } from "../types/doctor";
import { MedicationScheduleCards } from "../components/MedicationScheduleCards";

const inputClass = "ui-input";
const buttonClass = "ui-button-primary";
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
  const [preVisit, setPreVisit] = useState<PreVisitSummary | null>(null);
  const [postVisit, setPostVisit] = useState<PatientPostVisitSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [calendar, setCalendar] = useState<{ status: "connected" | "reauthorization_required" | "disconnected"; calendar_id: string | null } | null>(null);
  const [calendarBusy, setCalendarBusy] = useState(false);

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

  useEffect(() => { if (!accessToken) return; api.calendarStatus(accessToken).then(setCalendar).catch(() => setCalendar(null)); }, [accessToken]);

  useEffect(() => {
    const result = new URLSearchParams(window.location.search).get("calendar");
    if (!result) return;
    if (result === "connected") {
      setNotice("Google Calendar connected. Future appointment changes will be queued for synchronization.");
      if (accessToken) api.calendarStatus(accessToken).then(setCalendar).catch(() => setCalendar(null));
    } else if (result === "failed") {
      setError("Google Calendar authorization was not completed. Your appointments are unaffected.");
    }
    window.history.replaceState({}, "", window.location.pathname);
  }, [accessToken]);

  const connectCalendar = async () => { if (!accessToken) return; setCalendarBusy(true); try { const result = await api.connectCalendar(accessToken); window.location.assign(result.authorization_url); } catch { setError("Google Calendar could not be started. Your appointments are unaffected."); setCalendarBusy(false); } };
  const disconnectCalendar = async () => { if (!accessToken || !window.confirm("Disconnect Google Calendar? Pending Calendar sync jobs will be cancelled.")) return; setCalendarBusy(true); try { await api.disconnectCalendar(accessToken); setCalendar(await api.calendarStatus(accessToken)); setNotice("Google Calendar disconnected."); } catch { setError("Google Calendar could not be disconnected."); } finally { setCalendarBusy(false); } };
  const syncCalendar = async (appointmentId: string) => { if (!accessToken) return; try { await api.syncCalendarAppointment(accessToken, appointmentId); setNotice("Calendar synchronization queued. Appointments remain confirmed if synchronization fails."); } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Calendar sync could not be queued."); } };

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

  const loadVisitIntelligence = async (appointmentId: string) => {
    if (!accessToken) return;
    setError("");
    setPreVisit(null);
    setPostVisit(null);
    try {
      setPreVisit(await api.patientPreVisitSummary(accessToken, appointmentId));
      try {
        setPostVisit(await api.patientPostVisitSummary(accessToken, appointmentId));
      } catch (caught) {
        if (!(caught instanceof ApiError) || caught.status !== 404) throw caught;
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load visit summaries.");
    }
  };

  return (
    <section className="space-y-10">
      <div className="rounded-3xl bg-gradient-to-br from-care-900 via-care-800 to-ink p-7 text-white shadow-lift sm:p-9"><p className="text-sm font-semibold uppercase tracking-wider text-care-100">Patient workspace</p><h1 className="mt-2 text-3xl font-bold text-white sm:text-4xl">Hello, {user?.full_name}</h1><p className="mt-3 max-w-2xl text-slate-200">Manage appointments, prepare for visits, and keep approved follow-up guidance close at hand.</p></div>
      {loading && <p className="ui-card-muted p-4 text-sm text-slate-600">Loading your doctors and appointments…</p>}
      {error && <p className="ui-alert-error" role="alert">{error}</p>}
      {notice && <p className="ui-alert-success">{notice}</p>}
      <section className="rounded-2xl border bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Google Calendar</h2><p className="mt-1 text-sm text-slate-600">{calendarBusy ? "Connecting…" : calendar ? calendar.status.replaceAll("_", " ") : "Loading Calendar status…"}. Appointments remain confirmed even if Calendar synchronization fails.</p>{calendar?.calendar_id && <p className="mt-1 text-xs text-slate-500">Calendar: {calendar.calendar_id}</p>}</div>{calendar?.status === "connected" ? <button className="rounded-lg border px-4 py-2 text-sm" disabled={calendarBusy} onClick={disconnectCalendar}>{calendarBusy ? "Disconnecting…" : "Disconnect"}</button> : <button className={buttonClass} disabled={calendarBusy || !calendar} onClick={connectCalendar}>{calendarBusy ? "Connecting…" : calendar?.status === "reauthorization_required" ? "Reconnect Google Calendar" : "Connect Google Calendar"}</button>}</div></section>

      <section><h2 className="text-2xl font-semibold">My appointments</h2><div className="mt-4 grid gap-4 lg:grid-cols-2"><AppointmentGroup title="Upcoming" items={upcoming} onCancel={cancel} onSummary={loadVisitIntelligence} onCalendarSync={calendar?.status === "connected" ? syncCalendar : undefined} onReschedule={(id) => { setReschedulingId(id); setNotice("Choose and hold a replacement slot below."); window.scrollTo({ top: 500, behavior: "smooth" }); }} /><AppointmentGroup title="Past and cancelled" items={past} onSummary={loadVisitIntelligence} onCalendarSync={calendar?.status === "connected" ? syncCalendar : undefined} /></div></section>

      {preVisit && <section className="rounded-2xl border border-care-200 bg-white p-6"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Pre-visit Care Packet</h2><div className="flex gap-2"><StatusBadge status={preVisit.status} />{preVisit.urgency && <span className="rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-900">{preVisit.urgency} urgency</span>}</div></div>{preVisit.generation_source === "deterministic_fallback" && <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">A reliable standard summary is shown because AI generation was unavailable.</p>}<h3 className="mt-4 font-medium">{preVisit.chief_complaint}</h3><ol className="mt-3 list-decimal space-y-2 pl-5 text-sm">{preVisit.suggested_questions?.map((question) => <li key={question}>{question}</li>)}</ol>{preVisit.safety_disclaimer && <p className="mt-4 text-xs text-slate-500">{preVisit.safety_disclaimer}</p>}
      {postVisit ? postVisit.availability === "approved" && postVisit.approved_content ? <div className="mt-6 border-t pt-5"><h2 className="text-xl font-semibold">Post-visit summary</h2><p className="mt-3">{postVisit.approved_content.patient_friendly_summary}</p><h3 className="mt-4 font-medium">Medication schedule</h3><MedicationScheduleCards items={postVisit.approved_content.medication_schedule} /><h3 className="mt-4 font-medium">Follow-up steps</h3><ul className="list-disc pl-5 text-sm">{postVisit.approved_content.follow_up_steps.map((step) => <li key={step}>{step}</li>)}</ul>{postVisit.approved_content.safety_disclaimer && <p className="mt-4 text-xs text-slate-500">{postVisit.approved_content.safety_disclaimer}</p>}</div> : <p className="mt-6 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Post-visit summary awaiting doctor review.</p> : null}</section>}

      <section><h2 className="text-2xl font-semibold">Find a doctor</h2><form className="mt-4 flex max-w-xl gap-2" onSubmit={(event) => { event.preventDefault(); loadDoctors(1, search); }}><input className={`${inputClass} min-w-0 flex-1`} placeholder="Search specialisation" value={search} onChange={(e) => setSearch(e.target.value)} /><button className={buttonClass}>Search</button></form><div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1.2fr]"><div><p className="mb-3 text-sm text-slate-500">{total} doctors found</p><div className="space-y-3">{doctors.map((doctor) => <button className={`w-full rounded-2xl border bg-white p-5 text-left ${selected?.id === doctor.id ? "border-care-500" : "border-slate-200"}`} key={doctor.id} onClick={() => { setSelected(doctor); setPreview(null); setHold(null); }}><span className="block font-semibold">{doctor.full_name}</span><span className="text-sm text-care-700">{doctor.specialisation}</span></button>)}</div><div className="mt-4 flex gap-2"><button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={page <= 1} onClick={() => loadDoctors(page - 1)}>Previous</button><button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={page * 10 >= total} onClick={() => loadDoctors(page + 1)}>Next</button></div></div>
      {selected ? <div className="rounded-2xl border border-slate-200 bg-white p-6"><h3 className="text-xl font-semibold">{selected.full_name}</h3><p className="text-care-700">{selected.specialisation}</p><p className="mt-3 text-sm text-slate-600">{selected.biography}</p><div className="mt-5 flex gap-2"><input className={inputClass} type="date" value={date} onChange={(e) => setDate(e.target.value)} /><button className={buttonClass} onClick={showSlots}>Preview slots</button></div>{preview && <div className="mt-5"><p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">{preview.disclaimer}</p><div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">{preview.slots.map((slot) => <button className="rounded-lg border border-care-200 bg-care-50 p-2 text-sm text-care-900 hover:bg-care-100" key={slot.start} onClick={() => holdSlot(slot.start)}>{new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit", timeZone: preview.timezone }).format(new Date(slot.start))}</button>)}</div>{!preview.slots.length && <p className="mt-3 text-sm text-slate-500">No available slots.</p>}</div>}</div> : <div className="rounded-2xl border border-dashed p-10 text-center text-slate-500">Select a doctor.</div>}</div></section>

      {hold && <form className="rounded-2xl border-2 border-care-500 bg-white p-6" onSubmit={completeBooking}><div className="flex items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">{reschedulingId ? "Confirm replacement slot" : "Complete symptom form"}</h2><p className="mt-1 text-sm text-slate-500">Server hold expires at {new Date(hold.expires_at).toLocaleTimeString()}.</p></div><span className="rounded-full bg-care-100 px-3 py-1 font-mono text-care-900">{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}</span></div>{!reschedulingId && <div className="mt-5 grid gap-3 sm:grid-cols-2"><input className={inputClass} required placeholder="Chief complaint" value={symptoms.chief_complaint} onChange={(e) => setSymptoms({ ...symptoms, chief_complaint: e.target.value })} /><input className={inputClass} required placeholder="Duration" value={symptoms.duration} onChange={(e) => setSymptoms({ ...symptoms, duration: e.target.value })} /><textarea className={`${inputClass} sm:col-span-2`} required placeholder="Describe your symptoms" value={symptoms.symptom_description} onChange={(e) => setSymptoms({ ...symptoms, symptom_description: e.target.value })} /><label className="text-sm">Severity: {symptoms.severity}<input className="block w-full" type="range" min="1" max="10" value={symptoms.severity} onChange={(e) => setSymptoms({ ...symptoms, severity: Number(e.target.value) })} /></label><input className={inputClass} placeholder="Existing conditions (optional)" value={symptoms.existing_conditions ?? ""} onChange={(e) => setSymptoms({ ...symptoms, existing_conditions: e.target.value || null })} /><input className={inputClass} placeholder="Current medications (optional)" value={symptoms.current_medications ?? ""} onChange={(e) => setSymptoms({ ...symptoms, current_medications: e.target.value || null })} /></div>}<button className={`${buttonClass} mt-5`} disabled={!remaining}>{reschedulingId ? "Confirm reschedule" : "Confirm appointment"}</button><p className="mt-2 text-xs text-slate-500">The countdown is informational; the server is authoritative.</p></form>}
    </section>
  );
}

function AppointmentGroup({ title, items, onCancel, onReschedule, onSummary, onCalendarSync }: { title: string; items: AppointmentListItem[]; onCancel?: (id: string) => void; onReschedule?: (id: string) => void; onSummary?: (id: string) => void; onCalendarSync?: (id: string) => void }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-5"><h3 className="font-semibold">{title}</h3><div className="mt-3 space-y-3">{items.map((item) => <div className="rounded-xl bg-slate-50 p-3 text-sm" key={item.id}><div className="flex justify-between gap-2"><span className="font-medium">{item.doctor_name}</span><StatusBadge status={item.status} /></div><p className="mt-1 text-slate-500">{new Date(item.slot_start).toLocaleString()}</p><div className="mt-2 flex flex-wrap gap-3">{onSummary && <button className="text-care-700" onClick={() => onSummary(item.id)}>Visit summaries</button>}{onCalendarSync && <button className="text-care-700" onClick={() => onCalendarSync(item.id)}>Sync Calendar</button>}{onCancel && item.status !== "cancelled" && <><button className="text-red-600" onClick={() => onCancel(item.id)}>Cancel</button><button className="text-care-700" onClick={() => onReschedule?.(item.id)}>Reschedule</button></>}</div></div>)}{!items.length && <p className="text-sm text-slate-500">Nothing here yet.</p>}</div></div>;
}

export function StatusBadge({ status }: { status: string }) {
  return <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs capitalize">{status.replaceAll("_", " ")}</span>;
}
