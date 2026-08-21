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
    <div className="mx-auto max-w-md px-5 py-14">
      <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm sm:p-9">
        <h1 className="text-3xl font-bold tracking-tight">Create your account</h1>
        <p className="mt-2 text-slate-600">Public registration creates a patient account.</p>
        {error && <p className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}
        <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          <FormField id="full-name" label="Full name" value={fullName} autoComplete="name" placeholder="Alex Patient" onChange={setFullName} />
          <FormField id="email" label="Email address" type="email" value={email} autoComplete="email" placeholder="you@example.com" onChange={setEmail} />
          <FormField id="password" label="Password" type="password" value={password} autoComplete="new-password" onChange={setPassword} />
          <p className="text-xs leading-5 text-slate-500">Use at least 10 characters with an uppercase letter, lowercase letter, and number.</p>
          <button className="w-full rounded-xl bg-care-600 px-4 py-3 font-semibold text-white hover:bg-care-700 disabled:cursor-not-allowed disabled:opacity-60" type="submit" disabled={isSubmitting}>
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

