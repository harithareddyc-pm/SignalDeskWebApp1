"""
SignalDesk Web App — Flask Backend
Render.com compatible — batch scanning to avoid timeout
"""

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, date, timezone, timedelta
import threading
import os

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

IST = timezone(timedelta(hours=5, minutes=30))

# ── Cache ──────────────────────────────────────────────────────────────
_cache = {
    "data": None, "timestamp": None,
    "running": False, "progress": 0, "total": 0,
    "results": [], "error": None
}

# ── Nifty 500 symbols ──────────────────────────────────────────────────
NIFTY500 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS",
    "HINDUNILVR.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","TITAN.NS",
    "BAJFINANCE.NS","HCLTECH.NS","WIPRO.NS","ULTRACEMCO.NS","NESTLEIND.NS",
    "SUNPHARMA.NS","TECHM.NS","POWERGRID.NS","NTPC.NS","TATAMOTORS.NS",
    "INDUSINDBK.NS","BAJAJFINSV.NS","JSWSTEEL.NS","TATASTEEL.NS","HDFCLIFE.NS",
    "ONGC.NS","COALINDIA.NS","DIVISLAB.NS","CIPLA.NS","DRREDDY.NS",
    "ADANIPORTS.NS","HINDALCO.NS","GRASIM.NS","BRITANNIA.NS","EICHERMOT.NS",
    "M&M.NS","HEROMOTOCO.NS","BPCL.NS","IOC.NS","TATACONSUM.NS",
    "PIDILITIND.NS","SIEMENS.NS","HAVELLS.NS","DMART.NS","APOLLOHOSP.NS",
    "BAJAJ-AUTO.NS","SBILIFE.NS","ICICIPRULI.NS","TORNTPHARM.NS","LUPIN.NS",
    "DABUR.NS","MARICO.NS","BERGEPAINT.NS","COLPAL.NS","GODREJCP.NS",
    "ADANIENT.NS","AMBUJACEM.NS","ACC.NS","SHREECEM.NS","MUTHOOTFIN.NS",
    "PFC.NS","RECLTD.NS","BANKBARODA.NS","CANBK.NS","PNB.NS",
    "FEDERALBNK.NS","IDFCFIRSTB.NS","BANDHANBNK.NS","CHOLAFIN.NS","TATAPOWER.NS",
    "HAL.NS","BEL.NS","BHEL.NS","ZOMATO.NS","IRCTC.NS",
    "CONCOR.NS","GAIL.NS","IGL.NS","TRENT.NS","PAGEIND.NS",
    "VEDL.NS","NMDC.NS","SAIL.NS","HINDZINC.NS","NATIONALUM.NS",
    "MOTHERSON.NS","NHPC.NS","IRFC.NS","HUDCO.NS","MGL.NS",
    "DRREDDY.NS","AUROPHARMA.NS","ALKEM.NS","TORNTPHARM.NS","GLAXO.NS",
    "PFIZER.NS","ABBOTT.NS","SANOFI.NS","IPCALAB.NS","NATCOPHARM.NS",
    "DIXON.NS","AMBER.NS","VOLTAS.NS","WHIRLPOOL.NS","BLUESTARCO.NS",
    "SYMPHONY.NS","CROMPTON.NS","BAJAJELEC.NS","ORIENTELEC.NS","VGUARD.NS",
    "JUBLFOOD.NS","DEVYANI.NS","SAPPHIRE.NS","WESTLIFE.NS","BARBEQUE.NS",
    "INDHOTEL.NS","EIHOTEL.NS","CHALET.NS","LEMONTREE.NS","MAHINDRA.NS",
    "ESCORTS.NS","TIINDIA.NS","SUPRAJIT.NS","ENDURANCE.NS","SUNDRM.NS",
    "MRF.NS","APOLLOTYRE.NS","BALKRISIND.NS","CEATLTD.NS","GOODYEAR.NS",
    "ULTRACEMCO.NS","JKCEMENT.NS","RAMCOCEM.NS","HEIDELBERG.NS","BIRLACORPN.NS",
    "PIDILITIND.NS","ASIANPAINT.NS","KANSAINER.NS","AKZONOBEL.NS","INDIGO.NS",
]

# ── Indicators ─────────────────────────────────────────────────────────
def ema(s, p): return s.ewm(span=p, adjust=False).mean()

def atr_calc(df, p=14):
    h,l,c = df["High"],df["Low"],df["Close"]
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(span=p,adjust=False).mean()

def rsi_calc(s, p=14):
    d=s.diff()
    g=d.clip(lower=0).ewm(span=p,adjust=False).mean()
    l=(-d.clip(upper=0)).ewm(span=p,adjust=False).mean()
    return 100-(100/(1+g/l.replace(0,np.nan)))

def macd_calc(s):
    ml=ema(s,12)-ema(s,26); sig=ema(ml,9); return ml,sig,ml-sig

def bb_calc(s,p=20,std=2):
    m=s.rolling(p).mean(); sd=s.rolling(p).std()
    return m+std*sd,m,m-std*sd

# ── Strategies ─────────────────────────────────────────────────────────
def strat_ema(df):
    if len(df)<215: return 0,0,"insufficient"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    e20=ema(df["Close"],20).iloc[-1]
    e200=ema(df["Close"],200).iloc[-1]
    a=atr_calc(df).iloc[-1]
    b=(int(c>e200)+int(e20>e200)+int(abs(c-e20)<0.5*a)+int(c>o))*25
    s=(int(c<e200)+int(e20<e200)+int(abs(c-e20)<0.5*a)+int(c<o))*25
    return b,s,"uptrend" if c>e200 else "downtrend"

def strat_rsi(df):
    if len(df)<60: return 0,0,"insufficient"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    r=rsi_calc(df["Close"])
    rc,rp=r.iloc[-1],r.iloc[-2]
    e50=ema(df["Close"],50).iloc[-1]
    a=atr_calc(df).iloc[-1]
    b=(int(rc<30)+int(rc>rp)+int(abs(c-e50)<1.5*a)+int(c>o))*25
    s=(int(rc>70)+int(rc<rp)+int(abs(c-e50)<1.5*a)+int(c<o))*25
    return b,s,"oversold" if rc<30 else "overbought" if rc>70 else "ranging"

def strat_bb(df):
    if len(df)<55: return 0,0,"insufficient"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    up,mid,lo=bb_calc(df["Close"])
    bw=(up-lo)/mid
    wn=bw.iloc[-1]
    wmin=bw.rolling(50).min().iloc[-1]
    wmax=bw.rolling(50).max().iloc[-1]
    wr=wmax-wmin if wmax!=wmin else 1
    sq=int(wn<wmin+0.3*wr)
    vol=df.get("Volume",pd.Series([1]*len(df),index=df.index))
    av=vol.rolling(20).mean().iloc[-1]
    vp=min(int((vol.iloc[-1]/av if av>0 else 1)*12.5),25)
    b=min((sq*25)+int(c>up.iloc[-1])*25+vp+int(c>o)*25,100)
    s=min((sq*25)+int(c<lo.iloc[-1])*25+vp+int(c<o)*25,100)
    return b,s,"squeeze" if sq else "normal"

def strat_fvg(df):
    if len(df)<50: return 0,0,"no data"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    hi,lo,cl=df["High"],df["Low"],df["Close"]
    e200=ema(cl,200).iloc[-1]
    a=atr_calc(df).iloc[-1]
    htf=int(c>e200)
    buy_sc=sell_sc=0
    for i in range(min(50,len(df)-3),2,-1):
        idx=-i
        if lo.iloc[idx]>hi.iloc[idx-2]:
            gs=lo.iloc[idx]-hi.iloc[idx-2]
            if gs>0.08*a:
                sub=cl.iloc[idx+1:]
                if not any((sub>=hi.iloc[idx-2])&(sub<=lo.iloc[idx])):
                    prox=abs(c-lo.iloc[idx])/a
                    pp=max(0,int(35*(1-prox/0.25))) if prox<0.25 else 0
                    buy_sc=pp+(25 if i<=15 else 0)+(25 if htf else 0)+(15 if c>o else 0)
                    break
        if hi.iloc[idx]<lo.iloc[idx-2]:
            gs=lo.iloc[idx-2]-hi.iloc[idx]
            if gs>0.08*a:
                sub=cl.iloc[idx+1:]
                if not any((sub>=hi.iloc[idx])&(sub<=lo.iloc[idx-2])):
                    prox=abs(c-hi.iloc[idx])/a
                    pp=max(0,int(35*(1-prox/0.25))) if prox<0.25 else 0
                    sell_sc=pp+(25 if i<=15 else 0)+(25 if not htf else 0)+(15 if c<o else 0)
                    break
    return min(buy_sc,100),min(sell_sc,100),"fvg"

def strat_macd(df):
    if len(df)<215: return 0,0,"insufficient"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    e200=ema(df["Close"],200).iloc[-1]
    ml,sig,hist=macd_calc(df["Close"])
    mlc,sc=ml.iloc[-1],sig.iloc[-1]
    hn,hp=hist.iloc[-1],hist.iloc[-2]
    fc=any(ml.iloc[i]>sig.iloc[i] and ml.iloc[i-1]<=sig.iloc[i-1] for i in range(-3,0))
    fb=any(ml.iloc[i]<sig.iloc[i] and ml.iloc[i-1]>=sig.iloc[i-1] for i in range(-3,0))
    b=(int(c>e200)+int(mlc>sc)+int(hn>0 and hn>hp)+int(fc))*25
    s=(int(c<e200)+int(mlc<sc)+int(hn<0 and hn<hp)+int(fb))*25
    return b,s,"momentum_up" if b>50 else "momentum_down" if s>50 else "neutral"

# ── Scan one stock ─────────────────────────────────────────────────────
def scan_one(symbol):
    try:
        df=yf.Ticker(symbol).history(period="300d",interval="1d",auto_adjust=True)
        if df is None or len(df)<50: return None
        df=df.dropna(subset=["Close"])
        eb,es,er=strat_ema(df)
        rb,rs,rr=strat_rsi(df)
        bb,bs,br=strat_bb(df)
        fb,fs,fr=strat_fvg(df)
        mb,ms,mr=strat_macd(df)
        buys=[eb,rb,bb,fb,mb]
        sells=[es,rs,bs,fs,ms]
        ag_b=sum(1 for v in buys if v>=75)
        ag_s=sum(1 for v in sells if v>=75)
        avg_b=sum(buys)/5
        avg_s=sum(sells)/5
        if ag_b>=4 and avg_b>=60 and avg_b>avg_s+15:
            direction="LONG"; score=round(avg_b); ag=ag_b
        elif ag_s>=4 and avg_s>=60 and avg_s>avg_b+15:
            direction="SHORT"; score=round(avg_s); ag=ag_s
        else:
            return None
        c=df["Close"].iloc[-1]
        pc=df["Close"].iloc[-2] if len(df)>1 else c
        a=atr_calc(df).iloc[-1]
        chg=round((c-pc)/pc*100,2)
        sl=round(c-1.5*a,2) if direction=="LONG" else round(c+1.5*a,2)
        tp=round(c+3*a,2) if direction=="LONG" else round(c-3*a,2)
        vol=int(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
        avg_vol=int(df["Volume"].rolling(20).mean().iloc[-1]) if "Volume" in df.columns else 1
        vr=round(vol/avg_vol,1) if avg_vol>0 else 0
        return {
            "symbol": symbol.replace(".NS","").replace(".BO",""),
            "direction": direction,
            "score": score,
            "agree": ag,
            "unanimous": ag==5,
            "cmp": round(c,2),
            "chg": chg,
            "sl": sl,
            "target": tp,
            "atr": round(a,2),
            "vol_ratio": vr,
            "strategies": [
                {"name":"EMA Trend","buy":eb,"sell":es,"regime":er},
                {"name":"RSI MeanRev","buy":rb,"sell":rs,"regime":rr},
                {"name":"BB Squeeze","buy":bb,"sell":bs,"regime":br},
                {"name":"FVG","buy":fb,"sell":fs,"regime":fr},
                {"name":"MACD","buy":mb,"sell":ms,"regime":mr},
            ]
        }
    except Exception:
        return None

# ── Background scanner — batch processing ─────────────────────────────
def run_full_scan():
    global _cache
    _cache["running"]=True
    _cache["progress"]=0
    _cache["total"]=len(NIFTY500)
    _cache["results"]=[]
    _cache["error"]=None

    # Fetch all tickers in one batch call — much faster, avoids timeout
    try:
        symbols = " ".join(NIFTY500)
        raw = yf.download(
            symbols,
            period="300d",
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False
        )
    except Exception as e:
        _cache["error"] = str(e)
        _cache["running"] = False
        return

    results = []
    for i, symbol in enumerate(NIFTY500):
        _cache["progress"] = i + 1
        try:
            # Extract this ticker's data from the bulk download
            sym = symbol.replace(".NS","").replace(".BO","")
            if len(NIFTY500) > 1:
                if symbol in raw.columns.get_level_values(0):
                    df = raw[symbol].dropna(subset=["Close"])
                else:
                    continue
            else:
                df = raw.dropna(subset=["Close"])

            if len(df) < 50:
                continue

            eb,es,er=strat_ema(df)
            rb,rs,rr=strat_rsi(df)
            bb,bs,br=strat_bb(df)
            fb,fs,fr=strat_fvg(df)
            mb,ms,mr=strat_macd(df)
            buys=[eb,rb,bb,fb,mb]
            sells=[es,rs,bs,fs,ms]
            ag_b=sum(1 for v in buys if v>=75)
            ag_s=sum(1 for v in sells if v>=75)
            avg_b=sum(buys)/5
            avg_s=sum(sells)/5

            if ag_b>=4 and avg_b>=60 and avg_b>avg_s+15:
                direction="LONG"; score=round(avg_b); ag=ag_b
            elif ag_s>=4 and avg_s>=60 and avg_s>avg_b+15:
                direction="SHORT"; score=round(avg_s); ag=ag_s
            else:
                continue

            c=df["Close"].iloc[-1]
            pc=df["Close"].iloc[-2] if len(df)>1 else c
            a=atr_calc(df).iloc[-1]
            chg=round((c-pc)/pc*100,2)
            sl=round(c-1.5*a,2) if direction=="LONG" else round(c+1.5*a,2)
            tp=round(c+3*a,2) if direction=="LONG" else round(c-3*a,2)
            vol=int(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
            avg_vol=int(df["Volume"].rolling(20).mean().iloc[-1]) if "Volume" in df.columns else 1
            vr=round(vol/avg_vol,1) if avg_vol>0 else 0

            results.append({
                "symbol": sym,
                "direction": direction,
                "score": score,
                "agree": ag,
                "unanimous": ag==5,
                "cmp": round(float(c),2),
                "chg": chg,
                "sl": round(float(sl),2),
                "target": round(float(tp),2),
                "atr": round(float(a),2),
                "vol_ratio": vr,
                "strategies": [
                    {"name":"EMA Trend","buy":eb,"sell":es,"regime":er},
                    {"name":"RSI MeanRev","buy":rb,"sell":rs,"regime":rr},
                    {"name":"BB Squeeze","buy":bb,"sell":bs,"regime":br},
                    {"name":"FVG","buy":fb,"sell":fs,"regime":fr},
                    {"name":"MACD","buy":mb,"sell":ms,"regime":mr},
                ]
            })
        except Exception:
            continue

    longs=sorted([r for r in results if r["direction"]=="LONG"],key=lambda x:x["score"],reverse=True)[:25]
    shorts=sorted([r for r in results if r["direction"]=="SHORT"],key=lambda x:x["score"],reverse=True)[:25]

    _cache["data"] = {
        "date": datetime.now(IST).strftime("%d %b %Y"),
        "time": datetime.now(IST).strftime("%I:%M %p IST"),
        "scanned": len(NIFTY500),
        "total_signals": len(results),
        "longs": longs,
        "shorts": shorts,
    }
    _cache["running"] = False
    _cache["timestamp"] = datetime.now(IST).isoformat()

# ── Routes ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static","index.html")

@app.route("/api/scan", methods=["POST"])
def start_scan():
    if _cache["running"]:
        return jsonify({"status":"running","progress":_cache["progress"],"total":_cache["total"]})
    t=threading.Thread(target=run_full_scan, daemon=True)
    t.start()
    return jsonify({"status":"started"})

@app.route("/api/progress")
def progress():
    return jsonify({
        "running": _cache["running"],
        "progress": _cache["progress"],
        "total": _cache["total"],
        "pct": round(_cache["progress"]/_cache["total"]*100) if _cache["total"] else 0,
        "error": _cache.get("error")
    })

@app.route("/api/results")
def results():
    if not _cache["data"]:
        return jsonify({"error":"No scan data yet. Click Scan Now first."}), 404
    return jsonify(_cache["data"])

@app.route("/api/status")
def status():
    return jsonify({
        "running": _cache["running"],
        "has_data": _cache["data"] is not None,
        "timestamp": _cache["timestamp"],
        "progress": _cache["progress"],
        "total": _cache["total"],
    })

if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0", port=port, debug=False)
