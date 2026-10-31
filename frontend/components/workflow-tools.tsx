"use client";
import { useEffect, useState } from "react";
import { api, initializeSession } from "@/lib/types";
import { workflowJob, waitWorkflow, type WorkflowStatus } from "@/lib/workflow";
import { columnDataTypes } from "@/lib/column-data-types";
import { Button } from "./ui/button";
type Prep = {trim:boolean;collapse:boolean;normalize_missing:boolean;markers:string[];columns:Record<string,{excluded?:boolean;trim?:boolean|null;collapse?:boolean|null;markers?:string[]|null}>};
type Rule = {allow_negative?:boolean;type?:string;required?:boolean;unique?:boolean;allowed?:string[];minimum?:string;maximum?:string;date_min?:string;date_max?:string;pattern?:string;currency?:string;percentage_scale?:string;date_order?:string;severity?:string};
type Recipe = {version:1;name:string;source_columns:string[];steps:unknown[]};
type Settings = {revision:number;preparation:Prep;rules:Record<string,Rule>;ignored:unknown[];legacy_notice:string;recipe:Recipe};
type Proposal = {proposal?:{changed_cells:number;examples:Record<string,unknown>[]};changed_cells?:number;examples?:Record<string,unknown>[];mapping_warnings?:unknown[];extra_columns?:string[];imputation?:string};
type Audit = {total:number;rows:{revision:number;action:string;column:string;spreadsheet_row:number;before:unknown;after:unknown;removed_row:boolean}[];coverage:string;ignored:unknown[]};
export function WorkflowTools({fileId,revision,columns,onChanged,onBusyChange,onError}: {fileId:string;revision:number;columns:string[];onChanged:()=>Promise<void>;onBusyChange?:(busy:boolean)=>void;onError?:(message:string)=>void}) {
  const [tab,setTab]=useState(""); const [settings,setSettings]=useState<Settings|null>(null); const [prep,setPrep]=useState<Prep|null>(null);
  const [column,setColumn]=useState(columns[0]||""); const [rule,setRule]=useState<Rule>({}); const [recipe,setRecipe]=useState<Recipe|null>(null);
  const [recipeImported,setRecipeImported]=useState(false);
  const [proposal,setProposal]=useState<Proposal|null>(null); const [error,setError]=useState(""); const [message,setMessage]=useState(""); const [working,setWorking]=useState(false);
  const [job,setJob]=useState<WorkflowStatus|null>(null); const [audit,setAudit]=useState<Audit|null>(null); const [query,setQuery]=useState("");const [filterColumn,setFilterColumn]=useState("");const [filterAction,setFilterAction]=useState("");const [filterRevision,setFilterRevision]=useState("");const [page,setPage]=useState(1);
  const [includeChanges,setIncludeChanges]=useState(false); const [download,setDownload]=useState<{download:string;filename:string;revision:number}|null>(null);
  const [batch,setBatch]=useState<{file:File;fileId?:string;revision?:number;status:string;count?:number;report?:string;error?:string}[]>([]); const [batchBusy,setBatchBusy]=useState(false);
  const [batchJob,setBatchJob]=useState<WorkflowStatus|null>(null);
  useEffect(()=>{
    let active=true;
    try {
      const saved=JSON.parse(sessionStorage.getItem(`dataneat-batch-${fileId}`)||"null");
      if(!saved?.rows?.length)return;
      const restored=saved.rows.filter((row:{fileId?:string})=>row.fileId).map((row:{filename:string;fileId:string;revision:number;status:string;count?:number;report?:string;error?:string})=>({...row,file:new File([],row.filename)}));
      setBatch(restored);
      if(saved.recipe){setRecipe(saved.recipe);setRecipeImported(true);}
      setBatchBusy(true);
      void (async()=>{for(let i=0;i<restored.length&&active;i++){
        const row={...restored[i]};const key=sessionStorage.getItem(`dataneat-job-${row.fileId}`);
        if(!key)continue;
        try {const meta=await api<WorkflowStatus>(`/workflow-jobs/${key}`);const result=await waitWorkflow<Proposal>(row.fileId,key);const sheet=await api<{revision:number}>(`/files/${row.fileId}/editor`);row.revision=sheet.revision;row.count=result.changed_cells;row.status=meta.operation==="recipe"?"Applied":meta.operation==="recipe_preview"?"Preview ready":row.status;}catch(e){row.status="Failed";row.error=(e as Error).message;}
        if(active)setBatch(rows=>rows.map((item,n)=>n===i?row:item));
      }if(active)setBatchBusy(false);})();
    }catch{/* Corrupt browser metadata never changes server data. */}
    return()=>{active=false;};
  },[fileId]);
  useEffect(()=>{if(batch.length)sessionStorage.setItem(`dataneat-batch-${fileId}`,JSON.stringify({recipe,rows:batch.filter(row=>row.fileId).map(({file,...row})=>({...row,filename:file.name}))}));},[batch,recipe,fileId]);
  useEffect(()=>{if(!batchBusy){setBatchJob(null);return;}const listener=(event:Event)=>setBatchJob((event as CustomEvent).detail.status);window.addEventListener("dataneat-workflow-job",listener);return()=>window.removeEventListener("dataneat-workflow-job",listener);},[batchBusy]);
  useEffect(()=>{ api<Settings>(`/files/${fileId}/workflow/settings`).then(s=>{setSettings(s);setPrep(s.preparation);if(!recipeImported)setRecipe(s.recipe);setRule(s.rules[column]||{});}).catch(e=>setError(e.message)); },[fileId,revision,recipeImported]);
  useEffect(()=>{setRule(settings?.rules[column]||{});setProposal(null);},[column,settings]);
  useEffect(()=>{
    const listener=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail.fileId===fileId)setJob(detail.status);};
    window.addEventListener("dataneat-workflow-job",listener);
    const saved=sessionStorage.getItem(`dataneat-job-${fileId}`);
    if(saved){setWorking(true);waitWorkflow(fileId,saved).then(()=>onChanged()).catch(e=>setError(e.message)).finally(()=>setWorking(false));}
    return ()=>window.removeEventListener("dataneat-workflow-job",listener);
  },[fileId]);
  useEffect(()=>{
    if(tab!=="Review")return;
    const controller=new AbortController();
    const params=new URLSearchParams({search:query,column:filterColumn,action:filterAction,page:String(page)});if(filterRevision)params.set("revision",filterRevision);
    const timer=setTimeout(()=>api<Audit>(`/files/${fileId}/workflow/changes?${params}`,{signal:controller.signal}).then(setAudit).catch(e=>{if(!controller.signal.aborted)setError(e.message);}),250);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[tab,query,filterColumn,filterAction,filterRevision,page,fileId,revision]);
  function invalidate(){setProposal(null);setMessage("");setError("");}
  async function run(body:Record<string,unknown>,apply=false){setWorking(true);setError("");setMessage("");setDownload(null);try{const result=await workflowJob<Proposal & {download:string;filename:string}>(fileId,revision,body);if(body.operation==="export")setDownload({...result,revision});else if(apply){setProposal(null);await onChanged();setMessage("Decision applied and recorded in cleaning history.");}else setProposal(result);}catch(e){setError((e as Error).message);}finally{setWorking(false);}}
  function decision(){return tab==="Preparation"?{kind:"preparation",settings:prep}:{kind:"rules",column,settings:rule};}
  async function importRecipe(file:File){try{if(file.size>1024*1024)throw new Error("Recipe is larger than 1 MB");const value=JSON.parse(await file.text());if(value.version!==1||!Array.isArray(value.steps))throw new Error("Unsupported recipe format");setRecipeImported(true);setRecipe(value);setBatch(rows=>rows.map(row=>({...row,status:"Not checked",count:undefined})));invalidate();}catch(e){setError((e as Error).message);}}
  async function runBatch(apply:boolean){
    if(!recipe)return;setBatchBusy(true);setError("");await initializeSession();
    for(let i=0;i<batch.length;i++){
      let item={...batch[i]};try{
        if(apply&&item.status!=="Preview ready")continue;
        setBatch(rows=>rows.map((r,n)=>n===i?{...r,status:apply?"Applying…":"Checking…"}:r));
        if(!item.fileId){const form=new FormData();form.append("file",item.file);const uploaded=await api<{file_id:string}>("/files/upload",{method:"POST",body:form});item.fileId=uploaded.file_id;const initial=await api<{revision:number}>(`/files/${item.fileId}/workflow/init`,{method:"POST"});item.revision=initial.revision;}
        setBatch(rows=>rows.map((row,n)=>n===i?{...item,status:apply?"Applying…":"Checking…"}:row));
        const result=await workflowJob<Proposal>(item.fileId,item.revision||0,{operation:apply?"recipe":"recipe_preview",recipe});
        if(apply){const current=await api<{revision:number}>(`/files/${item.fileId}/editor`);item.revision=current.revision;item.status="Applied";}else item.status="Preview ready";
        item.count=result.changed_cells;item.error=undefined;
      }catch(e){item.status="Failed";item.error=(e as Error).message;}
      setBatch(rows=>rows.map((r,n)=>n===i?item:r));
    }setBatchBusy(false);
  }
  async function batchExport(index:number,format:string){const item=batch[index];if(!item.fileId)return;setBatchBusy(true);try{const result=await workflowJob<{download:string;filename:string}>(item.fileId,item.revision||0,{operation:"export",format});setBatch(rows=>rows.map((r,n)=>n===index?{...r,report:result.download}:r));}catch(e){setError((e as Error).message);}finally{setBatchBusy(false);}}
  const busy=working||batchBusy||!!job&&["queued","running"].includes(job.status);
  const local=prep?.columns[column]||{};
  const changedCount=proposal?.proposal?.changed_cells??proposal?.changed_cells;
  useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
  useEffect(()=>{if(error)onError?.(error);},[error,onError]);
  return <section className="workflow-tools panel" aria-label="Workspace tools">
    <div className="workflow-tabs">{["Preparation","Column rules","Recipes","Batch","Review","Exports"].map(name=><button type="button" key={name} aria-pressed={tab===name} disabled={busy} onClick={()=>{setTab(tab===name?"":name);invalidate();}}>{name}</button>)}<button disabled={busy} onClick={()=>run({operation:"analysis"},true)}>Recheck issues</button></div>
    {job&&["queued","running"].includes(job.status)&&<div role="status" className="workflow-job"><strong>{job.stage}</strong>{job.total_units?<progress value={job.completed_units||0} max={job.total_units}/>:<progress aria-label={job.stage}/>}<Button variant="outline" onClick={()=>api(`/workflow-jobs/${job.id}/cancel`,{method:"POST"}).catch(e=>setError(e.message))}>Cancel job</Button></div>}
    {batchBusy&&batchJob&&["queued","running"].includes(batchJob.status)&&<div role="status" className="workflow-job"><span>{batchJob.stage}</span><progress aria-label={batchJob.stage}/><Button variant="outline" onClick={()=>api(`/workflow-jobs/${batchJob.id}/cancel`,{method:"POST"}).catch(e=>setError(e.message))}>Cancel current batch file</Button></div>}
    {tab&&settings&&<div className="workflow-content"><h3>{tab}</h3>{settings.legacy_notice&&<p className="notice">{settings.legacy_notice}</p>}
      {tab==="Preparation"&&prep&&<>
        <p>Review preparation before applying. It affects the current working copy and is reversible through history. Disabling a rule does not restore values changed by an earlier step; undo that step first.</p>
        <div className="workflow-fields">{([ ["trim","Trim leading / trailing whitespace"],["collapse","Collapse repeated internal whitespace"],["normalize_missing","Convert selected missing markers to empty cells"]] as const).map(([key,label])=><label key={key}><input type="checkbox" checked={prep[key]} disabled={busy} onChange={e=>{setPrep({...prep,[key]:e.target.checked});invalidate();}}/>{label}</label>)}</div>
        <label className="setting">Global missing markers (one per line; blank cells always count as missing)<textarea rows={4} value={prep.markers.filter(Boolean).join("\n")} disabled={busy} onChange={e=>{setPrep({...prep,markers:["",...e.target.value.split("\n").filter(Boolean)]});invalidate();}}/></label>
        <label className="setting">Column override<select value={column} onChange={e=>setColumn(e.target.value)}>{columns.map(c=><option key={c}>{c}</option>)}</select></label>
        <label><input type="checkbox" checked={!!local.excluded} onChange={e=>{setPrep({...prep,columns:{...prep.columns,[column]:{...local,excluded:e.target.checked}}});invalidate();}}/>Exclude this column from preparation</label>
        <label><input type="checkbox" checked={local.markers!=null} onChange={e=>{setPrep({...prep,columns:{...prep.columns,[column]:{...local,markers:e.target.checked?[""]:null}}});invalidate();}}/>Use a separate missing-marker list for this column</label>
        {local.markers!=null&&<label className="setting">Column missing markers<textarea rows={3} value={local.markers.filter(Boolean).join("\n")} onChange={e=>{setPrep({...prep,columns:{...prep.columns,[column]:{...local,markers:["",...e.target.value.split("\n").filter(Boolean)]}}});invalidate();}}/></label>}
      </>}
      {tab==="Column rules"&&<>
        <p>Rules identify issues; they do not convert values. Identifiers are protected from automatic type conversions. A rare value is a review suggestion, not proof of an error.</p>
        <label className="setting">Column<select value={column} onChange={e=>setColumn(e.target.value)}>{columns.map(c=><option key={c}>{c}</option>)}</select></label>
        <div className="workflow-fields"><label className="setting">Declared type<select value={rule.type||""} onChange={e=>{setRule({...rule,type:e.target.value});invalidate();}}>{columnDataTypes.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        {["required","unique"].map(key=><label key={key}><input type="checkbox" checked={!!rule[key as keyof Rule]} onChange={e=>{setRule({...rule,[key]:e.target.checked});invalidate();}}/>{key==="required"?"Required value":"Unique values"}</label>)}
        <label className="setting">Severity<select value={rule.severity||"error"} onChange={e=>{setRule({...rule,severity:e.target.value});invalidate();}}><option value="error">Error under this rule</option><option value="warning">Warning for review</option></select></label></div>
        <label className="setting">Negative values<select aria-label="Rule negative value policy" value={rule.allow_negative===false?"deny":"allow"} onChange={e=>{setRule({...rule,allow_negative:e.target.value==="allow"});invalidate();}}><option value="allow">Allow negative values</option><option value="deny">Do not allow negative values</option></select></label>
        <label className="setting">Allowed exact values (one per line; leave empty for unrestricted)<textarea rows={3} value={(rule.allowed||[]).join("\n")} onChange={e=>{setRule({...rule,allowed:e.target.value.split("\n").filter(Boolean)});invalidate();}}/></label>
        <div className="workflow-fields">{[["minimum","Minimum number / percentage points"],["maximum","Maximum number / percentage points"],["date_min","Earliest date (YYYY-MM-DD)"],["date_max","Latest date (YYYY-MM-DD)"],["pattern","Wildcard pattern: * text, ? character, [0-9] digit"]].map(([key,label])=><label className="setting" key={key}>{label}<input value={String(rule[key as keyof Rule]||"")} onChange={e=>{setRule({...rule,[key]:e.target.value});invalidate();}}/></label>)}</div>
        {rule.type==="currency"&&<label className="setting">Expected literal currency label (for example $, USD, EUR)<input value={rule.currency||""} onChange={e=>{setRule({...rule,currency:e.target.value});invalidate();}}/></label>}
        {rule.type==="percentage"&&<label className="setting">Interpret bare percentages as<select value={rule.percentage_scale||""} onChange={e=>{setRule({...rule,percentage_scale:e.target.value});invalidate();}}><option value="">Require an explicit scale</option><option value="points">Points: 10 means 10%</option><option value="ratio">Ratio: 0.1 means 10%</option></select></label>}
        {(rule.type==="date"||rule.date_min||rule.date_max)&&<label className="setting">Date interpretation<select value={rule.date_order||"preserve"} onChange={e=>{setRule({...rule,date_order:e.target.value});invalidate();}}><option value="preserve">Flag ambiguous dates for review</option><option value="dayfirst">Day first</option><option value="monthfirst">Month first</option></select></label>}
      </>}
      {["Preparation","Column rules"].includes(tab)&&<div className="workflow-buttons"><Button disabled={busy} variant="outline" onClick={()=>run({operation:"preview",decision:decision()})}>Review proposed decision</Button><Button disabled={busy||!proposal} onClick={()=>run({operation:"decision",decision:decision()},true)}>Apply reviewed decision</Button></div>}
      {tab==="Recipes"&&<>
        <p>Recipes transfer preparation, column rules, text mappings and supported whole-column operations. Row-specific corrections and ignored findings are excluded. Mean, median and mode are recalculated for each file; constants remain fixed.</p>
        <a className="button outline" href={`/api/files/${fileId}/workflow/recipe`} download>Save current recipe</a>
        <Button variant="outline" disabled={busy} onClick={()=>{setRecipeImported(false);setRecipe(settings.recipe);invalidate();}}>Use current workspace recipe</Button>
        <label className="setting">Import recipe JSON<input type="file" accept=".json" disabled={busy} onChange={e=>{if(e.target.files?.[0])void importRecipe(e.target.files[0]);}}/></label>
        {recipe&&<p>{recipe.name} · Version {recipe.version} · {recipe.steps.length} steps</p>}
        <div className="workflow-buttons"><Button disabled={busy||!recipe?.steps.length} variant="outline" onClick={()=>run({operation:"recipe_preview",recipe})}>Check and preview recipe</Button><Button disabled={busy||!proposal||!recipe?.steps.length} onClick={()=>run({operation:"recipe",recipe},true)}>Apply reviewed recipe</Button></div>
      </>}
      {tab==="Batch"&&<>
        <p>Each file is processed separately with the selected recipe. Preview every file before applying. Files are never combined. Uploaded batch files and jobs recover in the same tab after refresh; files not yet uploaded must be selected again.</p>
        <label className="setting">Recipe JSON<input type="file" accept=".json" disabled={busy} onChange={e=>{if(e.target.files?.[0])void importRecipe(e.target.files[0]);}}/></label>
        <p>{recipe?.name||"No recipe selected"} · {recipe?.steps.length||0} steps</p>
        <label className="setting">Choose CSV / XLSX files<input type="file" multiple accept=".csv,.xlsx" disabled={busy} onChange={e=>{setBatch(Array.from(e.target.files||[]).map(file=>({file,status:"Not checked"})));invalidate();}}/></label>
        <div className="workflow-buttons"><Button variant="outline" disabled={busy||!batch.length||!recipe?.steps.length} onClick={()=>runBatch(false)}>Preview batch</Button><Button disabled={busy||!batch.some(item=>item.status==="Preview ready")||batch.some(item=>item.status==="Not checked")} onClick={()=>runBatch(true)}>Apply compatible files</Button></div>
        <ul className="batch-results">{batch.map((item,index)=><li key={index}><strong>{item.file.name}</strong><span>{item.status}{item.count!==undefined?` · ${item.count} affected cells`:""}</span>{item.error&&<p className="error">{item.error}</p>}{item.status==="Applied"&&<><Button disabled={busy} variant="outline" onClick={()=>batchExport(index,"xlsx")}>Prepare Excel download</Button><Button disabled={busy} variant="outline" onClick={()=>batchExport(index,"report")}>Prepare report</Button>{item.report&&<a href={item.report} download>Download prepared file</a>}</>}</li>)}</ul>
        {batch.length>0&&<a className="button outline" download="dataneat-batch-summary.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(batch.map(({file,status,count,error,fileId})=>({filename:file.name,status,count,error,fileId})),null,2))}`}>Download batch summary</a>}
      </>}
      {tab==="Review"&&<>
        <p>All recorded cell changes in the enhanced workflow. Removed rows are represented by their original cells. Rule and ignore decisions appear in cleaning history even when no cell changed.</p>
        <div className="workflow-fields"><label className="setting">Search before / after<input value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}}/></label><label className="setting">Column<select value={filterColumn} onChange={e=>{setFilterColumn(e.target.value);setPage(1);}}><option value="">All columns</option>{columns.map(c=><option key={c}>{c}</option>)}</select></label><label className="setting">Action<input value={filterAction} placeholder="For example: preparation" onChange={e=>{setFilterAction(e.target.value);setPage(1);}}/></label><label className="setting">Revision<input type="number" min="0" value={filterRevision} onChange={e=>{setFilterRevision(e.target.value);setPage(1);}}/></label></div>
        {audit&&<><small>{audit.total} changed cells · {audit.coverage||"Complete for enhanced workflow steps"}</small><div className="table-scroll"><table><thead><tr><th>Revision</th><th>Action</th><th>Column / row</th><th>Before</th><th>After</th></tr></thead><tbody>{audit.rows.map((row,i)=><tr key={i}><td>{row.revision}</td><td>{row.action}</td><td>{row.column} · {row.spreadsheet_row}</td><td>{String(row.before??"[empty]")}</td><td>{row.removed_row?"[row removed]":String(row.after??"[empty]")}</td></tr>)}</tbody></table></div><div className="workflow-buttons"><Button disabled={page<=1} variant="outline" onClick={()=>setPage(page-1)}>Previous changes</Button><Button disabled={page*50>=audit.total} variant="outline" onClick={()=>setPage(page+1)}>Next changes</Button></div><details><summary>Accepted / ignored findings ({audit.ignored.length})</summary><pre>{JSON.stringify(audit.ignored,null,2)}</pre></details></>}
      </>}
      {tab==="Exports"&&<>
        <p>Exports contain your current working data. PDF reports and recipes may include sensitive column names and cell examples. Review packages include report.pdf and recipe.json, plus the complete change log only if selected. The original upload is not included. PDF reports are in English; Arabic PDF rendering is not currently offered.</p>
        <label><input type="checkbox" checked={includeChanges} onChange={e=>setIncludeChanges(e.target.checked)}/>Include complete before/after cell values in review package</label>
        <div className="workflow-buttons">{[["xlsx","Excel"],["csv","CSV"],["report","PDF report"],["changes","Complete change log"],["package","Review package"]].map(([format,label])=><Button key={format} disabled={busy} variant="outline" onClick={()=>run({operation:"export",format,include_changes:includeChanges})}>Prepare {label}</Button>)}</div>
        {download&&<a className="button primary" href={download.download} download onClick={()=>{if(/\.(csv|xlsx)$/i.test(download.filename))window.dispatchEvent(new CustomEvent("dataneat-data-downloaded",{detail:{fileId,revision:download.revision}}));}}>{download.filename} — Download</a>}
      </>}
      {proposal&&<div className="notice" role="status"><strong>{changedCount||0} cells would change.</strong>{tab==="Column rules"&&<p>Rules will recheck issues without changing cell values.</p>}{proposal.extra_columns?.length?<p>Extra columns preserved: {proposal.extra_columns.join(", ")}</p>:null}{proposal.imputation&&<p>{proposal.imputation}</p>}<ul>{(proposal.proposal?.examples||proposal.examples||[]).map((item,i)=><li key={i}>Row {Number(item.row_index)+2}: {String(item.before??"[empty]")} → {String(item.after??"[empty]")}</li>)}</ul>{proposal.mapping_warnings?.length?<pre>{JSON.stringify(proposal.mapping_warnings,null,2)}</pre>:null}</div>}
    </div>}
    {error&&<p className="error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  </section>;
}
