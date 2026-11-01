"""Integrity review and compact report; does not fit or select any model."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/new-information-20261101';WORK=ROOT/'work/new-information-20261101'


def table(x):
    return '| '+' | '.join(x.columns)+' |\n| '+' | '.join(['---']*len(x.columns))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in x.itertuples(index=False,name=None))


def main():
    checks=[]
    def check(name,value):
        checks.append(dict(check=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    for filename,receipt in [('new_information_20261101.md','protocol_receipt.json'),('delivery_implementation_20261101.md','delivery_protocol_receipt.json')]:
        check('frozen protocol hash '+filename,hashlib.sha256((ROOT/'research/protocols'/filename).read_bytes()).hexdigest()==json.loads((OUT/receipt).read_text())['sha256'])
    z=pd.read_csv(OUT/'execution_replay.csv');fail=pd.read_csv(OUT/'execution_failures.csv');scope=json.loads((OUT/'execution_scope.json').read_text())
    check('all112 planned executions accounted',len(z)+len(fail)==scope['planned']==112)
    check('first fills strictly after forecast date',z.first_fill_min.gt(z.decision_date).all())
    check('unique portfolio observations',not z.duplicated(['decision_date','model','policy']).any())
    coverage=pd.read_csv(OUT/'delivery_coverage.csv');panel=pd.read_pickle(WORK/'delivery_panel.pkl.gz',compression='gzip')
    check('source sessions strictly before feature cutoff',coverage.source_session.lt(coverage.decision_date).all())
    check('coverage gates enforced',(coverage.loc[coverage.status.eq('COMPLETE'),'matched']>=500).all())
    check('new labels strictly after forecast',panel.label_end.gt(panel.decision_date).all())
    check('identity-date unique panel',not panel.duplicated(['isin','decision_date']).any())
    gate=json.loads((OUT/'delivery_gate.json').read_text())
    check('development kill keeps exposed performance unopened',not gate['exposed_evaluated'] and gate['status']=='KILLED_DEVELOPMENT')
    folds=[]
    for year in range(2020,2024):
        train=panel[panel.label_end.lt(f'{year}-01-01')];test=panel[panel.decision_date.str.startswith(str(year))]
        if train.decision_date.nunique()<3 or test.empty:continue
        folds.append(dict(year=year,train_rows=len(train),train_dates=train.decision_date.nunique(),latest_label_end=train.label_end.max(),test_rows=len(test)))
        check(f'mature annual fold{year}',train.label_end.max()<f'{year}-01-01')
    pd.DataFrame(folds).to_csv(OUT/'delivery_fold_reconstruction.csv',index=False)
    ic=pd.read_csv(OUT/'delivery_development_ic.csv')
    historical=ROOT/'experiments/champion-sip-profit-20261017/historical_scores.csv.gz'
    cols=['isin','decision_date','profile_name','sip_risk_confirmed_0.01'];parts=[]
    for chunk in pd.read_csv(historical,usecols=cols,chunksize=20000):
        q=chunk[chunk.profile_name.eq('base7500') & chunk.decision_date.isin(ic.decision_date)]
        if len(q):parts.append(q)
    champion=pd.concat(parts,ignore_index=True)
    # Champion guards have narrower support. Reconstruct the frozen six fits for
    # a truly matched diagnostic without changing the original development gate.
    from sklearn.linear_model import Ridge
    from delivery_probe_20261101 import BASE,EXTRA
    predictions=[]
    for fold in folds:
        year=fold['year'];train=panel[panel.label_end.lt(f'{year}-01-01')];test=panel[panel.decision_date.str.startswith(str(year))].copy()
        for name,cols in [('control',BASE),('delivery',BASE+EXTRA)]:
            model=Ridge(alpha=10);model.fit(train[cols],train.target);test[name]=model.predict(test[cols])
        predictions.append(test)
    predictions=pd.concat(predictions,ignore_index=True)
    reproduced=[]
    for date,g in predictions.groupby('decision_date'):
        reproduced.append(dict(decision_date=date,control_ic=g.control.corr(g.target,method='spearman'),delivery_ic=g.delivery.corr(g.target,method='spearman')))
    repro=pd.DataFrame(reproduced).merge(ic,on='decision_date',suffixes=('_new','_original'),validate='one_to_one')
    check('six frozen fits reproduce stored full-support IC',all(np.allclose(repro[k+'_new'],repro[k+'_original'],atol=1e-12,rtol=0) for k in ['control_ic','delivery_ic']))
    matched=predictions.merge(champion,on=['isin','decision_date'],validate='one_to_one').dropna(subset=['sip_risk_confirmed_0.01'])
    champion_ic=[]
    for date,g in matched.groupby('decision_date'):
        champion_ic.append(dict(decision_date=date,n=len(g),champion_ic=g['sip_risk_confirmed_0.01'].corr(g.target,method='spearman'),
            control_ic=g.control.corr(g.target,method='spearman'),delivery_ic=g.delivery.corr(g.target,method='spearman')))
    pd.DataFrame(champion_ic).to_csv(OUT/'delivery_champion_changed_target_diagnostic.csv',index=False)
    check('champion intersection diagnostics span same12dates',set(pd.DataFrame(champion_ic).decision_date)==set(ic.decision_date))
    llm=json.loads((OUT/'filing_gate.json').read_text())
    filing_review=dict(disposition='INCONCLUSIVE_OPERATIONAL_DROP',original_status=llm['status'],
        strict_single_label_score=f"{llm['llm_correct']}/{llm['cases']}",
        issues=['Only2of6cases completed; actual4801s versus600s intended budget; blocking-call timeout did not enforce absolute budget',
                'Case01 event correct; exact quote rejected because PDF wraps whitespace: not established hallucination',
                'Case02 contains both resignation and appointment; prompt had no priority rule, so single-label gold is ambiguous',
                'Case02 quote is a firm name, insufficient alone to substantiate appointment; substring match is weaker than semantic support'],
        repair='Added an absolute worker watchdog for future runs; not rerun; preserve original outputs and no prompt/model search',
        no_claim='Not evidence of financial predictive ability or general inferiority of LLM extraction')
    (OUT/'filing_post_review.json').write_text(json.dumps(filing_review,indent=2))
    (OUT/'integrity_checks.json').write_text(json.dumps(dict(checks=checks,all_passed=True,scope='Local artifact and causal timing checks; not independent point-in-time certification'),indent=2))
    summary=pd.read_csv(OUT/'execution_summary.csv')
    show=summary[['period','model','policy','valid_dates','legacy_xirr','next_open_xirr','xirr_change']].copy()
    for col in ['legacy_xirr','next_open_xirr','xirr_change']:show[col]=(show[col]*100).map(lambda v:f'{v:.3f}')
    show=show.rename(columns={'legacy_xirr':'legacy mean XIRR %','next_open_xirr':'next-open mean XIRR %','xirr_change':'change pp'})
    paired=pd.read_csv(OUT/'execution_paired.csv')
    for col in ['lens_minus_champion_xirr','lens_minus_champion_drawdown']:paired[col]=(paired[col]*100).map(lambda v:f'{v:.3f}')
    reasons=fail.groupby('reason').size().to_dict()
    report=f'''# Execution repair and new-information pilots — 1 November 2026

The execution proxy is corrected and tested. The first delivery-information head
failed its development gate; its exposed performance remains unopened. The filing
pilot is **inconclusive and operationally dropped**. No weights, champion, preference lens,
prospective ledger, trading account, or production ranking was changed.

## Actual next-open execution

The previous proxy could buy at the same close used for the decision. This is
unattainable timing for an after-close signal. It does not mathematically inflate
every return: an overnight fall can improve a later entry. Here the mean correction
is negative for every reported group. Raw legacy tables remain preserved.

The new proxy uses actual cached provider Open × (Adj Close / Close), not shifted
closing prices. Every scheduled contribution stays as idle cash and buys at the
first observed opening strictly after its scheduled date. This deliberately applies
to later monthly contributions too. Costs are25bp per buy and terminal sale.
Fractional shares, fixed selection/weights,12-month cohorts, original base7500
schedule. End-of-horizon liquidation uses the last observed adjusted close on or
before the known endpoint with a maximum7-day mark gap. First fills are all later
than the decision. Missing opens, paths or unresolved actions block entire portfolios.

{table(show)}

These are means of overlapping cohort XIRRs, not a chainable strategy CAGR.
Each row compares old and new execution on the same valid observations. Cross-model
comparisons require matched dates:

{table(paired)}

The last two columns above are lens minus champion in percentage points; negative
drawdown means worse loss. Development Top20 remains worse for the lens by2.314pp
on15matched dates. Exposed comparisons have only7Top20 or5sector observations and
were already exposed diagnostics, not a new holdout or a reason to promote a model.
There were82valid and30blocked of112planned portfolio observations. Failure reasons:
`{reasons}`. Missingness can bias the remaining sample.

## Cheap new-information long shot: lagged delivery percentage

Downloaded official NSE full delivery reports and same-session bhavcopy ISINs
serially. Full report endpoints were unavailable for15pre2020sample dates, so those
remain unknown. Coverage passed on29dates including December2019and28dates
in2020–25 (16development,12exposed),
with at least500complete EQ stocks/date. These are dated snapshots, not a continuous
daily microstructure panel and not a survivorship-free universe. BSE stocks,
surveillance stages, circuit execution, pledge changes and bulk/block histories were
not synthesized from ordinary price/volume data.

One fixed annual expanding Ridge(alpha10) price/volume control versus the same
head plus delivery percentage and delivery×recent momentum. The source session
must precede the decision date. Each annual fit uses only labels matured before
January1;December2019and2020provide training,2021–23provides12development evaluation dates.
Six initial fits, plus six identical review reconstructions that reproduced the
stored full-support IC exactly; no hyperparameter grid. The target is next-open to21st-session close net
of25bp per side, a different short-horizon objective from the champion's SIP goal.
Raw return/volatility features are the existing price head; official lagged quantity
and turnover are included in both models. All inputs are same-date global
percentiles. Protocols were hashed before fitting.

- Matched control mean IC: **{gate['control_ic']:.6f}**.
- Delivery-augmented mean IC: **{gate['delivery_ic']:.6f}**.
- Increment: **{gate['delta_ic']:+.6f}**, versus required **>{gate['hurdle']:.6f}**.
- Decision: **kill this fixed candidate**; exposed performance unopened.

Champion guard support is narrower than the full delivery cohort. On their
intersection, all three scores use exactly the same12date/stock/changed-target
rows: champion mean IC **{pd.DataFrame(champion_ic).champion_ic.mean():.6f}**,
control **{pd.DataFrame(champion_ic).control_ic.mean():.6f}**, delivery
**{pd.DataFrame(champion_ic).delivery_ic.mean():.6f}**. Date-level counts are in the
diagnostic CSV. This is separate from the original full-support kill gate and does
not redefine the champion's original objective or validate a competing product.
One failed two-feature head does not reject every Indian microstructure signal.

## Higher-ceiling long shot: local filing reader

Six real NSE filing documents were downloaded, hashed and read, including two
auditor resignation events, three auditor appointment events and one non-auditor
resignation. One resignation concerns a step-down subsidiary. A resignation is an
event, not evidence of wrongdoing: one document cites fee disagreement and another
auditor consolidation. Neither is automatically a loser label.

The installed llama3.2:3b was pinned by local digest; issuer identifiers were
redacted in bounded excerpts. One CPU compute thread, no GPU allocation, isolated
local service inside the same governed job. No cloud inference or model downloads.
Fixed prompt/seed, temperature0, exact-substring support required. Results:

- Original strict single-label score: **{llm['llm_correct']}/{llm['cases']}**.
- Fixed regex correct classifications: **{llm['rule_correct']}/{llm['cases']}**.
- Outcome: **INCONCLUSIVE — operationally dropped**; {llm['cases']}of6planned cases completed.
- Investment-alpha test: **not run**. Dated pledge data and mature prospective
  loser labels are missing. This is source-reviewed factual extraction, not an
  independent human-labeled governance benchmark or a financial backtest.

The intended600secondbudget overran to{llm['elapsed_seconds']}seconds of wall time;
the blocking HTTP timeout was not an absolute deadline. Host availability/scheduling
may contribute, but the cause of the wall-clock gap is not established. An absolute
worker watchdog was added afterward and inference was not rerun. Case1returned the
correct event but its quote differed only in PDF whitespace, causing strict rejection.
Case2contains both resignation and appointment, with no priority rule in the prompt;
its appointment answer is not established as factually wrong. Its firm-name quote
alone is insufficient semantic support. The original0/2score is preserved, but is
**not a sound estimate of extraction accuracy**. This pilot failed on operational
cost and evaluation design, not a demonstrated lack of governance signal.

Metadata was first observed in the existing October31acquisition; document bodies
were acquired November1. Exchange publication dates, metadata first observation,
and new document acquisition times are distinct. Nothing was backfilled into a
prospective forecast. Exact prompts, model settings, source receipts and hashed
results are retained; full documents/excerpts and raw LLM answers remain local.

## Disposition of the other suggestions

- Tail radar: not tested in this batch. A2x/24monthtarget needs more mature,
  point-in-time labels and a volatility-matched control; the12-monthSIP label is
  not a substitute.
- Global simple model: not shipped. A weak sector placebo is not an equivalence
  test of a new model. Keep it a separate preregistered non-inferiority question.
- Fixed regime switch: not tested. Complete point-in-time2012–19memberships,
  adjusted daily histories and terminal proceeds are still incomplete; there is
  no valid three-bear-regime panel ready to score.
- Public shadow: existing append-only research records remain intact. No actual
  money was committed. Fresh, complete champion inputs and source-to-fill parity
  still gate the start of an eligible prospective holdout.

## Reproduction and limits

Run the scripts only through `champion_market_low_load_20261031.run`, using
`work/new-information-20261101` for this run's status/logs. One research worker,
one compute thread, CPU cap12.5%,4seconds active/2seconds rest. The isolated LLM
was CPU-only; its service is shut down afterward. No power settings changed.
The PDF reader uses the installed bundled pypdf if absent from the repo venv.
Acquisition and raw price caches remain local; compact receipts are versioned.

Eight focused execution regression tests passed before replay. Artifact integrity
checks are recorded separately:15checks passed, including exact reproduction of
the development IC. The final local test run passed17tests covering execution,
the watchdog, and the existing professor factor module. Local validation does not imply remote CI passed.
The initial PDF logging attempt failed on Windows cp1252; switching this runner's
stdout toUTF8 fixed it, preserving the failed log. No model/prompt was tuned from
that error. Current-survivor identities, retrospective sectors, provider price
adjustment vintages, missing execution constraints and sparse overlapping dates
remain. The execution correction repairs this new research proxy; old model
training labels and old published benchmark cashflows have not been silently
retrained or overwritten. Original same-close performance claims remain provisional.

Sources: [NSE reports](https://www.nseindia.com/all-reports),
[Ollama generation API](https://docs.ollama.com/api/generate),
[Llama3.2model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md).
The model card lists a December2023pretraining cutoff; that and redaction reduce
some known-issuer leakage concerns, but do not establish contamination-free data.
'''
    # Human-readable spacing for generated fixed prose.
    import re
    report='\n'.join(line if line.startswith('|') or 'http' in line or '`' in line else
        re.sub(r'(?<=\d)(?=[A-Za-z])',' ',re.sub(r'(?<=[A-Za-z])(?=\d)',' ',line)) for line in report.splitlines())+'\n'
    # Do not alter URLs, paths, identifiers in tables, or source URLs with generic substitutions.
    report=report.replace('llama 3.2:3 b','llama3.2:3b').replace('Llama 3.2 model','Llama 3.2 model')
    for a,b in {'21 st':'21st','cp 1252':'cp1252','toUTF 8':'to UTF-8','December 2019 and 2020 provide':'December 2019 and 2020 provide',
        'Ridge(alpha 10)':'Ridge(alpha=10)','Llama3.2model card':'Llama 3.2 model card',
        'date/stock/changed-target':'date, stock and changed-target',',12':', 12',',2021':', 2021'}.items():report=report.replace(a,b)
    # Restore authoritative source link after prose spacing.
    report=report.replace('models/llama 3_2','models/llama3_2')
    path=ROOT/'research/reports/new_information_20261101.md';path.write_text(report,encoding='utf-8')
    outputs=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs');outputs.mkdir(exist_ok=True)
    (outputs/'new_information_20261101.md').write_text(report,encoding='utf-8')
    print('REVIEW',len(checks),'checks passed; report written',flush=True)


if __name__=='__main__':main()
