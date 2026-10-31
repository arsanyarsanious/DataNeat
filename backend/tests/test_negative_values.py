import pandas as pd
import pytest
from app.core.negative_values import is_negative, absolute_values
from app.core.interactive import propose
from app.models.requests import EditorRequest


@pytest.mark.parametrize('value,expected', [('-5','5'),('-5.50','5.50'),('USD -1,200.00','USD 1,200.00'),('-5 %','5 %'),('-5 K','5 K'),('\u22125','5'),('-1e-3','1e-3'),(-4,4)])
def test_negative_conversion_preserves_magnitude_and_notation(value,expected):
    assert is_negative(value)
    assert absolute_values(pd.Series([value],dtype=object))[0]==expected


@pytest.mark.parametrize('value', ['1e-3','ID-5','2024-01-01','PT45M',None,'',0,'-0','5 K','unknown'])
def test_unrelated_values_are_preserved(value):
    assert not is_negative(value)
    result=absolute_values(pd.Series([value],dtype=object))[0]
    assert result is None if value is None else result==value


def test_absolute_scope():
    df=pd.DataFrame({'Temperature':['-5','-2','0','unknown'], 'Other':['-3']*4})
    body=EditorRequest(revision=0,column='Temperature',row_index=0,action='absolute_values',scope='cell')
    one,_=propose(df,body)
    assert one.Temperature.tolist()==['5','-2','0','unknown']
    all_rows,_=propose(df,body.model_copy(update={'scope':'column'}))
    assert all_rows.Temperature.tolist()==['5','2','0','unknown']
    assert all_rows.Other.equals(df.Other)
