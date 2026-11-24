"use client";

import { useState } from "react";

type Distribution = {
  group: string[];
  count: number;
  observed_count: number;
  minimum: number;
  maximum: number;
  q1: number;
  median: number;
  q3: number;
  lower: number;
  upper: number;
  flagged_count: number;
  bins: { start: number; end: number; count: number; flagged: number }[];
  points: { row: number; value: number }[];
};

const shown = (value: number) => value.toLocaleString(undefined, { maximumSignificantDigits: 6 });

export function OutlierDistribution({ distributions, column, method }: {
  distributions: Distribution[];
  column: string;
  method: string;
}) {
  const [groupIndex, setGroupIndex] = useState(0);
  const [detail, setDetail] = useState("");
  const data = distributions[groupIndex] || distributions[0];
  if (!data) return null;
  const minimum = Math.min(data.bins[0].start, data.lower);
  const maximum = Math.max(data.bins[data.bins.length - 1].end, data.upper);
  // Scale before subtracting to keep very large finite measurements displayable.
  const scale = Math.max(Math.abs(minimum), Math.abs(maximum), 1);
  const span = maximum / scale - minimum / scale || 1;
  const x = (value: number) => 48 + ((value / scale - minimum / scale) / span) * 624;
  const peak = Math.max(...data.bins.map(bin => bin.count), 1);
  const green = "#38a96c";
  const orange = "#e98945";

  return <section className="quality-card" aria-label={`${column} distribution`}>
    <h3>{column} distribution</h3>
    {distributions.length > 1 && <label className="setting">Group to display
      <select value={groupIndex} onChange={event => { setGroupIndex(Number(event.target.value)); setDetail(""); }}>
        {distributions.map((group, index) => <option key={index} value={index}>{group.group.join(" / ") || "Entire column"}</option>)}
      </select>
    </label>}
    <p><strong>Median {shown(data.median)}</strong> · {data.count.toLocaleString()} values · {data.flagged_count.toLocaleString()} flagged</p>
    <div style={{ overflowX: "auto" }}>
      <svg viewBox="0 0 720 300" style={{ width: "100%", minWidth: 420, display: "block" }} role="img" aria-label={`Distribution of ${column}. Median ${shown(data.median)}. ${method.toUpperCase()} bounds ${shown(data.lower)} to ${shown(data.upper)}. ${data.flagged_count} unusual values.`}>
        <text x={48} y={18} fill="currentColor" fontSize={13}>Number of values (highest bar = {peak.toLocaleString()})</text>
        <rect x={x(data.lower)} y={30} width={Math.max(0, x(data.upper) - x(data.lower))} height={140} fill={green} opacity={0.09}/>
        {data.bins.map((bin, index) => {
          const height = bin.count / peak * 120;
          const flaggedHeight = bin.flagged / peak * 120;
          const label = `${shown(bin.start)} to ${shown(bin.end)}: ${bin.count} values, ${bin.flagged} flagged`;
          return <g key={index} tabIndex={0} onMouseEnter={() => setDetail(label)} onFocus={() => setDetail(label)} onClick={() => setDetail(label)} aria-label={label}>
            <title>{label}</title>
            <rect x={x(bin.start)} y={170 - height} width={Math.max(1, x(bin.end) - x(bin.start) - 1)} height={height} fill={green}/>
            <rect x={x(bin.start)} y={170 - height} width={Math.max(1, x(bin.end) - x(bin.start) - 1)} height={flaggedHeight} fill={orange}/>
          </g>;
        })}
        {[data.lower, data.upper].map((bound, index) => <line key={index} x1={x(bound)} x2={x(bound)} y1={30} y2={243} stroke={orange} strokeDasharray="5 4" strokeWidth={1.5}/>)}
        <line x1={x(data.median)} x2={x(data.median)} y1={30} y2={170} stroke="currentColor" strokeDasharray="3 3"/>
        <line x1={48} x2={672} y1={170} y2={170} stroke="currentColor" opacity={0.35}/>
        {[0, 1, 2, 3, 4].map(index => {
          const value = (minimum / scale * (1 - index / 4) + maximum / scale * index / 4) * scale;
          return <text key={index} x={48 + index * 156} y={192} textAnchor="middle" fill="currentColor" fontSize={12}>{shown(value)}</text>;
        })}
        <line x1={x(data.minimum)} x2={x(data.maximum)} y1={223} y2={223} stroke="currentColor" opacity={0.45}/>
        <rect x={x(data.q1)} y={210} width={Math.max(2, x(data.q3) - x(data.q1))} height={26} fill={green} opacity={0.55}/>
        <line x1={x(data.median)} x2={x(data.median)} y1={207} y2={239} stroke="currentColor" strokeWidth={3}/>
        {data.points.map((point, index) => {
          const label = `Row ${point.row}: ${shown(point.value)}; ${shown(Math.abs(point.value - data.median))} from the median`;
          return <circle key={point.row} cx={x(point.value)} cy={217 + (index % 3) * 6} r={5} fill={orange} stroke="var(--surface)" tabIndex={0} aria-label={label} onMouseEnter={() => setDetail(label)} onFocus={() => setDetail(label)} onClick={() => setDetail(label)}><title>{label}</title></circle>;
        })}
        <text x={48} y={267} fill="currentColor" fontSize={13}>Box = middle 50% · Centre line = median · Orange = flagged values</text>
        <text x={48} y={289} fill="currentColor" fontSize={13}>Dashed limits = {method.toUpperCase()} bounds · Thin line = full value range</text>
      </svg>
    </div>
    <p>Review bounds {shown(data.lower)} to {shown(data.upper)} · Middle 50% {shown(data.q1)} to {shown(data.q3)}</p>
    <p role="status" style={{ minHeight: "2.5em" }}>{detail || "Hover, tap or focus a bar or orange point to inspect its values."}</p>
    <p className="quality-muted">The histogram includes all {data.count.toLocaleString()} numeric values in this group. Median, quartiles and bounds use {data.observed_count.toLocaleString()} original observations. Previously estimated values are excluded from these calculations. {data.flagged_count > data.points.length && `Showing ${data.points.length} flagged points of ${data.flagged_count}; every flagged value is counted in the bars.`}</p>
  </section>;
}
