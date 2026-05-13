// requestAnimationFrame-driven number animation for the KPI hero values.
//
// Returns a number that eases from the previous value to `target` over
// `durationMs`, using an easeOutExpo curve. Restarts on every target change.
// Skips the animation entirely if the user prefers reduced motion.
import { useEffect, useRef, useState } from "react";

function easeOutExpo(t: number): number {
  return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function useCountUp(target: number, durationMs = 700): number {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);
  const startRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const prevTargetRef = useRef(target);

  useEffect(() => {
    if (target === prevTargetRef.current) return;
    if (prefersReducedMotion() || !Number.isFinite(target)) {
      setValue(target);
      prevTargetRef.current = target;
      return;
    }
    fromRef.current = prevTargetRef.current;
    prevTargetRef.current = target;
    startRef.current = null;

    const tick = (ts: number) => {
      if (startRef.current == null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(1, elapsed / durationMs);
      const eased = easeOutExpo(progress);
      const next = fromRef.current + (target - fromRef.current) * eased;
      setValue(next);
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setValue(target);
        rafRef.current = null;
      }
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [target, durationMs]);

  return value;
}
