"""BTC historical simulator. No live order or credential handling."""
import argparse
import csv
import datetime as dt
import json
import math
import pathlib
import urllib.request
from dataclasses import dataclass

DAY = 86400

@dataclass
class Config:
    capital: float = 10000
    window: int = 20
    dip: float = .03
    stop: float = .05
    target: float = .10
    risk: float = .01
    allocation: float = .25
    fee: float = .006
    slippage: float = .001

def validate(rows):
    if len(rows) < 22:
        raise ValueError('Need at least 22 completed daily candles')
    for i, r in enumerate(rows):
        if not all(math.isfinite(float(r[k])) for k in ('open','high','low','close','volume')):
            raise ValueError('Non-finite data')
        if not (0 < r['low'] <= min(r['open'],r['close']) <= max(r['open'],r['close']) <= r['high']) or r['volume'] < 0:
            raise ValueError('Invalid OHLCV')
        if i and r['time'] - rows[i-1]['time'] != DAY:
            raise ValueError('Duplicate, unordered, or missing daily candle')
    return rows

def load(path):
    with open(path, newline='') as f:
        return validate([{k: int(v) if k == 'time' else float(v) for k,v in r.items()} for r in csv.DictReader(f)])

def fetch(start, end, path):
    """End is exclusive UTC; only completed daily candles are retained."""
    begin = int(dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp())
    finish = int(dt.datetime.fromisoformat(end).replace(tzinfo=dt.timezone.utc).timestamp())
    if begin >= finish or finish > int(dt.datetime.now(dt.timezone.utc).timestamp()) // DAY * DAY:
        raise ValueError('Use start < end, with end no later than today UTC')
    found = {}
    cursor = begin
    while cursor < finish:
        stop = min(cursor + 299 * DAY, finish)
        url = f'https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start={cursor}&end={stop}'
        req = urllib.request.Request(url, headers={'User-Agent':'BTC-History-Simulator/1.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data, list):
            raise ValueError(f'Unexpected API response: {data}')
        for t, low, high, op, close, volume in data:
            if begin <= t < finish:
                found[t] = dict(time=t,open=op,high=high,low=low,close=close,volume=volume)
        cursor = stop
    rows = validate(sorted(found.values(), key=lambda r:r['time']))
    if rows[0]['time'] != begin or rows[-1]['time'] != finish-DAY:
        raise ValueError('Source did not cover the requested range')
    write_csv(path, rows)
    return rows

def write_csv(path, rows):
    pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True)
    if rows:
        with open(path,'w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)

def backtest(rows, c, start_index=None):
    validate(rows)
    if c.window < 2 or c.window >= len(rows) or c.capital <= 0:
        raise ValueError('Invalid window/capital')
    if not all(0 < x < 1 for x in (c.dip,c.stop,c.target,c.risk,c.allocation)) or not all(0 <= x < 1 for x in (c.fee,c.slippage)):
        raise ValueError('Invalid percentages')
    first = max(c.window, start_index or c.window)
    cash=c.capital; position=None; trades=[]; curve=[]; peak=c.capital; drawdown=0
    for i in range(first,len(rows)):
        bar=rows[i]; previous=rows[i-1]
        # Signals use only completed candles strictly before this bar.
        average=sum(r['close'] for r in rows[i-c.window:i])/c.window
        if position is None and previous['close'] < average*(1-c.dip):
            entry=bar['open']*(1+c.slippage)
            # Include fees and modeled stop slippage in planned risk sizing.
            loss_per_btc=entry*(1+c.fee)-entry*(1-c.stop)*(1-c.slippage)*(1-c.fee)
            quantity=min(cash*c.risk/loss_per_btc,cash*c.allocation/(entry*(1+c.fee)))
            cost=quantity*entry*(1+c.fee); cash-=cost
            position=dict(entry=entry,quantity=quantity,cost=cost,entry_time=bar['time'])
        if position:
            p=position; stop=p['entry']*(1-c.stop); target=p['entry']*(1+c.target)
            price=None; reason=None
            # Gaps fill at open. If both intrabar levels touch, assume stop first.
            if bar['open'] <= stop: price=bar['open']; reason='stop_gap'
            elif bar['open'] >= target: price=target; reason='target'
            elif p['entry_time'] != bar['time'] and previous['close'] >= average:
                price=bar['open']; reason='mean_recovery'
            elif bar['low'] <= stop: price=stop; reason='stop'
            elif bar['high'] >= target: price=target; reason='target'
            elif i == len(rows)-1: price=bar['close']; reason='end_of_test'
            if price is not None:
                fill=price*(1-c.slippage); proceeds=p['quantity']*fill*(1-c.fee); cash+=proceeds
                trades.append(dict(entry_time=p['entry_time'],exit_time=bar['time'],entry=p['entry'],exit=fill,btc=p['quantity'],pnl=proceeds-p['cost'],reason=reason))
                position=None
        equity=cash+(position['quantity']*bar['close']*(1-c.slippage)*(1-c.fee) if position else 0)
        peak=max(peak,equity); drawdown=max(drawdown,1-equity/peak)
        curve.append(dict(time=bar['time'],equity=equity))
    # Benchmark starts at the same open and pays identical modeled costs.
    hold=c.capital/(rows[first]['open']*(1+c.slippage)*(1+c.fee))*rows[-1]['close']*(1-c.slippage)*(1-c.fee)
    summary=dict(initial_usd=c.capital,final_usd=cash,return_pct=100*(cash/c.capital-1),buy_hold_return_pct=100*(hold/c.capital-1),max_daily_close_drawdown_pct=100*drawdown,trades=len(trades),win_rate_pct=100*sum(t['pnl']>0 for t in trades)/len(trades) if trades else 0,start=dt.datetime.fromtimestamp(rows[first]['time'],dt.timezone.utc).isoformat(),end=dt.datetime.fromtimestamp(rows[-1]['time'],dt.timezone.utc).isoformat(),config=vars(c))
    return summary,trades,curve

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    download=sub.add_parser('download'); download.add_argument('--start',required=True); download.add_argument('--end',required=True); download.add_argument('--output',default='data/btc.csv')
    run=sub.add_parser('backtest'); run.add_argument('--csv',default='data/btc.csv'); run.add_argument('--output',default='results')
    for key, field in Config.__dataclass_fields__.items():
        run.add_argument('--'+key.replace('_','-'),type=field.type,default=field.default)
    args=parser.parse_args()
    if args.command == 'download':
        rows=fetch(args.start,args.end,args.output); print(f'Saved {len(rows)} verified daily candles'); return
    rows=load(args.csv); c=Config(**{k:getattr(args,k) for k in Config.__dataclass_fields__})
    output=pathlib.Path(args.output); output.mkdir(parents=True,exist_ok=True)
    summaries={}
    for name, first in [('full',c.window),('holdout',max(c.window,int(len(rows)*.7)))]:
        summary,trades,curve=backtest(rows,c,first); summaries[name]=summary
        write_csv(output/f'{name}_trades.csv',trades); write_csv(output/f'{name}_equity.csv',curve)
    (output/'summary.json').write_text(json.dumps(summaries,indent=2))
    print(json.dumps(summaries,indent=2))

if __name__ == '__main__':
    main()
