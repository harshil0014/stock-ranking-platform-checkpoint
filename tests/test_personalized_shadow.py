import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from stock_research import personalized_shadow as shadow


def inputs(actions=(), prices=None):
    prices = prices if prices is not None else pd.DataFrame({'isin': ['P'] * 4, 'date': pd.to_datetime(['2026-09-26','2026-10-26','2026-11-25','2026-12-26']), 'close': [10.,10.,10.,10.]})
    columns = ['event_id','isin','ex_date','type','numerator','denominator','child_isin','cash_per_share','payment_date','fraction_cash_per_share','fraction_payment_date','source_sha256']
    events = pd.DataFrame(actions, columns=columns)
    events['ex_date'] = pd.to_datetime(events.ex_date)
    coverage = pd.DataFrame({'isin': ['P','C','D'], 'through_date': pd.to_datetime(['2026-12-26'] * 3)}).set_index('isin')
    return prices, events, coverage


def simulate(actions=(), prices=None, amount=105):
    return shadow.simulate('P', 'base', {'amount': amount, 'interval_days': 30, 'target_cagr': .2}, '2026-09-26', '2026-12-26', *inputs(actions, prices))


def action(kind, day='2026-10-26', num='', den='', child='', cash='', paid='', fraction='', fraction_paid=''):
    return [kind+child, 'P', day, kind, num, den, child, cash, paid, fraction, fraction_paid, 'a'*64]


def test_cash_carry_and_no_future_quote_needed_for_last_pending_contribution():
    result, journal = simulate()
    assert result['status'] == 'AVAILABLE'
    assert result['contributed'] == 420
    assert result['primary_wealth'] == 420
    assert result['cash'] == 0
    assert sum(r.get('spent', 0) for r in journal) == 420


def test_ex_date_buyer_does_not_receive_split_entitlement():
    result, _ = simulate([action('SPLIT', num=2, den=1)], amount=100)
    assert result['positions'][0]['shares'] == 50  # first 10 doubled, three later purchases of 10


def test_rights_lapse_never_adds_shares_or_cash():
    result, _ = simulate([action('RIGHTS_LAPSE')], amount=100)
    assert result['primary_wealth'] == 400
    assert result['positions'][0]['shares'] == 40


def test_fraction_unknown_blocks_without_synthetic_cash():
    result, _ = simulate([action('CONSOLIDATION', num=1, den=3)], amount=100)
    assert result['status'] == 'BLOCKED'
    assert 'UNKNOWN_FRACTION_SETTLEMENT' in result['reasons']
    assert result['primary_wealth'] is None


def test_fraction_cash_arrives_on_payment_date():
    result, journal = simulate([action('CONSOLIDATION', num=1, den=3, fraction=30, fraction_paid='2026-11-01')], amount=100)
    receipt = [r for r in journal if r['kind'] == 'CASH_RECEIPT'][0]
    assert receipt['date'] == '2026-11-01'
    assert receipt['cash_received'] == 10
    assert result['status'] == 'AVAILABLE'


def test_separate_child_and_multiple_resulting_entitlements():
    prices, _, _ = inputs()
    prices = pd.concat([prices, pd.DataFrame({'isin':['C','D'], 'date':pd.to_datetime(['2026-12-26']*2), 'close':[3.,4.]})])
    result, _ = simulate([action('DEMERGER',num=1,den=1,child='C'), action('DEMERGER',num=1,den=1,child='D')], prices, amount=100)
    assert result['primary_wealth'] == 470
    assert {r['isin']:r['shares'] for r in result['positions']} == {'P':40,'C':10,'D':10}


def test_dividends_recorded_separately_without_changing_primary_policy():
    result, _ = simulate([action('CASH_DIVIDEND',cash=2,paid='2026-11-01')], amount=100)
    assert result['primary_wealth'] == 400
    assert result['dividend_cash_excluded_from_primary'] == 20
    assert result['wealth_including_received_dividends'] == 420


def test_cash_exit_preserves_future_contributions_in_cash():
    result, _ = simulate([action('CASH_EXIT',cash=12,paid='2026-11-01')], amount=100)
    assert result['primary_wealth'] == 420
    assert result['cash'] == 420
    assert result['positions'] == []


def test_unknown_action_and_missing_terminal_never_drop_selected_security():
    result, _ = simulate([action('UNRESOLVED')])
    assert result['status'] == 'BLOCKED'
    prices, _, _ = inputs(); prices = prices.iloc[:2]
    result, _ = simulate(prices=prices)
    assert 'MISSING_TERMINAL_PRICE:P' in result['reasons']
    assert 'MISSING_EXECUTION_PRICE' in result['reasons']


def test_manifest_detects_mutation_extra_file_and_path_escape(tmp_path):
    (tmp_path/'a').write_text('good'); shadow.seal(tmp_path); shadow.verify(tmp_path)
    (tmp_path/'a').write_text('bad')
    with pytest.raises(ValueError,match='drift'):shadow.verify(tmp_path)
    shadow.seal(tmp_path);(tmp_path/'extra').write_text('extra')
    with pytest.raises(ValueError,match='Undeclared'):shadow.verify(tmp_path)


def minimal_freeze(root):
    root.mkdir()
    config = {'challenger_commit':'d4995807163bef1ec4b297179e6c54a59c71f390','weights':[.67,.33],'engine_sha256':shadow.digest(shadow.__file__),'prediction_as_of':'2026-09-18','latest_training_endpoint':'2026-06-30','prospective_origin':'2026-09-26','checkpoints':{'3':'2026-12-26'},'profiles':{'base':{'amount':100,'interval_days':30,'target_cagr':.2}}}
    shadow.write_json(root/'config.json',config)
    pd.DataFrame({'decision_date':['2026-09-18'],'future_xirr':[np.nan]}).to_csv(root/'rankings.csv.gz',index=False)
    pd.DataFrame({'profile':['base'],'strategy':['challenger'],'isin':['P']}).to_csv(root/'selections.csv',index=False)
    shadow.seal(root)


def evidence(root, future=False):
    root.mkdir();(root/'sources').mkdir();source=root/'sources'/'observations.txt';source.write_text('test evidence')
    prices, actions, coverage = inputs()
    if future: prices.loc[0,'date']=pd.Timestamp('2027-01-01')
    for frame in [prices,actions]:
        frame['source_url']='fixture://observations';frame['source_sha256']=shadow.digest(source)
    coverage=coverage.reset_index();coverage['price_basis']='OBSERVED_NOMINAL_CLOSE';coverage['action_status']='COMPLETE';coverage['source_url']='fixture://observations';coverage['source_sha256']=shadow.digest(source)
    prices.to_csv(root/'prices.csv',index=False);actions.to_csv(root/'actions.csv',index=False);coverage.to_csv(root/'coverage.csv',index=False)


def test_end_to_end_deterministic_idempotent_and_revision_guard(tmp_path):
    freeze=tmp_path/'freeze';obs=tmp_path/'obs';minimal_freeze(freeze);evidence(obs)
    out=tmp_path/'result';result=shadow.evaluate(freeze,obs,3,out,today='2026-12-27')
    assert result['complete_security_profiles']==1
    original=shadow.digest(out/'manifest.json')
    assert shadow.evaluate(freeze,obs,3,out,today='2027-01-01')==result
    assert shadow.digest(out/'manifest.json')==original
    shadow.evaluate(freeze,obs,3,tmp_path/'repeat',today='2026-12-27')
    assert shadow.digest(tmp_path/'repeat'/'manifest.json')==original
    (obs/'sources'/'new').write_text('revision')
    with pytest.raises(ValueError,match='different inputs'):shadow.evaluate(freeze,obs,3,out,today='2026-12-27')


def test_early_checkpoint_future_evidence_and_original_label_leakage_rejected(tmp_path):
    freeze=tmp_path/'freeze';obs=tmp_path/'obs';minimal_freeze(freeze);evidence(obs,True)
    with pytest.raises(ValueError,match='not closed'):shadow.evaluate(freeze,obs,3,tmp_path/'result',today='2026-12-26')
    with pytest.raises(ValueError,match='post-checkpoint'):shadow.evaluate(freeze,obs,3,tmp_path/'result',today='2026-12-27')
    pd.DataFrame({'decision_date':['2026-09-18'],'future_xirr':[.1]}).to_csv(freeze/'rankings.csv.gz',index=False);shadow.seal(freeze)
    with pytest.raises(ValueError,match='contaminated'):shadow.load_freeze(freeze)


def test_incomplete_coverage_suppresses_aggregate(tmp_path):
    freeze=tmp_path/'freeze';obs=tmp_path/'obs';minimal_freeze(freeze);evidence(obs)
    coverage=pd.read_csv(obs/'coverage.csv');coverage['through_date']='2026-12-01';coverage.to_csv(obs/'coverage.csv',index=False)
    result=shadow.evaluate(freeze,obs,3,tmp_path/'result',today='2026-12-27')
    assert result['metrics'][0]['status']=='INCOMPLETE_NO_AGGREGATE'
    assert result['metrics'][0]['mean_shortfall'] is None


@pytest.mark.parametrize('months,end',['3,2026-12-26'.split(','),'6,2027-03-26'.split(','),'12,2027-09-26'.split(',')])
def test_all_registered_horizons_preserve_cash_and_contribution_schedule(months,end):
    days=pd.date_range('2026-09-26',end)
    prices=pd.DataFrame({'isin':['P']*len(days),'date':days,'close':13.})
    _,events,coverage=inputs();coverage['through_date']=pd.Timestamp(end)
    result,_=shadow.simulate('P','base',{'amount':105,'interval_days':30,'target_cagr':.2},'2026-09-26',end,prices,events,coverage)
    expected=len(pd.date_range('2026-09-26',pd.Timestamp(end)-pd.Timedelta(days=1),freq='30D'))*105
    assert result['status']=='AVAILABLE'
    assert result['contributed']==expected
    assert result['primary_wealth']==expected
    assert result['purchase_spend']+result['cash']==expected


def test_pending_mandatory_cash_is_not_pretended_to_be_received():
    result,_=simulate([action('CASH_EXIT',cash=12,paid='2027-01-10')],amount=100)
    assert result['status']=='BLOCKED'
    assert result['cash']==300
    assert result['pending_receivables'][0]['amount']==120


def test_missing_raw_source_evidence_is_rejected(tmp_path):
    obs=tmp_path/'obs';evidence(obs)
    (obs/'sources'/'observations.txt').write_text('changed')
    with pytest.raises(ValueError,match='source is not preserved'):
        shadow.load_evidence(obs,pd.Timestamp('2026-12-26'))
