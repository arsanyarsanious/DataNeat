"""Conservative suggestions and syntax findings for specialized data formats."""
import re
from .common import missing
from .data_formats import parse_number, parse_unit, strict_json, normalize_json, normalize_url, normalize_ip, coordinate

SEMANTIC_TYPES={'localized_number','fraction','measurement','structured','delimited_list','url','ip','coordinate','zoned_datetime','numeric_timestamp'}
ACTION_FOR_TYPE={'localized_number':'normalize_number_format','fraction':'normalize_number_format','measurement':'convert_units','structured':'normalize_structured','delimited_list':'normalize_structured','url':'normalize_url','ip':'normalize_ip','coordinate':'normalize_coordinates','zoned_datetime':'convert_timezone','numeric_timestamp':'convert_numeric_dates'}


def detect_semantic(series,threshold=.8):
    values=[str(v).strip() for v in series if not missing(v)]
    if not values:return None
    name=str(series.name or '').lower()
    def share(test):return sum(bool(test(v)) for v in values)/len(values)
    def recognized(parser,value):
        try:parser(value);return True
        except (ValueError,TypeError,RecursionError,ArithmeticError):return False
    if re.search(r'(^|[_\s])(latitude|longitude|lat|lon|lng|coordinates?|latlon|gps)($|[_\s])',name):return {'type':'coordinate','match_score':1.0}
    ip_like=lambda v:(v.count('.')==3 or ':' in v) and recognized(lambda x:normalize_ip(x,{}),v)
    if re.search(r'(^|[_\s])(ip|ipv4|ipv6|ipaddress)($|[_\s])',name) or share(ip_like)>=threshold:return {'type':'ip','match_score':round(share(ip_like),4)}
    if re.search(r'url|website|web_link',name) or share(lambda v:bool(re.match(r'https?://|www\.',v,re.I)))>=threshold:return {'type':'url','match_score':round(share(lambda v:recognized(lambda x:normalize_url(x,{'add_https':True}),v)),4)}
    if share(lambda v:v.startswith(('[','{')))>=threshold:return {'type':'structured','match_score':round(share(lambda v:recognized(strict_json,v)),4)}
    if re.search(r'tags|categories|list',name) and share(lambda v:';' in v or '|' in v)>=threshold:return {'type':'delimited_list','match_score':1.0}
    if share(lambda v:bool(re.search(r'\d{2}:\d{2}.*\s[A-Za-z_]+/[A-Za-z_+\-]+$',v)))>=threshold:return {'type':'zoned_datetime','match_score':1.0}
    if re.search(r'unix|epoch|excel_serial|timestamp',name) and share(lambda v:bool(re.fullmatch(r'[+-]?\d+(?:\.\d+)?',v)))>=threshold:return {'type':'numeric_timestamp','match_score':1.0}
    fraction=share(lambda v:bool(re.fullmatch(r'[+-]?(?:\d+\s+)?\d+\s*/\s*\d+',v)) or any(c in '¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞' for c in v))
    numeric_share=share(lambda v:recognized(parse_number,v))
    if fraction>=threshold or fraction and numeric_share>=threshold:return {'type':'fraction','match_score':round(numeric_share,4)}
    if share(lambda v:bool(re.search(r'[٠-٩۰-۹٫٬]|\d\.\d{3},\d|\d,\d{1,2}$',v)))>=threshold:return {'type':'localized_number','match_score':1.0}
    units=share(lambda v:recognized(parse_unit,v))
    if units>=threshold:return {'type':'measurement','match_score':round(units,4)}
    return None


def semantic_findings(series,kind):
    if kind not in SEMANTIC_TYPES:return []
    review=[];invalid=[]
    name=str(series.name or '').lower()
    axis='latitude' if re.search(r'latitude|(^|_)lat($|_)',name) else 'longitude' if re.search(r'longitude|(^|_)(lon|lng)($|_)',name) else None
    for index,value in series.items():
        if missing(value):continue
        try:
            if kind=='structured':
                normalized=normalize_json(value,{})
                if normalized!=str(value):review.append((index,value))
            elif kind=='url':
                normalized=normalize_url(value,{'add_https':True})
                if normalized!=str(value):review.append((index,value))
            elif kind=='ip':
                if normalize_ip(value,{})!=str(value):review.append((index,value))
            elif kind=='coordinate' and axis:
                coordinate(value,{'axis':axis})
                if any(c in str(value) for c in '°NSEW'):review.append((index,value))
            elif kind=='measurement':parse_unit(value)
            elif kind=='fraction':
                parse_number(value);review.append((index,value))
            else:review.append((index,value))
        except (ValueError,TypeError,RecursionError,ArithmeticError):invalid.append((index,value))
    def issue(label,items):return {'issue':label,'column':str(series.name),'count':len(items),'examples':[str(v) for _,v in items[:5]],'row_indices':[int(i) for i,_ in items]}
    return [item for item in (issue('data_format',review),issue('invalid_data_format',invalid)) if item['count']]
