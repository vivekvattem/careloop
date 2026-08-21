import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { FormField } from "../components/FormField";
import { useAuth } from "../contexts/AuthContext";
import { dashboardPath } from "../routes/ProtectedRoute";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const notice = (location.state as { notice?: string } | null)?.notice;

  if (user) return <Navigate to={dashboardPath(user.role)} replace />;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const loggedInUser = await login({ email, password });
      navigate(dashboardPath(loggedInUser.role), { replace: true });
    } catch (caughtError) {
      setError(caughtError instanceof ApiError ? caughtError.message : "Unable to sign in right now.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-md px-5 py-16">
      <div className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm sm:p-9">
        <h1 className="text-3xl font-bold tracking-tight">Welcome back</h1>
        <p className="mt-2 text-slate-600">Sign in to your CareLoop workspace.</p>
        {notice && <p className="mt-5 rounded-xl bg-care-50 p-3 text-sm text-care-700">{notice}</p>}
        {error && <p className="mt-5 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}
        <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          <FormField id="email" label="Email address" type="email" value={email} autoComplete="email" placeholder="you@example.com" onChange={setEmail} />
          <FormField id="password" label="Password" type="password" value={password} autoComplete="current-password" onChange={setPassword} />
          <button className="w-full rounded-xl bg-care-600 px-4 py-3 font-semibold text-white hover:bg-care-700 disabled:cursor-not-allowed disabled:opacity-60" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-600">
          New to CareLoop? <Link className="font-semibold text-care-700 hover:underline" to="/register">Create a patient account</Link>
        </p>
      </div>
    </div>
  );
}

