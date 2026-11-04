"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Preview, type Profile, type OriginalColorsStatus } from "@/lib/types";
import { DataFormatControls, formatActions, formatActionForType, formatDefaults } from "./data-format-controls";
import { Button } from "./ui/button";
import { Search, History, SlidersHorizontal, CircleHelp, CheckCircle2, Undo2, FileDown, FileSpreadsheet, FileText, GitCompareArrows, ListChecks, ArrowRight, AlertTriangle, WandSparkles, X } from "lucide-react";
import { useContinuousSheet } from "@/lib/use-continuous-sheet";
import { OriginalColorsControl, originalFillStyle } from "./original-colors-control";
import { previewNumber } from "@/lib/preview-format";
import { imputationMethods } from "@/lib/imputation-methods";
import { getImputationReadiness } from "@/lib/imputation-readiness";
import { ImputationReadinessNotice } from "./imputation-controls";
import { CleaningProgress } from "./cleaning-progress";
import { UnifyTextValues } from "./unify-text-values";
import { ColumnSettings } from "./column-settings";
import { DateMedianNotice } from "./date-median-notice";
import { DateOutputFormat } from "./date-output-format";
import { AutomaticCleaning } from "./automatic-cleaning";
import { SheetShortcuts } from "./sheet-shortcuts";
import { WorkflowTools } from "./workflow-tools";
import { QualityWorkbench, qualityTools, type QualityToolId } from "./quality-workbench";
import { QuickCleanReview } from "./quick-clean-review";
import { GuidedCleaning, isMissingIssue, canonicalIssueGroups } from "./guided-cleaning";
import { editorRequest, workflowJob } from "@/lib/workflow";
type CellIssue = { kind: string; message: string; classification?: string };
type Sheet = {
  original_colors?: OriginalColorsStatus;
  preview: Preview & { row_indices: number[]; cell_issues: CellIssue[][][] };
  profile: Profile;
  revision: number;
  workflow_version?: number;
  legacy_notice?: string;
  overview?: {columns:number;cells:number;types:number;flags:number};
  automatic_runs?: string[];
  basic_log: { operation: string; column: string; modified_values: number }[];
  changes: { id?: string; action: string; scope?: string; column: string; changed_cells: number; interpreted_dates?: number }[];
};
type Selection = {
  row: number;
  column: string;
  value: unknown;
  issues: CellIssue[];
  left: number;
  top: number;
};
type Proposal = {
  changed_cells: number;
  interpreted_dates?: number;
  examples: { row_index: number; before: unknown; after: unknown }[];
  warnings: string[];
};
const issueNames: Record<string, string> = {
  cross_column: "Related column rule",
  outlier: "Unusual measurement",
  data_format: "Data format interpretation",
  invalid_data_format: "Invalid data format",
  missing_marker: "Possible missing-value label",
  time: "Clock time format",
  invalid_time: "Invalid clock time",
  duration: "Duration format",
  invalid_duration: "Invalid duration",
  boolean: "Mixed boolean labels",
  odd_value: "Odd value",
  whitespace: "Extra whitespace",
  missing: "Missing value",
  invalid_date: "Invalid date",
  ambiguous_date: "Ambiguous date",
  date_format: "Mixed date formats",
  capitalization: "Capitalization",
  currency: "Currency notation",
  percentage: "Percentage notation",
  symbol: "Unit notation",
  phone: "Phone format",
  type: "Type mismatch",
  email: "Invalid email",
  duplicate: "Duplicate row",
  rule_negative: "Negative value not allowed",
  rule_required: "Required value",
  rule_unique: "Unique value rule",
  rule_allowed: "Allowed values rule",
  rule_pattern: "Text pattern rule",
  rule_type: "Declared type rule",
  rule_range: "Numeric range rule",
  rule_date_range: "Date range rule",
};
const imputationLabels:Record<string,string>={date_sequence:"Date pattern — complete a regular sequence",mode:"Mode — most frequent",mean:"Mean — average",median:"Median — middle value",forward_fill:"Forward fill — previous observation",backward_fill:"Backward fill — next observation",linear_interpolation:"Linear interpolation — between observations",group_forward_fill:"Forward fill within groups",group_backward_fill:"Backward fill within groups"};
const orderedImputation=["date_sequence","forward_fill","backward_fill","linear_interpolation","group_forward_fill","group_backward_fill"];
const colors: Record<string, string> = {
  cross_column: "#ef8792", outlier: "#e6a852",
  data_format: "#53a4dd", invalid_data_format: "#ed6b78",
  missing_marker: "#d5aa67",
  time: "#53a4dd",
  invalid_time: "#ee6677",
  duration: "#53a4dd",
  invalid_duration: "#ee6677",
  boolean: "#a78be5",
  odd_value: "#e06d70",
  whitespace: "#6bc5db",
  missing: "#e4ad35",
  invalid_date: "#ed6b78",
  ambiguous_date: "#ab82ef",
  date_format: "#d79a56",
  capitalization: "#53a4dd",
  currency: "#4abea7",
  percentage: "#d986cc",
  symbol: "#88b964",
  phone: "#eb9b58",
  type: "#9ba1ed",
  email: "#e777a3",
  duplicate: "#879bae",
  rule_negative: "#ed6b78",
  rule_required: "#ed6b78", rule_unique: "#ed6b78", rule_allowed: "#ed6b78", rule_pattern: "#ed6b78", rule_type: "#ed6b78", rule_range: "#ed6b78", rule_date_range: "#ed6b78",
};
const issueKindMap: Record<string, string> = { data_format: "data_format", invalid_data_format: "invalid_data_format", time_format: "time", invalid_time: "invalid_time", duration_format: "duration", invalid_duration: "invalid_duration", missing_marker: "missing_marker", missing_values: "missing", invalid_dates: "invalid_date", ambiguous_dates: "ambiguous_date", date_format_inconsistency: "date_format", case_inconsistency: "capitalization", extra_whitespace: "whitespace", currency_inconsistency: "currency", percentage_inconsistency: "percentage", symbol_inconsistency: "symbol", phone_inconsistency: "phone", invalid_phone: "phone", type_mismatch: "type", odd_value: "odd_value", boolean_inconsistency: "boolean", invalid_email: "email" };
export function InteractiveSheet({ fileId, originalRows, persisted = false, onPhaseChange }: { fileId: string; originalRows:number; persisted?:boolean; onPhaseChange?:(phase:"choose"|"clean"|"impute"|"results")=>void }) {
  const [phase,setPhase]=useState<"choose"|"clean"|"impute"|"results">("choose"),[flowReady,setFlowReady]=useState(false);
  const [drawer,setDrawer]=useState<"issues"|"history"|"tools"|"help"|null>(null),[awaitingAutomatic,setAwaitingAutomatic]=useState(false);
  const [automaticNotes,setAutomaticNotes]=useState<{runId:string;hadSteps:boolean;skipped:string[]}|null>(null);
  const [toolsBusy,setToolsBusy]=useState(false),[activeJob,setActiveJob]=useState<{id:string;status:string;stage:string}|null>(null);
  const flowRef=useRef<HTMLElement>(null);
  useEffect(()=>{try{const saved=sessionStorage.getItem(`dataneat-flow-${fileId}`);if(saved==="clean"||saved==="impute"||saved==="results")setPhase(saved);}catch{}try{const notes=JSON.parse(sessionStorage.getItem(`dataneat-automatic-notes-${fileId}`)||"null");if(notes&&typeof notes.runId==="string"&&Array.isArray(notes.skipped))setAutomaticNotes(notes);}catch{}setFlowReady(true);},[fileId]);
  useEffect(()=>{if(!flowReady)return;try{sessionStorage.setItem(`dataneat-flow-${fileId}`,phase);}catch{}onPhaseChange?.(phase);flowRef.current?.scrollIntoView({block:"start"});flowRef.current?.querySelector<HTMLButtonElement>('nav button[aria-current="step"]')?.focus({preventScroll:true});},[phase,flowReady,fileId,onPhaseChange]);
  function goPhase(next:"choose"|"clean"|"impute"|"results"){setSelection(null);setDrawer(null);setAwaitingAutomatic(false);setPhase(next);}
  function toggleDrawer(next:"issues"|"history"|"tools"|"help"){setSelection(null);setDrawer(current=>current===next?null:next);}
  function beginAutomatic(){goPhase("clean");setAutomaticOpen(true);}

  const [showOriginalColors,setShowOriginalColors]=useState(false);
  const [colorsLoading,setColorsLoading]=useState(false);
  const [colorNotice,setColorNotice]=useState("");
  const [affectedOnly,setAffectedOnly]=useState(false),[filterColumn,setFilterColumn]=useState(""),[filterKind,setFilterKind]=useState("any");
  const [undoing,setUndoing]=useState(false),[historyFeedback,setHistoryFeedback]=useState<{error:boolean;message:string}|null>(null);
  const [manualMode,setManualMode]=useState(false);
  const [scopeCounts,setScopeCounts]=useState<Record<string,number>>({});
  const manualRef=useRef<HTMLDivElement>(null);
  function sheetPath(page:number){return `/files/${fileId}/editor?${new URLSearchParams({page:String(page),affected_only:String(affectedOnly),issue_column:filterColumn,issue_kind:filterKind,original_colors:String(showOriginalColors)})}`;}
  async function filterView(enabled:boolean,column=filterColumn,kind=filterKind){
    setBusy(true);setError("");setSelection(null);
    try{const data=await api<Sheet>(`/files/${fileId}/editor?${new URLSearchParams({page:"1",affected_only:String(enabled),issue_column:column,issue_kind:kind,original_colors:String(showOriginalColors)})}`);setAffectedOnly(enabled);setFilterColumn(column);setFilterKind(kind);setSheet(data);}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const [automaticOpen, setAutomaticOpen] = useState(false);
  const [quickReview,setQuickReview]=useState<"suggested"|"saved"|null>(null),[guidedOpen,setGuidedOpen]=useState(false);
  const [issueColumns,setIssueColumns]=useState<string[]>([]);
  const [qualityTool,setQualityTool]=useState<{tool:QualityToolId;column?:string}|null>(null);
  const [settingsColumn, setSettingsColumn] = useState<string | null>(null);
  const [commaSeparators, setCommaSeparators] = useState(false);
  const [legendVisible, setLegendVisible] = useState(false);
  const [readyExport, setReadyExport] = useState<{download:string;filename:string;revision:number;format:string}|null>(null);
  const [unifyColumn, setUnifyColumn] = useState<string | null>(null);
  const [issueColumn, setIssueColumn] = useState<string | null>(null);
  const [issueKind, setIssueKind] = useState("any");
  const [columnIssueKinds, setColumnIssueKinds] = useState<string[]>([]);
  const [loadingIssueKinds, setLoadingIssueKinds] = useState(false);
  const [issueKindsError, setIssueKindsError] = useState("");
  const [issuePosition, setIssuePosition] = useState(-1);
  const [issueStatus, setIssueStatus] = useState("");
  const [seenIssueKinds, setSeenIssueKinds] = useState<string[]>([]);
  const [allIssueTypesSeen, setAllIssueTypesSeen] = useState(false);
  const [currentIssueKind, setCurrentIssueKind] = useState("");
  const [quickChoice, setQuickChoice] = useState("custom");
  const [moreOptions, setMoreOptions] = useState(false);
  const [affectedCount, setAffectedCount] = useState<number | null>(null);
  const [interpretedDateCount, setInterpretedDateCount] = useState(0);
  const [countError, setCountError] = useState("");
  const [success, setSuccess] = useState<{ message: string; undoId?: string } | null>(null);
  const [scrollTarget,setScrollTarget]=useState<{row:number;token:number}|null>(null);
  const [targetRow, setTargetRow] = useState<number | null>(null);
  const targetRef = useRef<HTMLTableRowElement>(null);
  const [progressLabel, setProgressLabel] = useState("Processing your spreadsheet…");
  const [sheet, setSheet] = useState<Sheet | null>(null),
    [selection, setSelection] = useState<Selection | null>(null);

  useEffect(() => { setSeenIssueKinds([]); setAllIssueTypesSeen(false); setIssuePosition(-1); setIssueStatus(""); }, [issueColumn, issueKind, sheet?.revision]);
  const [orderBy,setOrderBy]=useState(""),[singleEntity,setSingleEntity]=useState(false);
  const [dateRounding,setDateRounding]=useState("floor"),[dateEstimateAck,setDateEstimateAck]=useState(false);
  const [fixWarnings,setFixWarnings]=useState<string[]>([]);
  const [dateOutput,setDateOutput]=useState("YYYY-MM-DD");
  const [action, setAction] = useState("replace"),
    [scope, setScope] = useState("cell"),
    [value, setValue] = useState("");
  const [formatParameters,setFormatParameters]=useState<Record<string,unknown>>({});
  const [datePatternInterpretation,setDatePatternInterpretation]=useState("preserve");
  const [datePatternCoverage,setDatePatternCoverage]=useState(60);
  const [symbol, setSymbol] = useState(""),
    [region, setRegion] = useState(""),
    [format, setFormat] = useState("add"),
    [group, setGroup] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const selectedColumn = sheet?.profile.columns.find(column => column.column_name === selection?.column);
  const imputationReadiness = getImputationReadiness(selectedColumn);
  const replacingEmpty = action === "replace" && value.trim() !== "" && (selection?.value == null || String(selection.value).trim() === "" || (["issue", "issue_columns"].includes(scope) && currentIssueKind === "missing"));
  const fillingMissing = (action === "impute_missing_values" && format !== "preserve") || replacingEmpty;
  const fillColumns = scope === "issue_columns" ? issueColumns : selection ? [selection.column] : [];
  const blockedFillColumns = fillingMissing ? fillColumns.map(name => sheet?.profile.columns.find(column => column.column_name === name)).filter(column => !getImputationReadiness(column).ready) : [];
  const fillBlockingMessage = blockedFillColumns.map(column => getImputationReadiness(column).message).join(" ");
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const colorsActive=showOriginalColors&&sheet?.original_colors?.status==="ready";
  async function toggleOriginalColors(){
    if(showOriginalColors){setShowOriginalColors(false);setColorNotice("");return;}
    setColorsLoading(true);setBusy(true);setError("");setSelection(null);setProgressLabel("Loading original cell colors…");
    try {
      const next=await api<Sheet>(sheetPath(sheet?.preview.page||1).replace("original_colors=false","original_colors=true"));
      setSheet(next);setShowOriginalColors(next.original_colors?.status==="ready");
      setColorNotice(next.original_colors?.message||"Original colors are unavailable.");
    } catch(e){setError((e as Error).message);}finally{setColorsLoading(false);setBusy(false);}
  }
  const stream=useContinuousSheet(sheet?.preview??null,fileId,sheet?.revision??0,affectedOnly,filterColumn,filterKind,scrollTarget,!!colorsActive);
  const [changedVisibleCells,setChangedVisibleCells]=useState<Set<string>>(new Set());
  const visibleSnapshot=useRef<{revision:number;values:Map<string,unknown>}|null>(null);
  const flashTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  useEffect(()=>{
    if(!sheet)return;
    const values=new Map<string,unknown>();
    for(const row of stream.rows)if(row.index!==undefined&&row.values)row.values.forEach((value,index)=>values.set(`${row.index}:${sheet.preview.columns[index]}`,value));
    const previous=visibleSnapshot.current;
    if(previous&&previous.revision!==sheet.revision){
      const changed=new Set([...values.keys()].filter(key=>previous.values.has(key)&&!Object.is(previous.values.get(key),values.get(key))));
      setChangedVisibleCells(changed);
      if(flashTimer.current)clearTimeout(flashTimer.current);
      flashTimer.current=setTimeout(()=>setChangedVisibleCells(new Set()),1600);
    }
    visibleSnapshot.current={revision:sheet.revision,values};
  },[sheet?.revision,stream.rows]);
  useEffect(()=>()=>{if(flashTimer.current)clearTimeout(flashTimer.current);},[]);

  const [shortcut,setShortcut]=useState<"search"|"compare"|"presets"|null>(null);
  const [pendingLeave,setPendingLeave]=useState<{proceed:()=>void}|null>(null);
  useEffect(()=>{const find=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="f"&&phase==="clean"&&!busy&&!toolsBusy&&!automaticOpen&&!settingsColumn&&!unifyColumn&&!qualityTool&&!quickReview&&!pendingLeave){e.preventDefault();if(hoverTimer.current)clearTimeout(hoverTimer.current);setSelection(null);setShortcut("search");}};window.addEventListener("keydown",find);return()=>window.removeEventListener("keydown",find);},[phase,busy,toolsBusy,automaticOpen,settingsColumn,unifyColumn,qualityTool,quickReview,pendingLeave]);
  const allowLeave=useRef(false);
  const [ignoreScope,setIgnoreScope]=useState("cell");
  const [example,setExample]=useState<Proposal["examples"][number]|null>(null);
  const [downloadedRevision,setDownloadedRevision]=useState(-1);
  const requestedColumn=useRef<string|null>(null);
  const lastRevision=useRef<{revision:number;ids:string[]}|null>(null);
  useEffect(()=>{if(!sheet)return;const previous=lastRevision.current;if(previous&&previous.revision!==sheet.revision){setReadyExport(null);const added=sheet.changes.filter(c=>c.id&&!previous.ids.includes(c.id));if(added.length)setSuccess({message:`${added.length} cleaning step${added.length>1?"s":""} recorded. See History for all steps.`,undoId:added.at(-1)?.id});}lastRevision.current={revision:sheet.revision,ids:sheet.changes.map(c=>c.id||"")};},[sheet?.revision]);
  useEffect(()=>{try{setDownloadedRevision(Number(sessionStorage.getItem(`dataneat-downloaded-${fileId}`)??-1));}catch{}},[fileId]);
  useEffect(()=>{const listener=(e:Event)=>{const detail=(e as CustomEvent).detail;if(detail.fileId!==fileId)return;setDownloadedRevision(detail.revision);try{sessionStorage.setItem(`dataneat-downloaded-${fileId}`,String(detail.revision));}catch{}};window.addEventListener("dataneat-data-downloaded",listener);return()=>window.removeEventListener("dataneat-data-downloaded",listener);},[fileId]);
  function markDownloaded(){if(!sheet)return;setDownloadedRevision(sheet.revision);try{sessionStorage.setItem(`dataneat-downloaded-${fileId}`,String(sheet.revision));}catch{}}
  useEffect(()=>{if(!sheet)return;const dirty=!persisted&&sheet.changes.length>0&&sheet.revision!==downloadedRevision;
    const leave=(e:BeforeUnloadEvent)=>{if(!allowLeave.current&&(dirty||busy||toolsBusy)){e.preventDefault();e.returnValue="";}};
    const navigate=(e:MouseEvent)=>{const target=e.target as HTMLElement;const link=target.closest<HTMLAnchorElement>("a[href]");if(!link||link.hasAttribute("download")||link.target==="_blank"||link.getAttribute("href")?.startsWith("#"))return;if(dirty||busy||toolsBusy){e.preventDefault();e.stopPropagation();setPendingLeave({proceed:()=>window.location.assign(link.href)});}};
    const reset=(e:Event)=>{if(dirty||busy||toolsBusy){e.preventDefault();setPendingLeave({proceed:(e as CustomEvent).detail.proceed});}};window.addEventListener("dataneat-before-reset",reset);
    window.addEventListener("beforeunload",leave);document.addEventListener("click",navigate,true);return()=>{window.removeEventListener("dataneat-before-reset",reset);window.removeEventListener("beforeunload",leave);document.removeEventListener("click",navigate,true);};
  },[sheet?.revision,sheet?.changes.length,downloadedRevision,persisted,busy,toolsBusy]);
  useEffect(()=>{if(!requestedColumn.current||!sheet)return;const name=requestedColumn.current;requestedColumn.current=null;requestAnimationFrame(()=>{const headers=flowRef.current?.querySelectorAll<HTMLTableCellElement>(".editor-table th");headers?.[sheet.preview.columns.indexOf(name)+1]?.scrollIntoView({block:"nearest",inline:"center"});});},[sheet,shortcut]);
  async function locate(match:{row_index:number;page:number;column:string}){if(!sheet)return;setBusy(true);setError("");try{if(match.page){setSheet(await api<Sheet>(`/files/${fileId}/editor?page=${match.page}&original_colors=${showOriginalColors}`));setAffectedOnly(false);setFilterColumn("");setFilterKind("any");setTargetRow(match.row_index);setScrollTarget({row:match.row_index,token:Date.now()});}requestedColumn.current=match.column;setShortcut(null);setSelection(null);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function applyPreset(column:string,preset:string){if(!sheet)return;setBusy(true);setError("");try{
    const actions=preset==="text"?[{action:"trim_whitespace",parameters:{}},{action:"normalize_capitalization",parameters:{strategy:"title"}}]:preset==="trim"?[{action:"trim_whitespace",parameters:{}}]:preset==="boolean"?[{action:"normalize_boolean",parameters:{}}]:[{action:"normalize_dates",parameters:{interpretation:"preserve",include_time:false,output_format:"YYYY-MM-DD"}}];
    await workflowJob(fileId,sheet.revision,{operation:"plan",steps:actions.map(a=>({kind:"fix",body:{revision:sheet.revision,column,row_index:sheet.preview.row_indices[0]??0,scope:"column",confirmed:true,...a}}))});
    const updated=await api<Sheet>(sheetPath(stream.visiblePage));setSheet(updated);setShortcut(null);setSuccess({message:`Shortcut applied to ${column}. Every step is in history.`,undoId:updated.changes.at(-1)?.id});
  }finally{setBusy(false);}}


  useEffect(()=>{const listener=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail.fileId===fileId&&detail.status){if(detail.status.operation==="automatic"&&detail.status.status==="completed"&&Array.isArray(detail.status.result?.skipped)){const notes={runId:detail.status.id,hadSteps:!!detail.status.result.operations?.length,skipped:detail.status.result.skipped as string[]};setAutomaticNotes(notes);try{sessionStorage.setItem(`dataneat-automatic-notes-${fileId}`,JSON.stringify(notes));}catch{}}setActiveJob(detail.status);setBusy(["queued","running"].includes(detail.status.status));if(detail.status.stage)setProgressLabel(detail.status.stage);}};window.addEventListener("dataneat-workflow-job",listener);return()=>window.removeEventListener("dataneat-workflow-job",listener);},[fileId]);
  useEffect(()=>{if(!success)return;const timer=setTimeout(()=>setSuccess(null),5000);return()=>clearTimeout(timer);},[success]);
  useEffect(()=>{if(shortcut||automaticOpen||settingsColumn||unifyColumn||qualityTool||quickReview){if(hoverTimer.current)clearTimeout(hoverTimer.current);setSelection(null);setDrawer(null);}},[shortcut,automaticOpen,settingsColumn,unifyColumn,qualityTool,quickReview]);
  useEffect(()=>{if(!selection||busy){setScopeCounts({});return;}const controller=new AbortController();setScopeCounts({});
    void api<Record<string,number>>(`/files/${fileId}/editor/scope-counts?${new URLSearchParams({column:selection.column,row_index:String(selection.row),kind:currentIssueKind})}`,{signal:controller.signal}).then(setScopeCounts).catch(()=>{});
    return()=>controller.abort();
  },[fileId,selection,sheet?.revision,currentIssueKind,busy]);
  useEffect(() => {
    setColumnIssueKinds([]); setIssueKindsError("");
    if (!issueColumn || !sheet) return;
    const controller = new AbortController();
    setLoadingIssueKinds(true);
    api<{ available_kinds: string[] }>(`/files/${fileId}/editor/next-issue?column=${encodeURIComponent(issueColumn)}&distinct_types=true`, { signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      setColumnIssueKinds(data.available_kinds.filter(kind=>!isMissingIssue(kind)));
      setIssueKind(kind => kind === "any" || data.available_kinds.includes(kind) ? kind : "any");
    }).catch(e => { if (!controller.signal.aborted) setIssueKindsError((e as Error).message); }).finally(() => { if (!controller.signal.aborted) setLoadingIssueKinds(false); });
    return () => controller.abort();
  }, [fileId, issueColumn, sheet?.revision]);
  useEffect(() => {
    if (!sheet || !selection || busy) return;
    const controller = new AbortController();
    setAffectedCount(null); setInterpretedDateCount(0); setCountError("");setExample(null);setFixWarnings([]);
    if (fillBlockingMessage) { setCountError(fillBlockingMessage); return; }
    if (["normalize_currency", "normalize_symbols"].includes(action) && format === "add" && !symbol.trim()) {
      setCountError("Enter the symbol or label you want to add.");
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const result = await api<{ proposal: Proposal }>(`/files/${fileId}/editor/fix`, { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal, body: JSON.stringify({ revision: sheet.revision, column: selection.column, row_index: selection.row, scope, action, value: value === "" ? null : value, parameters: parameters(), confirmed: false }) });
        if (!controller.signal.aborted) {setAffectedCount(result.proposal.changed_cells);setInterpretedDateCount(result.proposal.interpreted_dates||0);setExample(result.proposal.examples[0]||null);setFixWarnings(result.proposal.warnings||[]);}
      } catch (e) { if (!controller.signal.aborted) setCountError((e as Error).message); }
    }, 400);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [fileId, selection, sheet?.revision, action, scope, value, format, dateOutput, symbol, region, group, orderBy, singleEntity, dateRounding, datePatternInterpretation, datePatternCoverage, formatParameters, issueColumns, busy, currentIssueKind, fillBlockingMessage]);
  useEffect(() => {
    if (!sheet) return;
    try { sessionStorage.setItem(`dataneat-editor-${fileId}`, JSON.stringify({ page: stream.visiblePage, commaSeparators, column: issueColumn, kind: issueKind })); } catch { /* Storage is optional. */ }
  }, [fileId, stream.visiblePage, commaSeparators, issueColumn, issueKind]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setSheet(null);
    setError("");
    async function prepare() {
      try {
        let saved: { page?: number; commaSeparators?: boolean; column?: string; kind?: string } = {};
        try { saved = JSON.parse(sessionStorage.getItem(`dataneat-editor-${fileId}`) || "{}"); } catch { /* Start fresh if malformed. */ }
        setCommaSeparators(!!saved.commaSeparators);
        setIssueColumn(saved.column || null); setIssueKind(saved.kind || "any");
        const result = await api<Sheet | { status: "processing" }>(
          `/files/${fileId}/workflow/init`,
          { method: "POST", signal: controller.signal },
        );
        if ("preview" in result) {
          const restored = saved.page && saved.page > 1 ? await api<Sheet>(`/files/${fileId}/editor?page=${saved.page}`, { signal: controller.signal }) : result;
          if (active) setSheet(restored);
          return;
        }
        async function poll() {
          if (!active) return;
          try {
            const status = await api<{ status: "processing" | "ready" }>(
              `/files/${fileId}/editor/status`,
              { signal: controller.signal },
            );
            if (status.status === "ready") {
              const ready = await api<Sheet>(`/files/${fileId}/editor?page=${saved.page || 1}`, {
                signal: controller.signal,
              });
              if (active) setSheet(ready);
            } else if (active) timer = setTimeout(poll, 2000);
          } catch (e) {
            if (active) setError((e as Error).message);
          }
        }
        await poll();
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    void prepare();
    return () => {
      active = false;
      controller.abort();
      if (timer) clearTimeout(timer);
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
    };
  }, [fileId]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelection(null);setDrawer(null);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  async function load(page: number) {
    setProgressLabel("Loading spreadsheet page…");
    setBusy(true);
    setError("");
    try {
      setSheet(await api<Sheet>(sheetPath(page)));
      setSelection(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function closeAfterHover() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => setSelection(null), 300);
  }
  function chooseQuick(choice: string, cell = selection, bulk = false, kindOverride?: string) {
    if (!cell) return;
    const kind = kindOverride || cell.issues.find(issue => !["odd_value", "type", "duplicate"].includes(issue.kind))?.kind || cell.issues[0]?.kind || "";
    setDateEstimateAck(false);setDateRounding("floor");setCurrentIssueKind(kind); setQuickChoice(choice); setMoreOptions(false); setProposal(null);setIssueColumns([cell.column]);
    setAffectedCount(null); setCountError("");
    if (choice === "custom") {setAction("replace");setScope(bulk?"issue":"cell");setValue(cell.value==null?"":String(cell.value));return;}
    setAction("replace"); setScope(bulk ? kind === "invalid_date" ? "invalid_dates" : "issue" : "cell"); setValue("");
    if (choice === "data_format") { const next=formatActionForType[sheet?.profile.columns.find(c=>c.column_name===cell.column)?.detected_type||""]||"normalize_number_format";setAction(next);setFormatParameters(formatDefaults(next));setScope(bulk?"column":"cell"); }
    if (choice === "absolute") { setAction("absolute_values"); setScope(bulk ? "column" : "cell"); }
    if (choice === "time") { setAction("normalize_time"); setScope(bulk ? "column" : "cell"); setFormat("24_hour"); }
    if (choice === "duration") { setAction("normalize_duration"); setScope(bulk ? "column" : "cell"); }
    if (choice === "trim") { setAction("trim_whitespace"); setScope(bulk ? "column" : "cell"); }
    if (choice === "boolean") { setAction("normalize_boolean"); setScope("column");setFormat("true_false"); }
    if (choice === "title") { setAction("normalize_capitalization"); setScope("column"); setFormat("title"); }
    if (choice === "dates") { setAction("normalize_dates"); setScope("column"); setFormat("preserve"); }
    if (choice === "duplicates") { setAction("remove_duplicates"); setScope("column"); }
    if (choice in imputationLabels) { setAction("impute_missing_values"); setScope(bulk ? "column" : "cell"); setFormat(choice);setOrderBy(choice==="date_sequence"?"__sheet_order__":"");setSingleEntity(false);setGroup(""); }
    if (choice === "constant") setValue(cell.value == null ? "" : String(cell.value));
  }
  function open(cell: Selection) {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    if (busy||toolsBusy||shortcut||pendingLeave||automaticOpen||settingsColumn||unifyColumn||qualityTool||quickReview) return;
    setSymbol("");setDatePatternInterpretation("preserve");
    setDateEstimateAck(false);setDateRounding("floor");setIgnoreScope("cell");setExample(null);setOrderBy("");setSingleEntity(false);setGroup("");setSelection(cell);setDateOutput("YYYY-MM-DD");
    setMoreOptions(false); setQuickChoice("custom"); setCurrentIssueKind(cell.issues[0]?.kind || "");
    setAction("replace");
    setScope("cell");
    setValue(cell.value == null ? "" : String(cell.value));
    setProposal(null);
    setError("");
    const primary = cell.issues.find(issue => issue.kind === "whitespace")?.kind || cell.issues.find(issue => !["odd_value", "type", "duplicate"].includes(issue.kind))?.kind || cell.issues[0]?.kind;
    const method = primary === "whitespace" ? "trim" : ["data_format","invalid_data_format"].includes(primary||"") ? "data_format" : primary === "rule_negative" ? "absolute" : primary === "time" ? "time" : primary === "duration" ? "duration" : primary === "boolean" ? "boolean" : primary === "capitalization" ? "title" : primary === "date_format" || primary === "ambiguous_date" ? "dates" : primary === "missing" ? "constant" : ["currency", "percentage", "phone", "symbol"].includes(primary || "") ? "custom" : primary === "duplicate" ? "duplicates" : "clear";
    chooseQuick(method, cell, primary === "invalid_date", primary);
  }
  function invalidate() {
    setProposal(null);
    setAffectedCount(null); setCountError("");
  }
  async function resolveMissingMarkers(column:string,convert:boolean){
    if(!sheet||busy)return;
    setBusy(true);setError("");setSelection(null);setProgressLabel(convert?"Converting missing-value labels to empty cells…":"Keeping missing-value labels as text…");
    try{await workflowJob(fileId,sheet.revision,{operation:"decision",decision:{kind:"missing_markers",column,settings:{convert}}});const updated=await api<Sheet>(sheetPath(1));setSheet(updated);if(awaitingAutomatic&&!updated.profile.columns.some(c=>c.missing_marker_review?.count)){setAwaitingAutomatic(false);setDrawer(null);setAutomaticOpen(true);}setSuccess({message:convert?`Missing-value labels in ${column} converted to empty cells.`:`Labels in ${column} are kept as text, not treated as missing.`,undoId:updated.changes.at(-1)?.id});}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function undo(changeId: string, wholeRun=false) {
    if (!sheet || busy) return;
    setUndoing(true);setHistoryFeedback(null);
    setProgressLabel("Undoing step and recalculating later changes…");
    setBusy(true);
    setSelection(null);
    setProposal(null);
    setError("");
    try {
      await workflowJob(fileId, sheet.revision, wholeRun?{operation:"undo_run",run_id:changeId}:{operation:"undo",step_id:changeId});
      setSheet(await api<Sheet>(sheetPath(1)));
      const message=wholeRun?"Automatic cleaning run undone. Later independent changes are preserved.":"Step undone. The sheet and issue counts have been updated.";
      setSuccess({ message });setHistoryFeedback({error:false,message});
    } catch (e) { setHistoryFeedback({error:true,message:(e as Error).message}); }
    finally { setBusy(false);setUndoing(false); }
  }
  async function jumpToIssue(first = false, fixIt = false, requestedColumn = issueColumn, requestedKind = issueKind) {
    if (!sheet || !requestedColumn || busy) return;
    if (isMissingIssue(requestedKind)) {goPhase("impute");return;}
    setDrawer(null);
    setIssueColumn(requestedColumn); setIssueKind(requestedKind);
    setBusy(true);
    setProgressLabel(`Finding ${requestedKind === "any" ? "issues" : issueNames[requestedKind]} · ${requestedColumn}…`);
    setSelection(null);
    setError("");
    try {
      const query = new URLSearchParams({ column: requestedColumn, kind: requestedKind, after: String(first ? -1 : issuePosition), page_size: String(sheet.preview.page_size || 25), distinct_types: "true", seen_kinds: first ? "" : seenIssueKinds.join(",") });
      const found = await api<{ total: number; total_types?: number; all_types_seen?: boolean; new_kinds?: string[]; target: { row_index: number; position: number; page: number } | null }>(`/files/${fileId}/editor/next-issue?${query}`);
      if (!found.target) { setAllIssueTypesSeen(true); setIssueStatus(found.all_types_seen ? "All different issue types have been shown. Use First issue to start again." : "No matching issues in this column."); return; }
      setAffectedOnly(false);setFilterColumn("");setFilterKind("any");
      const nextSheet = await api<Sheet>(`/files/${fileId}/editor?page=${found.target.page}&original_colors=${showOriginalColors}`);
      setSheet(nextSheet);
      const targetKind = found.new_kinds?.[0] || requestedKind;
      if(isMissingIssue(targetKind)){goPhase("impute");return;}
      setCurrentIssueKind(targetKind);
      if (fixIt) {
        const row = nextSheet.preview.row_indices.indexOf(found.target.row_index);
        const columnIndex = nextSheet.preview.columns.indexOf(requestedColumn);
        const cell: Selection = { row: found.target.row_index, column: requestedColumn, value: nextSheet.preview.rows[row][columnIndex], issues: nextSheet.preview.cell_issues[row][columnIndex], left: Math.max(12, Math.min(window.innerWidth - 652, window.innerWidth / 2 - 320)), top: 110 };
        setSelection(cell);
        setDateOutput("YYYY-MM-DD");setGroup("");setOrderBy("");setIgnoreScope("cell");setSymbol("");setIssueColumns([requestedColumn]);
        chooseQuick(targetKind === "whitespace" ? "trim" : ["data_format","invalid_data_format"].includes(targetKind) ? "data_format" : targetKind === "rule_negative" ? "absolute" : targetKind === "time" ? "time" : targetKind === "duration" ? "duration" : targetKind === "boolean" ? "boolean" : targetKind === "capitalization" ? "title" : targetKind === "date_format" || targetKind === "ambiguous_date" ? "dates" : targetKind === "missing" ? "constant" : ["currency", "percentage", "phone", "symbol"].includes(targetKind) ? "custom" : targetKind === "duplicate" ? "duplicates" : "clear", cell, true, targetKind);
      }
      setTargetRow(found.target.row_index);setScrollTarget({row:found.target.row_index,token:Date.now()});
      setIssuePosition(found.target.position);
      const visitedKinds = [...new Set([...(first ? [] : seenIssueKinds), ...(found.new_kinds || [])])];
      setSeenIssueKinds(visitedKinds);
      setAllIssueTypesSeen(visitedKinds.length >= (found.total_types || 0));
      setIssueStatus(`${(found.new_kinds || []).map(kind => issueNames[kind] || kind).join(", ")} · Spreadsheet row ${found.target.row_index + 2} · ${found.total_types} issue types in this column`);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function parameters() {
    if (action in formatActions)return formatParameters;
    if (scope === "issue") return { issue_kind: currentIssueKind };
    if (scope === "issue_columns") return {issue_kind:currentIssueKind,columns:issueColumns};
    if (action === "normalize_dates")
      return { interpretation: format, include_time: false, output_format:dateOutput };
    if (action === "normalize_time") return { format };
    if (action === "normalize_capitalization") return { strategy: format };
    if (action === "normalize_boolean") return {format};
    if (action === "normalize_currency" || action === "normalize_symbols")
      return { action: format, symbol, position: "prefix", grouping: "remove" };
    if (action === "normalize_percentage") return { action: format };
    if (action === "normalize_phone")
      return { action: format, region: region.toUpperCase() };
    if (action === "impute_missing_values")
      return {
        method: format,
        date_rounding:dateRounding,date_estimate_acknowledged:dateEstimateAck,
        group_by: group ? [group] : [],
        ...(orderedImputation.includes(format)?{order_by:orderBy,single_entity:singleEntity}:{}),
        confirmed: true,
        ...(format==="date_sequence"?{date_interpretation:datePatternInterpretation,pattern_min_coverage:datePatternCoverage}:{}),
      };
    return {};
  }
  async function fix(confirmed: boolean) {
    if (!sheet || !selection) return;
    if (fillBlockingMessage) { setCountError(fillBlockingMessage); return; }
    setProgressLabel(`${confirmed ? "Applying" : "Previewing"} ${action.replaceAll("_", " ")} · ${selection.column}…`);
    setBusy(true);
    setError("");
    try {
      const response = await editorRequest<{ proposal: Proposal }>(
        `/files/${fileId}/editor/fix`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            revision: sheet.revision,
            column: selection.column,
            row_index: selection.row,
            scope,
            action,
            value: value === "" ? null : value,
            parameters: parameters(),
            confirmed,
          }),
        },
      );
      if (confirmed) {
        const updated = await api<Sheet>(sheetPath(stream.visiblePage));
        setSheet(updated);
        const remaining = updated.profile.columns.reduce((sum, column) => sum + column.issues.length, 0);
        setSuccess({ message: `${response.proposal.changed_cells} ${action === "remove_duplicates" ? "rows" : response.proposal.changed_cells === 1 ? "cell" : "cells"} changed${response.proposal.interpreted_dates ? ` · ${response.proposal.interpreted_dates} date interpretations confirmed` : ""} · ${remaining} column issue categories remain.`, undoId: updated.changes.at(-1)?.id });
        setSelection(null);
        setProposal(null);
      } else {
        setProposal(response.proposal);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!sheet)
    return (
      <section className="panel">
        <div className="panel-body">
          {error ? (
            <p role="alert">{error}</p>
          ) : (
            <><CleaningProgress label="Preparing your original spreadsheet preview…" /><div className="sheet-skeleton" aria-hidden="true">{Array.from({length:6},(_,i)=><div key={i}><i/><i/><i/><i/></div>)}</div></>
          )}
        </div>
      </section>
    );
  const available = selection
    ? Array.from(new Set(selection.issues.map((i) => i.kind)))
    : [];
  const summaryMap = new Map<string, { kind: string; count: number; column: string }>();
  for (const column of sheet.profile.columns) for (const issue of column.issues) {
    const kind = issueKindMap[issue.issue] || (issue.issue.startsWith("rule_") ? issue.issue : "");
    if (!kind || (phase==="clean" && isMissingIssue(kind))) continue;
    const previous = summaryMap.get(kind);
    summaryMap.set(kind, { kind, count: (previous?.count || 0) + issue.count, column: previous?.column || column.column_name });
  }
  if (sheet.profile.duplicate_rows) summaryMap.set("duplicate", { kind: "duplicate", count: sheet.profile.duplicate_rows, column: sheet.preview.columns[0] });
  const issueSummary = [...summaryMap.values()].sort((a, b) => b.count - a.count);
  const dateMedian=action==="impute_missing_values"&&["median","group_median"].includes(format)&&["date","datetime"].includes(sheet.profile.columns.find(c=>c.column_name===selection?.column)?.detected_type||"");
  const matchingIssueColumns=selection?canonicalIssueGroups(sheet.profile).filter(item=>item.kind===currentIssueKind&&sheet.profile.columns.find(column=>column.column_name===item.column)?.detected_type!=="identifier"&&sheet.profile.columns.find(column=>column.column_name===item.column)?.intent?.type!=="identifier"):[];
  const blockingMessage=fillBlockingMessage||countError||(dateMedian&&!dateEstimateAck?"Confirm that an estimated date is appropriate before applying this change.":quickChoice==="constant"&&!value.trim()?"Enter a replacement value before applying this change.":"");
  const noPendingChange=affectedCount===0&&interpretedDateCount===0;
  const hasRecordedDataChanges=sheet.changes.some(change=>change.changed_cells>0);
  const originalColorsControl=sheet.original_colors?.supported?<OriginalColorsControl enabled={!!colorsActive} busy={colorsLoading} disabled={busy||toolsBusy} message={sheet.original_colors.message} onToggle={()=>void toggleOriginalColors()}/>:null;
  const cleaningGroups=canonicalIssueGroups(sheet.profile).filter(item=>!isMissingIssue(item.kind));
  const exploreColumns=sheet.preview.columns.slice(0,5);
  const exploreRows=sheet.preview.rows.slice(0,4);
  return (
    <section ref={flowRef} className={`interactive-editor calm-workspace flow-${phase}${drawer&&phase==="clean"?" has-drawer":""}`} aria-label="Interactive spreadsheet editor" aria-busy={busy||toolsBusy}>
      {phase!=="results"&&colorNotice&&!colorsActive&&<p className="original-colors-note" role="status">{colorNotice}</p>}
      {phase!=="results"&&colorsActive&&<div className="original-colors-note"><span>{sheet.original_colors?.has_colors===false?"No original solid fills found.":"Original colors shown. Warning icons and colored edges mark issues."}</span><details><summary>Display &amp; export limits</summary><p>{sheet.original_colors?.limitations.join(" ")}</p></details></div>}
      <nav className="cleaning-journey" aria-label="Cleaning stages">
        <div className="journey-step journey-step-complete"><span className="journey-step-number" aria-hidden="true"><CheckCircle2 size={17}/></span><span className="journey-step-label">Upload<small className="journey-step-status">Complete</small></span></div>
        {([["choose","Explore",2],["clean","Clean",3],["impute","Imputation",4],["results","Export",5]] as const).map(([step,label,number])=><button className="journey-step" key={step} type="button" aria-current={phase===step?"step":undefined} disabled={busy||toolsBusy} onClick={()=>goPhase(step)}><span className="journey-step-number" aria-hidden="true">{number}</span><span className="journey-step-label">{label}</span></button>)}
      </nav>
      <section className="method-choice" aria-label="Choose a cleaning method" hidden={phase!=="choose"}>
        <section className="explore-preview-card" aria-label="Data preview and metrics">
          <header className="explore-preview-heading"><div><span className="eyebrow">YOUR UPLOADED DATA</span><h3>Data preview &amp; metrics</h3></div><p>Current working copy · {exploreRows.length} rows and {exploreColumns.length} columns shown</p>{originalColorsControl}</header>
          <div className="explore-preview-content">
            <div className="explore-preview-table-wrap" role="region" aria-label="Current spreadsheet preview" tabIndex={0}>
              <table className="explore-preview-table" aria-label="Preview of your uploaded spreadsheet"><thead><tr><th scope="col">#</th>{exploreColumns.map(column=><th key={column} scope="col" title={column}>{column}</th>)}</tr></thead><tbody>{exploreRows.length?exploreRows.map((row,index)=><tr key={sheet.preview.row_indices[index]??index}><th scope="row">{(sheet.preview.row_indices[index]??index)+2}</th>{exploreColumns.map((column,columnIndex)=><td key={column} className={colorsActive?"source-fill-cell":undefined} style={colorsActive?{...originalFillStyle(sheet.preview.original_fills?.[index]?.[columnIndex]),borderLeft:sheet.preview.cell_issues[index]?.[columnIndex]?.length?`4px solid ${colors[sheet.preview.cell_issues[index][columnIndex][0].kind]||"#ed6b78"}`:undefined}:undefined} title={row[columnIndex]==null?"Empty cell":String(row[columnIndex])}>{colorsActive&&!!sheet.preview.cell_issues[index]?.[columnIndex]?.length&&<AlertTriangle size={14} className="source-color-warning" aria-label="Cleaning issue"/>}{row[columnIndex]==null||row[columnIndex]===""?<em>empty</em>:previewNumber(row[columnIndex],sheet.profile.columns.find(item=>item.column_name===column)?.detected_type||"",commaSeparators)}</td>)}</tr>):<tr><td colSpan={exploreColumns.length+1}>This spreadsheet has no data rows.</td></tr>}</tbody></table>
            </div>
            <dl className="explore-preview-metrics"><div><dt>Rows</dt><dd>{sheet.profile.rows.toLocaleString()}</dd></div><div><dt>Columns</dt><dd>{sheet.profile.columns_count.toLocaleString()}</dd></div><div><dt>Missing cells</dt><dd>{sheet.profile.missing_count.toLocaleString()}</dd></div><div><dt>Cells to review</dt><dd>{sheet.overview?sheet.overview.cells.toLocaleString():"—"}</dd></div></dl>
          </div>
        </section>
        <h2>How would you like to clean your data?</h2><p>{originalRows.toLocaleString()} rows · {sheet.profile.columns_count} columns · Your original is preserved.</p>
        <div className="cleaning-paths"><div><span className="recommended-path">Recommended</span><h3>Review fixes together</h3><p>Choose a correction once for each type of issue, preview the changes, then apply them together.</p><Button disabled={busy||toolsBusy} onClick={()=>{goPhase("clean");setQuickReview("suggested");}}>Review suggested fixes</Button><Button variant="ghost" disabled={busy||toolsBusy} onClick={beginAutomatic}>Clean automatically</Button></div><div><h3>Interactive cleaning</h3><p>Follow one issue at a time, or explore the spreadsheet yourself.</p><Button disabled={busy||toolsBusy} onClick={()=>{goPhase("clean");setGuidedOpen(true);}}>Guided cleaning</Button><Button variant="outline" disabled={busy||toolsBusy} onClick={()=>goPhase("clean")}>Clean manually</Button></div></div>
      </section>
{phase==="impute"&&<section className="imputation-phase panel"><h2>Missing value imputation</h2>{cleaningGroups.length>0&&<p role="alert">Finish reviewing the {cleaningGroups.length} remaining column or row issues in Clean before filling empty cells.</p>}<p>Review missing values and the distribution of the observed data before choosing an estimate. You can also leave cells empty.</p>
       {sheet.profile.columns.some(c=>c.missing_marker_review?.count)&&<section className="marker-review panel" aria-label="Review possible missing-value labels"><strong>Should these labels become empty cells?</strong><p>Text such as NA, null and empty is kept as written until you choose. Actual blank cells are already empty.</p><details><summary>Review labels in {sheet.profile.columns.filter(c=>c.missing_marker_review?.count).length} columns</summary>{sheet.profile.columns.filter(c=>c.missing_marker_review?.count).map(column=><div className="marker-review-column" key={column.column_name}><strong>{column.column_name}</strong><span>{column.missing_marker_review!.count} cells · {column.missing_marker_review!.examples.join(", ")}</span><Button size="sm" disabled={busy} onClick={()=>void resolveMissingMarkers(column.column_name,true)}>Convert labels to empty</Button><Button size="sm" variant="outline" disabled={busy} onClick={()=>void resolveMissingMarkers(column.column_name,false)}>Keep as text</Button></div>)}</details></section>}
 {sheet.profile.columns.filter(c=>c.missing_count>0).map(c=>{
 const recommendation=c.imputation, numeric=recommendation?.statistics?.numeric, ready=getImputationReadiness(c);
 return <article className="panel" key={c.column_name}><h3>{c.column_name}</h3><p>{c.missing_count} missing · {c.missing_percentage}% of this column</p>
 {numeric&&<p>Mean {numeric.mean?.toFixed(2)} · Median {numeric.median?.toFixed(2)} · Standard deviation {numeric.std?.toFixed(2)} · Possible outliers {numeric.outlier_count} · Skewness {numeric.skewness?.toFixed(2)}</p>}
 <p>{recommendation?.explanation}</p>{recommendation?.warnings?.map((w,i)=><p key={i}>{w}</p>)}{!ready.ready&&<p role="alert">{ready.message}</p>}
 <Button disabled={busy||!ready.ready||!!cleaningGroups.length} onClick={()=>setSettingsColumn(c.column_name)}>Choose imputation method</Button>
 {numeric&&<Button variant="outline" onClick={()=>setQualityTool({tool:"outliers",column:c.column_name})}>Analyze outliers</Button>}
 {["integer","decimal","numeric","float"].includes(c.detected_type)&&<Button variant="outline" disabled={!ready.ready||!!cleaningGroups.length} onClick={()=>setQualityTool({tool:"model_imputation",column:c.column_name})}>KNN or iterative imputation</Button>}</article>})}
 {!sheet.profile.missing_count&&<p>No empty cells to fill.</p>}
 <Button variant="outline" onClick={()=>goPhase("clean")}>Back to cleaning</Button> <Button onClick={()=>goPhase("results")}>Review &amp; export</Button></section>}
      <div className="sheet-toolbar" hidden={phase!=="clean"}>
        <div className="ribbon-heading"><span className="ribbon-title">Workbook tools</span>
        <div className="ribbon-heading-actions">
        <Button className="ribbon-quick-review" size="sm" disabled={busy||toolsBusy} onClick={()=>setQuickReview("suggested")}><WandSparkles size={15} aria-hidden="true"/>Review suggested fixes</Button>
        <button className="overview-button" disabled={busy} onClick={()=>toggleDrawer("issues")} aria-label="Open issue overview">{sheet.overview?.columns??sheet.profile.columns.filter(c=>c.issues.length).length} columns to review · {sheet.overview?.types??issueSummary.length} issue types · {sheet.changes.length} steps</button>
        <Button className="ribbon-automatic" size="sm" variant="outline" disabled={busy||toolsBusy} title="Open the automatic cleaning survey for your current spreadsheet" onClick={beginAutomatic}><WandSparkles size={15} aria-hidden="true"/>Automatic cleaning</Button>
        </div>
        </div>
        <div className="sheet-toolbar-actions" aria-label="Spreadsheet tools">
          {originalColorsControl&&<div className="ribbon-group" role="group" aria-label="Original cell colors"><div className="ribbon-group-buttons">{originalColorsControl}</div><span className="ribbon-group-label">Appearance</span></div>}
          <div className="ribbon-group" role="group" aria-label="Explore spreadsheet"><div className="ribbon-group-buttons"><Button size="sm" variant="ghost" disabled={busy||toolsBusy} onClick={()=>{setSelection(null);setShortcut("search");}}><Search size={16} aria-hidden="true"/>Search</Button><Button size="sm" variant="ghost" disabled={busy||toolsBusy||!hasRecordedDataChanges} title={hasRecordedDataChanges?"Compare the original upload with your current copy":"Apply a cleaning change before comparing before and after"} onClick={()=>{setSelection(null);setShortcut("compare");}}><GitCompareArrows size={16} aria-hidden="true"/>Before & after</Button></div><span className="ribbon-group-label">Explore</span></div>
          <div className="ribbon-group" role="group" aria-label="Clean and review"><div className="ribbon-group-buttons">{(["issues","history","tools"] as const).map(panel=><Button key={panel} size="sm" variant="ghost" aria-pressed={drawer===panel} onClick={()=>toggleDrawer(panel)}>{panel==="history"?<History size={16} aria-hidden="true"/>:panel==="tools"?<SlidersHorizontal size={16} aria-hidden="true"/>:<ListChecks size={16} aria-hidden="true"/>}{panel[0].toUpperCase()+panel.slice(1)}</Button>)}</div><span className="ribbon-group-label">Clean & review</span></div>
          <div className="ribbon-group" role="group" aria-label="Simpler cleaning"><div className="ribbon-group-buttons"><Button size="sm" variant="ghost" disabled={busy||toolsBusy} aria-pressed={guidedOpen} onClick={()=>{setSelection(null);setDrawer(null);setGuidedOpen(open=>!open);}}><ArrowRight size={16} aria-hidden="true"/>Guided cleaning</Button><Button size="sm" variant="ghost" disabled={busy||toolsBusy} onClick={()=>setQuickReview("saved")}>Saved choices</Button></div><span className="ribbon-group-label">Fewer steps</span></div>
          <div className="ribbon-group" role="group" aria-label="Help"><div className="ribbon-group-buttons"><Button size="sm" variant="ghost" aria-pressed={drawer==="help"} onClick={()=>toggleDrawer("help")}><CircleHelp size={16} aria-hidden="true"/>Help & legend</Button></div><span className="ribbon-group-label">Guide</span></div>
          <div className="ribbon-group ribbon-finish" role="group" aria-label="Export spreadsheet"><div className="ribbon-group-buttons"><Button size="sm" disabled={busy||toolsBusy} onClick={()=>goPhase("impute")}><FileDown size={16} aria-hidden="true"/>Continue to imputation</Button></div><span className="ribbon-group-label">Finish</span></div>
        </div>
      </div>
      {pendingLeave&&<div className="shortcut-backdrop"><section className="shortcut-dialog panel" role="dialog" aria-modal="true" aria-label="Download before leaving"><h2>Before you leave</h2><p>{busy||toolsBusy?"A task is still running. Your latest completed changes may not have been downloaded.":"Your latest changes have not been downloaded as Excel or CSV."}</p><div className="shortcut-actions"><Button onClick={()=>{setPendingLeave(null);goPhase("results");}}>Stay and download</Button><Button variant="outline" onClick={()=>setPendingLeave(null)}>Keep cleaning</Button><Button variant="ghost" onClick={()=>{allowLeave.current=true;pendingLeave.proceed();setPendingLeave(null);}}>Leave anyway</Button></div></section></div>}
      {shortcut&&<SheetShortcuts key={shortcut} mode={shortcut} fileId={fileId} profile={sheet.profile} revision={sheet.revision} busy={busy||toolsBusy} onClose={()=>setShortcut(null)} onLocate={locate} onPreset={applyPreset}/>}
      <div className="workspace-job-slot">{(busy||toolsBusy)?<div className="workspace-job-status" role="status"><CleaningProgress label={activeJob&&["queued","running"].includes(activeJob.status)?activeJob.stage:progressLabel}/>{activeJob&&["queued","running"].includes(activeJob.status)&&<Button size="sm" variant="outline" onClick={()=>api(`/workflow-jobs/${activeJob.id}/cancel`,{method:"POST"}).catch(e=>setError(e.message))}>Cancel job</Button>}{toolsBusy&&<Button size="sm" variant="outline" onClick={()=>{setPhase("clean");setDrawer("tools");}}>View tools task</Button>}</div>:success&&<div className="cleaning-success" role="status"><CheckCircle2 size={18} aria-hidden="true"/><span>{success.message}</span>{success.undoId && <Button variant="outline" disabled={busy} onClick={() => undo(success.undoId!)}><Undo2 size={15} aria-hidden="true"/>Undo last change</Button>}<button className="icon-button" aria-label="Dismiss success message" onClick={() => setSuccess(null)}>×</button></div>}</div>
      {error&&!selection&&<div className="error workspace-persistent-error" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={()=>setError("")}>×</button></div>}
      {historyFeedback?.error&&drawer!=="history"&&<div className="error" role="alert">{historyFeedback.message}<Button variant="ghost" size="sm" onClick={()=>{setPhase("clean");setDrawer("history");}}>View history</Button></div>}
      {automaticOpen && <AutomaticCleaning fileId={fileId} revision={sheet.revision} profile={sheet.profile} onClose={() => setAutomaticOpen(false)} onApplied={async () => {setSelection(null);setAffectedOnly(false);setFilterColumn("");setFilterKind("any");const updated=await api<Sheet>(`/files/${fileId}/editor?page=1&original_colors=${showOriginalColors}`);setSheet(updated);setSuccess({message:"Automatic cleaning finished. Undo the whole run in History.",undoId:updated.changes.at(-1)?.id});}} onReview={()=>{setAutomaticOpen(false);goPhase("clean");setDrawer("issues");void filterView(true,"","any");}} onDownload={async()=>{const result=await workflowJob<{download:string;filename:string}>(fileId,sheet.revision,{operation:"export",format:"xlsx"});const link=document.createElement("a");link.href=result.download;link.download=result.filename;link.click();markDownloaded();}} />}
      {settingsColumn && <ColumnSettings imputation={phase==="impute"} fileId={fileId} revision={sheet.revision} profile={sheet.profile} initialColumn={settingsColumn} onClose={() => setSettingsColumn(null)} onChanged={async () => { setSelection(null); setIssueColumn(null); setAffectedOnly(false);setFilterColumn("");setFilterKind("any"); setSheet(await api<Sheet>(`/files/${fileId}/editor?page=1&original_colors=${showOriginalColors}`)); }} />}
      {qualityTool&&<QualityWorkbench imputation={phase==="impute"} fileId={fileId} revision={sheet.revision} profile={sheet.profile} initialTool={qualityTool.tool} initialColumn={qualityTool.column} onClose={()=>setQualityTool(null)} onBusyChange={setToolsBusy} onChanged={async()=>{setSelection(null);setIssueColumn(null);setSheet(await api<Sheet>(sheetPath(1)));}}/>}
      {quickReview&&<QuickCleanReview fileId={fileId} revision={sheet.revision} profile={sheet.profile} initialTab={quickReview} onClose={()=>setQuickReview(null)} onBusyChange={setToolsBusy} onApplied={async()=>{setSelection(null);setIssueColumn(null);setAffectedOnly(false);setFilterColumn("");setFilterKind("any");setSheet(await api<Sheet>(`/files/${fileId}/editor?page=1&original_colors=${showOriginalColors}`));}} onGuided={()=>{setQuickReview(null);goPhase("clean");setGuidedOpen(true);}} onFinish={()=>{setQuickReview(null);goPhase("impute");}}/>}
      {unifyColumn && <UnifyTextValues key={unifyColumn} fileId={fileId} column={unifyColumn} onClose={() => setUnifyColumn(null)} onApplied={async count => { const updated = await api<Sheet>(sheetPath(stream.visiblePage)); setSheet(updated); setSuccess({ message: `${count} cells unified in ${unifyColumn}.`, undoId: updated.changes.at(-1)?.id }); }} />}

      <div className="workspace-sheet" hidden={phase!=="clean"}>
      <GuidedCleaning fileId={fileId} revision={sheet.revision} profile={sheet.profile} open={guidedOpen&&phase==="clean"} busy={busy||toolsBusy} onFix={async item=>{await jumpToIssue(true,true,item.column,item.kind);}} onClose={()=>setGuidedOpen(false)} onFinish={()=>goPhase("impute")} onQuickReview={()=>setQuickReview("suggested")} onTool={(tool,column)=>setQualityTool({tool:tool==="outliers"?"outliers":"cross_column",column})}/>
      {!guidedOpen&&<div className="next-suggestion"><span>{issueSummary.length?`${sheet.overview?.types??issueSummary.length} issue types remain. Review them together or follow Guided cleaning.`:"No detected issues remain. Your current copy is ready to review and download."}</span><Button size="sm" variant="ghost" disabled={busy||toolsBusy} onClick={()=>issueSummary.length?setGuidedOpen(true):goPhase("impute")}>{issueSummary.length?"Guide me":"Continue to imputation"}</Button></div>}
      <div className="panel editor-sheet-panel">
      {stream.rows.some(row=>row.imputed?.some(Boolean)) && <small className="imputed-estimate-note">Dotted underlines mark estimated (imputed) values, not verified observations.</small>}
        {issueColumn && <div className="issue-navigation" aria-label="Column issue navigation">
          <strong>{issueColumn} · Find issues in this column</strong>
          <select aria-label="Issue type to find" value={issueKind} disabled={busy || loadingIssueKinds || !!issueKindsError || columnIssueKinds.length === 0} onChange={e => { setIssueKind(e.target.value); setIssuePosition(-1); setIssueStatus(""); }}><option value="any">All issue types</option>{columnIssueKinds.map(kind => <option key={kind} value={kind}>{issueNames[kind] || kind}</option>)}</select>
          <Button variant="outline" disabled={busy || loadingIssueKinds || !!issueKindsError || columnIssueKinds.length === 0} onClick={() => jumpToIssue(true)}>First issue</Button><Button variant="outline" disabled={busy || loadingIssueKinds || !!issueKindsError || columnIssueKinds.length === 0 || allIssueTypesSeen} onClick={() => jumpToIssue()}>Next Issue</Button>
          <Button disabled={busy || loadingIssueKinds || !!issueKindsError || columnIssueKinds.length === 0 || (!currentIssueKind && issueKind === "any")} onClick={() => jumpToIssue(true, true, issueColumn, issueKind === "any" ? currentIssueKind : issueKind)}>Fix this issue</Button>
          <small role="status">{loadingIssueKinds ? "Loading issues in this column…" : issueKindsError || (columnIssueKinds.length === 0 ? "No issues detected in this column." : issueStatus || "Choose a type and jump directly to its affected cells.")}</small>
        </div>}
        <div ref={stream.viewport} onScroll={()=>{if(stream.onScroll()){if(hoverTimer.current)clearTimeout(hoverTimer.current);setSelection(null);}}} className="table-scroll editor-table-scroll continuous-table-scroll" tabIndex={0} aria-label="Scrollable spreadsheet">
          <table className="editor-table" aria-rowcount={sheet.preview.total_rows+1}>
            <thead>
              <tr>
                <th>#</th>
                {sheet.preview.columns.map((c) => (
                  <th key={c} className={(selection?.column||issueColumn)===c?"is-active-column":undefined}><span className="sheet-column-name">{c}</span><button type="button" className="column-issue-button" disabled={busy} aria-label={`Settings for ${c}`} onClick={() => { setSelection(null); setSettingsColumn(c); }} title={`Settings for ${c}`}>⋯</button><button type="button" className="column-issue-button" disabled={busy} aria-label={`Find issues in ${c}`} onClick={() => { setIssueColumn(c); setIssueKind("any"); setIssuePosition(-1); setIssueStatus(""); }}>{sheet.profile.columns.find(column => column.column_name === c)?.issues.reduce((sum, issue) => sum + issue.count, 0) || 0} issues</button>{["text", "category"].includes(sheet.profile.columns.find(column => column.column_name === c)?.detected_type || "") && <button type="button" className="column-issue-button column-unify-shortcut" disabled={busy} onClick={() => { setSelection(null); setUnifyColumn(c); }}>Unify text values</button>}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stream.topSpace>0&&<tr aria-hidden="true" className="virtual-spacer"><td colSpan={sheet.preview.columns.length+1} style={{height:stream.topSpace}}/></tr>}
              {stream.rows.map(item => !item.values||item.index===undefined||!item.issues?<tr key={`loading-${item.position}`} className="virtual-data-row" aria-rowindex={item.position+2}><td>{affectedOnly?"…":item.position+2}</td><td colSpan={sheet.preview.columns.length} className="virtual-loading">Loading rows…</td></tr>:(
                <tr key={item.index} aria-rowindex={item.position+2} ref={item.index === targetRow ? targetRef : undefined} className={`virtual-data-row${item.index===targetRow?" issue-target-row":""}`}>
                  <td>{item.index + 2}</td>
                  {item.values.map((v, c) => {
                    const kind = sheet.profile.columns.find((column) => column.column_name === sheet.preview.columns[c])?.detected_type || "";
                    const displayed = previewNumber(v, kind, commaSeparators);
                    const issues = item.issues![c].filter(issue=>!isMissingIssue(issue.kind));
                    function cell(element: HTMLElement): Selection {
                      const rect = element.getBoundingClientRect();
                      const width = Math.min(640, window.innerWidth - 24);
                      return {
                        row: item.index!,
                        column: sheet!.preview.columns[c],
                        value: v,
                        issues,
                        left:
                          rect.right + width + 12 < window.innerWidth
                            ? rect.right + 8
                            : Math.max(12, rect.left - width - 8),
                        top: Math.max(
                          12,
                          Math.min(rect.top, window.innerHeight - Math.min(window.innerHeight * 0.75, 600) - 12),
                        ),
                      };
                    }
                    return (
                      <td
                        key={c}
                        className={[colorsActive ? "source-fill-cell" : "", item.imputed?.[c] ? "imputed-estimate" : "", changedVisibleCells.has(`${item.index}:${sheet.preview.columns[c]}`) ? "cell-just-changed" : ""].filter(Boolean).join(" ") || undefined}
                        title={item.imputed?.[c] ? "Imputed estimate — not a verified observation" : undefined}
                        style={
                          colorsActive ? originalFillStyle(item.originalFills?.[c]) : issues.length
                            ? { background: `color-mix(in srgb, ${colors[issues[0].kind] || "#ed6b78"} 8%, var(--surface))` }
                            : undefined
                        }
                      >
                        {issues.length ? (
                          <button
                            className="issue-cell"
                            aria-label={`Issues in ${sheet.preview.columns[c]} row ${item.index! + 2}: ${issues.map((i) => issueNames[i.kind]).join(", ")}`}
                            onMouseEnter={(e) => {
                              if (hoverTimer.current)
                                clearTimeout(hoverTimer.current);
                              const selected = cell(e.currentTarget);
                              hoverTimer.current = setTimeout(
                                () => open(selected),
                                180,
                              );
                            }}
                            onMouseLeave={closeAfterHover}
                            onClick={(e) => open(cell(e.currentTarget))}
                            onFocus={(e) => open(cell(e.currentTarget))}
                          >
                            <span className="cell-color-markers">
                              {issues.map((i, n) => (
                                <i
                                  key={n}
                                  style={{ background: colors[i.kind] }}
                                  title={issueNames[i.kind]}
                                />
                              ))}
                            </span>
                            {colorsActive&&<AlertTriangle size={14} className="source-color-warning" aria-hidden="true"/>}
                            {v == null || v === "" ? <em>empty</em> : displayed}
                          </button>
                        ) : v == null || v === "" ? (
                          <em>empty</em>
                        ) : (
                          displayed
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {stream.bottomSpace>0&&<tr aria-hidden="true" className="virtual-spacer"><td colSpan={sheet.preview.columns.length+1} style={{height:stream.bottomSpace}}/></tr>}
            </tbody>
          </table>
        </div>
        <div className="table-footer"><span>{sheet.preview.total_rows.toLocaleString()} {affectedOnly?"affected rows":"rows"} · Scroll to explore</span>{stream.error&&<div role="alert">{stream.error}<Button size="sm" variant="outline" onClick={stream.retry}>Retry loading rows</Button></div>}</div>
      </div>
      </div>
      <aside className="workspace-drawer" aria-label="Workspace side panel" hidden={phase!=="clean"||!drawer}>
        <header className="workspace-drawer-heading"><h2>{drawer==="issues"?"Issues & filters":drawer==="history"?"Cleaning history":drawer==="tools"?"Tools":"Help & legend"}</h2><Button variant="ghost" size="sm" aria-label="Close side panel" onClick={()=>setDrawer(null)}>×</Button></header>
        <div hidden={drawer!=="issues"}>
          {awaitingAutomatic&&<div className="notice automatic-review-notice"><p>Review possible missing-value labels before automatic cleaning.</p><Button size="sm" disabled={busy} onClick={()=>{setAwaitingAutomatic(false);setDrawer(null);setAutomaticOpen(true);}}>Continue to automatic cleaning</Button><small>Unresolved columns stay unchanged.</small></div>}

      <div className="affected-row-tools" ref={manualRef}>
        {manualMode&&<p>Manual cleaning: click an issue type or a highlighted cell to choose a correction.</p>}
        <label><input type="checkbox" disabled={busy} checked={affectedOnly} onChange={e=>void filterView(e.target.checked)}/> Show affected rows only</label>
        <label>Column<select aria-label="Affected rows column" disabled={busy} value={filterColumn} onChange={e=>void filterView(true,e.target.value,"any")}><option value="">All columns</option>{sheet.preview.columns.map(c=><option key={c} value={c}>{c}</option>)}</select></label>
        <label>Issue type<select aria-label="Affected rows issue type" disabled={busy} value={filterKind} onChange={e=>void filterView(true,filterColumn,e.target.value)}><option value="any">All issue types</option>{issueSummary.filter(item=>!filterColumn||sheet.profile.columns.find(c=>c.column_name===filterColumn)?.issues.some(issue=>(issueKindMap[issue.issue]||issue.issue)===item.kind)||item.kind==="duplicate").map(item=><option key={item.kind} value={item.kind}>{issueNames[item.kind]||item.kind}</option>)}</select></label>
        {affectedOnly&&<Button variant="ghost" disabled={busy} onClick={()=>void filterView(false,"","any")}>Show all rows</Button>}
      </div>
      <div className="issue-summary" aria-label="Whole file issue summary"><strong>Across your whole file</strong><small>Counts are issue flags; one cell can have more than one. Click a type to find it, or Fix to open its correction.</small><div>{issueSummary.length ? issueSummary.map(item => <span className="issue-summary-chip" key={item.kind}><button disabled={busy} onClick={() => jumpToIssue(true, false, item.column, item.kind)}>{issueNames[item.kind]}: {item.count}</button><button disabled={busy} aria-label={`Fix ${issueNames[item.kind]}`} title={`Fix this issue in ${item.column}`} onClick={() => jumpToIssue(true, true, item.column, item.kind)}>Fix</button></span>) : <span>No issues detected by the current checks.</span>}</div></div>
        </div>
        <div hidden={drawer!=="history"}>
      <section className="cleaning-history panel" aria-label="Cleaning history">
        <h3>Cleaning history</h3>
        {undoing&&<p role="status">{progressLabel}</p>}
        {historyFeedback&&<p role={historyFeedback.error?"alert":"status"} className={historyFeedback.error?"error":""}>{historyFeedback.message}</p>}
        <div className="history-actions"><Button size="sm" variant="outline" disabled={busy||!sheet.changes.at(-1)?.id} onClick={()=>{const id=sheet.changes.at(-1)?.id;if(id)void undo(id);}}>Undo last action</Button><Button size="sm" variant="outline" disabled={busy||!sheet.automatic_runs?.length} onClick={()=>{const id=sheet.automatic_runs?.at(-1);if(id)void undo(id,true);}}>Undo automatic cleaning run</Button></div>
        <p>Undo removes a step and recalculates later steps. Your original is preserved.</p>
        {!sheet.changes.length && <p>No confirmed changes yet.</p>}
        <ol>{sheet.changes.map((change, index) => <li key={change.id || index}><details className="history-step"><summary><span className="history-step-number" aria-hidden="true">{index+1}</span><span><strong>{change.scope === "values" ? "Unify text values" : change.action.replaceAll("_", " ")}</strong><small>{change.column} · {change.changed_cells.toLocaleString()} {change.action==="remove_duplicates"?"rows":"cells"}{change.interpreted_dates?` · ${change.interpreted_dates} dates confirmed`:""}</small></span></summary><div className="history-step-details"><p>Step {index+1} · {change.column}</p><p>Scope: {change.scope?.replaceAll("_"," ")||"column"}</p><p>{change.changed_cells.toLocaleString()} {change.action==="remove_duplicates"?"rows removed":"cells changed"}.{change.interpreted_dates?` Interpretation confirmed for ${change.interpreted_dates} dates.`:""} Use the undo button to remove this step and recalculate later steps.</p></div></details><button type="button" disabled={busy || !change.id} aria-label={`Undo step ${index + 1}: ${change.action.replaceAll("_", " ")}`} title={change.id ? "Undo this step" : "This older step predates undo support"} onClick={() => change.id && undo(change.id)}><Undo2 size={15} aria-hidden="true"/></button></li>)}</ol>
        <small>Preparation and cleaning decisions are recorded here.</small>
      </section>
        </div>
        <div hidden={drawer!=="tools"}>
          <Button variant="outline" disabled={busy} onClick={beginAutomatic}>Automatic cleaning survey</Button>
          <section className="quality-launchers" aria-label="Additional cleaning tools"><h3>More cleaning tools</h3>{qualityTools.filter(tool=>tool.id!=="model_imputation").map(tool=><button type="button" key={tool.id} disabled={busy||toolsBusy} onClick={()=>setQualityTool({tool:tool.id,column:issueColumn||undefined})}><strong>{tool.title}</strong><small>{tool.description}</small></button>)}</section>
      <div className="column-tools-bar"><Button variant="outline" disabled={busy || !sheet.preview.columns.length} onClick={() => { setSelection(null); setSettingsColumn(issueColumn || sheet.preview.columns[0]); }}>Column settings &amp; insights</Button><small>More options for the same working copy</small></div>

          <Button variant="outline" disabled={busy||toolsBusy} onClick={()=>{setDrawer(null);setShortcut("presets");}}>Ready-made shortcuts</Button><label className="setting">Unify text values in<select aria-label="Unify text column" value={unifyColumn||""} disabled={busy} onChange={e=>{if(e.target.value){setSelection(null);setUnifyColumn(e.target.value);}}}><option value="">Choose a text column…</option>{sheet.profile.columns.filter(c=>["text","category","categorical"].includes(c.detected_type)).map(c=><option key={c.column_name} value={c.column_name}>{c.column_name}</option>)}</select></label>
      <WorkflowTools fileId={fileId} revision={sheet.revision} columns={sheet.preview.columns} onBusyChange={setToolsBusy} onError={setError} onChanged={async () => { setSelection(null); setSheet(await api<Sheet>(sheetPath(stream.visiblePage))); }} />
        </div>
        <div hidden={drawer!=="help"}>
      <aside className="automatic-preparation-note"><strong>Preparation:</strong> Changes require your approval. Automatic cleaning and individual decisions appear in cleaning history and can be undone. Your original file is preserved.</aside>
      <div className="editor-bottom-controls">
      <div className="notice">
        Preparation is configurable and reviewed before application. Your original file is preserved.
      </div>
      {sheet.basic_log.length > 0 && <details className="panel editor-basic-log">
        <summary>
          Basic cleanup report (
          {sheet.basic_log.reduce((sum, l) => sum + l.modified_values, 0)}{" "}
          changes)
        </summary>
        {sheet.basic_log
          .filter((l) => l.modified_values)
          .map((l, i) => (
            <p key={i}>
              {l.column}: {l.operation.replaceAll("_", " ")} ·{" "}
              {l.modified_values} values
            </p>
          ))}
      </details>}
      <button type="button" className="button outline" aria-expanded={legendVisible} aria-controls="issue-color-legend" onClick={() => setLegendVisible(visible => !visible)}>Legend</button>
      <div id="issue-color-legend" className="issue-legend" aria-label="Issue color legend" hidden={!legendVisible}>
        {Object.entries(issueNames).map(([kind, name]) => (
          <span key={kind}>
            <i style={{ background: colors[kind] }} />
            {name}
          </span>
        ))}
      </div>
      <p>
        Hover, click, or focus a highlighted cell to see its issues and fix
        choices. Multiple issues have multiple color markers. The affected count is calculated automatically; data changes only when you click Apply change.
      </p>
      <label className="preview-format-option">
        <input type="checkbox" checked={commaSeparators} onChange={(e) => setCommaSeparators(e.target.checked)} />
        Show comma separators in numeric columns (preview only)
      </label>
      </div>
        </div>
      </aside>
      <section className="flow-results" aria-label="Review and export" hidden={phase!=="results"}>
        <div className="cleaning-finish-card" role="status"><CheckCircle2 size={26} aria-hidden="true"/><div><h2>{(sheet.overview?.cells??0)===0?"Ready to download":"Your selected cleaning is complete"}</h2><p>{(sheet.overview?.cells??0)===0?"No issues are detected by the current checks. Review the recorded changes, then download your current copy.":`${(sheet.overview?.cells??0).toLocaleString()} cells still have review flags. You can review them or download your current copy now.`}</p></div></div>
        <div className="results-metrics"><div><strong>{sheet.profile.rows.toLocaleString()}</strong><span>rows in the current file</span></div><div><strong>{sheet.changes.length}</strong><span>recorded steps</span></div><div><strong>{sheet.overview?.cells??0}</strong><span>cells still flagged for review</span></div><div><strong>{Math.max(0,originalRows-sheet.profile.rows).toLocaleString()}</strong><span>rows removed</span></div></div>
        <details className="result-details"><summary>What changed ({sheet.changes.length} steps)</summary>{sheet.changes.length?<ol>{sheet.changes.map((change,index)=><li key={change.id||index}>{change.action.replaceAll("_"," ")} · {change.column} · {change.changed_cells} cells / rows</li>)}</ol>:<p>No cleaning decisions have been applied.</p>}<Button size="sm" variant="outline" onClick={()=>{goPhase("clean");setDrawer("history");}}>Open history & undo</Button></details>
        <details className="result-details"><summary>What still needs attention ({sheet.overview?.cells??0} cells)</summary>{issueSummary.length?<ul>{issueSummary.map(item=><li key={item.kind}><Button variant="ghost" size="sm" disabled={busy} onClick={()=>{goPhase("clean");setDrawer("issues");void jumpToIssue(true,false,item.column,item.kind);}}>{issueNames[item.kind]||item.kind}: {item.count} flags</Button></li>)}</ul>:<p>No issues detected by the current checks.</p>}<Button size="sm" variant="outline" disabled={busy} onClick={()=>{goPhase("clean");setDrawer("issues");void filterView(true,"","any");}}>Review remaining issues</Button></details>
        <details className="result-details"><summary>What was kept unchanged and why</summary><p>All cells and rows outside recorded decisions remain as they were. Your original upload is preserved.</p>{automaticNotes&&(!automaticNotes.hadSteps||sheet.automatic_runs?.includes(automaticNotes.runId))&&automaticNotes.skipped.length>0&&<><strong>Kept during the latest automatic cleaning run</strong><ul>{automaticNotes.skipped.map((note,index)=><li key={index}>{note}</li>)}</ul></>}<ul>{sheet.profile.columns.filter(c=>c.missing_marker_review?.count).map(c=><li key={c.column_name}>{c.column_name}: possible missing-value labels remain as text until you choose.</li>)}</ul>{sheet.legacy_notice&&<p>{sheet.legacy_notice}</p>}<Button size="sm" variant="outline" onClick={()=>{goPhase("clean");setDrawer("tools");}}>Detailed audit & export tools</Button></details>
        <div className="result-downloads"><div className="download-section-heading"><div><h3>Take your work with you</h3><p>Choose your cleaned data or a readable record of the changes.</p></div><span className="download-revision">{sheet.changes.length} confirmed actions · Revision {sheet.revision}</span></div>
      <div className="download-format-cards">
        {([
          {format:"xlsx",extension:".XLSX",title:"Excel workbook",description:"Your current cleaned table, ready to open in Excel.",Icon:FileSpreadsheet},
          {format:"csv",extension:".CSV",title:"CSV data",description:"A plain text table for analysis and other data tools.",Icon:FileText},
          {format:"report",extension:".PDF",title:"Cleaning report",description:"A readable document of the recorded cleaning steps.",Icon:ListChecks},
        ]).map(({format,extension,title,description,Icon})=><article key={format} className={`download-format-card download-format-${format}`} aria-label={title}>
          <div className="download-format-top"><span className="download-format-icon"><Icon size={24} aria-hidden="true"/></span><span className="download-extension">{extension}</span></div><h4>{title}</h4><p>{description}</p>
          <div className="download-format-actions"><Button variant="outline" disabled={busy} onClick={async () => { setBusy(true); setError(""); setReadyExport(null); try { const result = await workflowJob<{download:string;filename:string}>(fileId,sheet.revision,{operation:"export",format});setReadyExport({...result,revision:sheet.revision,format}); } catch(e) {setError((e as Error).message);} finally {setBusy(false);} }}><FileDown size={15} aria-hidden="true"/>Prepare {format === "report" ? "PDF report" : format.toUpperCase()}</Button>
          {readyExport?.format===format&&<a className="button primary" href={readyExport.download} download onClick={()=>{if(readyExport.revision===sheet.revision&&/\.(csv|xlsx)$/i.test(readyExport.filename))markDownloaded();}}><CheckCircle2 size={15} aria-hidden="true"/><span>Download {readyExport.filename}</span></a>}</div>
        </article>)}
      </div>
        </div><Button variant="outline" disabled={busy||toolsBusy} onClick={()=>goPhase("clean")}>Back to spreadsheet</Button>
      </section>
      {selection && (
        <div
          role="dialog"
          aria-label={`Fix ${selection.column} row ${selection.row + 2}`}
          key={JSON.stringify([selection.column, selection.row])}
          className="cell-fix-panel"
          style={{ width:"min(640px, calc(100vw - 24px))", maxWidth:"calc(100vw - 24px)", left: selection.left, top: selection.top }}
          onMouseEnter={() => {
            if (hoverTimer.current) clearTimeout(hoverTimer.current);
          }}
          onMouseLeave={closeAfterHover}
        >
          <div className="panel-heading">
            <h3>
              {selection.column} · Row {selection.row + 2}
            </h3>
            <Button
              variant="ghost"
              onClick={() => {
                setSelection(null);
              }}
            >
              Close
            </Button>
          </div>
          <div className="panel-body">
            <ul>
              {selection.issues.filter(issue => issue.kind === currentIssueKind).slice(0, 1).map((i, n) => (
                <li key={n}>
                  <strong>{issueNames[i.kind]}:</strong> {i.message}
                  {i.classification && <small className="finding-classification">{i.classification === "review" ? "Review suggestion — may be valid" : i.classification === "inconsistency" ? "Inconsistent representation" : "Invalid under the current check or rule"}</small>}
                </li>
              ))}
            </ul>
            {["cross_column","outlier"].includes(currentIssueKind)&&<Button variant="outline" disabled={busy} onClick={()=>setQualityTool({tool:currentIssueKind==="cross_column"?"cross_column":"outliers",column:selection.column})}>Open {currentIssueKind==="cross_column"?"related column rules":"outlier review"}</Button>}
            {currentIssueKind==="missing"&&!imputationReadiness.ready&&<><ImputationReadinessNotice column={selectedColumn}/><Button variant="outline" disabled={busy} onClick={()=>void jumpToIssue(true,true,selection.column,imputationReadiness.blocking_issues[0]?.kind||"any")}>Review other issues in this column</Button></>}
            {currentIssueKind==="missing"&&["integer","decimal"].includes(selectedColumn?.detected_type||"")&&<Button variant="outline" disabled={busy||!imputationReadiness.ready} onClick={()=>setQualityTool({tool:"model_imputation",column:selection.column})}>Use KNN or Iterative imputation</Button>}
            {currentIssueKind === "missing_marker" ? <div className="marker-cell-choice"><p>Apply your choice to NA, null, empty and other recognized missing-value labels across this column. Actual blank cells stay empty.</p><Button disabled={busy} onClick={()=>void resolveMissingMarkers(selection.column,true)}>Convert labels to empty</Button><Button variant="outline" disabled={busy} onClick={()=>void resolveMissingMarkers(selection.column,false)}>Keep as text</Button></div> : <>
            {example&&<div className="correction-comparison" aria-label={`Correction example, row ${example.row_index+2}`}><div><small>Before · row {example.row_index+2}</small><span>{example.before==null||example.before===""?"(empty)":String(example.before)}</span></div><ArrowRight size={17} aria-hidden="true"/><div><small>After</small><strong>{example.after==null||example.after===""?"(empty)":String(example.after)}</strong></div></div>}
            <div className="recommended-correction"><small>{quickChoice==="clear"||quickChoice==="constant"||quickChoice==="custom"?"Your correction":"Suggested correction"}</small><strong>{({trim:"Trim extra whitespace",boolean:"Standardize boolean labels",title:"Standardize capitalization: Title",dates:"Standardize unambiguous dates",time:"Standardize clock time",duration:"Standardize duration",duplicates:"Remove full duplicate rows",absolute:"Remove the minus sign",clear:"Clear affected cells",constant:"Replace with one value",custom:"Review and choose a correction",data_format:"Interpret this data format"} as Record<string,string>)[quickChoice]||imputationLabels[quickChoice]||quickChoice.replaceAll("_"," ")}</strong><Button size="sm" variant="ghost" disabled={busy} onClick={()=>{setMoreOptions(open=>!open);}}>Change correction</Button></div>
            {action==="normalize_boolean"&&<label className="setting">Boolean labels<select aria-label="Boolean output format" value={format} disabled={busy} onChange={e=>{setFormat(e.target.value);invalidate();}}><option value="true_false">true / false</option><option value="yes_no">Yes / No</option><option value="one_zero">1 / 0</option></select></label>}
            <details open={moreOptions} onToggle={e => setMoreOptions(e.currentTarget.open)} className="cell-more-options"><summary>More options</summary>
            <label className="setting">Choose a correction<select aria-label="Quick correction" disabled={busy} value={quickChoice} onChange={e => chooseQuick(e.target.value, selection, scope !== "cell", currentIssueKind)}>
              {available.some(kind=>["data_format","invalid_data_format"].includes(kind)) && <option value="data_format">Interpret / standardize this data format</option>}
              {available.includes("rule_negative") && <option value="absolute">Remove minus sign (make positive)</option>}
              {available.includes("whitespace") && <option value="trim">Trim extra whitespace</option>}
              {currentIssueKind !== "whitespace" && <><option value="clear">{currentIssueKind === "invalid_date" ? "Clear invalid dates" : "Clear affected cells"}</option><option value="constant">Replace with one value</option></>}
              {(available.includes("time") || sheet.profile.columns.find(c=>c.column_name===selection.column)?.detected_type==="time") && <option value="time">Standardize clock time</option>}
              {available.includes("duration") && <option value="duration">Standardize duration: HH:MM:SS</option>}
              {available.includes("boolean") && <option value="boolean">Standardize to true/false</option>}
              {available.includes("capitalization") && <option value="title">Standardize capitalization: Title</option>}
              {(available.includes("date_format") || available.includes("ambiguous_date")) && <option value="dates">Standardize dates (keep ambiguous dates)</option>}
              {available.includes("duplicate") && <option value="duplicates">Remove duplicate rows</option>}
              {available.includes("missing") && imputationMethods(sheet.profile.columns.find(column=>column.column_name===selection.column)?.imputation?.available_methods||[]).filter(method=>method in imputationLabels&&(method!=="linear_interpolation"||!["currency","percentage","number_with_symbol"].includes(sheet.profile.columns.find(c=>c.column_name===selection.column)?.detected_type||""))).map(method=><option key={method} disabled={!imputationReadiness.ready} value={method}>Fill missing cells: {imputationLabels[method]}</option>)}
              <option value="custom">Custom settings</option>
            </select></label>
            
            {quickChoice === "constant" && moreOptions && <label className="setting">Replacement value<input aria-label="Replacement value" value={value} disabled={busy} onChange={e => { setValue(e.target.value); invalidate(); }} placeholder="Enter one value for the affected cells" /></label>}
            {action === "absolute_values" && <p>Example: −5 becomes 5. Only choose this if the magnitude is correct. Positive values, zeros and unrecognized text remain unchanged.</p>}
            {quickChoice === "duration" && <p>PT45M and 45 min become 00:45:00. You can apply this to the cell or all recognized durations in the column. Invalid values stay unchanged; durations over 24 hours do not wrap.</p>}
            {quickChoice === "trim" && <p className="cell-trim-note">Trim leading / trailing spaces and collapse repeated internal whitespace. The text itself is retained.</p>}
            <ul>{selection.issues.filter(issue => issue.kind !== currentIssueKind).map(issue => <li key={issue.kind}><strong>{issueNames[issue.kind]}:</strong> {issue.message}</li>)}</ul>
            <label className="setting">
              Fix option
              <select
                aria-label="Cell fix option"
                disabled={busy}
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  if(e.target.value in formatActions){setFormatParameters(formatDefaults(e.target.value));if(e.target.value==="expand_structured")setScope("column");}
                  if (["normalize_currency", "normalize_symbols"].includes(e.target.value)) setSymbol("");
                  setQuickChoice("custom"); setMoreOptions(true);
                  setScope(e.target.value==="expand_structured"?"column":"cell");
                  if (e.target.value === "normalize_boolean") setScope("column");
                  if (e.target.value === "remove_duplicates")
                    setScope("column");
                  setFormat(
                    e.target.value === "normalize_boolean" ? "true_false" : e.target.value === "normalize_time" ? "24_hour" : e.target.value === "normalize_dates"
                      ? "preserve"
                      : e.target.value === "normalize_capitalization"
                        ? "title"
                        : e.target.value === "impute_missing_values"
                          ? "mode"
                          : e.target.value === "normalize_phone"
                            ? "international"
                            : "add",
                  );
                  invalidate();
                }}
              >
                {Object.entries(formatActions).map(([value,label])=><option key={value} value={value}>{label}</option>)}
                <option value="replace">
                  Enter a corrected value / clear cell
                </option>
                {sheet.profile.columns.find(c=>c.column_name===selection.column)?.detected_type==="time" && <option value="normalize_time">Standardize clock time (12 / 24 hour)</option>}
                {available.includes("rule_negative") && <option value="absolute_values">Remove minus sign (make positive)</option>}
                {available.includes("duration") && <option value="normalize_duration">Standardize duration to HH:MM:SS</option>}
                {available.includes("boolean") && <option value="normalize_boolean">Standardize boolean labels to true/false</option>}
                {available.includes("whitespace") && (
                  <option value="trim_whitespace">Trim extra whitespace</option>
                )}
                {(available.includes("ambiguous_date") || available.includes("date_format")) && (
                  <option value="normalize_dates">
                    Standardize date format / interpretation
                  </option>
                )}
                {available.includes("capitalization") && (
                  <option value="normalize_capitalization">
                    Standardize capitalization
                  </option>
                )}
                {available.includes("currency") && (
                  <option value="normalize_currency">
                    Standardize currency notation
                  </option>
                )}
                {available.includes("percentage") && (
                  <option value="normalize_percentage">
                    Include or remove %
                  </option>
                )}
                {available.includes("symbol") && (
                  <option value="normalize_symbols">
                    Standardize unit notation
                  </option>
                )}
                {available.includes("phone") && (
                  <option value="normalize_phone">
                    Standardize phone format
                  </option>
                )}
                {available.includes("type") && (
                  <option value="normalize_boolean">
                    Recognized boolean labels
                  </option>
                )}
                {available.includes("missing") && (
                  <option value="impute_missing_values" disabled={!imputationReadiness.ready}>
                    Fill missing cells with an estimate
                  </option>
                )}
                {available.includes("duplicate") && (
                  <option value="remove_duplicates">
                    Remove full duplicate rows (dataset)
                  </option>
                )}
              </select>
            </label>
            {action === "replace" && (
              <label className="setting">
                Corrected value
                <input
                  aria-label="Corrected cell value"
                  value={value}
                  disabled={busy}
                  onChange={(e) => {
                    setValue(e.target.value);
                    invalidate();
                  }}
                />
                <small>
                  Leave blank to clear. Matching values are case-sensitive and include the whole column. Use Apply change to replace matching values across this column. You can undo the step from Cleaning history.
                </small>
              </label>
            )}
            {action !== "replace" &&
              action !== "remove_duplicates" &&
              action !== "normalize_boolean" &&
              action !== "trim_whitespace" &&
              action !== "normalize_duration" &&
              action !== "normalize_time" &&
              action !== "absolute_values" &&
              !(action in formatActions) && (
                <label className="setting">
                  {action === "normalize_dates" ? "Interpret ambiguous input dates" : "Desired format"}
                  <select
                    aria-label="Cell fix format"
                    value={format}
                    disabled={busy}
                    onChange={(e) => {
                      setFormat(e.target.value);setOrderBy(e.target.value==="date_sequence"?"__sheet_order__":"");setSingleEntity(false);setDateEstimateAck(false);
                      setQuickChoice("custom"); setMoreOptions(true);
                      invalidate();
                    }}
                  >
                    {(action === "normalize_dates"
                      ? ["preserve", "day_first", "month_first"]
                      : action === "normalize_capitalization"
                        ? ["title", "upper", "lower"]
                        : action === "impute_missing_values"
                          ? imputationMethods(sheet.profile.columns.find(c=>c.column_name===selection.column)?.imputation?.available_methods||[]).filter(method=>method in imputationLabels&&(method!=="linear_interpolation"||!["currency","percentage","number_with_symbol"].includes(sheet.profile.columns.find(c=>c.column_name===selection.column)?.detected_type||"")))
                          : action === "normalize_phone"
                            ? [
                                "international",
                                "international_digits",
                                "national",
                                "remove_plus",
                                "add_plus",
                              ]
                            : ["add", "remove"]
                    ).map((f) => (
                      <option key={f} value={f}>
                        {action === "normalize_capitalization" ? ({ title: "Title", upper: "UPPER", lower: "lower" } as Record<string, string>)[f] : action === "impute_missing_values" ? imputationLabels[f] : f.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            {(action === "normalize_currency" ||
              action === "normalize_symbols") &&
              format === "add" && (
                <label className="setting">
                  Symbol
                  <input
                    aria-label="Cell currency symbol"
                    disabled={busy}
                    value={symbol}
                    onChange={(e) => {
                      setSymbol(e.target.value);
                      invalidate();
                    }}
                  />
                </label>
              )}
            {action === "normalize_phone" && (
              <label className="setting">
                Country (ISO code)
                <input
                  aria-label="Cell phone country"
                  disabled={busy}
                  maxLength={2}
                  placeholder="EG, US, GB…"
                  value={region}
                  onChange={(e) => {
                    setRegion(e.target.value);
                    invalidate();
                  }}
                />
              </label>
            )}
            </details>
            {quickChoice === "constant" && !moreOptions && <label className="setting">Replacement value<input aria-label="Replacement value" value={value} disabled={busy} onChange={e=>{setValue(e.target.value);invalidate();}} placeholder="Enter one value for the affected cells"/></label>}
            {action === "impute_missing_values" && (
              <label className="setting">
                {format.startsWith("group_")?"Group by (required)":"Group by (optional)"}
                <select
                  aria-label="Cell imputation group"
                  disabled={busy}
                  value={group}
                  onChange={(e) => {
                    setGroup(e.target.value);if(e.target.value===orderBy)setOrderBy("");
                    invalidate();
                  }}
                >
                  <option value="">Whole column</option>
                  {sheet.preview.columns
                    .filter((c) => c !== selection.column)
                    .map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                </select>
              </label>
            )}
            {dateMedian&&<DateMedianNotice rounding={dateRounding} acknowledged={dateEstimateAck} disabled={busy} onRounding={v=>{setDateRounding(v);invalidate();}} onAcknowledge={setDateEstimateAck}/>}
            {action === "impute_missing_values" && orderedImputation.includes(format) && <div className="ordered-imputation"><label className="setting">Order observations by<select aria-label="Imputation ordering column" value={orderBy} disabled={busy} onChange={e=>{setOrderBy(e.target.value);invalidate();}}><option value="">Choose a numeric or ISO date column…</option>{format==="date_sequence"&&<option value="__sheet_order__">Current sheet row order</option>}{sheet.preview.columns.filter(c=>c!==selection.column&&c!==group).map(c=><option key={c}>{c}</option>)}</select></label>{!group&&<label className="preview-format-option"><input type="checkbox" checked={singleEntity} disabled={busy} onChange={e=>{setSingleEntity(e.target.checked);invalidate();}}/>These rows form one related sequence</label>}<small>Uses ascending order without rearranging the sheet. Order values must be unique within each group. Only gaps between observed values are filled; leading/trailing gaps stay empty.{format==="date_sequence"?" Detects regular day/hour/week intervals and calendar month/year patterns from at least three original observations. The step follows ordered row positions; mixed patterns are left unchanged.":format.includes("backward")?" Backward fill uses a later observation.":format==="linear_interpolation"?" Interpolation uses the spacing between numeric or date coordinates.":" Forward fill carries an earlier observation."}</small></div>}
            {action==="impute_missing_values"&&format==="date_sequence"&&<label className="setting">Interpret input dates<select aria-label="Date pattern interpretation" value={datePatternInterpretation} disabled={busy} onChange={e=>{setDatePatternInterpretation(e.target.value);invalidate();}}><option value="preserve">Keep known formats; block ambiguous dates</option><option value="day_first">Day / month / year</option><option value="month_first">Month / day / year</option></select><small>Choose grouping columns for separate sequences. Filled dates remain marked as estimates.</small></label>}
            {action==="impute_missing_values"&&format==="date_sequence"&&<label className="setting">Minimum original-date coverage<select aria-label="Minimum date pattern coverage" value={datePatternCoverage} disabled={busy} onChange={e=>{setDatePatternCoverage(Number(e.target.value));invalidate();}}>{[50,60,75,90,100].map(value=><option key={value} value={value}>{value}% of rows in each sequence</option>)}</select><small>At least this share of rows must have original observed dates, with a minimum of 3. Every original date must match the same pattern; previous estimates do not count.</small></label>}
            {action === "normalize_dates" && <DateOutputFormat value={dateOutput} disabled={busy} onChange={value=>{setDateOutput(value);invalidate();}} />}
            {action === "normalize_time" && <label className="setting">Clock format<select aria-label="Clock output format" value={format} disabled={busy} onChange={e=>{setFormat(e.target.value);invalidate();}}><option value="24_hour">24-hour · 14:30:00</option><option value="12_hour">12-hour · 02:30:00 PM</option></select><small>Midnight is 12:00 AM; noon is 12:00 PM. Invalid times remain unchanged.</small></label>}
            {action in formatActions&&<DataFormatControls action={action} parameters={formatParameters} disabled={busy} onChange={p=>{setFormatParameters(p);invalidate();}}/>}
            <div className="explicit-fix-scopes" role="group" aria-label="Apply correction to">
             <strong>Where should this correction apply?</strong>
             {(action==="replace"?[{key:"cell",label:"This cell"},{key:"issue",label:"Same issue in this column"}]:action==="expand_structured"?[{key:"column",label:"Expand this column (keep original)"}]:action==="remove_duplicates"?[{key:"column",label:"Duplicate rows in this dataset"}]:[{key:"cell",label:"This cell"},{key:"column",label:"Eligible cells in this column"}]).map(option=><button type="button" key={option.key} disabled={busy||(option.key==="issue"&&!currentIssueKind)} aria-pressed={scope===option.key||(scope==="invalid_dates"&&option.key==="issue")} onClick={()=>{setScope(option.key);invalidate();}}>{option.label}<small>{scopeCounts[option.key]??"…"} targeted {option.key==="column"?"rows":"cells"}</small></button>)}
            </div>
            {action==="replace"&&<details className="scope-more-options" open={scope==="matching"||scope==="issue_columns"?true:undefined}><summary>More scope options</summary><div className="explicit-fix-scopes"><button type="button" disabled={busy} aria-pressed={scope==="matching"} onClick={()=>{setScope("matching");invalidate();}}>Same value in this column<small>{scopeCounts.matching??"…"} targeted cells</small></button>{matchingIssueColumns.length>1&&<button type="button" disabled={busy} aria-pressed={scope==="issue_columns"} onClick={()=>{setScope("issue_columns");setIssueColumns(matchingIssueColumns.map(item=>item.column));invalidate();}}>This issue in selected columns<small>One correction for {matchingIssueColumns.length} eligible columns</small></button>}</div>{scope==="issue_columns"&&<fieldset className="issue-column-choices" disabled={busy}><legend>Choose the affected columns</legend>{matchingIssueColumns.map(item=><label key={item.column}><input type="checkbox" checked={issueColumns.includes(item.column)} disabled={item.column===selection.column} onChange={e=>{setIssueColumns(columns=>e.target.checked?[...columns,item.column]:columns.filter(name=>name!==item.column));invalidate();}}/>{item.column} · {item.count} flags</label>)}<small>Only cells with {issueNames[currentIssueKind]||currentIssueKind} in these columns receive this replacement. Review the combined affected count before applying.</small></fieldset>}</details>}
            {scope === "column" && quickChoice !== "custom" && ["normalize_boolean", "normalize_capitalization", "normalize_dates"].includes(action) && <small>Applies to this whole column. Other columns stay unchanged.</small>}
            {fixWarnings.length>0&&<details className="imputation-calculation-notes"><summary>Calculation notes ({fixWarnings.length})</summary><ul>{fixWarnings.map((warning,i)=><li key={i}>{warning}</li>)}</ul></details>}
            {!blockingMessage&&<div className="affected-count" role="status">{affectedCount === null ? "Calculating affected cells…" : `Will change ${affectedCount} ${action === "remove_duplicates" ? affectedCount === 1 ? "row" : "rows" : affectedCount === 1 ? "cell" : "cells"} in ${selection.column}.${interpretedDateCount ? ` Confirm ${interpretedDateCount} date interpretations${affectedCount===0?" without changing the displayed values":""}.` : ""}`}</div>}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            </>}
            <details className="accept-finding"><summary>This value is correct</summary><p>Accept this finding without changing the data. Other checks still apply.</p><label className="setting">Accept for<select aria-label="Accept finding for" value={ignoreScope} onChange={e=>setIgnoreScope(e.target.value)}><option value="cell">This cell only</option><option value="matching">This value in this column</option><option value="column">This issue throughout this column</option></select></label><Button variant="outline" disabled={busy||!currentIssueKind} onClick={async () => { setBusy(true);setError(""); try { await workflowJob(fileId, sheet.revision, {operation:"decision",decision:{kind:"ignore",column:selection.column,issue:currentIssueKind,row_index:ignoreScope==="cell"?selection.row:null,value:ignoreScope==="column"?null:selection.value==null?null:String(selection.value),reason:"Reviewed and accepted by user"}}); setSelection(null);const updated=await api<Sheet>(sheetPath(stream.visiblePage));setSheet(updated);setSuccess({message:"Finding accepted. No data changed; you can undo this decision.",undoId:updated.changes.at(-1)?.id}); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }}>Accept as correct</Button></details>
            <div className="advanced-cell-link"><button className="advanced-settings-link" disabled={busy} onClick={() => { setSettingsColumn(selection.column); setSelection(null); }}>More column settings</button></div>
          {currentIssueKind !== "missing_marker" && <div className="cell-fix-footer">
            {blockingMessage&&<div id="cell-fix-blocking-error" className="blocking-action-error" role="alert"><AlertTriangle size={18} aria-hidden="true"/><div><strong>Cannot apply this change</strong><p>{blockingMessage}</p></div></div>}
            {!blockingMessage&&noPendingChange&&<p id="cell-fix-no-change" className="no-pending-change" role="status">No changes to apply. {action==="normalize_dates"?"Dates already in the selected format stay unchanged. Invalid or unconfirmed ambiguous dates are left unchanged.":"The selected cells already match this correction."}</p>}
            {!blockingMessage&&affectedCount===0&&interpretedDateCount>0&&<p id="cell-fix-date-confirmation" className="date-confirmation-summary" role="status">Confirm {format.replaceAll("_"," ")} for {interpretedDateCount} {interpretedDateCount===1?"date":"dates"}. The displayed values stay the same.</p>}
            <Button aria-describedby={blockingMessage?"cell-fix-blocking-error":noPendingChange?"cell-fix-no-change":affectedCount===0&&interpretedDateCount>0?"cell-fix-date-confirmation":undefined} disabled={busy || (dateMedian&&!dateEstimateAck) || affectedCount === null || noPendingChange || !!blockingMessage} onClick={() => fix(true)}><CheckCircle2 size={16} aria-hidden="true"/>Apply change</Button>
          </div>}
          </div>
        </div>
      )}
    </section>
  );
}
