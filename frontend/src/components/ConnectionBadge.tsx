type ConnectionBadgeProps = {
  connected: boolean;
  checking: boolean;
};

export function ConnectionBadge({ connected, checking }: ConnectionBadgeProps) {
  const label = checking ? "Checking" : connected ? "Connected" : "Disconnected";
  const tone = checking
    ? "border border-amber-400/30 bg-amber-500/10 text-amber-200"
    : connected
      ? "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
      : "border border-rose-400/30 bg-rose-500/10 text-rose-200";

  return (
    <div className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${tone}`}>
      <span className="h-2 w-2 rounded-full bg-current" />
      {label}
    </div>
  );
}
