/** Three spreadsheet cells form DataNeat's compact check mark. */
export function DataNeatMark({ size = 36, className = "" }: { size?: number; className?: string }) {
  return <svg
    className={`dataneat-mark${className ? ` ${className}` : ""}`}
    width={size}
    height={size * 0.84}
    viewBox="0 0 100 84"
    fill="none"
    aria-hidden="true"
    focusable="false"
  >
    <rect className="dataneat-mark-cell" x="6.5" y="32.5" width="21" height="21" rx="3.5" transform="rotate(45 17 43)" />
    <rect className="dataneat-mark-arm" x="24" y="39" width="51" height="27" rx="4" transform="rotate(-45 49.5 52.5)" />
    <rect className="dataneat-mark-tip" x="66.5" y="8.5" width="23" height="23" rx="3.5" transform="rotate(45 78 20)" />
  </svg>;
}
