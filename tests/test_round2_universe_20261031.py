from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from round2_universe_20261031 import key,reconstruct,members_on,extract_pdf_events

def test_membership_excludes_on_effective_exit_day():
    events=pd.DataFrame([dict(company='A Ltd.',company_key='A',action='INCLUDE',effective_date='2012-01-01'),dict(company='A Ltd.',company_key='A',action='EXCLUDE',effective_date='2012-03-01')])
    intervals,errors,counts=reconstruct(events)
    assert len(members_on(intervals,'2012-02-29'))==1
    assert len(members_on(intervals,'2012-03-01'))==0
    assert errors.empty

def test_unknown_exclusion_is_retained_as_error_not_a_phantom_member():
    e=pd.DataFrame([dict(company='Former Ltd.',company_key='FORMER',action='EXCLUDE',effective_date='2012-03-01')])
    intervals,errors,counts=reconstruct(e)
    assert intervals.empty
    assert errors.error.tolist()==['EXCLUSION_WITHOUT_VERIFIED_ACTIVE_IDENTITY']

def test_normalization_is_not_an_unverified_rename_resolver():
    assert key('ABC Limited')==key('Abc Ltd.')
    assert key('Old Issuer Ltd.')!=key('New Issuer Ltd.')

def test_parser_stops_at_other_index_section():
    text='Changes effective from September 28, 2012\n(5) S&P CNX 500 Index\nThe following companies are being excluded:\n 1  Former Ltd.    FORMER\nThe following companies are being included:\n 1  New Ltd.    NEW\n(6) CNX Midcap Index\nThe following companies are being excluded:\n 1  Wrong Ltd.    WRONG'
    rows=extract_pdf_events(text,'2012-08-16','https://niftyindices.com/example.pdf')
    assert [r['symbol'] for r in rows]==['FORMER','NEW']
    assert all(r['effective_date']=='2012-09-28' for r in rows)

def test_no_snapshot_gap_interpolation_in_event_registry():
    events=pd.DataFrame([dict(company='A',company_key='A',action='INCLUDE',effective_date='2012-03-01'),dict(company='B',company_key='B',action='INCLUDE',effective_date='2014-03-01')])
    intervals,_,_=reconstruct(events)
    assert set(members_on(intervals,'2013-01-01').company_key)=={'A'}
