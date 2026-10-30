"""Archive primary issuer PDFs and locate relevant financial statements."""
import hashlib
import json
from pathlib import Path
import requests
import fitz

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/sector-specialist-ensemble-20261011/issuer_review/followup'
SOURCES={
    'ceigall_fy2026':'https://ceigall.com/wp-content/uploads/2026/08/Annual-Report-2025-26.pdf',
    'gptinfra_fy2026':'https://gpt-infra.s3.ap-south-1.amazonaws.com/annual-reports/10_07_2026_GIL_Annual_Report_Web_Upload_2025-26.pdf',
    'anandrathi_fy2026':'https://www.anandrathiwealth.in/wealthpdf/27april2026/AnnualReport2025-26.pdf',
}

def main():
    OUT.mkdir(parents=True,exist_ok=True);records=[]
    for name,url in SOURCES.items():
        path=OUT/(name+'.pdf')
        try:
            if not path.exists():
                response=requests.get(url,timeout=60);response.raise_for_status()
                assert response.content.startswith(b'%PDF')
                path.write_bytes(response.content)
            document=fitz.open(path);matches=[]
            for number,page in enumerate(document):
                text=page.get_text();lower=text.lower()
                if ('cash flows from operating' in lower or 'cash flow from operating' in lower or 'pledged shares' in lower or 'pledge reduction' in lower or 'shares pledged' in lower):
                    matches.append(dict(pdf_page=number+1,text=text))
            (OUT/(name+'_matches.json')).write_text(json.dumps(matches,indent=2),encoding='utf-8')
            records.append(dict(name=name,url=url,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pages=len(document),matched_pages=[m['pdf_page'] for m in matches]))
        except Exception as exc:
            records.append(dict(name=name,url=url,error=str(exc)))
    (OUT/'sources.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps(records,indent=2),flush=True)

if __name__=='__main__':main()
