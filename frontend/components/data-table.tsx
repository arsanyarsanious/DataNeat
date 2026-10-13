"use client";
import { useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import type { Preview } from "@/lib/types";
import { Button } from "./ui/button";
export function DataTable({
  data,
  onPage,
  disabled = false,
}: {
  data: Preview;
  onPage?: (page: number) => void;
  disabled?: boolean;
}) {
  const columns = useMemo<ColumnDef<unknown[]>[]>(
    () =>
      data.columns.map((name, index) => ({
        id: String(index),
        header: name,
        accessorFn: (row) => row[index],
        cell: (info) => {
          const value = info.getValue();
          return value === null || value === "" ? (
            <span className="empty-cell">empty</span>
          ) : (
            String(value)
          );
        },
      })),
    [data.columns],
  );
  const table = useReactTable({
    data: data.rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <>
      <div className="table-scroll">
        <table>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                <th className="row-number">#</th>
                {group.headers.map((h) => (
                  <th key={h.id}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr key={row.id}>
                <td className="row-number">
                  {(data.page - 1) * data.page_size + i + 1}
                </td>
                {row.getVisibleCells().map((c) => (
                  <td
                    key={c.id}
                    className={
                      data.is_imputed?.[i]?.[Number(c.column.id)]
                        ? "imputed-cell"
                        : undefined
                    }
                    title={
                      data.is_imputed?.[i]?.[Number(c.column.id)]
                        ? "Imputed estimate, not an observed value"
                        : undefined
                    }
                    data-is-imputed={
                      data.is_imputed?.[i]?.[Number(c.column.id)] || undefined
                    }
                  >
                    {data.is_imputed?.[i]?.[Number(c.column.id)] && (
                      <span className="imputed-badge">Estimated</span>
                    )}
                    {flexRender(c.column.columnDef.cell, c.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-footer">
        <span>
          {data.total_rows.toLocaleString()} rows · Page {data.page} of{" "}
          {Math.max(1, Math.ceil(data.total_rows / data.page_size))}
        </span>
        <div>
          <Button
            variant="outline"
            size="sm"
            disabled={disabled || data.page === 1 || !onPage}
            onClick={() => onPage?.(data.page - 1)}
          >
            Previous
          </Button>{" "}
          <Button
            variant="outline"
            size="sm"
            disabled={
              disabled ||
              data.page * data.page_size >= data.total_rows ||
              !onPage
            }
            onClick={() => onPage?.(data.page + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </>
  );
}
