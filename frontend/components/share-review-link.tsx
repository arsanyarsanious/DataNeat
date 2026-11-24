"use client";
import { useEffect, useState } from "react";
import { Link2, Copy, Check } from "lucide-react";
import { api } from "@/lib/types";
import { Button } from "./ui/button";

type ShareStatus = {
  active: boolean;
  created_at?: number;
  expires_at?: number;
  ttl_hours?: number;
};

function readable(seconds: number) {
  return new Date(seconds * 1000).toLocaleString();
}

export function ShareReviewLink({ fileId }: { fileId: string }) {
  const [status, setStatus] = useState<ShareStatus | null>(null);
  const [link, setLink] = useState("");
  const [expiresAt, setExpiresAt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    api<ShareStatus>(`/files/${fileId}/share`)
      .then((value) => {
        if (alive) setStatus(value);
      })
      .catch(() => {
        /* A status failure must not block exporting. */
      });
    return () => {
      alive = false;
    };
  }, [fileId]);

  const active = Boolean(
    status?.active && (status.expires_at ?? 0) > Date.now() / 1000,
  );
  const until = expiresAt || status?.expires_at || 0;

  async function create() {
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const result = await api<{ token: string; expires_at: number }>(
        `/files/${fileId}/share`,
        { method: "POST" },
      );
      setLink(
        `${window.location.origin}/share?t=${encodeURIComponent(result.token)}`,
      );
      setExpiresAt(result.expires_at);
      setStatus({ active: true, expires_at: result.expires_at });
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    setBusy(true);
    setError("");
    try {
      await api(`/files/${fileId}/share`, { method: "DELETE" });
      setLink("");
      setExpiresAt(0);
      setStatus({ active: false });
      setCopied(false);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setError("Copy failed. Select the link above and copy it manually.");
    }
  }

  return (
    <details className="result-details" aria-label="Share a read-only review link">
      <summary>Share a read-only review</summary>
      <p>
        Create an expiring link so a colleague can read the change summary, a
        25-row preview and the PDF report. They cannot edit, download the
        original file, or open your workspace.
      </p>
      {active ? (
        <>
          <p>
            {until
              ? `An active review link is available until ${readable(until)}.`
              : "An active review link exists."}
          </p>
          {link && (
            <label className="setting">
              Review link
              <input
                readOnly
                value={link}
                onFocus={(event) => event.currentTarget.select()}
              />
            </label>
          )}
          <div className="workflow-buttons">
            {link ? (
              <Button size="sm" onClick={copy}>
                {copied ? (
                  <>
                    <Check size={14} aria-hidden="true" /> Copied
                  </>
                ) : (
                  <>
                    <Copy size={14} aria-hidden="true" /> Copy link
                  </>
                )}
              </Button>
            ) : (
              <Button size="sm" disabled={busy} onClick={create}>
                <Link2 size={14} aria-hidden="true" /> Create a new link
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={revoke}
            >
              Revoke all links
            </Button>
          </div>
        </>
      ) : (
        <div className="workflow-buttons">
          <Button size="sm" disabled={busy} onClick={create}>
            <Link2 size={14} aria-hidden="true" /> Create read-only link
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p>
        <small>
          Anyone with the link can see the values in the preview and the PDF.
          The link expires automatically after seven days and can be revoked at
          any time. The original upload is never included.
        </small>
      </p>
    </details>
  );
}
