type StatusMessageProps = {
  tone?: "neutral" | "success" | "warning" | "error";
  message: string;
};

const toneClassName: Record<NonNullable<StatusMessageProps["tone"]>, string> = {
  neutral: "bg-slate-100 text-slate-700",
  success: "bg-emerald-50 text-emerald-700",
  warning: "bg-amber-50 text-amber-700",
  error: "bg-rose-50 text-rose-700",
};

export function StatusMessage({ tone = "neutral", message }: StatusMessageProps) {
  return <div className={`rounded-2xl px-4 py-3 text-sm ${toneClassName[tone]}`}>{message}</div>;
}
