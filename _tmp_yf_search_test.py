import yfinance as yf, json
for q in ["Fluidomat Ltd","Taparia Tools Ltd","ADC India Communications"]:
    try:
        s=yf.Search(q,max_results=8,news_count=0)
        print("\nQUERY",q)
        for x in s.quotes:
            print({k:x.get(k) for k in ["symbol","shortname","longname","exchange","quoteType"]})
    except Exception as e: print("ERR",q,type(e).__name__,e)
