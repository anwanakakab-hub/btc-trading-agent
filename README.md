# BTC historical trading agent

Python 3.10+; standard library only. Simulated spot BTC-USD trades only: no exchange credentials, leverage, shorts, or live orders.

## Run

Unzip, open a terminal in `btc-agent`, then:

```sh
python agent.py backtest --csv data/btc.csv
python -m unittest -v
```

Download another period (UTC end date is exclusive):

```sh
python agent.py download --start 2023-01-01 --end 2026-10-24 --output data/btc.csv
python agent.py backtest --stop 0.05 --target 0.10 --capital 10000
```

Internet access is required only for downloads. Custom CSV columns: `time,open,high,low,close,volume`, with Unix seconds, ascending uninterrupted UTC daily candles. Invalid/missing data fails explicitly. Download failures never substitute fabricated prices.

## Default strategy

- Buy at the next daily open when the previous close is more than 3% below the 20-day simple moving average.
- Exit when the previous close recovers to its moving average, at the next open; or use a 5% stop / 10% profit target from the actual modeled entry price.
- One long position at a time. Maximum 25% of available cash per entry, additionally sized for a planned 1% account loss including modeled costs. Gaps can exceed that planned risk.
- Starting capital: USD 10,000. Assumed fee: 0.6% per side; adverse slippage: 0.1% per side. Replace with your actual trading tier and execution assumptions.
- Stops and targets can trigger on the entry day. If both touch, stop takes priority. Gap-down stops execute at the opening price, with slippage. Profit targets conservatively fill at target even on gap-up opens.
- Liquidate remaining holdings at the final close with costs. Equity and drawdown use daily closing liquidation value; intraday drawdown can be worse.

## Outputs and interpretation

`results/summary.json`: returns, closed-trade count, win rate, closing-equity drawdown, and identical-period buy-and-hold after the same costs. CSVs contain individual trades and daily equity. All values are USD, not CAD; taxes, market impact, outages, funding, cash interest and exchange minimum order sizes are excluded.

The included data is the Coinbase BTC-USD daily candle API response retrieved during this build, filtered to 2025-11-10 through 2026-10-23 UTC inclusive. Raw response is included for provenance. No synthetic data is used in performance results. Synthetic candles are used only in unit tests.

`full` begins after 20 warm-up days. `holdout` resets cash and begins at the last 30% of available candles, using preceding history solely for indicator warm-up. Parameters were fixed before inspecting results, with no optimization. The holdout overlaps the full run and is not an independent second market sample. This short sample cannot establish a profitable strategy. Test longer ranges and differing fee/slippage assumptions before drawing conclusions.

This implements a definition of a dip and recovery; it cannot identify future bottoms or tops. Historical performance does not promise future returns. A stop price is not a guaranteed execution price. No live trading is enabled.

## Sources

- Candle API and schema: https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles
- Requested endpoint: https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400
- Stop execution risk: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15

The endpoint returned 350 rows despite the documentation describing a 300-candle limit. The downloader uses explicit ranges below 300 days and verifies completeness instead of relying on the undocumented larger default response.
