"use client";
import { useEffect, useRef, useState } from "react";
import { api, type Preview, type OriginalColorsStatus } from "./types";
type Flags={kind:string;message:string;classification?:string};
type Block=Preview&{row_indices:number[];cell_issues:Flags[][][]};
const HEIGHT=48, BLOCK=25;
export function useContinuousSheet(seed:Block|null, fileId:string, revision:number, filtered:boolean, column:string, kind:string, target:{row:number;token:number}|null, originalColors=false){
 const viewport=useRef<HTMLDivElement>(null);
 const key=`${fileId}:${revision}:${filtered}:${column}:${kind}:${originalColors}`;
 const [cache,setCache]=useState<{key:string;blocks:Map<number,Block>}>({key:"",blocks:new Map()});
 const pending=useRef(new Map<number,AbortController>()),failed=useRef(new Set<number>());
 const [top,setTop]=useState(0),[height,setHeight]=useState(500),[error,setError]=useState(""),[retry,setRetry]=useState(0);
 const programmatic=useRef(false);
 const initialized=useRef(false),consumedTarget=useRef<number|null>(null);
 const latest=useRef(key);latest.current=key;
 const filterKey=`${fileId}:${filtered}:${column}:${kind}`;
 useEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>setHeight(el.clientHeight||500));observer.observe(el);return()=>observer.disconnect();},[!!seed]);
 useEffect(()=>{pending.current.forEach(c=>c.abort());pending.current.clear();failed.current.clear();setError("");return()=>{pending.current.forEach(c=>c.abort());pending.current.clear();};},[key]);
 useEffect(()=>{if(viewport.current){viewport.current.scrollTop=0;setTop(0);}},[filterKey]);
 useEffect(()=>{if(seed&&!initialized.current&&viewport.current){initialized.current=true;const initial=(seed.page-1)*seed.page_size*HEIGHT;viewport.current.scrollTop=initial;setTop(initial);}},[seed]);
 useEffect(()=>{if(!seed)return;setCache(current=>{const blocks=current.key===key?new Map(current.blocks):new Map<number,Block>();blocks.set(seed.page,seed);return{key,blocks};});},[seed,key]);
 useEffect(()=>{if(!seed||!target||!viewport.current||consumedTarget.current===target.token)return;const local=seed.row_indices.indexOf(target.row);if(local<0)return;consumedTarget.current=target.token;const position=(seed.page-1)*seed.page_size+local;programmatic.current=true;viewport.current.scrollTop=position*HEIGHT;setTop(position*HEIGHT);},[target,seed]);
 const total=seed?.total_rows||0;
 const first=Math.max(0,Math.min(Math.max(0,total-1),Math.floor(top/HEIGHT))-8);
 const end=Math.min(total,first+Math.ceil(height/HEIGHT)+20);
 useEffect(()=>{if(!seed)return;const blocks=cache.key===key?cache.blocks:new Map<number,Block>();
   const firstPage=Math.max(1,Math.floor(first/BLOCK)+1),lastPage=Math.ceil(end/BLOCK)+1;
   for(let page=firstPage;page<=lastPage&&page<=Math.ceil(total/BLOCK);page++){
    if(blocks.has(page)||pending.current.has(page)||failed.current.has(page))continue;
    const controller=new AbortController();pending.current.set(page,controller);
    void api<{preview:Block;revision:number;original_colors?:OriginalColorsStatus}>(`/files/${fileId}/editor?${new URLSearchParams({page:String(page),page_size:String(BLOCK),affected_only:String(filtered),issue_column:column,issue_kind:kind,original_colors:String(originalColors)})}`,{signal:controller.signal}).then(data=>{
      if(controller.signal.aborted||latest.current!==key||data.revision!==revision)return;
      if(originalColors&&data.original_colors?.status!=="ready")throw new Error(data.original_colors?.message||"Original colors could not be loaded. Turn off original colors or retry.");
      setCache(current=>{const next=current.key===key?new Map(current.blocks):new Map<number,Block>();next.set(page,data.preview);while(next.size>12){const farthest=[...next.keys()].sort((a,b)=>Math.abs(b-firstPage)-Math.abs(a-firstPage))[0];next.delete(farthest);}return{key,blocks:next};});
    }).catch(e=>{if(!controller.signal.aborted&&latest.current===key){failed.current.add(page);setError(e.message);}}).finally(()=>{if(pending.current.get(page)===controller)pending.current.delete(page);});
   }
 },[key,first,end,total,cache,retry,seed,fileId,revision,filtered,column,kind,originalColors]);
 const blocks=cache.key===key?cache.blocks:new Map<number,Block>();
 const rows=Array.from({length:Math.max(0,end-first)},(_,offset)=>{const position=first+offset,page=Math.floor(position/BLOCK)+1,local=position%BLOCK;const block=blocks.get(page)||(seed?.page===page?seed:null);return{position,index:block?.row_indices[local],values:block?.rows[local],issues:block?.cell_issues[local],imputed:block?.is_imputed?.[local],originalFills:block?.original_fills?.[local]};});
 return {viewport,rows,topSpace:first*HEIGHT,bottomSpace:Math.max(0,total-end)*HEIGHT,error,retry:()=>{failed.current.clear();setError("");setRetry(n=>n+1);},onScroll:()=>{const el=viewport.current;if(el)setTop(el.scrollTop);const manual=!programmatic.current;programmatic.current=false;return manual;},visiblePage:Math.floor(Math.max(0,top)/HEIGHT/BLOCK)+1};
}
