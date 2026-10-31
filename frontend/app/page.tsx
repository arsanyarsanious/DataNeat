import { ThemeToggle } from "@/components/theme-toggle";
import { DataNeatMark } from "@/components/dataneat-mark";
import { ArrowRight, Check, FileSpreadsheet, ShieldCheck, Undo2 } from "lucide-react";

function SampleCorrection({ before, after, step, empty = false }: { before: string; after: string; step: string; empty?: boolean }) {
  return <span className={`cover-correction ${step}`}>
    <span className="cover-value-before" aria-hidden="true">{before}</span>
    <span className={`cover-value-after${empty ? " cover-empty-value" : ""}`} aria-hidden="true">{after}<Check size={12} /></span>
    <span className="cover-screen-reader">{before}, corrected to {after} in this example.</span>
  </span>;
}

export default function WelcomePage() {
  return <main className="welcome-page cover-refresh">
    <header className="welcome-nav"><a href="/" className="welcome-brand" aria-label="DataNeat home"><span className="dataneat-brand-symbol"><DataNeatMark size={38} /></span>DataNeat</a><div className="welcome-nav-actions"><span className="welcome-motto">LESS MESS.</span><ThemeToggle /></div></header>
    <section className="welcome-hero" aria-labelledby="welcome-title">
      <div className="welcome-copy"><p className="welcome-pill"><span />MADE FOR MESSY SPREADSHEETS</p>
        <h1 id="welcome-title">Good data.<br /><em>A fresh start.</em></h1>
        <p className="welcome-description">A calmer way to clean your spreadsheets.<br />See the issues. Choose the fixes.</p>
        <a className="welcome-begin" href="/login">Begin cleaning <ArrowRight size={21} /></a>
        <p className="welcome-note">Works with CSV &amp; Excel</p>
        <div className="cover-promises"><span><ShieldCheck size={16} />Original preserved</span><span><Undo2 size={16} />Undo any change</span></div>
      </div>
      <div className="welcome-art">
        <div className="cover-example-label"><span />A LITTLE CLARITY, IN ACTION</div>
        <div className="welcome-sheet">
          <div className="welcome-sheet-title"><span><FileSpreadsheet size={18} />Quarterly overview.csv</span><span className="cover-sample-badge">Sample</span></div>
          <table className="welcome-table">
            <caption className="cover-screen-reader">Illustrative spreadsheet showing three chosen corrections: spelling, a missing-value label, and a boolean format. You choose the corrections for your own data.</caption>
            <thead><tr><th scope="col" className="cover-row-number">#</th><th scope="col">City</th><th scope="col">Revenue</th><th scope="col">Active</th></tr></thead>
            <tbody><tr><th scope="row" className="cover-row-number">1</th><td>Cairo</td><td>$12,450</td><td>Yes</td></tr>
            <tr><th scope="row" className="cover-row-number">2</th><td><SampleCorrection before="Kairo" after="Cairo" step="cover-step-one" /></td><td>$8,920</td><td>Yes</td></tr>
            <tr><th scope="row" className="cover-row-number">3</th><td>Alexandria</td><td><SampleCorrection before="N/A" after="empty" step="cover-step-two" empty /></td><td>No</td></tr>
            <tr><th scope="row" className="cover-row-number">4</th><td>Giza</td><td>$6,310</td><td><SampleCorrection before="TRUE" after="Yes" step="cover-step-three" /></td></tr>
            <tr><th scope="row" className="cover-row-number">5</th><td>Mansoura</td><td>$9,740</td><td>No</td></tr></tbody>
          </table>
          <div className="cover-sheet-footer"><div className="cover-demo-status" aria-hidden="true"><span className="cover-status-before"><span className="cover-status-dot" />A few small inconsistencies</span><span className="cover-status-after"><Check size={15} />Your choices, applied</span></div><span>5 rows · 3 columns</span></div>
        </div>
        <div className="cover-cleaning-steps" aria-hidden="true"><span className="cover-step-one"><Check size={14} />Spelling</span><span className="cover-step-two"><Check size={14} />Missing labels</span><span className="cover-step-three"><Check size={14} />Formats</span></div>
        <p className="cover-example-note">An example of what you can do. Every correction is your choice.</p>
      </div>
    </section>
    <footer className="welcome-footer"><strong>YOUR DATA. YOUR CONTROL.</strong><div><a href="/privacy">Privacy policy</a><span>Guided corrections</span></div></footer>
  </main>;
}
