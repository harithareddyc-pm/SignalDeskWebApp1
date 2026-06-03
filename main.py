"""
SignalDesk V2.2 — Production Scanner
Nifty 500 + MCX India Commodities
Upgrades: Relative Strength, Market Breadth, Composite Ranking
Signal Tracker built in.
Auto-scans every 15 minutes during market hours.
"""
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone, timedelta
import threading, os, time, json

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
IST = timezone(timedelta(hours=5, minutes=30))

# ── Signal log (in-memory, persisted to JSON file) ─────────────────────
SIGNAL_LOG_FILE = "signal_log.json"

def load_signal_log():
    try:
        if os.path.exists(SIGNAL_LOG_FILE):
            with open(SIGNAL_LOG_FILE) as f:
                return json.load(f)
    except: pass
    return []

def save_signal_log(log):
    try:
        with open(SIGNAL_LOG_FILE, "w") as f:
            json.dump(log, f, indent=2)
    except: pass

signal_log = load_signal_log()

# ── Cache ──────────────────────────────────────────────────────────────
def empty_cache():
    return {"data":None,"running":False,"progress":0,"total":0,
            "partial_longs":[],"partial_shorts":[],"partial_count":0,"ts":None}

_nifty = empty_cache()
_mcx   = empty_cache()

# ── Nifty 500 — full list ──────────────────────────────────────────────
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
    "APOLLOHOSP.NS","BAJAJ-AUTO.NS","SBILIFE.NS","ICICIPRULI.NS","SHRIRAMFIN.NS",
    "PIDILITIND.NS","SIEMENS.NS","HAVELLS.NS","DMART.NS","MUTHOOTFIN.NS",
    "TORNTPHARM.NS","LUPIN.NS","DABUR.NS","MARICO.NS","BERGEPAINT.NS",
    "COLPAL.NS","GODREJCP.NS","AMBUJACEM.NS","ACC.NS","SHREECEM.NS",
    "PFC.NS","RECLTD.NS","BANKBARODA.NS","CANBK.NS","PNB.NS",
    "FEDERALBNK.NS","IDFCFIRSTB.NS","BANDHANBNK.NS","CHOLAFIN.NS","TATAPOWER.NS",
    "HAL.NS","BEL.NS","BHEL.NS","ZOMATO.NS","IRCTC.NS",
    "CONCOR.NS","GAIL.NS","IGL.NS","TRENT.NS","PAGEIND.NS",
    "VEDL.NS","NMDC.NS","SAIL.NS","HINDZINC.NS","NATIONALUM.NS",
    "MOTHERSON.NS","NHPC.NS","IRFC.NS","HUDCO.NS","MGL.NS",
    "ADANIENT.NS","ADANIGREEN.NS","ADANITRANS.NS","ADANIPOWER.NS","ADANIWILMAR.NS",
    "HDFCAMC.NS","NIPPONLIFE.NS","UTIAMC.NS","360ONE.NS","ANGELONE.NS",
    "CDSL.NS","BSE.NS","MCX.NS","ICICIGI.NS","MFSL.NS",
    "ABCAPITAL.NS","BAJAJHLDNG.NS","M&MFIN.NS","MANAPPURAM.NS",
    "AAVAS.NS","CANFINHOME.NS","LICHSGFIN.NS","PNBHOUSING.NS","APTUS.NS",
    "HOMEFIRST.NS","REPCO.NS","CREDITACC.NS","UJJIVAN.NS","EQUITASBNK.NS",
    "KARURVYSYA.NS","CITYUNIONB.NS","DCBBANK.NS","RBLBANK.NS","YESBANK.NS",
    "INDIANB.NS","UCOBANK.NS","CENTRALBK.NS","UNIONBANK.NS","BANKINDIA.NS",
    "KFINTECH.NS","CAMS.NS","NSDL.NS",
    "COFORGE.NS","MPHASIS.NS","LTTS.NS","PERSISTENT.NS","KPITTECH.NS",
    "TATAELXSI.NS","MASTEK.NS","ZENSAR.NS","RATEGAIN.NS","BSOFT.NS",
    "ECLERX.NS","TANLA.NS","INTELLECT.NS","NEWGEN.NS","CYIENT.NS",
    "BIRLASOFT.NS","LTIMINDTREE.NS","SONATSOFTW.NS","ROUTE.NS","NAUKRI.NS",
    "JUSTDIAL.NS","INDIAMART.NS","CARTRADE.NS","EASEMYTRIP.NS","DELHIVERY.NS",
    "NYKAA.NS","PAYTM.NS","POLICYBZR.NS","MATRIMONY.NS",
    "AUROPHARMA.NS","ALKEM.NS","IPCALAB.NS","ZYDUSLIFE.NS","MANKIND.NS",
    "GLENMARK.NS","JBCHEPHARM.NS","AJANTPHARM.NS","LAURUS.NS","GRANULES.NS",
    "NATCOPHARM.NS","NEULANDLAB.NS","GLAXO.NS","PFIZER.NS","ABBOTT.NS",
    "SANOFI.NS","FLUOROCHEM.NS","CLEAN.NS","FINEORG.NS","IOLCP.NS",
    "VINATIORGA.NS","ROSSARI.NS","JUBILANT.NS","FORTIS.NS","MAXHEALTH.NS",
    "METROPOLIS.NS","KIMS.NS","RAINBOW.NS","STARHEALTH.NS",
    "TVSMOTOR.NS","OLECTRA.NS","BOSCH.NS","SUPRAJIT.NS","MAHINDCIE.NS",
    "ENDURANCE.NS","MRF.NS","APOLLOTYRE.NS","BALKRISIND.NS","CEATLTD.NS",
    "GOODYEAR.NS","TIINDIA.NS","ESCORTS.NS","SONACOMS.NS","CRAFTSMAN.NS",
    "GABRIEL.NS","LUMAXIND.NS","SUBROS.NS","ASHOKLEY.NS","FORCEMOT.NS",
    "EMAMILTD.NS","ZYDUSWELL.NS","JYOTHYLAB.NS","GILLETTE.NS","PGHH.NS",
    "VSTIND.NS","GODFRYPHLP.NS","BIKAJI.NS","AVANTIFEED.NS","VENKYS.NS",
    "RADICO.NS","VMART.NS","SHOPERSTOP.NS","BATAIND.NS","RELAXO.NS",
    "RAYMOND.NS","ARVIND.NS","RUPA.NS","DOLLAR.NS","LUX.NS",
    "TRIDENT.NS","VARDHMAN.NS","ALOK.NS","ABFRL.NS","MANYAVAR.NS",
    "SAPPHIRE.NS","VEDANT.NS","NBCC.NS","RVNL.NS","IRCON.NS",
    "HCC.NS","PNCINFRA.NS","KNRCON.NS","CAPACITE.NS","ITD.NS",
    "GMRINFRA.NS","JSWINFRA.NS","DLF.NS","GODREJPROP.NS","OBEROIRLTY.NS",
    "PHOENIXLTD.NS","PRESTIGE.NS","BRIGADE.NS","SOBHA.NS","MAHLIFE.NS",
    "KOLTEPATIL.NS","ANANTRAJ.NS","ASTRAL.NS","PRINCEPIPE.NS","SUPREMEIND.NS",
    "POLYCAB.NS","KEI.NS","RRKABEL.NS","HBLPOWER.NS","APAR.NS",
    "CESC.NS","TORNTPOWER.NS","JSWENERGY.NS","SJVN.NS","GIPCL.NS",
    "HINDPETRO.NS","MRPL.NS","PETRONET.NS","GUJGASLTD.NS","ATGL.NS",
    "IREDA.NS","RPOWER.NS","JPPOWER.NS",
    "APLAPOLLO.NS","RATNAMANI.NS","JINDALSAW.NS","MOIL.NS","NALCO.NS",
    "KALYANKJIL.NS","GALLANTT.NS","TATASPONGE.NS","TINPLATE.NS",
    "HEIDELBERG.NS","BIRLACORPN.NS","INDIACEM.NS","DALMIACEM.NS",
    "ORIENTCEM.NS","PRISMJOHNS.NS","JKCEMENT.NS","RAMCOCEM.NS",
    "ABB.NS","CGPOWER.NS","THERMAX.NS","VOLTAS.NS","BLUESTARCO.NS",
    "SYMPHONY.NS","WHIRLPOOL.NS","AMBER.NS","DIXON.NS","KAYNES.NS",
    "SYRMA.NS","DATAPATTNS.NS","ELGIEQUIP.NS","GRINDWELL.NS","SCHAEFFLER.NS",
    "TIMKEN.NS","SKFINDIA.NS","GREAVESCOT.NS","ELECON.NS","LAKSHMI.NS",
    "MIDHANI.NS","BEML.NS","MTAR.NS","COCHINSHIP.NS","GRSE.NS",
    "MAZAGON.NS","TITAGARH.NS","TEXRAIL.NS",
    "TATACOMM.NS","HFCL.NS","RAILTEL.NS","TEJASNET.NS","STLTECH.NS",
    "ZEEL.NS","SUNTV.NS","PVRINOX.NS",
    "ALKYLAMINE.NS","NOCIL.NS","ATUL.NS","TIRUMALCHM.NS","TATACHEM.NS",
    "GNFC.NS","DEEPAKNTR.NS","AARTI.NS","NAVINFLUOR.NS","SRF.NS",
    "KRBL.NS","DHAMPUR.NS","BALRAMCHIN.NS","TRIVENI.NS","EID.NS",
    "RENUKA.NS","DCMSHRIRAM.NS","CHAMBAL.NS","COROMANDEL.NS",
    "HATSUN.NS","HERITAGE.NS","JUBLFOOD.NS","DEVYANI.NS",
    "INDHOTEL.NS","EIHOTEL.NS","CHALET.NS","LEMONTREE.NS",
    "INDIGO.NS","SPICEJET.NS","BLUEDART.NS","GESHIP.NS","SCI.NS",
    "VRL.NS","SNOWMAN.NS","ALLCARGO.NS","MAHLOG.NS",
    "CASTROLIND.NS","BALMER.NS","VAIBHAVGBL.NS","BAJAJCON.NS",
    "MANAKSIA.NS","SUTLEJ.NS","HIMATSEIDE.NS","NITIN.NS",
    "SUDARSCHEM.NS","ROSSARI.NS","CLEAN.NS",
    "FINOLEX.NS","JYOTICNC.NS","NETWORK18.NS","SPENCERS.NS",
    "KSCL.NS","LTFH.NS","IDFC.NS","MAHABANK.NS","IOB.NS",
]
# Deduplicate preserving order
NIFTY500 = list(dict.fromkeys(NIFTY500))

# ── MCX India Commodities (global futures proxies via yfinance) ────────
MCX_SYMBOLS = {
    "GC=F":  {"name":"Gold",        "unit":"per 10g",  "multiplier":0.0321507*10, "base":"$"},
    "SI=F":  {"name":"Silver",      "unit":"per kg",   "multiplier":0.0321507*1000,"base":"$"},
    "CL=F":  {"name":"Crude Oil",   "unit":"per bbl",  "multiplier":1,            "base":"$"},
    "BZ=F":  {"name":"Brent Crude", "unit":"per bbl",  "multiplier":1,            "base":"$"},
    "NG=F":  {"name":"Natural Gas", "unit":"per mmBtu","multiplier":1,            "base":"$"},
    "HG=F":  {"name":"Copper",      "unit":"per kg",   "multiplier":2.20462,      "base":"$"},
    "ALI=F": {"name":"Aluminium",   "unit":"per kg",   "multiplier":0.453592,     "base":"$"},
    "ZN=F":  {"name":"Zinc",        "unit":"per kg",   "multiplier":0.453592,     "base":"$"},
    "PB=F":  {"name":"Lead",        "unit":"per kg",   "multiplier":0.453592,     "base":"$"},
    "NI=F":  {"name":"Nickel",      "unit":"per kg",   "multiplier":0.453592,     "base":"$"},
    "CT=F":  {"name":"Cotton",      "unit":"per bale", "multiplier":1,            "base":"$"},
    "KC=F":  {"name":"Coffee",      "unit":"per bag",  "multiplier":1,            "base":"$"},
    "PL=F":  {"name":"Platinum",    "unit":"per 10g",  "multiplier":0.0321507*10, "base":"$"},
    "PA=F":  {"name":"Palladium",   "unit":"per 10g",  "multiplier":0.0321507*10, "base":"$"},
}

# ── Indicators ─────────────────────────────────────────────────────────
def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def sma(s,p): return s.rolling(p).mean()

def atr_calc(df,p=14):
    h,l,c=df["High"],df["Low"],df["Close"]
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(span=p,adjust=False).mean()

def rsi_calc(s,p=14):
    d=s.diff(); g=d.clip(lower=0).ewm(span=p,adjust=False).mean()
    l=(-d.clip(upper=0)).ewm(span=p,adjust=False).mean()
    return 100-(100/(1+g/l.replace(0,np.nan)))

def macd_calc(s):
    ml=ema(s,12)-ema(s,26); sig=ema(ml,9); return ml,sig,ml-sig

def bb_calc(s,p=20,std=2):
    m=s.rolling(p).mean(); sd=s.rolling(p).std(); return m+std*sd,m,m-std*sd

# ── V2.2: Relative Strength Score ─────────────────────────────────────
def relative_strength(df, benchmark_returns=None):
    """
    RS Score 0-100.
    Compares stock's return over 1m, 3m, 6m vs its own history.
    If benchmark returns provided, compares against index.
    """
    try:
        c = df["Close"]
        if len(c) < 130: return 50
        r1 = (c.iloc[-1]/c.iloc[-21]-1)*100  if len(c)>21  else 0
        r3 = (c.iloc[-1]/c.iloc[-63]-1)*100  if len(c)>63  else 0
        r6 = (c.iloc[-1]/c.iloc[-126]-1)*100 if len(c)>126 else 0
        # Weighted composite: 40% recent, 35% medium, 25% long
        composite = 0.40*r1 + 0.35*r3 + 0.25*r6
        if benchmark_returns:
            b1,b3,b6 = benchmark_returns
            bcomp = 0.40*b1 + 0.35*b3 + 0.25*b6
            composite = composite - bcomp  # relative to benchmark
        # Normalise to 0-100 using sigmoid-like mapping
        score = 50 + composite * 2
        return max(0, min(100, round(score)))
    except: return 50

# ── V2.2: Market Breadth ───────────────────────────────────────────────
_breadth_cache = {"score": 50, "ts": None, "advancing": 0, "declining": 0, "total": 0}

def compute_breadth(sample_symbols, n=80):
    """Compute advance/decline ratio from a sample of stocks."""
    sample = sample_symbols[:n]
    advancing = declining = 0
    try:
        data = yf.download(
            " ".join(sample), period="5d", interval="1d",
            auto_adjust=True, group_by="ticker",
            threads=True, progress=False
        )
        for sym in sample:
            try:
                if len(sample) > 1:
                    if sym not in data.columns.get_level_values(0): continue
                    closes = data[sym]["Close"].dropna()
                else:
                    closes = data["Close"].dropna()
                if len(closes) >= 2:
                    if closes.iloc[-1] > closes.iloc[-2]: advancing += 1
                    else: declining += 1
            except: continue
    except: pass
    total = advancing + declining
    score = round((advancing / total * 100)) if total > 0 else 50
    _breadth_cache.update({
        "score": score, "advancing": advancing,
        "declining": declining, "total": total,
        "ts": datetime.now(IST).isoformat()
    })
    return score

# ── V2.2: Composite Ranking ────────────────────────────────────────────
def composite_rank(signal_score, rs_score, breadth_score, vol_ratio, rr, direction):
    """
    Composite rank 0-100 combining:
    - Signal strength (40%)
    - Relative strength (25%)
    - Market breadth alignment (15%)
    - Volume confirmation (10%)
    - Risk:Reward (10%)
    """
    # Breadth alignment: bullish breadth favours longs, bearish favours shorts
    if direction == "LONG":
        breadth_align = breadth_score  # high breadth = bullish = good for longs
    else:
        breadth_align = 100 - breadth_score  # low breadth = bearish = good for shorts

    # Volume score (cap at 3x)
    vol_score = min(100, round(vol_ratio / 3 * 100))

    # RR score (cap at 3:1)
    rr_score = min(100, round(rr / 3 * 100))

    composite = (
        0.40 * signal_score +
        0.25 * rs_score +
        0.15 * breadth_align +
        0.10 * vol_score +
        0.10 * rr_score
    )
    return round(composite)

# ── Strategies ─────────────────────────────────────────────────────────
def strat_ema(df):
    n = 200 if len(df) >= 215 else 50
    if len(df) < n+15: return 0,0,"insufficient"
    c,o = df["Close"].iloc[-1],df["Open"].iloc[-1]
    e20 = ema(df["Close"],20).iloc[-1]
    e200 = ema(df["Close"],n).iloc[-1]
    a = atr_calc(df).iloc[-1]
    b=(int(c>e200)+int(e20>e200)+int(abs(c-e20)<0.5*a)+int(c>o))*25
    s=(int(c<e200)+int(e20<e200)+int(abs(c-e20)<0.5*a)+int(c<o))*25
    return b,s,"uptrend" if c>e200 else "downtrend"

def strat_rsi(df):
    if len(df)<60: return 0,0,"insufficient"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    r=rsi_calc(df["Close"]); rc,rp=r.iloc[-1],r.iloc[-2]
    e50=ema(df["Close"],50).iloc[-1]; a=atr_calc(df).iloc[-1]
    b=(int(rc<35)+int(rc>rp)+int(abs(c-e50)<1.5*a)+int(c>o))*25
    s=(int(rc>65)+int(rc<rp)+int(abs(c-e50)<1.5*a)+int(c<o))*25
    return b,s,"oversold" if rc<35 else "overbought" if rc>65 else "ranging"

def strat_bb(df):
    if len(df)<55: return 0,0,"insufficient"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    up,mid,lo=bb_calc(df["Close"])
    bw=(up-lo)/mid; wn=bw.iloc[-1]
    wmin=bw.rolling(50).min().iloc[-1]; wmax=bw.rolling(50).max().iloc[-1]
    wr=wmax-wmin if wmax!=wmin else 1; sq=int(wn<wmin+0.3*wr)
    vol=df.get("Volume",pd.Series([1]*len(df),index=df.index))
    av=vol.rolling(20).mean().iloc[-1]
    vp=min(int((vol.iloc[-1]/av if av>0 else 1)*12.5),25)
    b=min((sq*25)+int(c>up.iloc[-1])*25+vp+int(c>o)*25,100)
    s=min((sq*25)+int(c<lo.iloc[-1])*25+vp+int(c<o)*25,100)
    return b,s,"squeeze" if sq else "expansion" if wn>wmin+0.7*wr else "normal"

def strat_fvg(df):
    if len(df)<50: return 0,0,"no data"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    hi,lo,cl=df["High"],df["Low"],df["Close"]
    n=200 if len(df)>=215 else 50
    e200=ema(cl,n).iloc[-1]; a=atr_calc(df).iloc[-1]; htf=int(c>e200)
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
                    buy_sc=pp+(25 if i<=15 else 0)+(25 if htf else 0)+(15 if c>o else 0); break
        if hi.iloc[idx]<lo.iloc[idx-2]:
            gs=lo.iloc[idx-2]-hi.iloc[idx]
            if gs>0.08*a:
                sub=cl.iloc[idx+1:]
                if not any((sub>=hi.iloc[idx])&(sub<=lo.iloc[idx-2])):
                    prox=abs(c-hi.iloc[idx])/a
                    pp=max(0,int(35*(1-prox/0.25))) if prox<0.25 else 0
                    sell_sc=pp+(25 if i<=15 else 0)+(25 if not htf else 0)+(15 if c<o else 0); break
    return min(buy_sc,100),min(sell_sc,100),"fvg"

def strat_macd(df):
    if len(df)<35: return 0,0,"insufficient"
    c,o=df["Close"].iloc[-1],df["Open"].iloc[-1]
    n=200 if len(df)>=215 else 50
    e200=ema(df["Close"],n).iloc[-1]
    ml,sig,hist=macd_calc(df["Close"])
    mlc,sc=ml.iloc[-1],sig.iloc[-1]; hn,hp=hist.iloc[-1],hist.iloc[-2]
    fc=any(ml.iloc[i]>sig.iloc[i] and ml.iloc[i-1]<=sig.iloc[i-1] for i in range(-3,0))
    fb=any(ml.iloc[i]<sig.iloc[i] and ml.iloc[i-1]>=sig.iloc[i-1] for i in range(-3,0))
    b=(int(c>e200)+int(mlc>sc)+int(hn>0 and hn>hp)+int(fc))*25
    s=(int(c<e200)+int(mlc<sc)+int(hn<0 and hn<hp)+int(fb))*25
    return b,s,"momentum_up" if b>50 else "momentum_down" if s>50 else "neutral"

# ── Swing filter ───────────────────────────────────────────────────────
def swing_filter(df,direction):
    try:
        c=df["Close"].iloc[-1]; a=atr_calc(df).iloc[-1]
        e20=ema(df["Close"],20).iloc[-1]
        n=200 if len(df)>=215 else 50
        e200=ema(df["Close"],n).iloc[-1]
        r=rsi_calc(df["Close"]).iloc[-1]
        vol=df.get("Volume",pd.Series([1]*len(df),index=df.index))
        av=vol.rolling(20).mean().iloc[-1]
        vol_surge=vol.iloc[-1]/av if av>0 else 1
        atr_tp=(3*a/c)*100; atr_sl=(1.5*a/c)*100
        if direction=="LONG":
            if c>e200 and abs(c-e20)<a and vol_surge>1.2: setup="Trend Pullback"; tp=max(5,min(15,atr_tp*1.2))
            elif c>df["High"].tail(20).iloc[:-1].max()*0.99: setup="Breakout"; tp=max(6,min(15,atr_tp*1.5))
            elif r<35 and c>e200: setup="Oversold Bounce"; tp=max(5,min(12,atr_tp))
            else: setup="Swing Long"; tp=max(5,min(12,atr_tp))
        else:
            if c<e200 and abs(c-e20)<a: setup="Trend Breakdown"; tp=max(5,min(15,atr_tp*1.2))
            elif r>65 and c<e200: setup="Overbought Short"; tp=max(5,min(12,atr_tp))
            else: setup="Swing Short"; tp=max(5,min(12,atr_tp))
        passes=tp>=4 and vol_surge>=0.5
        return passes,round(tp,1),round(atr_sl,1),setup
    except: return True,7.0,3.5,"Swing"

def estimate_holding(df,target_pct):
    try:
        daily=(df["High"]-df["Low"]).tail(20).mean()
        c=df["Close"].iloc[-1]; move=c*(target_pct/100)
        days=max(3,min(30,round(move/daily*0.6)))
        if days<=5: return f"{days}d","Very short swing"
        if days<=10: return f"{days}d","Short swing"
        if days<=20: return f"{days}d","Medium swing"
        return f"{days}d","Positional"
    except: return "7-15d","Swing"

# ── Scan one symbol ────────────────────────────────────────────────────
def scan_one(symbol, friendly_name=None, currency="₹", min_agree=4, breadth=50):
    try:
        df=yf.Ticker(symbol).history(period="300d",interval="1d",auto_adjust=True)
        if df is None or len(df)<55: return None
        df=df.dropna(subset=["Close"])
        eb,es,er=strat_ema(df); rb,rs,rr=strat_rsi(df)
        bb_b,bb_s,bb_r=strat_bb(df); fb,fs,fr=strat_fvg(df); mb,ms,mr=strat_macd(df)
        buys=[eb,rb,bb_b,fb,mb]; sells=[es,rs,bb_s,fs,ms]
        ag_b=sum(1 for v in buys if v>=75); ag_s=sum(1 for v in sells if v>=75)
        avg_b=sum(buys)/5; avg_s=sum(sells)/5
        if ag_b>=min_agree and avg_b>=55 and avg_b>avg_s+15:
            direction="LONG"; score=round(avg_b); ag=ag_b
        elif ag_s>=min_agree and avg_s>=55 and avg_s>avg_b+15:
            direction="SHORT"; score=round(avg_s); ag=ag_s
        else: return None
        passes,tpct,slpct,setup=swing_filter(df,direction)
        if not passes: return None
        c=float(df["Close"].iloc[-1]); pc=float(df["Close"].iloc[-2]) if len(df)>1 else c
        a=float(atr_calc(df).iloc[-1]); chg=round((c-pc)/pc*100,2)
        sl=round(c*(1-slpct/100),2) if direction=="LONG" else round(c*(1+slpct/100),2)
        tp=round(c*(1+tpct/100),2) if direction=="LONG" else round(c*(1-tpct/100),2)
        hold,hold_lbl=estimate_holding(df,tpct)
        vol=int(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
        avg_vol=int(df["Volume"].rolling(20).mean().iloc[-1]) if "Volume" in df.columns else 1
        vr=round(vol/avg_vol,1) if avg_vol>0 else 0
        risk=abs(c-sl); reward=abs(tp-c)
        rr_ratio=round(reward/risk,1) if risk>0 else 0
        # V2.2 upgrades
        rs=relative_strength(df)
        comp=composite_rank(score,rs,breadth,vr,rr_ratio,direction)
        sym=friendly_name or symbol.replace(".NS","").replace(".BO","").replace("=F","")
        return {
            "symbol":sym,"ticker":symbol,"direction":direction,
            "score":score,"comp_rank":comp,"rs_score":rs,
            "agree":ag,"unanimous":ag==5,"setup":setup,
            "cmp":round(c,2),"chg":chg,"sl":sl,"target":tp,
            "sl_pct":slpct,"target_pct":tpct,"hold":hold,
            "hold_label":hold_lbl,"rr":rr_ratio,"atr":round(a,2),
            "vol_ratio":vr,"currency":currency,
            "date":datetime.now(IST).strftime("%d %b %Y"),
            "time":datetime.now(IST).strftime("%H:%M IST"),
            "strategies":[
                {"name":"EMA Trend","buy":eb,"sell":es,"regime":er},
                {"name":"RSI MeanRev","buy":rb,"sell":rs,"regime":rr},
                {"name":"BB Squeeze","buy":bb_b,"sell":bb_s,"regime":bb_r},
                {"name":"FVG","buy":fb,"sell":fs,"regime":fr},
                {"name":"MACD","buy":mb,"sell":ms,"regime":mr},
            ]
        }
    except Exception: return None

# ── Scanner runners ────────────────────────────────────────────────────
def run_scan(symbols_list, cache, is_mcx=False, min_agree=4):
    # First compute breadth
    breadth = _breadth_cache["score"]
    if not is_mcx:
        threading.Thread(target=lambda: compute_breadth(symbols_list), daemon=True).start()

    if is_mcx:
        items = [(k, v["name"], "$") for k,v in symbols_list.items()]
    else:
        items = [(s, None, "₹") for s in symbols_list]

    cache.update({"running":True,"progress":0,"total":len(items),
                  "partial_longs":[],"partial_shorts":[],"partial_count":0})
    results = []
    for i,(sym,name,cur) in enumerate(items):
        r = scan_one(sym, name, cur, min_agree, breadth)
        if r:
            results.append(r)
            longs  = sorted([x for x in results if x["direction"]=="LONG"],
                           key=lambda x:x["comp_rank"], reverse=True)[:25]
            shorts = sorted([x for x in results if x["direction"]=="SHORT"],
                           key=lambda x:x["comp_rank"], reverse=True)[:25]
            cache["partial_longs"]  = longs
            cache["partial_shorts"] = shorts
            cache["partial_count"]  = len(results)
        cache["progress"] = i+1

    now = datetime.now(IST)
    longs  = sorted([r for r in results if r["direction"]=="LONG"],
                   key=lambda x:x["comp_rank"], reverse=True)[:25]
    shorts = sorted([r for r in results if r["direction"]=="SHORT"],
                   key=lambda x:x["comp_rank"], reverse=True)[:25]
    cache.update({
        "running":False,"ts":now.isoformat(),
        "data":{
            "date":now.strftime("%d %b %Y"),
            "time":now.strftime("%I:%M %p IST"),
            "scanned":len(items),
            "total_signals":len(results),
            "longs":longs,"shorts":shorts,
            "breadth":_breadth_cache,
        }
    })

def scan_nifty(): run_scan(NIFTY500, _nifty, is_mcx=False, min_agree=4)
def scan_mcx():   run_scan(MCX_SYMBOLS, _mcx,  is_mcx=True,  min_agree=3)

# ── Auto scheduler ─────────────────────────────────────────────────────
def scheduler():
    time.sleep(5)
    threading.Thread(target=scan_nifty, daemon=True).start()
    time.sleep(15)
    threading.Thread(target=scan_mcx, daemon=True).start()
    while True:
        time.sleep(60)
        now = datetime.now(IST)
        is_weekday = now.weekday() < 5
        at_15 = now.minute % 15 == 0 and now.second < 90
        nifty_hours = is_weekday and 9 <= now.hour < 16
        mcx_hours   = is_weekday and (9 <= now.hour < 16 or 18 <= now.hour < 24)
        if at_15:
            if nifty_hours and not _nifty["running"]:
                threading.Thread(target=scan_nifty, daemon=True).start()
            if mcx_hours and not _mcx["running"]:
                threading.Thread(target=scan_mcx, daemon=True).start()

threading.Thread(target=scheduler, daemon=True).start()

# ── Routes ─────────────────────────────────────────────────────────────
@app.route("/")
def index(): return send_from_directory("static","index.html")

def prog_payload(cache):
    p=cache["progress"]; t=cache["total"] or 1
    return {"running":cache["running"],"progress":p,"total":t,
            "pct":round(p/t*100),"partial_count":cache["partial_count"],
            "longs":cache["partial_longs"],"shorts":cache["partial_shorts"],"scanned":p}

@app.route("/api/nifty/progress")
def nifty_prog(): return jsonify(prog_payload(_nifty))

@app.route("/api/nifty/results")
def nifty_res():
    return jsonify(_nifty["data"]) if _nifty["data"] else (jsonify({"error":"Scanning..."}),202)

@app.route("/api/mcx/progress")
def mcx_prog(): return jsonify(prog_payload(_mcx))

@app.route("/api/mcx/results")
def mcx_res():
    return jsonify(_mcx["data"]) if _mcx["data"] else (jsonify({"error":"Scanning..."}),202)

@app.route("/api/breadth")
def breadth(): return jsonify(_breadth_cache)

@app.route("/api/status")
def status():
    now=datetime.now(IST)
    return jsonify({
        "nifty":{"running":_nifty["running"],"has_data":_nifty["data"] is not None,"ts":_nifty["ts"],"progress":_nifty["progress"],"total":_nifty["total"]},
        "mcx":  {"running":_mcx["running"],  "has_data":_mcx["data"]  is not None,"ts":_mcx["ts"],  "progress":_mcx["progress"],  "total":_mcx["total"]},
        "server_time":now.strftime("%I:%M %p IST"),
        "next_refresh":f"{15-now.minute%15}min",
        "breadth":_breadth_cache,
    })

# ── Signal tracker API ─────────────────────────────────────────────────
@app.route("/api/signals", methods=["GET"])
def get_signals(): return jsonify(signal_log)

@app.route("/api/signals", methods=["POST"])
def add_signal():
    global signal_log
    data = request.json
    data["id"] = datetime.now(IST).strftime("%Y%m%d%H%M%S")
    data["added"] = datetime.now(IST).strftime("%d %b %Y %H:%M")
    data["result"] = "Open"
    data["holding_days"] = 0
    signal_log.insert(0, data)
    save_signal_log(signal_log)
    return jsonify({"ok":True,"id":data["id"]})

@app.route("/api/signals/<sig_id>", methods=["PUT"])
def update_signal(sig_id):
    global signal_log
    data = request.json
    for s in signal_log:
        if s.get("id") == sig_id:
            s.update(data)
            if s.get("exit_price") and s.get("result") in ("WIN","LOSS"):
                entry=float(s.get("cmp",0)); exit_=float(s.get("exit_price",0))
                if s["direction"]=="LONG": pnl=round((exit_-entry)/entry*100,2)
                else: pnl=round((entry-exit_)/entry*100,2)
                s["pnl_pct"]=pnl
                from_date=datetime.strptime(s["date"],"%d %b %Y") if s.get("date") else datetime.now(IST)
                s["holding_days"]=(datetime.now(IST).replace(tzinfo=None)-from_date.replace(tzinfo=None)).days
    save_signal_log(signal_log)
    return jsonify({"ok":True})

@app.route("/api/signals/<sig_id>", methods=["DELETE"])
def delete_signal(sig_id):
    global signal_log
    signal_log = [s for s in signal_log if s.get("id") != sig_id]
    save_signal_log(signal_log)
    return jsonify({"ok":True})

@app.route("/api/signals/stats", methods=["GET"])
def signal_stats():
    closed = [s for s in signal_log if s.get("result") in ("WIN","LOSS")]
    if not closed:
        return jsonify({"total":len(signal_log),"closed":0,"open":len(signal_log),
                       "win_rate":0,"avg_win":0,"avg_loss":0,"profit_factor":0,"expectancy":0})
    wins   = [s for s in closed if s.get("result")=="WIN"]
    losses = [s for s in closed if s.get("result")=="LOSS"]
    win_pnls  = [float(s.get("pnl_pct",0)) for s in wins]
    loss_pnls = [abs(float(s.get("pnl_pct",0))) for s in losses]
    avg_win   = round(sum(win_pnls)/len(win_pnls),2)   if win_pnls  else 0
    avg_loss  = round(sum(loss_pnls)/len(loss_pnls),2) if loss_pnls else 0
    gross_win = sum(win_pnls)
    gross_loss= sum(loss_pnls)
    pf = round(gross_win/gross_loss,2) if gross_loss>0 else 999
    wr = round(len(wins)/len(closed)*100,1)
    expectancy = round((wr/100)*avg_win - (1-wr/100)*avg_loss, 2)
    avg_hold = round(sum(int(s.get("holding_days",0)) for s in closed)/len(closed),1)
    return jsonify({
        "total":len(signal_log),"closed":len(closed),
        "open":len([s for s in signal_log if s.get("result")=="Open"]),
        "wins":len(wins),"losses":len(losses),
        "win_rate":wr,"avg_win":avg_win,"avg_loss":avg_loss,
        "profit_factor":pf,"expectancy":expectancy,"avg_hold":avg_hold,
        "target_wr":50,"target_pf":1.5,
    })

if __name__=="__main__":
    port=int(os.environ.get("PORT",8080))
    app.run(host="0.0.0.0",port=port,debug=False)
