type ConnectionBadgeProps = {
  connected: boolean;
  checking: boolean;
};

export function ConnectionBadge({ connected, checking }: ConnectionBadgeProps) {
  const label = checking ? "Checking" : connected ? "Connected" : "Disconnected";
  const tone = checking
    ? "bg-amber-100 text-amber-700"
    : connected
      ? "bg-emerald-100 text-emerald-700"
      : "bg-rose-100 text-rose-700";

  return (
    <div className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${tone}`}>
      <span className="h-2 w-2 rounded-full bg-current" />
      {label}
    </div>
  );
}
