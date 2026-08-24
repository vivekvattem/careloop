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
    <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 sm:px-8 lg:grid-cols-[.85fr_1.15fr] lg:items-stretch lg:py-20">
      <aside className="hidden rounded-4xl bg-ink p-10 text-white lg:flex lg:flex-col"><p className="text-sm font-semibold uppercase tracking-wider text-care-100">CareLoop</p><h1 className="mt-4 text-4xl font-bold tracking-tight text-white">Care that stays in sync.</h1><p className="mt-5 text-base leading-7 text-slate-300">Sign in to manage the next step in your care journey or clinical workspace.</p><div className="mt-auto rounded-2xl bg-white/10 p-5 text-sm leading-6 text-slate-200">Your workspace is tailored to your role and keeps the actions that matter within reach.</div></aside>
      <div className="ui-card mx-auto w-full max-w-xl p-7 shadow-lift sm:p-10">
        <p className="text-sm font-semibold uppercase tracking-wider text-care-700">Secure sign in</p><h1 className="mt-2 text-3xl font-bold tracking-tight">Welcome back</h1>
        <p className="mt-2 text-slate-600">Sign in to your CareLoop workspace.</p>
        {notice && <p className="ui-alert-success mt-5">{notice}</p>}
        {error && <p className="ui-alert-error mt-5" role="alert">{error}</p>}
        <form className="mt-7 space-y-5" onSubmit={handleSubmit}>
          <FormField id="email" label="Email address" type="email" value={email} autoComplete="email" placeholder="you@example.com" onChange={setEmail} />
          <div><FormField id="password" label="Password" type="password" value={password} autoComplete="current-password" onChange={setPassword} /><Link className="mt-2 inline-block text-sm font-semibold text-care-700 hover:underline" to="/forgot-password">Forgot password?</Link></div>
          <button className="ui-button-primary w-full py-3" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-600">
          New to CareLoop? <Link className="font-semibold text-care-700 hover:underline" to="/register">Create a patient account</Link>
        </p>
        <p className="mt-4 text-center text-sm"><Link className="text-care-700 hover:underline" to="/">Return to home</Link></p>
      </div>
    </div>
  );
}
