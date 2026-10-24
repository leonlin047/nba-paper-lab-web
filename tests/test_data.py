#!/usr/bin/env python3
"""Offline smoke tests for published NBA snapshots. No external requests."""
import json,pathlib,unittest,datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
class DataTests(unittest.TestCase):
 def test_games(self):
  p=ROOT/"data/games.json"
  if not p.exists():self.skipTest("First collection pending")
  d=json.loads(p.read_text())
  self.assertIsInstance(d["games"],list)
  ids=[x["id"] for x in d["games"]]
  self.assertEqual(len(ids),len(set(ids)))
  for g in d["games"]:
   self.assertIn(g["status"],("pre","in","post"))
   self.assertTrue(g["home"] and g["away"] and g["home"]!=g["away"])
 def test_research(self):
  d=json.loads((ROOT/"data/research.json").read_text())
  self.assertIsInstance(d["predictions"],list)
  for p in d["predictions"]:
   self.assertGreaterEqual(p["home_win_probability"],0)
   self.assertLessEqual(p["home_win_probability"],1)
   self.assertFalse(p.get("validated",False))
 def test_joined_market_data(self):
  p=ROOT/"data/games.json"
  if not p.exists():self.skipTest("Collection pending")
  data=json.loads(p.read_text())
  games={str(x["id"]) for x in data["games"]}
  for m in data.get("market_snapshots",[]):
   self.assertIn(str(m["event_id"]),games)
   self.assertTrue(m.get("provider"))
   self.assertTrue(m.get("captured_at_utc"))
   self.assertEqual(m.get("rights_status"),"review")
   money=m.get("moneyline",{})
   h,a=money.get("home_no_vig_probability"),money.get("away_no_vig_probability")
   if h is not None and a is not None:self.assertAlmostEqual(h+a,1,places=4)
   spread=m.get("spread",{})
   hline,aline=spread.get("home_line"),spread.get("away_line")
   if hline is not None and aline is not None:self.assertAlmostEqual(hline,-aline,places=4)
 def test_market_coverage_is_not_inflated(self):
  d=json.loads((ROOT/"data/games.json").read_text())
  coverage=d.get("market_coverage")
  if coverage is None:self.skipTest("New scoreboard odds source has not published")
  markets=d.get("market_snapshots",[])
  complete=set()
  for x in markets:
   ml=x.get("moneyline") or {}
   sp=x.get("spread") or {}
   tl=x.get("total") or {}
   price=x.get("observed_prices") or {}
   if (ml.get("home_decimal") is not None and ml.get("away_decimal") is not None
       and sp.get("home_line") is not None and tl.get("line") is not None
       and all(price.get(k) is not None for k in (
         "spread_home_american","spread_away_american",
         "total_over_american","total_under_american"))):
    complete.add(str(x["event_id"]))
  self.assertEqual(coverage["complete_three_market_events"],len(complete))
  self.assertEqual(coverage["paired_market_events"],len({str(x["event_id"]) for x in markets}))
  self.assertFalse(coverage["taiwan_sportslottery_connected"])
  self.assertLessEqual(coverage["complete_three_market_events"],coverage["future_game_count"])
 def test_coverage_has_public_ui(self):
  html=(ROOT/"index.html").read_text()
  js=(ROOT/"research-dashboard.js").read_text()
  self.assertIn('id="pl-market-coverage"',html)
  self.assertIn("實際獨贏賠率",js)
  self.assertIn("實際讓分賠率",js)
  self.assertIn("實際大小分賠率",js)
 def test_playsport_status_is_not_misrepresented(self):
  p=ROOT/"data/playsport_status.json"
  if not p.exists():self.skipTest("First probe pending")
  d=json.loads(p.read_text())
  self.assertEqual(d.get("published_market_data"),False)
  self.assertEqual(d.get("redistribution_authorized"),False)
  self.assertIn(d.get("fetch_status"),("reachable","http_error","error","unknown"))
 def test_dashboard_assets(self):
  html=(ROOT/"index.html").read_text()
  self.assertIn('id="research"',html)
  self.assertIn('research-dashboard.js',html)
  self.assertIn('game-details.js',html)
  self.assertTrue((ROOT/"research-dashboard.js").exists())
  self.assertTrue((ROOT/"scripts/market_model.py").exists())
  self.assertTrue((ROOT/"game-details.js").exists())
if __name__=="__main__":unittest.main()
