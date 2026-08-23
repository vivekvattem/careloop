import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl px-5 py-24 text-center">
      <div className="ui-card p-10 shadow-lift"><p className="font-semibold text-care-600">404</p>
      <h1 className="mt-2 text-4xl font-bold tracking-tight">This page is out of the loop</h1>
      <p className="mt-4 text-slate-600">The page you requested does not exist.</p>
      <Link className="ui-button-primary mt-8 px-5 py-3" to="/">
        Return home
      </Link>
      </div>
    </div>
  );
}
