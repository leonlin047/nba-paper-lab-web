"""Score-model validation and market-probability tests with fully synthetic scored history."""
import datetime as dt,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from score_model import evaluate_and_project,market_probabilities,sample_model

def history():
 start=dt.datetime(2025,1,1,tzinfo=dt.timezone.utc)
 out=[]
 for i in range(260):
  date=(start+dt.timedelta(days=i)).isoformat()
  a,b=("MIL","CHI") if i%2==0 else ("CHI","MIL")
  out.append({"id":f"train{i}","date":date,"season_end":2025,"home":a,"away":b,
              "home_score":100+(i%14),"away_score":98+(i%11),"phase":"regular"})
 return out
def matchup():
 return {"id":"game2027","date":"2026-10-25T00:00:00Z","season_year":2027,
  "season_phase":2,"home":"MIL","away":"CHI","status":"pre"}
class ScoreTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.history=history()
  cls.holdout=[]
  start=dt.datetime(2026,1,1,tzinfo=dt.timezone.utc)
  for i in range(60):
   date=(start+dt.timedelta(days=i)).isoformat()
   cls.holdout.append({"id":f"holdout{i}","date":date,"season_end":2026,
     "home":"MIL" if i%2 else "CHI","away":"CHI" if i%2 else "MIL",
     "home_score":106+i%15,"away_score":101+i%12,"phase":"regular"})
 def test_train_only_sigma_and_holdout_mae(self):
  m={"event_id":"game2027","home_win_probability":.58}
  forecasts,metrics=evaluate_and_project(self.history+self.holdout,[matchup()],[m])
  self.assertEqual(metrics["holdout_margin_n"],60)
  self.assertGreater(metrics["train_margin_n"],150)
  self.assertIsNotNone(metrics["margin_mae"])
  self.assertIsNotNone(metrics["total_mae"])
  self.assertIsNone(metrics["ats_brier"])
  self.assertFalse(metrics["validated_against_historical_odds"])
  self.assertIsNotNone(forecasts["game2027"]["margin_sigma"])
 def test_future_scores_cannot_affect_prior_projection(self):
  m={"event_id":"game2027","home_win_probability":.58}
  first,_=evaluate_and_project(self.history+self.holdout,[matchup()],[m])
  after={"id":"after","date":"2026-10-27T00:00:00Z","season_end":2027,
    "home":"MIL","away":"CHI","home_score":190,"away_score":70,"phase":"regular"}
  later,_=evaluate_and_project(self.history+self.holdout+[after],[matchup()],[m])
  self.assertEqual(first["game2027"]["expected_margin"],later["game2027"]["expected_margin"])
  self.assertEqual(first["game2027"]["expected_total"],later["game2027"]["expected_total"])
 def test_market_probability_requires_real_lines(self):
  m={"event_id":"game2027","home_win_probability":.58}
  forecasts,_=evaluate_and_project(self.history+self.holdout,[matchup()],[m])
  f=forecasts["game2027"]
  self.assertEqual(market_probabilities(f,None),{"spread":None,"total":None})
  d=market_probabilities(f,{"spread":{"home_line":-2.5},"total":{"line":218.5}})
  self.assertTrue(0<d["spread"]["home"]<1)
  self.assertTrue(0<d["total"]["over"]<1)
  self.assertEqual(d["spread"]["home"]+d["spread"]["away"],1)
if __name__=="__main__":unittest.main()
