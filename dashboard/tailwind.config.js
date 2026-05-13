/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
        display: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
      },
      letterSpacing: {
        micro: "0.16em",
        label: "0.14em",
      },
      backgroundImage: {
        "card-glow":
          "radial-gradient(ellipse 600px 200px at 0% 0%, rgba(99, 102, 241, 0.08), transparent 60%)",
        "card-glow-warm":
          "radial-gradient(ellipse 600px 200px at 100% 0%, rgba(16, 185, 129, 0.08), transparent 60%)",
      },
      boxShadow: {
        glass:
          "0 1px 0 0 rgba(255, 255, 255, 0.04) inset, 0 20px 50px -20px rgba(0, 0, 0, 0.6)",
        glassHover:
          "0 1px 0 0 rgba(255, 255, 255, 0.08) inset, 0 30px 60px -20px rgba(0, 0, 0, 0.7)",
        glow: "0 0 20px -2px rgba(99, 102, 241, 0.4)",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "tooltip-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.6", transform: "scale(0.92)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(1)", opacity: "0.7" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
      },
      animation: {
        shimmer: "shimmer 1.8s ease-in-out infinite",
        "tooltip-in": "tooltip-in 140ms cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-up": "fade-up 320ms cubic-bezier(0.16, 1, 0.3, 1) both",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        "pulse-ring": "pulse-ring 2s ease-out infinite",
      },
    },
  },
  plugins: [],
};
