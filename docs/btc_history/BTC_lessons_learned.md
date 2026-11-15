# BTC strategy – lessons learned (for the Claude app autolearning loop)
Version 1, 10 Nov 2026. Source: Claude Science research campaign, 59 trader videos, ~330 backtested attempts, plus combination, walk-forward and losing-streak studies on BTCUSDT perp 1m data (Jan 2023 – Oct 2026). Read this before proposing anything. Every number here comes from a backtest that was run; treat them as the reference.

## 1. The live system and its honest numbers
- LIVE: **v7.5.3** (since 10 Nov 2026, R = $1, manual orders, test of at least one month). **No changes to 7.5.3 during the test month.** Ideas go to a candidate list for the review after the month.
- 7.5.3 = the 7.4.1 trend entries/exits (9 breakout sleeves: 72/144/240h high/low, confirmed on 30m/2.5h/5.5h closes; 1 ATR stop, 10R target, break-even at +4R, 10-day max) + regime sizing x1.5 favourable / x0.5 unfavourable (Asia balance, HTF acceptance, OI z30 >= 1.2, flag C) with base from flags A/B and a 1.5R per-trade cap + **5R trend open-risk cap** + **separate 1R budget** for R1 range fades (0.5R x votes: x2.0 if net >= 2, x0.5 if net <= -1) and HTF-gated re-entries after an early stop-out (0.5R, direction-matched HTF).
- Full backtest 2023–26 (settings chosen on this data, optimistic): 910 trades, 313 winners, **632.7R, DD 9.43R, R/DD 67.1**.
- **Honest number = walk-forward out-of-fold 2024–26: 404.9R, DD 10.6R, R/DD 38.4** (v7.5.1 same months: 315.2R, DD 9.7, R/DD 32.5). Plan with ~38 or less. Most of the gap from 67 is period length (2023 alone was +215R); the rest is tuning.
- Character: win rate ~33%; median month only +2.2R; 12 of 46 months negative; worst drawdown -9.4R (29 Jan – 20 Mar 2025, 2 winners in 33 trades); worst day -7.4R; longest time without a new high 119 days. Gains come from a few big trend trades.

## 2. What works on BTC (keep, build on)
1. The edge lives in multi-day trend breakouts (72–240h); small losers, few big winners.
2. Regime states that keep their sign out of sample are perp positioning and higher-timeframe acceptance: **HTF acceptance** (any daily close in the last 10 days beyond the prior 20-day high/low), **OI elevated (z30 >= 1.2), best when also rising**, **Asia balance** (00–08 UTC volume-profile POC in the middle third), **flag C** (24h move >= 1.5 daily ATR into the entry with <= 20% retracement).
3. Sizing on those states (bet more in favourable regimes) is the single biggest improvement found. More trades did NOT come from new sleeves.
4. The only trade-adding rule that keeps passing: **re-entry after a stop-out, gated by HTF acceptance in the trade direction** (several independent sources).
5. R1 range fades work (sweep of the prior 24h high/low in a ranging market with an OI flush), and are better when location/crowding votes agree (90-day range location, Mayer < 1, funding crowd on the other side).
6. BTC at 1h–24h is momentum-dominated: thrusts continue, fades of extensions lose.

## 3. Do NOT repeat (tested and failed, with reason)
- Fast/short-term standalone sleeves without a regime gate (15m–4h breakouts, scalps): costs and noise eat them; they stack on the trend book and raise DD.
- Order flow / CVD / absorption / footprint at 4–24h: no information.
- Value-area fades, POC/VAH/VAL rejections, ping-pong in ranges: fail out of sample.
- Compression / tight-range breakouts: inverted on BTC (narrow boxes are WORSE).
- CME gap fades: 0 of 24 versions positive.
- Plain pullback entries (EMA touch, N-down-closes, Grimes/Scherman literal): lose out of sample.
- Counter-trend fades of extensions, close-at-extreme fades: lose.
- Equities/VIX/DXY/yields/USDT.D as filters: flip sign out of sample; USDT.D is a same-day mirror of BTC (r -0.97), no lead.
- Whale/on-chain flows as triggers: only weak 7–14 day contrarian information; zero intraday lead.
- Optimised parameters: lose in walk-forward; first-guess settings did better.
- Loss brakes (stop-out brakes, direction pauses, equity-curve filters, daily circuit breakers, chop filters): cut more winners than losers (best: -31R for -1R DD).
- Partial profit-taking and early break-even: hurt.
- Hash ribbons on top of 7.5.3: no gain (p 0.97).

## 4. Watch-list (promising, NOT proven)
- **Shadow-logged during the test month:** (a) Larry Williams volatility breakout, long only in the 200d uptrend, stop at the day open, exit at the close: +57 winners, +11.1R, DD 9.38, R/DD 68.6, null p 0.004 – chosen after seeing results; (b) panic dip-buy (1h Williams VIX-Fix first spike, long only in the uptrend, exit at SMA30): +57 winners, +8.5R, R/DD 69.1, p 0.003 full but ~0.05 per half, cost-fragile.
- Near-misses: Williams OI-gated daily-open breakout (+61 winners, +19R, OOS R/DD 29.8); Grimes "quiet tape" add-on when >= 3 trend sleeves agree (61%/54% win rate, DD 9.99); Scherman in-trend 4h pullback (+17 winners, p 0.17); 1h Keltner thrust (real timing but overlaps trend entries – possible x1.5 overlay on trend entries); volatility-contraction x0.5 (ATR14/ATR100 < 0.9); post-FOMC 48h window; balance-duration x0.5.

## 5. Testing standard (any idea must pass ALL)
1. **BTC only** (no ETH/SOL as evidence). Untouched data: BTC Jun 2022 – Jan 2023 only (thin; report trade counts).
2. Choose settings on 2023-01-15 .. 2024-12-31 only; 2025–26 untouched until the end.
3. Test ON TOP of 7.5.3 (with its caps), not standalone. Report: trades, winners, win rate, R, DD, R/DD, R/DD 2023–24 and 2025–26, R by year, worst day.
4. Candidate = more winners and R, DD <= 9.93R (base + 0.5), R/DD not worse in either half, walk-forward out-of-fold >= 38.4, random-timing null clustered at unique entry times p < 0.01.
5. Count how many variants you tried; ~1,000 comparisons have been run in this project, so p 0.03–0.05 results are expected by luck.

## 6. Required output block at the end of every loop run
```
RUN: <date time UTC>
IDEA: <one line>  | SOURCE: <video/post/own>
DIFFERS FROM DO-NOT-REPEAT BECAUSE: <one line>
RULES: entry / stop / exit / gate, exact
TESTED: yes/no  | DATA: <period>  | VARIANTS TRIED: <n>
RESULT ON TOP OF 7.5.3: trades, winners, R, DD, R/DD, R/DD 23-24, R/DD 25-26, null p
VERDICT: candidate / near-miss / fail / untested
CHANGE TO LIVE 7.5.3 PROPOSED: none (test month)
```
