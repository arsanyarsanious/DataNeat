"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/types";
import { workflowJob, waitWorkflow } from "@/lib/workflow";
import { Button } from "./ui/button";
export function AdvancedExports({fileId,jobId}:{fileId:string;jobId:string}){
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [ready,setReady]=useState<{download:string;filename:string}|null>(null);
  useEffect(()=>{const saved=sessionStorage.getItem(`dataneat-job-${fileId}`);if(saved){setBusy(true);waitWorkflow<{download:string;filename:string}>(fileId,saved).then(setReady).catch(e=>setError(e.message)).finally(()=>setBusy(false));}},[fileId]);
  async function prepare(format:string){setBusy(true);setError("");try{const sheet=await api<{revision:number}>(`/files/${fileId}/workflow/init`,{method:"POST"});const result=await workflowJob<{download:string;filename:string}>(fileId,sheet.revision,{operation:"export",format,source_job:jobId});setReady(result);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <div className="workflow-buttons">{["report","xlsx","csv"].map(format=><Button key={format} disabled={busy} variant="outline" onClick={()=>prepare(format)}>Prepare {format==="report"?"PDF report":format.toUpperCase()}</Button>)}{busy&&<><span role="status">Generating export in the background…</span><Button variant="outline" onClick={()=>{const key=sessionStorage.getItem(`dataneat-job-${fileId}`);if(key)void api(`/workflow-jobs/${key}/cancel`,{method:"POST"}).catch(e=>setError(e.message));}}>Cancel export</Button></>}{ready&&<a className="button primary" href={ready.download} download>Download {ready.filename}</a>}{error&&<p role="alert" className="error">{error}</p>}</div>;
}
