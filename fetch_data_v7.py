#!/usr/bin/env python3
"""BTC + ETH data collector for model v7  (1-minute bars, order-book data, derivatives data).  Output goes to ./data7  (xz-compressed CSV).
Run by the GitHub Action `fetch-data-v7`, or by hand:  PARTS=probe python fetch_data_v7.py
Environment:
  PARTS     comma list of: probe, klines, premium, metrics, funding, depth, liq, bookticker, misc, hist     (default: klines,premium,metrics,funding,depth,liq,misc)
  SYMS      default BTCUSDT,ETHUSDT
  START     first month of 1-minute history, YYYY-MM (default 2022-06: keeps the warm-up the 200-day EMA etc. need before 2023)
  BT_FROM   first day for bookTicker (heavy files, default = 30 days ago), YYYY-MM-DD
  WORKERS   parallel downloads (default 8)
Safe to re-run: finished months are skipped, the current month is rebuilt, months with no data on the server are remembered (*.none)."""
import io, os, sys, time, json, zipfile, tempfile, subprocess, threading, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests, pandas as pd, numpy as np

BV = "https://data.binance.vision/data"; OUT = "data7"; os.makedirs(OUT, exist_ok=True)
WORKERS = int(os.environ.get("WORKERS", "8")); T0 = time.time(); LAST_CP = [time.time()]
TL = threading.local()
def sess():
    if not hasattr(TL, "s"): TL.s = requests.Session(); TL.s.headers["User-Agent"] = "btc-research/7"
    return TL.s
def get(url, tries=4, head=False):
    for i in range(tries):
        try:
            r = sess().head(url, timeout=60) if head else sess().get(url, timeout=120)
            if r.status_code in (404, 403): return None
            r.raise_for_status(); return r
        except Exception as e:
            if i == tries - 1: print("FAIL", url, e, flush=True); return None
            time.sleep(2 * (i + 1))
def zbytes(url):
    r = get(url)
    if r is None: return None
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content)); return z.read(z.namelist()[0])
    except Exception as e: print("BADZIP", url, e); return None
def zstream(url):
    """download a (possibly very large) zip to disk and return (file object of the first member, temp path). Returns (None, None) on 404."""
    for i in range(3):
        try:
            r = sess().get(url, stream=True, timeout=300)
            if r.status_code in (404, 403): return None, None
            r.raise_for_status(); tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            for ch in r.iter_content(1 << 20): tmp.write(ch)
            tmp.close(); z = zipfile.ZipFile(tmp.name); return z.open(z.namelist()[0]), tmp.name
        except Exception as e:
            if i == 2: print("FAIL", url, e, flush=True); return None, None
            time.sleep(3 * (i + 1))
def months(a, b):
    y, m = a
    while (y, m) <= b:
        yield y, m; m += 1
        if m == 13: y, m = y + 1, 1
def days_of(y, m, upto):
    d = dt.date(y, m, 1)
    while d.month == m and d <= upto: yield d; d += dt.timedelta(days=1)
TODAY = dt.date.today(); YEST = TODAY - dt.timedelta(days=1); CUR = (TODAY.year, TODAY.month)
START = tuple(int(x) for x in os.environ.get("START", "2022-06").split("-")); SYMS = os.environ.get("SYMS", "BTCUSDT,ETHUSDT").split(",")
PARTS = set(os.environ.get("PARTS", "klines,premium,metrics,funding,depth,liq,misc").split(","))
def to_dt(ts):
    ts = pd.to_numeric(ts); us = ts > 1e14; ts = ts.where(~us, ts // 1000); return pd.to_datetime(ts, unit="ms", utc=True)
def save(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True); df.to_csv(path, compression="xz")
def checkpoint(force=False):
    """commit + push what exists so far (only inside GitHub Actions); keeps progress if the job is cancelled"""
    if os.environ.get("GITHUB_ACTIONS") != "true": return
    if not force and time.time() - LAST_CP[0] < 1500: return
    LAST_CP[0] = time.time()
    for c in (["git", "add", OUT], ["git", "-c", "user.name=data-bot", "-c", "user.email=bot@users.noreply.github.com", "commit", "-m", "update data7"], ["git", "pull", "--rebase", "-q"], ["git", "push", "-q"]):
        subprocess.run(c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def month_done(path, y, m):
    return (y, m) != CUR and (os.path.exists(path) or os.path.exists(path + ".none"))
def mark_none(path, y, m):
    if (y, m) != CUR: os.makedirs(os.path.dirname(path), exist_ok=True); open(path + ".none", "w").write("no data on server\n")

# ------------------------------------------------------------------------------------------------ parsers
KC = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
def read_klines(b):
    x = pd.read_csv(io.BytesIO(b), header=None, names=KC, skiprows=1 if b[:4] == b"open" else 0)
    x["time"] = to_dt(x["open_time"]); return x.drop(columns=["open_time", "close_time", "ignore"]).drop_duplicates("time").set_index("time").sort_index()
def parse_metrics(b):
    x = pd.read_csv(io.BytesIO(b)); x["time"] = pd.to_datetime(x["create_time"], utc=True); return x.drop(columns=[c for c in ("create_time", "symbol") if c in x]).set_index("time").pipe(lambda d: d[~d.index.duplicated()]).sort_index()
def parse_depth(b):
    """bookDepth: rows (timestamp, percentage, depth, notional). -> one row per minute, notional (USD) within each % band: bd_m1..bd_m5 (bids), bd_p1..bd_p5 (asks)"""
    x = pd.read_csv(io.BytesIO(b)); x.columns = [c.lower() for c in x.columns]
    x["time"] = pd.to_datetime(x["timestamp"], utc=True); x["p"] = x["percentage"].astype(float).round().astype(int)
    w = x.pivot_table(index="time", columns="p", values="notional", aggfunc="last"); w.columns = [f"bd_{'m' if c < 0 else 'p'}{abs(c)}" for c in w.columns]
    return w.resample("1min").last().dropna(how="all")
def parse_bookticker(b):
    """bookTicker: update stream -> 1-minute aggregates (n updates, spread bps mean/max/min, imbalance mean, last bid/ask/sizes, last microprice)"""
    parts = []
    for ch in pd.read_csv(io.BytesIO(b) if isinstance(b, (bytes, bytearray)) else b, chunksize=1_500_000):
        ch.columns = [c.lower() for c in ch.columns]; tt = "transaction_time" if "transaction_time" in ch else "event_time"
        bid, ask, bq, aq = (ch[c].astype(float).to_numpy() for c in ("best_bid_price", "best_ask_price", "best_bid_qty", "best_ask_qty"))
        mid = (bid + ask) / 2; ch["m"] = (ch[tt].astype("int64") // 60000); ch["sp"] = (ask - bid) / mid * 1e4; ch["imb"] = (bq - aq) / (bq + aq).clip(min=1e-12); ch["mic"] = (ask * bq + bid * aq) / (bq + aq).clip(min=1e-12)
        ch["bid"], ch["ask"], ch["bq"], ch["aq"] = bid, ask, bq, aq
        g = ch.groupby("m"); parts.append(pd.DataFrame({"n": g.size(), "sp_sum": g.sp.sum(), "sp_max": g.sp.max(), "sp_min": g.sp.min(), "imb_sum": g.imb.sum(), "bid": g.bid.last(), "ask": g.ask.last(), "bid_qty": g.bq.last(), "ask_qty": g.aq.last(), "micro": g.mic.last()}))
    a = pd.concat(parts); g = a.groupby(level=0)
    o = pd.DataFrame({"n_updates": g.n.sum(), "spread_bps_mean": g.sp_sum.sum() / g.n.sum(), "spread_bps_max": g.sp_max.max(), "spread_bps_min": g.sp_min.min(), "imb_mean": g.imb_sum.sum() / g.n.sum(),
                      "bid": g.bid.last(), "ask": g.ask.last(), "bid_qty": g.bid_qty.last(), "ask_qty": g.ask_qty.last(), "micro": g.micro.last()})
    o.index = pd.to_datetime(o.index * 60, unit="s", utc=True); o.index.name = "time"; return o
def parse_liq(b):
    x = pd.read_csv(io.BytesIO(b)); x.columns = [c.lower() for c in x.columns]
    tcol = next((c for c in ("trade_time", "time", "transaction_time") if c in x), None)
    if tcol is None: raise ValueError("liq columns " + str(list(x.columns)))
    t = to_dt(x[tcol]).dt.floor("1min"); px = x["average_price"].where(x.get("average_price", 0) > 0, x["price"]) if "average_price" in x else x["price"]
    qty = x["accumulated_fill_quantity"] if "accumulated_fill_quantity" in x else x["original_quantity"]; usd = px * qty
    side = x["side"].astype(str).str.upper()           # SELL order = a LONG position was liquidated
    d = pd.DataFrame({"time": t, "long_liq_usd": np.where(side == "SELL", usd, 0.0), "short_liq_usd": np.where(side == "BUY", usd, 0.0), "n_liq": 1})
    return d.groupby("time").sum()

# ------------------------------------------------------------------------------------------------ builders
def build_monthly_zip(market, kind, sym, interval, y, m, path, keep):
    """one month of klines-type files: monthly zip, else the daily zips"""
    base = f"{BV}/{market}"; frames = []
    b = zbytes(f"{base}/monthly/{kind}/{sym}/{interval}/{sym}-{interval}-{y}-{m:02d}.zip")
    if b: frames.append(read_klines(b))
    else:
        ds = list(days_of(y, m, YEST))
        for bb in ThreadPoolExecutor(WORKERS).map(lambda d: zbytes(f"{base}/daily/{kind}/{sym}/{interval}/{sym}-{interval}-{d}.zip"), ds):
            if bb: frames.append(read_klines(bb))
    if not frames: mark_none(path, y, m); return 0
    df = pd.concat(frames); df = df[~df.index.duplicated()].sort_index()[keep]; save(df, path); return len(df)
def build_daily(dataset, sym, y, m, path, parse, market="futures/um", sub=None, freq=None):
    ds = list(days_of(y, m, YEST)); name = sub or dataset
    def one(d):
        b = zbytes(f"{BV}/{market}/daily/{dataset}/{sym}/{sym}-{dataset}-{d}.zip")
        if b is None: return None
        try: return parse(b)
        except Exception as e: print("PARSEFAIL", dataset, sym, d, e, flush=True); return None
    fr = [f for f in ThreadPoolExecutor(WORKERS).map(one, ds) if f is not None]
    if not fr: mark_none(path, y, m); return 0
    df = pd.concat(fr); df = df[~df.index.duplicated(keep="last")].sort_index()
    if freq: df = df.resample(freq).last()
    save(df, path); return len(df)
def run_months(label, sym, fn, pathfmt):
    n = 0
    for y, m in months(START, CUR):
        path = pathfmt.format(y=y, m=m)
        if month_done(path, y, m): continue
        c = fn(y, m, path); n += c; print(f"{label} {sym} {y}-{m:02d}: {c} rows  [{(time.time()-T0)/60:.1f} min]", flush=True); checkpoint()
    return n
def bookticker(sym):
    frm = dt.date.fromisoformat(os.environ["BT_FROM"]) if os.environ.get("BT_FROM") else TODAY - dt.timedelta(days=30)
    d = frm
    while d <= YEST:
        p = f"{OUT}/bookticker/{sym}/{d}.csv.xz"
        if not (os.path.exists(p) or os.path.exists(p + ".none")):
            b, tmpf = zstream(f"{BV}/futures/um/daily/bookTicker/{sym}/{sym}-bookTicker-{d}.zip")
            if b is None: os.makedirs(os.path.dirname(p), exist_ok=True); open(p + ".none", "w").write("none\n")
            else:
                try: save(parse_bookticker(b), p); print("bookTicker", sym, d, "ok", flush=True)
                except Exception as e: print("PARSEFAIL bookTicker", sym, d, e, flush=True)
                finally:
                    b.close()
                    if tmpf and os.path.exists(tmpf): os.remove(tmpf)
            checkpoint()
        d += dt.timedelta(days=1)

# ------------------------------------------------------------------------------------------------ funding / misc
def funding(sym):
    frames = []
    for y, m in months(START, CUR):
        b = zbytes(f"{BV}/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{y}-{m:02d}.zip")
        if b: frames.append(pd.read_csv(io.BytesIO(b)))
    df = pd.concat(frames); df["time"] = to_dt(df["calc_time"]); df = df.drop(columns="calc_time").drop_duplicates("time").set_index("time").sort_index()
    try:
        start = int((df.index[-1] + pd.Timedelta(hours=1)).timestamp() * 1000); out = []
        while True:
            r = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={start}&limit=1000")
            if r is None: break
            rows = r.json()
            if not rows: break
            out += rows; start = rows[-1]["fundingTime"] + 1
            if len(rows) < 1000: break
        if out:
            x = pd.DataFrame(out); x["time"] = pd.to_datetime(x["fundingTime"], unit="ms", utc=True).dt.round("s"); x = x.rename(columns={"fundingRate": "last_funding_rate"})[["time", "last_funding_rate"]].set_index("time"); x["funding_interval_hours"] = 8
            df = pd.concat([df, x[~x.index.isin(df.index)]]).sort_index()
    except Exception as e: print("funding REST tail skipped", e)
    save(df, f"{OUT}/funding/{sym}_funding.csv.xz"); print("funding", sym, len(df), flush=True)
def stablecoin_supply():
    out = {}
    for name, sid in (("usdt", 1), ("usdc", 2)):
        r = get(f"https://stablecoins.llama.fi/stablecoincharts/all?stablecoin={sid}")
        if r is None: continue
        x = pd.DataFrame([{"time": pd.to_datetime(int(a["date"]), unit="s", utc=True), name: (a.get("totalCirculatingUSD") or a.get("totalCirculating") or {}).get("peggedUSD")} for a in r.json()]).set_index("time"); out[name] = x[name]
    save(pd.DataFrame(out).sort_index(), f"{OUT}/misc/stablecoin_supply_daily.csv.xz")
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
    save(df.drop(columns="timestamp").drop_duplicates("time").set_index("time").sort_index(), f"{OUT}/misc/btcusd_daily_bitstamp.csv.xz")
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
    df = pd.DataFrame(out); df["time"] = pd.to_datetime(df["timestamp"], utc=True); save(df[["time", "fundingRate", "fundingRateDaily"]].set_index("time"), f"{OUT}/misc/xbtusd_funding_bitmex.csv.xz")

# ------------------------------------------------------------------------------------------------ probe
def probe():
    """checks which datasets exist, from when, how big, and what the columns look like. writes data7/_probe.txt"""
    L = []; P = lambda *a: (print(*a, flush=True), L.append(" ".join(str(x) for x in a)))
    sym = SYMS[0]
    def first_day(ds, market="futures/um", frm=dt.date(2020, 1, 1), step=20):
        d = frm
        while d <= YEST:
            r = get(f"{BV}/{market}/daily/{ds}/{sym}/{sym}-{ds}-{d}.zip", head=True)
            if r is not None: return d
            d += dt.timedelta(days=step)
        return None
    for ds in ("bookDepth", "bookTicker", "liquidationSnapshot", "metrics", "premiumIndexKlines"):
        if ds == "premiumIndexKlines": url = lambda d: f"{BV}/futures/um/daily/{ds}/{sym}/1m/{sym}-1m-{d}.zip"
        else: url = lambda d, ds=ds: f"{BV}/futures/um/daily/{ds}/{sym}/{sym}-{ds}-{d}.zip"
        f = None; d = dt.date(2020, 1, 1)
        while d <= YEST:
            r = get(url(d), head=True)
            if r is not None: f = d; break
            d += dt.timedelta(days=15)
        P(f"{ds}: first available day (scan step 15d) = {f}")
        for dd in [x for x in (f, dt.date(2023, 6, 1), dt.date(2025, 6, 1), YEST - dt.timedelta(days=3)) if x]:
            r = get(url(dd), head=True)
            if r is None: P(f"   {dd}: not found"); continue
            P(f"   {dd}: {int(r.headers.get('Content-Length', 0))/1e6:.1f} MB zip")
        if f:
            b = zbytes(url(f))
            if b: P("   header+2 rows:", b[:500].decode(errors="replace").replace("\n", " | ")[:420])
    for ds in ("liquidationSnapshot",):
        r = get(f"{BV}/futures/um/monthly/{ds}/{sym}/{sym}-{ds}-2023-01.zip", head=True); P(f"{ds} monthly 2023-01: {'found' if r is not None else 'not found'}")
    open(f"{OUT}/_probe.txt", "w").write("\n".join(L) + "\n")

# ------------------------------------------------------------------------------------------------ main
if __name__ == "__main__":
    print("PARTS", sorted(PARTS), "SYMS", SYMS, "START", START, flush=True)
    if "probe" in PARTS: probe()
    for sym in SYMS:
        tag = sym.lower()
        if "klines" in PARTS:
            for market, nm in (("spot", "spot"), ("futures/um", "perp")):
                run_months(f"klines {nm}", sym, lambda y, m, p, market=market: build_monthly_zip(market, "klines", sym, "1m", y, m, p, ["open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"]), f"{OUT}/klines/{tag}_{nm}_1m/{{y}}-{{m:02d}}.csv.xz")
        if "premium" in PARTS:
            run_months("premium", sym, lambda y, m, p: build_monthly_zip("futures/um", "premiumIndexKlines", sym, "1m", y, m, p, ["close"]), f"{OUT}/premium/{tag}_premium_1m/{{y}}-{{m:02d}}.csv.xz")
        if "metrics" in PARTS:
            run_months("metrics", sym, lambda y, m, p: build_daily("metrics", sym, y, m, p, parse_metrics), f"{OUT}/metrics/{tag}_metrics_5m/{{y}}-{{m:02d}}.csv.xz")
        if "depth" in PARTS:
            run_months("bookDepth", sym, lambda y, m, p: build_daily("bookDepth", sym, y, m, p, parse_depth), f"{OUT}/depth/{tag}_bookdepth_1m/{{y}}-{{m:02d}}.csv.xz")
        if "liq" in PARTS:
            run_months("liquidations", sym, lambda y, m, p: build_daily("liquidationSnapshot", sym, y, m, p, parse_liq), f"{OUT}/liq/{tag}_liq_1m/{{y}}-{{m:02d}}.csv.xz")
        if "funding" in PARTS: funding(sym)
        if "bookticker" in PARTS: bookticker(sym)
    if "misc" in PARTS: stablecoin_supply(); print("stablecoins ok", flush=True)
    if "hist" in PARTS: bitstamp_daily(); bitmex_funding(); print("history 2011+ ok", flush=True)
    man = {}
    for root, _, fs in os.walk(OUT):
        for f in fs:
            if f.endswith(".xz") or f.endswith(".none"): man.setdefault(os.path.relpath(root, OUT), []).append(f)
    json.dump({k: dict(files=len(v), first=sorted(v)[0], last=sorted(v)[-1]) for k, v in sorted(man.items())}, open(f"{OUT}/_manifest.json", "w"), indent=1)
    checkpoint(True); print("done in %.1f min" % ((time.time() - T0) / 60), flush=True)
