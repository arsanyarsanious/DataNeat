"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Clock3, FolderOpen, Save } from "lucide-react";
import { api } from "@/lib/types";
import "@/app/files/files.css";

export type FileStorageStatus = {
  saved: boolean;
  saved_name?: string;
  expires_at?: number | null;
  account_enabled?: boolean;
  signed_in?: boolean;
};

export function AccountFileControls({ fileId, onChange, disabled = false }: {
  fileId: string;
  onChange?: (status: FileStorageStatus) => void;
  disabled?: boolean;
}) {
  const [status, setStatus] = useState<FileStorageStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmTemporary, setConfirmTemporary] = useState(false);
  const [error, setError] = useState("");
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const generation = useRef(0);
  const loadStatus = useCallback(async () => {
    const config = await api<{ enabled: boolean }>("/auth/config");
    if (!config.enabled) return { saved: false, account_enabled: false, signed_in: false } as FileStorageStatus;
    try { await api<{ email: string }>("/auth/me"); }
    catch { return { saved: false, account_enabled: true, signed_in: false } as FileStorageStatus; }
    const current = await api<FileStorageStatus>(`/account/files/${encodeURIComponent(fileId)}/status`);
    return { ...current, account_enabled: true, signed_in: true };
  }, [fileId]);
  useEffect(() => {
    const current = ++generation.current;
    setLoading(true); setStatus(null); setError(""); setConfirmTemporary(false); setBusy(false);
    void loadStatus().then(result => {
      if (generation.current !== current) return;
      setStatus(result); onChangeRef.current?.(result);
    }).catch(e => { if (generation.current === current) setError((e as Error).message); })
      .finally(() => { if (generation.current === current) setLoading(false); });
    return () => { generation.current += 1; };
  }, [loadStatus]);
  async function changeRetention(save: boolean) {
    if (!status?.signed_in || busy || disabled) return;
    const current = generation.current;
    setBusy(true); setError("");
    try {
      await api(`/account/files/${encodeURIComponent(fileId)}/${save ? "save" : "temporary"}`, {
        method: "POST",
      });
      const next = await loadStatus();
      if (generation.current !== current) return;
      setStatus(next); setConfirmTemporary(false); onChangeRef.current?.(next);
    } catch (e) { if (generation.current === current) setError((e as Error).message); }
    finally { if (generation.current === current) setBusy(false); }
  }
  return <div className="account-file-controls" aria-label="File storage">
    <div className="account-file-storage-row">
      <span className={`account-file-storage-state${status?.saved ? " saved" : ""}`}>
        {status?.saved ? <Check size={14} /> : <Clock3 size={14} />}
        {loading ? "Checking file storage…" : status?.saved ? "Saved to your account" : status ? "Temporary · 24 hours" : "Storage status unavailable"}
      </span>
      {!loading && status?.signed_in && (status.saved ? <>
        <a href="/files" target="_blank" rel="noopener noreferrer"><FolderOpen size={13} /> My files</a>
        <button className="account-file-text-button" disabled={busy || disabled} onClick={() => setConfirmTemporary(!confirmTemporary)}>Make temporary</button>
      </> : <button className="button outline account-file-save" disabled={busy || disabled} onClick={() => void changeRetention(true)}><Save size={13} />{busy ? "Saving…" : "Save to my files"}</button>)}
      {!loading && status?.account_enabled && !status.signed_in && <a className="account-file-login" href="/login" target="_blank" rel="noopener noreferrer">Sign in to save</a>}
      {!loading && status && !status.account_enabled && <button className="button outline account-file-save" disabled title="Account saving needs Google sign-in setup"><Save size={13} /> Save to my files</button>}
    </div>
    {!loading && status?.saved && <p className="account-file-hint">Original, current copy, and cleaning history are saved. Further changes are saved with this file. No automatic expiry.</p>}
    {!loading && status && !status.account_enabled && <p className="account-file-hint">Account saving needs Google sign-in setup. <a href="/files" target="_blank" rel="noopener noreferrer">About My files</a></p>}
    {confirmTemporary && <div className="account-file-confirm" role="group" aria-label="Make file temporary">
      <p>Remove this file from My files? It will expire 24 hours from now.</p>
      <div><button className="button outline" disabled={busy || disabled} onClick={() => setConfirmTemporary(false)}>Keep saved</button><button className="button" disabled={busy || disabled} onClick={() => void changeRetention(false)}>{busy ? "Updating…" : "Make temporary"}</button></div>
    </div>}
    {error && <p role="alert" className="account-file-error">{error}</p>}
  </div>;
}
