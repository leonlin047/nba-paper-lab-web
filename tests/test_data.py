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
 def test_dashboard_assets(self):
  html=(ROOT/"index.html").read_text()
  self.assertIn('id="research"',html)
  self.assertIn('research-dashboard.js',html)
  self.assertIn('game-details.js',html)
  self.assertTrue((ROOT/"research-dashboard.js").exists())
  self.assertTrue((ROOT/"game-details.js").exists())
if __name__=="__main__":unittest.main()
