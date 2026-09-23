/* The mark reads as a document spine with an evidence marker — the product in
   one glyph. Ochre dot is the same token used for citations everywhere else. */

export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="2.5" width="18" height="19" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8.2 2.5v19" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M12 9.5h5M12 13h3.4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <circle cx="5.6" cy="17.4" r="1.5" fill="var(--ochre)" />
    </svg>
  );
}

export function Wordmark({ tone = "ink" }: { tone?: "ink" | "inverse" }) {
  return (
    <span
      className="row row-2"
      style={{ color: tone === "inverse" ? "var(--ink-inverse)" : "var(--ink)" }}
    >
      <Mark />
      <span
        className="display"
        style={{ fontSize: "17px", letterSpacing: "-0.01em", fontWeight: 500 }}
      >
        StudentOS
      </span>
    </span>
  );
}
