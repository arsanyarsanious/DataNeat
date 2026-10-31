"use client";
import { useState } from "react";

export type ColumnChoice = { value: string; label: string; detail?: string };
export function ColumnNavigator({ columns, value, onChange }: {
  columns: ColumnChoice[]; value: string; onChange: (value: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = columns.filter(c => c.label.toLocaleLowerCase().includes(query.toLocaleLowerCase().trim()));
  const selected = columns.find(c => c.value === value);
  const index = columns.findIndex(c => c.value === value);
  return <div className="column-navigator">
    <label>Find a column<input type="search" aria-label="Search columns" placeholder="Search column names…" value={query} onChange={e => setQuery(e.target.value)} /></label>
    <label>Selected column<select aria-label="Select column" value={value} onChange={e => onChange(e.target.value)}>
      {selected && !filtered.some(c => c.value === value) && <option value={selected.value}>{selected.label} · current</option>}
      {filtered.map(c => <option key={c.value} value={c.value}>{c.label}{c.detail ? ` · ${c.detail}` : ""}</option>)}
    </select></label>
    <div className="column-navigation-actions">
      <button className="button outline" disabled={index <= 0} aria-label="Previous column" onClick={() => onChange(columns[index - 1].value)}>Previous</button>
      <span>{index + 1} / {columns.length}</span>
      <button className="button outline" disabled={index < 0 || index >= columns.length - 1} aria-label="Next column" onClick={() => onChange(columns[index + 1].value)}>Next</button>
    </div>
    {!filtered.length && <p role="status">No columns match “{query}”. Try another name.</p>}
  </div>;
}
