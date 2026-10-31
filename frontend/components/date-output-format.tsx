"use client";
import { DATE_FORMAT_OPTIONS } from "@/lib/date-formats";
export function DateOutputFormat({value,onChange,disabled=false}:{value:string;onChange:(value:string)=>void;disabled?:boolean}){
 return <label className="setting">Date output format<select aria-label="Date output format" value={value} disabled={disabled} onChange={event=>onChange(event.target.value)}>{DATE_FORMAT_OPTIONS.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><small>Choose how the result looks. Input day/month interpretation is a separate choice.</small></label>;
}
