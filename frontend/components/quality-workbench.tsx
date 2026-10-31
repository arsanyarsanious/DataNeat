"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Profile } from "@/lib/types";
import { workflowJob, type WorkflowStatus } from "@/lib/workflow";
import { Button } from "./ui/button";
import { CrossColumnTool } from "./cross-column-tool";
import { ModelImputationTool } from "./model-imputation-tool";
import { RecordMatchingTool } from "./record-matching-tool";
import { OutlierTool } from "./outlier-tool";
import type { ToolRun } from "./quality-tool-ui";

export const qualityTools=[
 {id:"cross_column",title:"Related column rules",description:"Check totals, date order and conditional required values."},
 {id:"model_imputation",title:"KNN & Iterative imputation",description:"Estimate missing measurements using other numeric columns."},
 {id:"record_matching",title:"Similar records",description:"Compare possible duplicates and choose which values to keep."},
 {id:"outliers",title:"Outlier review",description:"Find unusual measurements, then keep, clear or cap them."},
] as const;
export type QualityToolId=typeof qualityTools[number]["id"];
export function QualityWorkbench({fileId,revision,profile,initialTool,initialColumn,onClose,onChanged,onBusyChange}:{fileId:string;revision:number;profile:Profile;initialTool:QualityToolId;initialColumn?:string;onClose:()=>void;onChanged:()=>Promise<void>;onBusyChange:(value:boolean)=>void}){
 const [tool,setTool]=useState<QualityToolId>(initialTool),[working,setWorking]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
 // eslint-disable-next-line @typescript-eslint/no-explicit-any
 const [saved,setSaved]=useState<Record<string,any>|null>(null);
 const [job,setJob]=useState<WorkflowStatus|null>(null);
 const panel=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(error){const body=panel.current?.querySelector<HTMLElement>(".quality-body");body?.scrollTo({top:0,behavior:"smooth"});}},[error]);
 useEffect(()=>{onBusyChange(working);return()=>onBusyChange(false);},[working,onBusyChange]);
 useEffect(()=>{let active=true;api<Record<string,unknown>>(`/files/${fileId}/workflow/settings`).then(value=>{if(active)setSaved(value);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[fileId,revision]);
 useEffect(()=>{const listener=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail.fileId===fileId)setJob(detail.status);};window.addEventListener("dataneat-workflow-job",listener);return()=>window.removeEventListener("dataneat-workflow-job",listener);},[fileId]);
 useEffect(()=>{const previous=document.activeElement as HTMLElement;const overflow=document.body.style.overflow;document.body.style.overflow="hidden";panel.current?.focus();return()=>{document.body.style.overflow=overflow;previous?.focus();};},[]);
 const run:ToolRun=async(mode,settings)=>{
  setWorking(true);setError("");setMessage("");setJob(null);
  try{
   const result=await workflowJob(fileId,revision,mode==="analyze"?{operation:"quality_review",quality:settings}:{operation:mode==="preview"?"preview":"decision",decision:{kind:"quality",settings}});
   if(mode==="apply"){await onChanged();setMessage("Decision applied to your current sheet. See History to review or undo it.");}
   return result;
  }catch(e){setError((e as Error).message);return null;}finally{setWorking(false);}
 };
 const heading=qualityTools.find(item=>item.id===tool)!;
 const Component=tool==="cross_column"?CrossColumnTool:tool==="model_imputation"?ModelImputationTool:tool==="record_matching"?RecordMatchingTool:OutlierTool;
 return <div className="quality-backdrop"><div className="quality-workbench" role="dialog" aria-modal="true" aria-labelledby="quality-title" tabIndex={-1} ref={panel} onKeyDown={e=>{
  if(e.key==="Escape"&&!working)onClose();
  if(e.key==="Tab"){const nodes=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),select:not(:disabled),input:not(:disabled),textarea:not(:disabled),summary,a[href]')||[]).filter(node=>node.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&(document.activeElement===first||document.activeElement===panel.current)){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}
 }}><header className="quality-heading"><div><small>Cleaning tools · Current working copy</small><h2 id="quality-title">{heading.title}</h2></div><Button variant="outline" disabled={working} onClick={onClose}>Close</Button></header><nav className="quality-tabs" aria-label="Cleaning tool">{qualityTools.map(item=><button type="button" key={item.id} disabled={working} aria-current={tool===item.id?"page":undefined} onClick={()=>{setTool(item.id);setError("");setMessage("");}}>{item.title}</button>)}</nav><div className="quality-body"><p className="quality-intro">{heading.description}</p>{message&&<p className="quality-success" role="status">{message}</p>}{error&&<div className="quality-error" role="alert"><strong>Cannot complete this step</strong><p>{error}</p></div>}{working&&<div className="quality-progress" role="status"><progress aria-label="Cleaning tool progress"/><span>{job?.stage||"Preparing your review…"}</span>{job?.id&&["running","queued"].includes(job.status)&&<Button size="sm" variant="outline" onClick={async()=>{try{await api(`/workflow-jobs/${job.id}/cancel`,{method:"POST"});}catch(e){setError((e as Error).message);}}}>Cancel</Button>}</div>}{saved?.revision===revision?<Component key={`${tool}-${revision}`} columns={profile.columns} initialColumn={initialColumn} saved={saved} run={run} busy={working}/>:<p role="status">Loading your current settings…</p>}</div><footer className="quality-footer">Your original upload is preserved. Applied decisions appear in History and can be undone.</footer></div></div>;
}
