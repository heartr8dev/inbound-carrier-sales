// 4-dot polyline logo mark (ported from /tmp/acme-design/acme-dash/project/app.jsx).
// `currentColor` inherited from the parent — restyle via CSS color.
export function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 17 L9 8 L14 14 L21 5" />
      <circle cx="3" cy="17" r="1.5" fill="currentColor" />
      <circle cx="9" cy="8" r="1.5" fill="currentColor" />
      <circle cx="14" cy="14" r="1.5" fill="currentColor" />
      <circle cx="21" cy="5" r="1.5" fill="currentColor" />
    </svg>
  );
}
