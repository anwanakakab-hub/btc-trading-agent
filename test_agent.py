import unittest
from agent import Config, backtest, validate

def fixture():
    return [dict(time=i*86400,open=100.,high=101.,low=99.,close=100.,volume=1.) for i in range(25)]

class ExecutionTests(unittest.TestCase):
    def test_flat_market_no_trades(self):
        result,trades,_=backtest(fixture(),Config())
        self.assertEqual(trades,[])
        self.assertEqual(result['final_usd'],10000)

    def test_stop_wins_ambiguous_bar_and_fees(self):
        rows=fixture(); rows[19].update(open=90.,low=89.,high=91.,close=90.)
        rows[20].update(open=90.,low=70.,high=120.,close=100.)
        result,trades,_=backtest(rows,Config())
        self.assertEqual(trades[0]['reason'],'stop')
        self.assertLess(trades[0]['pnl'],0)
        self.assertLessEqual(-trades[0]['pnl'],100.00001)

    def test_gap_can_exceed_planned_risk(self):
        rows=fixture(); rows[19].update(open=90.,low=89.,high=91.,close=90.)
        rows[20].update(open=90.,low=89.,high=91.,close=90.)
        rows[21].update(open=60.,low=59.,high=61.,close=60.)
        _,trades,_=backtest(rows,Config())
        self.assertEqual(trades[0]['reason'],'stop_gap')
        self.assertLess(trades[0]['pnl'],-100)

    def test_missing_candle_rejected(self):
        rows=fixture(); del rows[4]
        with self.assertRaises(ValueError): validate(rows)

if __name__=='__main__': unittest.main()
