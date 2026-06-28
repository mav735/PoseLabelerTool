export function EyeButton({ on, onToggle, title }: {
  on: boolean;
  onToggle: () => void;
  title?: string;
}) {
  const label = (title ? title + " — " : "") + (on ? "hide" : "show");
  return (
    <button type="button" className={"eye" + (on ? "" : " off")} aria-label={label} title={label}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
           strokeLinecap="round" strokeLinejoin="round">
        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z" />
        <circle cx="12" cy="12" r="3" />
        {!on && <path d="M3 3l18 18" />}
      </svg>
    </button>
  );
}
