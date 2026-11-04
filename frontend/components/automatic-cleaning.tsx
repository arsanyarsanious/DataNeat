"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Profile } from "@/lib/types";
import { workflowJob } from "@/lib/workflow";
import { DATE_FORMAT_OPTIONS } from "@/lib/date-formats";
import { Button } from "./ui/button";
type Policy={trim:boolean;boolean:string;capitalization:string;dates:string;date_output:string;missing:string};
type PolicyKey=keyof Policy;
type Answers=Policy & {duplicates:"preserve"|"remove";exceptions:Record<string,Partial<Policy>>};
const questions:{key:PolicyKey;title:string;options:[string,string][];types?:string[]}[]=[
 {key:"trim",title:"Trim extra whitespace",options:[["true","Trim extra whitespace"],["false","Keep whitespace unchanged"]]},
 {key:"boolean",title:"How should boolean answers look?",types:["boolean"],options:[["preserve","Keep existing labels"],["true_false","true / false"],["yes_no","Yes / No"],["one_zero","1 / 0"]]},
 {key:"capitalization",title:"How should text capitalization look?",types:["text","category","categorical"],options:[["preserve","Keep existing capitalization"],["title","Title"],["upper","UPPER"],["lower","lower"]]},
 {key:"dates",title:"How should dates be interpreted?",types:["date","datetime"],options:[["preserve","Keep dates unchanged"],["unambiguous","Standardize only unambiguous dates"],["day_first","Day first (DD/MM/YYYY)"],["month_first","Month first (MM/DD/YYYY)"]]},
 {key:"date_output",title:"How should standardized dates look?",types:["date","datetime"],options:DATE_FORMAT_OPTIONS},
];
type Result={changed_cells:number;removed_rows?:number;operations:unknown[];skipped:string[];remaining?:{cells?:number};run_id?:string};
export function AutomaticCleaning({fileId,revision,profile,onClose,onApplied,onReview,onDownload}:{fileId:string;revision:number;profile:Profile;onClose:()=>void;onApplied:()=>Promise<void>;onReview:()=>void;onDownload:()=>Promise<void>}){
 const [answers,setAnswers]=useState<Answers>({trim:true,boolean:"preserve",capitalization:"preserve",dates:"preserve",date_output:"YYYY-MM-DD",missing:"preserve",duplicates:"preserve",exceptions:{}});
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[result,setResult]=useState<Result|null>(null);
 const [job,setJob]=useState<{id:string;stage:string}|null>(null);
 useEffect(()=>{const listen=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail.fileId===fileId&&detail.status)setJob(detail.status);};window.addEventListener("dataneat-workflow-job",listen);return()=>window.removeEventListener("dataneat-workflow-job",listen);},[fileId]);
 const panel=useRef<HTMLDivElement>(null);
 useEffect(()=>{const previous=document.activeElement as HTMLElement;const overflow=document.body.style.overflow;document.body.style.overflow="hidden";panel.current?.focus();return()=>{document.body.style.overflow=overflow;previous?.focus();};},[]);
 const [saveChoices,setSaveChoices]=useState(false),[savedAvailable,setSavedAvailable]=useState(false),[restoreNotice,setRestoreNotice]=useState("");
 const [batchColumns,setBatchColumns]=useState<string[]>([]),[batchValue,setBatchValue]=useState("");
 useEffect(()=>{try{setSavedAvailable(!!localStorage.getItem("dataneat-automatic-choices-v1"));}catch{}},[]);
 function restoreChoices(){try{
  const saved=JSON.parse(localStorage.getItem("dataneat-automatic-choices-v1")||"{}");
  const restored:Answers={trim:true,boolean:"preserve",capitalization:"preserve",dates:"preserve",date_output:"YYYY-MM-DD",missing:"preserve",duplicates:"preserve",exceptions:{}};
  for(const q of questions)if(q.options.some(([v])=>v===String(saved[q.key])))Object.assign(restored,{[q.key]:q.key==="trim"?saved[q.key]===true:saved[q.key]});
  if(saved.duplicates==="preserve"||saved.duplicates==="remove")restored.duplicates=saved.duplicates;
  const skipped:string[]=[];
  for(const [name,values] of Object.entries(saved.exceptions||{})){
   const column=profile.columns.find(c=>c.column_name===name);
   if(!column){skipped.push(name);continue;}
   for(const q of questions){const v=(values as Partial<Policy>)?.[q.key];if(v===undefined)continue;
    if(column.detected_type==="identifier"||(q.types&&!q.types.includes(column.detected_type))){skipped.push(`${name} (${q.key})`);continue;}
    if(q.options.some(([option])=>option===String(v)))restored.exceptions[name]={...restored.exceptions[name],[q.key]:v};
   }
  }
  setAnswers(restored);setRestoreNotice(skipped.length?`Saved exceptions not used in this file: ${skipped.join(", ")}. Other choices were loaded.`:"Saved choices loaded. Check them before starting.");
 }catch{setError("Saved choices could not be read. You can choose new answers.");}}
 function example(key:PolicyKey,chosen:string,columnName?:string){
  const q=questions.find(q=>q.key===key)!;
  const column=columnName?profile.columns.find(c=>c.column_name===columnName):profile.columns.find(c=>c.detected_type!=="identifier"&&(!q.types||q.types.includes(c.detected_type)));
  if(!column)return "No applicable columns in this file.";
  const raw=(key==="trim"?column.sample_values.find(v=>typeof v==="string"&&v.trim().replace(/\s+/g," ")!==v):undefined)??column.sample_values.find(v=>v!==null&&v!==undefined);const before=String(raw??"empty");let after=before;
  if(key==="trim"&&chosen==="true")after=before.trim().replace(/\s+/g," ");
  if(key==="capitalization"&&chosen!=="preserve")after=chosen==="lower"?before.toLowerCase():chosen==="upper"?before.toUpperCase():before.toLowerCase().replace(/\b\p{L}/gu,c=>c.toUpperCase());
  if(key==="boolean"&&chosen!=="preserve"){const normalized=before.trim().toLowerCase();if(!["true","yes","y","1","false","no","n","0"].includes(normalized))return `${column.column_name}: “${before}” stays unchanged (not a recognized boolean label).`;const truth=["true","yes","y","1"].includes(normalized);after=chosen==="yes_no"?(truth?"Yes":"No"):chosen==="one_zero"?(truth?"1":"0"):String(truth);}
  if(key==="date_output")return `Output: ${chosen}. Used when date standardization is enabled; this does not choose the input day/month order.`;
  if(key==="dates"&&chosen!=="preserve")return `${column.column_name}: ${before} → ${answers.exceptions[column.column_name]?.date_output||answers.date_output}; ${chosen==="unambiguous"?"ambiguous dates stay unchanged":chosen.replace("_"," ")}.`;
  if(key==="missing")return chosen==="preserve"?`${column.column_name}: empty → empty`:`${column.column_name}: empty → column ${chosen} (estimate, calculated from all eligible rows)`;
  return `${column.column_name}: “${before}” → “${after}”`;
 }
 const [adding,setAdding]=useState<PolicyKey|null>(null);
 const choose=(key:PolicyKey,value:string)=>setAnswers(a=>({...a,[key]:key==="trim"?value==="true":value}));
 function exception(column:string,key:PolicyKey,value:string|null){
  setAnswers(a=>{const exceptions={...a.exceptions};const values={...exceptions[column]};
   if(value===null)delete values[key];else Object.assign(values,{[key]:key==="trim"?value==="true":value});
   if(Object.keys(values).length)exceptions[column]=values;else delete exceptions[column];
   return {...a,exceptions};});
 }

 async function start(){setBusy(true);setError("");try{const value=await workflowJob<Result>(fileId,revision,{operation:"automatic",answers});setResult(value);if(saveChoices){try{localStorage.setItem("dataneat-automatic-choices-v1",JSON.stringify(answers));setSavedAvailable(true);}catch{setError("Cleaning completed, but this browser could not save your choices.");}}await onApplied();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <div className="auto-cleaning-backdrop"><div className="auto-cleaning-dialog" role="dialog" aria-modal="true" aria-labelledby="automatic-title" tabIndex={-1} ref={panel} onKeyDown={e=>{if(e.key==="Escape"&&!busy)onClose();if(e.key==="Tab"){const nodes=panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),select:not(:disabled),input:not(:disabled)');if(!nodes?.length)return;const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}}>
 <div className="auto-cleaning-title"><h2 id="automatic-title">Automatic cleaning</h2><Button variant="outline" disabled={busy} onClick={onClose}>Close</Button></div>
 {result?<><p role="status">Completed: {result.operations.length} recorded steps, {result.changed_cells.toLocaleString()} cell changes.</p>{result.removed_rows!==undefined&&<p>{result.removed_rows.toLocaleString()} duplicate rows removed; the first occurrence is kept.</p>}<p>{result.remaining?.cells ?? 0} cells still have issue flags. Your original file is preserved; each step and this whole run can be undone in cleaning history.</p>{result.skipped.length>0&&<details><summary>Values kept unchanged ({result.skipped.length})</summary><ul>{result.skipped.map((v,i)=><li key={i}>{v}</li>)}</ul></details>}<div className="auto-result-actions"><Button onClick={onReview}>Review remaining issues</Button><Button variant="outline" disabled={busy} onClick={async()=>{setBusy(true);try{await onDownload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>Download cleaned file</Button><Button variant="ghost" onClick={onClose}>Return to spreadsheet</Button></div>{error&&<p role="alert">{error}</p>}</>:<>
 <p>Answer these optional questions. We will analyze every column of your current sheet and apply these choices in one run, without asking you to review each fix. Column exceptions override the general answer; remove an exception to use the general answer again.</p>
 {savedAvailable&&<div className="auto-result-actions"><Button variant="outline" disabled={busy} onClick={restoreChoices}>Load saved choices</Button><Button variant="ghost" disabled={busy} onClick={()=>{try{localStorage.removeItem("dataneat-automatic-choices-v1");setSavedAvailable(false);setRestoreNotice("Saved choices removed from this browser. Current answers stay unchanged.");}catch{setError("This browser could not remove saved choices.");}}}>Forget saved choices</Button></div>}{restoreNotice&&<p role="status">{restoreNotice}</p>}
 <fieldset disabled={busy} className="auto-cleaning-questions">
 {questions.map(question=>{
  const candidates=profile.columns.filter(column=>column.detected_type!=="identifier"&&(!question.types||question.types.includes(column.detected_type)));
  const selected=Object.entries(answers.exceptions).filter(([,values])=>values[question.key]!==undefined);
  const available=candidates.filter(column=>answers.exceptions[column.column_name]?.[question.key]===undefined);
  return <section className="auto-cleaning-question" key={question.key}>
   {question.key==="trim"?<label><input type="checkbox" checked={answers.trim} onChange={e=>choose("trim",String(e.target.checked))}/>{question.title}</label>:<label>{question.title}<select value={String(answers[question.key])} onChange={e=>choose(question.key,e.target.value)}>{question.options.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>}
   <small className="auto-example">{example(question.key,String(answers[question.key]))}</small>
   {selected.map(([column,values])=><div className="auto-cleaning-exception" key={column}>
    <span className="auto-exception-column">{column}</span>
    <label><select aria-label={`${question.key} exception for ${column}`} value={String(values[question.key])} onChange={e=>exception(column,question.key,e.target.value)}>{question.options.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    <small className="auto-exception-example">{example(question.key,String(values[question.key]),column)}</small>
    <Button variant="ghost" size="sm" aria-label={`Remove ${question.key} exception for ${column}`} onClick={()=>exception(column,question.key,null)}>×</Button>
   </div>)}
   {adding===question.key?<div className="auto-add-exception">
    <strong>Choose columns with the same exception</strong>
    <div className="auto-column-checklist">{available.map(column=><label key={column.column_name}><input type="checkbox" checked={batchColumns.includes(column.column_name)} onChange={e=>setBatchColumns(values=>e.target.checked?[...values,column.column_name]:values.filter(v=>v!==column.column_name))}/>{column.column_name}</label>)}</div>
    <label>Exception rule<select aria-label={`${question.key} shared exception rule`} value={batchValue} onChange={e=>setBatchValue(e.target.value)}>{question.options.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
    <Button size="sm" disabled={!batchColumns.length} onClick={()=>{for(const name of batchColumns)exception(name,question.key,batchValue);setAdding(null);setBatchColumns([]);}}>Add exceptions ({batchColumns.length})</Button>
    <Button size="sm" variant="ghost" onClick={()=>setAdding(null)}>Cancel</Button>
   </div>:<Button variant="ghost" size="sm" disabled={!available.length} onClick={()=>{setAdding(question.key);setBatchColumns([]);setBatchValue(String(answers[question.key]));}} aria-label={`Add exception: ${question.title}`}>+ Add exception</Button>}
  </section>;
 })}
 <section className="auto-cleaning-question"><label>How should duplicate rows be handled?<select aria-label="Duplicate rows" value={answers.duplicates} onChange={e=>setAnswers(a=>({...a,duplicates:e.target.value as Answers["duplicates"]}))}><option value="preserve">Keep duplicate rows</option><option value="remove">Remove duplicate rows — keep the first occurrence</option></select></label><small className="auto-example">{profile.duplicate_rows.toLocaleString()} full duplicate rows currently detected. Removal runs after your selected cleaning, compares every column, and can be undone. Rows sharing only some values are kept.</small></section>
 <label><input type="checkbox" checked={saveChoices} onChange={e=>setSaveChoices(e.target.checked)}/> Use these choices next time (saved in this browser after a successful run)</label>
 </fieldset>
 <p className="muted">Identifiers and columns with your manual corrections are preserved. Invalid values, ambiguous units, missing values are reviewed in the Imputation phase. Duplicate rows are removed only if you choose that option. No currency conversion is performed.</p>
 {error&&<p role="alert">{error}</p>}
 {busy?<div><p role="status">{job?.stage || "Analyzing and cleaning…"}</p><progress aria-label="Automatic cleaning progress" />{job&&<Button variant="outline" onClick={async()=>{try{await api(`/workflow-jobs/${job.id}/cancel`,{method:"POST"});}catch(e){setError((e as Error).message);}}}>Cancel cleaning</Button>}</div>:<Button onClick={start}>Start automatic cleaning</Button>}
 </>}
 </div></div>;
}
