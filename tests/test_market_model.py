"""Deterministic, offline odds/margin unit tests."""
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from market_model import (american_to_decimal,no_vig_probabilities,
 home_spread_from_pickcenter,experimental_cover_probability,build_market)

class MarketTests(unittest.TestCase):
 def test_us_prices(self):
  self.assertEqual(american_to_decimal(-110),1.909091)
  self.assertEqual(american_to_decimal(120),2.2)
  for x in (None,0,90,-90,"not a price",float("nan")):
   self.assertIsNone(american_to_decimal(x))
 def test_fair_market(self):
  market=no_vig_probabilities(2,2)
  self.assertEqual(market["home"],0.5)
  self.assertEqual(market["away"],0.5)
  self.assertEqual(market["overround"],0)
  self.assertIsNone(no_vig_probabilities(1,2))
 def test_spread_team_sign(self):
  self.assertEqual(home_spread_from_pickcenter(-1.5,"MIL -1.5","MIL","CHI"),-1.5)
  self.assertEqual(home_spread_from_pickcenter(2.5,"ATL -2.5","CHA","ATL"),2.5)
  self.assertIsNone(home_spread_from_pickcenter(-2.5,"ATL -2.5","CHA","ATL"))
  self.assertIsNone(home_spread_from_pickcenter(None,"UNKNOWN -2.5","CHA","ATL"))
 def test_probability_monotonic(self):
  a=experimental_cover_probability(.5,0)
  b=experimental_cover_probability(.5,3.5)
  c=experimental_cover_probability(.5,-3.5)
  self.assertEqual(a,.5)
  self.assertLess(c,a)
  self.assertGreater(b,a)
  self.assertIsNone(experimental_cover_probability(None,3.5))
 def test_match_snapshot(self):
  pick=dict(provider="Demo",home_moneyline=-118,away_moneyline=-102,
   spread=2.5,details="ATL -2.5",over_under=227.5,captured_at_utc="2026-10-24T01:00:00Z")
  game=dict(id="123",date="2026-10-24T06:00:00Z",home="CHA",away="ATL")
  pred=dict(home_win_probability=.4)
  m=build_market(pick,game,pred)
  self.assertEqual(m["event_id"],"123")
  self.assertEqual(m["spread"]["home_line"],2.5)
  self.assertEqual(m["spread"]["away_line"],-2.5)
  self.assertAlmostEqual(m["moneyline"]["home_no_vig_probability"]+m["moneyline"]["away_no_vig_probability"],1,places=4)
  self.assertGreater(m["spread"]["home_cover_probability_experimental"],.4)
  self.assertEqual(m["rights_status"],"review")
 def test_whole_line_push_is_unresolved(self):
  game=dict(id="1",date="2026-10-25T00:00:00Z",home="MIL",away="CHI")
  p=dict(spread=-2,details="MIL -2",provider="Test")
  m=build_market(p,game,dict(home_win_probability=.55))
  self.assertTrue(m["spread"]["whole_point_push_possible"])
  self.assertIsNone(m["spread"]["away_cover_probability_experimental"])

if __name__=="__main__":unittest.main()
