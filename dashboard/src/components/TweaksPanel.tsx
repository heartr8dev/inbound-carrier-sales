// Floating tweaks panel — theme / density / accent toggles.
// Opens via a fixed gear button bottom-right; persists via useTweaks.
import { useState } from "react";
import { useTweaks, type Theme, type Density, type Accent } from "@/hooks/useTweaks";

type Option<T extends string> = { label: string; value: T };

function TweakRadio<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="twk-row">
      <div className="twk-lbl">
        <span>{label}</span>
      </div>
      <div className="twk-seg" role="tablist" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            data-on={value === o.value}
            onClick={() => onChange(o.value)}
            className="twk-seg-btn"
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function TweakSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <div className="twk-sect">{label}</div>
      {children}
    </>
  );
}

export function TweaksPanel() {
  const { tweaks, setTweak } = useTweaks();
  const [open, setOpen] = useState(false);

  return (
    <>
      <style>{TWEAKS_STYLE}</style>
      <button
        type="button"
        className="twk-fab"
        aria-label="Toggle tweaks panel"
        aria-pressed={open}
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>
      {open && (
        <div className="twk-panel" role="dialog" aria-label="Tweaks">
          <div className="twk-hd">
            <b>Tweaks</b>
            <button className="twk-x" type="button" aria-label="Close tweaks" onClick={() => setOpen(false)}>
              ✕
            </button>
          </div>
          <div className="twk-body">
            <TweakSection label="Theme">
              <TweakRadio<Theme>
                label="Mode"
                options={[
                  { label: "Linen", value: "light" },
                  { label: "Obsidian", value: "dark" },
                ]}
                value={tweaks.theme}
                onChange={(v) => setTweak("theme", v)}
              />
              <TweakRadio<Density>
                label="Density"
                options={[
                  { label: "Comfortable", value: "comfortable" },
                  { label: "Compact", value: "compact" },
                ]}
                value={tweaks.density}
                onChange={(v) => setTweak("density", v)}
              />
            </TweakSection>
            <TweakSection label="Accent">
              <TweakRadio<Accent>
                label="Brand color"
                options={[
                  { label: "Sage", value: "sage" },
                  { label: "Amber", value: "amber" },
                  { label: "Rouge", value: "rouge" },
                  { label: "Plum", value: "plum" },
                ]}
                value={tweaks.accent}
                onChange={(v) => setTweak("accent", v)}
              />
            </TweakSection>
          </div>
        </div>
      )}
    </>
  );
}

const TWEAKS_STYLE = `
  .twk-fab {
    position: fixed; right: 16px; bottom: 16px; z-index: 2147483645;
    appearance: none; border: 0; cursor: pointer;
    width: 44px; height: 44px;
    border-radius: 50%;
    background: var(--surface-1);
    color: var(--fg-2);
    box-shadow: var(--neu-raised-sm);
    display: grid; place-items: center;
    transition: box-shadow var(--d-fast) var(--ease-soft), color var(--d-fast) var(--ease-soft);
  }
  .twk-fab:hover { color: var(--fg-1); }
  .twk-fab:active { box-shadow: var(--neu-pressed-sm); }
  .twk-fab[aria-pressed="true"] { color: var(--brand); box-shadow: var(--neu-pressed-sm); }

  .twk-panel {
    position: fixed; right: 16px; bottom: 72px; z-index: 2147483646;
    width: 280px;
    background: var(--surface-1);
    color: var(--fg-1);
    border-radius: var(--r-3);
    box-shadow: var(--neu-float);
    font-family: var(--font-sans);
    font-size: 12px;
    overflow: hidden;
    animation: twkIn var(--d-base) var(--ease-soft);
  }
  @keyframes twkIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

  .twk-hd {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 8px 10px 14px;
    border-bottom: var(--hairline);
  }
  .twk-hd b { font-size: 13px; font-weight: var(--w-semibold); letter-spacing: -0.005em; }
  .twk-x {
    appearance: none; border: 0; background: transparent; color: var(--fg-3);
    width: 24px; height: 24px; border-radius: 6px; cursor: pointer; font-size: 13px; line-height: 1;
  }
  .twk-x:hover { background: var(--surface-2); color: var(--fg-1); }

  .twk-body { padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 10px; }

  .twk-row { display: flex; flex-direction: column; gap: 6px; }
  .twk-lbl { display: flex; justify-content: space-between; align-items: baseline; color: var(--fg-3); font-size: 11px; font-weight: var(--w-medium); }

  .twk-sect {
    font-size: 10px; font-weight: var(--w-semibold); letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--fg-3); padding-top: 6px;
  }
  .twk-sect:first-child { padding-top: 0; }

  .twk-seg {
    display: inline-flex;
    background: var(--surface-2);
    border-radius: var(--r-pill);
    padding: 3px;
    box-shadow: var(--neu-inset);
  }
  .twk-seg-btn {
    appearance: none; border: 0; cursor: pointer; flex: 1;
    padding: 5px 10px;
    font-family: var(--font-sans);
    font-size: 11px;
    font-weight: var(--w-medium);
    color: var(--fg-3);
    background: transparent;
    border-radius: var(--r-pill);
    transition: color var(--d-fast) var(--ease-soft), box-shadow var(--d-fast) var(--ease-soft), background var(--d-fast) var(--ease-soft);
    white-space: nowrap;
  }
  .twk-seg-btn[data-on="true"] {
    background: var(--surface-1);
    color: var(--fg-1);
    box-shadow: var(--neu-raised-sm);
  }
  .twk-seg-btn:hover:not([data-on="true"]) { color: var(--fg-2); }
`;
