export function LoadingScreen() {
  return (
    <div className="grid min-h-screen place-items-center bg-care-50" role="status">
      <div className="text-center">
        <div className="mx-auto mb-4 h-9 w-9 animate-spin rounded-full border-4 border-care-100 border-t-care-600" />
        <p className="text-sm font-medium text-care-900">Loading CareLoop…</p>
      </div>
    </div>
  );
}

