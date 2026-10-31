import pandas as pd
import pytest
from app.core.imputation import impute_missing_values


def fill(values,**settings):
    return impute_missing_values(pd.DataFrame({'Date':values}),'Date','date_sequence',{'order_by':'__sheet_order__','single_entity':True,**settings})


@pytest.mark.parametrize('values,expected',[
 (['2024-01-01',None,'2024-01-03','2024-01-04',None,'2024-01-06'],['2024-01-01','2024-01-02','2024-01-03','2024-01-04','2024-01-05','2024-01-06']),
 (['2024-01-01',None,'2024-01-07','2024-01-10'],['2024-01-01','2024-01-04','2024-01-07','2024-01-10']),
 (['2024-01-01',None,'2024-01-15','2024-01-22'],['2024-01-01','2024-01-08','2024-01-15','2024-01-22']),
 (['2024-01-31',None,'2024-03-31','2024-04-30'],['2024-01-31','2024-02-29','2024-03-31','2024-04-30']),
 (['2020-02-29',None,'2022-02-28','2023-02-28'],['2020-02-29','2021-02-28','2022-02-28','2023-02-28']),
 (['2024-01-01T08:00:00',None,'2024-01-01T12:00:00','2024-01-01T14:00:00'],['2024-01-01T08:00:00','2024-01-01T10:00:00','2024-01-01T12:00:00','2024-01-01T14:00:00']),
])
def test_different_date_patterns(values,expected):
    result,detail=fill(values)
    assert result.Date.tolist()==expected
    assert detail['imputed_count']==sum(v is None for v in values)
    assert detail['detected_pattern']['observed_points']>=3


def test_slash_dates_preserve_user_interpretation_and_scope():
    values=['01/01/2024',None,'03/01/2024','04/01/2024',None,'06/01/2024']
    result,detail=fill(values,date_interpretation='day_first',_target_rows=[1])
    assert result.Date.tolist()==['01/01/2024','02/01/2024','03/01/2024','04/01/2024',None,'06/01/2024']
    assert detail['date_output_format']=='DD/MM/YYYY'
    assert detail['imputed_cells'][0]['row_index']==1


@pytest.mark.parametrize('values',[
 ['2024-01-01',None,'2024-01-04','2024-01-05'],
 ['2024-01-01',None,'2024-01-03'],
 ['2024-01-01',None,'2024-02-30','2024-01-04'],
 ['01/02/2024',None,'03/02/2024','04/02/2024'],
 ['2024-01-01',None,'2024-01-02','2024-01-03'],
])
def test_no_guess_when_pattern_invalid_ambiguous_or_too_weak(values):
    with pytest.raises(ValueError): fill(values)


def test_no_extrapolation_or_estimate_feedback():
    result,detail=fill([None,'2024-01-01',None,'2024-01-03','2024-01-04',None],pattern_min_coverage=50)
    assert result.Date.tolist()==[None,'2024-01-01','2024-01-02','2024-01-03','2024-01-04',None]
    with pytest.raises(ValueError,match='at least three'):
        fill(['2024-01-01',None,'2024-01-03','2024-01-04'],_excluded_rows=[2])


def test_relative_support_rejects_sparse_large_dataset():
    values=['2024-01-01',None,'2024-01-03','2024-01-04']+[None]*996
    with pytest.raises(ValueError,match='Insufficient original date evidence'):
        fill(values)
    # The same three observations support a small sequence, not 1,000 rows.
    result,audit=fill(values[:4])
    assert result.Date[1]=='2024-01-02'
    assert audit['detected_pattern']['observed_coverage_percent']==75


def test_minimum_coverage_setting():
    values=['2024-01-01',None,'2024-01-03','2024-01-04',None,'2024-01-06']
    with pytest.raises(ValueError,match='Insufficient original date evidence'):
        fill(values,pattern_min_coverage=75)
    assert fill(values,pattern_min_coverage=60)[1]['imputed_count']==2


def test_group_order_and_failure_isolation():
    df=pd.DataFrame({'Date':['2024-01-04',None,'2024-01-01','2024-01-03','2024-01-01',None,'bad','2024-01-04'], 'Group':['A']*4+['B']*4, 'Sequence':[4,2,1,3,1,2,3,4]})
    result,detail=impute_missing_values(df,'Date','date_sequence',{'order_by':'Sequence','group_by':['Group']})
    assert result.Date[1]=='2024-01-02'
    assert result.Date[5] is None
    assert detail['failures'] and detail['imputed_count']==1
    assert result.Sequence.equals(df.Sequence)
