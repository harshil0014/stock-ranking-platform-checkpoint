"""User-authorized SIP preference activation with exact export replay."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
import numpy as np
from stock_ranker.sector_champion_product import ChampionScorer
from stock_ranker.personalized_product import parse_profile

def main():
    out=ROOT/'research/runtime/sector-champion-recency';path=out/'manifest.json'
    prior=path.read_text();backup=out/'manifest_before_sip.json'
    if not backup.exists():backup.write_text(prior)
    fields=['isin','profile_name','professor_whole_share_score','unused_cash_excluded_by_professor','amount_contributed']
    pd.read_csv(ROOT/'research/runtime/personalized-v17/peak_current.csv.gz',usecols=fields).to_csv(out/'sip_profiles.csv.gz',index=False)
    e=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv')
    e[e.status.ne('ALIGNED_MULTIPLIER')][['isin','event_date']].to_csv(out/'sip_events.csv',index=False)
    m=json.loads(prior);m.update(sip_weight=.01,sip_variant='risk_confirmed',profile_affects_ranking=True,
       chosen_by='User explicitly requested SIP preference integration after accepting slight historical degradation',
       profile_behavior='Trailing professor-mode SIP signal depends on amount, interval and lookback. Target controls goals, not this SIP formula.',
       sip_formula='recency_champion + .01*(sector_profit_percentile-.5)*invested_fraction*inverse_downside_percentile',
       automated_research_gate_passed=False)
    for name in ['sip_profiles.csv.gz','sip_events.csv']:m['files'][name]=hashlib.sha256((out/name).read_bytes()).hexdigest()
    path.write_text(json.dumps(m,indent=2))
    try:
        s=ChampionScorer();p=parse_profile(dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12))
        a=s.add_sip(s.score(p),p,s.sip_profiles[s.sip_profiles.profile_name.eq('base7500')]).set_index('isin').sort_index()
        b=pd.read_csv(ROOT/'experiments/champion-sip-profit-20261017/current_all_4436_audit.csv').set_index('isin').sort_index()
        np.testing.assert_allclose(a.personalized_score,b['sip_risk_confirmed_0.01'],atol=1e-12,rtol=0)
        np.testing.assert_array_equal(a.personalized_sector_rank,b.candidate_sector_rank)
        receipt={'rows':len(a),'max_score_error':float((a.personalized_score-b['sip_risk_confirmed_0.01']).abs().max()),'sector_ranks_exact':True}
        (out/'sip_verification.json').write_text(json.dumps(receipt,indent=2));print(receipt)
    except Exception:
        path.write_text(prior);raise

if __name__=='__main__':main()
