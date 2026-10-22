"""Downloads 1-minute Binance spot candles for BTCUSDT, ETHUSDT, SOLUSDT, but only the windows around the events listed in events_15m.csv
(75 minutes per event: 30 min before to 45 min after the 15m bar). Output: data/events_1m_btc.csv, _eth.csv, _sol.csv"""
import io, os, time, zipfile
import requests, pandas as pd

BV = "https://data.binance.vision/data/spot/daily/klines"
os.makedirs("data", exist_ok=True); os.makedirs("raw", exist_ok=True)
S = requests.Session(); S.headers["User-Agent"] = "btc-research/1.0"
KC = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]

def get(url, tries=4):
    for i in range(tries):
        try:
            r = S.get(url, timeout=60)
            if r.status_code == 404: return None
            r.raise_for_status(); return r
        except Exception as e:
            if i == tries - 1: print("FAIL", url, e, flush=True); return None
            time.sleep(2 * (i + 1))

def to_dt(ts):
    ts = pd.to_numeric(ts); us = ts > 1e14
    return pd.to_datetime(ts.where(~us, ts // 1000), unit="ms", utc=True)

def day_df(sym, day):
    url = f"{BV}/{sym}/1m/{sym}-1m-{day}.zip"; r = get(url)
    if r is None: return None
    b = zipfile.ZipFile(io.BytesIO(r.content)).read(zipfile.ZipFile(io.BytesIO(r.content)).namelist()[0])
    df = pd.read_csv(io.BytesIO(b), header=None, names=KC, skiprows=1 if b[:4] == b"open" else 0)
    df["time"] = to_dt(df["open_time"]); return df.set_index("time")[["open", "high", "low", "close", "volume", "taker_buy_base"]].sort_index()

if __name__ == "__main__":
    ev = pd.to_datetime(pd.read_csv("events_15m.csv")["time"], utc=True)
    days = sorted(set(ev.dt.floor("D")) | set((ev - pd.Timedelta("30min")).dt.floor("D")) | set((ev + pd.Timedelta("45min")).dt.floor("D")))
    print("events", len(ev), "days", len(days), flush=True)
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        parts = []; t0 = time.time()
        for k, d in enumerate(days):
            df = day_df(sym, d.strftime("%Y-%m-%d"))
            if df is not None:
                m = pd.Series(False, index=df.index)
                for t in ev[(ev >= d - pd.Timedelta("1h")) & (ev <= d + pd.Timedelta("25h"))]:
                    m |= (df.index >= t - pd.Timedelta("30min")) & (df.index < t + pd.Timedelta("45min"))
                if m.any(): parts.append(df[m])
            if k % 100 == 0: print(sym, k, "/", len(days), round(time.time() - t0), "s", flush=True)
        out = pd.concat(parts); out = out[~out.index.duplicated()].sort_index()
        out.to_csv(f"data/events_1m_{sym[:3].lower()}.csv"); print(sym, "ok", len(out), flush=True)
