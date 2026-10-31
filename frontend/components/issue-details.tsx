"use client";
import { useId, useState, type ReactNode } from "react";

export function IssueDetails({ children, label, onView }: { children: ReactNode; label: string; onView?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  return <div className="issue-details">
    <button type="button" className="issue-details-toggle" aria-label={`${expanded ? "Hide" : "Show"} details for ${label}`} aria-expanded={expanded} aria-controls={id} onClick={() => { if (!expanded) onView?.(); setExpanded(value => !value); }}>{expanded ? "Hide details" : "Show details"}<span aria-hidden="true">{expanded ? " −" : " +"}</span></button>
    <div id={id} hidden={!expanded} className="issue-details-content">{children}</div>
  </div>;
}
