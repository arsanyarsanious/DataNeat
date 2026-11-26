"use client";

import { useEffect, useState, type ReactNode } from "react";
import { DataNeatMark } from "./dataneat-mark";

type SkeletonVariant = "workspace" | "files" | "share" | "login";

const NAV_WIDTHS = ["68%", "54%", "62%", "47%", "58%"];
const ROW_WIDTHS = [
  [72, 58, 81, 46, 66, 53],
  [61, 74, 49, 68, 44, 77],
  [78, 46, 64, 72, 55, 42],
  [52, 67, 75, 49, 80, 61],
  [69, 43, 57, 76, 48, 70],
  [45, 71, 63, 54, 74, 51],
  [76, 52, 47, 69, 60, 43],
  [58, 79, 55, 44, 68, 73],
  [64, 48, 72, 60, 46, 56],
  [49, 62, 78, 51, 70, 65],
  [73, 56, 43, 75, 58, 47],
];

function SkeletonBrand() {
  return (
    <div className="skeleton-brand">
      <span className="skeleton-brand-mark">
        <DataNeatMark size={30} />
      </span>
      <span className="skeleton-brand-text">DataNeat</span>
    </div>
  );
}

function SkeletonNav({ activeIndex = 0 }: { activeIndex?: number }) {
  return (
    <div className="skeleton-nav" aria-hidden="true">
      <span className="skeleton-workspace-label">WORKSPACE</span>
      {NAV_WIDTHS.map((width, index) => (
        <span
          key={index}
          className={`skeleton-nav-pill${index === activeIndex ? " is-active" : ""}`}
        >
          <span className="skeleton-nav-dot" />
          <span className="skeleton-nav-label" style={{ width }} />
        </span>
      ))}
    </div>
  );
}

function SkeletonSidebar({ activeIndex = 0 }: { activeIndex?: number }) {
  return (
    <aside className="skeleton-sidebar" aria-hidden="true">
      <div className="skeleton-sidebar-head">
        <SkeletonBrand />
        <span className="skeleton-icon-button" />
      </div>
      <SkeletonNav activeIndex={activeIndex} />
      <div className="skeleton-sidebar-bottom">
        <span className="skeleton-avatar" />
        <div>
          <span className="skeleton-line skeleton-line-sm" />
          <span className="skeleton-line skeleton-line-xs" />
        </div>
      </div>
    </aside>
  );
}

function SkeletonStatus({ label }: { label: string }) {
  return (
    <div className="skeleton-status" aria-live="polite">
      <span className="skeleton-status-dot" aria-hidden="true" />
      <span className="skeleton-status-text">{label}</span>
    </div>
  );
}

function SkeletonTopbar({ label }: { label: string }) {
  return (
    <header className="skeleton-topbar">
      <SkeletonStatus label={label} />
      <div className="skeleton-actions" aria-hidden="true">
        <span className="skeleton-button" />
        <span className="skeleton-button skeleton-button-wide" />
        <span className="skeleton-icon-button" />
      </div>
    </header>
  );
}

function DataGridSkeleton() {
  return (
    <section className="skeleton-surface skeleton-grid-card" aria-hidden="true">
      <div className="skeleton-table-toolbar">
        <div>
          <span className="skeleton-line skeleton-line-md" />
          <span className="skeleton-line skeleton-line-sm" />
        </div>
        <div className="skeleton-actions">
          <span className="skeleton-button" />
          <span className="skeleton-button" />
        </div>
      </div>
      <div className="skeleton-table-scroll">
        <div className="skeleton-table-head">
          <span className="skeleton-row-number" />
          {Array.from({ length: 6 }, (_, index) => (
            <div className="skeleton-column-head" key={index}>
              <span
                className="skeleton-header-name"
                style={{ width: `${68 - index * 4}%` }}
              />
              <span
                className="skeleton-header-badge"
                style={{ width: `${42 - index * 3}%` }}
              />
            </div>
          ))}
        </div>
        <div className="skeleton-table-body">
          {ROW_WIDTHS.map((widths, row) => (
            <div className="skeleton-row" key={row}>
              <span className="skeleton-row-number" />
              {widths.map((width, column) => (
                <span className="skeleton-cell" key={column}>
                  <span className="skeleton-cell-bar" style={{ width: `${width}%` }} />
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FilesSkeleton() {
  return (
    <div className="skeleton-content skeleton-files-content" aria-hidden="true">
      <div className="skeleton-heading">
        <span className="skeleton-line skeleton-line-eyebrow" />
        <span className="skeleton-line skeleton-line-title" />
        <span className="skeleton-line skeleton-line-copy" />
      </div>
      <div className="skeleton-files-toolbar">
        <span className="skeleton-search" />
        <span className="skeleton-line skeleton-line-sm" />
      </div>
      {[0, 1, 2].map((card) => (
        <div className="skeleton-surface skeleton-file-card" key={card}>
          <span className="skeleton-file-icon" />
          <div className="skeleton-file-copy">
            <span className="skeleton-line skeleton-line-md" />
            <span className="skeleton-line skeleton-line-sm" />
            <span className="skeleton-line skeleton-line-xs" />
          </div>
          <span className="skeleton-button skeleton-button-wide" />
        </div>
      ))}
    </div>
  );
}

function WorkspaceSkeletonContent() {
  return (
    <div className="skeleton-content" aria-hidden="true">
      <div className="skeleton-heading">
        <span className="skeleton-line skeleton-line-eyebrow" />
        <span className="skeleton-line skeleton-line-title" />
        <span className="skeleton-line skeleton-line-copy" />
      </div>
      <div className="skeleton-stepper" aria-hidden="true">
        {[0, 1, 2, 3].map((step) => (
          <span className="skeleton-step" key={step}>
            <span className="skeleton-step-number" />
            <span className="skeleton-line skeleton-line-sm" />
          </span>
        ))}
      </div>
      <DataGridSkeleton />
    </div>
  );
}

function ShareSkeletonContent({ label }: { label: string }) {
  return (
    <div className="skeleton-shell skeleton-share" role="status" aria-live="polite" aria-busy="true">
      <div className="skeleton-share-topbar">
        <SkeletonBrand />
        <span className="skeleton-icon-button" aria-hidden="true" />
      </div>
      <main className="skeleton-share-main">
        <SkeletonStatus label={label} />
        <section className="skeleton-surface skeleton-share-card" aria-hidden="true">
          <div className="skeleton-heading">
            <span className="skeleton-line skeleton-line-eyebrow" />
            <span className="skeleton-line skeleton-line-title" />
            <span className="skeleton-line skeleton-line-copy" />
          </div>
          <div className="skeleton-share-metrics">
            {[0, 1, 2, 3].map((metric) => (
              <div key={metric}>
                <span className="skeleton-line skeleton-line-xs" />
                <span className="skeleton-line skeleton-line-md" />
              </div>
            ))}
          </div>
          <div className="skeleton-share-table">
            {[0, 1, 2, 3, 4, 5, 6].map((row) => (
              <div className="skeleton-share-row" key={row}>
                <span className="skeleton-row-number" />
                {[68, 52, 75, 46, 61].map((width, column) => (
                  <span className="skeleton-cell" key={column}>
                    <span className="skeleton-cell-bar" style={{ width: `${width}%` }} />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function LoginSkeletonContent({ label }: { label: string }) {
  return (
    <div className="skeleton-shell skeleton-login" role="status" aria-live="polite" aria-busy="true">
      <section className="skeleton-surface skeleton-login-card">
        <SkeletonBrand />
        <div className="skeleton-heading">
          <span className="skeleton-line skeleton-line-eyebrow" />
          <span className="skeleton-line skeleton-line-title" />
          <span className="skeleton-line skeleton-line-copy" />
        </div>
        <span className="skeleton-field" aria-hidden="true" />
        <span className="skeleton-field" aria-hidden="true" />
        <span className="skeleton-button skeleton-button-block" aria-hidden="true" />
        <span className="skeleton-line skeleton-line-xs skeleton-centered" aria-hidden="true" />
        <SkeletonStatus label={label} />
      </section>
    </div>
  );
}

export function AppSkeleton({
  variant = "workspace",
  activeIndex = 0,
  label = "Preparing your data environment...",
}: {
  variant?: SkeletonVariant;
  activeIndex?: number;
  label?: string;
}) {
  if (variant === "share") return <ShareSkeletonContent label={label} />;
  if (variant === "login") return <LoginSkeletonContent label={label} />;
  return (
    <div className={`skeleton-shell skeleton-${variant}`} role="status" aria-live="polite" aria-busy="true" aria-label={label}>
      <SkeletonSidebar activeIndex={activeIndex} />
      <div className="skeleton-main">
        <SkeletonTopbar label={label} />
        {variant === "files" ? <FilesSkeleton /> : <WorkspaceSkeletonContent />}
      </div>
    </div>
  );
}

export function LoadingOverlay({
  loading,
  variant = "workspace",
  activeIndex = 0,
  label = "Preparing your data environment...",
  children,
}: {
  loading: boolean;
  variant?: SkeletonVariant;
  activeIndex?: number;
  label?: string;
  children: ReactNode;
}) {
  const [visible, setVisible] = useState(loading);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (loading) {
      setVisible(true);
      setLeaving(false);
      return;
    }
    if (!visible) return;
    setLeaving(true);
    const timer = window.setTimeout(() => {
      setVisible(false);
      setLeaving(false);
    }, 200);
    return () => window.clearTimeout(timer);
  }, [loading, visible]);

  return (
    <>
      {!loading && children}
      {visible && (
        <div
          className={`skeleton-layer${leaving ? " is-leaving" : ""}`}
          aria-hidden={loading ? undefined : true}
        >
          <AppSkeleton variant={variant} activeIndex={activeIndex} label={label} />
        </div>
      )}
    </>
  );
}
