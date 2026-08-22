import { useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import type { DoctorPublic, SlotPreview } from "../types/doctor";

const inputClass = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";

export function PatientDashboardPage() {
  const { user, accessToken } = useAuth();
  const [doctors, setDoctors] = useState<DoctorPublic[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<DoctorPublic | null>(null);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [preview, setPreview] = useState<SlotPreview | null>(null);
  const [error, setError] = useState("");

  const load = async (requestedPage = page, term = search) => {
    if (!accessToken) return;
    try {
      setError("");
      const result = await api.publicDoctors(accessToken, term, requestedPage);
      setDoctors(result.items);
      setTotal(result.total);
      setPage(result.page);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load doctors.");
    }
  };

  useEffect(() => { load(1, ""); }, [accessToken]);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setSelected(null);
    setPreview(null);
    load(1, search);
  };

  const showSlots = async () => {
    if (!accessToken || !selected) return;
    try {
      setError("");
      setPreview(await api.previewSlots(accessToken, selected.id, date));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not generate slots.");
    }
  };

  return (
    <section>
      <p className="text-sm font-semibold uppercase tracking-wider text-care-600">Patient workspace</p>
      <h1 className="mt-1 text-3xl font-bold">Hello, {user?.full_name}</h1>
      <p className="mt-2 text-slate-600">Find an active doctor and preview their working slots.</p>
      {error && <p className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}

      <form className="mt-7 flex max-w-xl gap-2" onSubmit={submitSearch}>
        <input className={`${inputClass} min-w-0 flex-1`} placeholder="Search specialisation, e.g. cardio" value={search} onChange={(e) => setSearch(e.target.value)} />
        <button className="rounded-lg bg-care-600 px-4 py-2 text-sm font-semibold text-white" type="submit">Search</button>
      </form>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div>
          <p className="mb-3 text-sm text-slate-500">{total} doctor{total === 1 ? "" : "s"} found</p>
          <div className="space-y-3">{doctors.map((doctor) => <button className={`w-full rounded-2xl border bg-white p-5 text-left shadow-sm ${selected?.id === doctor.id ? "border-care-500" : "border-slate-200"}`} key={doctor.id} type="button" onClick={() => { setSelected(doctor); setPreview(null); }}><span className="block text-lg font-semibold">{doctor.full_name}</span><span className="mt-1 block text-care-700">{doctor.specialisation}</span><span className="mt-2 block text-sm text-slate-500">{doctor.qualifications || "Qualifications not listed"}</span></button>)}</div>
          <div className="mt-4 flex gap-2"><button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={page <= 1} onClick={() => load(page - 1)} type="button">Previous</button><button className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40" disabled={page * 10 >= total} onClick={() => load(page + 1)} type="button">Next</button></div>
        </div>

        {selected ? <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-2xl font-semibold">{selected.full_name}</h2><p className="mt-1 font-medium text-care-700">{selected.specialisation}</p><p className="mt-4 leading-7 text-slate-600">{selected.biography || "No biography provided."}</p><dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-slate-500">Consultation</dt><dd className="capitalize">{selected.consultation_mode.replace("_", " ")}</dd></div><div><dt className="text-slate-500">Location</dt><dd>{selected.location ?? "Online"}</dd></div><div><dt className="text-slate-500">Slot duration</dt><dd>{selected.slot_duration_minutes} minutes</dd></div><div><dt className="text-slate-500">Timezone</dt><dd>{selected.timezone}</dd></div></dl><div className="mt-6 flex flex-wrap gap-2"><input className={inputClass} type="date" value={date} onChange={(e) => { setDate(e.target.value); setPreview(null); }} /><button className="rounded-lg bg-care-600 px-4 py-2 text-sm font-semibold text-white" type="button" onClick={showSlots}>Preview slots</button></div>{preview && <div className="mt-6"><p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">{preview.disclaimer}</p><div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">{preview.slots.map((slot) => <div className="rounded-lg border border-care-100 bg-care-50 p-2 text-center text-sm text-care-900" key={slot.start}>{new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit", timeZone: preview.timezone }).format(new Date(slot.start))}</div>)}</div>{!preview.slots.length && <p className="mt-3 text-sm text-slate-500">No slots: {preview.availability.replaceAll("_", " ")}.</p>}</div>}</div> : <div className="rounded-2xl border border-dashed border-slate-300 p-10 text-center text-slate-500">Select a doctor to see their public profile.</div>}
      </div>
    </section>
  );
}

