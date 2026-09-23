from dataclasses import replace
import numpy as np
import pandas as pd
import pytest

from stock_ranker.personalized import InvestorProfile, HistoryBook, PersonalizedEngine, xirr, simulate_raw, rank_candidates


def history(start='2010-01-01', end='2026-01-01', rate=.15, price=100.):
    dates = pd.date_range(start, end)
    return pd.DataFrame({'date': dates, 'adjusted_close': price * (1 + rate) ** ((dates - dates[0]).days / 365)})


@pytest.mark.parametrize('field,value', [('amount', 0), ('amount', -1), ('amount', float('nan')),
    ('target_cagr', -1), ('target_cagr', float('inf')), ('interval_days', 0), ('interval_days', 1.5),
    ('lookback_months', True), ('fee_bps', -1), ('fixed_fee', -2), ('horizon_months', 0)])
def test_profile_rejects_invalid(field, value):
    with pytest.raises(ValueError):
        InvestorProfile(**{field: value})


@pytest.mark.parametrize('rate', [-.7, -.2, 0, .2, 1., 5.])
def test_xirr_recovers_dated_exponential_returns(rate):
    dates = pd.to_datetime(['2020-01-01', '2020-05-17', '2021-01-01'])
    terminal = 100 * (1 + rate) ** (366 / 365) + 250 * (1 + rate) ** (229 / 365)
    assert xirr(dates, [-100, -250, terminal]) == pytest.approx(rate, abs=1e-10)


def test_xirr_ambiguous_or_zero_duration_is_unknown():
    assert xirr(['2020-01-01', '2020-01-01'], [-100, 110]) is None
    assert xirr(['2020-01-01', '2020-06-01', '2021-01-01'], [-100, 250, -140]) is None


def test_fractional_amount_scale_invariance_and_independent_xirr():
    book = HistoryBook({'A': history(), 'B': history(rate=.25)})
    a = book.simulate(InvestorProfile(), '2026-01-01')
    b = book.simulate(InvestorProfile(amount=10000), '2026-01-01')
    np.testing.assert_allclose(a.xirr, b.xirr, atol=1e-12)
    np.testing.assert_allclose(a.target_attainment, b.target_attainment, atol=1e-12)
    np.testing.assert_allclose(a.current_value * 10000 / 7500, b.current_value)
    assert a.iloc[0].xirr == pytest.approx(.15)
    assert a.iloc[0].cagr_3y == pytest.approx(.15)
    assert a.shares_bought.isna().all()


def test_no_future_or_missing_history_imputation():
    data = history()
    book = HistoryBook({'A': data, 'B': data[data.date < '2025-01-01'], 'C': data[data.date > '2025-01-01']})
    r = book.simulate(InvestorProfile(), '2026-01-01').set_index('isin')
    assert r.loc['B', 'status'] == 'STALE_TERMINAL'
    assert r.loc['C', 'status'] == 'INSUFFICIENT_HISTORY'
    assert pd.isna(r.loc['B', 'profit_loss_pct'])
    past = book.simulate(InvestorProfile(), '2024-01-01').set_index('isin')
    data.loc[data.date > '2024-01-01', 'adjusted_close'] *= 100
    changed = HistoryBook({'A': data}).simulate(InvestorProfile(), '2024-01-01')
    assert past.loc['A', 'xirr'] == changed.iloc[0].xirr


def test_duplicate_bad_prices_and_missing_execution_are_rejected():
    h = history()
    bad = h.copy(); bad.loc[4, 'adjusted_close'] = 0
    gap = h[~h.date.between('2024-01-01', '2024-04-01')]
    book = HistoryBook({'A': pd.concat([h, h.tail(1)]), 'B': bad, 'C': gap})
    r = book.simulate(InvestorProfile(), '2026-01-01')
    assert list(r.status) == ['INVALID_HISTORY', 'INVALID_HISTORY', 'MISSING_EXECUTION_PRICE']


def test_target_does_not_change_returns_or_create_weight():
    book = HistoryBook({'A': history(rate=.15)})
    a = book.simulate(InvestorProfile(target_cagr=.1), '2026-01-01').iloc[0]
    b = book.simulate(InvestorProfile(target_cagr=.3), '2026-01-01').iloc[0]
    assert a.xirr == b.xirr
    assert a.target_shortfall == 0 < b.target_shortfall
    assert a.current_value == b.current_value


def test_whole_share_cash_affordability_costs_and_ledger_gate():
    p = pd.DataFrame({'date': pd.date_range('2020-01-01', '2020-03-01'), 'raw_close': 600.})
    small = InvestorProfile(amount=100, whole_shares=True)
    with pytest.raises(ValueError, match='verified'):
        simulate_raw(p, pd.DataFrame(), small, '2020-01-01', '2020-03-01')
    r = simulate_raw(p, pd.DataFrame(), small, '2020-01-01', '2020-03-01', verified_ledger=True)
    assert r['shares_bought'] == 0 and r['unused_cash'] == 200 and r['xirr'] == pytest.approx(0, abs=1e-10)
    r = simulate_raw(p, pd.DataFrame(), replace(small, amount=1000, fixed_fee=10), '2020-01-01', '2020-03-01', verified_ledger=True)
    assert r['shares_bought'] == 3 and r['unused_cash'] == 180 and r['fees'] == 20


def test_split_economic_invariance_and_volume_constraint():
    p = pd.DataFrame({'date': pd.date_range('2020-01-01', '2020-03-01'), 'raw_close': 100., 'volume': 10.})
    p.loc[p.date >= '2020-02-01', 'raw_close'] = 50
    actions = pd.DataFrame([{'date': '2020-02-01', 'split_ratio': 2., 'dividend_per_old_share': 0.}])
    profile = InvestorProfile(amount=1000, whole_shares=True)
    r = simulate_raw(p, actions, profile, '2020-01-01', '2020-03-01', verified_ledger=True)
    assert r['current_value'] == 2000 and r['shares_bought'] == 40
    capped = simulate_raw(p, actions, profile, '2020-01-01', '2020-03-01', verified_ledger=True, max_participation=.1)
    assert capped['current_value'] == 2000 and capped['shares_bought'] == 4


def test_short_horizons_are_unknown_and_missing_family_not_zero():
    b = HistoryBook({'A': history(start='2022-01-01')})
    r = b.simulate(InvestorProfile(), '2026-01-01')
    assert r.cagr_5y.isna().all() and r.cagr_10y.isna().all()
    evidence = pd.DataFrame({'isin': ['A'], 'sector': ['X'], 'quality_score': [np.nan]})
    ranked = rank_candidates(r, [b.simulate(InvestorProfile(), '2023-01-01')], evidence)
    assert ranked.goal_score.isna().all()
    assert 'family_aggregation_score' not in ranked


def test_adjusted_data_cannot_silently_become_whole_shares():
    with pytest.raises(ValueError, match='whole shares'):
        HistoryBook({'A': history()}).simulate(InvestorProfile(whole_shares=True), '2026-01-01')


def test_cache_reuses_amount_and_target_without_mutating_results():
    engine = PersonalizedEngine(HistoryBook({'A': history()}))
    a = engine.simulate(InvestorProfile(), '2026-01-01')
    b = engine.simulate(InvestorProfile(amount=10000, target_cagr=.3), '2026-01-01')
    assert len(engine.cache) == 1
    assert b.iloc[0].current_value / a.iloc[0].current_value == pytest.approx(10000 / 7500)
    assert a.iloc[0].target_wealth != b.iloc[0].target_wealth
    a.loc[0, 'xirr'] = 123
    assert engine.simulate(InvestorProfile(), '2026-01-01').iloc[0].xirr == pytest.approx(.15)


def test_horizon_longer_than_lookback_is_insufficient():
    engine = PersonalizedEngine(HistoryBook({'A': history()}))
    r = engine.rank(InvestorProfile(lookback_months=12, horizon_months=24), '2026-01-01')
    assert r.goal_score.isna().all()
    assert r.goal_windows.eq(0).all()


def test_horizon_changes_scenario_evidence_not_amount_weights():
    dates = pd.date_range('2020-01-01', '2026-01-01')
    days = np.arange(len(dates))
    h = pd.DataFrame({'date': dates, 'adjusted_close': 100 * np.exp(.0004 * days + .5 * np.sin(days / 130))})
    engine = PersonalizedEngine(HistoryBook({'A': h}))
    a = engine.rank(InvestorProfile(horizon_months=12), '2026-01-01')
    b = engine.rank(InvestorProfile(horizon_months=24), '2026-01-01')
    assert a.iloc[0].xirr == b.iloc[0].xirr
    assert a.iloc[0].goal_score != b.iloc[0].goal_score


def test_fractional_costs_match_independent_cashflow_equation():
    profile = InvestorProfile(fixed_fee=15, fee_bps=10)
    engine = HistoryBook({'A': history()})
    r = engine.simulate(profile, '2026-01-01').iloc[0]
    schedule = pd.date_range('2023-01-01', '2025-12-31', freq='30D')
    expected = xirr([*schedule, pd.Timestamp('2026-01-01')], [-7500] * len(schedule) + [r.current_value])
    assert r.xirr == pytest.approx(expected)
    assert r.fees + r.amount_invested == pytest.approx(r.amount_contributed)


def test_ranking_metrics_ties_and_chronological_purge():
    from stock_research.personalized_validation import ranking_metrics, chronological_split
    f = pd.DataFrame({'s': [1, 1, 1], 'future_xirr': [.1, .2, .3], 'future_shortfall': [.2, .1, 0], 'future_drawdown': [-.1] * 3, 'isin': ['A', 'B', 'C']})
    assert ranking_metrics(f, 's')['pairwise_accuracy'] == .5
    panel = pd.DataFrame({'decision_date': ['2019-01-01', '2021-01-01', '2021-01-01', '2022-01-01'],
                          'endpoint': ['2020-01-01', '2021-12-01', '2022-01-01', '2023-01-01']})
    train, val = chronological_split(panel)
    assert train.tolist() == [True, False, False, False]
    assert val.tolist() == [False, False, False, True]


def test_terminal_weekend_contribution_stays_cash():
    h = history()
    h = h[h.date.dt.dayofweek < 5]
    profile = InvestorProfile(interval_days=1, lookback_months=1)
    result = HistoryBook({'A': h}).simulate(profile, '2025-08-31').iloc[0]
    assert result.status == 'AVAILABLE'
    assert result.unused_cash == profile.amount
    assert result.fees == 0
    assert result.amount_contributed == result.amount_invested + result.unused_cash


def test_current_fundamental_availability_is_enforced():
    from stock_ranker.personalized_data import current_evidence
    facts = pd.DataFrame({'isin': ['A', 'B'], 'product_sector': ['S', 'S'],
                          'screener_roce_pct': [12, 20], 'screener_pe_ratio': [10, 8],
                          'screener_source_observed_at': ['2025-01-01', '2026-01-01']})
    evidence = current_evidence(facts, knowledge_date='2025-06-01')
    assert evidence.loc[0, 'quality_score'] == 12
    assert pd.isna(evidence.loc[1, 'quality_score'])


def test_dividend_entitlement_is_not_assigned_to_later_buyers():
    p = pd.DataFrame({'date': pd.date_range('2020-01-01', '2020-03-01'), 'raw_close': 100.})
    actions = pd.DataFrame([{'date': '2020-01-15', 'split_ratio': 1., 'dividend_per_old_share': 10., 'dividend_payment_date': '2020-02-15'}])
    r = simulate_raw(p, actions, InvestorProfile(amount=1000, whole_shares=True), '2020-01-01', '2020-03-01', verified_ledger=True)
    assert r['current_value'] == 2100  # Ten shares eligible, not the twenty held at payment.
    assert r['unused_cash'] == 100
    actions['dividend_payment_date'] = '2020-04-01'
    r = simulate_raw(p, actions, InvestorProfile(amount=1000, whole_shares=True), '2020-01-01', '2020-03-01', verified_ledger=True)
    assert r['unused_cash'] == 0 and r['dividend_receivable_at_face_value'] == 100


def test_professor_spend_denominator_is_separate_from_contributed_money():
    from stock_ranker.personalized_benchmark import professor_purchase_benchmark
    r = professor_purchase_benchmark([60, 80], 100, 100, verified_raw_basis=True)
    assert r['shares_bought'] == 2 and r['average_price'] == 70
    assert r['amount_invested'] == 140 and r['amount_allocated'] == 200
    assert r['profit_loss_pct'] == pytest.approx(200 / 140 - 1)
    r = professor_purchase_benchmark([60, 80], 100, None, verified_raw_basis=True)
    assert r['profit_loss_pct'] is None


def test_new_benchmark_preserves_unknown_cache(tmp_path):
    from test_professor_strategy import _workbook
    from stock_ranker.personalized_benchmark import professor_benchmark
    from zipfile import ZipFile
    # Minimal source including the referenced history sheet.
    p = tmp_path / 'reference.xlsx'
    _workbook(p)
    with ZipFile(p) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    parts['xl/workbook.xml'] = parts['xl/workbook.xml'].decode().replace('</sheets>', '<sheet name="StockHistoryData" sheetId="4" r:id="rId4"/></sheets>').encode()
    parts['xl/_rels/workbook.xml.rels'] = parts['xl/_rels/workbook.xml.rels'].decode().replace('</Relationships>', '<Relationship Id="rId4" Type="worksheet" Target="worksheets/sheet4.xml"/></Relationships>').encode()
    with ZipFile(p, 'w') as z:
        for name, value in parts.items():
            z.writestr(name, value)
        z.writestr('xl/worksheets/sheet4.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
    frame, audit = professor_benchmark(p)
    assert frame.profit_loss_pct.isna().all()
    assert audit['source_is_instruction'] is False


def test_personalized_cli_rejects_invalid_profile_without_writing(tmp_path, capsys):
    from stock_ranker.cli import main
    out = tmp_path / 'new'
    assert main(['personalized', '--amount', '-1', '--output', str(out)]) == 2
    assert not out.exists()
    assert 'Error:' in capsys.readouterr().err


def test_exact_identity_and_listing_gate(tmp_path):
    from stock_ranker.personalized_data import load_history_book
    h = history(start='2020-01-01')
    h.to_csv(tmp_path / 'A.csv', index=False)
    facts = pd.DataFrame({'isin': ['ID'], 'ticker': ['A'], 'listing_date': ['2025-01-01']})
    book, hashes = load_history_book(facts, tmp_path)
    assert book.arrays['ID'][0][0] == np.datetime64('2025-01-01')
    assert len(hashes['A.csv']) == 64
    assert book.simulate(InvestorProfile(), '2026-01-01').iloc[0].status == 'INSUFFICIENT_HISTORY'
    with pytest.raises(ValueError, match='identities'):
        load_history_book(pd.concat([facts, facts]), tmp_path)
    facts['ticker'] = '../escape'
    with pytest.raises(ValueError, match='unsafe'):
        load_history_book(facts, tmp_path)


def test_history_book_applies_frozen_terminal_repair(tmp_path):
    from stock_ranker.personalized_data import load_history_book
    pd.DataFrame({
        'date': ['2020-01-01', '2020-01-02'],
        'adjusted_close': [10.0, 11.0],
    }).to_csv(tmp_path / 'A.csv', index=False)
    facts = pd.DataFrame({'isin': ['ID'], 'ticker': ['A'], 'listing_date': [None]})
    repairs = pd.DataFrame([{
        'isin': 'ID', 'ticker': 'A', 'appended_date': '2020-01-10', 'appended_price': 12.5,
    }])
    book, _ = load_history_book(facts, tmp_path, terminal_repairs=repairs)
    assert str(book.arrays['ID'][0][-1]) == '2020-01-10'
    assert book.arrays['ID'][1][-1] == 12.5


def test_models_are_deterministic_and_never_impute_unrankable_securities():
    pytest.importorskip('sklearn')
    from stock_research.personalized_validation import FEATURES, fit_challengers
    rng = np.random.default_rng(1)
    frames = []
    for year in (2017, 2019, 2022):
        data = pd.DataFrame(rng.normal(size=(30, len(FEATURES))), columns=FEATURES)
        data['isin'] = [str(i) for i in range(30)]
        data['profile_name'] = 'P'
        data['decision_date'], data['endpoint'] = f'{year}-01-01', f'{year+1}-01-01'
        data['future_xirr'] = rng.normal(size=30)
        frames.append(data)
    panel = pd.concat(frames, ignore_index=True)
    panel.loc[panel.index[-1], 'xirr_score'] = np.nan
    a, audit_a = fit_challengers(panel)
    b, audit_b = fit_challengers(panel)
    pd.testing.assert_frame_equal(a, b)
    assert audit_a == audit_b
    assert pd.isna(a.iloc[-1].ridge_personalized_score)
    # Validation labels cannot affect fitted scores or training clusters.
    panel.loc[panel.decision_date.ge('2022'), 'future_xirr'] *= -100
    c, _ = fit_challengers(panel)
    np.testing.assert_allclose(a.ridge_personalized_score, c.ridge_personalized_score, equal_nan=True)


def test_personalized_cli_exports_complete_universe(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import json
    import stock_ranker.personalized_cli as cli
    facts = pd.DataFrame({'isin': ['A', 'B'], 'ticker': ['ONE', 'TWO'], 'company': ['One', 'Two'],
                          'listing_date': ['2010-01-01'] * 2, 'trade_date': ['2026-01-01'] * 2,
                          'product_sector': ['Sector'] * 2})
    monkeypatch.setattr(cli, 'resolve_company_fact_snapshot', lambda _: tmp_path)
    monkeypatch.setattr(cli, 'load_company_fact_snapshot', lambda _: SimpleNamespace(facts=facts))
    (tmp_path / 'accepted_state.json').write_text(json.dumps({'accepted_at': '2026-01-02T00:00:00Z'}))
    history().to_csv(tmp_path / 'ONE.csv', index=False)
    out = tmp_path / 'result'
    assert cli.main(['--state-root', str(tmp_path), '--history-root', str(tmp_path), '--output', str(out)]) == 0
    rows = pd.read_csv(out / 'rankings.csv')
    assert len(rows) == 2 and rows.loc[1, 'status'] == 'INVALID_HISTORY'
    assert pd.isna(rows.loc[1, 'goal_score'])
    assert (out / 'manifest.json').is_file()
    with pytest.raises(ValueError, match='fresh'):
        cli.main(['--output', str(out)])
