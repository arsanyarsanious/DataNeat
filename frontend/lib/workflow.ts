import { api } from "./types";
export type WorkflowStatus = { id: string; status: string; stage: string; operation: string; error?: string; result?: Record<string, unknown>; completed_units?: number; total_units?: number };
export function announceJob(fileId: string, status: WorkflowStatus | null) { window.dispatchEvent(new CustomEvent("dataneat-workflow-job", {detail: {fileId, status}})); }
export async function waitWorkflow<T>(fileId: string, jobId: string): Promise<T> {
  const started = Date.now();
  for (;;) {
    const status = await api<WorkflowStatus>(`/workflow-jobs/${jobId}`);
    announceJob(fileId, status);
    if (status.status === "completed") { sessionStorage.removeItem(`dataneat-job-${fileId}`); return status.result as T; }
    if (["failed", "cancelled"].includes(status.status)) { sessionStorage.removeItem(`dataneat-job-${fileId}`); throw new Error(status.error || "Cancelled; your last committed revision is preserved."); }
    await new Promise(resolve => setTimeout(resolve, Date.now() - started < 5000 ? 300 : 1500));
  }
}
export async function workflowJob<T>(fileId: string, revision: number, body: Record<string, unknown>): Promise<T> {
  const job = await api<{job_id: string}>(`/files/${fileId}/workflow/jobs`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({revision,...body})});
  sessionStorage.setItem(`dataneat-job-${fileId}`, job.job_id);
  announceJob(fileId, {id:job.job_id,status:"queued",stage:"Queued",operation:String(body.operation)});
  return waitWorkflow<T>(fileId, job.job_id);
}
export async function editorRequest<T>(path: string, init: RequestInit): Promise<T> {
  const body=JSON.parse(String(init.body));
  if(!body.confirmed)return api<T>(path,init);
  const fileId=path.split("/")[2];
  return workflowJob<T>(fileId,body.revision,{operation:"decision",decision:{kind:"fix",body}});
}
