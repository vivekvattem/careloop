import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { FormField } from "../components/FormField";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState(""); const [submitted, setSubmitted] = useState(false); const [error, setError] = useState(""); const [pending, setPending] = useState(false);
  const submit = async (event: FormEvent) => { event.preventDefault(); setPending(true); setError(""); try { await api.forgotPassword(email); setSubmitted(true); } catch (caught) { setError(caught instanceof ApiError ? "Unable to submit that request right now." : "Unable to submit that request right now."); } finally { setPending(false); } };
  return <div className="mx-auto max-w-md px-5 py-14"><div className="ui-card p-7 shadow-lift sm:p-9"><Link className="text-sm font-semibold text-care-700 hover:underline" to="/login">← Return to sign in</Link><h1 className="mt-5 text-3xl font-bold">Reset your password</h1>{submitted ? <p className="ui-alert-success mt-5">If an active CareLoop account exists for that email, we’ve sent password-reset instructions.</p> : <><p className="mt-2 text-slate-600">Enter your email and we’ll send a one-time reset link if an active account exists.</p>{error && <p className="ui-alert-error mt-4" role="alert">{error}</p>}<form className="mt-6 space-y-5" onSubmit={submit}><FormField id="email" label="Email address" type="email" value={email} autoComplete="email" onChange={setEmail}/><button className="ui-button-primary w-full" disabled={pending}>{pending ? "Sending…" : "Send reset instructions"}</button></form></>}</div></div>;
}
