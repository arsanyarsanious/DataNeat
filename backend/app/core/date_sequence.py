"""Conservative date-pattern completion: a regular sequence, never extrapolation."""
import calendar
import math
import re
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from collections import Counter
from .common import missing
from .date_analyzer import parse_formatted_date, render_date, detect_date_pattern, DATE_OUTPUT_FORMATS


def complete_date_sequence(df, column, settings):
    from .imputation import ordered_coordinates, imputation_summary
    original=df[column]
    order=settings['order_by']
    if order=='__sheet_order__':
        indices=list(df.index)
    else:
        if order not in df or order==column:
            raise ValueError('Choose a different ordering column or current sheet order')
        indices=list(ordered_coordinates(df[order]).sort_values(kind='stable').index)
    excluded=set(settings.get('_excluded_rows',[]))
    sources=settings.get('_source_formats',{})
    observed=[]; formats=[]
    interpretation=settings.get('date_interpretation','preserve')
    if interpretation not in ('preserve','day_first','month_first'):
        raise ValueError('Choose a supported date interpretation')
    for position,index in enumerate(indices):
        value=original.loc[index]
        if missing(value) or index in excluded: continue
        try:
            parsed=parse_formatted_date(value,interpretation,sources.get(int(index)))
            if not isinstance(parsed,datetime): parsed=datetime.combine(parsed,datetime.min.time())
        except (ValueError,TypeError,OverflowError) as exc:
            raise ValueError(f"Column '{column}', spreadsheet row {int(index)+2}: resolve invalid or ambiguous dates before detecting a pattern.") from exc
        observed.append((position,parsed))
        fmt=sources.get(int(index)) or detect_date_pattern(value)
        if fmt not in DATE_OUTPUT_FORMATS and interpretation in ('day_first','month_first') and re.fullmatch(r'\d{1,2}[-/]\d{1,2}[-/]\d{4}',str(value).strip()):
            sep='/' if '/' in str(value) else '-'
            fmt=sep.join(['DD','MM','YYYY'] if interpretation=='day_first' else ['MM','DD','YYYY'])
        if fmt in DATE_OUTPUT_FORMATS: formats.append(fmt)
    if len(observed)<3:
        raise ValueError('Date pattern needs at least three original observed dates in the sequence; previous estimates are not evidence.')
    coverage=settings.get('pattern_min_coverage',60)
    if isinstance(coverage,bool) or not isinstance(coverage,(int,float)) or not math.isfinite(coverage) or not 1<=coverage<=100:
        raise ValueError('Minimum observed coverage must be a percentage from 1 to 100')
    required=max(3,math.ceil(len(indices)*coverage/100))
    if len(observed)<required:
        raise ValueError(f'Insufficient original date evidence: {len(observed)} of {len(indices)} rows ({len(observed)/len(indices):.1%}); need at least {coverage:g}% ({required} original dates) in this sequence. Previous estimates do not count.')
    if len({d.utcoffset() is not None for _,d in observed})>1:
        raise ValueError('Normalize mixed timezone-aware and timezone-naive dates first')
    output=Counter(formats).most_common(1)[0][0] if formats else 'YYYY-MM-DD'
    if settings.get('output_format'):
        output=settings['output_format']
        if output not in DATE_OUTPUT_FORMATS: raise ValueError('Choose a supported output date format')
    include_time=any(d.time()!=datetime.min.time() for _,d in observed) or any(re.search(r'[T ]\d{2}:\d{2}',str(original.loc[i])) for i in indices if not missing(original.loc[i]) and i not in excluded)
    start,anchor=observed[0]
    def month_number(d): return (d.year-1)*12+d.month-1
    month_step=Fraction(month_number(observed[1][1])-month_number(anchor),observed[1][0]-start)
    end_of_month=all(d.day==calendar.monthrange(d.year,d.month)[1] for _,d in observed)
    def calendar_candidate(position):
        ordinal=month_number(anchor)+int(month_step)*(position-start)
        year,month=divmod(ordinal,12);year+=1;month+=1
        if not 1<=year<=9999: raise ValueError('Date sequence exceeds supported calendar range')
        day=calendar.monthrange(year,month)[1] if end_of_month else min(anchor.day,calendar.monthrange(year,month)[1])
        return anchor.replace(year=year,month=month,day=day)
    if month_step.denominator==1 and month_step and all(calendar_candidate(p)==d for p,d in observed):
        candidate=calendar_candidate
        description=f'every {int(month_step)} calendar month(s)'+(' at month end' if end_of_month else '')
        pattern={'unit':'calendar_months','step':int(month_step),'month_end':end_of_month}
    else:
        def utc(d): return d.astimezone(timezone.utc) if d.utcoffset() is not None else d
        step=Fraction((utc(observed[1][1])-utc(anchor))//timedelta(microseconds=1),observed[1][0]-start)
        if not step or step.denominator!=1 or any((utc(d)-utc(anchor))//timedelta(microseconds=1)!=step*(p-start) for p,d in observed):
            raise ValueError('No consistent date pattern matches all original observations. Missing cells were left unchanged.')
        def candidate(position):
            try:
                value=utc(anchor)+timedelta(microseconds=int(step)*(position-start))
                return value.astimezone(anchor.tzinfo) if anchor.utcoffset() is not None else value
            except OverflowError as exc: raise ValueError('Date sequence exceeds supported calendar range') from exc
        seconds=float(step/1000000)
        amount,unit=next(((seconds/divisor,label) for divisor,label in [(86400,'days'),(3600,'hours'),(60,'minutes'),(1,'seconds')] if seconds%divisor==0),(seconds,'seconds'))
        description=f'every {amount:g} {unit}'
        pattern={'unit':'microseconds','step':int(step)}
    result=df.copy(deep=True).astype({column:object})
    targets=set(settings['_target_rows']) if '_target_rows' in settings else set(indices)
    for position,index in enumerate(indices):
        if index not in targets or not missing(original.loc[index]) or not start<position<observed[-1][0]: continue
        estimate=candidate(position)
        if not include_time and estimate.time()!=datetime.min.time():
            raise ValueError('Detected pattern would invent a time in a date-only column; no cells were filled')
        result.at[index,column]=render_date(estimate,output,include_time)
    detail={'method':'date_sequence','group_by':settings.get('group_by',[]),'order_by':order,'date_output_format':output,'detected_pattern':{**pattern,'observed_points':len(observed)},'warnings':[f'Detected date pattern: {description} per ordered row, matching all {len(observed)} original observations. Only interior gaps are filled; leading/trailing gaps remain empty.','Filled dates are pattern-based estimates, not verified events. Observed values remain unchanged.'],'excluded_estimates':sum(i in excluded and not missing(original.loc[i]) for i in indices),'failures':[]}
    detail['detected_pattern'].update(original_dates=len(observed),sequence_rows=len(indices),observed_coverage_percent=100*len(observed)/len(indices),minimum_coverage_percent=coverage,matching_observations_percent=100)
    detail['warnings'].append(f'Original-date coverage: {len(observed)}/{len(indices)} rows ({100*len(observed)/len(indices):.1f}%, minimum {coverage:g}%). All original observed dates must match the pattern; previous estimates are excluded.')
    return result,imputation_summary(original,result[column],detail)
