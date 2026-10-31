"use client";
import { Fragment, createContext, useContext, useEffect, useRef, useState, type ReactNode, type FormEvent } from "react";
import { createClient, type SupabaseClient, type Session } from "@supabase/supabase-js";
import { ShieldCheck } from "lucide-react";
import { DataNeatMark } from "./dataneat-mark";
import { ThemeToggle } from "./theme-toggle";
import { api } from "@/lib/types";

type Config = { enabled: boolean; url: string; publishable_key: string; google_enabled: boolean };
type Account = { email: string; admin: boolean; id?: string };
type AccountNavigation = { logout: () => void; showUsage?: () => void };
const AccountNavigationContext = createContext<AccountNavigation | null>(null);
export function useAccountNavigation() { return useContext(AccountNavigationContext); }

function returnPath() {
  const requested = window.location.pathname === "/login" ? new URLSearchParams(window.location.search).get("next") : window.location.pathname + window.location.search;
  if (requested === "/files") return requested;
  if (requested === "/workspace") return requested;
  if (requested && /^\/workspace\?file=[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i.test(requested)) return requested;
  return "/workspace";
}
function clearWorkspaceCache() {
  try {
    for (const key of Object.keys(sessionStorage)) if (["dataneat-workspace", "dataneat-legacy-workspace", "dataneat-login-event"].includes(key) || /^(dataneat-editor-|dataneat-flow-|dataneat-automatic-notes-|dataneat-downloaded-)/.test(key)) sessionStorage.removeItem(key);
  } catch { /* Account authorization remains enforced by the server. */ }
}

function LoginPanel({ client, config, recovery, onRecovered }: {
  client: SupabaseClient | null; config: Config; recovery: boolean; onRecovered: () => void;
}) {
  const [mode, setMode] = useState<"signin" | "signup" | "reset">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const ready = config.enabled && client !== null;
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!client || !ready) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const redirectTo = `${window.location.origin}/login?next=${encodeURIComponent(returnPath())}`;
      if (recovery) {
        const { error } = await client.auth.updateUser({ password });
        if (error) throw error;
        setPassword(""); onRecovered();
      } else if (mode === "reset") {
        const { error } = await client.auth.resetPasswordForEmail(email, { redirectTo: redirectTo + "&recovery=1" });
        if (error) throw error;
        setMessage("If an account exists, a password-reset link has been sent. Check your inbox.");
      } else if (mode === "signup") {
        const { error } = await client.auth.signUp({ email, password, options: { emailRedirectTo: redirectTo } });
        if (error) throw error;
        setPassword(""); setMessage("Check your inbox to verify your email, then sign in.");
      } else {
        const { error } = await client.auth.signInWithPassword({ email, password });
        if (error) throw error;
        setPassword("");
      }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function google() {
    if (!client || !config.google_enabled) return;
    setBusy(true); setError("");
    try {
      const { error } = await client.auth.signInWithOAuth({ provider: "google", options: { redirectTo: `${window.location.origin}/login?next=${encodeURIComponent(returnPath())}` } });
      if (error) throw error;
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }
  return <main className="access-shell">
    <div className="access-theme-control"><ThemeToggle /></div>
    <section className="access-story">
      <a href="/" className="access-brand"><DataNeatMark size={34} /> DataNeat</a>
      <span className="eyebrow">LESS MESS. MORE POSSIBILITY.</span>
      <h1>Good data.<br />Your own workspace.</h1>
      <p>Clean your spreadsheets and keep your files, progress, and cleaning history together in your account.</p>
      <div className="access-assurance"><ShieldCheck size={24} /><p>Your original files stay intact. Spreadsheet contents are excluded from usage analytics.</p></div>
    </section>
    <section className="access-card" aria-label="Account access">
      <h2>{recovery ? "Choose a new password" : mode === "signup" ? "Create your account" : mode === "reset" ? "Reset your password" : "Welcome back"}</h2>
      <p>{recovery ? "Use at least 12 characters." : "Sign in to your DataNeat workspace."}</p>
      {!ready && <div className="notice" role="status">Login is being set up. Account creation and Google sign-in are not available yet.</div>}
      {!recovery && mode !== "reset" && <>
        <button className="button outline access-google" disabled={!ready || !config.google_enabled || busy} onClick={() => void google()}>
          <span aria-hidden="true" className="google-letter">G</span> Continue with Google
        </button>
        {ready && !config.google_enabled && <p className="access-help">Google sign-in is awaiting activation.</p>}
        <div className="access-divider"><span />or use your email<span /></div>
      </>}
      <form onSubmit={submit}>
        {!recovery && <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required disabled={!ready || busy} /></label>}
        {(recovery || mode !== "reset") && <label>{recovery ? "New password" : "Password"}<input type="password" autoComplete={recovery || mode === "signup" ? "new-password" : "current-password"} minLength={recovery || mode === "signup" ? 12 : undefined} value={password} onChange={e => setPassword(e.target.value)} required disabled={!ready || busy} /></label>}
        {error && <p role="alert" className="access-error">{error}</p>}
        {message && <p role="status" className="notice">{message}</p>}
        <button className="button access-submit" type="submit" disabled={!ready || busy}>{busy ? "Please wait…" : recovery ? "Save new password" : mode === "signup" ? "Create account" : mode === "reset" ? "Send reset link" : "Sign in"}</button>
      </form>
      {!recovery && <div className="access-links">
        <button onClick={() => { setMode(mode === "signup" ? "signin" : "signup"); setError(""); setMessage(""); }}>{mode === "signup" ? "Already have an account? Sign in" : "New here? Create an account"}</button>
        <button onClick={() => { setMode(mode === "reset" ? "signin" : "reset"); setError(""); setMessage(""); }}>{mode === "reset" ? "Back to sign in" : "Forgot password?"}</button>
      </div>}
      <p className="access-disclosure">When accounts are enabled, we record your email, sign-ins, uploads, cleaning requests, confirmed fixes, and downloads for usage monitoring. Records are retained for 90 days. Spreadsheet contents and passwords are excluded. Supabase handles authentication; Google handles Google sign-in.</p>
      <a className="access-return" href="/privacy" target="_blank" rel="noopener noreferrer">Read the privacy policy</a>
      {!ready && <a className="button outline access-return" href="/workspace">Continue to local workspace</a>}
    </section>
  </main>;
}

export function AccountAccess({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [client, setClient] = useState<SupabaseClient | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [loginPage, setLoginPage] = useState(false);
  const [publicPage, setPublicPage] = useState(false);
  const [usage, setUsage] = useState<{ retention_days: number; totals: Record<string, number>; users: { email: string; counts: Record<string, number> }[] } | null>(null);
  const usageDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = usageDialog.current;
    if (usage && dialog && !dialog.open) dialog.showModal();
    return () => { if (dialog?.open) dialog.close(); };
  }, [usage]);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", localStorage.getItem("dataneat-theme") === "dark");
    let active = true;
    let unsubscribe: (() => void) | undefined;
    let sequence = 0;
    if (["/", "/privacy", "/guide"].includes(window.location.pathname)) { setPublicPage(true); setPending(false); return; }
    setLoginPage(window.location.pathname === "/login");
    setRecovery(new URLSearchParams(window.location.search).get("recovery") === "1");
    async function start() {
      try {
        const conf = await api<Config>("/auth/config");
        if (!active) return;
        setConfig(conf);
        if (!conf.enabled) { setPending(false); return; }
        const supabase = createClient(conf.url, conf.publishable_key, { auth: { flowType: "pkce", detectSessionInUrl: true, autoRefreshToken: true, persistSession: true } });
        setClient(supabase);
        async function sync(session: Session | null, event = "INITIAL_SESSION") {
          const current = ++sequence;
          try {
            if (!session) {
              await api("/auth/logout", { method: "POST" });
              if (active && current === sequence) { clearWorkspaceCache(); sessionStorage.removeItem("dataneat-account-id"); setAccount(null); setPending(false); }
              return;
            }
            const result = await api<Account>("/auth/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ access_token: session.access_token }) });
            if (!active || current !== sequence) return;
            const previousAccount = sessionStorage.getItem("dataneat-account-id");
            if (previousAccount && previousAccount !== session.user.id) clearWorkspaceCache();
            sessionStorage.setItem("dataneat-account-id", session.user.id);
            setAccount({ ...result, id: session.user.id }); setPending(false); setError("");
            const marker = session.user.id + ":" + session.user.last_sign_in_at;
            if (event === "SIGNED_IN" && sessionStorage.getItem("dataneat-login-event") !== marker) {
              await api("/auth/sign-in-event", { method: "POST" });
              sessionStorage.setItem("dataneat-login-event", marker);
            }
            if (window.location.pathname === "/login" && event !== "PASSWORD_RECOVERY" && !window.location.search.includes("recovery")) {
              // Keep login and recovery on the same trusted origin.
              if (event === "SIGNED_IN" || event === "INITIAL_SESSION") window.location.replace(returnPath());
            }
          } catch (e) {
            if (active && current === sequence) { setAccount(null); setError((e as Error).message); setPending(false); }
          }
        }
        let syncQueue = Promise.resolve();
        const { data } = supabase.auth.onAuthStateChange((event, session) => {
          if (!active) return;
          if (event === "PASSWORD_RECOVERY") setRecovery(true);
          if (event === "SIGNED_OUT") { setAccount(null); setUsage(null); }
          syncQueue = syncQueue.then(() => active ? sync(session, event) : undefined);
        });
        unsubscribe = () => data.subscription.unsubscribe();
      } catch (e) { if (active) { setError((e as Error).message); setPending(false); } }
    }
    void start();
    return () => { active = false; unsubscribe?.(); };
  }, []);
  if (publicPage) return <>{children}</>;
  if (pending) return <main className="access-loading" role="status">Opening your workspace…</main>;
  if (!config) return <main className="access-loading"><p role="alert">{error || "The workspace is temporarily unavailable."}</p><button className="button" onClick={() => window.location.reload()}>Retry</button></main>;
  if (recovery || (config.enabled && !account) || (loginPage && !account)) return <>
    {error && <p role="alert" className="access-global-error">{error}</p>}
    <LoginPanel client={client} config={config} recovery={recovery} onRecovered={() => { setRecovery(false); window.location.replace(returnPath()); }} />
  </>;
  return <AccountNavigationContext.Provider value={account ? {
    logout: () => { clearWorkspaceCache(); sessionStorage.removeItem("dataneat-account-id"); setAccount(null); setUsage(null); void api("/auth/logout", { method: "POST" }); void client?.auth.signOut(); },
    showUsage: account.admin ? () => void api<NonNullable<typeof usage>>("/admin/usage").then(setUsage).catch(e => setError(e.message)) : undefined,
  } : null}>
    {usage && <dialog ref={usageDialog} className="usage-overview" aria-labelledby="usage-overview-title" onCancel={()=>setUsage(null)}><h2 id="usage-overview-title">Usage overview · last {usage.retention_days} days</h2><button type="button" onClick={() => setUsage(null)}>Close</button><div className="table-scroll"><table><thead><tr><th>Account</th><th>Sign-ins</th><th>Uploads</th><th>Cleaning requests</th><th>Confirmed fixes</th><th>Downloads</th></tr></thead><tbody>{usage.users.map(u => <tr key={u.email}><td>{u.email}</td>{["sign_in", "upload", "clean", "editor_fix", "download"].map(e => <td key={e}>{u.counts[e] || 0}</td>)}</tr>)}</tbody></table></div></dialog>}
    <Fragment key={account?.id || "local"}>{children}</Fragment>
  </AccountNavigationContext.Provider>;
}
