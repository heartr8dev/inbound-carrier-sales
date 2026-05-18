// useTweaks — localStorage-backed reducer for theme/density/accent.
// Applies data-theme + data-density to documentElement so descendant CSS
// selectors hit globally. Sets --brand custom property from accent.
import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";
export type Density = "comfortable" | "compact";
export type Accent = "sage" | "amber" | "rouge" | "plum";

export type Tweaks = {
  theme: Theme;
  density: Density;
  accent: Accent;
};

const DEFAULTS: Tweaks = {
  theme: "dark",
  density: "comfortable",
  accent: "sage",
};

const STORAGE_KEY = "acme-tweaks";

const ACCENT_TOKEN: Record<Accent, string> = {
  sage: "var(--accent-sage)",
  amber: "var(--accent-amber)",
  rouge: "var(--accent-rouge)",
  plum: "var(--accent-plum)",
};

function loadInitial(): Tweaks {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Tweaks>;
    return {
      theme: parsed.theme === "light" ? "light" : "dark",
      density: parsed.density === "compact" ? "compact" : "comfortable",
      accent:
        parsed.accent && parsed.accent in ACCENT_TOKEN
          ? (parsed.accent as Accent)
          : DEFAULTS.accent,
    };
  } catch {
    return DEFAULTS;
  }
}

export function useTweaks() {
  const [tweaks, setTweaks] = useState<Tweaks>(loadInitial);

  // Apply tweaks to <html> + persist
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", tweaks.theme);
    root.setAttribute("data-density", tweaks.density);
    root.style.setProperty("--brand", ACCENT_TOKEN[tweaks.accent]);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tweaks));
    } catch {
      /* ignore quota */
    }
  }, [tweaks]);

  const setTweak = useCallback(
    <K extends keyof Tweaks>(key: K, value: Tweaks[K]) => {
      setTweaks((t) => ({ ...t, [key]: value }));
    },
    [],
  );

  return { tweaks, setTweak };
}
