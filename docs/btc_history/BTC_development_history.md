# BTC system: development history v6 -> 7.4.1 -> 7.5.3 (read before proposing ANY idea)
Compiled 15 Nov 2026 from the six version PDFs, the corrected-expectations PDF, the bot code and the project notes. Every number is copied from those documents. Exact decision DATES are not in the surviving files (the PDFs were uploaded together on 31 Oct 2026); the ORDER of versions is certain.

## 0. Source map (where each fact lives)
| Document | Content |
|---|---|
| BTC_model_v6.pdf | v6: reversal + three trend sleeves, risk layer, candle-size scan, slippage |
| BTC_v7_strategy.pdf | first v7: 72h/1.0 ATR trend settings + depth swing sleeve (+506R) |
| BTC_v7_depth_research.pdf | 1-minute data and all order-book depth tests on v6 (about 300 comparisons) |
| BTC_v71_regime_and_drawdown.pdf | 7.1 range gate; depth veto and ten regime filters rejected; drawdown rules |
| BTC_v7_version_ladder.pdf | ladder 7.0 to "7.4" (50-day direction, not adopted) |
| BTC_v74_live_plan.pdf | 7.4 = lookback ensemble 72/144/240h + swing live; plan for $100 account |
| BTC_v741_corrected_expectations.pdf | 7.4.1 = same rules, time-correct numbers (328R, not 410R) |
| BTC_v7.5.3 packages and BTC_lessons_learned.md | Claude Science research campaign (10 Nov 2026) |
| v6engine.py, swing.py, collector.py, swing_ref.csv (btc-shadow.zip) | the code that implements all of it |

## 1. Timeline
| Step | What changed | Result (BTC perp, 15 Jan 2023 -> Oct 2026, 5 bp/side, flat size unless noted) |
|---|---|---|
| v6 | Reversal sleeve + trend breakouts on 30m / 2.5h / 5.5h candles, 48h lookback, 1.5 ATR stop, direction from 200d EMA, gate |dist|<14%. Built on SPOT data. | 375 trades, +420R, DD 25.4 (spot). Rebuilt on PERP prices: 390 trades, +312R, DD 27.4, R/DD 11.4. Perp is the right base (what you trade). |
| 7.0 | Trend settings 72h lookback, 1.0 ATR stop (27 combinations tested; rankings agreed IS vs OOS at 0.68/0.69) | 385 trades, 424R, DD 24.4, R/DD 17.4 |
| 7.1 | Reversal sleeve only when ER20 < 0.25 (range). Skipped trades averaged -0.15R. | 429R, DD 22.1, R/DD 19.4. "Promising, not proven": 34 trades, about 20 regime variants looked at. |
| 7.2 | Depth-flagged SWING sleeve added (counter-trend breakouts, old 48h/1.5 ATR triggers, taken when depth score S4 >= 0.8). | 512R, DD 21.0, R/DD 24.4 (rebuilt 516/21.4). Swing alone 84 trades, +82.5R, 29% win, 95% interval -0.01 to +1.99 (not solid). Paper only on the server. |
| 7.3 | Size scaling max(0.5, 1 - DD/20) on closed-trade drawdown | Original claim 440R / DD 13.8 / R/DD 32.0. CORRECTED later: 364R / 14.2 / 25.6. |
| "7.4" (first meaning) | Direction from 50d EMA instead of 200d | 452R, DD 15.2, R/DD 29.7: NOT adopted. Overlaps the swing sleeve (correlation to swing rose -0.08 to +0.46). Revisit only together with the swing sleeve. |
| 7.4 (second meaning, used from then on) | Lookback ensemble 72/144/240h x 3 candle sizes = 9 trend sleeves at 1/3 R each + range reversal + swing sleeve LIVE from day one | Claimed 805 trades, 410R, DD 11.0, R/DD 37.3 (about 25 lookback combos tried). |
| 7.4.1 (corrected) | NO rule change. Re-run on full 1-minute perp data with the size factor computed in time order (the old 410R/37.3 scaled trades in trade-list order = inflated). | 820 trades, 328R, DD 11.9, R/DD 27.6 (flat size 445R / DD 16.8). Cost 5/10/15/25 bp: R/DD 27.6 / 21.6 / 16.6 / 9.2. Group split: reversal 34 trades +44R; trend 692 +313R flat; swing 94 +88R flat (DD 12.8). |
| 7.5 | Same entries/exits + sizing flags A (extension) / B (volume), 0.5/1/2x tiers, 3R open-risk cap + R1 range sweep-fade sleeve (OI-flush condition) | Sizing scheme with R/DD +35% OOS vs 7.4.1 trend sleeves; PROBABLE not PROVEN (412-variant scan). A look-ahead bug (open 1h bar read at :15/:30/:45) inflated early flag results; fixed 4 Nov. |
| 7.5.1 / 7.5.3 (Claude Science) | Regime sizing (Asia balance, HTF acceptance, OI z30, flag C), 1.5R cap, 5R trend pool, separate 1R pool for R1 with votes + RE re-entry. NO swing sleeve, NO reversal sleeve in the alerts. | In sample 2023-26: 910 trades, 632.7R, DD 9.43, R/DD 67.1. Honest out-of-fold 2024-26: 404.9R, DD 10.6, R/DD 38.4 (v7.5.1 32.5). LIVE since 10 Nov 2026. |

## 2. How the order book got into the strategy
1. v6 + depth tests (depth research PDF): 14 pre-existing features (premium, basis, OI, ratios, taker, lead-lag) = 0 of 42 tests pass. Depth as a filter on v6 in-trend trades: 9 features, 27 tests, nothing passes. Depth imbalance beyond +-$100M: no stable effect. "Liquidity withdrawal" looked strong (+1.95R vs +0.48R) but was a proxy for momentum: WITHDRAWN. 60-combination scan: one survivor, change in depth within +-1% on the side BEHIND the trade over 4h (rank corr +0.165, positive all four years) but as a skip filter it failed OOS. 5% bid/ask imbalance predicts direction weakly at 24-48h (bearish tail holds OOS, bullish does not): shadow log only.
2. The idea that unlocked it (v7 strategy PDF): the 200d EMA separates +1.04R signals from -0.08R ones. Depth does not help IN-trend trades (flips sign) but does the opposite job on COUNTER-trend breakouts: top 20% of a 4-number depth score (imbalance, 4h/24h/72h change, all +-1%, signed to the trade, percentiles vs history) turns them into +0.98R/trade swing trades. 15 depth/flow features ranked on 2023-24 (483 signals), checked on 2025-26 (579 signals): same sign.
3. 7.1 (regime PDF): "skip a trade when the book leans against it" (36 variants): total R fell in nearly every variant. NOT adopted. Ten regime filters for trend sleeves: nothing consistent.
4. 7.2: swing sleeve added; paper-only until about 15 real signals, then 7.4 plan says LIVE from day one with a stop rule (pause if the first 8 are all losers). Live depth comes from our own collector (started 23-24 Oct 2026); it must PASS depth_check.py against Binance's bookDepth files first. Rebuilt features give 1,097 signals vs 1,062 in the reference.
5. Status 15 Nov 2026: swing.py logs paper signals only. 10 counter-trend signals 29 Oct - 4 Nov, S4 0.29-0.69, none flagged, no swing trade yet. v7.5.3 contains NO depth or swing logic. ETH depth-swing sleeve: in-sample negative, rejected.

## 3. Mistakes we keep making (check every new idea against this list)
1. Re-testing depth/order-book/order-flow as a trend FILTER: done at least four times (depth research 27+60 tests, 7.1 depth veto 36 variants, ETH depth sleeve, Claude Science order-flow). It fails OOS every time. Depth works only as the counter-trend selector.
2. Thresholds or horizons chosen AFTER seeing results (ensemble from about 25 combos, 2.5h/5.5h candle picks, "keep only change >= -5%", 7.5 flags, Williams breakout): flag it, never present as evidence.
3. Reporting the in-sample number as the expectation: 7.3 440R -> 364R; 7.4 410R/37.3 -> 328R/27.6; 7.5.3 67 -> 38. Always state the honest figure first.
4. Look-ahead and ordering bugs: size factor scaled in trade-list order (inflated 7.3/7.4); open 1h bar used for entry flags (7.5); spot instead of perp prices (-19% R); OI history only 5 days instead of 30 (7.5.3 live, fixed 13 Nov).
5. Version names that change meaning: "7.4" meant the 50-day candidate first and the lookback ensemble later. Never reuse a version number; write what a version contains.
6. Mixed R units: v6/7.x sleeve = 1R each; 7.4 trend sleeves = 1/3R each; 7.5.3 uses a $1 budget with per-sleeve weights. Compare versions only in the same unit.
7. Many comparisons: about 300 in the depth study, about 600 by 7.4, about 1,000 in the Science campaign, about 2,500 BTC scans. Expect p 0.03-0.05 results by luck.
8. Plans that changed without notice: swing sleeve "paper until 15 signals" (v7) then "live from day one" (7.4 plan) then absent from 7.5.3 alerts. Record the current status explicitly.
9. Marking something rejected, then re-proposing it under a new name (pullback entries, 50d direction, drawdown brakes, partial exits, ML meta-labelling, funding filters on trend).
10. Trusting sample size: swing 84 trades, reversal 34 trades, R1 214 trades, RE 33 trades. Label them with n.

## 4. What is NOT recoverable
Versions before v6 (v1-v5), the exact decision dates and the chat discussion that led to each rule, the 7.5.1 intermediate write-up and the Claude Science per-video results. If any of those matter, ask Claude Science for its campaign log or re-export the old chat.

## 5. Rules for keeping this history alive
- Every new version or rejected idea is appended here (date, what, numbers, n, variants tried) and the file is re-sent to the user and re-published to the loop artifact.
- The project skill carries the timeline (section 1) and the mistakes list (section 3); the full text lives in this file in the repo/artifact.
- Keep the six PDFs and this file together in the GitHub repo (folder docs/btc_history/) so any new session can clone them.
