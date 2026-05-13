// Shimmer skeleton primitives used while metrics are in flight.
//
// `Skeleton` is a generic shimmer block; `ChartSkeleton` composes a few of
// them to suggest the actual chart's geometry (mini bars + axis line) instead
// of a featureless rectangle.
import clsx from "clsx";
import { InboxIcon } from "@/components/icons";

export function Spinner({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={clsx(
        "h-5 w-5 animate-spin rounded-full border-2 border-white/10 border-t-white/60",
        className,
      )}
    />
  );
}

export function Skeleton({
  className,
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      aria-hidden
      className={clsx("shimmer-bg animate-shimmer rounded-md", className)}
      style={style}
    />
  );
}

/**
 * Chart-shaped skeleton: a row of ascending mini-bars with an axis baseline.
 * Reads more like “a chart is loading” than the previous spinner-in-a-box.
 */
export function ChartSkeleton({ height = 240 }: { height?: number }) {
  return (
    <div
      role="status"
      aria-label="Loading chart"
      className="relative w-full overflow-hidden rounded-xl border border-white/[0.04] bg-white/[0.02] px-4 py-4"
      style={{ height }}
    >
      <div className="mb-3 flex justify-between">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 w-16" />
      </div>
      <div
        className="flex items-end gap-1.5"
        style={{ height: height - 60 }}
      >
        {Array.from({ length: 14 }).map((_, i) => {
          const h = 30 + ((i * 17) % 70);
          return (
            <Skeleton
              key={i}
              className="flex-1 rounded-md"
              style={{ height: `${h}%` }}
            />
          );
        })}
      </div>
      <div className="mt-3 flex gap-2">
        <Skeleton className="h-2 w-12" />
        <Skeleton className="h-2 w-12" />
        <Skeleton className="h-2 w-12" />
      </div>
    </div>
  );
}

export function EmptyState({
  title = "No data yet",
  description,
  icon,
}: {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center px-6 text-center">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.06] bg-white/[0.02] text-slate-500">
        {icon ?? <InboxIcon size={18} />}
      </div>
      <p className="text-sm font-medium text-slate-200">{title}</p>
      {description && (
        <p className="mt-1 max-w-[260px] text-xs leading-relaxed text-slate-500">
          {description}
        </p>
      )}
    </div>
  );
}
