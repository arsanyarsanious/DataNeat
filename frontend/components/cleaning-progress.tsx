export function CleaningProgress({ label }: { label: string }) {
  return <div className="cleaning-progress" role="status" aria-live="polite">
    <span>{label}</span>
    <div className="cleaning-progress-track" role="progressbar" aria-label={label}><div /></div>
  </div>;
}
