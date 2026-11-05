"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Profile, type Operation } from "@/lib/types";
import { workflowJob, waitWorkflow } from "@/lib/workflow";
import { DateOutputFormat } from "./date-output-format";
import { Button } from "./ui/button";
import { ColumnAnalysis } from "./column-analysis";
import { ImputationControls } from "./imputation-controls";
import { CurrencyControls } from "./currency-controls";
import { PercentageControls } from "./percentage-controls";
import { PhoneControls } from "./phone-controls";
import { DataFormatControls, formatActions, formatActionForType, formatDefaults } from "./data-format-controls";
import { SymbolControls } from "./symbol-controls";
import { columnDataTypes, columnTypeLabel } from "@/lib/column-data-types";
import { getImputationReadiness } from "@/lib/imputation-readiness";

type Step = {kind:"fix"|"rename";column?:string;settings?:Record<string,unknown>;body?:Record<string,unknown>};
type Draft = {id:string;label:string;step:Step};
type Entry = {action:string;column:string;changed_cells:number;examples:{row_index:number;before:unknown;after:unknown}[];warnings:string[];imputation?:{imputed_count:number;missing_before:number;missing_after:number;distribution_before?:{numeric?:{mean:number;median:number;std:number};frequencies?:{value:string;count:number}[]};distribution_after?:{numeric?:{mean:number;median:number;std:number};frequencies?:{value:string;count:number}[]}}};
type Review = {changed_cells:number;operations:Entry[]};
const stat = (value: number | null | undefined) => value == null ? "—" : new Intl.NumberFormat("en", {maximumFractionDigits:4}).format(value);
const actions:Record<string,string>={...formatActions,normalize_time:"Clock time (12 / 24 hour)",normalize_duration:"Elapsed duration",normalize_capitalization:"Capitalization",normalize_dates:"Date format",resolve_invalid_dates:"Clear invalid dates",normalize_boolean:"Boolean labels",normalize_numeric:"Numeric values",normalize_currency:"Currency notation",normalize_percentage:"Percentages / ratios",normalize_phone:"Phone numbers",normalize_symbols:"Symbols / units",impute_missing_values:"Fill missing values",remove_duplicates:"Remove duplicate rows",rename_column:"Rename column"};
function defaults(action:string):Record<string,unknown>{
  if(action in formatActions)return formatDefaults(action);
  if(action==="impute_missing_values")return {method:"preserve",group_by:[],confirmed:true};
  if(action==="normalize_capitalization")return {strategy:"title"};
  if(action==="normalize_time")return {format:"24_hour"};
  if(action==="normalize_duration")return {};
  if(action==="normalize_dates")return {interpretation:"preserve",include_time:false,output_format:"YYYY-MM-DD"};
  if(action==="resolve_invalid_dates")return {action:"empty",replacements:{}};
  if(action==="remove_duplicates")return {subset:null};
  if(action==="rename_column")return {name:""};
  if(action==="normalize_numeric")return {};
  return {action:"preserve",symbol:"",position:"prefix",grouping:"remove"};
}
export function ColumnSettings({fileId,revision,profile,initialColumn,imputation=false,onClose,onChanged}:{fileId:string;revision:number;profile:Profile;initialColumn:string;imputation?:boolean;onClose:()=>void;onChanged:()=>Promise<void>}){
  const [column,setColumn]=useState(initialColumn);
  const [allowNegative,setAllowNegative]=useState(profile.columns.find(c=>c.column_name===initialColumn)?.intent?.allow_negative!==false);
  useEffect(()=>{setAllowNegative(profile.columns.find(c=>c.column_name===column)?.intent?.allow_negative!==false);},[column,profile]);
  const selectedProfile=profile.columns.find(c=>c.column_name===column);
  const [dataType,setDataType]=useState(String(selectedProfile?.intent?.type||""));
  useEffect(()=>{setDataType(String(selectedProfile?.intent?.type||""));},[column,profile]);
  async function saveDataType(){
    setBusy(true);setError("");setMessage("");setStage("Updating column type and checking issues…");
    try {
      const current=await api<{rules:Record<string,Record<string,unknown>>}>(`/files/${fileId}/workflow/settings`);
      await workflowJob(fileId,revision,{operation:"decision",decision:{kind:"rules",column,settings:{...(current.rules[column]||{}),type:dataType}}});
      await onChanged();setReview(null);
      setAction(initialAction);setParameters(defaults(initialAction));
      setMessage("Column type saved. Checks and suggestions now use your choice. Values are unchanged; you can undo this in History.");
    } catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const [tab,setTab]=useState("Settings");
  const inferredType=profile.columns.find(c=>c.column_name===initialColumn)?.detected_type||"";
  const initialAction=imputation?"impute_missing_values":formatActionForType[inferredType]||(inferredType==="time"?"normalize_time":"normalize_capitalization");
  const [action,setAction]=useState(initialAction);
  const [parameters,setParameters]=useState<Record<string,unknown>>(defaults(initialAction));
  const [drafts,setDrafts]=useState<Draft[]>([]);
  const [editingId,setEditingId]=useState<string|null>(null);
  const [loaded,setLoaded]=useState(false);
  const [review,setReview]=useState<Review|null>(null);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [message,setMessage]=useState("");const [stage,setStage]=useState("");
  const applying=useRef(false);
  const panel=useRef<HTMLDivElement>(null);const closeRef=useRef<HTMLButtonElement>(null);
  const available=profile.columns.map(c=>c.column_name);
  useEffect(()=>{try{const saved=JSON.parse(sessionStorage.getItem(`dataneat-plan-${fileId}`)||"null");if(saved?.drafts)setDrafts(saved.drafts);const pending=sessionStorage.getItem(`dataneat-plan-apply-${fileId}`);if(pending){setBusy(true);void waitWorkflow(fileId,pending).then(async()=>{setDrafts([]);await onChanged();setMessage("Your previous cleaning plan completed. The current sheet includes its changes.");}).catch(e=>setError(e.message)).finally(()=>{sessionStorage.removeItem(`dataneat-plan-apply-${fileId}`);setBusy(false);});}}catch{}setLoaded(true);},[fileId]);
  useEffect(()=>{if(loaded)sessionStorage.setItem(`dataneat-plan-${fileId}`,JSON.stringify({drafts}));},[drafts,loaded,fileId]);
  useEffect(()=>{setReview(null);},[revision]);
  useEffect(()=>{const before=document.activeElement as HTMLElement|null;const overflow=document.body.style.overflow;document.body.style.overflow="hidden";closeRef.current?.focus();return()=>{document.body.style.overflow=overflow;before?.focus();};},[]);
  useEffect(()=>{const listener=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail.fileId===fileId&&detail.status){setStage(detail.status.stage);if(applying.current)sessionStorage.setItem(`dataneat-plan-apply-${fileId}`,detail.status.id);}};window.addEventListener("dataneat-workflow-job",listener);return()=>window.removeEventListener("dataneat-workflow-job",listener);},[fileId]);
  const op:Operation={id:"column-setting",column,operation:action,parameters,enabled:false,issue:"",affected_rows:0,explanation:"",safety:"review",requires_confirmation:true};
  const readiness=getImputationReadiness(profile.columns.find(c=>c.column_name===column));
  const imputationBlocked=action==="impute_missing_values"&&String(parameters.method||"preserve")!=="preserve"&&!readiness.ready&&parameters.inconsistencies_acknowledged!==true;
  function change(next:Record<string,unknown>){setParameters(next);setError("");}
  function editDraft(draft:Draft){
    setEditingId(draft.id);
    setColumn(String(draft.step.body?.column||draft.step.column||initialColumn));
    setAction(String(draft.step.body?.action||"rename_column"));
    setParameters({...((draft.step.body?.parameters||draft.step.settings||{}) as Record<string,unknown>)});
    setTab("Settings");
    setReview(null);
  }
  function showStepError(message:string,steps:Draft[]){
    const match=message.match(/Plan step (\d+) /);
    const draft=match?steps[Number(match[1])-1]:undefined;
    if(draft)editDraft(draft);
    setError(message);
    setReview(null);
  }
  useEffect(()=>{
    if(error)panel.current?.querySelector<HTMLElement>('[role="alert"].error')?.scrollIntoView({block:"nearest"});
  },[error,tab]);
  async function add(){
    if(imputationBlocked){setError("Please accept the warning about existing issues, or return to cleaning.");return;}
    if(action==="impute_missing_values"&&["median","group_median"].includes(String(parameters.method))&&["date","datetime"].includes(profile.columns.find(c=>c.column_name===column)?.detected_type||"")&&parameters.date_estimate_acknowledged!==true){setError("Confirm that an estimated date is appropriate before adding date median.");return;}
    if(drafts.some(d=>d.step.kind==="rename")){setError("Apply the queued rename before adding more actions, so later actions use the new column name.");return;}
    if(action==="rename_column"&&(!String(parameters.name||"").trim()||available.includes(String(parameters.name).trim()))){setError("Enter a new, unique column name.");return;}
    const step:Step=action==="rename_column"?{kind:"rename",column,settings:parameters}:{kind:"fix",body:{revision,column,row_index:0,scope:"column",action,parameters:{...parameters,confirmed:true}}};
    const draft:Draft={id:editingId||crypto.randomUUID(),label:`${column} · ${actions[action]}`,step};
    const index=editingId?drafts.findIndex(item=>item.id===editingId):-1;
    const next=index<0?[...drafts,draft]:drafts.map(item=>item.id===editingId?draft:item);
    setBusy(true);setError("");setMessage("");setStage("Checking this action with the preceding plan steps...");
    try{
      await workflowJob(fileId,revision,{operation:"plan_preview",steps:next.slice(0,index<0?next.length:index+1).map(item=>item.step)});
      setDrafts(next);setEditingId(null);setReview(null);
      setMessage("Action checked and added to your plan.");setTab("Cleaning plan");
    }catch(e){
      const message=(e as Error).message;
      const match=message.match(/Plan step (\d+) /);
      const failed=match?next[Number(match[1])-1]:undefined;
      if(failed&&failed.id!==draft.id)showStepError(message,drafts);
      else setError(message);
    }finally{setBusy(false);}
  }
  async function run(apply=false){
    applying.current=apply;setBusy(true);setError("");setMessage("");setStage(apply?"Applying reviewed cleaning plan…":"Previewing cleaning plan…");
    try{const result=await workflowJob<Review>(fileId,revision,{operation:apply?"plan":"plan_preview",steps:drafts.map(d=>d.step)});if(apply){setDrafts([]);setReview(null);await onChanged();setMessage("Cleaning plan applied to your current spreadsheet. Every step is available in cleaning history.");}else setReview(result);}catch(e){showStepError((e as Error).message,drafts);}finally{applying.current=false;sessionStorage.removeItem(`dataneat-plan-apply-${fileId}`);setBusy(false);}
  }
  return <div className="column-settings-backdrop"><div className="column-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="column-settings-title" ref={panel} onKeyDown={e=>{
    if(e.key==="Escape"&&!busy){e.stopPropagation();onClose();}
    if(e.key==="Tab"){const controls=panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary');if(!controls?.length)return;const first=controls[0],last=controls[controls.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
  }}>
    <header className="column-settings-heading"><div><h2 id="column-settings-title">{imputation?"Column imputation":"Column settings"}</h2><p>Changes use your current spreadsheet · Revision {revision}</p></div><button ref={closeRef} className="icon-button" aria-label="Close column settings" disabled={busy} onClick={onClose}>×</button></header>
    <nav className="column-settings-tabs" aria-label="Column tools">{["Settings","Insights","Cleaning plan"].map(name=><button key={name} disabled={busy} aria-pressed={tab===name} onClick={()=>setTab(name)}>{name}{name==="Cleaning plan"&&drafts.length?` (${drafts.length})`:""}</button>)}</nav>
    <div className="column-settings-content">
    {tab!=="Cleaning plan"&&<label className="setting">Column<select value={column} disabled={busy} onChange={e=>{setColumn(e.target.value);setParameters(defaults(action));setMessage("");setError("");}}>{available.map(c=><option key={c}>{c}</option>)}</select></label>}
    {tab==="Insights"&&<><ColumnAnalysis columns={profile.columns.filter(c=>c.column_name===column)} selectedColumn={column}/>{profile.columns.find(c=>c.column_name===column)?.imputation&&<ImputationControls operation={{...op,operation:"impute_missing_values",parameters:{method:"preserve"}}} columns={profile.columns} disabled onChange={()=>{}}/>}</>}
    {tab==="Settings"&&<><section hidden={imputation} className="column-data-type-setting">
      <label className="setting">Column data type<select aria-label="Column data type" disabled={busy} value={dataType} onChange={e=>{setDataType(e.target.value);setMessage("");}}><option value="" hidden>Detected automatically</option>{columnDataTypes.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <p>Currently: <strong>{columnTypeLabel(String(selectedProfile?.intent?.type||selectedProfile?.detected_type||"unknown"))}</strong> · {selectedProfile?.intent?.type?"Chosen by you":"Automatically detected"}</p>
      <small>Your choice overrides the column name and automatic detection. It changes checks and suggestions, without converting values. Serial / identifier protects leading zeros. Salary does not assign or convert a currency.</small>
      <Button disabled={busy||dataType===String(selectedProfile?.intent?.type||"")} onClick={saveDataType}>Save data type</Button>
    </section><section hidden={imputation} className="negative-policy"><label className="setting">Negative values<select aria-label="Negative value policy" disabled={busy} value={allowNegative?"allow":"deny"} onChange={e=>{setAllowNegative(e.target.value==="allow");setMessage("");}}><option value="allow">Allow negative values</option><option value="deny">Do not allow negative values</option></select><small>For example, Celsius can be negative; Kelvin cannot. This policy flags values without changing them.</small></label><Button variant="outline" disabled={busy||allowNegative===(profile.columns.find(c=>c.column_name===column)?.intent?.allow_negative!==false)} onClick={async()=>{setBusy(true);setError("");try{await workflowJob(fileId,revision,{operation:"decision",decision:{kind:"negative_policy",column,settings:{allow_negative:allowNegative}}});await onChanged();setMessage("Negative value policy saved. Your values were not changed. Close settings to review flagged cells.");}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>Save negative value policy</Button></section><label className="setting">Action<select aria-label="Column cleaning action" disabled={busy} value={action} onChange={e=>{setAction(e.target.value);setParameters(defaults(e.target.value));setError("");setMessage("");}}>{Object.entries(actions).filter(([id])=>(id==="impute_missing_values")===imputation).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    <fieldset className="column-action-fields" disabled={busy}>
    {action in formatActions&&<DataFormatControls action={action} parameters={parameters} disabled={busy} onChange={change}/>}
    {action==="impute_missing_values"&&<ImputationControls operation={op} columns={profile.columns} disabled={busy} onChange={change}/>}
    {action==="normalize_currency"&&<CurrencyControls operation={op} disabled={busy} onChange={change}/>}
    {action==="normalize_percentage"&&<PercentageControls operation={op} disabled={busy} onChange={change}/>}
    {action==="normalize_phone"&&<PhoneControls operation={op} disabled={busy} onChange={change}/>}
    {action==="normalize_symbols"&&<SymbolControls operation={op} disabled={busy} onChange={change}/>}
    {action==="normalize_capitalization"&&<label className="setting">Capitalization<select value={String(parameters.strategy)} onChange={e=>change({strategy:e.target.value})}><option value="title">Title</option><option value="upper">UPPER</option><option value="lower">lower</option></select></label>}
    {action==="normalize_dates"&&<><label className="setting">Ambiguous dates<select value={String(parameters.interpretation)} onChange={e=>change({...parameters,interpretation:e.target.value})}><option value="preserve">Preserve ambiguous dates</option><option value="day_first">I confirm day / month / year</option><option value="month_first">I confirm month / day / year</option></select></label><DateOutputFormat value={String(parameters.output_format||"YYYY-MM-DD")} onChange={value=>change({...parameters,output_format:value})}/><label><input type="checkbox" checked={parameters.include_time===true} onChange={e=>change({...parameters,include_time:e.target.checked})}/> Include time in output</label></>}
    {action==="normalize_time"&&<label className="setting">Clock format<select aria-label="Column clock format" value={String(parameters.format)} onChange={e=>change({format:e.target.value})}><option value="24_hour">24-hour · 14:30:00</option><option value="12_hour">12-hour · 02:30:00 PM</option></select><small>Changes recognized clock times only. Invalid values remain for review.</small></label>}
    {action==="normalize_duration"&&<p>Standardize recognized elapsed durations to HH:MM:SS, retaining hours above 24. Invalid values remain unchanged.</p>}
    {action==="normalize_boolean"&&<p>Standardize recognized boolean labels to true/false. Missing and unrecognized values stay unchanged.</p>}
    {action==="normalize_numeric"&&<p>Convert supported numeric text to numbers. Review identifier columns and leading zeros before applying.</p>}
    {action==="resolve_invalid_dates"&&<p>Clear every invalid date in this column. Valid dates, ambiguous dates and existing empty cells are preserved. Use the sheet to correct individual dates.</p>}
    {action==="rename_column"&&<label className="setting">New column name<input value={String(parameters.name||"")} maxLength={512} onChange={e=>change({name:e.target.value})}/></label>}
    {action==="remove_duplicates"&&<><p>Removes complete rows and keeps the first occurrence. Choose comparison columns, or leave all unchecked to compare every column.</p><div className="duplicate-column-choices">{available.map(c=><label key={c}><input type="checkbox" checked={(parameters.subset as string[]|null)?.includes(c)||false} onChange={e=>{const selected=(parameters.subset as string[]|null)||[];const next=e.target.checked?[...selected,c]:selected.filter(v=>v!==c);change({subset:next.length?next:null});}}/>{c}</label>)}</div></>}
    </fieldset><Button disabled={busy||drafts.length>=100||imputationBlocked} onClick={()=>void add()}>{editingId?"Check and update action":"Check and add action to plan"}</Button><p className="column-settings-hint">Review the plan before applying. Actions run in the order shown.{action==="impute_missing_values"&&!readiness.ready?" Existing issues may affect estimates. Review the warning before continuing.":""}</p></>}
    {tab==="Cleaning plan"&&<><p>Review these actions against your current working copy. Preview leaves your data unchanged.</p>{drafts.length?<ol className="queued-cleaning-plan">{drafts.map((draft,index)=><li key={draft.id}><div><strong>{index+1}. {draft.label}</strong><Button size="sm" variant="outline" disabled={busy} onClick={()=>{setError("");setMessage("");editDraft(draft);}}>Edit action</Button><details><summary>Settings</summary><dl>{Object.entries((draft.step.settings||draft.step.body?.parameters||{}) as Record<string,unknown>).filter(([key])=>key!=="confirmed").map(([key,value])=><div key={key}><dt>{key.replaceAll("_"," ")}</dt><dd>{value===null?"All columns":Array.isArray(value)?value.join(", ")||"None":typeof value==="boolean"?value?"Yes":"No":String(value||"Not selected").replaceAll("_"," ")}</dd></div>)}</dl></details></div><button className="icon-button" disabled={busy} aria-label={`Remove ${draft.label}`} onClick={()=>{setDrafts(items=>items.filter(d=>d.id!==draft.id));setReview(null);}}>×</button></li>)}</ol>:<p>No queued actions. Choose a column action in Settings.</p>}
    {drafts.length>0&&<div className="workflow-buttons"><Button variant="outline" disabled={busy} onClick={()=>run()}>Preview cleaning plan</Button><Button disabled={busy||!review} onClick={()=>run(true)}>Apply reviewed plan</Button></div>}
    {review&&<section className="plan-review" aria-label="Cleaning plan preview"><h3>{review.changed_cells} cell / row / heading changes proposed</h3>{review.operations.map((entry,index)=><div key={index}><strong>{index+1}. {entry.column} · {actions[entry.action]||entry.action} · {entry.changed_cells} changes</strong>{entry.imputation&&<p>Missing: {entry.imputation.missing_before} → {entry.imputation.missing_after}. Filled: {entry.imputation.imputed_count}. {entry.imputation.distribution_before?.numeric&&<>Mean: {stat(entry.imputation.distribution_before.numeric.mean)} → {stat(entry.imputation.distribution_after?.numeric?.mean)}; median: {stat(entry.imputation.distribution_before.numeric.median)} → {stat(entry.imputation.distribution_after?.numeric?.median)}; standard deviation: {stat(entry.imputation.distribution_before.numeric.std)} → {stat(entry.imputation.distribution_after?.numeric?.std)}.</>}</p>}{entry.imputation&&<details><summary>Before and after category frequencies</summary><p>Before: {entry.imputation.distribution_before?.frequencies?.map(f=>`${f.value}: ${f.count}`).join(" · ")||"No observations"}</p><p>After: {entry.imputation.distribution_after?.frequencies?.map(f=>`${f.value}: ${f.count}`).join(" · ")||"No observations"}</p></details>}<ul>{entry.examples.map((example,i)=><li key={i}>Row {example.row_index+2}: {String(example.before==null||example.before===""?"empty":example.before)} → {String(example.after==null||example.after===""?"empty":example.after)}</li>)}</ul>{entry.warnings.map((warning,i)=><p key={i}>{warning}</p>)}</div>)}</section>}</>}
    {busy&&<div role="status" className="workflow-job"><progress aria-label={stage}/><span>{stage}</span><Button variant="outline" onClick={()=>{const id=sessionStorage.getItem(`dataneat-job-${fileId}`);if(id)void api(`/workflow-jobs/${id}/cancel`,{method:"POST"}).catch(e=>setError(e.message));}}>Cancel job</Button></div>}
    {error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status" className="notice">{message}</p>}
    </div>
  </div></div>;
}
