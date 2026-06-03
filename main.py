"""
SignalDesk V3.0 — Professional Swing Trading Scanner
Nifty 500 + MCX India Commodities
VCP · Darvas · Flag · Sector Strength · RS vs Nifty · OI Signal
Composite Rank: 30% RS · 20% Volume · 20% Trend · 15% Sector · 10% Setup · 5% RR
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

# ── Signal log ──────────────────────────────────────────────────────────────
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

# ── Cache ────────────────────────────────────────────────────────────────────
def empty_cache():
    return {"data": None, "running": False, "progress": 0, "total": 0,
            "partial_longs": [], "partial_shorts": [], "partial_count": 0, "ts": None}

_nifty = empty_cache()
_mcx   = empty_cache()

# ══════════════════════════════════════════════════════════════════════════════
# NSEProvider — yfinance data layer (swap to NSE API when available)
# ══════════════════════════════════════════════════════════════════════════════
class NSEProvider:
    @staticmethod
    def get_stock_history(symbol, period="300d"):
        try:
            return yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
        except: return None

    @staticmethod
    def get_stock_quote(symbol):
        try:
            info = yf.Ticker(symbol).fast_info
            return {"price": info.last_price, "prev_close": info.previous_close}
        except: return None

    @staticmethod
    def get_52w_data(symbol):
        try:
            info = yf.Ticker(symbol).fast_info
            return {"high_52w": info.year_high, "low_52w": info.year_low}
        except: return None

    @staticmethod
    def get_delivery_data(symbol):
        # Requires NSE bhavcopy feed — placeholder
        return None

    @staticmethod
    def get_market_breadth(symbols, n=80):
        sample = symbols[:n]
        advancing = declining = 0
        try:
            data = yf.download(
                " ".join(sample), period="5d", interval="1d",
                auto_adjust=True, group_by="ticker", threads=True, progress=False
            )
            for sym in sample:
                try:
                    closes = data[sym]["Close"].dropna() if len(sample) > 1 else data["Close"].dropna()
                    if sym not in data.columns.get_level_values(0) and len(sample) > 1: continue
                    if len(closes) >= 2:
                        if closes.iloc[-1] > closes.iloc[-2]: advancing += 1
                        else: declining += 1
                except: continue
        except: pass
        total = advancing + declining
        score = round(advancing / total * 100) if total > 0 else 50
        return {"score": score, "advancing": advancing, "declining": declining,
                "total": total, "ts": datetime.now(IST).isoformat()}

    @staticmethod
    def get_nifty500_returns():
        """Returns (r1m, r3m, r6m) for Nifty 500 index."""
        try:
            df = yf.Ticker("^CRSLDX").history(period="200d", interval="1d", auto_adjust=True)
            if df is None or len(df) < 130: return None
            c = df["Close"]
            r1 = (c.iloc[-1]/c.iloc[-21]-1)*100  if len(c) > 21  else 0
            r3 = (c.iloc[-1]/c.iloc[-63]-1)*100  if len(c) > 63  else 0
            r6 = (c.iloc[-1]/c.iloc[-126]-1)*100 if len(c) > 126 else 0
            return (r1, r3, r6)
        except: return None

# ══════════════════════════════════════════════════════════════════════════════
# MCXProvider — yfinance data layer (swap to MCX API when available)
# Removed: GC=F (Gold), SI=F (Silver), CL=F (Crude Oil), NG=F (Natural Gas)
# ══════════════════════════════════════════════════════════════════════════════
class MCXProvider:
    SYMBOLS = {
        "BZ=F":  {"name": "Brent Crude", "unit": "per bbl",  "multiplier": 1,             "base": "$"},
        "HG=F":  {"name": "Copper",      "unit": "per kg",   "multiplier": 2.20462,        "base": "$"},
        "ALI=F": {"name": "Aluminium",   "unit": "per kg",   "multiplier": 0.453592,       "base": "$"},
        "ZN=F":  {"name": "Zinc",        "unit": "per kg",   "multiplier": 0.453592,       "base": "$"},
        "PB=F":  {"name": "Lead",        "unit": "per kg",   "multiplier": 0.453592,       "base": "$"},
        "NI=F":  {"name": "Nickel",      "unit": "per kg",   "multiplier": 0.453592,       "base": "$"},
        "PL=F":  {"name": "Platinum",    "unit": "per 10g",  "multiplier": 0.0321507*10,   "base": "$"},
        "PA=F":  {"name": "Palladium",   "unit": "per 10g",  "multiplier": 0.0321507*10,   "base": "$"},
    }

    @staticmethod
    def get_commodity_history(symbol, period="300d"):
        try:
            return yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
        except: return None

    @staticmethod
    def get_commodity_quote(symbol):
        try:
            info = yf.Ticker(symbol).fast_info
            return {"price": info.last_price, "prev_close": info.previous_close}
        except: return None

    @staticmethod
    def get_open_interest(symbol):
        # Requires MCX live feed — placeholder; OI signal derived from volume proxy
        return None

    @staticmethod
    def get_volume_data(symbol, df):
        try:
            if "Volume" not in df.columns: return 1.0
            vol = df["Volume"]
            avg = vol.rolling(20).mean().iloc[-1]
            return round(vol.iloc[-1] / avg, 2) if avg > 0 else 1.0
        except: return 1.0

    @staticmethod
    def get_contract_data(symbol):
        return MCXProvider.SYMBOLS.get(symbol, {})

# ── Nifty 500 symbols ────────────────────────────────────────────────────────
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
    "SUDARSCHEM.NS","FINOLEX.NS","JYOTICNC.NS","NETWORK18.NS","SPENCERS.NS",
    "KSCL.NS","LTFH.NS","IDFC.NS","MAHABANK.NS","IOB.NS",
]
NIFTY500 = list(dict.fromkeys(NIFTY500))

# ── Sector Map ───────────────────────────────────────────────────────────────
SECTOR_MAP = {
    # DEFENCE
    "HAL.NS":"DEFENCE","BEL.NS":"DEFENCE","MIDHANI.NS":"DEFENCE",
    "BEML.NS":"DEFENCE","MTAR.NS":"DEFENCE","COCHINSHIP.NS":"DEFENCE",
    "GRSE.NS":"DEFENCE","MAZAGON.NS":"DEFENCE","DATAPATTNS.NS":"DEFENCE",
    "BHEL.NS":"DEFENCE",
    # CAPITAL_GOODS
    "LT.NS":"CAPITAL_GOODS","ABB.NS":"CAPITAL_GOODS","SIEMENS.NS":"CAPITAL_GOODS",
    "CGPOWER.NS":"CAPITAL_GOODS","THERMAX.NS":"CAPITAL_GOODS",
    "ELGIEQUIP.NS":"CAPITAL_GOODS","GRINDWELL.NS":"CAPITAL_GOODS",
    "SCHAEFFLER.NS":"CAPITAL_GOODS","TIMKEN.NS":"CAPITAL_GOODS",
    "LAKSHMI.NS":"CAPITAL_GOODS","ELECON.NS":"CAPITAL_GOODS",
    # BANKING
    "HDFCBANK.NS":"BANKING","ICICIBANK.NS":"BANKING","SBIN.NS":"BANKING",
    "KOTAKBANK.NS":"BANKING","AXISBANK.NS":"BANKING","INDUSINDBK.NS":"BANKING",
    "BANKBARODA.NS":"BANKING","CANBK.NS":"BANKING","PNB.NS":"BANKING",
    "FEDERALBNK.NS":"BANKING","IDFCFIRSTB.NS":"BANKING","BANDHANBNK.NS":"BANKING",
    "YESBANK.NS":"BANKING","RBLBANK.NS":"BANKING","DCBBANK.NS":"BANKING",
    "KARURVYSYA.NS":"BANKING","CITYUNIONB.NS":"BANKING","INDIANB.NS":"BANKING",
    "UCOBANK.NS":"BANKING","CENTRALBK.NS":"BANKING","UNIONBANK.NS":"BANKING",
    "BANKINDIA.NS":"BANKING","MAHABANK.NS":"BANKING","IOB.NS":"BANKING",
    # PHARMA
    "SUNPHARMA.NS":"PHARMA","DIVISLAB.NS":"PHARMA","CIPLA.NS":"PHARMA",
    "DRREDDY.NS":"PHARMA","TORNTPHARM.NS":"PHARMA","LUPIN.NS":"PHARMA",
    "AUROPHARMA.NS":"PHARMA","ALKEM.NS":"PHARMA","IPCALAB.NS":"PHARMA",
    "ZYDUSLIFE.NS":"PHARMA","MANKIND.NS":"PHARMA","GLENMARK.NS":"PHARMA",
    "JBCHEPHARM.NS":"PHARMA","AJANTPHARM.NS":"PHARMA","LAURUS.NS":"PHARMA",
    "GRANULES.NS":"PHARMA","NATCOPHARM.NS":"PHARMA","GLAXO.NS":"PHARMA",
    "PFIZER.NS":"PHARMA","ABBOTT.NS":"PHARMA","SANOFI.NS":"PHARMA",
    # IT
    "TCS.NS":"IT","INFY.NS":"IT","HCLTECH.NS":"IT","WIPRO.NS":"IT",
    "TECHM.NS":"IT","LTIMINDTREE.NS":"IT","COFORGE.NS":"IT","MPHASIS.NS":"IT",
    "LTTS.NS":"IT","PERSISTENT.NS":"IT","KPITTECH.NS":"IT","TATAELXSI.NS":"IT",
    "MASTEK.NS":"IT","ZENSAR.NS":"IT","BIRLASOFT.NS":"IT","CYIENT.NS":"IT",
    "INTELLECT.NS":"IT","NEWGEN.NS":"IT","ECLERX.NS":"IT","TANLA.NS":"IT",
    # AUTO
    "MARUTI.NS":"AUTO","TATAMOTORS.NS":"AUTO","M&M.NS":"AUTO",
    "EICHERMOT.NS":"AUTO","HEROMOTOCO.NS":"AUTO","BAJAJ-AUTO.NS":"AUTO",
    "TVSMOTOR.NS":"AUTO","ASHOKLEY.NS":"AUTO","BOSCH.NS":"AUTO",
    "MOTHERSON.NS":"AUTO","ENDURANCE.NS":"AUTO","MRF.NS":"AUTO",
    "APOLLOTYRE.NS":"AUTO","BALKRISIND.NS":"AUTO","CEATLTD.NS":"AUTO",
    "ESCORTS.NS":"AUTO","FORCEMOT.NS":"AUTO","OLECTRA.NS":"AUTO",
    # FMCG
    "HINDUNILVR.NS":"FMCG","ITC.NS":"FMCG","NESTLEIND.NS":"FMCG",
    "BRITANNIA.NS":"FMCG","DABUR.NS":"FMCG","MARICO.NS":"FMCG",
    "COLPAL.NS":"FMCG","GODREJCP.NS":"FMCG","EMAMILTD.NS":"FMCG",
    "TATACONSUM.NS":"FMCG","GILLETTE.NS":"FMCG","PGHH.NS":"FMCG",
    "BIKAJI.NS":"FMCG","RADICO.NS":"FMCG","JYOTHYLAB.NS":"FMCG",
    # METALS
    "JSWSTEEL.NS":"METALS","TATASTEEL.NS":"METALS","HINDALCO.NS":"METALS",
    "VEDL.NS":"METALS","NMDC.NS":"METALS","SAIL.NS":"METALS",
    "HINDZINC.NS":"METALS","NATIONALUM.NS":"METALS","MOIL.NS":"METALS",
    "NALCO.NS":"METALS","APLAPOLLO.NS":"METALS","RATNAMANI.NS":"METALS",
    "JINDALSAW.NS":"METALS",
    # RAILWAYS
    "IRCTC.NS":"RAILWAYS","CONCOR.NS":"RAILWAYS","IRFC.NS":"RAILWAYS",
    "RVNL.NS":"RAILWAYS","IRCON.NS":"RAILWAYS","TITAGARH.NS":"RAILWAYS",
    "TEXRAIL.NS":"RAILWAYS","RAILTEL.NS":"RAILWAYS",
    # ENERGY
    "ONGC.NS":"ENERGY","COALINDIA.NS":"ENERGY","BPCL.NS":"ENERGY",
    "IOC.NS":"ENERGY","TATAPOWER.NS":"ENERGY","POWERGRID.NS":"ENERGY",
    "NTPC.NS":"ENERGY","GAIL.NS":"ENERGY","HINDPETRO.NS":"ENERGY",
    "MRPL.NS":"ENERGY","PETRONET.NS":"ENERGY","GUJGASLTD.NS":"ENERGY",
    "ATGL.NS":"ENERGY","JSWENERGY.NS":"ENERGY","SJVN.NS":"ENERGY",
    "CESC.NS":"ENERGY","TORNTPOWER.NS":"ENERGY","NHPC.NS":"ENERGY",
    "IREDA.NS":"ENERGY","PFC.NS":"ENERGY","RECLTD.NS":"ENERGY",
}

SECTOR_ETFS = {
    "DEFENCE":      ["HAL.NS","BEL.NS","BEML.NS","MAZAGON.NS","GRSE.NS"],
    "CAPITAL_GOODS":["LT.NS","ABB.NS","SIEMENS.NS","CGPOWER.NS","THERMAX.NS"],
    "BANKING":      ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","KOTAKBANK.NS","AXISBANK.NS"],
    "PHARMA":       ["SUNPHARMA.NS","DIVISLAB.NS","CIPLA.NS","DRREDDY.NS","LUPIN.NS"],
    "IT":           ["TCS.NS","INFY.NS","HCLTECH.NS","WIPRO.NS","TECHM.NS"],
    "AUTO":         ["MARUTI.NS","TATAMOTORS.NS","M&M.NS","EICHERMOT.NS","HEROMOTOCO.NS"],
    "FMCG":         ["HINDUNILVR.NS","ITC.NS","NESTLEIND.NS","BRITANNIA.NS","DABUR.NS"],
    "METALS":       ["JSWSTEEL.NS","TATASTEEL.NS","HINDALCO.NS","VEDL.NS","NMDC.NS"],
    "RAILWAYS":     ["IRCTC.NS","IRFC.NS","RVNL.NS","TITAGARH.NS","RAILTEL.NS"],
    "ENERGY":       ["ONGC.NS","NTPC.NS","POWERGRID.NS","TATAPOWER.NS","BPCL.NS"],
}

# ── Sector strength cache ────────────────────────────────────────────────────
_sector_cache = {"data": {}, "ts": None}

def compute_sector_strength():
    """Compute 1M + 3M returns per sector, rank 1-10."""
    raw = {}
    for sector, symbols in SECTOR_ETFS.items():
        r1_list, r3_list = [], []
        for sym in symbols:
            try:
                df = NSEProvider.get_stock_history(sym, period="100d")
                if df is None or len(df) < 63: continue
                c = df["Close"]
                r1 = (c.iloc[-1]/c.iloc[-21]-1)*100 if len(c) > 21 else 0
                r3 = (c.iloc[-1]/c.iloc[-63]-1)*100 if len(c) > 63 else 0
                r1_list.append(r1); r3_list.append(r3)
            except: continue
        if r1_list:
            raw[sector] = 0.5*(sum(r1_list)/len(r1_list)) + 0.5*(sum(r3_list)/len(r3_list) if r3_list else 0)

    sector_scores = {}
    if raw:
        vals = list(raw.values())
        mn, mx = min(vals), max(vals)
        rng = mx - mn if mx != mn else 1
        for sector, val in raw.items():
            sector_scores[sector] = round((val - mn) / rng * 100)
        ranked = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
        sector_ranks = {s: i+1 for i, (s, _) in enumerate(ranked)}
    else:
        sector_scores = {s: 50 for s in SECTOR_ETFS}
        sector_ranks  = {s: i+1 for i, s in enumerate(SECTOR_ETFS)}

    _sector_cache["data"] = {"scores": sector_scores, "ranks": sector_ranks}
    _sector_cache["ts"]   = datetime.now(IST).isoformat()
    return _sector_cache["data"]

def get_sector_info(symbol):
    """Return (sector_name, sector_score 0-100, sector_rank 1-N)."""
    sector = SECTOR_MAP.get(symbol, "OTHER")
    data   = _sector_cache.get("data", {})
    score  = data.get("scores", {}).get(sector, 50)
    rank   = data.get("ranks",  {}).get(sector, len(SECTOR_ETFS)+1)
    return sector, score, rank

# ── Core indicators ──────────────────────────────────────────────────────────
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def sma(s, p): return s.rolling(p).mean()

def atr_calc(df, p=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()

def bb_calc(s, p=20, std=2):
    m = s.rolling(p).mean(); sd = s.rolling(p).std()
    return m+std*sd, m, m-std*sd

# ── Nifty 500 returns cache ──────────────────────────────────────────────────
_nifty500_ret_cache = {"data": None, "ts": None}

def get_nifty500_returns():
    now = datetime.now(IST)
    cached_ts = _nifty500_ret_cache["ts"]
    if cached_ts and (now - datetime.fromisoformat(cached_ts)).seconds < 3600:
        return _nifty500_ret_cache["data"]
    ret = NSEProvider.get_nifty500_returns()
    _nifty500_ret_cache.update({"data": ret, "ts": now.isoformat()})
    return ret

# ── Relative Strength: 40% stock · 40% vs Nifty500 · 20% vs Sector ──────────
def relative_strength(df, symbol=None):
    try:
        c = df["Close"]
        if len(c) < 130: return 50, 0.0
        r1 = (c.iloc[-1]/c.iloc[-21]-1)*100  if len(c) > 21  else 0
        r3 = (c.iloc[-1]/c.iloc[-63]-1)*100  if len(c) > 63  else 0
        r6 = (c.iloc[-1]/c.iloc[-126]-1)*100 if len(c) > 126 else 0
        stock_comp = 0.40*r1 + 0.35*r3 + 0.25*r6

        # vs Nifty 500
        nret = get_nifty500_returns()
        if nret:
            n1, n3, n6 = nret
            vs_nifty_comp = (0.40*r1 + 0.35*r3 + 0.25*r6) - (0.40*n1 + 0.35*n3 + 0.25*n6)
        else:
            vs_nifty_comp = 0

        # vs Sector (normalised score difference)
        sector_adj = 0
        if symbol:
            sec_data = _sector_cache.get("data", {})
            sec_score = sec_data.get("scores", {}).get(SECTOR_MAP.get(symbol, ""), 50)
            sector_adj = (sec_score - 50) * 0.15

        # RS = 40% absolute rank + 40% vs nifty + 20% vs sector
        stock_norm  = max(0, min(100, stock_comp * 2 + 50))
        nifty_norm  = max(0, min(100, vs_nifty_comp * 3 + 50))
        sector_norm = max(0, min(100, sector_adj + 50))

        score = round(0.40*stock_norm + 0.40*nifty_norm + 0.20*sector_norm)
        return max(0, min(100, score)), round(r1, 1)
    except: return 50, 0.0

# ── 52-Week High Proximity ───────────────────────────────────────────────────
def high_proximity(df):
    try:
        if len(df) < 50: return 50, 0.0
        c       = df["Close"].iloc[-1]
        high_52 = df["High"].tail(252).max() if len(df) >= 252 else df["High"].max()
        dist    = round((high_52 - c) / high_52 * 100, 1)
        if dist <= 0:   score = 100
        elif dist <= 5: score = 100
        elif dist <= 10:score = 80
        elif dist <= 15:score = 65
        elif dist <= 25:score = 50
        elif dist <= 40:score = 30
        else:           score = 10
        return score, dist
    except: return 50, 0.0

# ── Position Sizing ──────────────────────────────────────────────────────────
def position_size(entry, stoploss, capital=100000):
    try:
        risk_amount   = capital * 0.01
        risk_per_share= abs(entry - stoploss)
        if risk_per_share <= 0: return 0, int(risk_amount)
        qty = int(risk_amount / risk_per_share)
        return qty, int(risk_amount)
    except: return 0, 1000

# ── Delivery Score ───────────────────────────────────────────────────────────
def delivery_score(symbol):
    data = NSEProvider.get_delivery_data(symbol)
    if data is None: return 50, "N/A"
    pct = data.get("delivery_pct", 50)
    if pct >= 70: return 90, f"{pct:.0f}%"
    if pct >= 60: return 70, f"{pct:.0f}%"
    if pct >= 50: return 50, f"{pct:.0f}%"
    return 25, f"{pct:.0f}%"

# ══════════════════════════════════════════════════════════════════════════════
# SETUP DETECTORS
# ══════════════════════════════════════════════════════════════════════════════

def detect_vcp(df):
    """Volatility Contraction Pattern — shrinking pullbacks, volume contraction, above EMAs."""
    try:
        if len(df) < 60: return {"score": 0, "setup": None}
        c  = df["Close"]; h = df["High"]; l = df["Low"]
        e20 = ema(c, 20); e50 = ema(c, 50)
        cur = c.iloc[-1]

        if cur < e20.iloc[-1] or cur < e50.iloc[-1]:
            return {"score": 0, "setup": None}

        # Find pullbacks in last 60 days (scan every 5 bars)
        wc = c.tail(60); wh = h.tail(60); wl = l.tail(60)
        n = len(wc); pullbacks = []
        for i in range(5, n-5, 5):
            lh = wh.iloc[max(0, i-5):i+1].max()
            ll = wl.iloc[i:min(n, i+10)].min()
            pb = (lh - ll) / lh * 100
            if pb > 0: pullbacks.append(pb)

        if len(pullbacks) < 4: return {"score": 0, "setup": None}
        last4 = pullbacks[-4:]
        contracting = all(last4[i] > last4[i+1] for i in range(3))

        vol_contract = True
        if "Volume" in df.columns:
            vol = df["Volume"]
            vol_contract = vol.tail(10).mean() < vol.tail(20).mean() * 0.9

        score = 0
        if contracting:       score += 50
        if vol_contract:      score += 25
        if cur > e20.iloc[-1]:score += 15
        if cur > e50.iloc[-1]:score += 10

        return {"score": min(100, score), "setup": "VCP"} if score >= 60 else {"score": 0, "setup": None}
    except: return {"score": 0, "setup": None}


def detect_darvas(df):
    """Darvas Box — 20-day consolidation, breakout on 1.5× volume."""
    try:
        if len(df) < 30: return {"score": 0, "setup": None}
        h = df["High"]; l = df["Low"]; c = df["Close"]
        high_20 = h.tail(21).iloc[:-1].max()

        # Consolidation: no close above high_20 for at least 15 of last 20 days
        days_below   = (c.tail(21).iloc[:-1] <= high_20).sum()
        consolidating= days_below >= 15
        breakout     = c.iloc[-1] > high_20

        vol_surge = True
        if "Volume" in df.columns:
            vol = df["Volume"]
            vol_surge = vol.iloc[-1] > 1.5 * vol.tail(20).mean()

        if breakout and consolidating and vol_surge: return {"score": 95, "setup": "DARVAS"}
        if breakout and consolidating:               return {"score": 80, "setup": "DARVAS"}
        return {"score": 0, "setup": None}
    except: return {"score": 0, "setup": None}


def detect_flag(df):
    """Bull Flag — >10% pole in 10 days, <50% pullback, volume declines, then breakout."""
    try:
        if len(df) < 25: return {"score": 0, "setup": None}
        c = df["Close"]
        pole_start = c.iloc[-21]; pole_end = c.iloc[-11]
        if pole_start <= 0: return {"score": 0, "setup": None}
        pole_gain = (pole_end - pole_start) / pole_start * 100
        if pole_gain < 10: return {"score": 0, "setup": None}

        flag_high = c.iloc[-11]
        pullback  = (flag_high - c.tail(11).min()) / flag_high * 100
        if pullback > pole_gain * 0.5: return {"score": 0, "setup": None}

        vol_decline = True
        if "Volume" in df.columns:
            vol = df["Volume"]
            vol_decline = vol.tail(10).mean() < vol.iloc[-21:-11].mean()

        breakout = c.iloc[-1] > flag_high

        score = 0
        if pole_gain >= 10:  score += 30
        if pole_gain >= 20:  score += 15
        if pullback  <= 30:  score += 25
        if vol_decline:      score += 20
        if breakout:         score += 10

        return {"score": min(100, score), "setup": "FLAG"} if score >= 50 else {"score": 0, "setup": None}
    except: return {"score": 0, "setup": None}

# ── OI Signal ────────────────────────────────────────────────────────────────
def oi_signal(df):
    """
    Price+Volume proxy for OI signal:
    Price Up + OI Up    → LONG_BUILDUP
    Price Down + OI Up  → SHORT_BUILDUP
    Price Up + OI Down  → SHORT_COVERING
    Price Down + OI Down→ LONG_UNWINDING
    """
    try:
        c = df["Close"]
        price_up = c.iloc[-1] > c.iloc[-2]
        oi_change = 0.0
        oi_up = True
        if "Volume" in df.columns:
            vol      = df["Volume"]
            avg_vol  = vol.rolling(10).mean().iloc[-1]
            oi_up    = vol.iloc[-1] > avg_vol
            oi_change= round((vol.iloc[-1] / avg_vol - 1) * 100, 1) if avg_vol > 0 else 0.0

        if     price_up and     oi_up: signal = "LONG_BUILDUP"
        elif not price_up and   oi_up: signal = "SHORT_BUILDUP"
        elif   price_up and not oi_up: signal = "SHORT_COVERING"
        else:                          signal = "LONG_UNWINDING"
        return signal, oi_change
    except: return "LONG_BUILDUP", 0.0

# ── Commodity Structure ──────────────────────────────────────────────────────
def commodity_structure(df):
    try:
        c = df["Close"]
        if len(c) < 25: return "NEUTRAL", 40
        high_20 = df["High"].tail(21).iloc[:-1].max()
        low_20  = df["Low"].tail(21).iloc[:-1].min()
        cur     = c.iloc[-1]
        e20     = ema(c, 20).iloc[-1]
        e50     = ema(c, 50).iloc[-1] if len(c) >= 50 else e20

        if cur > high_20:                             return "BREAKOUT",      90
        if cur < low_20:                              return "BREAKDOWN",     90
        if e20 > e50 and e50 < cur < e20:             return "TREND_PULLBACK",70
        return "NEUTRAL", 40
    except: return "NEUTRAL", 40

# ══════════════════════════════════════════════════════════════════════════════
# STRATEGIES
# ══════════════════════════════════════════════════════════════════════════════

def strat_ema(df):
    n = 200 if len(df) >= 215 else 50
    if len(df) < n+15: return 0, 0, "insufficient"
    c, o  = df["Close"].iloc[-1], df["Open"].iloc[-1]
    e20   = ema(df["Close"], 20).iloc[-1]
    e200  = ema(df["Close"], n).iloc[-1]
    a     = atr_calc(df).iloc[-1]
    b     = (int(c>e200)+int(e20>e200)+int(abs(c-e20)<0.5*a)+int(c>o))*25
    s     = (int(c<e200)+int(e20<e200)+int(abs(c-e20)<0.5*a)+int(c<o))*25
    return b, s, "uptrend" if c > e200 else "downtrend"

def strat_bb(df):
    if len(df) < 55: return 0, 0, "insufficient"
    c, o  = df["Close"].iloc[-1], df["Open"].iloc[-1]
    up, mid, lo = bb_calc(df["Close"])
    bw    = (up-lo)/mid; wn = bw.iloc[-1]
    wmin  = bw.rolling(50).min().iloc[-1]; wmax = bw.rolling(50).max().iloc[-1]
    wr    = wmax-wmin if wmax != wmin else 1
    sq    = int(wn < wmin+0.3*wr)
    vol   = df.get("Volume", pd.Series([1]*len(df), index=df.index))
    av    = vol.rolling(20).mean().iloc[-1]
    vp    = min(int((vol.iloc[-1]/av if av>0 else 1)*12.5), 25)
    b     = min((sq*25)+int(c>up.iloc[-1])*25+vp+int(c>o)*25, 100)
    s     = min((sq*25)+int(c<lo.iloc[-1])*25+vp+int(c<o)*25, 100)
    return b, s, "squeeze" if sq else "expansion" if wn>wmin+0.7*wr else "normal"

def strat_fvg(df):
    if len(df) < 50: return 0, 0, "no data"
    c, o  = df["Close"].iloc[-1], df["Open"].iloc[-1]
    hi, lo, cl = df["High"], df["Low"], df["Close"]
    n     = 200 if len(df) >= 215 else 50
    e200  = ema(cl, n).iloc[-1]; a = atr_calc(df).iloc[-1]; htf = int(c>e200)
    buy_sc= sell_sc = 0
    for i in range(min(50, len(df)-3), 2, -1):
        idx = -i
        if lo.iloc[idx] > hi.iloc[idx-2]:
            gs = lo.iloc[idx]-hi.iloc[idx-2]
            if gs > 0.08*a:
                sub = cl.iloc[idx+1:]
                if not any((sub>=hi.iloc[idx-2])&(sub<=lo.iloc[idx])):
                    prox = abs(c-lo.iloc[idx])/a
                    pp   = max(0, int(35*(1-prox/0.25))) if prox < 0.25 else 0
                    buy_sc = pp+(25 if i<=15 else 0)+(25 if htf else 0)+(15 if c>o else 0); break
        if hi.iloc[idx] < lo.iloc[idx-2]:
            gs = lo.iloc[idx-2]-hi.iloc[idx]
            if gs > 0.08*a:
                sub = cl.iloc[idx+1:]
                if not any((sub>=hi.iloc[idx])&(sub<=lo.iloc[idx-2])):
                    prox = abs(c-hi.iloc[idx])/a
                    pp   = max(0, int(35*(1-prox/0.25))) if prox < 0.25 else 0
                    sell_sc = pp+(25 if i<=15 else 0)+(25 if not htf else 0)+(15 if c<o else 0); break
    return min(buy_sc, 100), min(sell_sc, 100), "fvg"

# ── New Composite Ranking: 30/20/20/15/10/5 ──────────────────────────────────
def composite_rank_v3(rs_score, vol_ratio, trend_score, sector_score, setup_score, rr):
    vol_score = min(100, round(vol_ratio / 3 * 100))
    rr_score  = min(100, round(rr / 3 * 100))
    return round(
        0.30 * rs_score     +
        0.20 * vol_score    +
        0.20 * trend_score  +
        0.15 * sector_score +
        0.10 * setup_score  +
        0.05 * rr_score
    )

# ── Commodity Ranking: 30/25/20/15/10 ────────────────────────────────────────
def commodity_rank_score(trend_score, oi_score, vol_ratio, structure_score, rr):
    vol_score = min(100, round(vol_ratio / 3 * 100))
    rr_score  = min(100, round(rr / 3 * 100))
    return round(
        0.30 * trend_score     +
        0.25 * oi_score        +
        0.20 * vol_score       +
        0.15 * structure_score +
        0.10 * rr_score
    )

# ── Market breadth ───────────────────────────────────────────────────────────
_breadth_cache = {"score": 50, "ts": None, "advancing": 0, "declining": 0, "total": 0}

def compute_breadth(sample_symbols, n=80):
    result = NSEProvider.get_market_breadth(sample_symbols, n)
    _breadth_cache.update(result)
    return result["score"]

# ── Swing filter ─────────────────────────────────────────────────────────────
def swing_filter(df, direction):
    try:
        c     = df["Close"].iloc[-1]; a = atr_calc(df).iloc[-1]
        e20   = ema(df["Close"], 20).iloc[-1]
        n     = 200 if len(df) >= 215 else 50
        e200  = ema(df["Close"], n).iloc[-1]
        vol   = df.get("Volume", pd.Series([1]*len(df), index=df.index))
        av    = vol.rolling(20).mean().iloc[-1]
        vr    = vol.iloc[-1]/av if av > 0 else 1
        atr_tp= (3*a/c)*100; atr_sl = (1.5*a/c)*100
        if direction == "LONG":
            if c > e200 and abs(c-e20) < a and vr > 1.2:
                setup="Trend Pullback"; tp=max(5, min(15, atr_tp*1.2))
            elif c > df["High"].tail(20).iloc[:-1].max()*0.99:
                setup="Breakout";       tp=max(6, min(15, atr_tp*1.5))
            else:
                setup="Swing Long";     tp=max(5, min(12, atr_tp))
        else:
            if c < e200 and abs(c-e20) < a:
                setup="Trend Breakdown";tp=max(5, min(15, atr_tp*1.2))
            else:
                setup="Swing Short";    tp=max(5, min(12, atr_tp))
        return tp >= 4 and vr >= 0.5, round(tp, 1), round(atr_sl, 1), setup
    except: return True, 7.0, 3.5, "Swing"

def estimate_holding(df, target_pct):
    try:
        daily = (df["High"]-df["Low"]).tail(20).mean()
        c     = df["Close"].iloc[-1]; move = c*(target_pct/100)
        days  = max(3, min(30, round(move/daily*0.6)))
        if days <= 5:  return f"{days}d", "Very short swing"
        if days <= 10: return f"{days}d", "Short swing"
        if days <= 20: return f"{days}d", "Medium swing"
        return f"{days}d", "Positional"
    except: return "7-15d", "Swing"

# ══════════════════════════════════════════════════════════════════════════════
# SCAN ONE STOCK
# ══════════════════════════════════════════════════════════════════════════════
def scan_one(symbol, currency="₹", breadth=50):
    try:
        df = NSEProvider.get_stock_history(symbol)
        if df is None or len(df) < 55: return None
        df = df.dropna(subset=["Close"])

        # Core strategies
        eb,  es,  er  = strat_ema(df)
        bb_b,bb_s,bb_r= strat_bb(df)
        fb,  fs,  fr  = strat_fvg(df)

        # Setups (momentum-only)
        vcp    = detect_vcp(df)
        darvas = detect_darvas(df)
        flag   = detect_flag(df)
        best_setup = max(vcp, darvas, flag, key=lambda x: x["score"])

        # Direction — pure composite rank, no min_agree threshold
        buys  = [eb, bb_b, fb]; sells = [es, bb_s, fs]
        avg_b = sum(buys)/3; avg_s = sum(sells)/3
        setup_boost = best_setup["score"] * 0.20  # setup adds up to 20pts to long score
        avg_b_adj   = avg_b + setup_boost

        if avg_b_adj >= 45 and avg_b_adj > avg_s + 10:
            direction = "LONG";  score = round(avg_b_adj)
        elif avg_s >= 45 and avg_s > avg_b + 10:
            direction = "SHORT"; score = round(avg_s)
        else: return None

        passes, tpct, slpct, base_setup = swing_filter(df, direction)
        if not passes: return None

        c   = float(df["Close"].iloc[-1])
        pc  = float(df["Close"].iloc[-2]) if len(df) > 1 else c
        a   = float(atr_calc(df).iloc[-1])
        chg = round((c-pc)/pc*100, 2)
        sl  = round(c*(1-slpct/100), 2) if direction=="LONG" else round(c*(1+slpct/100), 2)
        tp  = round(c*(1+tpct/100), 2) if direction=="LONG" else round(c*(1-tpct/100), 2)
        hold, hold_lbl = estimate_holding(df, tpct)

        vol     = int(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
        avg_vol = int(df["Volume"].rolling(20).mean().iloc[-1]) if "Volume" in df.columns else 1
        vr      = round(vol/avg_vol, 1) if avg_vol > 0 else 0

        risk     = abs(c - sl); reward = abs(tp - c)
        rr_ratio = round(reward/risk, 1) if risk > 0 else 0

        # RS (40% stock · 40% vs Nifty · 20% vs sector)
        rs_score, rs_rank_val = relative_strength(df, symbol)

        # Sector
        sector_name, sector_score_val, sector_rank_val = get_sector_info(symbol)

        # 52W high proximity
        prox_score, dist_52w = high_proximity(df)

        # Delivery
        del_score, del_pct = delivery_score(symbol)

        # Trend quality
        n     = 200 if len(df) >= 215 else 50
        e20_v = ema(df["Close"], 20).iloc[-1]
        e50_v = ema(df["Close"], 50).iloc[-1] if len(df) >= 50 else e20_v
        e200_v= ema(df["Close"], n).iloc[-1]
        if direction == "LONG":
            trend_score = int(c>e200_v)*40 + int(e20_v>e50_v)*30 + int(e50_v>e200_v)*30
        else:
            trend_score = int(c<e200_v)*40 + int(e20_v<e50_v)*30 + int(e50_v<e200_v)*30

        # Setup quality
        if direction == "LONG":
            setup_quality = best_setup["score"]
            setup_type    = best_setup["setup"] or base_setup
        else:
            setup_quality = 30
            setup_type    = base_setup

        # Composite rank V3 (30/20/20/15/10/5)
        comp = composite_rank_v3(rs_score, vr, trend_score, sector_score_val, setup_quality, rr_ratio)

        # Position sizing (₹1 lakh capital, 1% risk)
        qty, risk_amt = position_size(c, sl)

        sym = symbol.replace(".NS", "").replace(".BO", "")
        return {
            "symbol":       sym,
            "ticker":       symbol,
            "direction":    direction,
            "score":        score,
            "comp_rank":    comp,
            "rs_score":     rs_score,
            "rs_rank":      rs_rank_val,
            "sector":       sector_name,
            "sector_score": sector_score_val,
            "sector_rank":  sector_rank_val,
            "setup":        setup_type,
            "setup_score":  setup_quality,
            "prox_score":   prox_score,
            "dist_52w":     dist_52w,
            "delivery_pct": del_pct,
            "cmp":          round(c, 2),
            "chg":          chg,
            "sl":           sl,
            "target":       tp,
            "sl_pct":       slpct,
            "target_pct":   tpct,
            "hold":         hold,
            "hold_label":   hold_lbl,
            "rr":           rr_ratio,
            "atr":          round(a, 2),
            "vol_ratio":    vr,
            "currency":     currency,
            "position_qty": qty,
            "risk_amount":  risk_amt,
            "date":         datetime.now(IST).strftime("%d %b %Y"),
            "time":         datetime.now(IST).strftime("%H:%M IST"),
            "strategies": [
                {"name": "EMA Trend",  "buy": eb,               "sell": es,   "regime": er},
                {"name": "BB Squeeze", "buy": bb_b,             "sell": bb_s, "regime": bb_r},
                {"name": "FVG",        "buy": fb,               "sell": fs,   "regime": fr},
                {"name": "VCP",        "buy": vcp["score"],     "sell": 0,    "regime": vcp["setup"]    or "—"},
                {"name": "DARVAS",     "buy": darvas["score"],  "sell": 0,    "regime": darvas["setup"] or "—"},
                {"name": "FLAG",       "buy": flag["score"],    "sell": 0,    "regime": flag["setup"]   or "—"},
            ]
        }
    except Exception: return None

# ══════════════════════════════════════════════════════════════════════════════
# SCAN ONE COMMODITY
# ══════════════════════════════════════════════════════════════════════════════
def scan_commodity(symbol, meta):
    try:
        df = MCXProvider.get_commodity_history(symbol)
        if df is None or len(df) < 55: return None
        df = df.dropna(subset=["Close"])

        c   = float(df["Close"].iloc[-1])
        pc  = float(df["Close"].iloc[-2]) if len(df) > 1 else c
        a   = float(atr_calc(df).iloc[-1])
        chg = round((c-pc)/pc*100, 2)

        n     = 200 if len(df) >= 215 else 50
        e20   = ema(df["Close"], 20).iloc[-1]
        e200  = ema(df["Close"], n).iloc[-1]

        # Trend
        if c > e200 and e20 > e200:
            direction = "LONG";  trend_s = 80
        elif c < e200 and e20 < e200:
            direction = "SHORT"; trend_s = 80
        else:
            direction = "LONG" if c > e200 else "SHORT"; trend_s = 45

        # Volume
        vr    = MCXProvider.get_volume_data(symbol, df)

        # OI Signal
        oi_sig, oi_chg = oi_signal(df)
        if direction == "LONG":
            oi_s = {"LONG_BUILDUP":90,"SHORT_COVERING":70,"LONG_UNWINDING":30,"SHORT_BUILDUP":20}[oi_sig]
        else:
            oi_s = {"SHORT_BUILDUP":90,"LONG_UNWINDING":70,"SHORT_COVERING":30,"LONG_BUILDUP":20}[oi_sig]

        # Structure
        struct_name, struct_s = commodity_structure(df)

        # Levels
        sl_pct = round((1.5*a/c)*100, 1); tp_pct = round((3*a/c)*100, 1)
        sl  = round(c*(1-sl_pct/100), 2) if direction=="LONG" else round(c*(1+sl_pct/100), 2)
        tp  = round(c*(1+tp_pct/100), 2) if direction=="LONG" else round(c*(1-tp_pct/100), 2)
        risk= abs(c-sl); reward=abs(tp-c)
        rr_ratio = round(reward/risk, 1) if risk > 0 else 0

        comp = commodity_rank_score(trend_s, oi_s, vr, struct_s, rr_ratio)
        hold, hold_lbl = estimate_holding(df, tp_pct)

        return {
            "symbol":     meta["name"],
            "ticker":     symbol,
            "direction":  direction,
            "score":      comp,
            "comp_rank":  comp,
            "cmp":        round(c, 2),
            "chg":        chg,
            "sl":         sl,
            "target":     tp,
            "sl_pct":     sl_pct,
            "target_pct": tp_pct,
            "hold":       hold,
            "hold_label": hold_lbl,
            "rr":         rr_ratio,
            "atr":        round(a, 2),
            "vol_ratio":  vr,
            "vol_change": round((vr-1)*100, 1),
            "oi_signal":  oi_sig,
            "oi_change":  oi_chg,
            "structure":  struct_name,
            "currency":   "$",
            "date":       datetime.now(IST).strftime("%d %b %Y"),
            "time":       datetime.now(IST).strftime("%H:%M IST"),
        }
    except Exception: return None

# ── Scanner runners ──────────────────────────────────────────────────────────
def run_nifty_scan():
    cache   = _nifty
    breadth = _breadth_cache["score"]
    threading.Thread(target=lambda: compute_breadth(NIFTY500), daemon=True).start()

    cache.update({"running": True, "progress": 0, "total": len(NIFTY500),
                  "partial_longs": [], "partial_shorts": [], "partial_count": 0})
    results = []
    for i, sym in enumerate(NIFTY500):
        r = scan_one(sym, currency="₹", breadth=breadth)
        if r:
            results.append(r)
            longs  = sorted([x for x in results if x["direction"]=="LONG"],
                            key=lambda x: x["comp_rank"], reverse=True)[:25]
            shorts = sorted([x for x in results if x["direction"]=="SHORT"],
                            key=lambda x: x["comp_rank"], reverse=True)[:25]
            cache["partial_longs"]  = longs
            cache["partial_shorts"] = shorts
            cache["partial_count"]  = len(results)
        cache["progress"] = i + 1

    now    = datetime.now(IST)
    longs  = sorted([r for r in results if r["direction"]=="LONG"],
                    key=lambda x: x["comp_rank"], reverse=True)[:25]
    shorts = sorted([r for r in results if r["direction"]=="SHORT"],
                    key=lambda x: x["comp_rank"], reverse=True)[:25]
    cache.update({
        "running": False, "ts": now.isoformat(),
        "data": {
            "date":          now.strftime("%d %b %Y"),
            "time":          now.strftime("%I:%M %p IST"),
            "scanned":       len(NIFTY500),
            "total_signals": len(results),
            "longs":         longs,
            "shorts":        shorts,
            "breadth":       _breadth_cache,
            "sector_data":   _sector_cache.get("data", {}),
        }
    })

def run_mcx_scan():
    cache = _mcx
    items = list(MCXProvider.SYMBOLS.items())
    cache.update({"running": True, "progress": 0, "total": len(items),
                  "partial_longs": [], "partial_shorts": [], "partial_count": 0})
    results = []
    for i, (sym, meta) in enumerate(items):
        r = scan_commodity(sym, meta)
        if r:
            results.append(r)
            longs  = sorted([x for x in results if x["direction"]=="LONG"],
                            key=lambda x: x["comp_rank"], reverse=True)[:10]
            shorts = sorted([x for x in results if x["direction"]=="SHORT"],
                            key=lambda x: x["comp_rank"], reverse=True)[:10]
            cache["partial_longs"]  = longs
            cache["partial_shorts"] = shorts
            cache["partial_count"]  = len(results)
        cache["progress"] = i + 1

    now    = datetime.now(IST)
    longs  = sorted([r for r in results if r["direction"]=="LONG"],
                    key=lambda x: x["comp_rank"], reverse=True)[:10]
    shorts = sorted([r for r in results if r["direction"]=="SHORT"],
                    key=lambda x: x["comp_rank"], reverse=True)[:10]
    cache.update({
        "running": False, "ts": now.isoformat(),
        "data": {
            "date":          now.strftime("%d %b %Y"),
            "time":          now.strftime("%I:%M %p IST"),
            "scanned":       len(items),
            "total_signals": len(results),
            "longs":         longs,
            "shorts":        shorts,
        }
    })

def scan_nifty(): run_nifty_scan()
def scan_mcx():   run_mcx_scan()

# ── Auto scheduler ───────────────────────────────────────────────────────────
def scheduler():
    threading.Thread(target=compute_sector_strength, daemon=True).start()
    time.sleep(5)
    threading.Thread(target=scan_nifty, daemon=True).start()
    time.sleep(15)
    threading.Thread(target=scan_mcx, daemon=True).start()
    while True:
        time.sleep(60)
        now       = datetime.now(IST)
        is_wd     = now.weekday() < 5
        at_15     = now.minute % 15 == 0 and now.second < 90
        nifty_hrs = is_wd and 9 <= now.hour < 16
        mcx_hrs   = is_wd and (9 <= now.hour < 16 or 18 <= now.hour < 24)
        if at_15:
            if nifty_hrs and not _nifty["running"]:
                threading.Thread(target=scan_nifty, daemon=True).start()
            if mcx_hrs and not _mcx["running"]:
                threading.Thread(target=scan_mcx, daemon=True).start()
        if now.minute == 0 and now.second < 90:
            threading.Thread(target=compute_sector_strength, daemon=True).start()

threading.Thread(target=scheduler, daemon=True).start()

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return send_from_directory("static", "index.html")

def prog_payload(cache):
    p = cache["progress"]; t = cache["total"] or 1
    return {"running": cache["running"], "progress": p, "total": t,
            "pct": round(p/t*100), "partial_count": cache["partial_count"],
            "longs": cache["partial_longs"], "shorts": cache["partial_shorts"], "scanned": p}

@app.route("/api/nifty/progress")
def nifty_prog(): return jsonify(prog_payload(_nifty))

@app.route("/api/nifty/results")
def nifty_res():
    return jsonify(_nifty["data"]) if _nifty["data"] else (jsonify({"error": "Scanning..."}), 202)

@app.route("/api/mcx/progress")
def mcx_prog(): return jsonify(prog_payload(_mcx))

@app.route("/api/mcx/results")
def mcx_res():
    return jsonify(_mcx["data"]) if _mcx["data"] else (jsonify({"error": "Scanning..."}), 202)

@app.route("/api/breadth")
def breadth(): return jsonify(_breadth_cache)

@app.route("/api/sectors")
def sectors(): return jsonify(_sector_cache.get("data", {}))

@app.route("/api/status")
def status():
    now = datetime.now(IST)
    return jsonify({
        "nifty":       {"running": _nifty["running"], "has_data": _nifty["data"] is not None,
                        "ts": _nifty["ts"], "progress": _nifty["progress"], "total": _nifty["total"]},
        "mcx":         {"running": _mcx["running"],   "has_data": _mcx["data"]  is not None,
                        "ts": _mcx["ts"],   "progress": _mcx["progress"],   "total": _mcx["total"]},
        "server_time": now.strftime("%I:%M %p IST"),
        "next_refresh":f"{15-now.minute%15}min",
        "breadth":     _breadth_cache,
        "sector_data": _sector_cache.get("data", {}),
    })

# ── Signal tracker ───────────────────────────────────────────────────────────
@app.route("/api/signals", methods=["GET"])
def get_signals(): return jsonify(signal_log)

@app.route("/api/signals", methods=["POST"])
def add_signal():
    global signal_log
    data = request.json
    data["id"]           = datetime.now(IST).strftime("%Y%m%d%H%M%S")
    data["added"]        = datetime.now(IST).strftime("%d %b %Y %H:%M")
    data["result"]       = "Open"
    data["holding_days"] = 0
    signal_log.insert(0, data)
    save_signal_log(signal_log)
    return jsonify({"ok": True, "id": data["id"]})

@app.route("/api/signals/<sig_id>", methods=["PUT"])
def update_signal(sig_id):
    global signal_log
    data = request.json
    for s in signal_log:
        if s.get("id") == sig_id:
            s.update(data)
            if s.get("exit_price") and s.get("result") in ("WIN", "LOSS"):
                entry = float(s.get("cmp", 0)); exit_ = float(s.get("exit_price", 0))
                pnl   = round((exit_-entry)/entry*100, 2) if s["direction"]=="LONG" \
                        else round((entry-exit_)/entry*100, 2)
                s["pnl_pct"] = pnl
                fd = datetime.strptime(s["date"], "%d %b %Y") if s.get("date") else datetime.now(IST)
                s["holding_days"] = (datetime.now(IST).replace(tzinfo=None)-fd.replace(tzinfo=None)).days
    save_signal_log(signal_log)
    return jsonify({"ok": True})

@app.route("/api/signals/<sig_id>", methods=["DELETE"])
def delete_signal(sig_id):
    global signal_log
    signal_log = [s for s in signal_log if s.get("id") != sig_id]
    save_signal_log(signal_log)
    return jsonify({"ok": True})

@app.route("/api/signals/stats", methods=["GET"])
def signal_stats():
    closed = [s for s in signal_log if s.get("result") in ("WIN","LOSS")]
    if not closed:
        return jsonify({"total":len(signal_log),"closed":0,"open":len(signal_log),
                        "win_rate":0,"avg_win":0,"avg_loss":0,"profit_factor":0,"expectancy":0})
    wins   = [s for s in closed if s.get("result")=="WIN"]
    losses = [s for s in closed if s.get("result")=="LOSS"]
    wp = [float(s.get("pnl_pct",0)) for s in wins]
    lp = [abs(float(s.get("pnl_pct",0))) for s in losses]
    aw = round(sum(wp)/len(wp),2) if wp else 0
    al = round(sum(lp)/len(lp),2) if lp else 0
    pf = round(sum(wp)/sum(lp),2) if sum(lp) > 0 else 999
    wr = round(len(wins)/len(closed)*100,1)
    ex = round((wr/100)*aw - (1-wr/100)*al, 2)
    ah = round(sum(int(s.get("holding_days",0)) for s in closed)/len(closed),1)
    return jsonify({
        "total":len(signal_log),"closed":len(closed),
        "open":len([s for s in signal_log if s.get("result")=="Open"]),
        "wins":len(wins),"losses":len(losses),
        "win_rate":wr,"avg_win":aw,"avg_loss":al,
        "profit_factor":pf,"expectancy":ex,"avg_hold":ah,
        "target_wr":50,"target_pf":1.5,
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
