import type { Log } from "@/lib/types";
export function ImputationAudit({ operations }: { operations: Log[] }) {
  const logs = operations.filter(
    (o) => o.operation === "impute_missing_values" && o.method !== "preserve",
  );
  if (!logs.length) return null;
  return (
    <section className="panel imputation-audit" aria-label="Imputation audit">
      <div className="panel-heading">
        <h2>Imputation results</h2>
      </div>
      <div className="panel-body">
        {logs.map((log, i) => (
          <section key={`${log.id}-${i}`}>
            <h3>
              {log.column} · {String(log.method).replaceAll("_", " ")}
            </h3>
            <p>
              {log.imputed_count} cells imputed · Missing before:{" "}
              {log.missing_before} · Remaining missing: {log.missing_after}
            </p>
            <p>
              Grouping: {log.group_by?.join(", ") || "Whole column"} · Ordering:{" "}
              {log.order_by || "Not used"}
            </p>
            {log.distribution_before?.numeric && (
              <p>
                Before → after: mean {log.distribution_before.numeric.mean} →{" "}
                {log.distribution_after?.numeric?.mean ?? "—"}; median{" "}
                {log.distribution_before.numeric.median} →{" "}
                {log.distribution_after?.numeric?.median ?? "—"}; standard
                deviation {log.distribution_before.numeric.std} →{" "}
                {log.distribution_after?.numeric?.std ?? "—"}
              </p>
            )}
            <details>
              <summary>Before and after category frequencies</summary>
              <p>
                Before:{" "}
                {log.distribution_before?.frequencies
                  .map((f) => `${f.value}: ${f.count}`)
                  .join(" · ") || "No observations"}
              </p>
              <p>
                After:{" "}
                {log.distribution_after?.frequencies
                  .map((f) => `${f.value}: ${f.count}`)
                  .join(" · ") || "No observations"}
              </p>
            </details>
            {log.warnings?.map((warning) => (
              <p className="imputation-warning" key={warning}>
                {warning}
              </p>
            ))}
            {log.failures?.map((failure) => (
              <p role="alert" key={failure}>
                {failure}
              </p>
            ))}
          </section>
        ))}
      </div>
      <p className="panel-body">
        Highlighted cells are imputed estimates. The downloadable JSON cleaning
        report identifies every imputed cell using its original spreadsheet row
        and is_imputed flag.
      </p>
    </section>
  );
}
