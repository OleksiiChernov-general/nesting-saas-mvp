import type { ReactNode } from "react";

type FieldProps = {
  label: string;
  error?: string;
  children: ReactNode;
};

export function Field({ label, error, children }: FieldProps) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-medium text-slate-300">{label}</span>
      {children}
      {error ? <span className="block text-xs text-rose-300">{error}</span> : null}
    </label>
  );
}
