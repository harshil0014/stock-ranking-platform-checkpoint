import yfinance as yf
for s in ["HINDMOTORS.BO","TAPARIA.BO","FLUIDOM.BO","ADCINDIA.BO"]:
    try:
        h=yf.Ticker(s).history(period="max",auto_adjust=False,actions=False)
        print(s,len(h),h.index.min() if len(h) else None,h.index.max() if len(h) else None)
        if len(h): print(h.tail(2)[["Close","Adj Close"]])
    except Exception as e: print(s,"ERR",type(e).__name__,e)
