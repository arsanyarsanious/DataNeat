import pandas as pd
import pytest
from app.core.duration import parse_duration, format_duration
from app.core.profiler import profile_dataframe
from app.core.interactive import annotate, propose
from app.models.requests import EditorRequest


@pytest.mark.parametrize('value,expected', [('PT45M','00:45:00'),('45 min','00:45:00'),('P1DT3H15M','27:15:00'),('27:15:00','27:15:00'),('1.5 hours','01:30:00'),('PT0S','00:00:00'),('PT1.25S','00:00:01.25')])
def test_duration_format(value, expected):
    assert format_duration(value) == expected


@pytest.mark.parametrize('value', ['25:99:00','PT','P1M','-45 min','45','08:30 PM','P1DT'])
def test_ambiguous_or_invalid_duration(value):
    with pytest.raises(ValueError):
        parse_duration(value)


@pytest.mark.parametrize('value,expected', [
    ('1 day 3 hours', '27:00:00'),
    ('2 hours 30 minutes', '02:30:00'),
    ('1 day, 2 hours and 3 minutes', '26:03:00'),
    ('1d3h30m15s', '27:30:15'),
    ('2 HRS 30 MINS 1.25 SECS', '02:30:01.25'),
    ('0 days 0 hours 0 minutes', '00:00:00'),
    ('1.5 hours 30 minutes', '02:00:00'),
    ('30 minutes and 90 seconds', '00:31:30'),
])
def test_compound_duration(value, expected):
    assert format_duration(value) == expected


@pytest.mark.parametrize('value', ['1 hour -30 minutes', '1 hour tomorrow', '1 day 3', '1 hour and', '1 hour,', '1 month 2 days', '1 hour or 2 minutes'])
def test_compound_duration_rejects_partial_parsing(value):
    with pytest.raises(ValueError):
        parse_duration(value)


def test_compound_duration_column_correction():
    df=pd.DataFrame({'Elapsed_Duration':['1 day 3 hours','2 hours 30 minutes','01:00:00','1 hour unknown']})
    report=profile_dataframe(df)
    assert report['columns'][0]['detected_type']=='duration'
    body=EditorRequest(revision=0,column='Elapsed_Duration',row_index=0,scope='column',action='normalize_duration')
    result,detail=propose(df,body,report)
    assert result.Elapsed_Duration.tolist()==['27:00:00','02:30:00','01:00:00','1 hour unknown']
    assert detail['changed_cells']==2


def test_duration_detection_correction_scope_and_invalid_preservation():
    df=pd.DataFrame({'Elapsed_Duration':['01:45:00','PT45M','45 min','27:15:00','bad',None], 'Other':['keep']*6})
    report=profile_dataframe(df)
    column=report['columns'][0]
    assert column['detected_type']=='duration'
    assert 'case_inconsistency' not in [i['issue'] for i in column['issues']]
    flags=annotate(df,report,df)
    assert [i['kind'] for i in flags[1][0]]==['duration']
    assert [i['kind'] for i in flags[4][0]]==['invalid_duration']
    request=EditorRequest(revision=0,column='Elapsed_Duration',row_index=1,action='normalize_duration',scope='column')
    changed,details=propose(df,request,report)
    assert changed.Elapsed_Duration.tolist()==['01:45:00','00:45:00','00:45:00','27:15:00','bad',None]
    assert details['changed_cells']==2
    one,_=propose(df,request.model_copy(update={'scope':'cell'}),report)
    assert one.Elapsed_Duration[2]=='45 min'
    assert changed.Other.equals(df.Other)
    assert df.Elapsed_Duration[1]=='PT45M'


def test_duration_editor_apply_and_undo():
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    data='Elapsed_Duration,Other\n01:45:00,a\nPT45M,b\n45 min,c\n27:15:00,d\nbad,e\n'
    uploaded=client.post('/api/files/upload', files={'file':('durations.csv',data.encode(),'text/csv')})
    assert uploaded.status_code==200
    fid=uploaded.json()['file_id']
    assert client.post(f'/api/files/{fid}/editor/start').status_code==200
    # Simulate a file saved before duration support with stale text findings.
    from app.main import store
    record=store.get(fid,client.cookies.get('dataneat_session'))
    record.pop('analysis_schema_version',None)
    record['editor_profile']['columns'][0]['detected_type']='category'
    record['workflow_raw_profile']=record['editor_profile']
    record['workflow_annotations']={'Elapsed_Duration':{1:[{'kind':'capitalization','message':'Old cache'}]},'Other':{}}
    store.save(record)
    sheet=client.get(f'/api/files/{fid}/editor').json()
    assert sheet['profile']['columns'][0]['detected_type']=='duration'
    assert sheet['preview']['cell_issues'][1][0][0]['kind']=='duration'
    migrated=store.get(fid,client.cookies.get('dataneat_session'))
    # This legacy editor record retains its separate detection schema.
    assert migrated['analysis_schema_version']==5
    assert migrated['editor_revision']==0
    assert migrated['editor_df'].Elapsed_Duration[1]=='PT45M'
    body=dict(revision=0,column='Elapsed_Duration',row_index=1,action='normalize_duration',scope='column',confirmed=True)
    applied=client.post(f'/api/files/{fid}/editor/fix',json=body)
    assert applied.status_code==200, applied.text
    assert applied.json()['proposal']['changed_cells']==2
    after=client.get(f'/api/files/{fid}/editor').json()
    assert after['preview']['rows'][1][0]=='00:45:00'
    assert after['preview']['rows'][3][0]=='27:15:00'
    assert after['preview']['rows'][4][0]=='bad'
    change=after['changes'][-1]['id']
    assert client.post(f'/api/files/{fid}/editor/undo/{change}?revision=1').status_code==200
    restored=client.get(f'/api/files/{fid}/editor').json()
    assert restored['preview']['rows'][1][0]=='PT45M'


def test_saved_workflow_detection_upgrades_without_data_or_history_changes():
    from fastapi.testclient import TestClient
    from app.main import app, store
    client=TestClient(app)
    fid=client.post('/api/files/upload',files={'file':('dur.csv',b'Elapsed_Duration\n00:45:00\nPT45M\n45 min\n','text/csv')}).json()['file_id']
    assert client.post(f'/api/files/{fid}/workflow/init').status_code==200
    record=store.get(fid,client.cookies.get('dataneat_session'))
    before=record['editor_df'].copy(deep=True)
    history=record['editor_changes'].copy()
    record.pop('analysis_schema_version',None)
    record['editor_profile']['columns'][0]['detected_type']='category'
    record['workflow_annotations']={'Elapsed_Duration':{1:[{'kind':'capitalization','message':'Old cache'}]}}
    record['_workflow_dirty']=set()
    store.save(record)
    response=client.get(f'/api/files/{fid}/editor')
    assert response.status_code==200
    assert response.json()['profile']['columns'][0]['detected_type']=='duration'
    assert response.json()['preview']['cell_issues'][1][0][0]['kind']=='duration'
    after=store.get(fid,client.cookies.get('dataneat_session'))
    assert after['editor_df'].equals(before)
    assert after['editor_changes']==history
    assert after['analysis_schema_version']==8
