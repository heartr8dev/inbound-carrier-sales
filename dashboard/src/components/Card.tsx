// Glass-surface card shell used for every panel.
//
// Composition:
//   • `.glass-surface` provides the frosted background, hairline border, and
//     inset-highlight + drop-shadow.
//   • A positioned radial-gradient ::before sits in the top-left corner of
//     each card to add depth — implemented as an absolute child so we can
//     control opacity per-card via the `tone` prop.
//   • Header row uses a subtle bottom border (white at 4% opacity).
//   • Cards lift slightly on hover (-translate-y-0.5) for tactility.
import clsx from "clsx";
import type { ReactNode } from "react";

type CardTone = "default" | "warm" | "cool" | "muted";

interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: CardTone;
  children: ReactNode;
}

const toneGlows: Record<CardTone, string> = {
  default:
    "before:bg-[radial-gradient(ellipse_500px_240px_at_0%_0%,rgba(99,102,241,0.10),transparent_60%)]",
  warm: "before:bg-[radial-gradient(ellipse_500px_240px_at_0%_0%,rgba(16,185,129,0.10),transparent_60%)]",
  cool: "before:bg-[radial-gradient(ellipse_500px_240px_at_0%_0%,rgba(6,182,212,0.10),transparent_60%)]",
  muted:
    "before:bg-[radial-gradient(ellipse_500px_240px_at_0%_0%,rgba(148,163,184,0.06),transparent_60%)]",
};

export function Card({
  title,
  subtitle,
  action,
  className,
  bodyClassName,
  tone = "default",
  children,
}: CardProps) {
  return (
    <section
      className={clsx(
        "group/card relative overflow-hidden rounded-2xl",
        "glass-surface hover:-translate-y-0.5",
        // Radial corner-glow overlay
        "before:pointer-events-none before:absolute before:inset-0 before:rounded-2xl",
        toneGlows[tone],
        className,
      )}
    >
      <div className="relative z-10">
        {(title || subtitle || action) && (
          <header className="flex items-start justify-between gap-4 border-b border-white/[0.05] px-6 py-4">
            <div className="min-w-0">
              {title && (
                <h2 className="text-sm font-semibold tracking-tight text-slate-100">
                  {title}
                </h2>
              )}
              {subtitle && (
                <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
              )}
            </div>
            {action && <div className="flex shrink-0 items-center">{action}</div>}
          </header>
        )}
        <div className={clsx("p-6", bodyClassName)}>{children}</div>
      </div>
    </section>
  );
}
