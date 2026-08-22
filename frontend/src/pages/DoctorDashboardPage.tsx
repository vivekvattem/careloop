import { useEffect, useMemo, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import type { AppointmentDetail, AppointmentListItem, CompleteVisitInput, PostVisitSummary, PreVisitSummary, PrescriptionItemInput } from "../types/appointment";
import type { DoctorLeave, DoctorSchedule, DoctorSelf } from "../types/doctor";
import { StatusBadge } from "./PatientDashboardPage";

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const inputClass = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";
const buttonClass = "rounded-lg bg-care-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50";
const emptyMedication = (): PrescriptionItemInput => ({ medication_name: "", dosage: "", route: null, frequency_per_day: 1, reminder_times: [], start_date: new Date().toISOString().slice(0, 10), end_date: null, food_instructions: null, additional_instructions: null, is_active: true });
const emptyVisit = (): CompleteVisitInput => ({ clinical_note: { original_notes: "", diagnosis: null, treatment_plan: null, follow_up_instructions: "", recommended_follow_up_date: null, private_doctor_notes: null }, prescription: { general_instructions: null, items: [] } });

export function DoctorDashboardPage() {
  const { accessToken } = useAuth();
  const [profile, setProfile] = useState<DoctorSelf | null>(null);
  const [schedule, setSchedule] = useState<DoctorSchedule | null>(null);
  const [leaves, setLeaves] = useState<DoctorLeave[]>([]);
  const [appointments, setAppointments] = useState<AppointmentListItem[]>([]);
  const [selected, setSelected] = useState<AppointmentDetail | null>(null);
  const [preVisit, setPreVisit] = useState<PreVisitSummary | null>(null);
  const [postVisit, setPostVisit] = useState<PostVisitSummary | null>(null);
  const [visit, setVisit] = useState<CompleteVisitInput>(emptyVisit());
  const [approvedEdit, setApprovedEdit] = useState("");
  const [busy, setBusy] = useState(false);
  const [regenerating, setRegenerating] = useState<"pre" | "post" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadAppointments = async () => {
    if (!accessToken) return;
    setAppointments((await api.doctorAppointments(accessToken)).items);
  };

  useEffect(() => {
    if (!accessToken) return;
    Promise.all([api.doctorProfile(accessToken), api.doctorSchedule(accessToken), api.doctorLeave(accessToken), api.doctorAppointments(accessToken)])
      .then(([profileResult, scheduleResult, leaveResult, appointmentResult]) => { setProfile(profileResult); setSchedule(scheduleResult); setLeaves(leaveResult.leaves); setAppointments(appointmentResult.items); })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load your workspace."));
  }, [accessToken]);

  const todayKey = new Date().toDateString();
  const today = useMemo(() => appointments.filter((item) => new Date(item.slot_start).toDateString() === todayKey), [appointments, todayKey]);
  const upcoming = useMemo(() => appointments.filter((item) => new Date(item.slot_start) > new Date() && new Date(item.slot_start).toDateString() !== todayKey), [appointments, todayKey]);

  const loadIntelligence = async (id: string) => {
    if (!accessToken) return;
    const [detail, pre] = await Promise.all([api.doctorAppointment(accessToken, id), api.doctorPreVisitSummary(accessToken, id)]);
    setSelected(detail); setPreVisit(pre); setPostVisit(null);
    if (detail.status === "completed") {
      const [record, post] = await Promise.all([api.clinicalRecord(accessToken, id), api.doctorPostVisitSummary(accessToken, id)]);
      setVisit({ clinical_note: { original_notes: record.original_notes, diagnosis: record.diagnosis, treatment_plan: record.treatment_plan, follow_up_instructions: record.follow_up_instructions, recommended_follow_up_date: record.recommended_follow_up_date, private_doctor_notes: record.private_doctor_notes }, prescription: { general_instructions: record.general_instructions, items: record.items } });
      setPostVisit(post); setApprovedEdit(post.patient_friendly_summary ?? "");
    } else setVisit(emptyVisit());
  };

  const inspect = async (id: string) => { setError(""); try { await loadIntelligence(id); } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Could not load appointment details."); } };
  const complete = async (event: FormEvent) => { event.preventDefault(); if (!accessToken || !selected) return; setBusy(true); setError(""); try { selected.status === "completed" ? await api.updateClinicalRecord(accessToken, selected.id, visit) : await api.completeVisit(accessToken, selected.id, visit); setNotice(selected.status === "completed" ? "Clinical record updated; summary regenerated." : "Visit completed; post-visit summary generation started."); await loadAppointments(); await loadIntelligence(selected.id); } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Could not save the visit."); } finally { setBusy(false); } };
  const regenerate = async (kind: "pre" | "post") => {
    if (!accessToken || !selected || regenerating) return;
    setBusy(true);
    setRegenerating(kind);
    setError("");
    try {
      if (kind === "pre") await api.regeneratePreVisitSummary(accessToken, selected.id);
      else await api.regeneratePostVisitSummary(accessToken, selected.id);
      setNotice(`${kind === "pre" ? "Pre" : "Post"}-visit generation started.`);

      const terminalStatuses = new Set(["completed", "fallback", "retry_pending", "failed"]);
      const deadline = Date.now() + 20_000;
      while (Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 2_000));
        if (kind === "pre") {
          const summary = await api.doctorPreVisitSummary(accessToken, selected.id);
          setPreVisit(summary);
          if (terminalStatuses.has(summary.status)) break;
        } else {
          const summary = await api.doctorPostVisitSummary(accessToken, selected.id);
          setPostVisit(summary);
          if (terminalStatuses.has(summary.status)) break;
        }
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Regeneration failed.");
    } finally {
      setRegenerating(null);
      setBusy(false);
    }
  };
  const review = async (decision: "approve" | "reject") => { if (!accessToken || !selected) return; try { const result = decision === "approve" ? await api.approvePostVisitSummary(accessToken, selected.id, approvedEdit) : await api.rejectPostVisitSummary(accessToken, selected.id); setPostVisit(result); setNotice(decision === "approve" ? "Summary approved for the patient." : "Summary rejected and remains hidden."); } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Review action failed."); } };
  const addMedication = () => setVisit({ ...visit, prescription: { ...visit.prescription, items: [...visit.prescription.items, emptyMedication()] } });
  const updateMedication = (index: number, fields: Partial<PrescriptionItemInput>) => setVisit({ ...visit, prescription: { ...visit.prescription, items: visit.prescription.items.map((item, itemIndex) => itemIndex === index ? { ...item, ...fields } : item) } });

  return <section className="space-y-8"><div><p className="text-sm font-semibold uppercase tracking-wider text-care-600">Doctor workspace</p><h1 className="mt-1 text-3xl font-bold">My practice</h1><p className="mt-2 text-slate-600">Review Care Packets, record visits, and approve patient-facing summaries.</p></div>{error && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}{notice && <p className="rounded-xl bg-care-50 p-3 text-sm text-care-800">{notice}</p>}{profile && <div className="grid gap-6 lg:grid-cols-3"><article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">{profile.full_name}</h2><p className="text-care-700">{profile.specialisation}</p><p className="mt-3 text-sm text-slate-600">{profile.biography}</p></article><article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">Weekly schedule</h2><p className="text-xs text-slate-500">{schedule?.slot_duration_minutes}-minute slots · {schedule?.timezone}</p><div className="mt-3 space-y-2">{schedule?.working_hours.map((item) => <div className="rounded-lg bg-slate-50 p-2 text-sm" key={item.id}>{weekdays[item.day_of_week]} · {item.start_time.slice(0, 5)}–{item.end_time.slice(0, 5)}</div>)}</div></article><article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">Upcoming leave</h2>{leaves.map((item) => <div className="mt-2 rounded-lg bg-slate-50 p-2 text-sm" key={item.id}>{item.leave_date}</div>)}{!leaves.length && <p className="mt-3 text-sm text-slate-500">No upcoming leave.</p>}</article></div>}
  <div className="grid gap-6 lg:grid-cols-2"><AppointmentList title="Today’s appointments" items={today} onSelect={inspect} /><AppointmentList title="Upcoming appointments" items={upcoming} onSelect={inspect} /></div>
  {selected && preVisit && <><article className="rounded-2xl border border-care-200 bg-white p-6"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-xl font-semibold">Pre-visit Care Packet</h2><p className="text-sm text-slate-500">{selected.patient_name} · original symptoms retained</p></div><div className="flex gap-2"><StatusBadge status={preVisit.status} />{preVisit.urgency && <span className="rounded-full bg-amber-100 px-2 py-1 text-xs">{preVisit.urgency}</span>}</div></div><p className="mt-4 font-medium">{preVisit.chief_complaint}</p><p className="mt-2 text-sm">{selected.symptoms?.symptom_description}</p><ol className="mt-4 list-decimal space-y-2 pl-5 text-sm">{preVisit.suggested_questions?.map((question) => <li key={question}>{question}</li>)}</ol>{preVisit.generation_source === "deterministic_fallback" && <p className="mt-3 text-xs text-slate-500">Standard deterministic summary</p>}<div className="mt-4"><h3 className="text-sm font-semibold">History sources used</h3>{preVisit.sources.map((source) => <p className="mt-1 text-xs text-slate-500" key={source.document_id}>#{source.rank_position} {source.document_type} · {new Date(source.event_date).toLocaleDateString()} · score {source.ranking_score.toFixed(2)}</p>)}{!preVisit.sources.length && <p className="text-xs text-slate-500">No prior verified CareLoop history used.</p>}</div><button className={`${buttonClass} mt-4`} disabled={busy || regenerating !== null} onClick={() => regenerate("pre")}>{regenerating === "pre" ? "Generating…" : "Regenerate Care Packet"}</button></article>
  <form className="space-y-4 rounded-2xl border bg-white p-6" onSubmit={complete}><h2 className="text-xl font-semibold">Clinical record</h2><textarea className={inputClass} required placeholder="Original internal clinical observations" value={visit.clinical_note.original_notes} onChange={(e) => setVisit({ ...visit, clinical_note: { ...visit.clinical_note, original_notes: e.target.value } })} /><input className={inputClass} placeholder="Assessment / diagnosis (optional)" value={visit.clinical_note.diagnosis ?? ""} onChange={(e) => setVisit({ ...visit, clinical_note: { ...visit.clinical_note, diagnosis: e.target.value || null } })} /><textarea className={inputClass} placeholder="Treatment plan (optional)" value={visit.clinical_note.treatment_plan ?? ""} onChange={(e) => setVisit({ ...visit, clinical_note: { ...visit.clinical_note, treatment_plan: e.target.value || null } })} /><textarea className={inputClass} placeholder="Private doctor notes (never shown to patients)" value={visit.clinical_note.private_doctor_notes ?? ""} onChange={(e) => setVisit({ ...visit, clinical_note: { ...visit.clinical_note, private_doctor_notes: e.target.value || null } })} /><textarea className={inputClass} required placeholder="Follow-up instructions" value={visit.clinical_note.follow_up_instructions} onChange={(e) => setVisit({ ...visit, clinical_note: { ...visit.clinical_note, follow_up_instructions: e.target.value } })} /><input className={inputClass} type="date" value={visit.clinical_note.recommended_follow_up_date ?? ""} onChange={(e) => setVisit({ ...visit, clinical_note: { ...visit.clinical_note, recommended_follow_up_date: e.target.value || null } })} /><input className={inputClass} placeholder="General prescription instructions" value={visit.prescription.general_instructions ?? ""} onChange={(e) => setVisit({ ...visit, prescription: { ...visit.prescription, general_instructions: e.target.value || null } })} />{visit.prescription.items.map((item, index) => <div className="grid gap-2 rounded-xl bg-slate-50 p-4 sm:grid-cols-2" key={index}><input className={inputClass} required placeholder="Medication" value={item.medication_name} onChange={(e) => updateMedication(index, { medication_name: e.target.value })} /><input className={inputClass} required placeholder="Dosage" value={item.dosage} onChange={(e) => updateMedication(index, { dosage: e.target.value })} /><input className={inputClass} placeholder="Route" value={item.route ?? ""} onChange={(e) => updateMedication(index, { route: e.target.value || null })} /><input className={inputClass} type="number" min="1" max="24" value={item.frequency_per_day} onChange={(e) => updateMedication(index, { frequency_per_day: Number(e.target.value) })} /><input className={inputClass} type="date" value={item.start_date} onChange={(e) => updateMedication(index, { start_date: e.target.value })} /><input className={inputClass} placeholder="Reminder times, comma separated" value={item.reminder_times.join(", ")} onChange={(e) => updateMedication(index, { reminder_times: e.target.value.split(",").map((value) => value.trim()).filter(Boolean) })} /><button className="text-left text-sm text-red-600" type="button" onClick={() => setVisit({ ...visit, prescription: { ...visit.prescription, items: visit.prescription.items.filter((_, itemIndex) => itemIndex !== index) } })}>Remove medication</button></div>)}<button className="text-sm font-semibold text-care-700" type="button" onClick={addMedication}>+ Add medication</button><button className={`${buttonClass} block`} disabled={busy || selected.status === "cancelled"} type="submit">{selected.status === "completed" ? "Save clinical record" : "Complete visit"}</button></form>
  {postVisit && <article className="rounded-2xl border border-indigo-200 bg-white p-6"><div className="flex justify-between gap-3"><h2 className="text-xl font-semibold">Post-visit summary review</h2><StatusBadge status={postVisit.review_status} /></div><p className="mt-2 text-xs text-slate-500">{postVisit.generation_source === "deterministic_fallback" ? "Deterministic fallback · still fully reviewable" : "AI-generated · approval required"}</p><textarea className={`${inputClass} mt-4`} value={approvedEdit} onChange={(e) => setApprovedEdit(e.target.value)} /><h3 className="mt-4 font-medium">Medication schedule (locked to prescription)</h3>{postVisit.medication_schedule?.map((item, index) => <pre className="mt-2 overflow-auto rounded-lg bg-slate-50 p-3 text-xs" key={index}>{JSON.stringify(item, null, 2)}</pre>)}<h3 className="mt-4 font-medium">Follow-up</h3><ul className="list-disc pl-5 text-sm">{postVisit.follow_up_steps?.map((step) => <li key={step}>{step}</li>)}</ul>{postVisit.safety_disclaimer && <p className="mt-4 text-xs text-slate-500">{postVisit.safety_disclaimer}</p>}{postVisit.failure_message && <p className="mt-3 text-sm text-amber-700">Generation status: {postVisit.failure_message}</p>}<div className="mt-5 flex flex-wrap gap-3"><button className={buttonClass} type="button" onClick={() => review("approve")}>Approve edited version</button><button className="rounded-lg border px-4 py-2 text-sm" type="button" onClick={() => review("reject")}>Reject</button><button className="rounded-lg border px-4 py-2 text-sm" type="button" disabled={busy || regenerating !== null} onClick={() => regenerate("post")}>{regenerating === "post" ? "Generating…" : "Regenerate"}</button></div></article>}</>}</section>;
}

function AppointmentList({ title, items, onSelect }: { title: string; items: AppointmentListItem[]; onSelect: (id: string) => void }) {
  return <article className="rounded-2xl border bg-white p-6"><h2 className="text-xl font-semibold">{title}</h2><div className="mt-4 space-y-2">{items.map((item) => <button className="flex w-full items-center justify-between rounded-lg bg-slate-50 p-3 text-left text-sm hover:bg-care-50" key={item.id} onClick={() => onSelect(item.id)}><span><span className="block font-medium">{item.patient_name}</span><span className="text-slate-500">{new Date(item.slot_start).toLocaleTimeString()}</span></span><StatusBadge status={item.status} /></button>)}{!items.length && <p className="text-sm text-slate-500">No appointments.</p>}</div></article>;
}
