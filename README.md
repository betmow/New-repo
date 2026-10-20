# BTC derivatives data (2022-06 -> today)
Actions tab -> "fetch-btc-data" -> Run workflow. Files appear in /data:
- btcusdt_perp_15m_cvd.csv: Binance USDT-perp 15m OHLCV + taker buy volume + delta + cvd
- btcusdt_spot_15m_cvd.csv: Binance spot 15m, same columns (spot vs perp CVD divergence)
- binance_funding.csv: perp funding rate every 8h
- binance_oi_15m.csv: open interest, long/short ratios, taker long/short volume ratio, 15m
CVD = cumulative sum of (taker buy volume - taker sell volume) = 2*taker_buy_base - volume.
