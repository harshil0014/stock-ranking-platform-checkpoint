from pathlib import Path
import sys,io,zipfile,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from round2_bhavcopy_20261031 import validate_zip

def payload(rows):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:z.writestr('cm31JAN2012bhav.csv','SYMBOL,SERIES,ISIN,CLOSE,TOTTRDQTY,TIMESTAMP\n'+rows)
 return b.getvalue()

def test_exact_exchange_timestamp_and_identity_kept():
 x=validate_zip(payload('FORMER,EQ,INE000A01010,10,200,31-JAN-2012\n'),'2012-01-31')
 assert x.ISIN.iloc[0]=='INE000A01010' and x.SYMBOL.iloc[0]=='FORMER'

def test_wrong_file_date_cannot_be_used_as_month_end():
 with pytest.raises(ValueError,match='date disagree'):validate_zip(payload('FORMER,EQ,INE000A01010,10,200,30-JAN-2012\n'),'2012-01-31')

def test_duplicate_series_is_ambiguous_not_silently_deduplicated():
 row='FORMER,EQ,INE000A01010,10,200,31-JAN-2012\n'
 with pytest.raises(ValueError,match='Ambiguous'):validate_zip(payload(row+row),'2012-01-31')
