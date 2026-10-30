"""Read-only professor evidence audit against frozen Closing High rankings."""
from pathlib import Path
import sys, json, hashlib
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from stock_ranker.professor_reference import _XlsxCells, NS

SOURCE = Path(r'C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx')
OUT = ROOT / 'research/reports/top100-human-review-20261004'

def agreement(frame, a, b):
    pairs = [(x,y) for i,x in enumerate(frame.index) for y in frame.index[i+1:]
             if frame.loc[x,a] != frame.loc[y,a] and frame.loc[x,b] != frame.loc[y,b]]
    correct = sum((frame.loc[x,a]-frame.loc[y,a])*(frame.loc[x,b]-frame.loc[y,b])>0 for x,y in pairs)
    return {'agree': int(correct), 'pairs':len(pairs), 'fraction': correct/len(pairs) if pairs else None}

def run():
    OUT.mkdir(parents=True, exist_ok=True)
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    evidence = {}
    with ZipFile(SOURCE) as z:
        shared = _XlsxCells._shared_strings(z)
        paths = _XlsxCells._sheet_paths(z)
        for sheet in ['SIP Portfolio','StockHistoryData','ATHCutter','Buying (MultiStock - New Alloc)','Opportunity']:
            cells = {}
            with z.open(paths[sheet]) as stream:
                for _, node in ET.iterparse(stream, events=['end']):
                    if node.tag != '{'+NS['m']+'}row': continue
                    if int(node.attrib['r']) > 22: break
                    for cell in node.findall('m:c', NS):
                        v, f = cell.find('m:v', NS), cell.find('m:f', NS)
                        value = v.text if v is not None else None
                        if cell.attrib.get('t') == 's' and value is not None: value = shared[int(value)]
                        cells[cell.attrib['r']] = {'value':value, 'formula':f.text if f is not None else None}
                    node.clear()
            evidence[sheet] = cells
    sip = evidence['SIP Portfolio']
    assert all(sip[f'G{r}']['value']=='0' and sip[f'N{r}']['value']=='#N/A' for r in range(7,21))
    ranking_path = ROOT / 'experiments/v17-peak-confirmation-20261004/current_rankings.csv.gz'
    allr = pd.read_csv(ranking_path,low_memory=False)
    base = allr[allr.profile_name.eq('base7500')].copy()
    facts = pd.read_csv(ROOT/'experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_full_yahoo.csv.gz',low_memory=False)
    # Screenshot rows 7:20, transcribed separately; keep duplicate for raw evidence.
    ss_codes = ['NSE:KRISHANA','GVT&D','BOM:524717','NSE:SHAILY','NSE:WELCORP','NSE:V2RETAIL','NSE:TERASOFT','NSE:APOLLO','NSE:LUMAXTECH','BOM:539997','NSE:TDPOWERSYS','NSE:INDOTECH','NSE:CEMPRO','NSE:CEMPRO']
    ss_rank = [12,4,6,3,2,8,11,7,12,1,5,12,9,9]
    ss_cmp = [None,4356,399.6,3152,2745,234,239.6,408.6,None,3769.8,757,None,1319.3,1319.3]
    ss_pl = [-1,2.4123,2.0395,2.4376,2.7564,1.7667,1.0909,1.8834,-1,4.1025,2.3625,-1,1.6073,1.6073]
    screen = pd.DataFrame({'screenshot_row':range(7,21),'code':ss_codes,'screenshot_rank':ss_rank,'screenshot_cmp':ss_cmp,'screenshot_profit_pct':ss_pl})
    screen['duplicate_code'] = screen.code.duplicated(keep=False)
    screen.to_csv(OUT/'professor_screenshot_transcription.csv',index=False)
    rows=[]
    fields=['isin','ticker','company','status','new_rank','new_score','priority_rank','winner_rank','original_v17_rank','activity_eligible','activity_filter_reason','professor_whole_share_score','enhanced_carry_xirr_score','days_since_recorded_high','distance_from_recorded_high','momentum_6m','history_months','downside_volatility_1y']
    for r in range(7,21):
        code=sip[f'B{r}']['value']
        match=facts[pd.to_numeric(facts.screener_bse_code,errors='coerce').eq(int(code.split(':')[1]))] if code.startswith('BOM:') else facts[facts.ticker.eq(code.removeprefix('NSE:'))]
        assert len(match)==1,(code,len(match))
        stock=base[base['isin'].eq(match.iloc[0]['isin'])]
        assert len(stock)==1
        ss=screen[screen.code.eq(code)].head(1)
        row={'workbook_row':r,'code':code,**{k:stock.iloc[0][k] for k in fields},'workbook_cached_rank':sip[f'N{r}']['value'],'workbook_cached_invested':sip[f'G{r}']['value'],'workbook_cached_cmp':sip[f'D{r}']['value']}
        row.update({k:ss.iloc[0][k] if len(ss) else None for k in ['screenshot_rank','screenshot_cmp','screenshot_profit_pct']})
        rows.append(row)
    result=pd.DataFrame(rows)
    assert result['isin'].is_unique
    result['closing_high_order_within_workbook']=result.new_rank.rank(method='min')
    result['current_professor_order_within_workbook']=result.professor_whole_share_score.where(result.new_rank.notna()).rank(ascending=False,method='min')
    result.to_csv(OUT/'professor_stock_comparison.csv',index=False)
    valid=result.dropna(subset=['screenshot_cmp','screenshot_rank','new_rank'])
    current=result.dropna(subset=['new_rank','professor_whole_share_score'])
    univ=base[base.new_rank.notna() & base.professor_whole_share_score.notna()].copy()
    univ['closing_high_rank_common_population']=univ.new_rank.rank(method='min')
    univ['professor_rank_same_eligible_universe']=univ.professor_whole_share_score.rank(ascending=False,method='min')
    univ[['isin','ticker','company','new_rank','closing_high_rank_common_population','professor_rank_same_eligible_universe','professor_whole_share_score']].to_csv(OUT/'professor_same_universe_comparison.csv',index=False)
    missing=base[base.new_rank.notna() & base.professor_whole_share_score.isna()]
    missing[['isin','ticker','company','new_rank']].to_csv(OUT/'professor_missing_score_eligible.csv',index=False)
    summary={'profile':'base7500','decision_date':base.decision_date.unique().tolist(),'universe_rows':len(base),'eligible_rows':int(base.new_rank.notna().sum()),'workbook_rows':len(result),'matched_workbook_rows':len(result),'ranked_workbook_rows':int(result.new_rank.notna().sum()),'screenshot_unique_companies':int(screen.code.nunique()),'screenshot_usable_comparison_n':len(valid),'screenshot_spearman':valid.screenshot_rank.corr(valid.new_rank,method='spearman'),'screenshot_pair_agreement':agreement(valid,'screenshot_rank','new_rank'),'same_current_shortlist_n':len(current),'same_current_shortlist_spearman':current.current_professor_order_within_workbook.corr(current.new_rank,method='spearman'),'same_current_shortlist_pair_agreement':agreement(current,'current_professor_order_within_workbook','new_rank'),'same_current_full_eligible_spearman':univ.professor_rank_same_eligible_universe.corr(univ.new_rank,method='spearman'),'source_sha256':before,'ranking_sha256':hashlib.sha256(ranking_path.read_bytes()).hexdigest()}
    for n in [20,50,100]:
        summary[f'workbook_top{n}_members']=result.loc[result.new_rank.le(n),'ticker'].tolist()
        summary[f'same_universe_top{n}_overlap']=len(set(univ.loc[univ.closing_high_rank_common_population.le(n),'isin']) & set(univ.loc[univ.professor_rank_same_eligible_universe.le(n),'isin']))
    summary['same_current_full_comparable_n']=len(univ)
    summary['professor_score_missing_in_eligible']=len(missing)
    assert before==hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    summary['source_unchanged']=True
    (OUT/'professor_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (OUT/'professor_formula_evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print(result[['ticker','screenshot_rank','new_rank','closing_high_order_within_workbook','current_professor_order_within_workbook','days_since_recorded_high','distance_from_recorded_high']].to_string(index=False))

if __name__=='__main__': run()
