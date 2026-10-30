"""Read-only workbook comparison; never trains or edits model/source artifacts."""
from pathlib import Path
import sys, json, hashlib
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from stock_ranker.professor_reference import _XlsxCells, NS

SOURCE = Path(r'C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx')
OUT = ROOT / 'experiments/professor-v17-refined-comparison-20261004'

def run():
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = {}
    with ZipFile(SOURCE) as z:
        shared = _XlsxCells._shared_strings(z)
        paths = _XlsxCells._sheet_paths(z)
        for sheet in ['SIP Portfolio', 'StockHistoryData', 'ATHCutter', 'Buying (MultiStock - New Alloc)', 'Opportunity']:
            cells = {}
            with z.open(paths[sheet]) as stream:
                for event, node in ET.iterparse(stream, events=['end']):
                    if node.tag != '{'+NS['m']+'}row':
                        continue
                    if int(node.attrib['r']) > 22:
                        break
                    for cell in node.findall('m:c', NS):
                        v = cell.find('m:v', NS)
                        value = v.text if v is not None else None
                        if cell.attrib.get('t') == 's' and value is not None:
                            value = shared[int(value)]
                        f = cell.find('m:f', NS)
                        cells[cell.attrib['r']] = {'value': value, 'formula': f.text if f is not None else None}
                    node.clear()
            evidence[sheet] = cells
    sip = evidence['SIP Portfolio']
    current_path = ROOT / 'experiments/v17-refinement-20261004/final_current_rankings.csv.gz'
    current = pd.read_csv(current_path, low_memory=False)
    base = current[current.profile_name.eq('base7500')].copy()
    facts = pd.read_csv(ROOT / 'experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_full_yahoo.csv.gz', low_memory=False)
    # Explicit screenshot transcription: final duplicate CEMPRO omitted from company-level statistics.
    screenshot = {'KRISHANA':12,'GVT&D':4,'BSE-524717':6,'SHAILY':3,'WELCORP':2,'V2RETAIL':8,'TERASOFT':11,'APOLLO':7,'LUMAXTECH':12,'KPL':1,'TDPOWERSYS':5,'INDOTECH':12,'CEMPRO':9}
    missing_cmp = {'KRISHANA','LUMAXTECH','INDOTECH'}
    rows = []
    for row in range(7,21):
        code = sip[f'B{row}']['value']
        if code.startswith('BOM:'):
            match = facts[pd.to_numeric(facts.screener_bse_code, errors='coerce').eq(int(code.split(':')[1]))]
            method = 'exact BSE security code in V7 identity facts'
        else:
            match = facts[facts.ticker.eq(code.removeprefix('NSE:'))]
            method = 'exact ticker in V7 identity facts'
        assert len(match) == 1, (code, len(match))
        identity = match.iloc[0]['isin']
        stock = base[base['isin'].eq(identity)]
        assert len(stock) == 1
        s = stock.iloc[0]
        rows.append({'workbook_row':row,'workbook_code':code,'identity_match':method,
            **{k:s[k] for k in ['isin','ticker','company','status','winner_rank','winner_score','professor_whole_share_score','enhanced_carry_xirr_score','days_since_recorded_high','distance_from_recorded_high','history_months','evidence_confidence']},
            'screenshot_rank':screenshot.get(s.ticker), 'screenshot_missing_cmp':s.ticker in missing_cmp,
            'workbook_cached_rank':sip[f'N{row}']['value'], 'workbook_cached_investment':sip[f'G{row}']['value']})
    df = pd.DataFrame(rows)
    df['v17_rank_within_workbook_list'] = df.winner_score.rank(ascending=False,method='min')
    df['current_professor_style_rank_within_list'] = df.professor_whole_share_score.rank(ascending=False,method='min')
    valid = df[df.screenshot_rank.notna() & ~df.screenshot_missing_cmp & df.winner_rank.notna()]
    comparable = df.dropna(subset=['winner_rank','professor_whole_share_score'])
    def pair_agreement(frame, a, b):
        pairs = [(x,y) for i,x in enumerate(frame.index) for y in frame.index[i+1:] if frame.loc[x,a] != frame.loc[y,a] and frame.loc[x,b] != frame.loc[y,b]]
        return sum((frame.loc[x,a]-frame.loc[y,a])*(frame.loc[x,b]-frame.loc[y,b])>0 for x,y in pairs)/len(pairs) if pairs else None
    summary = {'profile':'base7500','amount':7500,'lookback_months':36,'interval_days':30,'model_target_cagr':0.2,'model_forward_horizon_months':12,
        'workbook_CAGR_field_is_highlight_not_target':True,'workbook_rows':len(df),'mapped_rows':len(df),'ranked_rows':int(df.winner_rank.notna().sum()),
        'top20_members':df.loc[df.winner_rank.le(20),'ticker'].tolist(),'top50_members':df.loc[df.winner_rank.le(50),'ticker'].tolist(),'top100_members':df.loc[df.winner_rank.le(100),'ticker'].tolist(),
        'screenshot_valid_comparable_n':len(valid),'screenshot_spearman':valid.screenshot_rank.corr(valid.winner_rank,method='spearman'),
        'screenshot_pair_agreement':pair_agreement(valid,'screenshot_rank','winner_rank'),
        'same_current_data_professor_style_n':len(comparable),'same_current_data_spearman':comparable.professor_whole_share_score.corr(-comparable.winner_rank,method='spearman'),
        'same_current_data_pair_agreement':pair_agreement(comparable,'current_professor_style_rank_within_list','winner_rank'),
        'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'frozen_current_rankings_sha256':hashlib.sha256(current_path.read_bytes()).hexdigest(),
        'limitations':['Screenshot is undated and not the same snapshot/list as workbook.','All 14 workbook SIP invested-value caches are zero and ranks #N/A.','Current professor-style score follows our price/action/calendar implementation; not an exact Google Sheets replay.','Current V7 includes professor-derived current-only growth fallback fields, so input sources are not independent.','No model selection, training, deployment or workbook changes.']}
    df.to_csv(OUT/'stock_comparison.csv',index=False)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (OUT/'workbook_formula_evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print(df[['ticker','screenshot_rank','winner_rank','v17_rank_within_workbook_list','current_professor_style_rank_within_list']].to_string(index=False))

if __name__ == '__main__':
    run()
