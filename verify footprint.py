"""Cross-check footprint against Binance klines already in data7: per-bar volume and taker-buy volume must match (1-minute and 15-minute)."""
import sys, pandas as pd
sym = sys.argv[1]; ym = sys.argv[2]; ok = True
k = pd.read_csv(f"data7/klines/{sym.lower()}_perp_1m/{ym}.csv.xz", parse_dates=["time"]).set_index("time")
for name, kk in (("1m", k[["volume", "taker_buy_base"]]), ("15m", k[["volume", "taker_buy_base"]].resample("15min").sum())):
    bars = pd.read_csv(f"footprint/{sym}/bars{'1m' if name == '1m' else ''}/{ym}.csv.xz", parse_dates=["bar"]).set_index("bar")
    j = bars.join(kk, how="inner"); j["tot"] = j.buy + j.sell
    e1 = (j.tot - j.volume).abs() / j.volume.clip(lower=1e-9); e2 = (j.buy - j.taker_buy_base).abs() / j.taker_buy_base.clip(lower=1e-9)
    print(f"{sym} {ym} {name}: {len(j)} bars | volume rel.err median {e1.median():.2e} max {e1.max():.2e} | taker-buy rel.err median {e2.median():.2e} max {e2.max():.2e}")
    ok &= e1.median() < 1e-3 and e2.median() < 1e-3
print("PASS" if ok else "CHECK")
