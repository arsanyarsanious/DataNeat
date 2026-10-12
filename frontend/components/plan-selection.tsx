"use client";
import { useEffect, useRef } from "react";
import type { Operation } from "@/lib/types";
import { Button } from "./ui/button";
export function PlanSelection({
  operations,
  disabled,
  onSelect,
}: {
  operations: Operation[];
  disabled: boolean;
  onSelect: (enabled: boolean) => void;
}) {
  const selected = operations.filter((o) => o.enabled).length,
    ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current)
      ref.current.indeterminate = selected > 0 && selected < operations.length;
  }, [selected, operations.length]);
  const destructive = operations.filter(
    (o) => o.safety === "destructive",
  ).length;
  return (
    <div className="plan-selection">
      <div className="plan-selection-controls">
        <label>
          <input
            ref={ref}
            type="checkbox"
            aria-label="Select all cleaning actions"
            checked={operations.length > 0 && selected === operations.length}
            disabled={disabled || operations.length === 0}
            onChange={(e) => onSelect(e.target.checked)}
          />
          Select all
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
        Select all enables every suggestion
        {destructive
          ? `, including ${destructive} action${destructive === 1 ? "" : "s"} that ${destructive === 1 ? "removes" : "remove"} rows`
          : ""}
        . Review their settings before applying. Currency and percentage
        interpretations still require your choice.
      </p>
    </div>
  );
}
