"""Offline semantic parsers. Interpretation choices are explicit operation settings."""
import calendar
import csv
import ipaddress
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import pandas as pd
from .common import missing

FORMAT_ACTIONS={'normalize_number_format','convert_units','convert_numeric_dates','convert_timezone','normalize_structured','normalize_coordinates','normalize_url','normalize_ip'}
UNITS={
 'm':('length','1','0'),'cm':('length','.01','0'),'mm':('length','.001','0'),'km':('length','1000','0'),'in':('length','.0254','0'),'ft':('length','.3048','0'),'yd':('length','.9144','0'),
 'kg':('mass','1','0'),'g':('mass','.001','0'),'mg':('mass','.000001','0'),'lb':('mass','.45359237','0'),'oz':('mass','.028349523125','0'),
 'L':('volume','1','0'),'mL':('volume','.001','0'),
 'C':('temperature','1','273.15'),'K':('temperature','1','0'),'F':('temperature','0.5555555555555555555555555556','255.3722222222222222222222222'),
 's':('duration','1','0'),'min':('duration','60','0'),'h':('duration','3600','0'),
}
ALIASES={'°C':'C','°F':'F','celsius':'C','fahrenheit':'F','kelvin':'K','meter':'m','meters':'m','metre':'m','metres':'m','litre':'L','liter':'L','liters':'L','litres':'L','ml':'mL','l':'L','lbs':'lb','seconds':'s','second':'s','minutes':'min','minute':'min','hours':'h','hour':'h'}
for label,unit in [('centimeter','cm'),('centimetre','cm'),('millimeter','mm'),('millimetre','mm'),('kilometer','km'),('kilometre','km'),('kilogram','kg'),('gram','g'),('milligram','mg'),('pound','lb'),('ounce','oz'),('inch','in'),('yard','yd'),('milliliter','mL'),('millilitre','mL')]:
    ALIASES[label]=unit;ALIASES[label+'s']=unit
ALIASES.update({'foot':'ft','feet':'ft','inches':'in','degC':'C','degF':'F'})


def decimal_text(value):
    text=format(value,'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def parse_number(value, locale='dot_decimal', fraction_digits=12):
    text=str(value).strip().replace('\u2212','-')
    text=''.join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)
    if text and unicodedata.category(text[-1])=='No' and 0<unicodedata.numeric(text[-1],-1)<1:
        frac=Decimal(str(unicodedata.numeric(text[-1])))
        # Use Unicode's exact numerator/denominator rather than its float value.
        decomposed=unicodedata.normalize('NFKD',text[-1]).split('⁄')
        if len(decomposed)==2: frac=Decimal(decomposed[0])/Decimal(decomposed[1])
        prefix=text[:-1].strip(); sign=-1 if prefix.startswith('-') else 1
        whole=Decimal(0) if prefix in ('-','+') else Decimal(prefix or '0')
        value=whole+sign*frac
        return value.quantize(Decimal(1).scaleb(-fraction_digits))
    fraction=re.fullmatch(r'([+-]?)(?:(\d+)\s+)?(\d+)\s*/\s*(\d+)',text)
    if fraction:
        sign,whole,num,den=fraction.groups()
        if not int(den): raise ValueError('A fraction cannot have a zero denominator')
        with localcontext() as ctx:
            ctx.prec=60
            value=(Decimal(whole or 0)+Decimal(num)/Decimal(den))*(-1 if sign=='-' else 1)
            return value.quantize(Decimal(1).scaleb(-fraction_digits))
    if locale=='arabic': text=text.replace('٬',',').replace('٫','.')
    elif '٬' in text or '٫' in text: raise ValueError('Choose Arabic decimal/grouping separators')
    if locale=='comma_decimal':
        if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?(?:[eE][+-]?\d+)?',text): raise ValueError('Value does not match comma-decimal notation')
        text=text.replace('.','').replace(',','.')
    else:
        if not re.fullmatch(r'[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?',text): raise ValueError('Value does not match dot-decimal notation')
        text=text.replace(',','')
    value=Decimal(text)
    if not value.is_finite() or abs(value.adjusted())>300: raise ValueError('Number outside supported finite range')
    return value


def parse_unit(value, source_unit=''):
    match=re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([^\d\s]+)?\s*',str(value))
    if not match: raise ValueError('Not a measurement with a supported unit')
    number,label=match.groups();unit=ALIASES.get(label,ALIASES.get(label.lower(),label)) if label else source_unit
    if unit not in UNITS: raise ValueError('Choose a supported source unit for unlabelled amounts')
    amount=Decimal(number)
    if not amount.is_finite(): raise ValueError('Nonfinite measurement')
    return amount,unit


def convert_unit(value,settings):
    amount,source=parse_unit(value,settings.get('source_unit',''))
    target=settings['target_unit'];a,scale,offset=UNITS[source];b,out_scale,out_offset=UNITS[target]
    if a!=b: raise ValueError(f'Cannot convert {source} to incompatible {target}')
    with localcontext() as ctx:
        ctx.prec=45
        # Fahrenheit uses exact rational arithmetic, avoiding spurious near-zero values.
        base=(amount-32)*Decimal(5)/9+Decimal('273.15') if source=='F' else amount*Decimal(scale)+Decimal(offset)
        if a=='temperature' and base<0: raise ValueError('Temperature is below absolute zero')
        result=(base-Decimal('273.15'))*9/5+32 if target=='F' else (base-Decimal(out_offset))/Decimal(out_scale)
        result=result.quantize(Decimal(1).scaleb(-settings.get('decimal_places',6)))
    return f'{decimal_text(result)} {target}'


def strict_json(value):
    def pairs(items):
        result={}
        for key,val in items:
            if key in result: raise ValueError(f'Duplicate JSON key: {key}')
            result[key]=val
        return result
    parsed=json.loads(str(value),object_pairs_hook=pairs,parse_float=Decimal,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
    if not isinstance(parsed,(list,dict)): raise ValueError('Expected a JSON list or object')
    return parsed


def dump_json(value,sort_keys=False):
    if isinstance(value,Decimal):
        if not value.is_finite():raise ValueError('Nonfinite JSON number')
        return str(value)
    if isinstance(value,list):return '['+','.join(dump_json(v,sort_keys) for v in value)+']'
    if isinstance(value,dict):return '{'+','.join(json.dumps(k,ensure_ascii=False)+':'+dump_json(value[k],sort_keys) for k in (sorted(value) if sort_keys else value))+'}'
    return json.dumps(value,ensure_ascii=False,allow_nan=False)


def normalize_json(value,settings):
    if settings.get('input','json')=='delimited':
        parsed=next(csv.reader([str(value)],delimiter=settings['delimiter'],strict=True))
    else:parsed=strict_json(value)
    def clean(item):
        if isinstance(item,str): return item.strip() if settings.get('trim_items',False) else item
        if isinstance(item,dict): return {k:clean(v) for k,v in item.items()}
        if isinstance(item,list):
            values=[clean(v) for v in item]
            if settings.get('deduplicate',False):
                seen=set(); unique=[]
                for v in values:
                    key=dump_json(v,sort_keys=True)
                    if key not in seen: seen.add(key);unique.append(v)
                return unique
            return values
        return item
    return dump_json(clean(parsed))


def numeric_date(value,settings):
    amount=parse_number(value)
    source=settings['source']
    if source.startswith('unix_'):
        divisor={'unix_seconds':1,'unix_milliseconds':1000,'unix_microseconds':1000000}[source]
        microseconds=amount*1000000/divisor
        if microseconds!=microseconds.to_integral_value(): raise ValueError('Timestamp exceeds microsecond precision')
        return (datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(microseconds=int(microseconds))).isoformat()
    if source=='excel_1900':
        if amount<1 or 60<=amount<61: raise ValueError('Invalid Excel 1900 date serial (including fictitious 1900-02-29)')
        origin=datetime(1899,12,31); amount-=1 if amount>=61 else 0
    else:
        if amount<0: raise ValueError('Negative Excel 1904 date serial')
        origin=datetime(1904,1,1)
    return (origin+timedelta(microseconds=int(amount*86400000000))).isoformat()


def zoned_datetime(value,settings):
    text=str(value).strip();match=re.fullmatch(r'(.+?)\s+([A-Za-z_]+(?:/[A-Za-z0-9_+\-]+)+)',text)
    embedded=None
    if match:text,embedded=match.groups()
    if not re.search(r'[T ]\d{2}:\d{2}',text):raise ValueError('Include both date and time for timezone conversion')
    try:parsed=datetime.fromisoformat(text.replace('Z','+00:00'))
    except ValueError as exc:raise ValueError('Use a valid ISO date and time before timezone conversion') from exc
    target=ZoneInfo(settings['target_zone'])
    source=embedded or settings.get('source_zone')
    if parsed.tzinfo is None:
        if not source:raise ValueError('Choose the source timezone for unzoned timestamps')
        zone=ZoneInfo(source);possibilities=[]
        for fold in (0,1):
            candidate=parsed.replace(tzinfo=zone,fold=fold)
            if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)==parsed and not any(v.utcoffset()==candidate.utcoffset() for v in possibilities): possibilities.append(candidate)
        if not possibilities:raise ValueError('This local time does not exist because the clock moves forward')
        if len(possibilities)>1:
            policy=settings.get('ambiguous','reject')
            if policy=='reject':raise ValueError('This local time occurs twice; choose earlier or later explicitly')
            possibilities.sort(key=lambda v:v.astimezone(timezone.utc))
            parsed=possibilities[0 if policy=='earlier' else -1]
        else:parsed=possibilities[0]
    elif embedded and parsed.utcoffset()!=parsed.astimezone(ZoneInfo(embedded)).utcoffset():
        raise ValueError('The timestamp offset conflicts with its named timezone')
    return parsed.astimezone(target).isoformat()


def coordinate(value,settings):
    def number(text,axis):
        text=str(text).strip();direction=re.search(r'([NSEW])$',text,re.I)
        if direction:
            letter=direction[1].upper();text=text[:direction.start()].strip()
            if axis=='latitude' and letter not in 'NS' or axis=='longitude' and letter not in 'EW':raise ValueError('Coordinate hemisphere conflicts with selected axis')
            sign=-1 if letter in 'SW' else 1
        else:sign=None
        dms=re.fullmatch(r'(\d+(?:\.\d+)?)°\s*(\d+(?:\.\d+)?)\s*[\'′]\s*(\d+(?:\.\d+)?)?\s*["″]?',text)
        if dms:
            deg,minutes,seconds=map(Decimal,[dms[1],dms[2],dms[3] or '0'])
            if minutes>=60 or seconds>=60:raise ValueError('Invalid DMS minutes or seconds')
            val=deg+minutes/60+seconds/3600
        else:val=parse_number(text)
        if sign is not None:
            if val<0:raise ValueError('Use a magnitude plus hemisphere, not both a negative sign and hemisphere')
            val*=sign
        limit=90 if axis=='latitude' else 180
        if abs(val)>limit:raise ValueError(f'{axis} is outside ±{limit}')
        return decimal_text(val.quantize(Decimal('.000001')))
    axis=settings['axis']
    if axis in ('latitude','longitude'):return number(value,axis)
    pieces=str(value).strip().strip('()').split(',')
    if len(pieces)!=2:raise ValueError('Expected exactly two comma-separated coordinates')
    if axis=='lon_lat':pieces.reverse()
    return f'{number(pieces[0],"latitude")}, {number(pieces[1],"longitude")}'


def normalize_url(value,settings):
    text=str(value).strip()
    if '\\' in text or any(c.isspace() or ord(c)<32 for c in text):raise ValueError('URL contains unescaped whitespace, backslashes or control characters')
    if '://' not in text:
        if not settings.get('add_https',False):raise ValueError('Choose whether to add https:// to bare hosts')
        text='https://'+text
    parts=urlsplit(text)
    if parts.scheme.lower() not in ('http','https') or not parts.hostname:raise ValueError('Expected an http or https URL with a host')
    if parts.username is not None or parts.password is not None:raise ValueError('Credential-bearing URLs require manual review')
    host=parts.hostname.encode('idna').decode('ascii').lower()
    if ':' in host:
        ipaddress.IPv6Address(host);host='['+host+']'
    elif not re.fullmatch(r'[a-z0-9](?:[a-z0-9.\-]*[a-z0-9])?',host) or any(not label or len(label)>63 or label.startswith('-') or label.endswith('-') for label in host.split('.')):raise ValueError('Invalid host name')
    port=parts.port
    return urlunsplit((parts.scheme.lower(),host+(f':{port}' if port is not None else ''),parts.path,parts.query,parts.fragment))


def normalize_ip(value,settings):
    address=ipaddress.ip_address(str(value).strip())
    return address.exploded if settings.get('format')=='expanded' else address.compressed


def validate_format_settings(action,settings):
    def choice(key,choices,default=None):
        if settings.get(key,default) not in choices:raise ValueError(f'Choose {key}: '+', '.join(choices))
    if action=='normalize_number_format':
        choice('locale',('dot_decimal','comma_decimal','arabic'));choice('output',('plain','scientific'),'plain')
        for key,default,maximum in [('fraction_digits',12,18)]:
            v=settings.get(key,default)
            if isinstance(v,bool) or not isinstance(v,int) or not 1<=v<=maximum:raise ValueError(f'{key} must be 1–{maximum}')
    if action=='convert_units':
        choice('target_unit',tuple(UNITS))
        source=settings.get('source_unit','')
        if source and (source not in UNITS or UNITS[source][0]!=UNITS[settings['target_unit']][0]):raise ValueError('Source and target units must measure the same dimension')
        places=settings.get('decimal_places',6)
        if isinstance(places,bool) or not isinstance(places,int) or not 0<=places<=12:raise ValueError('Choose 0–12 decimal places')
    if action=='convert_numeric_dates':choice('source',('unix_seconds','unix_milliseconds','unix_microseconds','excel_1900','excel_1904'))
    if action=='convert_timezone':
        if not settings.get('target_zone'):raise ValueError('Choose a target timezone')
        for key in ('source_zone','target_zone'):
            if settings.get(key):
                try:ZoneInfo(settings[key])
                except (ZoneInfoNotFoundError,ValueError,TypeError) as exc:raise ValueError(f'Unknown {key}') from exc
        choice('ambiguous',('reject','earlier','later'),'reject')
    if action in ('normalize_structured','expand_structured'):
        choice('input',('json','delimited'),'json')
        if settings.get('input')=='delimited' and (not isinstance(settings.get('delimiter'),str) or len(settings['delimiter'])!=1 or settings['delimiter'] in '\r\n"'):raise ValueError('Choose one delimiter character, such as ; or |')
        for key in ('trim_items','deduplicate'):
            if key in settings and not isinstance(settings[key],bool):raise ValueError(f'{key} must be true or false')
    if action=='normalize_coordinates':choice('axis',('latitude','longitude','lat_lon','lon_lat'))
    if action=='normalize_url' and not isinstance(settings.get('add_https',False),bool):raise ValueError('add_https must be true or false')
    if action=='normalize_ip':choice('format',('compressed','expanded'),'compressed')


def format_value(value,action,settings):
    if action=='normalize_number_format':
        number=parse_number(value,settings['locale'],settings.get('fraction_digits',12))
        return format(number,'E') if settings.get('output')=='scientific' else decimal_text(number)
    return {'convert_units':convert_unit,'convert_numeric_dates':numeric_date,'convert_timezone':zoned_datetime,'normalize_structured':normalize_json,'normalize_coordinates':coordinate,'normalize_url':normalize_url,'normalize_ip':normalize_ip}[action](value,settings)


def normalize_format(series,action,settings):
    validate_format_settings(action,settings)
    result=series.astype(object).copy()
    # An invalid cell fails the scoped operation with its exact location. No
    # partial conversion is committed, and no unsupported value is guessed.
    for index,value in series.items():
        if missing(value):continue
        try:result.at[index]=format_value(value,action,settings)
        except (ValueError,InvalidOperation,OverflowError,TypeError,RecursionError,ZoneInfoNotFoundError,csv.Error) as exc:
            raise ValueError(f"Column '{series.name}', spreadsheet row {int(index)+2}, value {str(value)[:120]!r}: {exc}") from exc
    return result


def expand_structured(df,column,settings):
    validate_format_settings('expand_structured',settings)
    parsed={};keys=[];container_type=None
    prefix=str(settings.get('prefix') or column).strip()
    if not prefix or len(prefix)>150:raise ValueError('Use a short, nonempty column prefix')
    for index,value in df[column].items():
        if missing(value):continue
        try:entry=strict_json(normalize_json(value,settings))
        except (ValueError,TypeError,RecursionError,ArithmeticError,csv.Error) as exc:raise ValueError(f"Column '{column}', spreadsheet row {int(index)+2}: {exc}") from exc
        if container_type is not None and type(entry) is not container_type:raise ValueError('Separate JSON objects and arrays into homogeneous columns before expansion')
        container_type=type(entry)
        fields={str(i+1):item for i,item in enumerate(entry)} if isinstance(entry,list) else entry
        parsed[index]=fields
        for key in fields:
            if key not in keys:keys.append(key)
        if len(keys)+len(df.columns)>200:raise ValueError('Expansion would exceed the 200-column limit')
    names={key:f'{prefix}.{key}' for key in keys}
    if any(name in df.columns or len(name)>512 for name in names.values()):raise ValueError('Expanded column names conflict with existing columns or are too long; choose another prefix')
    result=df.copy(deep=True)
    for key,name in names.items():
        values=[]
        for i in df.index:
            value=parsed.get(i,{}).get(key)
            if isinstance(value,(dict,list)):value=dump_json(value)
            elif isinstance(value,Decimal) or isinstance(value,int) and not isinstance(value,bool) and abs(value)>2**53:value=str(value)
            values.append(value)
        result[name]=pd.Series(values,index=df.index,dtype=object)
    return result
