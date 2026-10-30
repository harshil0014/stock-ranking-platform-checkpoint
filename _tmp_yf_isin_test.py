import yfinance as yf
for s in ["RELIANCE.NS","HINDMOTORS.BO","500500.BO"]:
    try:
        t=yf.Ticker(s)
        print(s,"isin",t.isin)
        print("fast",dict(t.fast_info))
    except Exception as e:
        print(s,"ERR",type(e).__name__,e)
