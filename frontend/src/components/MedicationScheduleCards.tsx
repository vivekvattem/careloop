export type MedicationScheduleItem = {
  medication_name?: unknown;
  dosage?: unknown;
  route?: unknown;
  frequency_per_day?: unknown;
  start_date?: unknown;
  end_date?: unknown;
  reminder_times?: unknown;
  food_instructions?: unknown;
  additional_instructions?: unknown;
};

export function MedicationScheduleCards({ items }: { items: MedicationScheduleItem[] }) {
  if (!items.length) return <p className="mt-2 text-sm text-slate-500">No active medication prescribed.</p>;
  return <div className="mt-2 grid gap-3 md:grid-cols-2">{items.map((item, index) => {
    const reminders = Array.isArray(item.reminder_times) ? item.reminder_times.filter((value): value is string => typeof value === "string") : [];
    return <article className="rounded-lg bg-slate-50 p-4 text-sm" key={`${String(item.medication_name)}-${index}`}><h4 className="font-semibold">{String(item.medication_name ?? "Medication")}</h4><dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2"><Detail label="Dosage" value={item.dosage} /><Detail label="Route" value={item.route} fallback="Not specified" /><Detail label="Frequency" value={typeof item.frequency_per_day === "number" ? `${item.frequency_per_day} time(s) per day` : item.frequency_per_day} /><Detail label="Start date" value={item.start_date} /><Detail label="End date" value={item.end_date} fallback="No end date specified" /><Detail label="Reminder times" value={reminders.length ? reminders.join(", ") : undefined} fallback="No reminders specified" /><Detail label="Food instructions" value={item.food_instructions} fallback="None" /><Detail label="Additional instructions" value={item.additional_instructions} fallback="None" /></dl></article>;
  })}</div>;
}

function Detail({ label, value, fallback = "Not specified" }: { label: string; value: unknown; fallback?: string }) {
  const display = typeof value === "string" && value.trim() ? value : typeof value === "number" ? String(value) : fallback;
  return <div><dt className="text-xs font-medium text-slate-500">{label}</dt><dd>{display}</dd></div>;
}
