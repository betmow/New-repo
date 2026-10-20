"""Downloads BTC history for the research project and writes CSVs into ./data.
Sources: Bitstamp (BTCUSD daily 2011->2017), Binance data portal (spot/perp klines, funding, open-interest metrics), BitMEX (XBTUSD funding from 2016).
Run:  python fetch_data.py        Safe to re-run: existing monthly/daily files are cached in ./raw."""
import io, os, sys, time, zipfile, datetime as dt
import requests, pandas as pd

BV = "https://data.binance.vision/data"
os.makedirs("data", exist_ok=True); os.makedirs("raw", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "btc-research/1.0"

def get(url, tries=4, **kw):
    for i in range(tries):
        try:
            r = S.get(url, timeout=60, **kw)
            if r.status_code == 404: return None
            r.raise_for_status(); return r
        except Exception as e:
            if i == tries - 1: print("FAIL", url, e); return None
            time.sleep(2 * (i + 1))

def zip_csv(url, cache):
    p = os.path.join("raw", cache)
    if os.path.exists(p): return open(p, "rb").read()
    r = get(url)
    if r is None: return None
    z = zipfile.ZipFile(io.BytesIO(r.content)); b = z.read(z.namelist()[0])
    if not url.endswith(dt.date.today().strftime("%Y-%m-%d.zip")) and not url.endswith(dt.date.today().strftime("%Y-%m.zip")):
        open(p, "wb").write(b)
    return b

def months(a, b):
    y, m = a
    while (y, m) <= b:
        yield y, m; m += 1
        if m == 13: y, m = y + 1, 1

def days(a, b):
    d = a
    while d <= b: yield d; d += dt.timedelta(days=1)

def to_dt(ts):
    ts = pd.to_numeric(ts); unit = "us" if ts.iloc[0] > 1e14 else "ms"
    return pd.to_datetime(ts, unit=unit, utc=True)

KC = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
def klines(market, symbol, interval, start):
    today = dt.date.today(); frames = []
    for y, m in months(start, (today.year, today.month)):
        path = f"{market}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{y}-{m:02d}.zip"
        b = zip_csv(f"{BV}/{path}", path.replace("/", "_"))
        if b is None and (y, m) == (today.year, today.month):   # current month: use the daily files
            for d in days(today.replace(day=1), today - dt.timedelta(days=1)):
                path = f"{market}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{d}.zip"
                bb = zip_csv(f"{BV}/{path}", path.replace("/", "_"))
                if bb: frames.append(pd.read_csv(io.BytesIO(bb), header=None, names=KC, skiprows=1 if bb[:4] == b"open" else 0))
            continue
        if b: frames.append(pd.read_csv(io.BytesIO(b), header=None, names=KC, skiprows=1 if b[:4] == b"open" else 0))
    df = pd.concat(frames); df["time"] = to_dt(df["open_time"]); df = df.drop(columns=["open_time", "close_time", "ignore"]).drop_duplicates("time").sort_values("time")
    return df.set_index("time")

def bitstamp_daily():
    out = []; start = int(dt.datetime(2011, 8, 18).timestamp())
    while True:
        r = get(f"https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=86400&limit=1000&start={start}")
        if r is None: break
        rows = r.json()["data"]["ohlc"]
        if not rows: break
        out += rows; last = int(rows[-1]["timestamp"])
        if last <= start or len(rows) < 1000: break
        start = last + 86400; time.sleep(0.5)
    df = pd.DataFrame(out).astype(float); df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df.drop(columns="timestamp").drop_duplicates("time").set_index("time").sort_index()

def bitmex_funding():
    out = []; start = 0
    while True:
        r = get(f"https://www.bitmex.com/api/v1/funding?symbol=XBTUSD&count=500&start={start}&reverse=false")
        if r is None: break
        rows = r.json()
        if not rows: break
        out += rows; start += len(rows)
        if len(rows) < 500: break
        time.sleep(1.2)
    df = pd.DataFrame(out); df["time"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[["time", "fundingRate", "fundingRateDaily"]].set_index("time")

def binance_funding_from(start):
    today = dt.date.today(); frames = []
    for y, m in months(start, (today.year, today.month)):
        path = f"futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-{y}-{m:02d}.zip"
        b = zip_csv(f"{BV}/{path}", path.replace("/", "_"))
        if b: frames.append(pd.read_csv(io.BytesIO(b)))
    df = pd.concat(frames); df["time"] = to_dt(df["calc_time"])
    return df.drop(columns="calc_time").drop_duplicates("time").set_index("time").sort_index()

def metrics(start=dt.date(2021, 12, 1)):
    today = dt.date.today(); frames = []
    for d in days(start, today - dt.timedelta(days=1)):
        path = f"futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-{d}.zip"
        b = zip_csv(f"{BV}/{path}", path.replace("/", "_"))
        if b:
            x = pd.read_csv(io.BytesIO(b)); x["time"] = pd.to_datetime(x["create_time"], utc=True); frames.append(x.drop(columns=["create_time", "symbol"]))
    df = pd.concat(frames).drop_duplicates("time").set_index("time").sort_index()
    return df.resample("15min").agg("last")      # 5-minute data thinned to 15-minute (last value)

def funding_rest_tail(df):
    """current month is not in the monthly archive: try the REST endpoint (may be geo-blocked on some runners; then the tail is simply missing)"""
    try:
        start = int((df.index[-1] + pd.Timedelta(hours=1)).timestamp() * 1000); out = []
        while True:
            r = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime={start}&limit=1000")
            if r is None: break
            rows = r.json()
            if not rows: break
            out += rows; start = rows[-1]["fundingTime"] + 1
            if len(rows) < 1000: break
        if out:
            x = pd.DataFrame(out); x["time"] = pd.to_datetime(x["fundingTime"], unit="ms", utc=True).dt.round("s")
            x = x.rename(columns={"fundingRate": "last_funding_rate"})[["time", "last_funding_rate"]].set_index("time"); x["funding_interval_hours"] = 8
            df = pd.concat([df, x[~x.index.isin(df.index)]]).sort_index()
    except Exception as e: print("rest tail skipped", e)
    return df

def with_cvd(df):
    df = df.copy(); df["delta"] = 2 * df["taker_buy_base"] - df["volume"]; df["cvd"] = df["delta"].cumsum(); return df

if __name__ == "__main__":
    START = (2022, 6)
    perp = with_cvd(klines("futures/um", "BTCUSDT", "15m", START)); perp.to_csv("data/btcusdt_perp_15m_cvd.csv"); print("perp 15m ok", len(perp))
    spot = with_cvd(klines("spot", "BTCUSDT", "15m", START)); spot.to_csv("data/btcusdt_spot_15m_cvd.csv"); print("spot 15m ok", len(spot))
    fu = funding_rest_tail(binance_funding_from(START)); fu.to_csv("data/binance_funding.csv"); print("funding ok", len(fu))
    oi = metrics(dt.date(2022, 6, 1)); oi.to_csv("data/binance_oi_15m.csv"); print("oi ok", len(oi))
