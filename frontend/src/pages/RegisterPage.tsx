import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError, api } from "../api/client";
import { FormField } from "../components/FormField";
import { useAuth } from "../contexts/AuthContext";
import { dashboardPath } from "../routes/ProtectedRoute";

export function RegisterPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (user) return <Navigate to={dashboardPath(user.role)} replace />;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await api.register({ full_name: fullName, email, password });
      navigate("/login", {
        replace: true,
        state: { notice: "Your patient account is ready. You can sign in now." },
      });
    } catch (caughtError) {
      setError(caughtError instanceof ApiError ? caughtError.message : "Unable to create your account right now.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 sm:px-8 lg:grid-cols-[.85fr_1.15fr] lg:items-stretch lg:py-20">
      <aside className="hidden rounded-4xl bg-gradient-to-br from-care-900 to-ink p-10 text-white lg:flex lg:flex-col"><p className="text-sm font-semibold uppercase tracking-wider text-care-100">For patients</p><h1 className="mt-4 text-4xl font-bold tracking-tight text-white">A clearer way to keep care moving.</h1><p className="mt-5 text-base leading-7 text-slate-200">Create your account to find a doctor, prepare for visits, and access approved follow-up information.</p><p className="mt-auto text-sm leading-6 text-care-100">Public registration is patient-only. Clinicians and administrators receive managed accounts.</p></aside>
      <div className="ui-card mx-auto w-full max-w-xl p-7 shadow-lift sm:p-10">
        <p className="text-sm font-semibold uppercase tracking-wider text-care-700">Patient account</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Create your account</h1>
        <p className="mt-2 text-slate-600">Public registration creates a patient account.</p>
        {error && <p className="ui-alert-error mt-5" role="alert">{error}</p>}
        <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          <FormField id="full-name" label="Full name" value={fullName} autoComplete="name" placeholder="Alex Patient" onChange={setFullName} />
          <FormField id="email" label="Email address" type="email" value={email} autoComplete="email" placeholder="you@example.com" onChange={setEmail} />
          <FormField id="password" label="Password" type="password" value={password} autoComplete="new-password" onChange={setPassword} />
          <p className="text-xs leading-5 text-slate-500">Use at least 10 characters with an uppercase letter, lowercase letter, and number.</p>
          <button className="ui-button-primary w-full py-3" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating account…" : "Create patient account"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-600">
          Already registered? <Link className="font-semibold text-care-700 hover:underline" to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
