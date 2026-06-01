"""
SignalDesk — Swing Trading Scanner
Scans Nifty 500 for 5-15% monthly swing setups.
Auto-rescans daily. Render.com free tier compatible.
"""
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, date, timezone, timedelta
import threading, os, time, traceback

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
IST = timezone(timedelta(hours=5, minutes=30))

_cache = {
    "data": None, "timestamp": None,
    "running": False, "progress": 0, "total": 0,
    "partial_longs": [], "partial_shorts": [],
    "partial_count": 0, "error": None, "last_auto": None
}

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
    "AUROPHARMA.NS","ALKEM.NS","IPCALAB.NS","DIXON.NS","VOLTAS.NS",
    "CROMPTON.NS","BAJAJELEC.NS","VGUARD.NS","JUBLFOOD.NS","DEVYANI.NS",
    "INDHOTEL.NS","EIHOTEL.NS","LEMONTREE.NS","ESCORTS.NS","TIINDIA.NS",
    "ENDURANCE.NS","MRF.NS","APOLLOTYRE.NS","BALKRISIND.NS","CEATLTD.NS",
    "JKCEMENT.NS","RAMCOCEM.NS","ABCAPITAL.NS","MFSL.NS","ICICIGI.NS",
    "HDFCAMC.NS","NIPPONLIFE.NS","UTIAMC.NS","360ONE.NS","ANGELONE.NS",
    "CDSL.NS","BSE.NS","MCX.NS","NAUKRI.NS","JUSTDIAL.NS",
    "ZYDUSLIFE.NS","MANKIND.NS","GLENMARK.NS","JBCHEPHARM.NS","AJANTPHARM.NS",
    "FLUOROCHEM.NS","CLEAN.NS","FINEORG.NS","AAVAS.NS","HOMEFIRST.NS",
    "CANFINHOME.NS","LICHSGFIN.NS","PNBHOUSING.NS","REPCO.NS","APTUS.NS",
    "TATACOMM.NS","HFCL.NS","RAILTEL.NS","TEJASNET.NS","STLTECH.NS",
    "DELHIVERY.NS","BLUEDART.NS","GESHIP.NS","SCI.NS","MAHLOG.NS",
    "ABFRL.NS","MANYAVAR.NS","SAPPHIRE.NS","VEDANT.NS","RRKABEL.NS",
    "POLYCAB.NS","KEI.NS","FINOLEX.NS","HBLPOWER.NS","APLAPOLLO.NS",
    "RATNAMANI.NS","JINDALSAW.NS","WELSPUNIND.NS","ASTRAL.NS","PRINCEPIPE.NS",
    "SOLARINDS.NS","PREMIER.NS","PARAS.NS","NEULANDLAB.NS","LAURUS.NS",
    "GRANULES.NS","SOLARA.NS","SEQUENT.NS","SUDARSCHEM.NS","IOLCP.NS",
    "PPLPHARMA.NS","VINATIORGA.NS","ROSSARI.NS","TATACHEM.NS","GNFC.NS",
    "DEEPAKNTR.NS","AARTI.NS","NAVINFLUOR.NS","SRF.NS","ALKYLAMINE.NS",
    "NOCIL.NS","ATUL.NS","TIRUMALCHM.NS","BORORENEW.NS","ANDHRSUGAR.NS",
    "COFORGE.NS","MPHASIS.NS","LTTS.NS","PERSISTENT.NS","KPITTECH.NS",
    "TATAELXSI.NS","MASTEK.NS","NIITLTD.NS","ZENSAR.NS","RATEGAIN.NS",
    "ZENSARTECH.NS","FSL.NS","BSOFT.NS","ECLERX.NS","TANLA.NS",
    "GPPL.NS","ADANIGREEN.NS","ADANIPORTS.NS","ADANITRANS.NS","ADANIPOWER.NS",
    "CESC.NS","TORNTPOWER.NS","JSWENERGY.NS","GREENPWR.NS","RENUKA.NS",
    "DHAMPUR.NS","BALRAMCHIN.NS","TRIVENI.NS","EID.NS","BAJAJCON.NS",
    "EMAMILTD.NS","ZYDUSWELL.NS","JYOTHYLAB.NS","GILLETTE.NS","PGHH.NS",
    "VSTIND.NS","GODFRYPHLP.NS","ITC.NS","PATANJALI.NS","BIKAJI.NS",
    "DIAMONDYD.NS","AVANTIFEED.NS","WATERBASE.NS","VENKYS.NS","SKFINDIA.NS",
    "GRINDWELL.NS","SCHAEFFLER.NS","TIMKEN.NS","NSKLTD.NS","ELGIEQUIP.NS",
    "GREAVESCOT.NS","JYOTICNC.NS","KENNAMET.NS","LAKSHMI.NS","TEXMOPIPES.NS",
    "TVSMOTOR.NS","BAJAJ-AUTO.NS","HEROMOTOCO.NS","EICHERMOT.NS","OLECTRA.NS",
    "GOLDWIN.NS","MAHINDCIE.NS","BOSCH.NS","VARROC.NS","SUPRAJIT.NS",
]

# ── Indicators ─────────────────────────────────────────────────────────
def ema(s, p): return s.ewm(span=p, adjust=False).mean()

def atr_calc(df, p=14):
    h,l,c = df["High"],df["Low"],df["Close"]
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()

def rsi_calc(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(span=p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(span=p, adjust=False).mean()
    return 100 - (100 / (1 + g / l.replace(0, np.nan)))

def macd_calc(s):
    ml = ema(s,12) - ema(s,26); sig = ema(ml,9); return ml, sig, ml-sig

def bb_calc(s, p=20, std=2):
    m = s.rolling(p).mean(); sd = s.rolling(p).std()
    return m+std*sd, m, m-std*sd

# ── Holding period estimator ───────────────────────────────────────────
def estimate_holding(df, direction, atr_val, target_pct):
    """Estimate days to reach target based on avg daily range."""
    try:
        daily_move = (df["High"] - df["Low"]).tail(20).mean()
        cmp = df["Close"].iloc[-1]
        target_move = cmp * (target_pct / 100)
        days = max(3, min(30, round(target_move / daily_move * 0.6)))
        if days <= 5: return f"{days}d", "Very short swing"
        if days <= 10: return f"{days}d", "Short swing"
        if days <= 20: return f"{days}d", "Medium swing"
        return f"{days}d", "Positional"
    except:
        return "7–15d", "Swing"

# ── Swing filter — 5-15% monthly potential ────────────────────────────
def swing_filter(df, direction):
    """
    Returns (passes, target_pct, sl_pct, setup_type) for swing trades.
    Targets 5-15% in 5-20 trading days.
    """
    try:
        c = df["Close"].iloc[-1]
        a = atr_calc(df).iloc[-1]
        e20 = ema(df["Close"], 20).iloc[-1]
        e50 = ema(df["Close"], 50).iloc[-1]
        e200 = ema(df["Close"], 200).iloc[-1]
        r = rsi_calc(df["Close"]).iloc[-1]

        # Momentum check — stock must be moving
        ret_20 = (c - df["Close"].iloc[-20]) / df["Close"].iloc[-20] * 100 if len(df) >= 20 else 0
        ret_5  = (c - df["Close"].iloc[-5]) / df["Close"].iloc[-5] * 100 if len(df) >= 5 else 0

        vol = df["Volume"].tail(5).mean() if "Volume" in df.columns else 1
        avg_vol = df["Volume"].tail(20).mean() if "Volume" in df.columns else 1
        vol_surge = vol / avg_vol if avg_vol > 0 else 1

        # ATR-based target: 3x ATR from entry
        atr_target_pct = (3 * a / c) * 100
        atr_sl_pct = (1.5 * a / c) * 100

        # Swing setup classification
        if direction == "LONG":
            # Strong swing: trending + pullback + volume
            if c > e200 and c > e50 and abs(c - e20) < a and vol_surge > 1.2:
                setup = "Trend Pullback"
                target_pct = max(5, min(15, atr_target_pct * 1.2))
            # Breakout swing
            elif c > df["High"].tail(20).iloc[:-1].max() * 0.99:
                setup = "Breakout"
                target_pct = max(6, min(15, atr_target_pct * 1.5))
            # Oversold bounce
            elif r < 35 and c > e200:
                setup = "Oversold Bounce"
                target_pct = max(5, min(12, atr_target_pct))
            else:
                setup = "Swing Long"
                target_pct = max(5, min(12, atr_target_pct))
        else:
            if c < e200 and c < e50 and abs(c - e20) < a:
                setup = "Trend Breakdown"
                target_pct = max(5, min(15, atr_target_pct * 1.2))
            elif r > 65 and c < e200:
                setup = "Overbought Short"
                target_pct = max(5, min(12, atr_target_pct))
            else:
                setup = "Swing Short"
                target_pct = max(5, min(12, atr_target_pct))

        # Must have at least 5% potential, momentum, and volume
        passes = target_pct >= 5 and vol_surge >= 0.8
        return passes, round(target_pct, 1), round(atr_sl_pct, 1), setup
    except:
        return False, 7.0, 3.5, "Swing"

# ── Strategies ─────────────────────────────────────────────────────────
def strat_ema(df):
    if len(df) < 215: return 0,0,"insufficient"
    c,o = df["Close"].iloc[-1], df["Open"].iloc[-1]
    e20 = ema(df["Close"],20).iloc[-1]; e200 = ema(df["Close"],200).iloc[-1]
    a = atr_calc(df).iloc[-1]
    b = (int(c>e200)+int(e20>e200)+int(abs(c-e20)<0.5*a)+int(c>o))*25
    s = (int(c<e200)+int(e20<e200)+int(abs(c-e20)<0.5*a)+int(c<o))*25
    return b, s, "uptrend" if c>e200 else "downtrend"

def strat_rsi(df):
    if len(df) < 60: return 0,0,"insufficient"
    c,o = df["Close"].iloc[-1], df["Open"].iloc[-1]
    r = rsi_calc(df["Close"]); rc,rp = r.iloc[-1], r.iloc[-2]
    e50 = ema(df["Close"],50).iloc[-1]; a = atr_calc(df).iloc[-1]
    b = (int(rc<35)+int(rc>rp)+int(abs(c-e50)<1.5*a)+int(c>o))*25
    s = (int(rc>65)+int(rc<rp)+int(abs(c-e50)<1.5*a)+int(c<o))*25
    return b, s, "oversold" if rc<35 else "overbought" if rc>65 else "ranging"

def strat_bb(df):
    if len(df) < 55: return 0,0,"insufficient"
    c,o = df["Close"].iloc[-1], df["Open"].iloc[-1]
    up,mid,lo = bb_calc(df["Close"])
    bw = (up-lo)/mid; wn = bw.iloc[-1]
    wmin = bw.rolling(50).min().iloc[-1]; wmax = bw.rolling(50).max().iloc[-1]
    wr = wmax-wmin if wmax!=wmin else 1
    sq = int(wn < wmin+0.3*wr)
    vol = df.get("Volume", pd.Series([1]*len(df), index=df.index))
    av = vol.rolling(20).mean().iloc[-1]
    vp = min(int((vol.iloc[-1]/av if av>0 else 1)*12.5), 25)
    b = min((sq*25)+int(c>up.iloc[-1])*25+vp+int(c>o)*25, 100)
    s = min((sq*25)+int(c<lo.iloc[-1])*25+vp+int(c<o)*25, 100)
    return b, s, "squeeze" if sq else "expansion" if wn>wmin+0.7*wr else "normal"

def strat_fvg(df):
    if len(df) < 50: return 0,0,"no data"
    c,o = df["Close"].iloc[-1], df["Open"].iloc[-1]
    hi,lo,cl = df["High"], df["Low"], df["Close"]
    e200 = ema(cl,200).iloc[-1]; a = atr_calc(df).iloc[-1]; htf = int(c>e200)
    buy_sc = sell_sc = 0
    for i in range(min(50,len(df)-3), 2, -1):
        idx = -i
        if lo.iloc[idx] > hi.iloc[idx-2]:
            gs = lo.iloc[idx]-hi.iloc[idx-2]
            if gs > 0.08*a:
                sub = cl.iloc[idx+1:]
                if not any((sub>=hi.iloc[idx-2])&(sub<=lo.iloc[idx])):
                    prox = abs(c-lo.iloc[idx])/a
                    pp = max(0,int(35*(1-prox/0.25))) if prox<0.25 else 0
                    buy_sc = pp+(25 if i<=15 else 0)+(25 if htf else 0)+(15 if c>o else 0)
                    break
        if hi.iloc[idx] < lo.iloc[idx-2]:
            gs = lo.iloc[idx-2]-hi.iloc[idx]
            if gs > 0.08*a:
                sub = cl.iloc[idx+1:]
                if not any((sub>=hi.iloc[idx])&(sub<=lo.iloc[idx-2])):
                    prox = abs(c-hi.iloc[idx])/a
                    pp = max(0,int(35*(1-prox/0.25))) if prox<0.25 else 0
                    sell_sc = pp+(25 if i<=15 else 0)+(25 if not htf else 0)+(15 if c<o else 0)
                    break
    return min(buy_sc,100), min(sell_sc,100), "fvg"

def strat_macd(df):
    if len(df) < 215: return 0,0,"insufficient"
    c,o = df["Close"].iloc[-1], df["Open"].iloc[-1]
    e200 = ema(df["Close"],200).iloc[-1]
    ml,sig,hist = macd_calc(df["Close"])
    mlc,sc = ml.iloc[-1], sig.iloc[-1]; hn,hp = hist.iloc[-1], hist.iloc[-2]
    fc = any(ml.iloc[i]>sig.iloc[i] and ml.iloc[i-1]<=sig.iloc[i-1] for i in range(-3,0))
    fb = any(ml.iloc[i]<sig.iloc[i] and ml.iloc[i-1]>=sig.iloc[i-1] for i in range(-3,0))
    b = (int(c>e200)+int(mlc>sc)+int(hn>0 and hn>hp)+int(fc))*25
    s = (int(c<e200)+int(mlc<sc)+int(hn<0 and hn<hp)+int(fb))*25
    return b, s, "momentum_up" if b>50 else "momentum_down" if s>50 else "neutral"

# ── Scan one stock ─────────────────────────────────────────────────────
def scan_one(symbol):
    try:
        df = yf.Ticker(symbol).history(period="300d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 60: return None
        df = df.dropna(subset=["Close"])

        eb,es,er = strat_ema(df); rb,rs,rr = strat_rsi(df)
        bb,bs,br = strat_bb(df); fb,fs,fr = strat_fvg(df); mb,ms,mr = strat_macd(df)
        buys=[eb,rb,bb,fb,mb]; sells=[es,rs,bs,fs,ms]
        ag_b = sum(1 for v in buys if v>=75); ag_s = sum(1 for v in sells if v>=75)
        avg_b = sum(buys)/5; avg_s = sum(sells)/5

        if ag_b >= 4 and avg_b >= 60 and avg_b > avg_s+15:
            direction = "LONG"; score = round(avg_b); ag = ag_b
        elif ag_s >= 4 and avg_s >= 60 and avg_s > avg_b+15:
            direction = "SHORT"; score = round(avg_s); ag = ag_s
        else:
            return None

        # Swing filter — must have 5-15% monthly potential
        passes, target_pct, sl_pct, setup_type = swing_filter(df, direction)
        if not passes: return None

        c = float(df["Close"].iloc[-1])
        pc = float(df["Close"].iloc[-2]) if len(df)>1 else c
        a = float(atr_calc(df).iloc[-1])
        chg = round((c-pc)/pc*100, 2)

        # Compute actual price levels
        sl = round(c*(1-sl_pct/100), 2) if direction=="LONG" else round(c*(1+sl_pct/100), 2)
        tp = round(c*(1+target_pct/100), 2) if direction=="LONG" else round(c*(1-target_pct/100), 2)

        # Holding period
        hold_days, hold_label = estimate_holding(df, direction, a, target_pct)

        vol = int(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
        avg_vol = int(df["Volume"].rolling(20).mean().iloc[-1]) if "Volume" in df.columns else 1
        vr = round(vol/avg_vol, 1) if avg_vol>0 else 0

        # Risk:Reward
        risk = abs(c - sl); reward = abs(tp - c)
        rr_ratio = round(reward/risk, 1) if risk > 0 else 0

        return {
            "symbol": symbol.replace(".NS","").replace(".BO",""),
            "direction": direction, "score": score, "agree": ag,
            "unanimous": ag==5, "setup": setup_type,
            "cmp": round(c,2), "chg": chg,
            "sl": sl, "target": tp,
            "sl_pct": sl_pct, "target_pct": target_pct,
            "hold": hold_days, "hold_label": hold_label,
            "rr": rr_ratio, "atr": round(a,2), "vol_ratio": vr,
            "strategies":[
                {"name":"EMA Trend","buy":eb,"sell":es,"regime":er},
                {"name":"RSI MeanRev","buy":rb,"sell":rs,"regime":rr},
                {"name":"BB Squeeze","buy":bb,"sell":bs,"regime":br},
                {"name":"FVG","buy":fb,"sell":fs,"regime":fr},
                {"name":"MACD","buy":mb,"sell":ms,"regime":mr},
            ]
        }
    except Exception:
        return None

# ── Full scan ──────────────────────────────────────────────────────────
def run_full_scan():
    global _cache
    _cache.update({
        "running":True, "progress":0, "total":len(NIFTY500),
        "partial_longs":[], "partial_shorts":[], "partial_count":0, "error":None
    })
    results = []
    for i, sym in enumerate(NIFTY500):
        r = scan_one(sym)
        if r:
            results.append(r)
            longs  = sorted([x for x in results if x["direction"]=="LONG"],  key=lambda x:x["score"], reverse=True)[:25]
            shorts = sorted([x for x in results if x["direction"]=="SHORT"], key=lambda x:x["score"], reverse=True)[:25]
            _cache["partial_longs"]  = longs
            _cache["partial_shorts"] = shorts
            _cache["partial_count"]  = len(results)
        _cache["progress"] = i + 1

    longs  = sorted([r for r in results if r["direction"]=="LONG"],  key=lambda x:x["score"], reverse=True)[:25]
    shorts = sorted([r for r in results if r["direction"]=="SHORT"], key=lambda x:x["score"], reverse=True)[:25]
    now = datetime.now(IST)
    _cache.update({
        "running": False,
        "data": {
            "date": now.strftime("%d %b %Y"),
            "time": now.strftime("%I:%M %p IST"),
            "scanned": len(NIFTY500),
            "total_signals": len(results),
            "longs": longs, "shorts": shorts,
        },
        "timestamp": now.isoformat(),
        "last_auto": now.isoformat()
    })

# ── Auto-scan scheduler — runs at 9:15 AM IST daily ───────────────────
def auto_scheduler():
    while True:
        now = datetime.now(IST)
        # Run at 9:15 AM IST on weekdays (Mon-Fri)
        if now.weekday() < 5 and now.hour == 9 and now.minute == 15:
            if not _cache["running"]:
                threading.Thread(target=run_full_scan, daemon=True).start()
            time.sleep(60)  # prevent double trigger
        time.sleep(30)

# Start auto-scheduler in background
threading.Thread(target=auto_scheduler, daemon=True).start()

# ── Routes ─────────────────────────────────────────────────────────────
@app.route("/")
def index(): return send_from_directory("static","index.html")

@app.route("/api/scan", methods=["POST"])
def start_scan():
    if _cache["running"]:
        return jsonify({"status":"running","progress":_cache["progress"],"total":_cache["total"]})
    threading.Thread(target=run_full_scan, daemon=True).start()
    return jsonify({"status":"started"})

@app.route("/api/progress")
def progress():
    p = _cache["progress"]; t = _cache["total"] or 1
    return jsonify({
        "running": _cache["running"],
        "progress": p, "total": _cache["total"],
        "pct": round(p/t*100),
        "partial_count": _cache["partial_count"],
        "error": _cache.get("error"),
        "longs": _cache["partial_longs"],
        "shorts": _cache["partial_shorts"],
        "scanned": p,
    })

@app.route("/api/results")
def results():
    if not _cache["data"]:
        return jsonify({"error":"No scan yet. Click Scan Now."}), 404
    return jsonify(_cache["data"])

@app.route("/api/status")
def status():
    return jsonify({
        "running": _cache["running"], "has_data": _cache["data"] is not None,
        "timestamp": _cache["timestamp"], "progress": _cache["progress"],
        "total": _cache["total"], "last_auto": _cache["last_auto"]
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
