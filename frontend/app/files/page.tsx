"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, FolderOpen, Pencil, Search, ShieldCheck, Trash2 } from "lucide-react";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { api } from "@/lib/types";
import "./files.css";

type SavedFile = {
  file_id: string; filename: string; saved_name?: string; saved_at: number | string;
  updated_at: number | string; rows: number; columns: number; revision: number;
};
type AccountStorage = { saved_files: number; saved_bytes: number; max_saved_files: number; max_saved_bytes: number };
function readableBytes(value: number) {
  return value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GB` : value >= 1024 ** 2 ? `${(value / 1024 ** 2).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB`;
}
function readableDate(value: number | string) {
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function MyFilesPage() {
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(false);
  const [accountEnabled, setAccountEnabled] = useState(false);
  const [email, setEmail] = useState("");
  const [files, setFiles] = useState<SavedFile[]>([]);
  const [storage, setStorage] = useState<AccountStorage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [busyFile, setBusyFile] = useState("");
  const [renameId, setRenameId] = useState("");
  const [name, setName] = useState("");
  const [deleteId, setDeleteId] = useState("");
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const config = await api<{ enabled: boolean }>("/auth/config");
      setAccountEnabled(config.enabled);
      if (!config.enabled) { setEmail(""); setFiles([]); setStorage(null); return; }
      let account: { email: string };
      try { account = await api<{ email: string }>("/auth/me"); }
      catch { setEmail(""); setFiles([]); setStorage(null); return; }
      setEmail(account.email);
      const result = await api<{ files: SavedFile[]; storage?: AccountStorage }>("/account/files");
      setFiles(result.files); setStorage(result.storage || null);
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    setCollapsed(localStorage.getItem("dataneat-sidebar-collapsed") === "true");
    const theme = localStorage.getItem("dataneat-theme") === "dark";
    setDark(theme); document.documentElement.classList.toggle("dark", theme);
    void refresh();
  }, [refresh]);
  const filtered = useMemo(() => {
    const search = query.trim().toLocaleLowerCase();
    return files.filter(file => !search || `${file.saved_name || ""} ${file.filename}`.toLocaleLowerCase().includes(search));
  }, [files, query]);
  async function rename(file: SavedFile) {
    if (!name.trim() || busyFile) return;
    setBusyFile(file.file_id); setError(""); setMessage("");
    try {
      await api(`/account/files/${encodeURIComponent(file.file_id)}/rename`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.trim() }) });
      setFiles(current => current.map(item => item.file_id === file.file_id ? { ...item, saved_name: name.trim() } : item));
      setRenameId(""); setMessage("File renamed.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusyFile(""); }
  }
  async function remove(file: SavedFile) {
    if (busyFile) return;
    setBusyFile(file.file_id); setError(""); setMessage("");
    try {
      await api(`/account/files/${encodeURIComponent(file.file_id)}`, { method: "DELETE" });
      setFiles(current => current.filter(item => item.file_id !== file.file_id));
      setDeleteId(""); setMessage("File deleted from your account.");
      const next = await api<{ files: SavedFile[]; storage?: AccountStorage }>("/account/files");
      setFiles(next.files); setStorage(next.storage || null);
    } catch (e) { setError((e as Error).message); }
    finally { setBusyFile(""); }
  }
  return <div className={`app-shell files-shell${collapsed ? " sidebar-collapsed" : ""}`}>
    <WorkspaceSidebar active="files" collapsed={collapsed} dark={dark} onToggle={() => { const next = !collapsed; setCollapsed(next); localStorage.setItem("dataneat-sidebar-collapsed", String(next)); }} onTheme={() => { const next = !dark; setDark(next); document.documentElement.classList.toggle("dark", next); localStorage.setItem("dataneat-theme", next ? "dark" : "light"); }} />
    <div className="main-shell"><header className="topbar files-topbar"><div className="breadcrumb">Workspace <span>My files</span></div><a className="button outline" href="/workspace">Open data cleaner <ArrowRight size={14} /></a></header>
      <main className="account-files-page">
        <div className="account-files-intro"><span className="eyebrow"><FolderOpen size={15} /> YOUR DATA, READY WHEN YOU ARE</span><h1>My files</h1><p>Save a file to your account and return to the same working copy and cleaning history.</p>{email && <p className="account-files-email">Signed in as <strong>{email}</strong></p>}</div>
        {loading ? <div className="account-files-state" role="status">Opening your files…</div> : !accountEnabled ? <section className="account-files-state">
          <ShieldCheck size={24} /><h2>Account saving is awaiting setup</h2><p>Google sign-in is not configured yet. Saved account files require sign-in. You can continue cleaning temporary files in the local workspace.</p><div><a className="button outline" href="/login">View sign-in options</a><a href="/workspace">Return to cleaning</a></div>
        </section> : !email ? <section className="account-files-state"><FolderOpen size={24} /><h2>Sign in to see your files</h2><p>Your saved files belong to your verified account.</p><a className="button" href="/login">Sign in</a></section> : <>
          <div className="account-files-tools"><label htmlFor="saved-file-search">Find a saved file</label><div className="account-files-search"><Search size={16} /><input id="saved-file-search" type="search" placeholder="Search by file name" value={query} onChange={e => setQuery(e.target.value)} /></div><div className="account-files-count"><span>{files.length} saved {files.length === 1 ? "file" : "files"}</span><button className="account-file-text-button" disabled={Boolean(busyFile)} onClick={() => void refresh()}>Refresh</button></div></div>
          <p className="account-files-retention">Saved files do not expire automatically. Temporary uploads still expire after 24 hours. You can delete a saved file whenever you choose.{storage && <span className="account-files-quota">Storage: {storage.saved_files} / {storage.max_saved_files} files · {readableBytes(storage.saved_bytes)} / {readableBytes(storage.max_saved_bytes)} used, including originals and history.</span>}</p>
          {filtered.length === 0 ? <section className="account-files-state"><FolderOpen size={28} /><h2>{query.trim() ? "No matching files" : "No saved files yet"}</h2><p>{query.trim() ? "Try another name." : "Open a spreadsheet in the cleaner and choose Save to my files. Its original, current copy, and cleaning history will be kept together."}</p>{query.trim() ? <button className="button outline" onClick={() => setQuery("")}>Clear search</button> : <a className="button" href="/workspace">Open data cleaner</a>}</section> : <div className="account-files-list">{filtered.map(file => <article key={file.file_id} className="account-saved-file">
            <div className="account-saved-file-main"><span className="account-saved-file-icon"><FolderOpen size={20} /></span><div><h2>{file.saved_name || file.filename}</h2>{file.saved_name && file.saved_name !== file.filename && <p className="account-file-original">Original: {file.filename}</p>}<p className="account-saved-file-meta">{file.rows.toLocaleString()} rows · {file.columns.toLocaleString()} columns · Revision {file.revision}</p><p className="account-saved-file-meta">Updated {readableDate(file.updated_at || file.saved_at)}</p></div></div>
            <div className="account-saved-file-actions"><a className="button" href={`/workspace?file=${encodeURIComponent(file.file_id)}`}>Continue cleaning <ArrowRight size={13} /></a><button className="button outline" disabled={Boolean(busyFile)} onClick={() => { setRenameId(renameId === file.file_id ? "" : file.file_id); setName(file.saved_name || file.filename); setDeleteId(""); }}><Pencil size={13} /> Rename</button><button className="button outline account-file-delete" disabled={Boolean(busyFile)} onClick={() => { setDeleteId(deleteId === file.file_id ? "" : file.file_id); setRenameId(""); }}><Trash2 size={13} /> Delete</button></div>
            {renameId === file.file_id && <form className="account-file-inline-form" onSubmit={e => { e.preventDefault(); void rename(file); }}><label htmlFor={`rename-${file.file_id}`}>File name<input id={`rename-${file.file_id}`} value={name} onChange={e => setName(e.target.value)} maxLength={160} required autoFocus disabled={Boolean(busyFile)} /></label><div><button className="button outline" type="button" disabled={Boolean(busyFile)} onClick={() => setRenameId("")}>Cancel</button><button className="button" disabled={!name.trim() || Boolean(busyFile)}>{busyFile === file.file_id ? "Saving…" : "Save name"}</button></div></form>}
            {deleteId === file.file_id && <div className="account-file-delete-confirm" role="group" aria-label={`Delete ${file.saved_name || file.filename}`}><p>Delete this file, its original, cleaned copy, and cleaning history? This cannot be undone.</p><div><button className="button outline" disabled={Boolean(busyFile)} onClick={() => setDeleteId("")}>Keep file</button><button className="button account-file-danger" disabled={Boolean(busyFile)} onClick={() => void remove(file)}>{busyFile === file.file_id ? "Deleting…" : "Delete permanently"}</button></div></div>}
          </article>)}</div>}
        </>}
        {error && <div className="account-file-error" role="alert"><p>{error}</p><button className="button outline" disabled={Boolean(busyFile)} onClick={() => void refresh()}>Retry</button></div>}
        {message && <p className="account-files-message" role="status">{message}</p>}
      </main>
    </div>
  </div>;
}
