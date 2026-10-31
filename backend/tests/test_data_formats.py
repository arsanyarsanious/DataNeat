from decimal import Decimal
import pandas as pd
import pytest
from app.core.data_formats import parse_number, format_value, normalize_format, expand_structured
from app.core.type_detector import detect_column_type
from app.core.interactive import propose
from app.models.requests import EditorRequest


@pytest.mark.parametrize('value,locale,expected', [('1.234,56','comma_decimal','1234.56'),('1,234.56','dot_decimal','1234.56'),('١٬٢٣٤٫٥٦','arabic','1234.56'),('۱٬۲۳۴٫۵۶','arabic','1234.56'),('1.2e3','dot_decimal','1200'),('½','dot_decimal','.5'),('-1 1/2','dot_decimal','-1.5'),('-½','dot_decimal','-.5'),('⅓','dot_decimal','.333333333333')])
def test_number_conventions(value,locale,expected):
    assert parse_number(value,locale)==Decimal(expected)


@pytest.mark.parametrize('value,source,target,expected',[('100 cm','','m','1 m'),('1 m','','cm','100 cm'),('0 C','','K','273.15 K'),('32 F','','C','0 C'),('0 K','','C','-273.15 C'),('1 lb','','g','453.59237 g'),('100','cm','m','1 m')])
def test_real_unit_conversion(value,source,target,expected):
    assert format_value(value,'convert_units',{'source_unit':source,'target_unit':target})==expected


@pytest.mark.parametrize('value,source,expected',[('0','unix_seconds','1970-01-01T00:00:00+00:00'),('1000','unix_milliseconds','1970-01-01T00:00:01+00:00'),('1000001','unix_microseconds','1970-01-01T00:00:01.000001+00:00'),('1','excel_1900','1900-01-01T00:00:00'),('61','excel_1900','1900-03-01T00:00:00'),('0','excel_1904','1904-01-01T00:00:00'),('1.5','excel_1904','1904-01-02T12:00:00')])
def test_numeric_date_sources(value,source,expected):
    assert format_value(value,'convert_numeric_dates',{'source':source})==expected


def test_timezones_and_dst():
    action='convert_timezone'
    assert format_value('2024-01-01T12:00:00 America/New_York',action,{'target_zone':'UTC'})=='2024-01-01T17:00:00+00:00'
    with pytest.raises(ValueError,match='occurs twice'):format_value('2024-11-03T01:30:00',action,{'source_zone':'America/New_York','target_zone':'UTC'})
    assert format_value('2024-11-03T01:30:00',action,{'source_zone':'America/New_York','target_zone':'UTC','ambiguous':'earlier'})=='2024-11-03T05:30:00+00:00'
    assert format_value('2024-11-03T01:30:00',action,{'source_zone':'America/New_York','target_zone':'UTC','ambiguous':'later'})=='2024-11-03T06:30:00+00:00'
    with pytest.raises(ValueError,match='does not exist'):format_value('2024-03-10T02:30:00',action,{'source_zone':'America/New_York','target_zone':'UTC'})


def test_structured_and_delimited_lists():
    assert format_value('[" Red ","Red","Blue"]','normalize_structured',{'trim_items':True,'deduplicate':True})=='["Red","Blue"]'
    assert format_value('"New; York"; Boston','normalize_structured',{'input':'delimited','delimiter':';','trim_items':True})=='["New; York","Boston"]'
    with pytest.raises(ValueError,match='Duplicate JSON key'):format_value('{"a":1,"a":2}','normalize_structured',{})
    df=pd.DataFrame({'Meta':['{"code":"001","count":2}','{"code":"002","nested":{"a":1}}',None]})
    out=expand_structured(df,'Meta',{})
    assert out.Meta.equals(df.Meta)
    assert out['Meta.code'].tolist()==['001','002',None]
    assert out['Meta.nested'][1]=='{"a":1}'
    with pytest.raises(ValueError,match='conflict'):expand_structured(out,'Meta',{})
    exact='{"amount":0.1234567890123456789012345,"id":12345678901234567890}'
    assert format_value(exact,'normalize_structured',{})==exact
    precise=expand_structured(pd.DataFrame({'Meta':[exact]}),'Meta',{})
    assert precise['Meta.amount'][0]=='0.1234567890123456789012345'
    assert precise['Meta.id'][0]=='12345678901234567890'


def test_geography_url_and_ip():
    assert format_value('30° 3\' 0" N','normalize_coordinates',{'axis':'latitude'})=='30.05'
    assert format_value('31, 30','normalize_coordinates',{'axis':'lon_lat'})=='30, 31'
    with pytest.raises(ValueError):format_value('91','normalize_coordinates',{'axis':'latitude'})
    assert format_value('HTTPS://EXAMPLE.COM/Case?Q=X#Section','normalize_url',{})=='https://example.com/Case?Q=X#Section'
    with pytest.raises(ValueError):format_value('example.com','normalize_url',{})
    assert format_value('example.com/Case','normalize_url',{'add_https':True})=='https://example.com/Case'
    assert format_value('2001:0db8:0000:0000:0000:0000:0000:0001','normalize_ip',{})=='2001:db8::1'
    with pytest.raises(ValueError):format_value('999.1.1.1','normalize_ip',{})


def test_explicit_settings_and_exact_error_scope():
    with pytest.raises(ValueError):EditorRequest(revision=0,column='Amount',row_index=0,action='normalize_number_format')
    df=pd.DataFrame({'Amount':['1.234,56','bad'],'Other':['keep']*2})
    body=EditorRequest(revision=0,column='Amount',row_index=0,action='normalize_number_format',parameters={'locale':'comma_decimal'})
    changed,_=propose(df,body)
    assert changed.Amount.tolist()==['1234.56','bad']
    with pytest.raises(ValueError,match="Column 'Amount', spreadsheet row 3"):
        propose(df,body.model_copy(update={'scope':'column'}))
    assert df.Amount[0]=='1.234,56'
    with pytest.raises(ValueError):format_value('60','convert_numeric_dates',{'source':'excel_1900'})
    with pytest.raises(ValueError):format_value('-1 K','convert_units',{'target_unit':'C'})
    with pytest.raises(ValueError):format_value('5 kg','convert_units',{'target_unit':'m'})


def test_scientific_numbers_support_existing_imputation():
    from app.core.imputation import impute_missing_values
    df=pd.DataFrame({'Reading':['1e3',None,'3e3']})
    result,detail=impute_missing_values(df,'Reading','mean',{})
    assert result.Reading[1]==2000
    assert detail['imputed_count']==1


def test_invalid_fractions_and_legacy_expansion():
    from app.core.profiler import profile_dataframe
    from app.core.cleaner import apply_cleaning_plan
    report=profile_dataframe(pd.DataFrame({'Portion':['1/0','2/0']}))
    assert report['columns'][0]['detected_type']=='fraction'
    assert report['columns'][0]['issues'][0]['issue']=='invalid_data_format'
    result,logs=apply_cleaning_plan(pd.DataFrame({'Meta':['{"x":1}']}),[{'column':'Meta','operation':'expand_structured','parameters':{},'enabled':True}])
    assert result['Meta.x'][0]==1
    assert logs[0]['modified_values']==1


@pytest.mark.parametrize('name,values,kind',[('Amount',['1.234,56','2.345,67'],'localized_number'),('Portion',['½','1/4'],'fraction'),('Distance',['100 cm','1 m'],'measurement'),('Meta',['{}','[]'],'structured'),('Tags',['A;B','C;D'],'delimited_list'),('Website',['https://example.com','bad'],'url'),('IP',['::1','999.1.1.1'],'ip'),('Latitude',['30','91'],'coordinate'),('When',['2024-01-01T12:00:00 America/New_York']*2,'zoned_datetime'),('unix_timestamp',['0','1000'],'numeric_timestamp'),('Reading',['1.2e3','2.5e3'],'integer')])
def test_semantic_detection(name,values,kind):
    assert detect_column_type(pd.Series(values,name=name))['type']==kind
