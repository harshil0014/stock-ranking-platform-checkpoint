"""Create compact, verified preference report from fixed sweep artifacts."""
from pathlib import Path
import csv,json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments/high-recency-tilt-20261101'
def main():
    decision=json.loads((OUT/'decision.json').read_text());rows=list(csv.DictReader((OUT/'summary.csv').open()));pairs=list(csv.DictReader((OUT/'development_portfolio_pairs.csv').open()))
    baseline=next(r for r in rows if r['model']=='champion')
    def delta(r,k):return float(r[k])-float(baseline[k])
    text=['# Champion with stronger high-recency preference','',f"Selected preference: **{decision['selected'] or 'none qualifying'}**. This selection optimizes the requested preference within the frozen tradeoff budgets; it is not a demonstrated predictive improvement. Default champion remains unchanged. Exposed period was not evaluated.",'','Lower days since the last recorded closing high receives a higher within-sector percentile. Score = (1-w) × champion percentile + w × high-recency percentile. The champion already contains high-related information; these coefficients are additional explicit score weights, not total feature importance. Other professor factors receive no new explicit weight in this round.','','## Development comparison, 2020–2023','','Differences are challenger minus champion. Positive drawdown difference means less severe drawdown. Top3 statistics are date-balanced sector averages; Top20 portfolio comparisons use each candidate’s matched valid dates.','','| Preference | High-recency gain (percentile points) | Mean high age change (days) | Changed sector Top3 | IC delta | Goal hit delta (pp) | Top3 drawdown delta (pp) | Top20 XIRR delta (pp) | Top20 drawdown delta (pp) | Portfolio dates | Qualifies |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in rows:
        if r['model']=='champion':continue
        p=next(p for p in pairs if p['model']==r['model'] and p['policy']=='global_top20');d=next(d for d in decision['candidates'] if d['model']==r['model'])
        text.append(f"| {r['model']} | {100*delta(r,'high_percentile'):+.2f} | {delta(r,'days_since_high'):+.1f} | {100*float(r['changed']):.1f}% | {delta(r,'rank_ic'):+.5f} | {100*delta(r,'top3_goal_hit'):+.2f} | {100*delta(r,'top3_stock_dd'):+.2f} | {100*float(p['xirr_delta']):+.2f} | {100*float(p['drawdown_delta']):+.2f} | {p['matched_dates']} | {d['qualifies']} |")
    text+=['','## Selection and scope','','Greatest weight passing all preregistered limits: positive recency gain, at least20% changed Top3 sets, IC loss<=0.02, goal-hit/stock drawdown/portfolio XIRR/portfolio drawdown worsening<=3pp, >=8 supported dates. No limits changed after results. These are user-preference tolerances, not significance thresholds.','',f"Documented research attempts: {decision['documented_attempts']} (four added). Registry remains incomplete; no full-history multiple-testing or predictive significance claim.",'','Development has already been reused adaptively. Overlapping cohorts, current-survivor universe, retrospective sector groups, recorded rather than certified lifetime highs, and missing/action-blocked observations limit conclusions. Portfolio replay uses existing next-open fills and100bp per side, with price-only adjusted histories and existing unresolved-action blocks. This round does not claim full corporate-action or dividend completeness. Joint complete Top3 cohorts are held fixed across this candidate family; portfolio pairs can differ in date support. See annual and failure CSVs.']
    if decision['selected']:
        chosen=next(r for r in rows if r['model']==decision['selected'])
        text+=['',f"Selected variant IC changes from {float(baseline['rank_ic']):.5f} to {float(chosen['rank_ic']):.5f}. That is a {100*(1-float(chosen['rank_ic'])/float(baseline['rank_ic'])):.1f}% reduction in the small positive pooled IC: passing the absolute tolerance does not make this a negligible accuracy cost. Annual metrics must be read alongside the pooled preference choice."]
    if decision['current']:
        c=decision['current'];text+=['','## Saved snapshot preference ranking','',f"Snapshot **{c['snapshot']}**, {c['eligible']} eligible stocks in {c['sectors']} sectors. Top3 membership changes in **{c['changed_sectors']}/{c['sectors']} sectors**; average overlap **{100*c['average_top3_overlap']:.2f}%**. Local CSV includes baseline and preference ranks, raw high age, and both score components. This is a stale saved snapshot, not live investment picks. Ineligible stocks are not silently assigned neutral factor values. No UI/default/ledger promotion."]
        file=Path(c['file']);current=list(csv.DictReader(file.open()));weight=next(d['weight'] for d in decision['candidates'] if d['model']==decision['selected'])
        assert hashlib.sha256(file.read_bytes()).hexdigest()==c['sha256']
        assert len(current)==c['eligible'] and len({r['isin'] for r in current})==len(current)
        assert all(abs(float(r['preference_score'])-((1-weight)*float(r['champion_percentile'])+weight*float(r['q_high_recency'])))<1e-12 for r in current)
        for sector in {r['sector'] for r in current}:
            group=[r for r in current if r['sector']==sector]
            ordered=sorted(group,key=lambda r:(-float(r['preference_score']),r['isin']))
            assert all(int(r['preference_rank'])==i+1 for i,r in enumerate(ordered))
        text+=['','Independent CSV review verified the file hash, unique stock count, every blend calculation and each sector’s deterministic preference ordering.']
    text+=['','## Verification','',f"{sum(decision['checks'].values())} runner checks passed: development-only dates, fixed four-candidate count, blend endpoints, monotonic recency direction, finite bounded scores, unique rows and prior ledger IDs preserved. Existing low-load governor enforced one compute thread,12.5% CPU cap and4s/2s duty cycle. No training or GPU.",'','Evidence: `experiments/high-recency-tilt-20261101/`; protocol: `research/protocols/high_recency_tilt_20261101.md`.']
    report=ROOT/'research/reports/high_recency_tilt_20261101.md';report.write_text('\n'.join(text)+'\n',encoding='utf-8',newline='\n')
    dest=Path('C:/Users/Harshil/Documents/Codex/2026-10-31/you/outputs');shutil.copy2(report,dest/report.name)
    files=[p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json']+[report,ROOT/'research/protocols/high_recency_tilt_20261101.md',ROOT/'research/research_variant_ledger.csv']
    manifest=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(report.read_text(),flush=True)
if __name__=='__main__':main()
