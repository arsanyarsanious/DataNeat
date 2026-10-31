"use client";
import { useState } from "react";
import type { Column } from "@/lib/types";
import { Button } from "./ui/button";

// Tool responses contain feature-specific, server-validated review metadata.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ToolRun = (mode:"analyze"|"preview"|"apply", settings:Record<string,unknown>)=>Promise<any>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ToolProps = {columns:Column[];run:ToolRun;busy:boolean;saved:Record<string,any>;initialColumn?:string};
export function displayValue(value:unknown){return value===null||value===undefined||value===""?"[empty]":String(value);}
export function Notes({warnings=[]}:{warnings?:string[]}){return warnings.length?<details className="quality-notes"><summary>Calculation notes ({warnings.length})</summary><ul>{warnings.map((warning,index)=><li key={index}>{warning}</li>)}</ul></details>:null;}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function FindingsTable({rows,expected=false}:{rows:any[];expected?:boolean}){
 return rows.length?<div className="quality-table-scroll"><table><thead><tr><th>Spreadsheet row</th><th>Column</th><th>Current value</th><th>{expected?"Expected value / finding":"Proposed value"}</th></tr></thead><tbody>{rows.slice(0,200).map((row,index)=><tr key={index}><td>{row.spreadsheet_row??Number(row.row_index)+2}</td><td>{row.column||"—"}</td><td>{displayValue(row.before)}</td><td>{expected?row.expected!==undefined&&row.expected!==null?displayValue(row.expected):row.message:row.removed_row?"[row removed]":displayValue(row.after)}{expected&&row.expected!==undefined&&row.expected!==null&&row.message&&<small>{row.message}</small>}</td></tr>)}</tbody></table></div>:<p className="quality-muted">No affected cells in this review.</p>;
}
export function ActionReview({settings,run,busy,label="Apply reviewed change",disabled=false,allowNoChanges=false}:{settings:Record<string,unknown>;run:ToolRun;busy:boolean;label?:string;disabled?:boolean;allowNoChanges?:boolean}){
 const key=JSON.stringify(settings);
 // eslint-disable-next-line @typescript-eslint/no-explicit-any
 const [preview,setPreview]=useState<{key:string;result:any}|null>(null);
 const current=preview?.key===key?preview.result:null;
 const proposal=current?.proposal;
 return <div className="quality-action-review"><div className="quality-actions"><Button variant="outline" disabled={busy||disabled} onClick={async()=>{setPreview(null);const result=await run("preview",settings);if(result)setPreview({key,result});}}>Review this change</Button><Button disabled={busy||disabled||!proposal||(!allowNoChanges&&!proposal.changed_cells)} onClick={async()=>{const result=await run("apply",settings);if(result)setPreview(null);}}>{label}</Button></div>{proposal&&<div className="quality-card" role="status"><strong>{proposal.changed_cells.toLocaleString()} cell changes in this preview</strong>{current.quality?.removed_row!==undefined&&<p><strong>One row will be removed.</strong> Row {current.quality.removed_row+2} is merged into row {current.quality.retained_row+2} using your chosen values.</p>}{!proposal.changed_cells&&allowNoChanges&&<p>This records your reviewed decision without editing cell values.</p>}<FindingsTable rows={proposal.examples||[]}/><Notes warnings={proposal.warnings||[]}/></div>}</div>;
}
