import type { PropsWithChildren, ReactNode } from "react";

type PanelProps = PropsWithChildren<{
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}>;

export function Panel({ title, subtitle, actions, children }: PanelProps) {
  return (
    <section className="rounded-[2rem] border border-[color:var(--border)] bg-[linear-gradient(180deg,rgba(17,24,39,0.96)_0%,rgba(15,23,42,0.98)_100%)] p-5 shadow-panel backdrop-blur md:p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-ink md:text-lg">{title}</h2>
          {subtitle ? <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-400">{subtitle}</p> : null}
        </div>
        {actions}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}
