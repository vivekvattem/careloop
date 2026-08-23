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
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  return (
    <label className="block" htmlFor={id}>
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <div className="relative"><input
        className="ui-input pr-16"
        id={id}
        name={id}
        type={isPassword && showPassword ? "text" : type}
        value={value}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required
        onChange={(event) => onChange(event.target.value)}
      />{isPassword && <button className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg px-2 py-1 text-xs font-semibold text-care-700 hover:bg-care-50" type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? "Hide" : "Show"}</button>}</div>
    </label>
  );
}
import { useState } from "react";
