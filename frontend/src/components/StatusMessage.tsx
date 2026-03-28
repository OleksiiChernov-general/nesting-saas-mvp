type StatusMessageProps = {
  tone?: "neutral" | "success" | "warning" | "error";
  message: string;
};

const toneClassName: Record<NonNullable<StatusMessageProps["tone"]>, string> = {
  neutral: "border border-[color:var(--border)] bg-black/15 text-slate-300",
  success: "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200",
  warning: "border border-amber-400/30 bg-amber-500/10 text-amber-200",
  error: "border border-rose-400/30 bg-rose-500/10 text-rose-200",
};

export function StatusMessage({ tone = "neutral", message }: StatusMessageProps) {
  return <div className={`rounded-2xl px-4 py-3 text-sm ${toneClassName[tone]}`}>{message}</div>;
}
