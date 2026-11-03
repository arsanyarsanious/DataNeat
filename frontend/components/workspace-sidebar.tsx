"use client";
import { ChevronsLeft, ChevronsRight, Table2, FileText, BookOpen, FolderOpen, ShieldCheck, UserRound, Sun, Moon, LogOut, ChartColumn } from "lucide-react";
import { DataNeatMark } from "./dataneat-mark";
import { useAccountNavigation } from "./account-access";

export function WorkspaceSidebar({ collapsed, onToggle, dark, onTheme, active = "cleaner", onCleaner }: {
  collapsed: boolean; onToggle: () => void; dark: boolean; onTheme: () => void;
  active?: "cleaner" | "privacy" | "guide" | "files"; onCleaner?: () => void;
}) {
  const accountNavigation = useAccountNavigation();
  return <aside className="sidebar workspace-sidebar compact-workspace-sidebar" aria-label="Workspace navigation">
    <div className="sidebar-header">
      <a href="/" className="brand" aria-label="DataNeat home"><span className="brand-symbol"><DataNeatMark size={30} /></span><span className="brand-text"><strong>DataNeat</strong></span></a>
      <button className="icon-button sidebar-toggle" aria-label={collapsed ? "Expand sidebar" : "Minimize sidebar"} aria-expanded={!collapsed} title={collapsed ? "Expand sidebar" : "Minimize sidebar"} onClick={onToggle}>{collapsed ? <ChevronsRight size={17} /> : <ChevronsLeft size={17} />}</button>
    </div>
    <div className="workspace-label">WORKSPACE</div>
    <nav className="workspace-nav">
      {onCleaner ? <button className={`nav-item${active === "cleaner" ? " active" : ""}`} aria-current={active === "cleaner" ? "page" : undefined} aria-label="Data cleaner" title="Data cleaner" onClick={onCleaner}><Table2 size={18} /><span className="sidebar-label">Data cleaner</span></button> : <a className="nav-item" href="/workspace" aria-label="Data cleaner" title="Data cleaner"><Table2 size={18} /><span className="sidebar-label">Data cleaner</span></a>}
      <a className={`nav-item${active === "files" ? " active" : ""}`} aria-current={active === "files" ? "page" : undefined} href="/files" aria-label="My files" title="My files"><FolderOpen size={18} /><span className="sidebar-label">My files</span></a>
      <a className={`nav-item${active === "guide" ? " active" : ""}`} aria-current={active === "guide" ? "page" : undefined} href="/guide" aria-label="Website guide" title="Website guide"><BookOpen size={18} /><span className="sidebar-label">Website guide</span></a>
      <a className={`nav-item${active === "privacy" ? " active" : ""}`} aria-current={active === "privacy" ? "page" : undefined} href="/privacy" aria-label="Privacy policy" title="Privacy policy"><FileText size={18} /><span className="sidebar-label">Privacy policy</span></a>
    </nav>
    <div className="sidebar-note"><ShieldCheck size={18} /><p>Original files preserved.<br />Your workspace stays private.</p></div>
    <div className="sidebar-bottom"><span className="avatar" aria-hidden="true"><UserRound size={16} /></span><div><strong>Personal workspace</strong><small>Temporary or saved files</small></div></div>
    <div className="sidebar-utilities"><button className="icon-button sidebar-theme-button" aria-label="Toggle dark mode" title="Toggle theme" onClick={onTheme}>{dark ? <Sun size={17} /> : <Moon size={17} />}<span className="sidebar-utility-label">{dark ? "Light mode" : "Dark mode"}</span></button></div>
    {accountNavigation && <div className="sidebar-account-actions" aria-label="Account actions">
      {accountNavigation.showUsage && <button type="button" className="sidebar-account-button" aria-label="Usage overview" title="Usage overview" onClick={accountNavigation.showUsage}><ChartColumn size={18} aria-hidden="true"/><span className="sidebar-account-label">Usage overview</span></button>}
      <button type="button" className="sidebar-account-button" aria-label="Logout" title="Logout" onClick={accountNavigation.logout}><LogOut size={18} aria-hidden="true"/><span className="sidebar-account-label">Logout</span></button>
    </div>}
  </aside>;
}
