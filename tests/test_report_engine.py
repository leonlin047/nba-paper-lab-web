"""Offline tests: all game reports include honest moneyline, spread and total observations."""
import pathlib,sys,unittest,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from report_engine import team,summary,build_reports,model_total

G={"id":"42","date":"2026-10-25T01:00:00Z","home":"MIL","away":"CHI","status":"pre"}
P={"event_id":"42","home_win_probability":.535}
M={"event_id":"42","moneyline":{"home_no_vig_probability":.52},
   "spread":{"home_line":-1.5,"home_cover_probability_experimental":.525},
   "total":{"line":234.5}}
class Tests(unittest.TestCase):
 def test_cn_team_names(self):
  self.assertEqual(team("MIL"),"密爾瓦基公鹿")
  self.assertEqual(team("GS"),"金州勇士")
  self.assertEqual(team("WSH"),"華盛頓巫師")
 def test_every_market_appears_in_report(self):
  for m in [M,None,{"event_id":"42","spread":None,"total":{"line":240.5}}]:
   text=summary(G,P,m,None)
   self.assertTrue(100<=len(text)<=200,(len(text),text))
   for market in ("獨贏","讓分","大小"):
    self.assertIn(market,text)
 def test_total_model_no_future_leakage(self):
  finals=[]
  for n in range(40):
   finals.append({"id":str(n),"date":f"2026-10-{10+n//5:02d}T01:00:00Z","home":"MIL" if n%2 else "CHI","away":"CHI" if n%2 else "MIL","home_score":108+n%8,"away_score":102+n%7})
  out=model_total(G,finals,220.5)
  self.assertIsNotNone(out)
  self.assertIsNotNone(out["over_probability_experimental"])
  self.assertGreater(out["league_sample_size"],0)
  self.assertIsNone(model_total(G,[{"date":"2026-10-26T00:00:00Z",**finals[0]}],220.5))
 def test_reports(self):
  r=build_reports([G],[P],[M],"2026-10-24T00:00:00Z")
  self.assertEqual(len(r),1)
  self.assertEqual(r[0]["home_zh"],"密爾瓦基公鹿")
  self.assertIn("moneyline",r[0]["markets"])
  self.assertIn("spread",r[0]["markets"])
  self.assertIn("total",r[0]["markets"])
  self.assertFalse(r[0]["news_verified"])
 def test_published_report_integrity(self):
  path=pathlib.Path(__file__).resolve().parents[1]/"data/reports.json"
  if not path.exists():self.skipTest("First report collection pending")
  d=json.loads(path.read_text())
  for report in d.get("reports",[]):
   body=report["report_zh"]
   self.assertTrue(100<=len(body)<=200,report.get("event_id"))
   self.assertTrue(all(key in body for key in ("獨贏","讓分","大小")))

if __name__=="__main__":unittest.main()
