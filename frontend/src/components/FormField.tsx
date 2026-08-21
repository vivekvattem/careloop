interface FormFieldProps {
  id: string;
  label: string;
  type?: string;
  value: string;
  autoComplete?: string;
  placeholder?: string;
  onChange: (value: string) => void;
}

export function FormField({
  id,
  label,
  type = "text",
  value,
  autoComplete,
  placeholder,
  onChange,
}: FormFieldProps) {
  return (
    <label className="block" htmlFor={id}>
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <input
        className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400"
        id={id}
        name={id}
        type={type}
        value={value}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

