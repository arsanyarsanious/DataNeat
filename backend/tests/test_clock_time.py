import pandas as pd
import pytest
from app.core.clock_time import format_clock_time, parse_clock_time
from app.core.profiler import profile_dataframe
from app.core.interactive import annotate, propose
from app.models.requests import EditorRequest


@pytest.mark.parametrize('value,expected', [('2:30 PM','14:30:00'),('12:00 AM','00:00:00'),('12:00 PM','12:00:00'),('8 PM','20:00:00'),('08:30 a.m.','08:30:00'),('23:59:59.125','23:59:59.125'),('0:00','00:00:00')])
def test_clock_input(value, expected):
    assert format_clock_time(value)==expected


@pytest.mark.parametrize('value,expected', [('00:00','12:00:00 AM'),('12:00','12:00:00 PM'),('14:30','02:30:00 PM'),('23:59:59.125','11:59:59.125 PM')])
def test_twelve_hour_output(value, expected):
    assert format_clock_time(value,'12_hour')==expected
    assert parse_clock_time(expected)==parse_clock_time(value)


@pytest.mark.parametrize('value', ['24:00','25:15:00','13:00 PM','00:00 AM','1:60 PM','1:00:60','2:30 PM garbage','PT45M','45 min','2024-01-01 14:00','14:00+02:00','14'])
def test_invalid_or_different_semantics(value):
    with pytest.raises(ValueError):
        parse_clock_time(value)


def test_clock_column_scope_and_duration_separation():
    df=pd.DataFrame({'Shift_Start':['08:30:00','8:30 PM','12:00 AM','25:15',None], 'Elapsed_Duration':['27:15:00','PT45M','45 min','01:00:00',None]})
    report=profile_dataframe(df)
    assert [c['detected_type'] for c in report['columns']]==['time','duration']
    assert 'case_inconsistency' not in [i['issue'] for i in report['columns'][0]['issues']]
    flags=annotate(df,report,df)
    assert flags[1][0][0]['kind']=='time'
    assert flags[3][0][0]['kind']=='invalid_time'
    body=EditorRequest(revision=0,column='Shift_Start',row_index=1,action='normalize_time',scope='column',parameters={'format':'24_hour'})
    result,detail=propose(df,body,report)
    assert result.Shift_Start.tolist()==['08:30:00','20:30:00','00:00:00','25:15',None]
    assert result.Elapsed_Duration.equals(df.Elapsed_Duration)
    assert detail['changed_cells']==2
    one,_=propose(df,body.model_copy(update={'scope':'cell'}),report)
    assert one.Shift_Start[2]=='12:00 AM'
    twelve,_=propose(result,body.model_copy(update={'parameters':{'format':'12_hour'}}))
    assert twelve.Shift_Start.tolist()==['08:30:00 AM','08:30:00 PM','12:00:00 AM','25:15',None]
    assert 'time_format' not in [i['issue'] for i in profile_dataframe(twelve)['columns'][0]['issues']]


def test_clock_option_validation():
    with pytest.raises(ValueError):
        EditorRequest(revision=0,column='Time',row_index=0,action='normalize_time',parameters={'format':'nonsense'})


def test_clock_editor_conversion_and_undo():
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    fid=client.post('/api/files/upload',files={'file':('clock.csv',b'Shift_Start\n8:30 PM\n12:00 AM\n14:00:00\n25:15\n','text/csv')}).json()['file_id']
    assert client.post(f'/api/files/{fid}/editor/start').status_code==200
    body=dict(revision=0,column='Shift_Start',row_index=0,scope='column',action='normalize_time',parameters={'format':'24_hour'},confirmed=True)
    response=client.post(f'/api/files/{fid}/editor/fix',json=body)
    assert response.status_code==200,response.text
    after=client.get(f'/api/files/{fid}/editor').json()
    assert [r[0] for r in after['preview']['rows']]==['20:30:00','00:00:00','14:00:00','25:15']
    change=after['changes'][-1]['id']
    assert client.post(f'/api/files/{fid}/editor/undo/{change}?revision=1').status_code==200
    assert client.get(f'/api/files/{fid}/editor').json()['preview']['rows'][0][0]=='8:30 PM'
