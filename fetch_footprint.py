#!/usr/bin/env python3
"""Binance USD-M perp footprint builder (free public archive: data.binance.vision aggTrades).
For every 1-minute bar it stores aggressive buy/sell volume at each price level (true 1-minute footprint), plus per-minute totals and large-trade tables.
Output (xz CSV) in ./footprint/<SYM>/:  levels1m (bar,level,buy,sell,nbuy,nsell) | bars1m (per-minute totals + poc/lo/hi/imbalance counts) | bars (15-minute, derived) | big1m (large trades by size band)
   level = price floored to TICK dollars; buy = aggressive buyers, base units.  _probe.txt, _missing.txt = days the archive does not have.
Environment: MODE probe|run|selftest   SYM (BTCUSDT)   START YYYY-MM   END YYYY-MM (blank = last finished month + current month)   TICK ($ per level; default 10 BTC, 0.5 ETH)   BIG (base units; default 2 BTC, 20 ETH)   WORKERS (default 3)
Safe to re-run: finished months are skipped (the current month is rebuilt)."""
import io, os, sys, time, zipfile, tempfile, datetime as dt
from concurrent.futures import ProcessPoolExecutor
import requests, numpy as np, pandas as pd
BV = "https://data.binance.vision/data/futures/um"; OUT = "footprint"
SYM = os.environ.get("SYM", "BTCUSDT"); MODE = os.environ.get("MODE", "probe")
TICK = float(os.environ.get("TICK") or (10 if SYM.startswith("BTC") else 0.5 if SYM.startswith("ETH") else 0.05))
BIG = float(os.environ.get("BIG") or (2 if SYM.startswith("BTC") else 20 if SYM.startswith("ETH") else 500))
EDGES = [float(x) for x in (os.environ.get("EDGES") or ("1,2,5,10,25" if SYM.startswith("BTC") else "10,20,50,100,250" if SYM.startswith("ETH") else "500,1000,2500,5000,10000")).split(",")]
WORKERS = int(os.environ.get("WORKERS") or 3); BAR_MS = 15 * 60 * 1000
def url_day(d): return f"{BV}/daily/aggTrades/{SYM}/{SYM}-aggTrades-{d:%Y-%m-%d}.zip"
def url_month(y, m): return f"{BV}/monthly/aggTrades/{SYM}/{SYM}-aggTrades-{y}-{m:02d}.zip"
def req(method, url, **kw):
    for i in range(4):
        try:
            r = requests.request(method, url, timeout=kw.pop("timeout", 120), **kw)
            if r.status_code in (403, 404): return None
            r.raise_for_status(); return r
        except Exception as e:
            if i == 3: print("FAIL", url, e, flush=True); return None
            time.sleep(3 * (i + 1))

def process_csv(f):
    """f: binary aggTrades csv (header optional). Returns (levels_1m, bars_1m, big_1m). Everything else (15m) is derived from these."""
    head = f.readline(); f.seek(0); has_header = head.lstrip()[:1].isalpha()
    cols = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]
    rd = pd.read_csv(f, header=0 if has_header else None, names=None if has_header else cols, usecols=["price", "quantity", "transact_time", "is_buyer_maker"],
                     dtype={"price": "float64", "quantity": "float64", "transact_time": "int64"}, chunksize=2_000_000)
    L, B, G = [], [], []
    for c in rd:
        ibm = c["is_buyer_maker"].astype(str).str.lower().eq("true").to_numpy()      # buyer is maker -> the aggressor SOLD
        p = c.price.to_numpy(); q = c.quantity.to_numpy(); t = c.transact_time.to_numpy()
        t = np.where(t > 1e14, t // 1000, t); bar = (t // 60_000) * 60_000; lvl = np.floor(p / TICK) * TICK
        buy = ~ibm
        g = pd.DataFrame(dict(bar=bar, level=lvl, buy=np.where(buy, q, 0.0), sell=np.where(buy, 0.0, q), nbuy=buy.astype(np.int32), nsell=(~buy).astype(np.int32)))
        L.append(g.groupby(["bar", "level"], sort=False).sum().reset_index())
        big = q >= BIG
        b = pd.DataFrame(dict(bar=bar, buy=g.buy.to_numpy(), sell=g.sell.to_numpy(), nbuy=g.nbuy.to_numpy(), nsell=g.nsell.to_numpy(), big_buy=np.where(big & buy, q, 0.0), big_sell=np.where(big & ~buy, q, 0.0), pq=p * q,
                          max_buy=np.where(buy, q, 0.0), max_sell=np.where(buy, 0.0, q)))
        B.append(b.groupby("bar", sort=False).agg(buy=("buy", "sum"), sell=("sell", "sum"), nbuy=("nbuy", "sum"), nsell=("nsell", "sum"), big_buy=("big_buy", "sum"), big_sell=("big_sell", "sum"), pq=("pq", "sum"), max_buy=("max_buy", "max"), max_sell=("max_sell", "max")).reset_index())
        sel = q >= EDGES[0]
        if sel.any():
            bk = np.digitize(q[sel], EDGES) - 1
            G.append(pd.DataFrame(dict(minute=bar[sel], bk=bk, side=np.where(buy[sel], "b", "s"), q=q[sel])).groupby(["minute", "bk", "side"]).q.agg(["sum", "count", "max"]).reset_index())
    lv = pd.concat(L).groupby(["bar", "level"]).sum().reset_index()
    br = pd.concat(B).groupby("bar").agg(buy=("buy", "sum"), sell=("sell", "sum"), nbuy=("nbuy", "sum"), nsell=("nsell", "sum"), big_buy=("big_buy", "sum"), big_sell=("big_sell", "sum"), pq=("pq", "sum"), max_buy=("max_buy", "max"), max_sell=("max_sell", "max")).reset_index()
    br["vwap"] = br.pq / (br.buy + br.sell); br = br.drop(columns="pq")
    return lv, br, big_wide(G)
def to15(lv, br):
    """derive 15-minute level table and bar table from the 1-minute ones"""
    l15 = lv.assign(bar=(lv.bar // BAR_MS) * BAR_MS).groupby(["bar", "level"]).sum().reset_index()
    b = br.assign(bar=(br.bar // BAR_MS) * BAR_MS, pq=br.vwap * (br.buy + br.sell))
    b15 = b.groupby("bar").agg(buy=("buy", "sum"), sell=("sell", "sum"), nbuy=("nbuy", "sum"), nsell=("nsell", "sum"), big_buy=("big_buy", "sum"), big_sell=("big_sell", "sum"), pq=("pq", "sum"), max_buy=("max_buy", "max"), max_sell=("max_sell", "max")).reset_index()
    b15["vwap"] = b15.pq / (b15.buy + b15.sell); return l15, b15.drop(columns="pq")
def big_wide(G):
    """1-minute large-trade table: for each size bucket k (edge k <= qty < edge k+1) volume (v), count (n) per side b/s; plus the biggest single trade per side."""
    if not G: return pd.DataFrame(columns=["minute"])
    g = pd.concat(G).groupby(["minute", "bk", "side"]).agg({"sum": "sum", "count": "sum", "max": "max"}).reset_index()
    out = pd.DataFrame(index=sorted(g.minute.unique())); out.index.name = "minute"
    for (bk, sd), x in g.groupby(["bk", "side"]):
        x = x.set_index("minute"); out[f"v{bk}{sd}"] = x["sum"]; out[f"n{bk}{sd}"] = x["count"]
    for sd, x in g.groupby("side"): out[f"max_{sd}"] = x.groupby("minute")["max"].max()
    return out.fillna(0).reset_index()
def add_stats(lv, br):
    """per-bar stats from the level table: point of control, price range, and diagonal imbalances (>=3:1, buys vs the sells one level below; sells vs the buys one level above)"""
    lv = lv.sort_values(["bar", "level"]).reset_index(drop=True); eps = 1e-9
    same_dn = lv.bar.eq(lv.bar.shift(1)); same_up = lv.bar.eq(lv.bar.shift(-1))
    sell_below = lv.sell.shift(1).where(same_dn, np.nan); buy_above = lv.buy.shift(-1).where(same_up, np.nan)
    lv["ib"] = (lv.buy >= 3 * (sell_below.fillna(0) + eps)) & sell_below.notna() & (lv.buy > 0)
    lv["is_"] = (lv.sell >= 3 * (buy_above.fillna(0) + eps)) & buy_above.notna() & (lv.sell > 0)
    lv["tot"] = lv.buy + lv.sell
    poc = lv.loc[lv.groupby("bar")["tot"].idxmax()].set_index("bar")["level"].rename("poc")
    g = lv.groupby("bar"); rng_ = g["level"].agg(lo="min", hi="max"); st = g[["ib", "is_"]].sum().rename(columns={"ib": "buy_imb_levels", "is_": "sell_imb_levels"})
    return br.set_index("bar").join(poc).join(rng_).join(st).reset_index()

def day_job(d):
    u = url_day(d); r = req("GET", u, stream=True, timeout=300)
    if r is None: return d, None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    for ch in r.iter_content(1 << 20): tmp.write(ch)
    tmp.close()
    try:
        z = zipfile.ZipFile(tmp.name)
        with z.open(z.namelist()[0]) as f: lv, br, bg = process_csv(f)
    except Exception as e: print("BADZIP", u, e, flush=True); os.unlink(tmp.name); return d, None
    os.unlink(tmp.name); day0 = int(pd.Timestamp(d, tz="UTC").timestamp() * 1000)
    ok = (lv.bar >= day0) & (lv.bar < day0 + 86_400_000); lv = lv[ok]; br = br[(br.bar >= day0) & (br.bar < day0 + 86_400_000)]; bg = bg[(bg.minute >= day0) & (bg.minute < day0 + 86_400_000)] if len(bg) else bg
    return d, (lv, br, bg)
def to_time(df, c="bar"): df = df.copy(); df[c] = pd.to_datetime(df[c], unit="ms", utc=True); return df
def do_month(y, m, pool):
    for sub in ("levels1m", "bars1m", "bars", "big1m"): os.makedirs(f"{OUT}/{SYM}/{sub}", exist_ok=True)
    f1, fb1, fb, fg = (f"{OUT}/{SYM}/{sub}/{y}-{m:02d}.csv.xz" for sub in ("levels1m", "bars1m", "bars", "big1m"))
    today = dt.date.today(); cur = (today.year, today.month) == (y, m)
    if all(os.path.exists(x) for x in (f1, fb1, fb, fg)) and not cur: print(y, m, "skip (done)"); return
    d = dt.date(y, m, 1); days = []
    while d.month == m and d < today: days.append(d); d += dt.timedelta(days=1)
    if not days: return
    t0 = time.time(); res = list(pool.map(day_job, days)); miss = [str(d) for d, r in res if r is None]; got = [r for d, r in res if r is not None]
    if miss:
        with open(f"{OUT}/{SYM}/_missing.txt", "a") as f: f.write(f"{y}-{m:02d}: {','.join(miss)}\n")
    if not got: print(y, m, "NO DATA", flush=True); return
    lv = pd.concat([g[0] for g in got]); br = pd.concat([g[1] for g in got]).sort_values("bar")
    bgs = [g[2] for g in got if len(g[2])]; bg = pd.concat(bgs).fillna(0).sort_values("minute") if bgs else pd.DataFrame(columns=["minute"])
    l15, b15 = to15(lv, br); b15 = add_stats(l15, b15); b1 = add_stats(lv, br)
    to_time(lv).sort_values(["bar", "level"]).to_csv(f1, index=False, float_format="%.4f"); to_time(b1).to_csv(fb1, index=False, float_format="%.4f")
    to_time(b15).to_csv(fb, index=False, float_format="%.4f"); to_time(bg, "minute").to_csv(fg, index=False, float_format="%.4f")
    print(f"{y}-{m:02d}: {len(got)}/{len(days)} days, {len(lv)} 1m-level rows, {time.time()-t0:.0f}s, missing {miss}", flush=True)

def probe():
    os.makedirs(OUT, exist_ok=True); lines = [f"probe {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC  {SYM}"]
    today = dt.date.today(); tests = [dt.date(2021, 1, 4), dt.date(2022, 6, 1), dt.date(2023, 1, 16), dt.date(2024, 6, 3), dt.date(2025, 6, 2), dt.date(2026, 10, 28), today - dt.timedelta(days=2), today - dt.timedelta(days=1)]
    for d in tests:
        r = req("HEAD", url_day(d)); lines.append(f"daily  {d}  " + (f"OK {int(r.headers.get('Content-Length', 0))/1e6:.0f} MB zipped" if r is not None else "MISSING (404/403)"))
    for y, m in ((2022, 6), (2024, 1), (2026, 9)):
        r = req("HEAD", url_month(y, m)); lines.append(f"month  {y}-{m:02d}  " + (f"OK {int(r.headers.get('Content-Length', 0))/1e6:.0f} MB zipped" if r is not None else "MISSING"))
    print("\n".join(lines)); open(f"{OUT}/_probe.txt", "w").write("\n".join(lines) + "\n")
def selftest():
    rng = np.random.default_rng(1); n = 300_000; t0 = int(pd.Timestamp("2024-03-05", tz="UTC").timestamp() * 1000)
    df = pd.DataFrame(dict(agg_trade_id=np.arange(n), price=np.round(60000 + np.cumsum(rng.normal(0, 3, n)), 1), quantity=np.round(rng.exponential(0.05, n) * np.where(rng.random(n) < 0.002, 40, 1), 3), first_trade_id=0, last_trade_id=0,
                           transact_time=t0 + np.sort(rng.integers(0, 86_400_000, n)), is_buyer_maker=rng.choice(["true", "false"], n)))
    for hdr in (True, False):
        buf = io.BytesIO(df.to_csv(index=False, header=hdr).encode()); lv, br, bg = process_csv(buf)
        assert abs(lv.buy.sum() + lv.sell.sum() - df.quantity.sum()) < 1e-6, "volume mismatch"
        assert abs(br.buy.sum() - df.quantity[df.is_buyer_maker == "false"].sum()) < 1e-6, "buy mismatch"
        assert (lv.groupby("bar")[["buy", "sell"]].sum().sum(axis=1) - br.set_index("bar").eval("buy+sell")).abs().max() < 1e-6
        l15, b15 = to15(lv, br); assert abs(l15.buy.sum() - lv.buy.sum()) < 1e-6 and len(b15) == 96 and abs(b15.buy.sum() - br.buy.sum()) < 1e-6
        st = add_stats(l15, b15); assert len(st) == 96 and st.poc.notna().all(); st1 = add_stats(lv, br); assert len(st1) == len(br)
    big = df[df.quantity >= EDGES[0]]; tot = sum(bg[c].sum() for c in bg.columns if c[0] == "v" and c[-1] in "bs")
    assert abs(tot - big.quantity.sum()) < 1e-6, "big-trade volume mismatch"; assert bg.minute.is_monotonic_increasing
    print("selftest OK:", len(lv), "1-minute level rows,", len(br), "minutes,", len(b15), "15m bars,", len(bg), "minutes with big trades")
def main():
    if MODE == "probe": return probe()
    if MODE == "selftest": return selftest()
    a = tuple(int(x) for x in os.environ.get("START", "2022-06").split("-")); today = dt.date.today()
    e = os.environ.get("END") or f"{today.year}-{today.month:02d}"; b = tuple(int(x) for x in e.split("-")); y, m = a
    with ProcessPoolExecutor(WORKERS) as pool:
        while (y, m) <= b:
            do_month(y, m, pool); m += 1
            if m == 13: y, m = y + 1, 1
if __name__ == "__main__": main()
