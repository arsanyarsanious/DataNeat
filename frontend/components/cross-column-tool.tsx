"use client";

import {useEffect, useMemo, useState} from "react";
import {ActionReview, FindingsTable, Notes, type ToolProps} from "./quality-tool-ui";

type Rule = {id:string;label:string;kind:"compare"|"arithmetic"|"required_if";target:string;left?:string;right?:string;operator?:string;arithmetic?:string;tolerance?:number;value_type?:string;interpretation?:string;condition_column?:string;condition_value?:string};
const symbols:Record<string,string> = {eq:"=",ne:"≠",lt:"<",le:"≤",gt:">",ge:"≥",add:"+",subtract:"−",multiply:"×",divide:"÷"};

function describe(rule:Rule) {
  if(rule.kind === "arithmetic") return `${rule.target} = ${rule.left} ${symbols[rule.arithmetic || "multiply"]} ${rule.right}`;
  if(rule.kind === "required_if") return `${rule.target} is required when ${rule.condition_column} ${rule.operator === "ne" ? "does not equal" : "equals"} “${rule.condition_value || "empty"}”`;
  return `${rule.target} ${symbols[rule.operator || "eq"]} ${rule.left}`;
}

export function CrossColumnTool({columns,run,busy,saved,initialColumn}:ToolProps) {
  const savedKey = JSON.stringify(saved.cross_column_rules || []);
  const savedRules = useMemo<Rule[]>(()=>JSON.parse(savedKey),[savedKey]);
  const firstTarget = initialColumn && columns.some(c=>c.column_name===initialColumn) ? initialColumn : columns[0]?.column_name || "";
  const [rules,setRules] = useState<Rule[]>(savedRules);
  const [kind,setKind] = useState<Rule["kind"]>("compare");
  const [label,setLabel] = useState("");
  const [target,setTarget] = useState(firstTarget);
  const [left,setLeft] = useState(columns.find(c=>c.column_name!==firstTarget)?.column_name || "");
  const [right,setRight] = useState(columns.find(c=>c.column_name!==firstTarget)?.column_name || "");
  const [valueType,setValueType] = useState("numeric");
  const [operator,setOperator] = useState("eq");
  const [arithmetic,setArithmetic] = useState("multiply");
  const [interpretation,setInterpretation] = useState("preserve");
  const [tolerance,setTolerance] = useState("0");
  const [conditionColumn,setConditionColumn] = useState(columns.find(c=>c.column_name!==firstTarget)?.column_name || "");
  const [conditionValue,setConditionValue] = useState("");
  const [conditionOperator,setConditionOperator] = useState("eq");
  const [editing,setEditing] = useState<string|null>(null);
  const [analysis,setAnalysis] = useState<any>(null);
  const [error,setError] = useState("");
  const [ruleId,setRuleId] = useState(savedRules[0]?.id || "");
  const [action,setAction] = useState("recalculate");
  const [scope,setScope] = useState("all");
  const [row,setRow] = useState("2");

  useEffect(()=>{setRules(savedRules);setAnalysis(null);setRuleId(old=>savedRules.some(r=>r.id===old)?old:savedRules[0]?.id || "");},[savedRules]);
  const selectedRule = savedRules.find(rule=>rule.id===ruleId);
  const numericColumns = columns.filter(column=>(column.intent?.type || column.detected_type)!=="identifier");
  const availableTargets = kind === "arithmetic" || (kind === "compare" && valueType!=="text") ? numericColumns : columns;
  const operandColumns = (kind === "arithmetic" || valueType!=="text" ? numericColumns : columns).filter(column=>column.column_name!==target);
  const numericTolerance = Number(tolerance);
  const draftValid = Boolean(target && label.trim() && availableTargets.some(c=>c.column_name===target) && (kind === "required_if" ? conditionColumn && conditionColumn!==target : left && left!==target && (kind!=="arithmetic" || right && right!==target)) && (kind==="required_if" || (Number.isFinite(numericTolerance)&&numericTolerance>=0)));
  const saveSettings = useMemo(()=>({tool:"cross_column",action:"save_rules",rules}),[rules]);
  const repairSettings = {tool:"cross_column",action:selectedRule?.kind === "arithmetic" ? action : "clear",rule_id:ruleId,row_indices:scope==="all"?null:[Number(row)-2]};
  const rowValid = scope==="all" || (Number.isInteger(Number(row)) && Number(row)>=2);
  const changedRules = JSON.stringify(rules)!==savedKey;

  function addRule() {
    if(!draftValid) return;
    const next:Rule = {id:editing || `rule-${crypto.randomUUID()}`,label:label.trim(),kind,target};
    if(kind === "required_if") Object.assign(next,{condition_column:conditionColumn,condition_value:conditionValue,operator:conditionOperator});
    else {
      Object.assign(next,{left,value_type:kind==="arithmetic"?"numeric":valueType,tolerance:valueType==="numeric"||kind==="arithmetic"?numericTolerance:0,interpretation});
      if(kind==="arithmetic") Object.assign(next,{right,arithmetic});
      else next.operator=operator;
    }
    setRules(old=>editing?old.map(rule=>rule.id===editing?next:rule):[...old,next]);
    setEditing(null);setLabel("");setAnalysis(null);setError("");
  }

  function editRule(rule:Rule) {
    setEditing(rule.id);setKind(rule.kind);setLabel(rule.label);setTarget(rule.target);
    setLeft(rule.left || columns.find(c=>c.column_name!==rule.target)?.column_name || "");
    setRight(rule.right || columns.find(c=>c.column_name!==rule.target)?.column_name || "");
    setValueType(rule.value_type || "numeric");setOperator(rule.operator || "eq");
    setArithmetic(rule.arithmetic || "multiply");setTolerance(String(rule.tolerance || 0));
    setInterpretation(rule.interpretation || "preserve");setConditionColumn(rule.condition_column || "");
    setConditionValue(rule.condition_value || "");setConditionOperator(rule.operator || "eq");
    setError("");
  }

  async function analyze() {
    setError("");
    try {
      const result=await run("analyze",saveSettings);
      setAnalysis(result?.quality || result?.review || result?.result?.quality || result?.result || result);
    } catch(cause) {setError(cause instanceof Error?cause.message:"Could not check these rules. Please try again.");}
  }

  function selectColumn(value:string) {
    setTarget(value);
    const other=columns.find(c=>c.column_name!==value && (valueType==="text" || (c.intent?.type || c.detected_type)!=="identifier"))?.column_name || "";
    if(left===value)setLeft(other);if(right===value)setRight(other);if(conditionColumn===value)setConditionColumn(other);
  }

  const options=(items:typeof columns)=>items.map(column=><option key={column.column_name} value={column.column_name}>{column.column_name}</option>);
  return <div className="quality-tool">
    <p className="quality-muted">Check relationships such as End date ≥ Start date, Total = Quantity × Price, or an email required for active accounts. Saving rules only highlights issues.</p>
    <fieldset className="quality-card" disabled={busy}>
      <legend>{editing?"Edit relationship":"Add a relationship"}</legend>
      <div className="quality-fields">
        <label>Rule name<input value={label} onChange={event=>setLabel(event.target.value)} maxLength={160} placeholder="For example: Total matches quantity × price" /></label>
        <label>Relationship<select value={kind} onChange={event=>{setKind(event.target.value as Rule["kind"]);setError("");}}><option value="compare">Compare two columns</option><option value="arithmetic">Check a calculation</option><option value="required_if">Require a value when a condition matches</option></select></label>
        <label>Target column<select value={target} onChange={event=>selectColumn(event.target.value)}><option value="">Choose a column</option>{options(availableTargets)}</select></label>
        {kind==="required_if" ? <>
          <label>Condition column<select value={conditionColumn} onChange={event=>setConditionColumn(event.target.value)}><option value="">Choose a column</option>{options(columns.filter(column=>column.column_name!==target))}</select></label>
          <label>Condition<select value={conditionOperator} onChange={event=>setConditionOperator(event.target.value)}><option value="eq">Equals</option><option value="ne">Does not equal</option></select></label>
          <label>Condition value<input value={conditionValue} onChange={event=>setConditionValue(event.target.value)} maxLength={1000} placeholder="Exact text; leave blank to match an empty cell" /></label>
        </> : <>
          {kind==="compare" && <label>Compare as<select value={valueType} onChange={event=>setValueType(event.target.value)}><option value="numeric">Numbers</option><option value="date">Dates and timestamps</option><option value="text">Exact text</option></select></label>}
          <label>{kind==="arithmetic"?"First operand column":"Compare against column"}<select value={left} onChange={event=>setLeft(event.target.value)}><option value="">Choose a column</option>{options(operandColumns)}</select></label>
          {kind==="compare" ? <label>Target must be<select value={operator} onChange={event=>setOperator(event.target.value)}><option value="eq">Equal to (=)</option><option value="ne">Different from (≠)</option><option value="lt">Less than (&lt;)</option><option value="le">Less than or equal to (≤)</option><option value="gt">Greater than (&gt;)</option><option value="ge">Greater than or equal to (≥)</option></select></label> : <>
            <label>Calculation<select value={arithmetic} onChange={event=>setArithmetic(event.target.value)}><option value="add">Add (+)</option><option value="subtract">Subtract (−)</option><option value="multiply">Multiply (×)</option><option value="divide">Divide (÷)</option></select></label>
            <label>Second operand column<select value={right} onChange={event=>setRight(event.target.value)}><option value="">Choose a column</option>{options(operandColumns)}</select></label>
          </>}
          {(kind==="arithmetic" || valueType==="numeric") && <label>Allowed numeric difference<input type="number" min="0" step="any" value={tolerance} onChange={event=>setTolerance(event.target.value)} /></label>}
          {kind==="compare" && valueType==="date" && <label>Interpret ambiguous dates<select value={interpretation} onChange={event=>setInterpretation(event.target.value)}><option value="preserve">Require existing confirmation</option><option value="day_first">Day first</option><option value="month_first">Month first</option></select></label>}
        </>}
      </div>
      {kind==="arithmetic" && <p className="quality-muted">Use plain numbers with compatible meaning. Standardize currencies, units and percentage scales first. Missing or invalid operands are flagged and left unchanged.</p>}
      {kind==="required_if" && <p className="quality-muted">The condition matches exact text, including capitalization. This rule asks for a missing value; it does not invent one.</p>}
      <div className="quality-actions"><button type="button" onClick={addRule} disabled={!draftValid || (!editing && rules.length>=30)}>{editing?"Update draft rule":"Add to draft rules"}</button>{editing && <button type="button" onClick={()=>{setEditing(null);setLabel("");}}>Cancel editing</button>}</div>
    </fieldset>

    <section className="quality-card" aria-label="Cross-column draft rules">
      <h4>Rules for this spreadsheet <span className="quality-muted">({rules.length}/30)</span></h4>
      {rules.length ? <ul className="quality-rule-list">{rules.map(rule=><li key={rule.id}><div><strong>{rule.label}</strong><p>{describe(rule)}</p>{Boolean(rule.tolerance) && <small>Allowed difference: {rule.tolerance}</small>}</div><div className="quality-actions"><button type="button" disabled={busy} onClick={()=>editRule(rule)} aria-label={`Edit ${rule.label}`}>Edit</button><button type="button" disabled={busy} onClick={()=>{setRules(old=>old.filter(item=>item.id!==rule.id));setAnalysis(null);if(editing===rule.id){setEditing(null);setLabel("");}}} aria-label={`Remove ${rule.label}`}>Remove</button></div></li>)}</ul> : <p className="quality-muted">Add a relationship above. No cross-column rules are active.</p>}
      <div className="quality-actions"><button type="button" disabled={busy || !rules.length} onClick={analyze}>Check draft rules</button></div>
      {error && <p role="alert" className="quality-error">{error}</p>}
      {analysis && <div className="quality-findings"><p><strong>{analysis.finding_count ?? analysis.findings?.length ?? 0} findings</strong> across {analysis.affected_cells ?? 0} cells.{Boolean(analysis.uncheckable_count) && ` ${analysis.uncheckable_count} cannot be checked until their source values are resolved.`}</p><FindingsTable rows={analysis.findings || []} expected /><Notes warnings={analysis.warnings} /></div>}
      <ActionReview settings={saveSettings} run={run} busy={busy} label="Save relationship rules" disabled={!changedRules} allowNoChanges />
      <p className="quality-muted">Saved rules appear as issues on the sheet. Removing a rule clears its flags without changing any values.</p>
    </section>

    {savedRules.length>0 && <section className="quality-card" aria-label="Fix cross-column findings">
      <h4>Correct a saved relationship</h4>
      <div className="quality-fields">
        <label>Saved rule<select value={ruleId} onChange={event=>{setRuleId(event.target.value);setAction("recalculate");}}>{savedRules.map(rule=><option key={rule.id} value={rule.id}>{rule.label}</option>)}</select></label>
        <label>Correction<select value={selectedRule?.kind==="arithmetic"?action:"clear"} onChange={event=>setAction(event.target.value)}>{selectedRule?.kind==="arithmetic" && <option value="recalculate">Recalculate target from its operands</option>}<option value="clear">Clear flagged target values</option></select></label>
        <label>Where should this correction apply?<select value={scope} onChange={event=>setScope(event.target.value)}><option value="all">All affected cells for this rule</option><option value="row">One spreadsheet row</option></select></label>
        {scope==="row" && <label>Spreadsheet row number<input type="number" min="2" step="1" value={row} onChange={event=>setRow(event.target.value)} /></label>}
      </div>
      <p className="quality-muted">Only the target column changes. Preview the exact Before → After values first. Recalculation skips invalid operands and blocks new conflicts with other saved rules.</p>
      <ActionReview settings={repairSettings} run={run} busy={busy} label="Apply relationship correction" disabled={!selectedRule || !rowValid} />
    </section>}
  </div>;
}

export default CrossColumnTool;
