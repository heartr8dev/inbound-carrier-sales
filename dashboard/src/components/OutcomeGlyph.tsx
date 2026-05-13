// Tiny inline SVG glyph per outcome. Each glyph plays a one-shot animation
// when it first scrolls into view (IntersectionObserver). After that, it
// stays static. Glyphs are 14px square, currentColor-driven, decorative.
//
// Visual recipe by outcome:
//   • booked              — check mark with a small burst ring on enter
//   • transferred_to_rep  — arrow that slides in from left
//   • no_matching_loads   — empty box with a question pulse
//   • carrier_declined_rate — minus + downward drop
//   • negotiation_stalled — circular dashed swirl
//   • carrier_failed_vetting — X with shake
//   • carrier_hung_up     — phone-handset that drops slightly
//
// Falls back to no animation for prefers-reduced-motion.
import { useEffect, useRef, useState } from "react";
import type { components } from "@/types/api";

type CallOutcome = components["schemas"]["CallOutcome"];

interface GlyphProps {
  outcome: CallOutcome;
  size?: number;
  color: string;
}

export function OutcomeGlyph({ outcome, size = 14, color }: GlyphProps) {
  const ref = useRef<SVGSVGElement | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (reduce) {
      setVisible(true);
      return;
    }
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setVisible(true);
            io.disconnect();
            break;
          }
        }
      },
      { threshold: 0.6 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const base = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: color,
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  // Each glyph defines its own internal SVG content + animation.
  return (
    <svg
      ref={ref}
      {...base}
      aria-hidden
      style={{ flexShrink: 0, color }}
      className="inline-block"
    >
      {outcome === "booked" && (
        <g>
          <polyline points="5 12 10 17 19 7">
            <animate
              attributeName="stroke-dasharray"
              from="0 30"
              to="30 0"
              dur="0.5s"
              begin={visible ? "0s" : "indefinite"}
              fill="freeze"
            />
          </polyline>
          {visible && (
            <circle
              cx="12"
              cy="12"
              r="8"
              stroke={color}
              strokeOpacity="0.5"
              strokeWidth="1.2"
              fill="none"
            >
              <animate
                attributeName="r"
                values="4;12"
                dur="0.6s"
                begin="0.15s"
                fill="freeze"
              />
              <animate
                attributeName="stroke-opacity"
                values="0.6;0"
                dur="0.6s"
                begin="0.15s"
                fill="freeze"
              />
            </circle>
          )}
        </g>
      )}
      {outcome === "transferred_to_rep" && (
        <g>
          <line x1="5" y1="12" x2="19" y2="12">
            <animate
              attributeName="x1"
              from="19"
              to="5"
              dur="0.4s"
              begin={visible ? "0s" : "indefinite"}
              fill="freeze"
            />
          </line>
          <polyline points="13 6 19 12 13 18" />
        </g>
      )}
      {outcome === "no_matching_loads" && (
        <g>
          <rect x="4" y="4" width="16" height="16" rx="3" />
          <line x1="9" y1="9" x2="15" y2="15" strokeOpacity="0.55" />
          <line x1="15" y1="9" x2="9" y2="15" strokeOpacity="0.55" />
        </g>
      )}
      {outcome === "carrier_declined_rate" && (
        <g>
          <circle cx="12" cy="12" r="8" />
          <line x1="8" y1="12" x2="16" y2="12">
            <animate
              attributeName="stroke-dasharray"
              from="0 16"
              to="16 0"
              dur="0.4s"
              begin={visible ? "0s" : "indefinite"}
              fill="freeze"
            />
          </line>
        </g>
      )}
      {outcome === "negotiation_stalled" && (
        <g>
          <circle
            cx="12"
            cy="12"
            r="8"
            strokeDasharray="3 3"
            transform={`rotate(0 12 12)`}
          >
            {visible && (
              <animateTransform
                attributeName="transform"
                type="rotate"
                from="0 12 12"
                to="180 12 12"
                dur="1.6s"
                fill="freeze"
              />
            )}
          </circle>
          <line x1="9" y1="12" x2="15" y2="12" />
        </g>
      )}
      {outcome === "carrier_failed_vetting" && (
        <g>
          <circle cx="12" cy="12" r="8" strokeOpacity="0.5" />
          <line x1="8" y1="8" x2="16" y2="16">
            <animate
              attributeName="stroke-dasharray"
              from="0 16"
              to="16 0"
              dur="0.3s"
              begin={visible ? "0s" : "indefinite"}
              fill="freeze"
            />
          </line>
          <line x1="16" y1="8" x2="8" y2="16">
            <animate
              attributeName="stroke-dasharray"
              from="0 16"
              to="16 0"
              dur="0.3s"
              begin={visible ? "0.1s" : "indefinite"}
              fill="freeze"
            />
          </line>
        </g>
      )}
      {outcome === "carrier_hung_up" && (
        <g transform="translate(0,0)">
          <path
            d="M5.5 12.5l3 -3a1 1 0 0 1 1.4 0l1.6 1.6a1 1 0 0 0 1.4 0l3 -3a1 1 0 0 1 1.4 0l1.6 1.6a1 1 0 0 1 0 1.4l-1.6 1.6"
            transform={visible ? "rotate(135 12 12)" : "rotate(0 12 12)"}
            style={{ transition: "transform 0.5s cubic-bezier(0.16,1,0.3,1)" }}
          />
        </g>
      )}
    </svg>
  );
}
