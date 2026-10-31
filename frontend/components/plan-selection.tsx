"use client";
import { useEffect, useRef } from "react";
import type { Operation } from "@/lib/types";
import { Button } from "./ui/button";
export function PlanSelection({
  operations,
  reviewedIds,
  disabled,
  onSelect,
}: {
  operations: Operation[];
  reviewedIds: Set<string>;
  disabled: boolean;
  onSelect: (enabled: boolean) => void;
}) {
  const eligible = operations.filter(o => reviewedIds.has(o.id));
  const selected = operations.filter((o) => o.enabled).length,
    ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current)
      ref.current.indeterminate = selected > 0 && selected < eligible.length;
  }, [selected, eligible.length]);
  const destructive = eligible.filter(
    (o) => o.safety === "destructive",
  ).length;
  return (
    <div className="plan-selection">
      <div className="plan-selection-controls">
        <label>
          <input
            ref={ref}
            type="checkbox"
            aria-label="Select all reviewed cleaning actions"
            checked={eligible.length > 0 && eligible.every(o => o.enabled)}
            disabled={disabled || eligible.length === 0}
            onChange={(e) => onSelect(e.target.checked)}
          />
          Select all reviewed
        </label>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || selected === 0}
          onClick={() => onSelect(false)}
        >
          Deselect all
        </Button>
        <span>
          {selected} / {operations.length} selected
        </span>
      </div>
      <p>
        Open Show details before selecting an action. Select all reviewed enables only the {eligible.length} actions whose details you have viewed
        {destructive
          ? `, including ${destructive} action${destructive === 1 ? "" : "s"} that ${destructive === 1 ? "removes" : "remove"} rows`
          : ""}
        . Review their settings before applying. Currency and percentage
        interpretations still require your choice.
      </p>
    </div>
  );
}
