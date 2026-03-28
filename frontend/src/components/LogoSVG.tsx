import { useId } from "react";

type LogoSVGProps = {
  className?: string;
  withWordmark?: boolean;
  iconClassName?: string;
  wordmarkClassName?: string;
};

export function LogoSVG({ className, withWordmark = true, iconClassName, wordmarkClassName }: LogoSVGProps) {
  const gradientId = useId();

  return (
    <div className={className}>
      <svg aria-hidden="true" className={iconClassName ?? "h-10 w-10 shrink-0"} viewBox="0 0 64 64">
        <defs>
          <linearGradient id={gradientId} x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="var(--brand-primary)" />
            <stop offset="100%" stopColor="var(--brand-accent)" />
          </linearGradient>
        </defs>
        <rect fill="rgba(255,255,255,0.04)" height="56" rx="18" width="56" x="4" y="4" />
        <path
          d="M18 46V18h9l19 20V18h8v28h-9L26 26v20z"
          fill={`url(#${gradientId})`}
        />
        <circle cx="48" cy="18" fill="var(--brand-accent)" r="4" />
      </svg>
      {withWordmark ? (
        <div className={wordmarkClassName ?? "min-w-0"}>
          <div className="text-lg font-semibold tracking-[0.08em] text-white">NESTORA</div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Smart Nesting</div>
        </div>
      ) : null}
    </div>
  );
}
